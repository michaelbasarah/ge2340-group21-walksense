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
import urllib.parse
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
        self.assertTrue(any(s.get('mode') in ('escalator', 'lift', 'stairs') for s in r['route']))
        self.assertAlmostEqual(r['distance_m'], round(sum(s.get('metres', 0) for s in r['route']), 1), places=1)


class TestPlanner(Base):
    """Route planner + modes + toilet filter through search.py (Gemini off: no key)."""
    key = ''

    def test_toilet_query_uses_mode_and_filter(self):
        for q in ('toilet', 'nearest restroom', 'washroom please'):
            r = search.search(q, from_id='canteen', gender='female')
            self.assertEqual(r['place_id'], 'female_toilet', q)
            self.assertIn('female toilet', r['answer'])
        r = search.search('toilet', from_id='canteen', mode='accessible', gender='female')    # only the 4F mixed one
        self.assertEqual(r['place_id'], 'disabled_toilet_4F')
        self.assertEqual([c['kind'] for c in r['connectors']], ['lift'])
        self.assertEqual(search.search('toilet', from_id='canteen', mode='accessible')['place_id'], 'disabled_toilet')
        r = search.search('male toilet', from_id='y5202', mode='standard', gender='any')
        self.assertEqual((r['method'], r['place_id']), ('keyword', 'male_toilet'))
        r = search.search('ladies', from_id='canteen', gender='male')                       # the words win over the filter
        self.assertEqual(r['place_id'], 'female_toilet')
        self.assertIn('not used', r['toilet']['note'])
        r = search.search('disabled toilet', from_id='y5202')                               # standard mode, words ask for accessible
        self.assertEqual(r['place_id'], 'disabled_toilet')

    def test_standard_prefers_ordinary_toilets_every_case(self):
        """Entry 90: Standard -> ordinary toilets (disabled ones stay free), Step-free -> disabled only; every start x
        mode x gender filter, plain "toilet" request; words "disabled" / "accessible" / "wheelchair" force disabled."""
        starts = ['canteen', 'y5202', 'y5401', 'exit_10', 'lt1a', 'y4502', 'lt2b', 'entrance_exit']
        ordinary = {'any': {'male_toilet', 'female_toilet'}, 'male': {'male_toilet'}, 'female': {'female_toilet'}}
        disabled = {'any': {'disabled_toilet', 'disabled_toilet_4F'}, 'male': {'disabled_toilet', 'disabled_toilet_4F'},
                    'female': {'disabled_toilet_4F'}}
        for st in starts:
            for gender in ('any', 'male', 'female'):
                r = search.search('toilet', from_id=st, mode='standard', gender=gender)
                self.assertIn(r['place_id'], ordinary[gender], (st, gender))
                self.assertEqual(r['toilet']['policy'], 'ordinary')
                self.assertIn('disabled toilets stay free', r['toilet']['policy_note'])
                r = search.search('toilet', from_id=st, mode='accessible', gender=gender)
                self.assertIn(r['place_id'], disabled[gender], (st, gender))
                self.assertEqual(r['toilet']['policy'], 'disabled_only')
                for words in ('disabled toilet', 'accessible toilet', 'wheelchair toilet'):
                    r = search.search(words, from_id=st, mode='standard', gender=gender)
                    self.assertIn(r['place_id'], disabled[gender], (st, gender, words))
                n = search.nearest('toilet', st, 'standard', gender)
                self.assertIn(n['place_id'], ordinary[gender], (st, gender))
        # the screenshot case: Standard + Male from the canteen -> the ordinary male toilet
        r = search.search('toilet', from_id='canteen', mode='standard', gender='male')
        self.assertEqual(r['place_id'], 'male_toilet')
        self.assertIn('Male disabled toilet (5F)', {x['name'] for x in r['toilet']['excluded']})
        # 4F start, Standard: up to the 5F male toilet, not the 4F mixed disabled toilet
        self.assertEqual(search.search('toilet', from_id='lt1a', gender='male')['place_id'], 'male_toilet')
        # a 4F-only request in Standard: no ordinary toilet on 4F -> the mixed disabled toilet, and the card says why
        r = search.search('toilet 4F', from_id='canteen', mode='standard', gender='male')
        self.assertEqual((r['place_id'], r['toilet']['policy']), ('disabled_toilet_4F', 'disabled_fallback'))
        self.assertIn('No ordinary male toilet on 4F', r['toilet']['policy_note'])

    def test_toilet_no_option_message(self):
        r = search.search('disabled toilet 5F', from_id='canteen', mode='accessible', gender='female')
        self.assertIsNone(r['place_id'])
        self.assertEqual(r['route'], [])
        self.assertIn('No disabled female toilet on 5F', r['answer'])
        self.assertEqual(r['toilet']['options'], [])

    def test_gemini_toilet_post_processed(self):
        self.key = FAKE_KEY
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': FAKE_KEY}):
            self.answers('{"place_id": "male_toilet", "answer": "The male toilet is on 5F near Exit 5."}')
            r = search.search('I need the toilet', from_id='y5202', gender='female')
            self.assertEqual((r['method'], r['matched_place'], r['place_id']), ('gemini', 'male_toilet', 'female_toilet'))
            self.assertNotIn('male toilet is', r['answer'])
            search._cache.clear()
            self.answers('{"place_id": "female_toilet", "answer": "The female toilet is next to Exit 10."}')
            r = search.search('where can I pee', from_id='y5202', gender='female')           # same toilet: Gemini's sentence kept
            self.assertEqual((r['place_id'], r['answer']), ('female_toilet', 'The female toilet is next to Exit 10.'))

    def test_accessible_route_and_bad_mode(self):
        r = search.search('lt1a', from_id='canteen', mode='accessible')
        self.assertEqual([c['kind'] for c in r['connectors']], ['lift'])
        self.assertTrue(any(t.startswith('Take the lift down to 4F') for t in r['instructions']))
        self.assertEqual(len(r['legs']), len(r['route']) - 1)
        with self.assertRaises(KeyError):
            search.search('lt1a', mode='wheelchair')
        with self.assertRaises(KeyError):
            search.search('toilet', gender='other')


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

    def get_json(self, path, expect=200):
        try:
            code, body = self.get(path)
        except urllib.error.HTTPError as e:
            with e:
                code, body = e.code, e.read().decode()
        self.assertEqual(code, expect, path)
        return json.loads(body)

    def test_api_route(self):
        server.STATE['session'] = server.ws.Session(5)
        r = self.get_json('/api/route?from=y5302&to=sr9')                                  # one floor, measured edge
        self.assertEqual((r['path'], r['distance_m'], r['mode']), (['y5302', 'sr9'], 13.9, 'standard'))
        self.assertEqual(r['legs'][0]['metres'], 13.9)
        st = self.get_json('/api/route?from=canteen&to=lt1a&mode=standard')
        ac = self.get_json('/api/route?from=canteen&to=lt1a&mode=accessible')
        self.assertEqual([c['kind'] for c in st['connectors']], ['escalator'])
        self.assertEqual([c['kind'] for c in ac['connectors']], ['lift'])
        self.assertAlmostEqual(ac['seconds'], round(sum(l['seconds'] for l in ac['legs']), 1), places=1)
        self.assertEqual(ac['from']['source'], 'chosen')
        r = self.get_json('/api/route?to=lt1a')                                            # no start: default gate
        self.assertEqual(r['from']['id'], 'entrance_exit')
        self.assertIn('error', self.get_json('/api/route?from=canteen&to=nowhere', 400))
        self.assertIn('mode', self.get_json('/api/route?from=canteen&to=lt1a&mode=fly', 400)['error'])

    def test_api_nearest(self):
        server.STATE['session'] = server.ws.Session(5)
        r = self.get_json('/api/nearest?type=toilet&from=y5202&gender=female')
        self.assertEqual((r['place_id'], r['floor']), ('female_toilet', 5))
        self.assertEqual(r['route'][-1]['id'], 'female_toilet')
        r = self.get_json('/api/nearest?type=toilet&from=y5401&mode=accessible&gender=female')
        self.assertEqual(r['place_id'], 'disabled_toilet_4F')
        self.assertEqual([c['kind'] for c in r['connectors']], ['lift'])
        self.assertEqual({x['id'] for x in r['excluded']}, {'male_toilet', 'female_toilet', 'disabled_toilet'})
        r = self.get_json('/api/nearest?type=toilet&from=lt1a&mode=accessible&gender=male')
        self.assertEqual(r['place_id'], 'disabled_toilet_4F')
        r = self.get_json('/api/nearest?type=toilet&from=lt1a&mode=standard&gender=male')            # entry 90 policy
        self.assertEqual((r['place_id'], r['policy']), ('male_toilet', 'ordinary'))
        self.assertIn('disabled_toilet_4F', {x['id'] for x in r['excluded']})
        server.STATE['session'].history.append({'kind': 'stop', 'floor': 5, 'lit': 'y5202'})   # from = the lit place
        r = self.get_json('/api/nearest?type=toilet')
        self.assertEqual((r['from']['source'], r['place_id']), ('tracked', 'female_toilet'))
        self.assertIn('error', self.get_json('/api/nearest?type=exit', 400))
        self.assertIn('gender', self.get_json('/api/nearest?type=toilet&gender=x', 400)['error'])
        self.answers('{"place_id": "male_toilet", "answer": "The male toilet is on 5F."}')      # Gemini (fake) picks a male one
        r = self.get_json('/api/search?' + urllib.parse.urlencode({'q': 'toilet', 'from': 'canteen', 'mode': 'accessible', 'gender': 'female'}))
        self.assertEqual((r['method'], r['matched_place'], r['place_id']), ('gemini', 'male_toilet', 'disabled_toilet_4F'))

    def test_current_location_waiting_and_fix(self):
        """Entry 93: from=here (Current location) with no fix -> waiting, no route; with a live fix -> from the fix,
        and while walking the last lit place stays the fix."""
        server.STATE['session'] = server.ws.Session(5)
        server.LIVE.update(tracker=None, fix=None)
        for path in ('/api/route?from=here&to=lt1a', '/api/nearest?type=toilet&from=here',
                     '/api/search?' + urllib.parse.urlencode({'q': 'y5401', 'from': 'here'})):
            self.answers(http_error(429, 'quota'))
            search._state.update(paused_until=0.0, disabled='', last_error='')
            r = self.get_json(path)
            self.assertTrue(r['waiting'], path)
            self.assertEqual((r['route'], r['from']['source'], r['from']['id']), ([], 'waiting', None), path)
        self.assertEqual(self.get_json('/api/route?from=here&to=lt1a')['to']['id'], 'lt1a')
        self.assertIsNone(server.fix_info(server.tracked_place()))          # /api/state 'fix' (needs trained models here)

        class T:
            device, model_note, lock = 'iPhone19,2', 'fake', threading.Lock()
            state = {'mode': 'stop', 'lit': 'canteen', 'floor': 5}
        server.LIVE.update(tracker=T(), fix=None, status={})
        try:
            r = self.get_json('/api/route?from=here&to=lt1a')
            self.assertEqual((r['from']['id'], r['from']['source'], r['route'][0]['id']), ('canteen', 'tracked', 'canteen'))
            self.assertEqual(self.get_json('/api/live')['fix']['id'], 'canteen')
            T.state = {'mode': 'walking', 'lit': None, 'floor': 5}                    # walking: keep the last fix
            self.assertEqual(self.get_json('/api/route?from=here&to=lt1a')['from']['id'], 'canteen')
            self.assertEqual(self.get_json('/api/route?from=y5302&to=lt1a')['from']['id'], 'y5302')   # a chosen From wins
            self.assertIn('error', self.get_json('/api/route?from=nowhere&to=lt1a', 400))
        finally:
            server.LIVE.update(tracker=None, fix=None, status={})

    def test_page_wording(self):
        """Entry 93 (user, 27 Nov): Google-Maps-like page; Disabled not Step-free; WC Male | Female, no Any WC; no Nearest
        toilet button or badge; no tap / legend hint lines; live data in a closed dropdown; From defaults to Current location."""
        page = self.get('/')[1]
        for gone in ('Step-free', 'Any WC', 'nearestwc', 'Nearest toilet</button>', 'Tap a place to set', 'id="tapto"',
                     'id="legend"', 'id="mapnote"', 'Answered by Gemini', "'answer'"):
            self.assertNotIn(gone, page, gone)
        self.assertIn('>Disabled</button>', page)
        self.assertIn('WC: <span class="seg"', page)
        self.assertIn('<details id="live" hidden><summary>Live sensor data</summary>', page)
        self.assertIn('<select id="from"><option value="here">Current location</option>', page)
        self.assertIn('<option value="nearest:toilet">Nearest toilet</option>', page)


