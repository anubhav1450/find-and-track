"""Offline release check: tracked-file hygiene and empty first-run persistence."""
from contextlib import closing
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'outputs/find-track-app'))
from server import init_db, validate
import sqlite3

paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
for name in filter(None, paths):
    path = ROOT / name
    assert 'data' not in path.parts[len(ROOT.parts):], f'Private data tracked: {name}'
    assert not name.endswith(('.sqlite3', '.pem', '.key')), f'Private file tracked: {name}'
    if path.is_file() and path.stat().st_size < 2_000_000:
        text = path.read_bytes().decode('utf-8', errors='ignore')
        assert not re.search(r'tvly-[A-Za-z0-9_-]{20,}', text), f'Possible live search credential: {name}'
seed = ROOT / 'outputs/find-track-app/seed.example.json'
data = validate(json.loads(seed.read_text()))
assert not data['profile'].get('resume')
for kind in ('jobs', 'contacts', 'companies', 'actions', 'events'):
    assert data[kind] == [], f'Personal records in default seed: {kind}'
with tempfile.TemporaryDirectory() as tmp:
    dbpath = Path(tmp) / 'workspace.sqlite3'
    init_db(dbpath, seed)
    with closing(sqlite3.connect(dbpath)) as db:
        saved = json.loads(db.execute('SELECT payload FROM workspace').fetchone()[0])
    assert saved == data
print('Release hygiene and empty first-run persistence passed.')
