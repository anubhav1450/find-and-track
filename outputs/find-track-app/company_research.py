"""Source-backed company and contact research using public search results."""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit
from concurrent.futures import ThreadPoolExecutor
from search_provider import search
from workflow import plain, utcnow


def safe_url(value):
    if not isinstance(value,str):return ''
    try:
        parts=urlsplit(value)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:return ''
        return urlunsplit((parts.scheme,parts.netloc,parts.path,parts.query,''))
    except ValueError:return ''


def profile_url(value):
    url=safe_url(value)
    if not url:return ''
    parts=urlsplit(url)
    host=parts.hostname
    if not (host=='linkedin.com' or host.endswith('.linkedin.com')) or not re.fullmatch(r'/in/[^/]+/?',parts.path):return ''
    return 'https://www.linkedin.com'+parts.path.rstrip('/')


def clean_company(value):
    if not isinstance(value,str) or not 2<=len(value.strip())<=150:raise ValueError('Confirm the company name before researching it.')
    return re.sub(r'["\r\n]', ' ',value).strip()


def affiliation_supported(heading,content,company):
    name=re.escape(company)
    # Require an employer relationship, not a word match in a person's skills/team.
    headline=heading+' '+content[:700]
    direct=rf'(?:\bat\s+|@\s*){name}(?:\s*[|,·(.]|\s+-|\s*$|\s+AI\b|\.ai\b)'
    titled=rf'(?: - |\| |Building ){name}(?: \||$| \|)'
    present=rf'at {name}\s*\([^)]*\b(?:present|current)\b'
    return bool(re.search(direct,headline,re.I) or re.search(titled,heading,re.I) or re.search(present,content,re.I))


