import json
from pathlib import Path
import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research import merge_batch
from server import init_db

class ResearchMergeTests(unittest.TestCase):
    def test_research_replay_preserves_application_and_person_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            data={'schema':1,'profile':{'name':'Test','resume':''},'jobs':[{'id':'j1','company':'Example','title':'Engineer','url':'https://example.com/job/1','status':'applied'}],'contacts':[{'id':'p1','name':'Recruiter','status':'accepted','jobIds':['j1']}],'events':[],'actions':[],'companies':[],'rules':[]}
            seed=root/'seed.json';seed.write_text(json.dumps(data));db_path=root/'db.sqlite3';init_db(db_path,seed)
            batch={'jobs':[{'id':'j1','company':'Example','title':'Engineer','url':'https://example.com/job/1','status':'saved'},{'id':'duplicate','company':'Example','title':'Engineer','url':'https://example.com/job/1?utm_source=alert','status':'saved'},{'id':'j2','company':'New','title':'Developer','url':'https://example.com/job/2','status':'saved'}]}
            self.assertEqual(merge_batch(db_path,batch)['jobs'],1)
            self.assertEqual(merge_batch(db_path,batch)['jobs'],0)
            with closing(sqlite3.connect(db_path)) as db:
                revision,payload=db.execute('SELECT revision,payload FROM workspace').fetchone()
            final=json.loads(payload)
            self.assertEqual(revision,2)
            self.assertEqual(final['jobs'][0]['status'],'applied')
            self.assertEqual(final['contacts'][0]['status'],'accepted')
            self.assertEqual(len(final['jobs']),2)

if __name__=='__main__':
    unittest.main()
