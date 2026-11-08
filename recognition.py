"""Local notation import. Timing is measured in quarter-note beats."""
import io
import re
import subprocess
from pathlib import Path
import fitz
import numpy as np
import mido
from music21 import converter, tempo

ROOT = Path(__file__).resolve().parent
AUDIVERIS = ROOT / 'engines/Audiveris.app/Contents/MacOS/Audiveris'
TUNINGS = {'standard': [64,59,55,50,45,40], 'drop-d': [64,59,55,50,45,38], 'dadgad': [62,57,55,50,45,38]}


def read_score(path):
    # Reject broken exports rather than silently playing implausible rhythms.
    import zipfile
    import xml.etree.ElementTree as ET
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist()) > 60*1024*1024:
                raise ValueError('The uncompressed score is too large.')
            container = ET.fromstring(z.read('META-INF/container.xml'))
            ref = next(e.attrib['full-path'] for e in container.iter() if e.tag.split('}')[-1]=='rootfile')
            xml = z.read(ref)
    else:
        xml = Path(path).read_bytes()
    root = ET.fromstring(xml)
    for part in root.findall('part'):
        divisions = None
        for measure in part.findall('measure'):
            for item in measure:
                if item.tag == 'attributes' and item.find('divisions') is not None:
                    divisions = float(item.findtext('divisions'))
                if item.tag in ('note','backup','forward') and item.find('duration') is not None and (divisions is None or divisions <= 0):
                    raise ValueError('The reader produced incomplete rhythm data. Try a clearer PDF or import corrected MusicXML. No misleading playback has been generated.')
    score = converter.parse(str(path))
    warnings = ['Automatic recognition can misread pitches, rhythms, and repeats. Compare the notes with your PDF.']
    try:
        score = score.expandRepeats()
    except Exception:
        warnings.append('Repeats could not be expanded. Check the playback order.')
    score = score.stripTies()
    marks = list(score.recurse().getElementsByClass(tempo.MetronomeMark))
    bpm = next((m.getQuarterBPM() for m in marks if m.getQuarterBPM()), 100)
    if len(marks) > 1:
        warnings.append('Playback uses one tempo. Changes of tempo within the score are not reproduced.')
    parts = list(score.parts) or [score]
    notes = []
    for pi, part in enumerate(parts):
        for n in part.flatten().notes:
            if not hasattr(n, 'pitches'):
                continue
            duration = float(n.duration.quarterLength)
            if duration <= 0:
                continue
            for p in n.pitches:
                notes.append({'pitch': int(p.midi), 'start': float(n.offset), 'duration': duration,
                              'velocity': 90, 'part': pi})
    if not notes:
        raise ValueError('No playable notes were found. Try a clearer score or import MusicXML.')
    return {'notes': sorted(notes, key=lambda n: (n['start'], n['pitch'])), 'bpm': round(bpm),
            'parts': [p.partName or f'Part {i+1}' for i,p in enumerate(parts)], 'warnings': warnings}


def staff_pdf(path, folder, update):
    if not AUDIVERIS.exists():
        raise ValueError('The local sheet-music reader is missing. See README.md for setup.')
    update('Reading the printed notation. This can take several minutes.')
    out = folder / 'recognized'
    out.mkdir(exist_ok=True)
    with (folder / 'recognition.log').open('w') as log:
        try:
            result = subprocess.run([str(AUDIVERIS), '-batch', '-transcribe', '-export', '-output', str(out), '--', str(path)],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=900)
        except subprocess.TimeoutExpired:
            raise ValueError('Recognition took longer than 15 minutes. Try a shorter PDF.')
    files = sorted(out.rglob('*.mxl')) + sorted(out.rglob('*.musicxml'))
    if not files:
        raise ValueError('No music could be recognized. Use a clear, straight scan of printed staff notation, or select Guitar tab for tablature.')
    notes, parts, warnings, offset = [], [], [], 0
    bpm = 100
    for f in files:
        data = read_score(f)
        if not notes:
            bpm = data['bpm']
        pi = len(parts)
        for n in data['notes']:
            notes.append(dict(n, start=n['start']+offset, part=n['part']+pi))
        parts.extend(data['parts'])
        warnings.extend(data['warnings'])
        offset = max(n['start'] + n['duration'] for n in notes)
    if result.returncode or 'Error visiting' in (folder / 'recognition.log').read_text():
        warnings.append('The reader reported a problem. The available result may be incomplete.')
    return {'notes': notes, 'parts': parts, 'bpm': bpm, 'warnings': list(dict.fromkeys(warnings)), 'method': 'Printed sheet music'}


