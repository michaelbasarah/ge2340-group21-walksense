"""End-to-end check: start the server, upload real 24-Nov phyphox ZIPs and some bad ones.
Run: python -m unittest test_walksense.py   (about 30 s, trains the models once)"""
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import numpy as np

import route
import server
import walksense as ws


def raw_zip(session, phone, typ, node=None, to=None):
    for r in ws.manifest(session):
        where = r['node'] if typ == 'stop' else r['from_node']      # walks have from_node/to_node, no node
        if r['phone'] == phone and r['type'] == typ and (node is None or where == node) and (to is None or r['to_node'] == to):
            return (ws.session_dir(session) / 'raw' / r['source_zip']).read_bytes(), r
    raise LookupError((session, phone, typ, node, to))


class UploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.STATE['models'] = ws.build_models()
        server.LABELS.update(ws.place_labels())
        server.UPLOADS = server.HERE / 'out' / 'test_uploads'     # keep test uploads out of uploads/
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, path, data=b''):
        req = urllib.request.Request(self.url + path, data=data, method='POST')
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_read_zip(self):
        data, row = raw_zip('sesi2', 'iphone', 'stop', 'canteen')
        rec = ws.read_zip(data)
        self.assertEqual(rec['device'], row['device'])
        self.assertTrue(len(rec['mag']) > 1000 and len(rec['baro']) > 10 and rec['start_epoch'] > 1.7e9)

    @unittest.skipUnless('25nov' in ws.SESSIONS, 'WALKSENSE_SESSIONS limits the sessions')
    def test_session_list_and_25nov_upload(self):
        self.assertEqual(ws.SESSIONS, ('sesi1', 'sesi2', '25nov', '25night', '25night_tian', '26tian', '27nov'))   # night run: entry 72; 26tian: entry 74; 27nov: entry 95
        for x in ws.SESSION_LIST:
            self.assertTrue((x['path'] / 'clean' / 'manifest.csv').exists(), x)
        self.assertIn('iPhone19,2', server.STATE['models'])
        self.post('/api/reset?floor=5')
        data, row = raw_zip('25nov', 'iphone', 'stop', 'canteen')
        code, body = self.post('/api/upload?kind=stop&truth=canteen', data)
        self.assertEqual(code, 200, body)
        self.assertEqual((body['result']['device'], body['result']['floor']), ('iPhone19,2', 5))
        self.assertIn('trained on this phone model', body['result']['model_note'])

    def test_route_stop_walk_stop_and_floor_change(self):
        self.post('/api/reset?floor=5')
        data, _ = raw_zip('sesi2', 'iphone', 'stop', 'canteen')
        code, body = self.post('/api/upload?kind=auto&truth=canteen', data)
        self.assertEqual(code, 200, body)
        r = body['result']
        self.assertEqual((r['kind'], r['floor'], r['device']), ('stop', 5, 'iPhone17,4'))
        self.assertEqual(len(r['top3']), 3)
        self.assertEqual(r['lit'], r['top3'][0][0] if r['top3'][0][1] >= ws.LIGHT_P else None)
        self.assertIn('trained on this phone model', r['model_note'])
        self.assertEqual(body['tally']['stops'], 1)
        data, _ = raw_zip('sesi2', 'iphone', 'walk', 'canteen', None)
        code, body = self.post('/api/upload?kind=auto', data)
        self.assertEqual((code, body['result']['kind']), (200, 'walk'))
        self.assertGreater(body['result']['steps'], 5)
        # 5F stairs landing, then the 4F landing: the floor must switch to 4
        for node, floor in (('lift_stairs5', 5), ('lift_stairs5', 4)):
            for r in ws.manifest('sesi2'):
                if r['phone'] == 'iphone' and r['type'] == 'stop' and r['node'] == node and int(r['floor']) == floor:
                    code, body = self.post('/api/upload?kind=stop', (ws.session_dir('sesi2') / 'raw' / r['source_zip']).read_bytes())
                    self.assertEqual(code, 200, body)
        self.assertEqual(body['result']['floor'], 4, body['result']['floor_note'])

    def test_map_has_every_place_and_is_served(self):
        with urllib.request.urlopen(self.url + '/map/places.json') as r:
            maps = json.loads(r.read())
        for floor, names in server.places().items():
            self.assertEqual(set(names), set(maps[str(floor)]['places']), floor)   # every guess can light a circle
            self.assertTrue(set(names) <= set(server.LABELS), floor)                 # and has a readable name
        with urllib.request.urlopen(self.url + '/map/floor5.png') as r:
            self.assertEqual(r.read(8), b'\x89PNG\r\n\x1a\n')
        for bad in ('/map/../server.py', '/map/make_map.py', '/walksense.py'):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(self.url + bad)

    def test_floorplan_has_every_place_and_is_served(self):
        with urllib.request.urlopen(self.url + '/map/floorplan.json') as r:
            plan = json.loads(r.read())
        with urllib.request.urlopen(self.url + '/map/floorplan.js') as r:
            self.assertIn(b'window.FloorPlan', r.read())
        for floor, names in server.places().items():
            fl = plan['floors'][str(floor)]
            self.assertEqual(set(names), set(fl['places']), floor)                    # every guess has a point in metres
            edges = {frozenset((e['from'], e['to'])) for e in fl['edges']}
            for a, nbrs in route.build().get(floor, {}).items():                      # every corridor the dot can walk
                for b, _, _ in nbrs:
                    self.assertIn(frozenset((a, b)), edges, (floor, a, b))
        for bad in ('/map/make_floorplan.py', '/map/sketch_trace.json'):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(self.url + bad)

    def test_bad_uploads_refused(self):
        self.assertEqual(self.post('/api/upload', b'not a zip')[0], 400)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('Accelerometer.csv', '"t","x","y","z"\n0,0,0,9.8\n')
        self.assertEqual(self.post('/api/upload', buf.getvalue())[0], 400)          # no magnetometer
        self.assertEqual(self.post('/api/upload?truth=%3Cscript%3E', b'x')[0], 400)  # place name injection
        self.assertEqual(self.post('/api/upload?kind=drop', b'x')[0], 400)
        self.assertEqual(self.post('/api/floor?floor=9')[0], 400)
        self.assertEqual(self.post('/api/upload', b'')[0], 413)


