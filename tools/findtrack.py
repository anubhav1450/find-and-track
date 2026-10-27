#!/usr/bin/env python3
"""Local Alan bridge. Preview is read-only; saving requires the exact reviewed digest."""
import argparse,copy,hashlib,json,os,re,sqlite3,sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'outputs'/'find-track-app'
sys.path.insert(0,str(APP))
from server import init_db,validate
from research import canonical
from workflow import skill_comparison,prepare,screen,utcnow

class BridgeError(ValueError):pass

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def read_json(path):
    if path.stat().st_size>1_000_000:raise BridgeError('Input must be under 1 MB.')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise BridgeError('Expected a JSON object.')
    return value

def db_for(workspace):
    return APP/'data'/'workspace.sqlite3' if workspace=='personal' else ROOT/'work'/'alan-demo'/'workspace.sqlite3'

def read_state(path):
    if not path.exists():raise BridgeError('Workspace is not initialized. Run the demo command first.')
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
    if not row:raise BridgeError('Workspace is empty.')
    return row[0],validate(json.loads(row[1]))

def profile_signature(data):return digest({'profile':data['profile'],'rules':data['rules']})

def make_proposal(data,source,workspace):
    for key in ('title','company','url','jd','location'):
        if not isinstance(source.get(key),str) or not source[key].strip():raise BridgeError('Missing required field: '+key)
    url=urlsplit(source['url'])
    if url.scheme not in ('https','http') or not url.hostname or url.username or url.password:raise BridgeError('Use an ordinary http(s) posting URL without embedded credentials.')
    if len(source['jd'])>60_000:raise BridgeError('JD must be under 60,000 characters.')
    if not isinstance(source.get('sample',False),bool):raise BridgeError('sample must be true or false.')
    decision,reason=screen(source['title'],source['jd'],source['location'])
    # An unspecified location is reviewable, never proof of ineligibility.
    if reason=='India eligibility not established' and source['location'].strip().lower() in ('unknown','unconfirmed','not stated'):decision,reason='review','Location / India eligibility needs confirmation'
    job={'id':'J-ALAN-'+hashlib.sha256(canonical(source['url']).encode()).hexdigest()[:16],'title':source['title'].strip(),'company':source['company'].strip(),'url':source['url'].strip(),'jd':source['jd'].strip(),'jdVerified':False,'location':source['location'].strip(),'model':source.get('model','Unconfirmed'),'type':source.get('type','Unconfirmed'),'status':'saved','screening':decision,'experience':reason,'skills':[],'requirements':[],'salary':source.get('salary','Unconfirmed — verify take-home pay'),'salaryConfirmed':False,'source':source['url'],'checkedAt':utcnow(),'createdAt':utcnow(),'fit':'Provisional comparison from the supplied JD. Review eligibility and source evidence.','unknowns':'Confirm vacancy availability, take-home pay, fees, bond, shifts and actual recruiter ownership.','notes':'SYNTHETIC DEMO FIXTURE — not a real vacancy.' if source.get('sample') else 'Added through the Alan companion workflow. Source content supplied by the assistant and reviewed by the user.'}
    if source.get('sample') and not job['title'].startswith('[Sample]'):job['title']='[Sample] '+job['title']
    staging={'schema':1,'profile':copy.deepcopy(data['profile']),'rules':copy.deepcopy(data['rules']),'jobs':[job],'contacts':[],'actions':[],'events':[],'companies':[]}
    prepare(staging)
    result={'version':1,'workspace':workspace,'profileSignature':profile_signature(data),'job':staging['jobs'][0],'assessment':{'screening':decision,'reason':reason,'skills':skill_comparison(job,data['profile']),'salary':'Unconfirmed unless checked against the actual offer; gross and CTC are not take-home.','limits':'Term-based evidence comparison, not an ATS score or verified hiring prediction.'}}
    result['approvalDigest']=digest(result)
    return result

