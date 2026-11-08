"""Read separate rhythm stems beneath six-line tablature.

Positions are PDF points; durations are quarter-note beats. Measures that fail
validation are returned as unresolved, never silently described as exact.
"""
import cv2
import numpy as np


def groups(values):
    values=np.asarray(values)
    return [g for g in np.split(values,np.where(np.diff(values)>1)[0]+1) if len(g)]


def raster(page, scale=4):
    import fitz
    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False)
    return (np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)<170).astype(np.uint8),scale


def components(mask):
    count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
    return [(x,y,w,h,area) for x,y,w,h,area in stats[1:] if area>3]


def read_system(image, scale, system, columns, numbers, meter=4):
    gap=float(np.median(np.diff(system)))*scale
    top=round(system[0]*scale); bottom=round(system[-1]*scale)
    # Barlines span all six strings. Merge double barlines.
    band=image[top+2:bottom-1]
    xs=np.where(band.mean(axis=0)>.82)[0]
    bars=[]
    for g in groups(xs):
        x=float(g.mean())
        if bars and x-bars[-1]<gap*.32: bars[-1]=(bars[-1]+x)/2
        else: bars.append(x)
    if len(bars)<2:
        return None
    # Separate rhythm stems terminate above the lyrics.
    y0=round(bottom+gap*.45); y1=min(image.shape[0],round(bottom+gap*2.95))
    rhythm=image[y0:y1].copy()
    vertical=cv2.morphologyEx(rhythm,cv2.MORPH_OPEN,np.ones((max(3,round(gap*.65)),1),np.uint8))
    stems=[]
    for x,y,w,h,area in components(vertical):
        if w<gap*.24 and h>=gap*.65 and bars[0]<x<bars[-1]:
            stems.append({'x':x+(w-1)/2,'y':y+y0,'end':y+h+y0-1,'height':h})
    stems.sort(key=lambda s:s['x'])
    merged=[]
    for stem in stems:
        if merged and stem['x']-merged[-1]['x']<gap*.6:
            if stem['height']>merged[-1]['height']:merged[-1]=stem
        else:merged.append(stem)
    stems=merged
    if not stems:return None
    baseline=float(np.median([s['end'] for s in stems if s['height']>gap])) if any(s['height']>gap for s in stems) else float(np.median([s['end'] for s in stems]))
    stems=[s for s in stems if abs(s['end']-baseline)<gap*.3]
    events=[]
    for stem in stems:
        x=round(stem['x']); end=round(stem['end'])
        # Horizontal beams on either side, excluding the stem itself.
        lo=max(y0,round(end-gap*.9)); hi=min(y1,end+2)
        left=image[lo:hi,max(0,round(x-gap*.65)):max(0,round(x-gap*.17))]
        right=image[lo:hi,round(x+gap*.17):round(x+gap*.65)]
        has=np.zeros(hi-lo,dtype=bool)
        for probe in (left,right):
            if probe.size:has |= probe.mean(axis=1)>.78
        beams=sum(len(g)>=2 for g in groups(np.where(has)[0]))
        duration=1/(2**min(beams,3))
        if not beams:
            # Unbeamed flags extend right from the lower part of a stem.
            probe=image[round(stem['y']):end+1,round(x+gap*.22):round(x+gap*.8)]
            if probe.size and probe.sum()>gap*gap*.06:
                duration=.5
        if not beams and duration==1 and stem['height']<gap*1.3:duration=2
        # Augmentation dots beside isolated stems.
        dotmask=image[max(y0,round(end-gap*.65)):end+2,round(x+gap*.18):round(x+gap*.8)]
        dotted=any(gap*.1<w<gap*.34 and gap*.1<h<gap*.34 and area/(w*h)>.5 for _,_,w,h,area in components(dotmask))
        if dotted and not (duration==.5 and not beams):duration*=1.5
        px=stem['x']/scale
        nearby=[(abs(col['x']-px),col) for col in columns if abs(col['x']-px)<gap/scale*.6]
        column=min(nearby,key=lambda v:v[0])[1] if nearby else None
        events.append({'x':px,'duration':duration,'kind':'note' if column else 'continuation','column':column,'beams':beams})
    # Remove thin string lines, then reconnect glyphs split by a line.
    staff=image[top:bottom+1].copy()
    horizontal=cv2.morphologyEx(staff,cv2.MORPH_OPEN,np.ones((1,max(3,round(gap*3))),np.uint8))
    clean=cv2.subtract(staff,horizontal)
    clean=cv2.morphologyEx(clean,cv2.MORPH_CLOSE,np.ones((max(2,round(gap*.14)),1),np.uint8))
    rest_candidates=[]; dots=[]
    for x,y,w,h,area in components(clean):
        cx=(x+w/2)/scale; cy=(top+y+h/2)/scale
        if not bars[0]/scale<cx<bars[-1]/scale:continue
        if any(abs(cx-col['x'])<gap/scale*.65 for col in columns):continue
        if any(abs(x+w/2-b)<gap*.3 for b in bars):continue
        if .10*gap<=w<=.36*gap and .10*gap<=h<=.36*gap and area/(w*h)>.5:
            dots.append((cx,cy));continue
        # Half rests stand above string four, whole rests hang below string three.
        if .55*gap<w<1.15*gap and .2*gap<h<.48*gap and area/(w*h)>.7:
            relative=(top+y)/scale
            if abs(relative-(system[3]-h/scale))<gap/scale*.18:
                rest_candidates.append({'x':cx,'y':cy,'duration':2,'kind':'rest','shape':'half'})
            elif abs(relative-system[2])<gap/scale*.22:
                rest_candidates.append({'x':cx,'y':cy,'duration':4,'kind':'rest','shape':'whole'})
        elif .35*gap<w<1.05*gap and .8*gap<h<1.7*gap and system[2]-.1*gap/scale<cy<system[4]:
            rest_candidates.append({'x':cx,'y':cy,'duration':.5,'kind':'rest','shape':'eighth'})
        elif .45*gap<w<1.15*gap and 1.7*gap<h<2.7*gap and system[1]<cy<system[4]:
            rest_candidates.append({'x':cx,'y':cy,'duration':1,'kind':'rest','shape':'quarter'})
    for rest in rest_candidates:
        if any(.45*gap/scale<dx-rest['x']<1.5*gap/scale and abs(dy-rest['y'])<.5*gap/scale for dx,dy in dots):rest['duration']*=1.5
        events.append(rest)
    measures=[]
    for left,right in zip(bars,bars[1:]):
        if right-left<gap*.6:continue
        local=[e.copy() for e in events if left/scale<e['x']<right/scale]
        local.sort(key=lambda e:e['x'])
        # Multi-measure rest: heavy horizontal bar with a count above the staff.
        area=image[round(top+gap*1.4):round(top+gap*3.5),round(left+gap*.5):round(right-gap*.5)]
        longrows=np.where(area.sum(axis=1)>max(gap*2,(right-left)*.5))[0] if area.size else []
        heavy=any(len(g)>gap*.2 for g in groups(longrows))
        counts=[n for n in numbers if n['text'].isdigit() and 2<=int(n['text'])<=99 and left/scale+gap/scale<n['x']<right/scale-gap/scale and system[0]-gap/scale*2.2<n['y']<system[0]-.4*gap/scale]
        multirest=int(min(counts,key=lambda n:abs(n['x']-(left+right)/(2*scale)))['text']) if heavy and counts else None
        if heavy and not multirest:
            before=[int(n['text']) for n in numbers if n['text'].isdigit() and abs(n['x']-left/scale)<gap/scale*.6 and system[0]-gap/scale<n['y']<system[0]]
            after=[int(n['text']) for n in numbers if n['text'].isdigit() and abs(n['x']-right/scale)<gap/scale*.6 and system[0]-gap/scale<n['y']<system[0]]
            if before and after and 2<=after[0]-before[0]<=99:multirest=after[0]-before[0]
        if multirest:
            local=[{'x':(left+right)/(2*scale),'duration':meter*multirest,'kind':'rest','shape':'multiple'}]
        length=sum(e['duration'] for e in local)
        # A whole rest is a full measure regardless of meter.
        if len(local)==1 and local[0].get('shape')=='whole':local[0]['duration']=meter;length=meter
        unresolved=[]
        if not local:unresolved.append('unreadable measure')
        elif not multirest and abs(length-meter)>.03:unresolved.append(f'{length:g} beats read; {meter:g} expected')
        for col in columns:
            if left/scale<col['x']<right/scale and col.get('unreadable'):unresolved.append('unreadable fret')
            if left/scale<col['x']<right/scale and not any(e.get('column') is col for e in local):unresolved.append('fret without a readable rhythm stem')
        measures.append({'left':left/scale,'right':right/scale,'events':local,'length':length,'expected':meter*(multirest or 1),'issues':unresolved,'multiple':multirest or 1})
    return measures


