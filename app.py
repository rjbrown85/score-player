import json
import re
import threading
import uuid
import library
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List
import fitz
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from recognition import staff_pdf, tab_pdf, read_score, make_midi, AUDIVERIS, tab_systems, tab_rhythmic_pdf

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
DATA.mkdir(exist_ok=True)
app=FastAPI(title='Score Player')
jobs={}
lock=threading.Lock()
worker=ThreadPoolExecutor(max_workers=1)

@app.middleware('http')
async def local_only(request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):
        return JSONResponse({'detail':'Local access only.'},status_code=403)
    origin=request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8767','http://localhost:8767'):
        return JSONResponse({'detail':'Open the app directly on this Mac.'},status_code=403)
    return await call_next(request)

@app.get('/api/status')
def status():
    return {'ready':AUDIVERIS.exists(),'name':'Score Player'}

def is_tab(path):
    with fitz.open(path) as doc:
        return any(tab_systems(doc[i]) for i in range(min(3,len(doc))))

def run_job(jid, path, mode, tuning, step, rhythm="read", meter=4):
    def update(message):
        with lock:
            jobs[jid]['message']=message
    try:
        if path.suffix.lower() in ('.xml','.musicxml','.mxl'):
            result=read_score(path)
            result['method']='MusicXML import'
        elif mode=='tab' or (mode=='auto' and is_tab(path)):
            result=tab_rhythmic_pdf(path,path.parent,tuning,update,meter) if rhythm=='read' else tab_pdf(path,path.parent,tuning,step,update)
        else:
            result=staff_pdf(path,path.parent,update)
        result['title']=jobs[jid]['title']
        if len(result['notes'])>20000:
            raise ValueError('This score has too many notes. Please split it into shorter PDFs.')
        (path.parent/'result.json').write_text(json.dumps(result))
        with lock:
            jobs[jid].update(status='done',message='Ready to review and play.',result=result)
        library.finish(DATA,jid,'done')
    except Exception as e:
        with lock:
            jobs[jid].update(status='error',message=str(e)[:700])
        library.finish(DATA,jid,'error')

@app.post('/api/import')
async def import_file(file: UploadFile=File(...),mode:str=Form('auto'),tuning:str=Form('standard'),step:float=Form(.5),rhythm:str=Form("read"),meter:float=Form(4)):
    if mode not in ('auto','staff','tab') or tuning not in ('standard','drop-d','dadgad') or step not in (.25,.5,1,2):
        raise HTTPException(400,'Invalid import settings.')
    if rhythm not in ('read','even') or meter not in (2,3,4,5,6):
        raise HTTPException(400,'Invalid rhythm settings.')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ('.pdf','.xml','.musicxml','.mxl'):
        raise HTTPException(400,'Choose a PDF or MusicXML file.')
    with lock:
        if sum(j['status']=='working' for j in jobs.values())>=3:
            raise HTTPException(429,'There are already three files in the queue. Wait for one to finish.')
    content=await file.read(30*1024*1024+1)
    if len(content)>30*1024*1024:
        raise HTTPException(400,'Please use a file smaller than 30 MB.')
    if suffix=='.pdf':
        try:
            with fitz.open(stream=content,filetype='pdf') as doc:
                if doc.needs_pass: raise ValueError('Remove the PDF password before importing.')
                if not 1<=len(doc)<=20: raise ValueError('Please use 1–20 pages at a time.')
        except Exception as e:
            raise HTTPException(400,f'Cannot read this PDF: {e}')
    jid=uuid.uuid4().hex
    folder=DATA/jid
    folder.mkdir()
    path=folder/('source'+suffix)
    path.write_bytes(content)
    with lock:
        jobs[jid]={'status':'working','message':'Waiting for the local reader…','title':Path(file.filename).stem,'pdf':suffix=='.pdf'}
    if suffix=='.pdf':library.register(DATA,jid,Path(file.filename).stem)
    worker.submit(run_job,jid,path,mode,tuning,step,rhythm,meter)
    return {'id':jid}