def save_proposal(path,proposal,approval,workspace):
    claimed=proposal.get('approvalDigest');unsigned={k:v for k,v in proposal.items() if k!='approvalDigest'}
    if not isinstance(approval,str) or approval!=claimed or digest(unsigned)!=claimed:raise BridgeError('Approval must match the exact, unchanged proposal digest shown in preview.')
    if proposal.get('workspace')!=workspace:raise BridgeError('Proposal belongs to a different workspace.')
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE');revision,payload=db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone();data=validate(json.loads(payload))
        if profile_signature(data)!=proposal.get('profileSignature'):raise BridgeError('Profile or rules changed. Prepare and review a fresh proposal.')
        job=proposal['job'];url=canonical(job['url'])
        existing=next((j for j in data['jobs'] if j['id']==job['id'] or canonical(j.get('url',''))==url),None)
        if existing:return {'result':'already_saved','jobId':existing['id'],'status':existing['status'],'revision':revision}
        if job.get('status')!='saved':raise BridgeError('A new job must start Saved. Applying remains manual.')
        data['jobs'].insert(0,job)
        data['events'].insert(0,{'id':'E-ALAN-'+claimed[:20],'jobId':job['id'],'type':'Job saved from Alan companion','note':'User approved the reviewed proposal. No application or outreach was sent.','at':utcnow(),'evidenceUrl':job['url']})
        validate(data)
        db.execute('INSERT OR REPLACE INTO history(revision,payload) VALUES (?,?)',(revision,payload))
        db.execute('DELETE FROM history WHERE revision < ?',(revision-49,))
        db.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1',(revision+1,json.dumps(data)))
    return {'result':'saved','jobId':job['id'],'status':'saved','revision':revision+1,'dashboard':'http://127.0.0.1:8766/' if workspace=='demo' else 'http://127.0.0.1:8765/'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',choices=['demo','personal'],default='demo')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('demo');commands.add_parser('profile');commands.add_parser('jobs')
    preview=commands.add_parser('preview');preview.add_argument('--job',type=Path,required=True)
    save=commands.add_parser('save');save.add_argument('--proposal',type=Path,required=True);save.add_argument('--approval',required=True)
    serve=commands.add_parser('serve');serve.add_argument('--port',type=int)
    args=parser.parse_args();path=db_for(args.workspace)
    try:
        if args.command=='demo':
            if args.workspace!='demo':raise BridgeError('The demo command never initializes or replaces a personal workspace.')
            existed=path.exists();init_db(path,ROOT/'examples'/'alan-demo'/'profile.json')
            print(json.dumps({'result':'existing_demo' if existed else 'demo_created','database':str(path),'personalWorkspaceTouched':False}));return
        if args.command=='serve':
            if not path.exists():raise BridgeError('Initialize the selected workspace before serving it.')
            os.execv(sys.executable,[sys.executable,str(APP/'server.py'),'--db',str(path),'--port',str(args.port or (8766 if args.workspace=='demo' else 8765))])
        revision,data=read_state(path)
        if args.command=='profile':result={'workspace':args.workspace,'revision':revision,'profile':data['profile'],'rules':data['rules']}
        elif args.command=='jobs':result={'workspace':args.workspace,'revision':revision,'jobs':[{'id':j['id'],'title':j['title'],'company':j['company'],'status':j['status'],'url':j['url']} for j in data['jobs']]}
        elif args.command=='preview':
            proposal=make_proposal(data,read_json(args.job),args.workspace)
            folder=ROOT/'work'/('alan-'+args.workspace)/'proposals';folder.mkdir(parents=True,exist_ok=True)
            file=folder/(proposal['approvalDigest']+'.json');file.write_text(json.dumps(proposal,indent=2));file.chmod(0o600)
            result={'proposalFile':str(file),'approvalDigest':proposal['approvalDigest'],'assessment':proposal['assessment'],'job':{'title':proposal['job']['title'],'company':proposal['job']['company'],'url':proposal['job']['url']},'saved':False}
        else:result=save_proposal(path,read_json(args.proposal),args.approval,args.workspace)
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
