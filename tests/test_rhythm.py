import io
from pathlib import Path
import fitz
import mido
import pytest
from tab_rhythm import raster,read_system
from recognition import make_midi


def fixture(tmp_path, second='eighths'):
    doc=fitz.open();page=doc.new_page(width=600,height=300)
    system=[100+12*i for i in range(6)]
    for y in system:page.draw_line((40,y),(560,y),color=(.4,.4,.4),width=.5)
    for x in (40,300,560):page.draw_line((x,100),(x,160),width=.7)
    cols=[]
    def fret(x,short=False):
        page.draw_rect(fitz.Rect(x-5,94,x+6,105),fill=(1,1,1),color=None)
        page.insert_text((x-3,104),'3',fontsize=11)
        page.draw_line((x,181.5 if short else 167.2),(x,193.5),width=.65)
        cols.append({'x':x,'frets':[(0,3)],'ghost':False})
    for x in (70,130,190,250):fret(x)
    if second=='eighths':
        for x in range(320,501,25):fret(x)
        page.draw_rect(fitz.Rect(320,191,495,194),fill=(0,0,0),color=None)
    elif second=='half':
        fret(330,True)
        page.draw_rect(fitz.Rect(440,132,450,136),fill=(0,0,0),color=None)
    elif second=='dotted':
        fret(330,True);page.draw_circle((337,189),1.5,fill=(0,0,0),color=None)
        fret(470)
    elif second=='incomplete':
        fret(330)
    image,scale=raster(page)
    return read_system(image,scale,system,cols,[],4)


def test_beams_and_quarters(tmp_path):
    measures=fixture(tmp_path)
    assert len(measures)==2
    assert [e['duration'] for e in measures[0]['events']]==[1]*4
    assert [e['duration'] for e in measures[1]['events']]==[.5]*8
    assert not any(m['issues'] for m in measures)


def test_half_note_and_rest(tmp_path):
    measures=fixture(tmp_path,'half')
    assert [(e['kind'],e['duration']) for e in measures[1]['events']]==[('note',2),('rest',2)]
    assert not measures[1]['issues']


def test_dotted_half(tmp_path):
    m=fixture(tmp_path,'dotted')[1]
    assert [e['duration'] for e in m['events']]==[3,1]
    assert not m['issues']


def test_incomplete_measure_is_flagged(tmp_path):
    m=fixture(tmp_path,'incomplete')[1]
    assert m['issues'] and m['length']==1
    assert '1 beats read' in m['issues'][0]


def test_midi_leading_and_trailing_rests():
    data=make_midi([{'pitch':60,'start':3.5,'duration':.5}],120,length=8)
    midi=mido.MidiFile(file=io.BytesIO(data))
    assert midi.length==4
    on=next(m for m in midi.tracks[0] if m.type=='note_on')
    assert on.time==1680
    assert midi.tracks[0][-1].time==1920
