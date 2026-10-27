import copy
import json
from pathlib import Path
import sys
import sqlite3
from contextlib import closing
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow import candidate, prepare, match_inbox, screen, refresh_feed, run
from server import init_db

def workspace():
    return {'schema':1,'profile':{'name':'Test Candidate','resume':'Test Candidate\nPROFILE\nA graduate with software internship experience.\nTECHNICAL SKILLS\nPython, JavaScript, REST APIs, Git, SQL\nPROFESSIONAL EXPERIENCE\nBuilt Python APIs and tested them.\n','confirmedSkills':['CI/CD fundamentals'],'candidate':{'graduationYear':2026,'degreeLabel':'B.Tech CSE'}},'jobs':[{'id':'j1','company':'Example','title':'Software Engineer','url':'https://example.com/jobs/123','requisitionId':'123','status':'applied','skills':['Python','CI/CD','React Native'],'requirements':[]}],'contacts':[{'id':'p1','name':'Test Recruiter','company':'Example','status':'request sent','url':'https://www.linkedin.com/in/test-recruiter','jobIds':['j1']}],'companies':[{'id':'c1','name':'Example','website':'https://example.com'}],'events':[],'actions':[{'id':'apply','kind':'apply','jobId':'j1','title':'Apply','status':'pending'}],'rules':[]}

