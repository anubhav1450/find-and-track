#!/usr/bin/env python3
"""Find&Track: dependency-free, loopback-only personal workspace."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
JOB_STATES = {'saved', 'selected', 'applied', 'assessment', 'interview', 'offer', 'rejected', 'withdrawn', 'closed'}
CONTACT_STATES = {'discovered', 'selected', 'request sent', 'accepted', 'message prepared', 'message sent', 'replied', 'do not contact'}

def validate(data):
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('Expected a Find&Track version 1 backup.')
    for key in ('jobs', 'contacts', 'events', 'actions', 'companies', 'rules'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'{key} must be a list.')
    if not isinstance(data.get('profile'), dict):
        raise ValueError('Profile is missing.')
    if not isinstance(data['profile'].get('name'), str) or not data['profile']['name'].strip():
        raise ValueError('Profile name is required.')
    if not isinstance(data['profile'].get('resume', ''), str):
        raise ValueError('Resume must be plain text.')
    for rule in data['rules']:
        if not isinstance(rule, dict) or not isinstance(rule.get('name'), str) or not isinstance(rule.get('value'), str):
            raise ValueError('Each rule needs a text name and value.')
    for kind in ('jobs', 'contacts', 'events', 'actions', 'companies'):
        ids = set()
        for row in data[kind]:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or row['id'] in ids:
                raise ValueError(f'Invalid or duplicate ID in {kind}.')
            ids.add(row['id'])
            text_fields = ('name', 'title', 'company', 'status', 'role', 'relevance', 'uncertainty', 'source', 'url', 'website', 'evidenceUrl', 'emailUrl', 'location', 'model', 'type', 'screening', 'experience', 'salary', 'fit', 'unknowns', 'notes', 'jd', 'tailoring', 'resumeSnapshot', 'at', 'note', 'details', 'due', 'assessment', 'checkedAt', 'postedAt', 'updatedAt', 'assessedAt', 'draft')
            if any(key in row and not isinstance(row[key], str) for key in text_fields):
                raise ValueError(f'Text fields in {kind} must contain text.')
            for key in ('url', 'website', 'source', 'evidenceUrl', 'emailUrl'):
                value = row.get(key, '')
                if value and (not isinstance(value, str) or urlsplit(value).scheme not in ('http', 'https')):
                    raise ValueError(f'Use an http or https link for {key}.')
    for job in data['jobs']:
        if not job.get('title') or not job.get('company') or job.get('status') not in JOB_STATES:
            raise ValueError('Each job needs a company, title and valid status.')
        if not isinstance(job.get('requirements', []), list):
            raise ValueError('Requirements must be a list.')
        if not isinstance(job.get('skills', []), list) or any(not isinstance(s, str) for s in job.get('skills', [])):
            raise ValueError('Skills must be a list of text values.')
        if 'jdVerified' in job and not isinstance(job['jdVerified'], bool):
            raise ValueError('JD confirmation must be true or false.')
        for req in job.get('requirements', []):
            if not isinstance(req, dict) or not isinstance(req.get('term'), str) or req.get('weight') not in (1, 2) or req.get('coverage') not in ('full', 'partial', 'known', 'missing', 'unreviewed'):
                raise ValueError('Invalid requirement assessment.')
            if not isinstance(req.get('evidence', ''), str):
                raise ValueError('Requirement evidence must be text.')
    job_ids = {j['id'] for j in data['jobs']}
    for person in data['contacts']:
        if not person.get('name') or person.get('status') not in CONTACT_STATES:
            raise ValueError('Each contact needs a name and valid status.')
        if not isinstance(person.get('jobIds', []), list) or any(j not in job_ids for j in person.get('jobIds', [])):
            raise ValueError('Contact references an unknown job.')
    contact_ids = {p['id'] for p in data['contacts']}
    for record in data['events']:
        if not isinstance(record.get('at'), str) or not record.get('type'):
            raise ValueError('Events need a date and type.')
    for record in data['actions']:
        if record.get('status') not in ('pending', 'done') or not record.get('title'):
            raise ValueError('Tasks need a title and pending/done status.')
    for row in data['actions'] + data['events']:
        if row.get('jobId') and row['jobId'] not in job_ids:
            raise ValueError('Activity references an unknown job.')
        if row.get('contactId') and row['contactId'] not in contact_ids:
            raise ValueError('Activity references an unknown person.')
    return data

def init_db(path, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        if not db.execute('SELECT 1 FROM workspace').fetchone():
            data = validate(json.loads(seed.read_text()))
            db.execute('INSERT INTO workspace VALUES (1,1,?)', (json.dumps(data),))
    os.chmod(path, 0o600)

def make_handler(db_path, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if not self.path.startswith('/api/session'):
                super().log_message(fmt, *args)

        def allowed_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def reply(self, status, data, content_type='application/json'):
            body = json.dumps(data).encode() if content_type == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {'error': 'Local access only.'})
            path = urlsplit(self.path).path
            if path == '/api/session':
                return self.reply(200, {'token': token, 'workflowVersion': 1})
            if path == '/api/state':
                with closing(sqlite3.connect(db_path)) as db, db:
                    revision, payload = db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
                return self.reply(200, {'revision': revision, 'data': json.loads(payload)})
            files = {'/': 'index.html', '/app.js': 'app.js', '/domain.js': 'domain.js', '/styles.css': 'styles.css'}
            if path not in files:
                return self.reply(404, {'error': 'Not found'})
            file = ROOT / 'static' / files[path]
            return self.reply(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or 'text/plain') + '; charset=utf-8')

        def do_PUT(self):
            if not self.allowed_host() or self.headers.get('X-Workspace-Token') != token:
                return self.reply(403, {'error': 'Invalid local session. Reload this page.'})
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                return self.reply(403, {'error': 'Invalid origin.'})
            if self.path != '/api/state':
                return self.reply(404, {'error': 'Not found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 5_000_000:
                    return self.reply(413, {'error': 'Backup must be under 5 MB.'})
                body = json.loads(self.rfile.read(size))
                data = validate(body['data'])
                with closing(sqlite3.connect(db_path)) as db, db:
                    db.execute('BEGIN IMMEDIATE')
                    revision, payload = db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
                    if body.get('revision') != revision:
                        return self.reply(409, {'error': 'This workspace changed in another tab. Reload before editing.'})
                    db.execute('INSERT OR REPLACE INTO history(revision,payload) VALUES (?,?)', (revision, payload))
                    db.execute('DELETE FROM history WHERE revision < ?', (revision - 49,))
                    db.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1', (revision+1, json.dumps(data)))
                return self.reply(200, {'revision': revision + 1})
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                return self.reply(400, {'error': str(exc)})
            except sqlite3.Error:
                return self.reply(500, {'error': 'Database write failed. Your previous version is intact.'})

        def do_POST(self):
            if not self.allowed_host() or self.headers.get('X-Workspace-Token') != token:
                return self.reply(403, {'error': 'Invalid local session. Reload this page.'})
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                return self.reply(403, {'error': 'Invalid origin.'})
            if self.path != '/api/workflow':
                return self.reply(404, {'error': 'Not found'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<1 or size>1024:
                    return self.reply(400,{'error':'Invalid workflow request.'})
                body=json.loads(self.rfile.read(size))
                if body.get('action') not in ('prepare','refresh'):
                    return self.reply(400,{'error':'Unknown workflow action.'})
                from workflow import run
                result=run(db_path,refresh=body['action']=='refresh')
                return self.reply(200,{'report':result})
            except (ValueError,TypeError,AttributeError) as exc:
                return self.reply(400,{'error':str(exc)})
            except sqlite3.Error:
                return self.reply(500,{'error':'Workflow could not save. Previous state preserved.'})
    return Handler

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'workspace.sqlite3')
    private_seed = ROOT / 'data' / 'seed.json'
    parser.add_argument('--seed', type=Path, default=private_seed if private_seed.exists() else ROOT / 'seed.example.json')
    args = parser.parse_args()
    init_db(args.db, args.seed)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.db, secrets.token_urlsafe(32)))
    print(f'Find&Track is running at http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
