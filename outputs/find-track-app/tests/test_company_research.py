import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from company_research import research_company,profile_url,affiliation_supported
from web_discovery import discover_roles,preview_link
from workflow import screen,apply_boards

class ResearchTests(unittest.TestCase):
    def test_people_deduplicate_and_keep_activity_unconfirmed(self):
        def searcher(query,recent=False):
            return {'results':[{'title':'Asha Verma - Example - LinkedIn','url':'https://in.linkedin.com/in/asha/?trk=test','content':'Technical recruiter at Example.'}, {'title':'Asha Verma - Example - LinkedIn','url':'https://www.linkedin.com/in/asha','content':'Technical recruiter at Example.'},{'title':'Wrong Person - Other','url':'https://linkedin.com/in/other','content':'Recruiter at another company'}]}
        result=research_company({'id':'j','company':'Example','title':'Engineer'},searcher=searcher)
        self.assertEqual(len(result['contacts']),1)
        self.assertEqual(result['contacts'][0]['activityStatus'],'unconfirmed')
        self.assertEqual(result['report']['shortfall'],9)
        self.assertEqual(result['report']['activityVerifiedCount'],0)
        self.assertEqual(profile_url('https://linkedin.com.evil.test/in/a'),'')

    def test_company_name_collision_is_rejected(self):
        self.assertFalse(affiliation_supported('Hailey - HR at ATC Drivetrain','HR coordinator at ATC Drivetrain','Drivetrain'))
        self.assertFalse(affiliation_supported('Alex - Drivetrain Engineer at John Deere','Mechanical engineer','Drivetrain'))
        self.assertTrue(affiliation_supported('Usama - Talent Partner @ Drivetrain - LinkedIn','Talent recruiter','Drivetrain'))
        self.assertTrue(affiliation_supported('Swapna - HRBP | Drivetrain | LinkedIn','HR','Drivetrain'))

    def test_search_errors_are_reported_without_false_scam_verdict(self):
        def broken(*args,**kwargs):raise ValueError('Quota reached')
        result=research_company({'id':'j','company':'Example'},searcher=broken)
        self.assertEqual(len(result['report']['errors']),12)
        self.assertEqual(result['contacts'],[])
        self.assertNotIn('safe',result['report']['assessment'].lower())

    def test_posting_index_date_is_not_published_date(self):
        url='https://www.linkedin.com/jobs/view/123'
        row={'url':url,'title':'Backend Developer at Example | LinkedIn','content':'Python internship','published_date':'2026-11-24'}
        result=preview_link(url,{'name':'Test','resume':'Python'},lambda *a,**k:{'results':[row]})['job']
        self.assertEqual(result['company'],'Example')
        self.assertIsNone(result['publishedAt'])
        self.assertEqual(result['availability'],'unconfirmed')
        self.assertFalse(result['jdVerified'])

    def test_role_search_discards_unavailable_postings(self):
        row={'url':'https://jobs.lever.co/example/123','title':'Software Engineer at Example','content':'Python'}
        def missing(*args):raise ValueError('Closed')
        result=discover_roles({'resume':'Python'},lambda *a,**k:{'results':[row]},missing)
        self.assertEqual(result['jobs'],[])
        self.assertEqual(result['leads'],[])
        self.assertEqual(len(result['errors']),1)

    def test_ashby_unlisted_and_secondary_locations(self):
        from startup_sources import ashby_posts
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'jobs':[
                {'title':'Hidden Engineer','isListed':False,'jobUrl':'https://jobs.ashbyhq.com/example/hidden'},
                {'title':'Software Engineer','isListed':True,'jobUrl':'https://jobs.ashbyhq.com/example/123','location':'US','secondaryLocations':[{'location':'India'}],'descriptionPlain':'Python','publishedAt':'2026-11-24'}]}).encode()
        with patch('startup_sources.urlopen',return_value=Response()):rows=ashby_posts('example')
        self.assertEqual(len(rows),1)
        self.assertIn('India',rows[0]['categories']['location'])
        self.assertEqual(rows[0]['dateMeaning'],'Last published by employer; may be a repost')

    def test_live_seniority_variants_and_unrelated_analysts(self):
        for title,text in [('Frontend Engineer','3–6 years in frontend engineering with shipped products'),('Software Engineer','4–6 years of building and operating production backend systems'),('Software Development Engineer 3','Backend work'),('Product Analyst II','Python and SQL analysis')]:
            self.assertEqual(screen(title,text,'India')[0],'exclude')
        self.assertEqual(screen('Software Analyst','Build REST APIs and develop web applications','India')[0],'review')

    def test_bond_and_cohort_constraints(self):
        self.assertEqual(screen('Software Engineer Intern','Full-time role subject to a 2-year service lock-in period','India')[0],'exclude')
        profile={'candidate':{'graduationYear':2026}}
        self.assertEqual(screen('Software Engineer Intern','Freshers graduating 2027 only','India',profile)[0],'review')
        self.assertEqual(screen('Engineering Intern','Build Python APIs and backend systems','India')[0],'review')

    def test_saved_search_key_is_private_and_never_returned(self):
        import search_provider
        with tempfile.TemporaryDirectory() as folder,patch.object(search_provider,'ROOT',Path(folder)),patch.dict('os.environ',{'TAVILY_API_KEY':''}):
            result=search_provider.save_key('tvly-unit-test-key')
            self.assertTrue(result['configured'])
            self.assertNotIn('tvly-unit-test-key',json.dumps(result))
            self.assertEqual((Path(folder)/'data/search-key.json').stat().st_mode & 0o777,0o600)

    def test_linkedin_numeric_link_matches_slug_with_same_id(self):
        from workflow import canonical_posting
        numeric='https://www.linkedin.com/jobs/view/4494314638/'
        slug='https://in.linkedin.com/jobs/view/junior-developer-at-example-4494314638?trk=feed'
        self.assertEqual(canonical_posting(numeric),canonical_posting(slug))
        self.assertNotEqual(canonical_posting(numeric),canonical_posting('https://linkedin.com/jobs/view/4494314639/'))
        calls=[]
        def searcher(query):
            calls.append(query)
            return {'results':[{'url':slug,'title':'Junior Developer at Example','content':'Software development role.'}]}
        job=preview_link(numeric,{'name':'Test','resume':'Python'},searcher)['job']
        self.assertEqual(job['url'],numeric)
        self.assertEqual(job['company'],'Example')
        self.assertEqual(job['availability'],'unconfirmed')
        self.assertIn('4494314638',calls[0])

    def test_linkedin_wrong_job_id_is_not_imported(self):
        with self.assertRaisesRegex(ValueError,'No matching posting'):
            preview_link('https://linkedin.com/jobs/view/4494314638',{'name':'Test'},lambda q:{'results':[{'url':'https://linkedin.com/jobs/view/another-role-4494314639','title':'Developer at Wrong'}]})

    def test_company_only_research_has_no_fake_job_and_career_sources(self):
        from company_research import research_company_name
        def searcher(query,**kwargs):
            return {'results':[{'title':'Asha Verma - Recruiter at Example','url':'https://linkedin.com/in/asha','content':'Recruiter at Example.'}, {'title':'Example careers','url':'https://example.com/careers','content':'Example software engineering careers.'}]}
        result=research_company_name('Example','https://example.com','Backend developer',searcher)
        self.assertEqual(result['report']['searchesRequested'],13)
        self.assertEqual(result['report']['targetRole'],'Backend developer')
        self.assertTrue(result['report']['careerEvidence'])
        self.assertTrue(result['contacts'])
        self.assertEqual(result['contacts'][0]['jobIds'],[])
        self.assertEqual(result['contacts'][0]['activityStatus'],'unconfirmed')

    def test_invalid_company_inputs_do_not_search(self):
        from company_research import research_company_name
        from unittest.mock import Mock
        searcher=Mock()
        for company,website,role in [('', '', ''),('Example','javascript:bad',''),('Example','','x'*151)]:
            with self.assertRaises(ValueError):research_company_name(company,website,role,searcher)
        searcher.assert_not_called()
