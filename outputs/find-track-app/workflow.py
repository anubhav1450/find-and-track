"""Candidate preparation, one documented public jobs feed, and evidence-based inbox sync."""
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
 'Go':r'\bgolang\b|\bgo\b', 'PostgreSQL':r'\bpostgres(?:ql)?\b',
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
    intro=f"I’m a {facts.get('graduationYear',2026)} {facts.get('degreeLabel','B.Tech CSE')} graduate"
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
    summary=f"{facts['graduationYear']} {facts['degreeLabel']} graduate with software internship experience."
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
        comparison=skill_comparison(job,profile)
        fingerprint=hashlib.sha256(json.dumps([facts['resumeHash'],job.get('skills',[]),job.get('requirements',[]),job.get('jd',''),job.get('sourceText',''),job.get('tailoring',''),profile.get('confirmedSkills',[])],sort_keys=True).encode()).hexdigest()
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
            person['connectionNote']=f"Hi {person['name'].split()[0]}, I’m interested in {job['company']}’s {job['title']} role. I’m a 2026 CSE graduate with software internship and backend/full-stack project experience. I’d be glad to connect."[:300]
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

def screen(title,text,location):
    title_lower=title.lower();description=text.lower()
    if re.search(r'\b(senior|staff|principal|lead|manager|director|architect)\b|\bsde\s*(?:ii|iii|2|3)\b',title_lower):
        return 'exclude','Senior/leadership role'
    if not re.search(r'software|developer|full.?stack|front.?end|back.?end|\bsde\b|test automation',title_lower):
        return 'exclude','Outside software-development scope'
    if not re.search(r'india|bangalore|bengaluru|noida|hyderabad|mumbai|pune|chennai|gurugram|gurgaon|kolkata|remote.?india',location,re.I):
        return 'exclude','India eligibility not established'
    if re.search(r'\bunpaid\b|permanent night shift|(?:pay|payment of) (?:an? )?(?:application|training|interview) fee',description):
        return 'exclude','Disclosed hard exclusion'
    # Numeric experience claims need local context; bare 0→1 product language never qualifies.
    ranges=re.findall(r'\b(\d+)\s*(?:[-–]|to)\s*(\d+)\s*years?\s*(?:of\s*)?(?:experience|in software|in development)',description)
    if any(int(lo)>=2 for lo,_ in ranges) or re.search(r'\b[2-9]\d*\s*\+\s*years?\b|(?:minimum|at least)\s+[2-9]\d*\s+years?',description):
        return 'exclude','Mandatory experience exceeds fresher scope'
    if re.search(r'fresh(?:er| graduate)|new.grad|recent graduate|little or no (?:prior )?experience|\b0\s*[-–]\s*[12]\s*years?\b',description):
        return 'shortlist','Explicit early-career / zero-experience eligibility; other terms need verification'
    return 'review','Experience / graduate eligibility needs review'

def fetch_hevo():
    endpoint='https://api.lever.co/v0/postings/hevodata?mode=json&limit=100'
    req=Request(endpoint,headers={'Accept':'application/json','User-Agent':'FindAndTrack-personal-prototype/0.3'})
    with urlopen(req,timeout=12) as response:
        raw=response.read(3_000_001)
        if len(raw)>3_000_000:
            raise ValueError('Job feed is larger than the configured limit.')
        posts=json.loads(raw)
    if not isinstance(posts,list):
        raise ValueError('Unexpected Lever response.')
    return posts

def refresh_feed(data,posts,stamp):
    report={'source':'Hevo Data / Lever public postings API','discovered':len(posts),'added':0,'updated':0,'excluded':0,'review':0}
    for post in posts:
        if not isinstance(post,dict) or not isinstance(post.get('id'),str):
            continue
        title=post.get('text','');categories=post.get('categories',{})
        location=categories.get('location','')
        text=plain(post.get('descriptionPlain') or post.get('description',''))
        text+=' '+ ' '.join(plain(item.get('text','')+' '+item.get('content','')) for item in post.get('lists',[]) if isinstance(item,dict))
        text+=' '+plain(post.get('additionalPlain') or post.get('additional',''))
        decision,reason=screen(title,text,location)
        url=post.get('hostedUrl','')
        if not url.startswith('https://jobs.lever.co/hevodata/'):
            continue
        existing=next((j for j in data['jobs'] if j.get('url','').rstrip('/')==url.rstrip('/')),None)
        if existing:
            existing['sourceText']=text[:30000];existing['sourceCheckedAt']=stamp
            # Keep existing eligibility decisions and application progress intact.
            report['updated']+=1;continue
        if decision=='exclude':
            report['excluded']+=1;continue
        job={'id':'J-LEVER-HEVO-'+post['id'],'company':'Hevo Data','title':title,'url':url,'location':location,'model':post.get('workplaceType','Unconfirmed').capitalize(),'type':categories.get('commitment','Unconfirmed'),'status':'saved','screening':decision,'experience':reason,'salary':'Not disclosed; take-home unconfirmed','salaryConfirmed':False,'fit':'Profile comparison prepared from the employer feed; inspect evidence and learning gaps.','unknowns':'Confirm all hard eligibility, compensation, fees, bonds and shifts. Feed availability is not an offer guarantee.','skills':[term for term,pattern in SKILLS.items() if re.search(pattern,text,re.I)],'sourceText':text[:30000],'source':url,'checkedAt':stamp,'createdAt':stamp,'requirements':[],'jd':'','jdVerified':False}
        data['jobs'].append(job);report['added']+=1
        if decision=='review':report['review']+=1
    return report

def run(db_path,refresh=False,messages=None,fetcher=fetch_hevo):
    from server import validate
    stamp=utcnow();posts=None;source_error=None
    if refresh:
        try:posts=fetcher()
        except Exception as exc:source_error=f'{type(exc).__name__}: {str(exc)[:160]}'
    with closing(sqlite3.connect(db_path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        revision,payload=db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone();data=json.loads(payload)
        report={'at':stamp,'mode':'prepare + public jobs feed' if refresh else 'prepare','sources':[]}
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
