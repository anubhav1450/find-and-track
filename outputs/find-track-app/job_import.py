"""Preview an employer posting from a supported public ATS URL."""
import copy
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from html import unescape

from workflow import GREENHOUSE, refresh_feed, prepare, utcnow


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError('The job source redirected. Open the original posting and check its URL.')


def fetch_json(url):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'FindAndTrack/0.3'})
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError('The posting is too large to import.')
        return json.loads(raw)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError('This posting is unavailable. It may have closed or moved.') from exc
        raise ValueError('The job source is unavailable. Try again later.') from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError('The job source could not be reached. Try again later.') from exc


def posting_reference(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Paste a valid job URL.')
    parts = urlsplit(url.strip())
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Use the original HTTPS posting URL.')
    segments = parts.path.strip('/').split('/')
    if parts.hostname == 'jobs.lever.co' and len(segments) in (2, 3):
        if len(segments) == 3 and segments[2] != 'apply':
            raise ValueError('Use a Lever job posting link.')
        board, job_id = segments[:2]
        provider = 'lever'
    elif parts.hostname=='jobs.ashbyhq.com' and len(segments) in (2,3):
        board,job_id=segments[:2]
        if len(segments)==3 and segments[2] not in ('application','apply'):raise ValueError('Use the Ashby posting URL.')
        provider='ashby'
    elif parts.hostname in ('boards.greenhouse.io', 'job-boards.greenhouse.io') and len(segments) == 3 and segments[1] == 'jobs':
        board, _, job_id = segments
        provider = 'greenhouse'
    elif parts.hostname in ('boards.greenhouse.io', 'job-boards.greenhouse.io') and parts.path == '/embed/job_app':
        query = parse_qs(parts.query)
        board = query.get('for', [''])[0]
        job_id = query.get('token', [''])[0]
        provider = 'greenhouse'
    else:
        raise ValueError('Automatic import supports Greenhouse, Lever and Ashby posting links. For AccioJob, open Apply and copy the original employer link. Other sites can be added manually.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', board) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', job_id):
        raise ValueError('The posting URL contains an invalid employer or job identifier.')
    if provider == 'greenhouse' and not job_id.isdigit():
        raise ValueError('The Greenhouse job identifier must be numeric.')
    return provider, board, job_id


def preview_job(url, profile, fetcher=fetch_json):
    provider, board, job_id = posting_reference(url)
    if provider == 'ashby':
        from startup_sources import ashby_posts, ASHBY_BOARDS
        post=next((p for p in ashby_posts(board) if p['id']==job_id),None)
        if post is None:raise ValueError('This posting is no longer listed on the employer board.')
        company=ASHBY_BOARDS.get(board,board)
    elif provider == 'greenhouse':
        row = fetcher(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}')
        if not isinstance(row, dict) or str(row.get('id')) != job_id:
            raise ValueError('The source did not return the requested posting.')
        post = {
            'id': job_id, 'text': row.get('title'), 'hostedUrl': row.get('absolute_url'),
            'description': unescape(row.get('content') or ''),
            'categories': {'location': (row.get('location') or {}).get('name') or 'Unspecified'},
            'publishedAt': row.get('first_published'),
        }
        company = row.get('company_name') or GREENHOUSE.get(board, (board,))[0]
    else:
        post = fetcher(f'https://api.lever.co/v0/postings/{board}/{job_id}?mode=json')
        if not isinstance(post, dict) or post.get('id') != job_id:
            raise ValueError('The source did not return the requested posting.')
        company = board
    if not isinstance(company, str) or not company.strip():
        raise ValueError('The posting has no employer identity.')
    # A preview is isolated and saved only after the user reviews it.
    data = {'profile': copy.deepcopy(profile), 'jobs': [], 'contacts': [], 'actions': [], 'events': []}
    stamp = utcnow()
    refresh_feed(data, [post], stamp, board, company, provider=provider, include_excluded=True)
    if not data['jobs']:
        raise ValueError('The posting response is incomplete or its application URL is unsupported.')
    prepare(data, stamp)
    job = data['jobs'][0]
    job['unknowns'] += ' Confirm the employer name shown in the original posting.'
    return {'job': job}