@app.get('/api/jobs/{jid}')
def job(jid:str):
    with lock:
        if jid in jobs: return dict(jobs[jid])
    if re.fullmatch(r'[a-f0-9]{32}',jid) and (DATA/jid/'result.json').exists():
        return {'status':'done','result':json.loads((DATA/jid/'result.json').read_text()),'pdf':(DATA/jid/'source.pdf').exists()}
    raise HTTPException(404,'This import is no longer available.')

@app.get('/api/jobs/{jid}/pdf')
def source_pdf(jid:str):
    if not re.fullmatch(r'[a-f0-9]{32}',jid) or not (DATA/jid/'source.pdf').exists():
        raise HTTPException(404,'PDF not found.')
    return FileResponse(DATA/jid/'source.pdf',media_type='application/pdf')

class Note(BaseModel):
    pitch:int=Field(ge=0,le=127)
    start:float=Field(ge=0,le=100000,allow_inf_nan=False)
    duration:float=Field(gt=0,le=10000,allow_inf_nan=False)
    velocity:int=Field(default=90,ge=1,le=127)
    part:int=Field(default=0,ge=0,le=1000)
class Export(BaseModel):
    notes:List[Note]=Field(min_length=1,max_length=20000)
    bpm:int=Field(ge=30,le=240)
    program:int=Field(default=0,ge=0,le=127)
    transpose:int=Field(default=0,ge=-24,le=24)
    length:float=Field(default=0,ge=0,le=100000,allow_inf_nan=False)

@app.post('/api/midi')
def midi(body:Export):
    try:
        data=make_midi([n.model_dump() for n in body.notes],body.bpm,body.program,body.transpose,body.length)
    except ValueError as e:
        raise HTTPException(400,str(e))
    return Response(data,media_type='audio/midi',headers={'Content-Disposition':'attachment; filename="score.mid"'})

class SavedScore(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    notes:List[Note]=Field(max_length=20000)
    parts:List[str]=Field(max_length=1001)
    warnings:List[str]=Field(default_factory=list,max_length=100)
    bpm:int=Field(default=100,ge=30,le=240)
    length:float=Field(default=0,ge=0,le=100000,allow_inf_nan=False)
    method:str=Field(default='Saved score',max_length=200)
    rhythm:str=Field(default='',max_length=30)
class LoopRange(BaseModel):
    start:float=Field(ge=0,le=100000,allow_inf_nan=False)
    end:float=Field(gt=0,le=100000,allow_inf_nan=False)
    enabled:bool=False
class SavedSession(BaseModel):
    score:SavedScore
    bpm:int=Field(ge=30,le=240)
    transpose:int=Field(default=0,ge=-24,le=24)
    sound:str=Field(default='0',pattern=r'^(0|24|80)$')
    loop:LoopRange

@app.get('/api/library')
def list_library():
    return library.listing(DATA)

@app.put('/api/library/{jid}')
def save_library(jid:str,body:SavedSession):
    if not re.fullmatch(r'[a-f0-9]{32}',jid) or not (DATA/jid/'source.pdf').exists():
        raise HTTPException(404,'Original PDF unavailable.')
    if body.loop.start>=body.loop.end:
        raise HTTPException(400,'Loop end must follow loop start.')
    session=body.model_dump()
    session.update(job=jid,hasPDF=True)
    library.save(DATA,jid,body.score.title,session)
    return {'id':jid,'saved':True}

@app.get('/api/library/{jid}')
def open_library(jid:str):
    item=library.get(DATA,jid)
    if item is None:raise HTTPException(404,'Saved PDF not found.')
    result=DATA/jid/'result.json'
    if item['session'] is None and result.exists():
        score=json.loads(result.read_text())
        length=max(1,score.get('length',0),max((n['start']+n['duration'] for n in score['notes']),default=0))
        item['session']={'score':score,'job':jid,'hasPDF':True,'bpm':max(30,min(240,score.get('bpm',100))),'transpose':0,'sound':'0','loop':{'start':0,'end':length,'enabled':False}}
    return item

@app.get('/')
def home():
    return FileResponse(ROOT/'static/index.html')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