class FloorRuleTest(unittest.TestCase):
    """Floor rule (d) in walksense.Session (PROCESS-LOG entry 90), with made-up pressures and votes; fast, no models.
    Recordings are 60 s, 3 min apart; 1 floor = about 0.6 hPa (pressure RISES going down)."""

    def run_rule(self, rule, recs, floor=5):
        """recs = [(t_min, p or None, vote (floor, p) or None, is_stop)] -> floor after each recording."""
        s, out = ws.Session(floor, rule=rule), []
        for t, p, vote, stop in recs:
            s.update_floor(p, p, t * 60.0, 60.0, is_stop=stop, vote=vote)
            out.append(s.floor)
        return out

    def test_default_rule_and_params(self):
        self.assertIn(ws.FLOOR_RULE, ws.FLOOR_RULES)
        self.assertEqual(ws.Session().rule, ws.FLOOR_RULE)
        self.assertEqual((ws.VOTE_K, ws.VOTE_P, ws.VOTE_H, ws.VOTE_M, ws.LONG_GAP_S), (15, 0.7, 2, 3, 900))   # floor/out/params.json

    def test_missing_pressure_uses_the_vote(self):
        recs = [(0, 1010.0, (5, 0.9), True), (3, 1010.0, (5, 0.9), True),
                (6, None, (4, 0.9), True), (9, None, None, False), (12, None, (4, 0.9), True), (15, None, (4, 0.9), True)]
        self.assertEqual(self.run_rule('d', recs), [5, 5, 5, 5, 4, 4])     # two confident votes in a row (H = 2)
        self.assertEqual(self.run_rule('R0', recs), [5] * 6)              # R0: no pressure = floor kept
        unsure = [r if r[2] is None else (r[0], r[1], (4, 0.6), r[3]) for r in recs]
        self.assertEqual(self.run_rule('d', unsure)[-1], 5)               # p < 0.7 never counts

    def test_long_gap_then_small_step(self):
        """25-night case: 55 min without pressure, back on 4F but the step is under 0.40 hPa (weather fell)."""
        recs = [(0, 1010.00, (5, 0.9), True), (3, 1010.02, (5, 0.9), True),
                (58, 1010.38, (4, 0.9), True), (61, 1010.38, (4, 0.9), True), (64, 1010.39, (4, 0.9), True)]
        self.assertEqual(self.run_rule('R0', recs), [5, 5, 5, 5, 5])
        self.assertEqual(self.run_rule('d', recs), [5, 5, 5, 4, 4])
        # after the switch the reference restarts from the 4F readings: later 4F readings keep 4F
        s = ws.Session(5, rule='d')
        for t, p, v, st in recs:
            s.update_floor(p, p, t * 60.0, 60.0, is_stop=st, vote=v)
        self.assertEqual(s.recent[-1], 1010.39)
        self.assertEqual(s.consult_left, 0)
        # only the first VOTE_M stops after the gap ask the vote
        late = recs[:2] + [(58, 1010.38, (5, 0.9), True), (61, 1010.38, (5, 0.9), True), (64, 1010.39, (5, 0.9), True),
                           (67, 1010.39, (4, 0.9), True), (70, 1010.39, (4, 0.9), True)]
        self.assertEqual(self.run_rule('d', late)[-1], 5)

    def test_weather_drift_with_pressure_does_not_ask_the_vote(self):
        """Continuous pressure drifting +0.3 hPa/h on 5F, the magnetometer wrongly says 4F: (d) = R0 = stays 5F."""
        recs = [(t, 1010.0 + 0.3 * t / 60, (4, 0.95), True) for t in range(0, 120, 3)]
        self.assertEqual(self.run_rule('d', recs), [5] * len(recs))
        self.assertEqual(self.run_rule('R0', recs), [5] * len(recs))

    def test_real_floor_change_with_pressure(self):
        recs = [(0, 1010.0, (5, 0.9), True), (3, 1010.01, (5, 0.9), True), (6, 1010.0, None, False),
                (9, 1010.62, (5, 0.95), True), (12, 1010.63, (5, 0.95), True), (15, 1010.0, (5, 0.95), True)]
        self.assertEqual(self.run_rule('R0', recs), [5, 5, 5, 4, 4, 5])
        self.assertEqual(self.run_rule('d', recs), [5, 5, 5, 4, 4, 5])     # pressure wins; votes are not asked

    def test_no_barometer_phone(self):
        votes = [(4, 0.9), (5, 0.9), (4, 0.9), (4, 0.5), (4, 0.9), (5, 0.9), (5, 0.8)]
        recs = [(3 * i, None, v, True) for i, v in enumerate(votes)]
        # 4 (1 of 2), 5 = current floor -> count reset, 4 (1), unsure 4 (count kept), 4 (2) -> 4F, then 5 twice -> 5F
        self.assertEqual(self.run_rule('d', recs), [5, 5, 5, 5, 4, 4, 5])
        self.assertEqual(self.run_rule('R0', recs), [5] * len(recs))
        # S24: its barometer is ignored under (d), used by R0
        rec = {'device': 'SM-S9280', 'baro': np.array([[0, 1010.0], [1, 1010.0], [5, 1010.1]])}
        self.assertEqual(ws.floor_pressure(rec, 'd'), (None, None))
        self.assertEqual(ws.floor_pressure(rec, 'R0'), (1010.0, 1010.1))
        rec['device'] = 'iPhone19,2'
        self.assertEqual(ws.floor_pressure(rec, 'd'), (1010.0, 1010.1))

    def test_rule_per_phone_model(self):
        """(d) passed the pre-registered rule for the iPhone only: barometer-less phones and the S24 keep R0 by default."""
        self.assertEqual(ws.floor_rule_for('iPhone19,2', 'd'), 'd')
        self.assertEqual(ws.floor_rule_for('iPhone17,4', 'd'), 'd')
        self.assertEqual(ws.floor_rule_for('SomeNewPhone', 'd'), 'd')
        self.assertEqual(ws.floor_rule_for('iPhone19,2', 'R0'), 'R0')
        old = ws.VOTE_NO_BARO
        try:
            ws.VOTE_NO_BARO = False
            for dev in ('SM-A566B', 'SM-A556E', 'SM-S9280'):
                self.assertEqual(ws.floor_rule_for(dev, 'd'), 'R0', dev)
            ws.VOTE_NO_BARO = True
            for dev in ('SM-A566B', 'SM-A556E', 'SM-S9280'):
                self.assertEqual(ws.floor_rule_for(dev, 'd'), 'd', dev)
        finally:
            ws.VOTE_NO_BARO = old

    def test_manual_floor_resets_the_count(self):
        s = ws.Session(5, rule='d')
        s.update_floor(None, None, 0, 60, vote=(4, 0.9))
        s.set_floor(5)
        s.update_floor(None, None, 180, 60, vote=(4, 0.9))
        self.assertEqual(s.floor, 5)