def tab_systems(page):
    """Find six evenly spaced horizontal string lines, including raster scans."""
    pix = page.get_pixmap(matrix=fitz.Matrix(2,2), colorspace=fitz.csGRAY, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width)
    rows = np.where((arr < 220).sum(axis=1) > pix.width * .35)[0]
    lines = []
    for run in np.split(rows, np.where(np.diff(rows) > 1)[0]+1):
        if len(run):
            lines.append(float(np.mean(run))/2)
    systems = []
    i = 0
    while i+5 < len(lines):
        group = lines[i:i+6]
        gaps = np.diff(group)
        if 3 <= np.median(gaps) <= 30 and max(gaps)-min(gaps) < max(1.5, np.median(gaps)*.2):
            systems.append(group)
            i += 6
        else:
            i += 1
    return systems


def tab_pdf(path, folder, tuning, step, update):
    notes, offset, missed = [], 0, []
    with fitz.open(path) as doc:
        for pn, page in enumerate(doc):
            update(f'Reading guitar tab, page {pn+1} of {len(doc)}…')
            systems = tab_systems(page)
            # PDF glyph positions preserve string and fret alignment.
            glyphs = []
            for block in page.get_text('rawdict')['blocks']:
                for line in block.get('lines', []):
                    chars = [c for span in line['spans'] for c in span['chars']]
                    text = ''.join(c['c'] for c in chars)
                    for match in re.finditer(r'\d{1,2}', text):
                        cs = chars[match.start():match.end()]
                        glyphs.append((int(match.group()), (cs[0]['bbox'][0]+cs[-1]['bbox'][2])/2,
                                       sum(c['bbox'][1]+c['bbox'][3] for c in cs)/(2*len(cs))))
            # OCR is reserved for image-only pages. No files leave the Mac.
            if systems and not any(abs(y-line)<float(np.median(np.diff(system)))*.42 for _,x,y in glyphs for system in systems for line in system):
                ocr = ROOT / 'engines/tab-ocr'
                if ocr.exists():
                    import json
                    img = folder / f'ocr-{pn}.png'
                    page.get_pixmap(matrix=fitz.Matrix(3,3)).save(img)
                    result = subprocess.run([str(ocr),str(img)],capture_output=True,text=True,timeout=90,check=True)
                    for item in json.loads(result.stdout):
                        if re.fullmatch(r'\d{1,2}',item['text']):
                            glyphs.append((int(item['text']),item['x']*page.rect.width,item['y']*page.rect.height))
            page_count = 0
            for system in systems:
                gap = float(np.median(np.diff(system)))
                hits = []
                for fret,x,y in glyphs:
                    si = min(range(6),key=lambda i:abs(system[i]-y))
                    if fret <= 24 and abs(system[si]-y) < gap*.42:
                        hits.append((x,si,fret))
                hits.sort()
                columns = []
                for x,si,fret in hits:
                    if not columns or x-columns[-1][0] > max(3,gap*.45):
                        columns.append((x,[]))
                    columns[-1][1].append((si,fret))
                for ci,(_,frets) in enumerate(columns):
                    for si,fret in set(frets):
                        notes.append({'pitch':TUNINGS[tuning][si]+fret,'start':offset+ci*step,
                                      'duration':step*.9,'velocity':90,'part':0,'string':si+1,'fret':fret})
                        page_count += 1
                offset += len(columns)*step
            if not page_count:
                missed.append(str(pn+1))
    if not notes:
        raise ValueError('No six-string tab was detected. This reader needs six clear horizontal lines and readable fret numbers. Try a sharper PDF, or import MusicXML.')
    warnings = ['Tab timing is approximate: each note column is given the same length. Edit starts and durations to match the rhythm.',
                'Check every fret and chord. Bends, slides, hammer-ons, repeats, and other playing techniques are not interpreted.',
                'Uses the tuning selected at import, with no capo. Add a transpose amount for a capo.']
    if missed:
        warnings.append('No tab notes found on page(s) '+', '.join(missed)+'. The result is incomplete.')
    return {'notes':notes,'bpm':100,'parts':['Guitar'],'warnings':warnings,'method':'Guitar tab · approximate rhythm'}


