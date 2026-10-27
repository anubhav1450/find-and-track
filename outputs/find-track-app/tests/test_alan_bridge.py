import copy,importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('alan_bridge',ROOT/'tools/findtrack.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
class AlanBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'demo.sqlite3';bridge.init_db(self.db,ROOT/'examples/alan-demo/profile.json');self.source=json.loads((ROOT/'examples/alan-demo/job.json').read_text())
    def tearDown(self):self.tmp.cleanup()
    def proposal(self):return bridge.make_proposal(bridge.read_state(self.db)[1],self.source,'demo')
    def test_preview_has_gaps_and_never_writes(self):
        before=bridge.read_state(self.db);p=self.proposal();self.assertEqual(bridge.read_state(self.db),before)
        self.assertIn('Docker',p['assessment']['skills']['gaps']);self.assertIn('Python',[m['term'] for m in p['assessment']['skills']['matches']]);self.assertEqual(p['job']['status'],'saved');self.assertIn('[Sample]',p['job']['title'])
    def test_exact_proposal_approval_is_required(self):
        p=self.proposal()
        with self.assertRaises(bridge.BridgeError):bridge.save_proposal(self.db,p,'wrong','demo')
        p['job']['title']='Tampered'
        with self.assertRaises(bridge.BridgeError):bridge.save_proposal(self.db,p,p['approvalDigest'],'demo')
        self.assertEqual(bridge.read_state(self.db)[0],1)
    def test_approved_job_persists_with_one_evidence_record(self):
        p=self.proposal();result=bridge.save_proposal(self.db,p,p['approvalDigest'],'demo');self.assertEqual(result['result'],'saved')
        _,data=bridge.read_state(self.db);self.assertEqual(len(data['jobs']),1);self.assertEqual(len(data['events']),1);self.assertEqual(data['jobs'][0]['status'],'saved')
    def test_duplicate_save_preserves_application_progress(self):
        p=self.proposal();bridge.save_proposal(self.db,p,p['approvalDigest'],'demo')
        with sqlite3.connect(self.db) as db:
            d=json.loads(db.execute('SELECT payload FROM workspace').fetchone()[0]);d['jobs'][0]['status']='interview';db.execute('UPDATE workspace SET payload=?',(json.dumps(d),))
        self.source['url']+='?utm_source=demo';p=self.proposal();result=bridge.save_proposal(self.db,p,p['approvalDigest'],'demo');self.assertEqual(result['result'],'already_saved');self.assertEqual(result['status'],'interview');self.assertEqual(len(bridge.read_state(self.db)[1]['jobs']),1)
    def test_profile_changes_require_fresh_review(self):
        p=self.proposal()
        with sqlite3.connect(self.db) as db:
            d=json.loads(db.execute('SELECT payload FROM workspace').fetchone()[0]);d['profile']['resume']='Different resume';db.execute('UPDATE workspace SET payload=?',(json.dumps(d),))
        with self.assertRaises(bridge.BridgeError):bridge.save_proposal(self.db,p,p['approvalDigest'],'demo')
    def test_workspace_and_new_job_state_cannot_be_changed(self):
        p=self.proposal()
        with self.assertRaises(bridge.BridgeError):bridge.save_proposal(self.db,p,p['approvalDigest'],'personal')
        p['job']['status']='applied';p['approvalDigest']=bridge.digest({k:v for k,v in p.items() if k!='approvalDigest'})
        with self.assertRaises(bridge.BridgeError):bridge.save_proposal(self.db,p,p['approvalDigest'],'demo')
    def test_missing_source_and_unsafe_urls_are_rejected(self):
        for change in ({'url':'javascript:alert(1)'},{'url':'https://user:password@example.com/job'},{'jd':''}):
            self.source.update(change)
            with self.assertRaises(bridge.BridgeError):self.proposal()