class TrainExcludeTest(unittest.TestCase):
    """Chris's a56 night session is never training data (PROCESS-LOG 77 option B, entry 90); other phones unchanged."""

    def test_a56_night_left_out_of_training(self):
        self.assertIn(('25night', 'a56'), ws.TRAIN_EXCLUDE)
        if '25night' not in ws.SESSIONS:
            self.skipTest('WALKSENSE_SESSIONS limits the sessions')
        a56 = ws.training_stops(device='SM-A566B', exclude=ws.TRAIN_EXCLUDE)
        self.assertNotIn('25night', {x['session'] for x in a56})
        self.assertIn('25night', {x['session'] for x in ws.training_stops(device='SM-A566B')})   # data still on disk
        ip = ws.training_stops(device='iPhone19,2', exclude=ws.TRAIN_EXCLUDE)
        self.assertIn('25night', {x['session'] for x in ip})                                     # Dicta's iPhone kept
        fake = {(s, 'a56'): [{'device': 'SM-A566B', 'session': s}] for s in ('sesi1', '25nov', '25night')}
        folds = {(te[0]['session'], mode): names for _, mode, names, _, te in ws.eval_folds(fake)}
        self.assertEqual(folds[('sesi1', 'same_model')], ['25nov'])
        self.assertEqual(folds[('25nov', 'same_model')], ['sesi1'])
        self.assertEqual(folds[('25night', 'same_model')], ['sesi1', '25nov'])    # still tested


if __name__ == '__main__':
    unittest.main()
