"""Search tests: Gemini mocked at the HTTP layer (no real call, no key), fallback keyword -> fuzzy, the graph-id <->
map-key table, and GET /api/search through a real server.py handler on a free local port.
Run: python -m unittest test_search.py   (a few seconds; the place models are not trained)"""
import csv
import io
import json
import os
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import search
import server

FAKE_KEY = 'test-key-not-real-1234'


def gem(text):
    body = json.dumps({'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': 'STOP'}],
                       'modelVersion': 'fake-model-001'}).encode()

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    return R(body)


def http_error(code, message):
    return urllib.error.HTTPError('https://x', code, 'err', {}, io.BytesIO(json.dumps({'error': {'message': message}}).encode()))


class Fake:
    def __init__(self, *actions):
        self.actions, self.calls = list(actions), 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        a = self.actions.pop(0)
        if isinstance(a, BaseException):
            raise a
        return gem(a)


class Base(unittest.TestCase):
    key = FAKE_KEY

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'GEMINI_API_KEY': self.key, 'GEMINI_MODEL': 'fake-model'})
        self.env.start()
        search._state.update(paused_until=0.0, disabled='', last_error='')
        search._cache.clear()
        self.fake = Fake()
        self.p = mock.patch.object(search.gemini, 'URLOPEN', self.fake)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.env.stop()

    def answers(self, *actions):
        self.fake.actions = list(actions)


class TestFallback(Base):
    def test_gemini_good(self):
        self.answers('{"place_id": "sr9", "answer": "The study rooms on 5F are the place to study."}')
        r = search.search('where can I study', tracked=(5, 'canteen'))
        self.assertEqual((r['method'], r['place_id'], r['floor']), ('gemini', 'sr9', 5))
        self.assertEqual(r['answer'], 'The study rooms on 5F are the place to study.')
        self.assertEqual(r['from']['source'], 'tracked')
        self.assertEqual(r['route'][0]['id'], 'canteen')
        self.assertEqual(r['route'][-1]['id'], 'sr9')
        search.search('Where can I   study')                 # same question: cached, no second call
        self.assertEqual(self.fake.calls, 1)

    def test_gemini_none(self):
        self.answers('{"place_id": "NONE", "answer": "Sorry, the chemistry lab is not in the area WalkSense covers."}')
        r = search.search('where is the chemistry lab')
        self.assertEqual((r['method'], r['place_id'], r['route']), ('gemini', None, []))
        self.assertIn('chemistry lab', r['answer'])

    def test_garbage_reply_falls_back(self):
        for bad in ('the canteen!!', '{"place_id": "chem_lab", "answer": "x"}'):
            search._cache.clear()
            self.answers(bad)
            r = search.search('y5401')
            self.assertEqual((r['method'], r['place_id']), ('keyword', 'y5401'))
            self.assertIn('not usable', r['fallback_reason'])

    def test_timeout_pauses_gemini(self):
        self.answers(socket.timeout('timed out'))
        r = search.search('canteen')
        self.assertEqual((r['method'], r['place_id']), ('keyword', 'canteen'))
        r = search.search('male toilet')                     # within PAUSE_S: no new call, answered offline
        self.assertEqual(self.fake.calls, 1)
        self.assertEqual(r['method'], 'keyword')

    def test_http_errors_fall_back(self):
        for code, msg, disabled in ((400, 'API key not valid. Please pass a valid API key.', True), (403, 'denied', True),
                                    (429, 'Resource exhausted', False)):
            search._state.update(paused_until=0.0, disabled='', last_error='')
            self.answers(http_error(code, msg))
            r = search.search('canteen')
            self.assertEqual(r['method'], 'keyword', code)
            self.assertEqual(bool(search._state['disabled']), disabled, code)
            self.assertNotIn(FAKE_KEY, json.dumps(r))

    def test_fuzzy_and_none_offline(self):
        self.answers(http_error(429, 'quota'))
        r = search.search('cantene')                         # typo: keyword misses, fuzzy finds it
        self.assertEqual((r['method'], r['place_id']), ('fuzzy', 'canteen'))
        r = search.search('qwzx blorp')
        self.assertEqual((r['method'], r['place_id']), ('none', None))
        self.assertIn('not find', r['answer'])


class TestNoKey(Base):
    key = ''

    def test_no_key_offline(self):
        r = search.search('toilet on 4th floor')
        self.assertEqual(self.fake.calls, 0)
        self.assertEqual((r['method'], r['floor']), ('keyword', 4))
        self.assertFalse(r['gemini']['configured'])
        self.assertEqual(r['from']['source'], 'default')
        self.assertTrue(r['instructions'][-1].startswith('You have arrived'))

    def test_route_across_floors(self):
        r = search.search('lt1a', from_id='canteen')
        self.assertEqual(r['from']['source'], 'chosen')
        self.assertEqual({s['floor'] for s in r['route']}, {4, 5})
        self.assertTrue(any(s.get('mode') in ('escalator', 'lift_stairs') for s in r['route']))
        self.assertAlmostEqual(r['distance_m'], round(sum(s.get('metres', 0) for s in r['route']), 1), places=1)


class TestIdTable(unittest.TestCase):
    def test_table_matches_floorplan_and_destinations(self):
        fp = json.loads((search.HERE / 'map' / 'floorplan.json').read_text(encoding='utf-8'))
        from_plan = {p['graph_id']: (int(f), k) for f, F in fp['floors'].items() for k, p in F['places'].items()}
        self.assertEqual(from_plan, search.GRAPH_TO_MAP)
        with (search.REQ / 'destinations.csv').open(encoding='utf-8') as f:
            dest = {d['place_id']: (int(d['floor']), d['map_key']) for d in csv.DictReader(f)}
        self.assertEqual(dest, search.GRAPH_TO_MAP)
        self.assertEqual(set(search.astar.graph().nodes), set(search.GRAPH_TO_MAP))
        px = json.loads((search.HERE / 'map' / 'places.json').read_text(encoding='utf-8'))
        for f, k in search.GRAPH_TO_MAP.values():
            self.assertIn(k, px[str(f)]['places'])


class TestServer(Base):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=10) as r:   # local server only
            return r.status, r.read().decode()

    def test_api_search(self):
        self.answers('{"place_id": "y5401", "answer": "Room Y5-401 is on 5F."}')
        server.STATE['session'] = server.ws.Session(5)
        server.STATE['session'].history.append({'kind': 'stop', 'floor': 5, 'lit': 'exit5_door'})
        code, body = self.get('/api/search?q=' + urllib.request.quote('where is y5 401?'))
        r = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual((r['method'], r['place_id'], r['from']['id'], r['from']['source']), ('gemini', 'y5401', 'exit_5', 'tracked'))
        self.assertNotIn(FAKE_KEY, body)
        code, body = self.get('/api/search/places')
        self.assertEqual(len(json.loads(body)), 26)
        code, body = self.get('/')
        self.assertIn('id="searchform"', body)
        self.assertNotIn(FAKE_KEY, body)


if __name__ == '__main__':
    unittest.main()
