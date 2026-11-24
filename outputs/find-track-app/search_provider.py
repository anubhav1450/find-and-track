"""Bounded Tavily basic search with a local key, cache and monthly request cap."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
LOCK = Lock()
MONTHLY_LIMIT = 900


def credentials():
    key = os.environ.get('TAVILY_API_KEY', '').strip()
    if key:
        return key
    path = ROOT / 'data' / 'search-key.json'
    if path.exists():
        return json.loads(path.read_text()).get('key', '')
    return ''


def settings():
    return {'configured': bool(credentials()), 'provider': 'Tavily', 'monthlyRequestLimit': MONTHLY_LIMIT,
            'setupUrl': 'https://app.tavily.com', 'priceNote': 'Use the free Researcher plan. Keep pay-as-you-go disabled in Tavily.'}


def save_key(value):
    if not isinstance(value,str) or not value.startswith('tvly-') or len(value)>300 or any(c.isspace() for c in value):
        raise ValueError('Paste the Tavily API key from your free account.')
    path = ROOT / 'data' / 'search-key.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    # The key stays outside workspace exports and Git.
    with LOCK:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as file:json.dump({'key':value},file)
        path.chmod(0o600)
    return settings()


def search(query, recent=False, domains=None):
    key=credentials()
    if not key:
        raise ValueError('Connect a free Tavily search key in Discover to run web research.')
    payload={'query':query,'search_depth':'basic','max_results':10,'include_answer':False,
             'include_raw_content':False,'auto_parameters':False}
    if recent:payload['time_range']='month'
    if domains:payload['include_domains']=domains
    cache_id=hashlib.sha256((key+json.dumps(payload,sort_keys=True)).encode()).hexdigest()
    directory=Path(os.environ.get('FINDTRACK_SEARCH_CACHE_DIR','/tmp/findtrack-search' if os.environ.get('VERCEL') else str(ROOT/'data')))
    directory.mkdir(parents=True,exist_ok=True)
    cache_file=directory/'search-cache.sqlite3'
    month=time.strftime('%Y-%m',time.gmtime())
    account=hashlib.sha256(key.encode()).hexdigest()
    with LOCK,closing(sqlite3.connect(cache_file)) as db,db:
        cache_file.chmod(0o600)
        db.execute('CREATE TABLE IF NOT EXISTS cache (id TEXT PRIMARY KEY, at REAL, payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS usage (account TEXT, month TEXT, requests INTEGER, PRIMARY KEY(account,month))')
        cached=db.execute('SELECT at,payload FROM cache WHERE id=?',(cache_id,)).fetchone()
        if cached and time.time()-cached[0]<21600:
            return json.loads(cached[1])
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO usage VALUES (?,?,0)',(account,month))
        count=db.execute('SELECT requests FROM usage WHERE account=? AND month=?',(account,month)).fetchone()[0]
        if count>=MONTHLY_LIMIT:raise ValueError('The app monthly search limit is reached. Public employer feeds still work.')
        db.execute('UPDATE usage SET requests=requests+1 WHERE account=? AND month=?',(account,month))
    request=Request('https://api.tavily.com/search',data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'FindAndTrack/0.4'})
    try:
        with urlopen(request,timeout=25) as response:raw=response.read(3_000_001)
        if len(raw)>3_000_000:raise ValueError('Search response exceeded the size limit.')
        data=json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('results'),list):raise ValueError('Search returned an unexpected response.')
    except HTTPError as exc:
        if exc.code in (401,403):raise ValueError('Search key was rejected. Check it in Discover.') from exc
        if exc.code in (429,432,433):raise ValueError('Search quota or rate limit reached. Try later; employer feeds still work.') from exc
        raise ValueError('Search provider is unavailable. Try again later.') from exc
    except (URLError,TimeoutError) as exc:raise ValueError('Search timed out. Try again later.') from exc
    result={'results':data['results'],'searchedAt':time.time()}
    with LOCK,closing(sqlite3.connect(cache_file)) as db,db:
        db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',(cache_id,time.time(),json.dumps(result)))
        db.execute('DELETE FROM cache WHERE at < ?',(time.time()-7*86400,))
    return result
