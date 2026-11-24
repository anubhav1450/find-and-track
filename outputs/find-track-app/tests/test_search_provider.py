from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search_provider as provider

class Response:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return json.dumps({'results': []}).encode()

class SearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for mock in (patch.dict('os.environ', {'FINDTRACK_SEARCH_CACHE_DIR': self.temp.name}),
                     patch.object(provider, 'credentials', return_value='fixture-key')):
            mock.start()
            self.addCleanup(mock.stop)

    def count(self):
        with closing(sqlite3.connect(Path(self.temp.name) / 'search-cache.sqlite3')) as db:
            return db.execute('SELECT sum(requests) FROM usage').fetchone()[0]

    def test_repeat_query_uses_cache_and_one_request(self):
        with patch.object(provider, 'urlopen', return_value=Response()) as remote:
            self.assertEqual(provider.search('backend India'), provider.search('backend India'))
        self.assertEqual(remote.call_count, 1)
        self.assertEqual(self.count(), 1)

    def test_cap_blocks_new_query_but_allows_cached_query(self):
        with patch.object(provider, 'MONTHLY_LIMIT', 1), patch.object(provider, 'urlopen', return_value=Response()) as remote:
            provider.search('one')
            provider.search('one')
            with self.assertRaisesRegex(ValueError, 'monthly search limit'):
                provider.search('two')
        self.assertEqual(remote.call_count, 1)
        self.assertEqual(self.count(), 1)

    def test_failed_request_counts_conservatively(self):
        with patch.object(provider, 'urlopen', side_effect=URLError('offline')):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                provider.search('one')
        self.assertEqual(self.count(), 1)

    def test_cache_is_scoped_to_key(self):
        with patch.object(provider, 'urlopen', return_value=Response()) as remote:
            provider.search('same')
            with patch.object(provider, 'credentials', return_value='another-fixture'):
                provider.search('same')
        self.assertEqual(remote.call_count, 2)