class WorkflowTests(unittest.TestCase):
    def test_resume_evidence_and_confirmed_basics_are_distinct(self):
        facts=candidate(workspace()['profile'])
        self.assertIn('Python',facts['skills'])
        self.assertNotIn('Java',facts['skills'])
        self.assertIn('CI/CD',facts['additionalKnowledge'])
        self.assertNotIn('React Native',facts['skills'])

    def test_requirement_terms_refresh_preparation_without_inventing_evidence(self):
        d=workspace();d['jobs'][0]['skills']=['Python'];prepare(d)
        self.assertEqual(d['jobs'][0]['preparation']['knownButOmitted'],[])
        d['jobs'][0]['requirements']=[{'term':'CI/CD','weight':1,'coverage':'known','evidence':'User confirms basics'}]
        self.assertEqual(prepare(d)['jobsPrepared'],1)
        self.assertEqual(d['jobs'][0]['preparation']['knownButOmitted'][0]['term'],'CI/CD')

    def test_preparation_is_truthful_idempotent_and_completes_apply_task(self):
        d=workspace();d['contacts'][0]['status']='accepted';original=d['profile']['resume']
        result=prepare(d,'2026-10-27T10:00:00+00:00')
        prepared=d['jobs'][0]['preparation']
        self.assertEqual(result['jobsPrepared'],1)
        self.assertEqual(d['actions'][0]['status'],'done')
        self.assertIn('React Native',prepared['gaps'])
        self.assertIn('user-confirmed',prepared['resumeText'])
        self.assertEqual(d['profile']['resume'],original)
        self.assertIn('thanks for connecting',d['contacts'][0]['draft'])
        self.assertNotIn('React Native',d['contacts'][0]['draft'])
        self.assertEqual(prepare(d)['jobsPrepared'],0)
        self.assertEqual(len([a for a in d['actions'] if a.get('kind')=='acceptance']),1)

    def test_user_draft_is_preserved_and_do_not_contact_closes_task(self):
        d=workspace();p=d['contacts'][0];p['status']='accepted';p['draft']='My reviewed message'
        prepare(d);self.assertEqual(p['draft'],'My reviewed message')
        p['status']='do not contact';prepare(d)
        self.assertTrue(all(a['status']=='done' for a in d['actions'] if a.get('contactId')=='p1'))

    def mail(self,**kwargs):
        return {'id':'m1','from':'Test Recruiter <invitations@linkedin.com>','subject':'Test Recruiter accepted your invitation','text':'You are now connected with Test Recruiter.','authVerified':True,'at':'2026-10-27T10:00:00+00:00','url':'https://mail.google.com/mail/u/0/#all/m1',**kwargs}

    def test_acceptance_is_matched_replayed_once_and_prepared(self):
        d=workspace();m=self.mail();self.assertEqual(match_inbox(d,[m])['matched'],1)
        self.assertEqual(d['contacts'][0]['status'],'accepted')
        self.assertEqual(match_inbox(d,[m])['duplicates'],1)
        prepare(d);self.assertEqual(len(d['events']),1)
        self.assertIn('thanks for connecting',d['contacts'][0]['draft'])

    def test_incoming_invitation_is_not_acceptance(self):
        d=workspace();result=match_inbox(d,[self.mail(subject='Test Recruiter wants to connect',text='Accept invitation')])
        self.assertEqual(result['ignored'],1);self.assertEqual(d['contacts'][0]['status'],'request sent')

    def test_first_name_only_and_unknown_authentication_are_reviewed(self):
        d=workspace();result=match_inbox(d,[self.mail(subject='Test accepted your invitation',text='Explore their network')])
        self.assertEqual(result['review'],1);self.assertEqual(d['contacts'][0]['status'],'request sent')
        d=workspace();result=match_inbox(d,[self.mail(authVerified=False)])
        self.assertEqual(result['review'],1);self.assertEqual(d['contacts'][0]['status'],'request sent')

    def test_unrelated_acceptance_ignored_and_later_states_not_regressed(self):
        d=workspace();result=match_inbox(d,[self.mail(subject='Another Person accepted your invitation',text='You are now connected with Another Person')])
        self.assertEqual(result['ignored'],1)
        d['contacts'][0]['status']='message sent';match_inbox(d,[self.mail()])
        self.assertEqual(d['contacts'][0]['status'],'message sent')

    def test_application_requires_unique_job_and_trusted_sender(self):
        m=self.mail(from_='')
        m.update({'from':'careers@example.com','subject':'Application received: Software Engineer at Example','text':'We have received your application for Software Engineer at Example, requisition 123.'})
        d=workspace();d['jobs'][0]['status']='saved';match_inbox(d,[m]);self.assertEqual(d['jobs'][0]['status'],'applied')
        d=workspace();d['jobs'][0]['status']='saved';m['from']='spam@unrelated.example';result=match_inbox(d,[m])
        self.assertEqual(result['review'],1);self.assertEqual(d['jobs'][0]['status'],'saved')
        d=workspace();d['jobs'][0]['status']='saved';d['jobs'].append({**d['jobs'][0],'id':'j2'})
        m['from']='careers@example.com';self.assertEqual(match_inbox(d,[m])['review'],1)

    def test_profile_screening_handles_seniority_geography_and_zero_to_one(self):
        self.assertEqual(screen('SDE I','0-1 years in software development','Bangalore, India')[0],'shortlist')
        self.assertEqual(screen('Software Engineer','Build a product from 0-1','Bangalore, India')[0],'review')
        self.assertEqual(screen('Senior Software Engineer','0-1 years','India')[0],'exclude')
        self.assertEqual(screen('Software Engineer','3+ years experience','India')[0],'exclude')
        self.assertEqual(screen('Software Engineer','Fresh graduates welcome','United States')[0],'exclude')

    def test_feed_updates_preserve_existing_application_and_deduplicate(self):
        d=workspace();d['jobs'][0]['url']='https://jobs.lever.co/hevodata/existing'
        posts=[{'id':'existing','text':'Software Engineer','hostedUrl':'https://jobs.lever.co/hevodata/existing','categories':{'location':'Bangalore, India'},'descriptionPlain':'0-1 years in software development. Python REST APIs.'},{'id':'new','text':'Backend Developer','hostedUrl':'https://jobs.lever.co/hevodata/new','categories':{'location':'Bangalore, India'},'descriptionPlain':'Fresh graduates welcome. Python.'}]
        result=refresh_feed(d,posts,'2026-10-27T10:00:00Z');self.assertEqual(result['added'],1)
        self.assertEqual(d['jobs'][0]['status'],'applied')
        self.assertEqual(refresh_feed(d,posts,'2026-10-27T10:00:00Z')['added'],0)

    def test_failed_feed_is_visible_and_preserves_local_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);seed=root/'seed.json';seed.write_text(json.dumps(workspace()));db=root/'state.sqlite3';init_db(db,seed)
            def failed():raise TimeoutError('fixture source timeout')
            report=run(db,refresh=True,fetcher=failed)
            self.assertIn('error',report['sources'][0])
            with closing(sqlite3.connect(db)) as connection:
                state=json.loads(connection.execute('select payload from workspace').fetchone()[0])
            self.assertEqual(state['jobs'][0]['status'],'applied')
            self.assertEqual(len(state['jobs']),1)

if __name__=='__main__':unittest.main()