def page_numbers(page, folder, pn, ocr):
    import re,json,subprocess,fitz
    from recognition import tab_systems
    systems=tab_systems(page)
    items=[]
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines',[]):
            chars=[c for span in line['spans'] for c in span['chars']]
            text=''.join(c['c'] for c in chars)
            for match in re.finditer(r'\d+',text):
                cs=chars[match.start():match.end()]
                items.append({'text':match.group(),'x':(cs[0]['bbox'][0]+cs[-1]['bbox'][2])/2,'y':sum(c['bbox'][1]+c['bbox'][3] for c in cs)/(2*len(cs)),'context':text})
    if systems and not any(abs(n['y']-y)<np.median(np.diff(s))*.42 for n in items for s in systems for y in s):
        cache=folder/f'rhythm-ocr-{pn}.json'
        if cache.exists():
            raw=json.loads(cache.read_text())
        else:
            img=folder/f'ocr-{pn}.png'
            if not img.exists():page.get_pixmap(matrix=fitz.Matrix(3,3)).save(img)
            result=subprocess.run([str(ocr),str(img)],capture_output=True,text=True,timeout=90,check=True)
            raw=json.loads(result.stdout);cache.write_text(json.dumps(raw))
        items.extend(dict(n,x=n['x']*page.rect.width,y=n['y']*page.rect.height) for n in raw)
    return systems,items