def research_company(job, website='', searcher=search):
    company=clean_company(job.get('company'))
    title=job.get('title','Software Engineer')
    checked=utcnow()
    identity_query=f'{company} official company website founders'
    try:identity_response=searcher(identity_query);identity_error=None
    except (ValueError,OSError) as exc:identity_response={'results':[]};identity_error=str(exc)
    entity=company
    known_site=safe_url(website)
    compact=re.sub(r'[^a-z0-9]','',company.lower())
    if not known_site:
        for row in identity_response.get('results',[]):
            url=safe_url(row.get('url')) if isinstance(row,dict) else ''
            host=urlsplit(url).hostname or ''
            if len(compact)>3 and compact in re.sub(r'[^a-z0-9]','',host) and not any(x in host for x in ('linkedin','facebook','tavily','glassdoor','jobs.','careers.')):
                known_site=url;break
    if known_site:entity=urlsplit(known_site).hostname.removeprefix('www.')
    queries=[
        ('identity',identity_query),
        ('company_profile',f'{entity} company LinkedIn'),
        ('concerns',f'{entity} recruitment scam job application fee complaints'),
        ('recruiter',f'{entity} talent acquisition recruiter LinkedIn'),
        ('hr',f'{entity} HRBP people LinkedIn'),
        ('engineer',f'{entity} software engineer LinkedIn'),
        ('team',f'{entity} engineering leadership CTO LinkedIn'),
        ('backend',f'{entity} backend developer engineer LinkedIn'),
        ('frontend',f'{entity} frontend fullstack engineer LinkedIn'),
        ('people_lead',f'{entity} head of people human resources LinkedIn'),
        ('staff',f'{entity} staff engineer platform LinkedIn'),
        ('activity',f'{entity} hiring internship engineer LinkedIn posts'),
    ]
    def query(item):
        kind,text=item
        if kind=='identity':return kind,identity_response,identity_error
        try:return kind,searcher(text,recent=kind=='activity'),None
        except (ValueError,OSError) as exc:return kind,{'results':[]},str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:batches=list(pool.map(query,queries))
    evidence=[];people={};errors=[];activity=[]
    for kind,response,error in batches:
        if error:errors.append({'section':kind,'error':error});continue
        for row in response.get('results',[]):
            if not isinstance(row,dict):continue
            url=safe_url(row.get('url'));heading=plain(row.get('title',''))
            content=plain(row.get('content',''))
            if not url or not heading:continue
            text=heading+' '+content
            if company.casefold() not in text.casefold():continue
            # Results are discovery evidence. A search date never establishes employment/activity freshness.
            item={'title':heading[:250],'url':url,'summary':content[:600],'checkedAt':checked,'kind':kind}
            if kind in ('identity','company_profile','concerns'):
                if kind!='concerns' or re.search(r'scam|fraud|complaint|application fee|interview fee',text,re.I):evidence.append(item)
                continue
            if kind=='activity':
                activity.append(item);continue
            profile=profile_url(url)
            if not profile or not affiliation_supported(heading,content,company):continue
            name=re.split(r'\s+[|–—-]\s+',heading)[0].strip()
            if not 2<=len(name.split())<=7 or name.lower().startswith(('profiles','top ','people')):continue
            lowered=(heading+' '+content[:700]).lower()
            if not re.search(r'recruit|talent|human resources|\bhr\b|hrbp|people operations|engineer|developer|gen ai|\bcto\b|founder',lowered):continue
            contact_type='Recruiter / HR' if re.search(r'recruit|talent acquisition|human resources|\bhr\b|hrbp|people operations',lowered) else 'Engineering / team'
            score=3 if contact_type=='Recruiter / HR' else 1
            if company.casefold() in heading.casefold():score+=2
            if re.search(r'former|previously|ex-'+re.escape(company.lower()),lowered):score-=3
            item={'id':'P-WEB-'+hashlib.sha256(profile.encode()).hexdigest()[:16],
                  'name':name,'company':company,'role':heading[:200], 'url':profile,'source':url,
                  'status':'discovered','jobIds':[job['id']] if job.get('id') else [], 'contactType':contact_type,
                  'relevance':'Indexed company and role match; verify current employer and vacancy relevance.',
                  'uncertainty':'Current employment and recent activity require confirmation. Search snippets may be stale.',
                  'checkedAt':checked,'activityStatus':'unconfirmed','affiliationStatus':'unconfirmed',
                  'evidenceSummary':content[:500],'researchScore':score}
            if profile not in people or score>people[profile]['researchScore']:people[profile]=item
    contacts=sorted(people.values(),key=lambda p:(-p['researchScore'],p['name']))[:20]
    concerns=[]
    jd=job.get('sourceText') or job.get('jd') or ''
    if re.search(r'(?:pay|payment|refundable)\s+(?:an?\s+)?(?:application|interview|training|security|registration)?\s*(?:fee|deposit)',jd,re.I):
        concerns.append('The saved posting mentions a fee or deposit. Inspect the original wording before proceeding.')
    if any(e['kind']=='concerns' for e in evidence):
        concerns.append('Potential complaint-related search results were found. Check the sources and company identity; a search hit alone does not establish wrongdoing.')
    if not evidence:concerns.append('Company identity could not be corroborated from the available search results.')
    report={'company':company,'checkedAt':checked,'assessment':'Evidence collected; employer and offer require review.',
            'website':safe_url(website),'websiteCandidate':known_site,'evidence':evidence,'concerns':concerns,'activityEvidence':activity,
            'contactsFound':len(contacts),'targetContacts':10,'activityVerifiedCount':0,
            'shortfall':max(0,10-len(contacts)),'errors':errors,
            'searchesRequested':len(queries)}
    return {'report':report,'contacts':contacts}


def research_company_name(company, website='', role='', searcher=search):
    """Research an employer without inventing a job or application record."""
    company=clean_company(company)
    if not isinstance(role,str) or len(role)>150:raise ValueError('Use a role under 150 characters.')
    if not isinstance(website,str) or (website and not safe_url(website)):
        raise ValueError('Use an HTTPS company website or leave it blank.')
    role=re.sub(r'["\r\n]', ' ',role).strip()
    result=research_company({'company':company,'title':role or 'Software Engineer'},website,searcher)
    report=result['report']
    report['targetRole']=role
    report['identityStatus']='user-supplied website; verify identity' if website else 'unconfirmed; review company identity before saving'
    report['careerEvidence']=[]
    entity=website or company
    try:
        response=searcher(f'{entity} careers jobs {role or "software engineer internship"}')
        for row in response.get('results',[]):
            if not isinstance(row,dict):continue
            url=safe_url(row.get('url'));title=plain(row.get('title',''));content=plain(row.get('content',''))
            if not url or company.casefold() not in (title+' '+content).casefold():continue
            report['careerEvidence'].append({'url':url,'title':title[:250],'summary':content[:600],'kind':'careers','checkedAt':report['checkedAt']})
    except (ValueError,OSError) as exc:report['errors'].append({'section':'careers','error':str(exc)})
    report['searchesRequested']+=1
    return result
