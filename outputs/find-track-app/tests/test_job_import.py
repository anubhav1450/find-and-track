import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from job_import import preview_job, posting_reference
from workflow import refresh_feed, screen, tailor_resume, candidate


class JobImportTests(unittest.TestCase):
    def test_greenhouse_preview_keeps_source_and_does_not_mutate_profile(self):
        profile={'name':'Candidate','resume':'Python Git'}
        before=copy.deepcopy(profile)
        row={'id':123,'title':'Software Engineer','company_name':'Example','absolute_url':'https://job-boards.greenhouse.io/example/jobs/123','content':'<p>Python. Fresh graduates welcome.</p>','location':{'name':'India'},'first_published':'2026-11-01T12:00:00Z'}
        fetch=Mock(return_value=row)
        job=preview_job(row['absolute_url']+'?gh_src=tracking',profile,fetch)['job']
        self.assertEqual(profile,before)
        self.assertEqual(job['publishedAt'],row['first_published'])
        self.assertIn('Fresh graduates',job['sourceText'])
        self.assertIn('Python',job['skills'])
        self.assertIn('preparation',job)
        fetch.assert_called_once_with('https://boards-api.greenhouse.io/v1/boards/example/jobs/123')

    def test_unsupported_and_internal_urls_never_fetch(self):
        fetch=Mock()
        for url in ['http://127.0.0.1/','https://localhost/','https://jobs.lever.co.evil.com/a/b','https://jobs.lever.co/a%2fb/123','https://user:pass@jobs.lever.co/a/123','https://jobs.lever.co:8000/a/123','https://placement.acciojob.com/jobs/']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                preview_job(url,{'name':'A','resume':''},fetch)
        fetch.assert_not_called()

    def test_lever_apply_link_and_ineligible_role_remain_reviewable(self):
        row={'id':'abc-123','text':'Senior Software Engineer','hostedUrl':'https://jobs.lever.co/example/abc-123','categories':{'location':'India'},'descriptionPlain':'Python. 5+ years experience required.'}
        job=preview_job(row['hostedUrl']+'/apply',{'name':'A','resume':'Python'},lambda _:row)['job']
        self.assertEqual(job['screening'],'exclude')
        self.assertEqual(job['status'],'saved')

    def test_closed_or_mismatched_posting_cannot_be_previewed(self):
        with self.assertRaises(ValueError):
            preview_job('https://job-boards.greenhouse.io/example/jobs/123',{},lambda _: {'id':999})

    def test_tracking_variants_do_not_duplicate_or_regress_application(self):
        original={'id':'manual','url':'https://jobs.lever.co/hevodata/123?utm_source=accio','status':'applied','notes':'Keep this','screening':'review'}
        data={'profile':{'resume':'Python'},'jobs':[original]}
        post={'id':'123','text':'Software Engineer','hostedUrl':'https://jobs.lever.co/hevodata/123','categories':{'location':'India'},'descriptionPlain':'Python. Fresh graduate.'}
        report=refresh_feed(data,[post], '2026-11-24T00:00:00Z')
        self.assertEqual(report['updated'],1)
        self.assertEqual(len(data['jobs']),1)
        self.assertEqual(original['status'],'applied')
        self.assertEqual(original['notes'],'Keep this')

    def test_malformed_post_does_not_drop_valid_results(self):
        data={'profile':{'resume':'Python'},'jobs':[]}
        good={'id':'123','text':'Software Engineer','hostedUrl':'https://jobs.lever.co/hevodata/123','categories':{'location':'India'},'descriptionPlain':'Python. Fresh graduate.'}
        report=refresh_feed(data,[{'id':'broken','text':None},good], '2026-11-24T00:00:00Z')
        self.assertEqual(report['invalid'],1)
        self.assertEqual(report['added'],1)

    def test_experience_exclusion_wins_over_selected_role_review(self):
        profile={'candidate':{'roleFamilies':['frontend']}}
        self.assertEqual(screen('Backend Developer','Minimum 4 years experience','India',profile)[0],'exclude')
        self.assertEqual(screen('Software Engineer','Freshers welcome, 1-2 years experience','India')[0],'review')

    def test_draft_and_skills_do_not_invent_experience(self):
        profile={'resume':'PROFILE\nGraduate.\nTECHNICAL SKILLS\nPython. Ready to go.','candidate':{'graduationYear':2026,'degreeLabel':'B.Tech'}}
        draft,_=tailor_resume(profile,{'matches':[],'knownButOmitted':[]})
        self.assertNotIn('internship',draft)
        self.assertNotIn('Go',candidate(profile)['skills'])
