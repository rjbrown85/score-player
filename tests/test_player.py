import io
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
import mido
import pytest
from music21 import stream, note, chord, meter, tempo, tie
from fastapi.testclient import TestClient
from recognition import read_score, tab_pdf, make_midi
from app import app

def make_tab(path, raster=False):
    doc=fitz.open()
    page=doc.new_page(width=600,height=350)
    page.insert_text((50,40),'Guitar practice - standard tuning',fontsize=15)
    for y in range(100,161,12):
        page.draw_line((40,y),(560,y),color=(0,0,0),width=.7)
    for x,y,f in [(100,160,'0'),(150,148,'2'),(200,136,'2'),(250,124,'0'),(300,112,'0'),(350,100,'0'),(400,100,'12')]:
        page.draw_rect(fitz.Rect(x-3,y-7,x+15,y+5),color=None,fill=(1,1,1))
        page.insert_text((x,y+4),f,fontsize=11)
    if raster:
        image=page.get_pixmap(matrix=fitz.Matrix(3,3)).tobytes('png')
        doc.close()
        doc=fitz.open();page=doc.new_page(width=600,height=350)
        page.insert_image(page.rect,stream=image)
    doc.save(path);doc.close()


def test_tab_pitch_chord_tuning(tmp_path):
    p=tmp_path/'tab.pdf';make_tab(p)
    result=tab_pdf(p,tmp_path,'standard',.5,lambda _:None)
    assert [n['pitch'] for n in result['notes']]==[40,47,52,55,59,64,76]
    assert [n['start'] for n in result['notes']]==[0,.5,1,1.5,2,2.5,3]
    assert tab_pdf(p,tmp_path,'drop-d',.5,lambda _:None)['notes'][0]['pitch']==38


def test_scanned_tab(tmp_path):
    p=tmp_path/'scan.pdf';make_tab(p,True)
    result=tab_pdf(p,tmp_path,'standard',.5,lambda _:None)
    assert [n['pitch'] for n in result['notes']]==[40,47,52,55,59,64,76]


def test_score_ties_and_chords(tmp_path):
    s=stream.Score();p=stream.Part();p.append(tempo.MetronomeMark(number=80));p.append(meter.TimeSignature('4/4'))
    a=note.Note('C4',quarterLength=1);a.tie=tie.Tie('start');b=note.Note('C4',quarterLength=1);b.tie=tie.Tie('stop');p.append([a,b,chord.Chord(['E4','G4'],quarterLength=2)]);s.insert(0,p)
    path=tmp_path/'score.musicxml';s.write('musicxml',fp=path)
    data=read_score(path)
    assert data['bpm']==80
    assert [(n['pitch'],n['start'],n['duration']) for n in data['notes']]==[(60,0,2),(64,2,2),(67,2,2)]


def test_export_round_trip():
    blob=make_midi([{'pitch':60,'start':1,'duration':.5,'velocity':90}],120,24,2)
    mid=mido.MidiFile(file=io.BytesIO(blob));track=mid.tracks[0]
    assert next(m for m in track if m.type=='note_on').note==62
    assert next(m for m in track if m.type=='note_on').time==480
    assert next(m for m in track if m.type=='note_off').time==240
    assert next(m for m in track if m.type=='program_change').program==24


def test_input_guards():
    c=TestClient(app)
    assert c.post('/api/import',files={'file':('bad.pdf',b'not pdf')}).status_code==400
    assert c.post('/api/midi',json={'notes':[{'pitch':128,'start':0,'duration':1}],'bpm':100}).status_code==422
    assert c.post('/api/midi',headers={'origin':'https://untrusted.example'},json={}).status_code==403
    assert c.get('/api/status',headers={'host':'untrusted.example'}).status_code==403
    assert c.post('/api/midi',json={'notes':[{'pitch':127,'start':0,'duration':1}],'bpm':100,'transpose':1}).status_code==400

if __name__=='__main__':
    base=Path(__file__).resolve().parents[1]/'samples'
    make_tab(base/'Guitar Practice.pdf')
    make_tab(base/'Guitar Practice Scan.pdf',True)

def test_broken_recognition_is_rejected(tmp_path):
    p=tmp_path/'broken.musicxml'
    p.write_text('<score-partwise><part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list><part id="P1"><measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note></measure></part></score-partwise>')
    with pytest.raises(ValueError,match='incomplete rhythm'):
        read_score(p)

def test_subtick_notes_still_release():
    mid=mido.MidiFile(file=io.BytesIO(make_midi([{'pitch':60,'start':0,'duration':.0001}],100)))
    events=[m for m in mid.tracks[0] if m.type in ('note_on','note_off')]
    assert events[0].type=='note_on'
    assert events[1].type=='note_off' and events[1].time>=1
