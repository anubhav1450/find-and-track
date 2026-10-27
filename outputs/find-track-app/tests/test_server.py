import copy
import importlib.util
import io
import json
import os
import http.client
from pathlib import Path
import sqlite3
import sys
from contextlib import closing
import tempfile
import threading
import unittest
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('server', ROOT / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'workspace.sqlite3'
        self.seed = Path(self.tmp.name) / 'seed.json'
        self.data = {'schema':1,'profile':{'name':'Test','resume':'Node.js'},'jobs':[{'id':'j1','title':'Engineer','company':'Example','status':'saved','url':'https://example.com/job','requirements':[]}],'contacts':[],'events':[],'actions':[],'companies':[],'rules':[]}
        self.seed.write_text(json.dumps(self.data))
        server.init_db(self.db,self.seed)
        self.http = None
        if os.environ.get('FIND_TRACK_HTTP_TEST') == '1':
            self.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(self.db,'test-token'))
            self.thread = threading.Thread(target=self.http.serve_forever,daemon=True)
            self.thread.start()
            self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        if self.http:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join()
        self.tmp.cleanup()

    def request(self,method='GET',path='/api/state',body=None,headers=None):
        if not self.http:
            class MemorySocket:
                def __init__(self, value):
                    self.input = io.BytesIO(value)
                    self.output = io.BytesIO()
                def makefile(self, *args, **kwargs):
                    return self.input
                def sendall(self, value):
                    self.output.write(value)
            payload = json.dumps(body).encode() if body is not None else b''
            fields = {'Host':'127.0.0.1:8765', 'Content-Length':str(len(payload)), **(headers or {})}
            request = f'{method} {path} HTTP/1.0\r\n' + ''.join(f'{k}: {v}\r\n' for k,v in fields.items()) + '\r\n'
            sock = MemorySocket(request.encode() + payload)
            server.make_handler(self.db,'test-token')(sock, ('127.0.0.1', 12345), SimpleNamespace(server_port=8765))
            response = http.client.HTTPResponse(MemorySocket(sock.output.getvalue()))
            response.begin()
            return response.status, json.loads(response.read())
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers=headers or {})
        try:
            with urlopen(req) as response:
                return response.status,json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code,json.loads(error.read())

    def put(self,data,revision=1,headers=None):
        return self.request('PUT',body={'revision':revision,'data':data},headers=headers or {'X-Workspace-Token':'test-token','Content-Type':'application/json'})

    def test_persistence_revision_and_history(self):
        self.data['jobs'][0]['status']='applied'
        self.assertEqual(self.put(self.data),(200,{'revision':2}))
        status,result=self.request()
        self.assertEqual(result['data']['jobs'][0]['status'],'applied')
        server.init_db(self.db,self.seed)
        self.assertEqual(self.request()[1]['revision'],2)
        with closing(sqlite3.connect(self.db)) as db, db:
            old=json.loads(db.execute('SELECT payload FROM history WHERE revision=1').fetchone()[0])
        self.assertEqual(old['jobs'][0]['status'],'saved')

    def test_stale_write_cannot_overwrite(self):
        self.assertEqual(self.put(self.data)[0],200)
        self.data['jobs'][0]['title']='Stale change'
        self.assertEqual(self.put(self.data)[0],409)
        self.assertEqual(self.request()[1]['data']['jobs'][0]['title'],'Engineer')

    def test_bad_import_is_atomic(self):
        for mutate in [lambda d:d['jobs'].append(copy.deepcopy(d['jobs'][0])),lambda d:d['jobs'][0].update(status='invented'),lambda d:d['jobs'][0].update(url='javascript:alert(1)'),lambda d:d['actions'].append({'id':'a1','jobId':'missing'})]:
            bad=copy.deepcopy(self.data)
            mutate(bad)
            self.assertEqual(self.put(bad)[0],400)
        self.assertEqual(self.request()[1]['revision'],1)

    def test_origin_token_and_host(self):
        self.assertEqual(self.put(self.data,headers={'X-Workspace-Token':'wrong'})[0],403)
        self.assertEqual(self.put(self.data,headers={'X-Workspace-Token':'test-token','Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request(headers={'Host':'evil.example'})[0],403)

    def test_private_files_not_served(self):
        self.assertEqual(self.request(path='/data/seed.json')[0],404)
        self.assertEqual(self.request(path='/../server.py')[0],404)

    def test_clean_clone_seed_contains_no_personal_workspace(self):
        clean_db=Path(self.tmp.name)/'clean.sqlite3'
        server.init_db(clean_db,ROOT/'seed.example.json')
        with closing(sqlite3.connect(clean_db)) as db:
            data=json.loads(db.execute('SELECT payload FROM workspace').fetchone()[0])
        self.assertEqual(data['profile']['resume'],'')
        self.assertEqual(data['profile']['name'],'Your name')
        for key in ('jobs','contacts','events','actions','companies'):
            self.assertEqual(data[key],[])

    def test_valid_requirement_states(self):
        self.data['jobs'][0]['requirements']=[{'term':'CI/CD','weight':1,'coverage':'known','evidence':'User confirmed basics'}]
        self.assertEqual(self.put(self.data)[0],200)
        self.data['jobs'][0]['requirements'][0]['coverage']='magic'
        self.assertEqual(self.put(self.data,2)[0],400)

    def test_preparation_route_requires_local_session_and_persists(self):
        body={'action':'prepare'}
        self.assertEqual(self.request('POST','/api/workflow',body)[0],403)
        status,result=self.request('POST','/api/workflow',body,{'X-Workspace-Token':'test-token'})
        self.assertEqual(status,200)
        self.assertEqual(result['report']['preparation']['jobsPrepared'],1)
        state=self.request()[1]
        self.assertIn('preparation',state['data']['jobs'][0])
        self.assertEqual(state['data']['profile']['resume'],'Node.js')
        self.assertEqual(state['revision'],2)

if __name__=='__main__':
    unittest.main()
