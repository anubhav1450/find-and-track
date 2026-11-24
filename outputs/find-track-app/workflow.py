"""Resume preparation, public job feeds, and evidence-based inbox sync."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
SKILLS={
 'JavaScript':r'\bjavascript\b', 'TypeScript':r'\btypescript\b', 'Python':r'\bpython\b',
 'Java':r'\bjava\b', 'Node.js':r'\bnode(?:\.js|js)?\b', 'Express':r'\bexpress(?:\.js|js)?\b',
 'FastAPI':r'\bfastapi\b', 'React':r'\breact(?:\.js|js)?\b', 'SQL':r'\b(?:sql|mysql|sqlite)\b',
 'MongoDB':r'\bmongodb\b', 'REST APIs':r'\brest(?:ful)?\b', 'Docker':r'\bdocker\b',
 'Git':r'\bgit\b', 'Linux':r'\blinux\b', 'Testing':r'\btests?\b|\btesting\b|\bplaywright\b',
 'OOP':r'\boop\b|object.oriented', 'DSA':r'\bdsa\b|data structures|algorithms',
 'LLM APIs':r'\bllm\b|large language model|genai', 'CI/CD':r'\bci\s*[/\-]\s*cd\b|continuous integration',
 'DevOps':r'\bdevops\b', 'Spring Boot':r'\bspring\s*boot\b', 'C# / .NET':r'c#|\.net|asp\.net',
 'React Native':r'react\s+native', 'RAG':r'\brag\b|retrieval.augmented',
 'Kubernetes':r'\bkubernetes\b|\bk8s\b', 'Django / Flask':r'\bdjango\b|\bflask\b',
 'Pandas / NumPy':r'\bpandas\b|\bnumpy\b', 'AWS':r'\baws\b', 'Azure':r'\bazure\b',
 'Go':r'\bgolang\b|(?-i:\bGo\b)(?: programming| language| developer| engineer)|\bgo(?=\s*[,/])', 'PostgreSQL':r'\bpostgres(?:ql)?\b',
}

def utcnow():
    return datetime.now(timezone.utc).isoformat()

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self,value):
        self.parts.append(value)

def plain(value):
    parser=TextParser();parser.feed(value or '')
    return unescape(' '.join(parser.parts))

def candidate(profile):
    resume=profile.get('resume','')
    evidence={}
    for term,pattern in SKILLS.items():
        matches=[line.strip().lstrip('• ') for line in resume.splitlines() if re.search(pattern,line,re.I)]
        if matches:
            # Prefer actual work/project statements over a generic skills list.
            chosen=next((line for line in matches if re.match(r'(Built|Designed|Added|Implemented|Tested|Integrated|Covered)',line)),matches[0])
            evidence[term]=chosen[:320]
    supplemental={}
    for value in profile.get('confirmedSkills',[]):
        for term,pattern in SKILLS.items():
            if re.search(pattern,value,re.I) and term not in evidence:
                supplemental[term]=value
    existing=profile.get('candidate',{})
    result={**existing,'resumeHash':hashlib.sha256(resume.encode()).hexdigest(),'skills':evidence,'additionalKnowledge':supplemental}
    return result

def skill_comparison(job,profile):
    facts=candidate(profile)
    # Only source JD text or the researched skill list is treated as job demand.
    # Personal tailoring notes may mention gaps and must not introduce requirements.
    demand=(job.get('jd','') or job.get('sourceText',''))+' '+' '.join(job.get('skills',[]))+' '+' '.join(row.get('term','') for row in job.get('requirements',[]))
    relevant=[term for term,pattern in SKILLS.items() if re.search(pattern,demand,re.I)]
    matches=[{'term':term,'evidence':facts['skills'][term]} for term in relevant if term in facts['skills']]
    known=[{'term':term,'evidence':facts['additionalKnowledge'][term]} for term in relevant if term in facts['additionalKnowledge']]
    gaps=[term for term in relevant if term not in facts['skills'] and term not in facts['additionalKnowledge']]
    return {'matches':matches,'knownButOmitted':known,'gaps':gaps,'basis':'exact JD' if job.get('jdVerified') else 'researched skill list / source text; full requirement coverage pending'}

def message_for(person,job,profile,connected=False):
    first=person['name'].split()[0]
    candidate_name=profile.get('name','').split()[0]
    facts=profile.get('candidate',{})
    intro = f"I’m {profile.get('name', '')}"
    status='I applied for' if job.get('status') in ('applied','assessment','interview','offer') else 'I’m interested in'
    comparison=skill_comparison(job,profile)
    terms=[m['term'] for m in comparison['matches'] if m['term'] not in ('Git','DSA','OOP')][:3]
    evidence='My resume includes '+', '.join(terms)+'. ' if terms else ''
    opening=f'Hi {first}, '+('thanks for connecting. ' if connected else '')
    return opening+f"{intro}. {status} the {job['title']} role at {job['company']}. "+evidence+f"Would you be the right person to contact about this role, or could you point me to the relevant recruiter? Thank you, {candidate_name}."

def tailor_resume(profile,comparison):
    original=profile.get('resume','')
    facts=profile.get('candidate',{})
    if not facts.get('graduationYear') or not facts.get('degreeLabel'):
        return original,[]
    terms=[m['term'] for m in comparison['matches']][:6]
    summary=f"{facts['graduationYear']} {facts['degreeLabel']} graduate."
    if terms:summary+=' Relevant skills: '+', '.join(terms)+'.'
    if facts.get('availableImmediately'):summary+=' Available immediately.'
    if facts.get('relocationIndia'):summary+=' Open to relocation within India.'
    pattern=r'(?<=PROFILE\n).*?(?=TECHNICAL SKILLS)'
    found=re.search(pattern,original,re.S)
    if not found:
        return original,[]
    draft=original[:found.start()]+summary+'\n'+original[found.end():]
    edits=[{'section':'Profile','before':found.group().strip(),'after':summary}]
    additional=[m['evidence'] for m in comparison['knownButOmitted']]
    if additional and 'PROFESSIONAL EXPERIENCE' in draft:
        line='Additional knowledge (user-confirmed): '+', '.join(additional)+'\n'
        draft=draft.replace('PROFESSIONAL EXPERIENCE',line+'PROFESSIONAL EXPERIENCE',1)
        edits.append({'section':'Skills','before':'Not listed in the master resume','after':line.strip()})
    return draft,edits

def prepare(data,stamp=None):
    stamp=stamp or utcnow()
    profile=data['profile'];facts=candidate(profile)
    profile['candidate']=facts
    before={j['id']:j.get('preparation',{}) for j in data['jobs']}
    for job in data['jobs']:
        if job.get('sourceKind')=='search-index':
            decision,reason=screen(job['title'],job.get('sourceText',''),facts.get('geography') or 'India',profile)
            job['latestDiscoveryDecision']={'screening':'review' if decision=='shortlist' else decision,'reason':reason}
        comparison=skill_comparison(job,profile)
        fingerprint=hashlib.sha256(json.dumps([facts['resumeHash'],job.get('skills',[]),job.get('requirements',[]),job.get('jd',''),job.get('sourceText',''),job.get('tailoring',''),profile.get('confirmedSkills',[]), {key:facts.get(key) for key in ('graduationYear','degreeLabel','availableImmediately','relocationIndia')}],sort_keys=True).encode()).hexdigest()
        if before[job['id']].get('fingerprint')==fingerprint:
            continue
        terms=[row['term'] for row in comparison['matches']]
        guidance=job.get('tailoring','')
        if not guidance:
            guidance='Emphasize verified '+', '.join(terms[:5])+'.' if terms else 'Full source requirements are needed before tailoring.'
        tailored,edits=tailor_resume(profile,comparison)
        job['preparation']={**comparison,'fingerprint':fingerprint,'preparedAt':stamp,'resumeHash':facts['resumeHash'],'guidance':guidance,'resumeText':tailored,'edits':edits,'resumeType':'Text draft with role-relevant profile emphasis; review before use' if edits else 'Master resume snapshot; source facts insufficient for automatic rewriting'}
    applied={'applied','assessment','interview','offer','rejected','withdrawn','closed'}
    completed_apply=0
    for task in data['actions']:
        job=next((j for j in data['jobs'] if j['id']==task.get('jobId')),None)
        if job and job['status'] in applied and (task.get('kind')=='apply' or task['id']=='A-CG-APPLY') and task.get('status')!='done':
            task['status']='done';task['completedAt']=stamp;completed_apply+=1
    for job in data['jobs']:
        if job['status'] not in ('applied','selected'):
            continue
        associated=any(job['id'] in p.get('jobIds',[]) for p in data['contacts'])
        task=next((a for a in data['actions'] if a.get('jobId')==job['id'] and a.get('kind')=='recruiter research'),None)
        if task is not None and associated:task['status']='done'
        if not associated and task is None:
            data['actions'].append({'id':'A-RECRUITERS-'+job['id'],'jobId':job['id'],'kind':'recruiter research','title':'Recruiter research: '+job['company'],'details':'Queued for assistant research. No background recruiter search is active.','status':'pending'})
    drafts=0
    for person in data['contacts']:
        job=next((j for j in data['jobs'] if j['id'] in person.get('jobIds',[])),None)
        if person.get('status')=='do not contact':
            for task in data['actions']:
                if task.get('contactId')==person['id'] and task.get('kind')=='acceptance':task['status']='done'
            continue
        if not job:
            continue
        if not person.get('connectionNote'):
            person['connectionNote']=f"Hi {person['name'].split()[0]}, I’m interested in {job['company']}’s {job['title']} role. I’d be glad to connect and learn more about the opportunity."[:300]
        if person.get('status') in ('accepted','message prepared') and not person.get('draft'):
            person['draft']=message_for(person,job,profile,connected=True)
            person['draftPreparedAt']=stamp
            drafts+=1
        if person.get('status') in ('accepted','message prepared'):
            existing=next((a for a in data['actions'] if a.get('contactId')==person['id'] and a.get('kind')=='acceptance'),None)
            if existing is None:
                existing={'id':'A-ACCEPT-'+person['id'],'contactId':person['id'],'jobId':job['id'],'kind':'acceptance','status':'pending'}
                data['actions'].append(existing)
            if existing['status']!='done':
                existing['title']='Review message for '+person['name']
                existing['details']='Your role-specific message is ready. Review, copy, and send manually with your chosen resume.'
        if person.get('status') in ('message sent','replied','do not contact'):
            for task in data['actions']:
                if task.get('contactId')==person['id'] and task.get('kind')=='acceptance':
                    task['status']='done'
    return {'jobsPrepared':sum(before[j['id']].get('fingerprint')!=j.get('preparation',{}).get('fingerprint') for j in data['jobs']),'draftsPrepared':drafts,'applicationTasksCompleted':completed_apply}

def match_inbox(data,messages):
    """Only normalized source messages with explicit language and unique identity can transition."""
    outcome={'matched':0,'review':0,'ignored':0,'duplicates':0}
    reviews=data.setdefault('inboxReviews',[])
    known={e.get('messageId') for e in data['events']}|{r.get('messageId') for r in reviews}
    for mail in messages:
        mid=mail.get('id','')
        if not mid:
            outcome['ignored']+=1;continue
        if mid in known:
            outcome['duplicates']+=1;continue
        subject=mail.get('subject','');body=mail.get('text','')
        content=(subject+'\n'+body).lower()
        sender=mail.get('from','').lower()
        kind=None;matches=[]
        if re.search(r'accepted your (?:invitation|connection request)|you(?:’|\x27)re now connected|you are now connected',content) and re.search(r'@(?:[a-z0-9-]+\.)?linkedin\.com\b',sender):
            kind='accepted'
            for person in data['contacts']:
                slug=person.get('url','').split('/in/')[-1].strip('/').split('?')[0]
                full=re.search(r'(?<!\w)'+re.escape(person['name'].lower())+r'(?!\w)',content)
                if full or (slug and '/in/' in body and slug.lower() in body.lower()):
                    matches.append(person)
            # Full identity is needed; first-name-only subjects remain ambiguous.
        elif re.search(r'(?:we have|we.ve) received your application|thank you for applying|application (?:has been )?(?:received|submitted)',content) and not re.search(r'job alert|apply now|jobs you may',subject,re.I):
            kind='applied'
            for job in data['jobs']:
                company=job['company'].lower()
                company_match=company in content
                requisition=str(job.get('requisitionId','')).lower()
                job_match=(requisition and requisition in content) or job['title'].lower() in content
                if company_match and job_match:
                    matches.append(job)
        if kind and not mail.get('authVerified'):
            # Unknown authentication stays review-only; never silently trusts a From display name.
            relevant=bool(matches) or any(j['company'].lower() in content for j in data['jobs'])
            if relevant:
                reviews.append({'id':'IR-'+mid,'messageId':mid,'subject':subject[:160],'url':mail.get('url',''),'reason':'Sender authentication not established','state':'pending'})
                known.add(mid);outcome['review']+=1
            else:outcome['ignored']+=1
            continue
        if kind=='applied' and len(matches)==1:
            job=matches[0]
            employer=next((c for c in data['companies'] if c.get('name')==job['company']),{})
            sender_match=re.search(r'@([a-z0-9.-]+)',sender)
            domain=sender_match.group(1) if sender_match else ''
            employer_domain=urlsplit(employer.get('website','')).hostname or ''
            employer_domain=employer_domain.removeprefix('www.')
            providers=('lever.co','greenhouse.io','workday.com','myworkday.com','smartrecruiters.com')
            if not domain or not ((employer_domain and (domain==employer_domain or domain.endswith('.'+employer_domain))) or any(domain==p or domain.endswith('.'+p) for p in providers)):
                reviews.append({'id':'IR-'+mid,'messageId':mid,'subject':subject[:160],'url':mail.get('url',''),'reason':'Sender domain not tied to employer or supported ATS','state':'pending'})
                known.add(mid);outcome['review']+=1;continue
        if not kind:
            outcome['ignored']+=1;continue
        if len(matches)!=1:
            # Do not retain irrelevant mail about people/companies outside this workspace.
            if not matches and not any(p['name'].split()[0].lower() in subject.lower() for p in data['contacts']) and not any(j['company'].lower() in content for j in data['jobs']):
                outcome['ignored']+=1;continue
            reviews.append({'id':'IR-'+mid,'messageId':mid,'subject':subject[:160],'url':mail.get('url',''),'reason':'No unique full identity / job match','state':'pending'})
            known.add(mid);outcome['review']+=1;continue
        record=matches[0]
        previous=record['status']
        # Old receipts never regress a later application stage or override later user changes.
        advanced={'assessment','interview','offer','rejected','withdrawn','closed'} if kind=='applied' else {'message prepared','message sent','replied','do not contact'}
        at=mail.get('at','')
        if not at:
            outcome['ignored']+=1;continue
        try:
            newer=not record.get('updatedAt') or datetime.fromisoformat(at.replace('Z','+00:00'))>=datetime.fromisoformat(record['updatedAt'].replace('Z','+00:00'))
        except (ValueError,TypeError):
            outcome['ignored']+=1;continue
        changed=previous not in advanced and newer and previous!=kind
        if changed:
            record['status']=kind;record['updatedAt']=at
        job_id=record['id'] if kind=='applied' else (record.get('jobIds') or [''])[0]
        data['events'].append({'id':'E-MAIL-'+mid,'messageId':mid,'jobId':job_id,'contactId':record['id'] if kind=='accepted' else '','type':'Gmail evidence: '+kind,'at':at,'evidenceUrl':mail.get('url',''),'note':('Status confirmed from explicit source message.' if changed else 'Evidence saved; current state preserved.')})
        known.add(mid);outcome['matched']+=1
    return outcome

def screen(title,text,location,profile=None):
    preferences=(profile or {}).get('candidate',{})
    geography=preferences.get('geography','India')
    role_families=preferences.get('roleFamilies',[])
    if isinstance(geography,str) and geography.strip() and geography.strip().lower()!='india':
        requested=geography.strip()
        if requested.lower() not in {'anywhere','worldwide','any'}:
            if not re.search(r'(?<!\w)'+re.escape(requested)+r'(?!\w)',location,re.I):
                return 'review','Requested geography is not established by the posting'
        # Reuse the legacy software/experience checks after geography review.
        location='India'

    title_lower=title.lower();description=text.lower()
    if re.search(r'\b(senior|mid[- ]level|staff|principal|lead|manager|director|architect)\b|\b(?:sde|software (?:development )?engineer)\s*(?:ii|iii|iv|[2-9])\b',title_lower):
        return 'exclude','Role exceeds entry-level seniority'
    if re.search(r'\b(?:product|data|business|cost|financial|fraud) analyst\b',title_lower):
        return 'exclude','Outside software-development scope'
    ambiguous_dev = re.search(r'\b(technology intern|analyst|programmer)\b',title_lower) and re.search(r'build(?:ing)? (?:rest )?apis|software development|develop(?:ing)? (?:web|software) applications',description)
    engineering_intern = 'engineering intern' in title_lower and re.search(r'python|typescript|javascript|backend|full.stack|software|generative ai|gen ai',description)
    ambiguous_dev = ambiguous_dev or engineering_intern
    if not ambiguous_dev and not re.search(r'software|developer|full.?stack|front.?end|back.?end|\bsde\b|test automation',title_lower):
        return 'exclude','Outside software-development scope'
    if not re.search(r'india|bangalore|bengaluru|delhi|noida|hyderabad|mumbai|pune|chennai|gurugram|gurgaon|kolkata|remote.?india',location,re.I):
        return 'exclude','India eligibility not established'
    # A compensation FAQ can mention both options before answering that it is paid.
    compensation = re.sub(r'paid\s*/\s*unpaid\s+internship\s*\?\s*it is a\s+paid\b', 'paid internship', description)
    if re.search(r'\bunpaid\b|permanent night shift|(?:pay|payment of) (?:an? )?(?:application|training|interview) fee',compensation):
        return 'exclude','Disclosed hard exclusion'
    if re.search(r'\b(?:[2-9]|[1-9]\d+) years? of (?:professional |relevant |software development |software engineering )?experience (?:is |are )?required',description):
        return 'exclude','Mandatory experience exceeds fresher scope'
    # Numeric experience claims need local context; bare 0→1 product language never qualifies.
    experience_ranges=re.finditer(r'\b(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*years?\b(.{0,85})',description)
    ranges=[(int(m[1]),int(m[2])) for m in experience_ranges if re.search(r'experience|engineering|development|frontend|backend|building|programming|working|in software',m[3])]
    if any(lo>=2 for lo,_ in ranges) or re.search(r'\b[2-9]\d*\s*\+\s*years?\b|(?:minimum|at least)\s+[2-9]\d*\s+years?',description):
        return 'exclude','Mandatory experience exceeds fresher scope'
    if re.search(r'\b(?:2|two|3|three)[- ]year\b.{0,35}(?:bond|service lock|commitment)|(?:bond|service lock).{0,35}\b(?:2|two|3|three)[- ]years?\b',description):
        return 'exclude','Multi-year service commitment disclosed'
    graduation=preferences.get('graduationYear')
    cohorts=re.findall(r'(?:graduating|graduation|batch|class of)\s*(?:in|of)?\s*(20\d{2})',description)
    if graduation and cohorts and str(graduation) not in cohorts:
        return 'review','Graduation cohort differs from saved profile; confirm eligibility'
    if isinstance(role_families,list):
        specific=[role.strip().lower() for role in role_families if isinstance(role,str) and role.strip()]
        broad={'software development','software engineering','software engineer','developer','programmer'}
        if specific and not broad.intersection(specific):
            aliases={'backend':r'back.?end','frontend':r'front.?end','full stack':r'full.?stack'}
            patterns=[aliases.get(role,re.escape(role)) for role in specific]
            if not any(re.search(pattern,title,re.I) for pattern in patterns):
                return 'review','Role title does not establish a selected role family'
    if re.search(r'\b1\s*[-–]\s*2\s*years?\b',description):
        return 'review','One to two years requested; review eligibility'
    if re.search(r'fresh(?:er| graduate)|new.grad|recent graduate|little or no (?:prior )?experience|\b0\s*[-–]\s*[12]\s*years?\b',description):
        return 'shortlist','Explicit early-career / zero-experience eligibility; other terms need verification'
    return 'review','Experience / graduate eligibility needs review'

# Employer boards are explicit so coverage and failures can be shown to users.
EMPLOYER_BOARDS = (('hevodata', 'Hevo Data'), ('zeta', 'Zeta'), ('cred', 'CRED'), ('drivetrain','Drivetrain'), ('merklescience','Merkle Science'))

def fetch_board(board):
    posts=[]
    for offset in range(0, 1000, 100):
        endpoint=f'https://api.lever.co/v0/postings/{board}?mode=json&limit=100&skip={offset}'
        req=Request(endpoint,headers={'Accept':'application/json','User-Agent':'FindAndTrack/0.2'})
        with urlopen(req,timeout=12) as response:
            raw=response.read(3_000_001)
        if len(raw)>3_000_000:
            raise ValueError('Job feed exceeds response limit.')
        page=json.loads(raw)
        if not isinstance(page,list):
            raise ValueError('Unexpected Lever response.')
        posts.extend(page)
        if len(page)<100:
            return posts
    raise ValueError('Board exceeds pagination limit; incomplete results were discarded.')

def fetch_hevo():
    return fetch_board('hevodata')

GREENHOUSE = {'stripe': ('Stripe', 'stripe.com'), 'rubrik': ('Rubrik', 'www.rubrik.com'),
              'hackerrank': ('HackerRank', 'job-boards.greenhouse.io'),
              'superapp': ('SuperApp', 'job-boards.greenhouse.io')}

def greenhouse_posts(board):
    endpoint=f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true'
    with urlopen(Request(endpoint,headers={'Accept':'application/json'}),timeout=25) as response:
        raw=response.read(32_000_001)
    if len(raw)>32_000_000:
        raise ValueError('Board exceeds size limit')
    return [{'id':str(job['id']), 'text':job['title'], 'hostedUrl':job['absolute_url'],
             'categories':{'location':job['location']['name']},'publishedAt':job.get('first_published'),
             'description':unescape(job.get('content') or '')} for job in json.loads(raw)['jobs']]

def fetch_boards():
    from concurrent.futures import ThreadPoolExecutor
    from startup_sources import ASHBY_BOARDS, ashby_posts
    sources=[(board,company,'lever') for board,company in EMPLOYER_BOARDS]
    sources.extend((board,value[0],'greenhouse') for board,value in GREENHOUSE.items())
    sources.extend((board,company,'ashby') for board,company in ASHBY_BOARDS.items())
    def fetch_one(item):
        board,company,provider=item
        try:
            fetcher={'lever':fetch_board,'greenhouse':greenhouse_posts,'ashby':ashby_posts}[provider]
            return {'board':board,'company':company,'provider':provider,'posts':fetcher(board)}
        except Exception:
            return {'board':board,'company':company,'provider':provider,'error':'Employer feed unavailable. Retry later.'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fetch_one,sources))

def target_roles(profile):
    roles=list(profile.get('candidate',{}).get('roleFamilies') or [])
    skills=candidate(profile)['skills']
    if skills.keys() & {'Node.js','FastAPI','Java','Python'}:
        roles.extend(['backend','back-end'])
    if skills.keys() & {'React','JavaScript','TypeScript'}:
        roles.extend(['frontend','front-end','full stack','full-stack'])
    roles.extend(['software engineer','software developer','graduate engineer','technology intern','SDE'])
    return list(dict.fromkeys(role.lower() for role in roles if isinstance(role,str) and role.strip()))

def remote_listings():
    # Download the cross-employer catalog once per six hours per running process.
    import time
    with _remote_lock:
        cached_at, rows = _remote_cache
        if cached_at and time.monotonic()-cached_at < 21600:
            return rows
        req=Request('https://remotive.com/api/remote-jobs?category=software-dev',headers={'User-Agent':'FindAndTrack/0.2'})
        with urlopen(req,timeout=12) as response:
            raw=response.read(12000001)
        if len(raw)>12000000:
            raise ValueError('Catalog size limit exceeded')
        rows=json.loads(raw)['jobs']
        if not isinstance(rows,list):
            raise ValueError('Invalid jobs catalog')
        _remote_cache[:]=[time.monotonic(),rows]
        return rows

from threading import Lock
_remote_lock=Lock()
_remote_cache=[0,[]]

def count_exclusion(report, reason):
    report['excluded'] += 1
    reasons = report.setdefault('reasons', {})
    reasons[reason] = reasons.get(reason, 0) + 1


def canonical_posting(url):
    from research import canonical
    return canonical(url)


def apply_role_search(data,rows,stamp):
    roles=target_roles(data['profile'])
    report={'source':'Remotive · remote role search','roles':roles,'discovered':len(rows),'added':0,'updated':0,'review':0,'excluded':0,'invalid':0,'reasons':{}}
    known=candidate(data['profile'])
    skills=set(known['skills']) | set(known['additionalKnowledge'])
    existing={canonical_posting(j['url']):j for j in data['jobs'] if j.get('url')}
    for row in rows:
        if not isinstance(row,dict) or not all(isinstance(row.get(k),str) for k in ('title','url','company_name','description')) or not isinstance(row.get('id'),(str,int)):
            report['invalid']+=1
            continue
        if any(not isinstance(row.get(k) or '',str) for k in ('candidate_required_location','salary','job_type','publication_date')):
            report['invalid']+=1
            continue
        title=row.get('title') or ''
        url=row.get('url') or ''
        if not url.startswith('https://remotive.com/remote-jobs/') or not any(role in title.lower() for role in roles):
            count_exclusion(report, 'Outside selected software roles or invalid source link')
            continue
        jd=plain(row.get('description',''))
        location=row.get('candidate_required_location') or 'Unspecified'
        geography=data['profile'].get('candidate',{}).get('geography') or 'India'
        decision,reason=screen(title,jd,geography if location.lower()=='worldwide' else location,data['profile'])
        if decision=='exclude':
            count_exclusion(report, reason)
            continue
        terms=[term for term,pattern in SKILLS.items() if re.search(pattern,jd,re.I)]
        matches=[term for term in terms if term in skills]
        gaps=[term for term in terms if term not in skills]
        evidence={'matchedSkills':matches,'missingSkills':gaps,'checkedAt':stamp}
        published=row.get('publication_date')
        key=canonical_posting(url)
        if key in existing:
            if published: existing[key]['publishedAt']=published
            existing[key].update(discoveryMatch=evidence,sourceCheckedAt=stamp,sourceText=jd[:30000],latestDiscoveryDecision={'screening':decision,'reason':reason})
            report['updated']+=1
            continue
        job={'id':'J-REMOTIVE-'+str(row['id']),'company':row['company_name'],'title':title,'url':url,'source':url,'location':location,'model':'Remote','type':row.get('job_type') or 'Unconfirmed','status':'saved','screening':'review','experience':reason,'fit':'Source: Remotive. Employer opening unverified. Resume matches: '+(', '.join(matches) or 'none identified')+'.','sourceText':jd[:30000],'skills':terms,'discoveryMatch':evidence,'salary':row.get('salary') or 'Unconfirmed','salaryConfirmed':False,'checkedAt':stamp,'createdAt':stamp,'requirements':[],'jdVerified':False}
        data['jobs'].append(job)
        job.update(firstSeenAt=stamp,publishedAt=published,publicationSource='Remotive')
        existing[key]=job
        report['added']+=1
        report['review']+=1
    return report

def get_remote_catalog():
    try:
        return remote_listings(),None
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return [],{'source':'Remotive','error':type(exc).__name__+' retrieving role catalog'}

def apply_boards(data,batches,stamp):
    reports=[]
    for batch in batches:
        if batch.get('error'):
            reports.append({'source':batch['company'],'error':batch['error']})
        else:
            report=refresh_feed(data,batch['posts'],stamp,batch['board'],batch['company'],provider=batch.get('provider'))
            reports.append(report)
            if not report.get('invalid'):
                listed={canonical_posting(p['hostedUrl']) for p in batch['posts'] if isinstance(p,dict) and isinstance(p.get('hostedUrl'),str)}
                for job in data['jobs']:
                    if job.get('publicationSource')==batch['company'] and job.get('url') and canonical_posting(job['url']) not in listed:
                        job['availability']='not returned by source'
                        job['availabilityCheckedAt']=stamp

    return reports

def refresh_feed(data,posts,stamp,board='hevodata',company='Hevo Data',provider=None,include_excluded=False):
    is_greenhouse = provider == 'greenhouse' or board in GREENHOUSE
    is_ashby = provider == 'ashby'
    report={'source':company+(' / Ashby' if is_ashby else ' / Greenhouse' if is_greenhouse else ' / Lever public postings API'),'discovered':len(posts),'added':0,'updated':0,'excluded':0,'review':0,'invalid':0,'reasons':{}}
    for post in posts:
        if not isinstance(post,dict) or not isinstance(post.get('id'),str) or not isinstance(post.get('text'),str) or not isinstance(post.get('categories',{}),dict):
            report['invalid']+=1
            continue
        if any(not isinstance(post.get(k,''),str) for k in ('descriptionPlain','description','additionalPlain','additional','hostedUrl')) or not isinstance(post.get('lists',[]),list):
            report['invalid']+=1
            continue
        title=post.get('text','');categories=post.get('categories',{})
        location=categories.get('location') or 'Unspecified'
        if not isinstance(location,str):
            report['invalid']+=1
            continue
        if not title.strip() or not post['id'] or any(not isinstance(categories.get(k,''),str) for k in ('commitment',)) or not isinstance(post.get('workplaceType') or '',str):
            report['invalid']+=1
            continue
        text=plain(post.get('descriptionPlain') or post.get('description',''))
        text+=' '+ ' '.join(plain(item.get('text','')+' '+item.get('content','')) for item in post.get('lists',[]) if isinstance(item,dict) and isinstance(item.get('text',''),str) and isinstance(item.get('content',''),str))
        text+=' '+plain(post.get('additionalPlain') or post.get('additional',''))
        decision,reason=screen(title,text,location,data.get('profile'))
        url=post.get('hostedUrl','')
        parts=urlsplit(url)
        if is_ashby:
            valid_url=parts.scheme=='https' and parts.hostname=='jobs.ashbyhq.com' and parts.path.startswith('/'+board+'/')
        elif is_greenhouse:
            permitted_hosts={'job-boards.greenhouse.io','boards.greenhouse.io'}
            if board in GREENHOUSE:
                permitted_hosts.add(GREENHOUSE[board][1])
            valid_url=parts.scheme=='https' and parts.hostname in permitted_hosts
        else:
            valid_url=parts.scheme=='https' and parts.hostname=='jobs.lever.co' and parts.path.startswith(f'/{board}/')
        if not valid_url or parts.username or parts.password:
            report['invalid']+=1
            continue
        existing=next((j for j in data['jobs'] if j.get('url') and canonical_posting(j['url'])==canonical_posting(url)),None)
        if existing:
            if post.get('publishedAt'): existing.update(publishedAt=post['publishedAt'],publicationSource=company)
            existing['sourceText']=text[:30000];existing['sourceCheckedAt']=stamp
            existing['availability']='listed';existing['availabilityCheckedAt']=stamp
            facts=candidate(data.get('profile',{}))
            known=set(facts['skills']) | set(facts['additionalKnowledge'])
            terms=[term for term,pattern in SKILLS.items() if re.search(pattern,text,re.I)]
            existing['discoveryMatch']={'matchedSkills':[term for term in terms if term in known],'missingSkills':[term for term in terms if term not in known],'checkedAt':stamp}
            existing['latestDiscoveryDecision']={'screening':decision,'reason':reason}

            # Keep existing eligibility decisions and application progress intact.
            report['updated']+=1;continue
        if decision=='exclude' and not include_excluded:
            count_exclusion(report,reason)
            continue
        job={'id':('J-ASHBY-' if is_ashby else 'J-GH-' if is_greenhouse else 'J-LEVER-')+board.upper()+'-'+post['id'],'company':company,'title':title,'url':url,'location':location,'model':(post.get('workplaceType') or 'Unconfirmed').capitalize(),'type':categories.get('commitment','Unconfirmed'),'status':'saved','screening':decision,'experience':reason,'salary':'Not disclosed; take-home unconfirmed','salaryConfirmed':False,'fit':'Profile comparison prepared from the employer feed; inspect evidence and learning gaps.','unknowns':'Confirm all hard eligibility, compensation, fees, bonds and shifts. Feed availability is not an offer guarantee.','skills':[term for term,pattern in SKILLS.items() if re.search(pattern,text,re.I)],'sourceText':text[:30000],'source':url,'checkedAt':stamp,'createdAt':stamp,'requirements':[],'jd':'','jdVerified':False}
        facts=candidate(data.get('profile',{}))
        known=set(facts['skills']) | set(facts['additionalKnowledge'])
        matches=[term for term in job['skills'] if term in known]
        missing=[term for term in job['skills'] if term not in known]
        job['discoveryMatch']={'matchedSkills':matches,'missingSkills':missing,'checkedAt':stamp}
        job['fit']='Resume matches: '+(', '.join(matches) or 'no recognized skills')+'. Review gaps: '+(', '.join(missing) or 'none recognized')+'. '+reason
        if not matches and decision=='shortlist':
            job['screening']='review'
            decision='review'
        job.update(firstSeenAt=stamp,publishedAt=post.get('publishedAt'),publicationSource=company,availability='listed',availabilityCheckedAt=stamp,dateMeaning=post.get('dateMeaning','Source publication date'))
        data['jobs'].append(job);report['added']+=1
        if decision=='review':report['review']+=1
    return report

def run(db_path,refresh=False,messages=None,fetcher=None):
    from server import validate
    stamp=utcnow();posts=None;source_error=None;batches=None
    if refresh:
        try:
            if fetcher is None:
                catalog,catalog_error=get_remote_catalog()
                batches=fetch_boards()
            else:posts=fetcher()
        except Exception as exc:source_error=f'{type(exc).__name__}: {str(exc)[:160]}'
    with closing(sqlite3.connect(db_path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        revision,payload=db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone();data=json.loads(payload)
        report={'at':stamp,'mode':'prepare + public jobs feed' if refresh else 'prepare','sources':[]}
        if batches is not None:
            report['sources'].append(catalog_error or apply_role_search(data,catalog,stamp))
            report['sources'].extend(apply_boards(data,batches,stamp))
        if posts is not None:report['sources'].append(refresh_feed(data,posts,stamp))
        if source_error:report['sources'].append({'source':'Hevo Data / Lever public postings API','error':source_error})
        if messages is not None:
            report['inbox']=match_inbox(data,messages)
            report['inboxCheckedAt']=stamp
            data.setdefault('workflow',{})['lastInboxCheck']=stamp
        report['preparation']=prepare(data,stamp)
        data.setdefault('workflow',{})['lastRun']=report
        validate(data)
        db.execute('INSERT OR REPLACE INTO history(revision,payload) VALUES (?,?)',(revision,payload))
        db.execute('DELETE FROM history WHERE revision < ?',(revision-49,))
        db.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1',(revision+1,json.dumps(data)))
        return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,default=ROOT/'data/workspace.sqlite3')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--mail',type=Path)
    args=parser.parse_args()
    messages=json.loads(args.mail.read_text()) if args.mail else None
    print(json.dumps(run(args.db,args.refresh,messages),indent=2))

if __name__=='__main__':main()