class TestFromTo(Base):
    """Entry 93: the query may name the start (From) as well as the destination (To); offline and with Gemini."""
    def offline(self):
        search._state.update(disabled='offline test')

    def test_from_and_to_offline(self):
        self.offline()
        r = search.search('how do I get from the canteen to lt1a', from_id='here')
        self.assertEqual((r['from_query']['id'], r['from']['source'], r['place_id']), ('canteen', 'chosen', 'lt1a'))
        self.assertEqual((r['route'][0]['id'], r['route'][-1]['id']), ('canteen', 'lt1a'))
        r = search.search('aku di kantin, toilet cewek dimana', from_id='here', gender='male')
        self.assertEqual((r['from']['id'], r['place_id']), ('canteen', 'female_toilet'))     # words win over the filter
        r = search.search('im in y5202')                                                     # only a start
        self.assertEqual((r['from_query']['id'], r['place_id'], r['route']), ('y5202', None, []))
        self.assertIn('Start set to', r['answer'])
        for q in ("I'm on 4F, where is the toilet", "I'm in a hurry, where is the toilet", 'escalator going up from the lower floor',
                  'nearest toilet from here'):
            r = search.search(q, from_id='canteen')
            self.assertIsNone(r['from_query'], q)                                             # not a place: From stays
            self.assertEqual(r['from']['id'], 'canteen', q)
        self.assertEqual(search.search("I'm on 4F, where is the toilet", from_id='canteen')['place_id'], 'disabled_toilet_4F')

    def test_to_only_keeps_from(self):
        self.offline()
        r = search.search('where is y5401', from_id='here', tracked=(5, 'canteen'))
        self.assertEqual((r['from_query'], r['from']['source'], r['from']['id'], r['place_id']), (None, 'tracked', 'canteen', 'y5401'))
        r = search.search('where is y5401', from_id='here')
        self.assertEqual((r['waiting'], r['to']['id'], r['route']), (True, 'y5401', []))
        r = search.search('where is y5401', from_id='lt1a')
        self.assertEqual((r['from']['id'], r['route'][-1]['id']), ('lt1a', 'y5401'))
        r = search.search('where is y5401')                                                  # API without From: old default
        self.assertEqual(r['from']['source'], 'default')

    def test_nearest_exit(self):
        self.offline()
        r = search.search('im in y5202, find me the nearest exit', from_id='here')
        self.assertEqual((r['from']['id'], r['place_id'], r['distance_m']), ('y5202', 'exit_10', 15.1))
        self.assertEqual(r['route'][-1]['id'], 'exit_10')
        r = search.search('im in y5202, where is the nearest emergency exit')     # entry 94: all exits are emergency exits
        self.assertEqual((r['place_id'], r['distance_m']), ('exit_10', 15.1))
        self.assertTrue(r['exit']['emergency'])
        self.assertEqual(search.search('nearest emergency exit', from_id='lt1a')['place_id'], 'exit_10_4F')
        self.assertEqual(search.search('fire exit', from_id='canteen')['place_id'], search.search('nearest exit', from_id='canteen')['place_id'])
        self.assertEqual(search.search('nearest exit', from_id='lt1a')['place_id'], 'exit_10_4F')
        self.assertEqual(search.search('exit 10 on the 5th floor', from_id='lt1a')['place_id'], 'exit_10')   # named: kept
        self.assertEqual(search.search('the exit gate', from_id='canteen')['place_id'], 'entrance_exit')
        r = search.search('nearest exit', from_id='here')
        self.assertEqual((r['waiting'], r['to']['nearest'], r['route']), (True, 'exit', []))
        # every start x mode: the answer is the cheapest exit by route
        for st in search.GRAPH_TO_MAP:
            for mode in search.MODES:
                best = min(search.astar.EXITS, key=lambda e: (search.astar.plan(st, e, mode).seconds, search.astar.plan(st, e, mode).metres, e))
                self.assertEqual(search.search('nearest exit', from_id=st, mode=mode)['place_id'], best, (st, mode))

    def test_nearest_toilet_with_start_and_gender(self):
        self.offline()
        self.assertEqual(search.search('nearest toilet from y5401', gender='female')['place_id'], 'female_toilet')
        r = search.search('nearest toilet from y5401', gender='male')
        self.assertEqual((r['from']['id'], r['place_id']), ('y5401', 'male_toilet'))
        r = search.search("I'm at LT1a, find a toilet", mode='accessible')
        self.assertEqual((r['from']['id'], r['place_id']), ('lt1a', 'disabled_toilet_4F'))
        r = search.search('toilet', from_id='here')
        self.assertEqual((r['waiting'], r['to']['nearest']), (True, 'toilet'))

    def test_gemini_v2_from_and_to(self):
        self.answers('{"from_id": "y5202", "place_id": "exit_5"}')
        r = search.search('im in y5202, find me the nearest exit', from_id='here')
        self.assertEqual((r['method'], r['from_query']['id'], r['matched_place'], r['place_id']), ('gemini', 'y5202', 'exit_5', 'exit_10'))
        r = search.search('IM IN Y5202,  find me the nearest exit', from_id='here')         # cached (v2 key): no new call
        self.assertEqual(self.fake.calls, 1)
        self.assertIn(('v2', 'im in y5202, find me the nearest exit'), search._cache)
        self.answers('{"from_id": "NONE", "place_id": "lt1a"}')                              # to-only: From stays
        r = search.search('where is lecture theatre 1a', from_id='canteen')
        self.assertEqual((r['from_query'], r['from']['id'], r['place_id']), (None, 'canteen', 'lt1a'))
        self.answers('{"place_id": "sr9", "answer": "x"}')                                   # v1-style reply still usable
        self.assertEqual(search.search('where can I study', from_id='canteen')['place_id'], 'sr9')
        self.answers('{"from_id": "chem_lab", "place_id": "sr9"}')                           # bad start id: fall back offline
        r = search.search('from the chem lab to y5401', from_id='canteen')
        self.assertEqual((r['method'], r['place_id']), ('keyword', 'y5401'))
        self.answers('{"from_id": "canteen", "place_id": "lt1a"}')
        r = search.search('from the canteen to lt1a', from_id='y5302', use_query_from=False)   # page rerun after a From change
        self.assertEqual((r['from_query'], r['from']['id'], r['place_id']), (None, 'y5302', 'lt1a'))
        search._state.update(disabled='offline test')
        r = search.search('from the canteen to lt1a', from_id='y5302', use_query_from=False)
        self.assertEqual((r['from']['id'], r['place_id']), ('y5302', 'lt1a'))


if __name__ == '__main__':
    unittest.main()