def columns_for(system,numbers):
    gap=float(np.median(np.diff(system)))
    hits=[]
    for n in numbers:
        if not n['text'].isdigit() or int(n['text'])>24:continue
        si=min(range(6),key=lambda i:abs(system[i]-n['y']))
        if abs(system[si]-n['y'])<gap*.42:
            hits.append((n['x'],si,int(n['text']),n.get('context','')))
    hits.sort();columns=[]
    for x,si,fret,context in hits:
        if not columns or x-columns[-1]['x']>max(3,gap*.45):columns.append({'x':x,'frets':[],'ghost':False})
        columns[-1]['frets'].append((si,fret))
        if '('+str(fret)+')' in context:columns[-1]['ghost']=True
    return columns


def read_pitches_at_stems(page, systems, image, scale, numbers, folder, pn, ocr, template_bank=None):
    """OCR isolated fret tiles; line-level OCR can collapse several digits to one box."""
    import fitz,subprocess,json
    from PIL import Image
    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False)
    gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    tiles=[]
    for si,system in enumerate(systems):
        result=read_system(image,scale,system,[],numbers)
        if result is None:continue
        gap=float(np.median(np.diff(system)))
        stems=[e['x'] for m in result for e in m['events'] if e['kind'] in ('note','continuation')]
        for x in stems:
            for string,y in enumerate(system):
                x0=round((x-gap*.62)*scale);x1=round((x+gap*.62)*scale)
                y0=round((y-gap*.47)*scale);y1=round((y+gap*.47)*scale)
                crop=gray[max(0,y0):y1,max(0,x0):x1].copy()
                # Tab string rules are gray; numerals are black.
                mask=(crop<95).astype(np.uint8)
                # Discard long line fragments entering either edge.
                for row in range(mask.shape[0]):
                    if mask[row].mean()>.8:mask[row]=0
                if mask.sum()<gap*gap*scale*scale*.045:continue
                if mask.sum()>gap*gap*scale*scale*.5:continue
                # Keep numeral bodies, discard staff fragments and thin parentheses.
                count,labs,stats,cents=cv2.connectedComponentsWithStats(mask)
                biggest=max(stats[1:,4],default=0)
                retained=np.zeros_like(mask)
                parens=[(cx,cy,cw,ch) for cx,cy,cw,ch,area in stats[1:] if ch>gap*scale*.35 and cw<ch*.28]
                ghost=any(cx<mask.shape[1]/2 for cx,cy,cw,ch in parens) and any(cx>mask.shape[1]/2 for cx,cy,cw,ch in parens)
                for ci,(cx,cy,cw,ch,area) in enumerate(stats[1:],1):
                    if area>biggest*.28 and ch>gap*scale*.35 and cw>ch*.12:retained[labs==ci]=1
                if not retained.any():continue
                ys,xs=np.where(retained)
                glyph=retained[ys.min():ys.max()+1,xs.min():xs.max()+1]
                clean=Image.fromarray((255-retained*255).astype('uint8'))
                tile=Image.new('L',(160,120),255)
                clean=clean.resize((round(clean.width*1.3),round(clean.height*1.3)))
                tile.paste(clean,((160-clean.width)//2,(120-clean.height)//2))
                tiles.append({'system':si,'x':x,'string':string,'tile':tile,'ghost':ghost,'glyph':cv2.resize(glyph,(32,48),interpolation=cv2.INTER_NEAREST)})
    if not tiles:return [[] for _ in systems]
    width=160*8;height=120*((len(tiles)+7)//8)
    montage=Image.new('L',(width,height),255)
    for i,t in enumerate(tiles):montage.paste(t['tile'],((i%8)*160,(i//8)*120))
    dest=folder/f'frets-{pn}.png';montage.save(dest)
    result=subprocess.run([str(ocr.parent/'fret-ocr'),str(dest)],capture_output=True,text=True,timeout=90,check=True)
    raw=json.loads(result.stdout)
    import re
    labels={};templates=list(template_bank or [])
    for n in raw:
        match=re.fullmatch(r'[^0-9]*([0-9]{1,2})[^0-9]*',n['text'].strip())
        if not match or int(match.group(1))>24 or n['tile']>=len(tiles):continue
        label=int(match.group(1));index=n['tile']
        # A clean recognized glyph can identify identical repetitions OCR missed.
        if n.get('confidence',0)>=.5:
            labels[index]=label
            templates.append((label,tiles[index]['glyph']))
    if template_bank is not None:template_bank.extend(templates[len(template_bank):])
    unresolved=[]
    for i,tile in enumerate(tiles):
        if i in labels:continue
        scores=[]
        for label,template in templates:
            intersection=np.logical_and(template,tile['glyph']).sum()
            union=np.logical_or(template,tile['glyph']).sum()
            scores.append((intersection/max(1,union),label))
        if scores:
            scores.sort(reverse=True)
            best,label=scores[0]
            runner=max((v for v,k in scores if k!=label),default=0)
            if best>=.78 and best-runner>=.12:labels[i]=label
        if i not in labels:unresolved.append(i)
    columns=[{} for _ in systems]
    for index,label in labels.items():
        tile=tiles[index];col=columns[tile['system']].setdefault(tile['x'],{'x':tile['x'],'frets':[],'ghost':False})
        col['ghost']=col['ghost'] or tile.get('ghost',False)
        pair=(tile['string'],label)
        if pair not in col['frets']:col['frets'].append(pair)
    for index in unresolved:
        tile=tiles[index];col=columns[tile['system']].setdefault(tile['x'],{'x':tile['x'],'frets':[],'ghost':False})
        col['unreadable']=True
    (folder/f'frets-{pn}.json').write_text(json.dumps(raw))
    return [sorted(cols.values(),key=lambda c:c['x']) for cols in columns]
