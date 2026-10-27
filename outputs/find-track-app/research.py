"""Merge an assistant's source-backed batch without replacing existing user records."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from server import ROOT, init_db, validate

def canonical(url):
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.endswith('.linkedin.com'):
        host = 'linkedin.com'
    query = urlencode(sorted((k,v) for k,v in parse_qsl(parts.query) if not k.lower().startswith('utm_') and k not in ('trk','trackingId','refId','gh_src')))
    return urlunsplit((parts.scheme,host,parts.path.rstrip('/'),query,''))

def merge_batch(db_path, batch):
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        revision, payload = db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
        data = json.loads(payload)
        additions = {}
        existing_urls = {canonical(j['url']) for j in data['jobs'] if j.get('url')}
        rejected_jobs = set()
        for key in ('jobs','companies','contacts','events','actions'):
            ids = {r['id'] for r in data[key]}
            additions[key] = 0
            for row in batch.get(key, []):
                if row['id'] in ids:
                    continue
                if key == 'jobs' and row.get('url') and canonical(row['url']) in existing_urls:
                    rejected_jobs.add(row['id'])
                    continue
                if row.get('jobId') in rejected_jobs:
                    continue
                data[key].append(row)
                ids.add(row['id'])
                additions[key] += 1
                if key == 'jobs' and row.get('url'):
                    existing_urls.add(canonical(row['url']))
        validate(data)
        if any(additions.values()):
            db.execute('INSERT OR REPLACE INTO history(revision,payload) VALUES (?,?)',(revision,payload))
            db.execute('DELETE FROM history WHERE revision < ?',(revision-49,))
            db.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1',(revision+1,json.dumps(data)))
        return additions

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('batch',type=Path)
    parser.add_argument('--db',type=Path,default=ROOT/'data/workspace.sqlite3')
    args=parser.parse_args()
    init_db(args.db,ROOT/'data/seed.json')
    print(json.dumps(merge_batch(args.db,json.loads(args.batch.read_text()))))

if __name__=='__main__':
    main()