def make_midi(notes, bpm, program=0, transpose=0, length=0):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo',tempo=mido.bpm2tempo(bpm),time=0))
    track.append(mido.Message('program_change',program=program,time=0))
    events=[]
    for n in notes:
        pitch=n['pitch']+transpose
        if not 0 <= pitch <= 127:
            raise ValueError('Transposed notes must remain within MIDI pitches 0–127.')
        events.extend([(round(n['start']*480),1,pitch,n.get('velocity',90)),
                       (max(round(n['start']*480)+1,round((n['start']+n['duration'])*480)),0,pitch,0)])
    prev=0
    for tick,on,pitch,velocity in sorted(events):
        track.append(mido.Message('note_on' if on else 'note_off',note=pitch,velocity=velocity,time=tick-prev))
        prev=tick
    track.append(mido.MetaMessage('end_of_track',time=max(0,round(length*480)-prev)))
    stream=io.BytesIO()
    mid.save(file=stream)
    return stream.getvalue()


def tab_rhythmic_pdf(path, folder, tuning, update, meter=4):
    """Read engraved tab rhythm, rejecting measures that do not balance."""
    import json
    from tab_rhythm import page_numbers, raster, read_pitches_at_stems, read_system
    bank=[];notes=[];measures=[];issues=[];offset=0;number=1;bpm=None;last=[]
    with fitz.open(path) as doc:
        for pn,page in enumerate(doc):
            update(f'Rhythm · {pn+1}/{len(doc)}')
            systems,numbers=page_numbers(page,folder,pn,ROOT/'engines/tab-ocr')
            if not systems:
                issues.append(f'page {pn+1}: no readable tab systems');continue
            if bpm is None:
                for n in numbers:
                    match=re.search(r'=\s*(\d{2,3})(?!\d)',n.get('context',''))
                    if match and 30<=int(match.group(1))<=240:
                        bpm=int(match.group(1));break
            image,scale=raster(page)
            refined=read_pitches_at_stems(page,systems,image,scale,numbers,folder,pn,ROOT/'engines/tab-ocr',bank)
            for si,system in enumerate(systems):
                result=read_system(image,scale,system,refined[si],numbers,meter)
                if result is None:
                    issues.append(f'page {pn+1}, line {si+1}: rhythm not readable');continue
                for m in result:
                    m.update(page=pn+1,system=si+1,number=number,start=offset)
                    measures.append(m)
                    if m['issues']:issues.append(f'measure {number}: '+', '.join(dict.fromkeys(m['issues'])))
                    beat=offset
                    for e in m['events']:
                        d=e['duration'];col=e.get('column')
                        if e['kind']=='rest':
                            last=[]
                        elif e['kind']=='continuation':
                            if last and all(abs(n['start']+n['duration']-beat)<.02 for n in last):
                                for n in last:n['duration']+=d
                            else:issues.append(f'measure {number}: tie without a preceding note')
                        elif col and col['frets']:
                            pitches={TUNINGS[tuning][string]+fret for string,fret in col['frets']}
                            if col.get('ghost') and last and pitches=={n['pitch'] for n in last} and all(abs(n['start']+n['duration']-beat)<.02 for n in last):
                                for n in last:n['duration']+=d
                            else:
                                last=[]
                                for string,fret in set(map(tuple,col['frets'])):
                                    n={'pitch':TUNINGS[tuning][string]+fret,'start':beat,'duration':d,'velocity':90,'part':0,'string':string+1,'fret':fret,'measure':number,'page':pn+1}
                                    notes.append(n);last.append(n)
                        beat+=d
                    offset+=m['expected'];number+=m['multiple']
    (folder/'rhythm-analysis.json').write_text(json.dumps({'measures':measures,'issues':issues,'notes':notes,'length':offset,'bpm':bpm},indent=2))
    if issues:
        raise ValueError('Rhythm needs review: '+'; '.join(issues[:4])+('.' if len(issues)<=4 else f'; and {len(issues)-4} more.')+' No timing has been guessed. Try a clearer PDF or choose Tab → Rhythm → Even for approximate playback.')
    if not notes:
        raise ValueError('No readable rhythm markings found. Select Tab → Rhythm → Even for approximate playback, or import MusicXML.')
    warnings=['Read from rhythm stems, beams, dots, rests, and ties. Measure lengths were checked against the selected meter.',
              'Guitar techniques and repeat signs are not performed. Playback follows the printed measure order.']
    if bpm is None:warnings.append('No tempo marking was read. BPM defaults to 100.')
    return {'notes':notes,'bpm':bpm or 100,'parts':['Guitar'],'length':offset,'warnings':warnings,
            'method':'Guitar tab · PDF rhythm','rhythm':'read','measures':number-1}
