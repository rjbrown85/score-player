"""Persistent library index. Original PDFs remain in their import folders."""
from contextlib import contextmanager
import json
import sqlite3
import time
from pathlib import Path


@contextmanager
def connect(data):
    db=sqlite3.connect(Path(data)/'library.sqlite3')
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS scores (id TEXT PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL,updated REAL NOT NULL,session TEXT)')
    try:
        with db:
            yield db
    finally:
        db.close()


def register(data,jid,title,status='working'):
    with connect(data) as db:
        db.execute('INSERT INTO scores VALUES (?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET status=excluded.status,updated=excluded.updated',(jid,title,status,time.time()))


def finish(data,jid,status):
    with connect(data) as db:db.execute('UPDATE scores SET status=?,updated=? WHERE id=?',(status,time.time(),jid))


def save(data,jid,title,session):
    with connect(data) as db:
        db.execute('INSERT INTO scores VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,status=excluded.status,updated=excluded.updated,session=excluded.session',(jid,title,'done',time.time(),json.dumps(session)))


def listing(data):
    with connect(data) as db:return [dict(r) for r in db.execute('SELECT id,title,status,updated FROM scores ORDER BY updated DESC')]


def get(data,jid):
    with connect(data) as db:row=db.execute('SELECT * FROM scores WHERE id=?',(jid,)).fetchone()
    if row is None:return None
    item=dict(row)
    item['session']=json.loads(item['session']) if item['session'] else None
    return item
