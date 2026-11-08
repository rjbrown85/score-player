import copy
import fitz
from fastapi.testclient import TestClient
import app
import library


def session():
    return {'score': {'title': 'Practice', 'notes': [{'pitch': 64, 'start': 2, 'duration': 1}], 'parts': ['Guitar'], 'bpm': 125, 'length': 8}, 'bpm': 90, 'transpose': -2, 'sound': '24', 'loop': {'start': 2, 'end': 4, 'enabled': True}}


def test_library_preserves_pdf_and_edits_across_connections(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'DATA', tmp_path)
    jid = 'a' * 32
    folder = tmp_path / jid
    folder.mkdir()
    original = b'original PDF bytes'
    (folder / 'source.pdf').write_bytes(original)
    client = TestClient(app.app)
    saved = session()
    assert client.put('/api/library/' + jid, json=saved).status_code == 200
    assert library.get(tmp_path, jid)['session']['bpm'] == 90
    saved['score']['notes'][0]['pitch'] = 67
    assert client.put('/api/library/' + jid, json=saved).status_code == 200
    assert len(client.get('/api/library').json()) == 1
    reopened = client.get('/api/library/' + jid).json()['session']
    assert reopened['score']['notes'][0]['pitch'] == 67
    assert reopened['loop'] == saved['loop']
    assert reopened['transpose'] == -2
    assert reopened['sound'] == '24'
    assert client.get('/api/jobs/' + jid + '/pdf').content == original
    invalid = copy.deepcopy(saved)
    invalid['loop']['end'] = 1
    assert client.put('/api/library/' + jid, json=invalid).status_code == 400
    assert client.put('/api/library/' + 'b'*32, json=saved).status_code == 404
    assert client.get('/api/library/' + 'b'*32).status_code == 404


def test_upload_saves_pdf_even_when_recognition_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'DATA', tmp_path)
    monkeypatch.setattr(app, 'jobs', {})
    class ImmediateWorker:
        def submit(self, fn, *args):
            fn(*args)
    def fail(*args):
        raise ValueError('Unreadable notation')
    monkeypatch.setattr(app, 'worker', ImmediateWorker())
    monkeypatch.setattr(app, 'staff_pdf', fail)
    doc = fitz.open()
    doc.new_page()
    pdf = doc.tobytes()
    doc.close()
    client = TestClient(app.app)
    response = client.post('/api/import', files={'file': ('Practice.pdf', pdf, 'application/pdf')}, data={'mode': 'staff'})
    assert response.status_code == 200
    jid = response.json()['id']
    assert client.get('/api/library').json()[0]['status'] == 'error'
    assert client.get('/api/library/' + jid).json()['session'] is None
    assert client.get('/api/jobs/' + jid + '/pdf').content == pdf
