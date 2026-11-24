"""Role-first search and link preview, with explicit source verification levels."""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from search_provider import search
from job_import import preview_job, posting_reference
from company_research import safe_url
from workflow import plain, screen, utcnow, canonical_posting, prepare
import copy


def indexed_lead(row, original_url=None):
    url=safe_url(original_url or row.get('url'))
    if not url:raise ValueError('Use a public HTTPS job posting URL.')
    title=plain(row.get('title',''))
    title=re.sub(r'\s*[|–-]\s*(LinkedIn|Wellfound|Y Combinator).*$', '',title,flags=re.I)
    company=''
    hiring=re.match(r'(.+?) is hiring (.+?) job(?: in| \(|$)',title,re.I)
    if hiring:
        company,title=hiring.groups()
    match=re.match(r'(.+?)\s+(?:at|@)\s+(.+)',title)
    if match:title,company=match.groups()
    company=re.split(r'\s*[•|]\s*',company)[0].strip()
    title=re.sub(r'\s*\|.*$','',title).strip()
    stamp=utcnow()
    return {'id':'J-WEB-'+hashlib.sha256(canonical_posting(url).encode()).hexdigest()[:20],
            'title':title,'company':company,'url':url,'source':safe_url(row.get('url')) or url,
            'sourceText':plain(row.get('content',''))[:12000], 'status':'saved','screening':'review',
            'location':'Unconfirmed','model':'Unconfirmed','type':'Unconfirmed','salary':'Unconfirmed',
            'salaryConfirmed':False,'experience':'Confirm eligibility from original posting',
            'fit':'Search-index lead; confirm original employer, description and availability.',
            'unknowns':'Company identity, current opening, complete JD, eligibility and pay require review.',
            'requirements':[],'skills':[],'jdVerified':False,'createdAt':stamp,'firstSeenAt':stamp,
            'checkedAt':stamp,'publishedAt':None,'availability':'unconfirmed','sourceKind':'search-index'}


def preview_link(url,profile,searcher=search):
    url=safe_url(url)
    if not url:raise ValueError('Paste the original HTTPS posting URL.')
    try:posting_reference(url)
    except ValueError:
        canonical=canonical_posting(url)
        query='"'+url+'" job role company responsibilities'
        linkedin=re.fullmatch(r'https://linkedin.com/jobs/view/(\d+)',canonical)
        if linkedin:query='site:linkedin.com/jobs/view/ "'+linkedin.group(1)+'"'
        results=searcher(query).get('results',[])
        matching=[row for row in results if isinstance(row,dict) and safe_url(row.get('url')) and canonical_posting(row['url'])==canonical]
        if not matching:raise ValueError('No matching posting was found in web search. It may be unindexed, restricted or unavailable. Use Enter details manually to keep this link and paste the job description; no LinkedIn login is required by this app.')
        job=indexed_lead(matching[0],url)
        data={'profile':copy.deepcopy(profile),'jobs':[job],'contacts':[],'events':[],'actions':[]}
        prepare(data)
        return {'job':job}
    return preview_job(url,profile)


def discover_roles(profile,searcher=search,previewer=preview_job):
    preferences=profile.get('candidate',{})
    location=preferences.get('geography') or 'India'
    roles=preferences.get('roleFamilies') or ['software engineer','backend developer','frontend developer']
    # Only role and location are sent; resume text and contact details stay local.
    queries=[f'"{role}" {location} startup fresher graduate internship 0 1 years jobs' for role in roles[:3]]
    leads={};errors=[]
    for query in queries:
        try:rows=searcher(query,recent=True,domains=['jobs.ashbyhq.com','jobs.lever.co','job-boards.greenhouse.io','boards.greenhouse.io','ycombinator.com','wellfound.com','cutshort.io']).get('results',[])
        except ValueError as exc:errors.append(str(exc));continue
        for row in rows:
            if not isinstance(row,dict) or not safe_url(row.get('url')):continue
            parts=urlsplit(row['url'])
            if parts.hostname in ('www.reddit.com','reddit.com','www.facebook.com','www.instagram.com'):continue
            if not re.search(r'/jobs?/|/job/|/positions/|jobs\.ashbyhq\.com/|jobs\.lever\.co/',row['url']):continue
            key=canonical_posting(row['url'])
            title=plain(row.get('title',''))
            if re.search(r'\b(senior|staff|principal|director|manager|unpaid)\b',title,re.I):continue
            if re.search(r'/jobs/(?:location|role|industry)/|/jobs/?$',urlsplit(row['url']).path):continue
            if not re.search(r'engineer|developer|programmer|intern|sde',title,re.I):continue
            leads.setdefault(key,row)
    def verify(row):
        url=row['url']
        try:posting_reference(url)
        except ValueError:
            lead=indexed_lead(row)
            decision,reason=screen(lead['title'],lead['sourceText'],profile.get('candidate',{}).get('geography') or 'India',profile)
            if decision=='exclude':return {'excluded':True}
            lead['latestDiscoveryDecision']={'screening':'review','reason':reason}

            return {'lead':lead}
        try:
            job=previewer(url,profile)['job']
            if job['screening']=='exclude':return {'excluded':True}
            return {'job':job}
        except (ValueError,OSError) as exc:return {'error':str(exc),'url':url}
    jobs=[];unverified=[];excluded=0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(verify,list(leads.values())[:18]):
            if 'job' in result:jobs.append(result['job'])
            elif 'lead' in result:unverified.append(result['lead'])
            elif 'error' in result:errors.append(result['url']+': '+result['error'])
            else:excluded+=1
    return {'jobs':jobs,'leads':unverified,'checkedAt':utcnow(),'queries':queries,'errors':errors,'excluded':excluded}
