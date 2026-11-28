"""Live mode against a fake phyphox phone that replays real 24-Nov session-2 iPhone recordings
(stop, walk, stop, ... down to 4F) 20x faster through the /get partial-update API.
The fake follows the phyphox web interface's calls; the /config shape is our assumption.
Run: python -m unittest test_live.py   (about 40 s)"""
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import numpy as np

import live
import walksense as ws

SPEED = 20.0
BARO_LAG = 4.0   # s; the real iPhone sends pressure late (PROCESS-LOG entry 28)
NAMES = {'acc': ('a_t', 'a_x', 'a_y', 'a_z'), 'gyr': ('g_t', 'g_x', 'g_y', 'g_z'),
         'mag': ('m_t', 'm_x', 'm_y', 'm_z'), 'baro': ('p_t', 'p')}     # not the guessed names: forces /config
SETS = {'acc': 'Accelerometer', 'gyr': 'Gyroscope', 'mag': 'Magnetometer', 'baro': 'Barometer'}
ROUTE = [('stop', 5, 'canteen'), ('walk', 5, 'canteen'), ('stop', 5, 'exit5_door'), ('walk', 5, 'exit5_door'),
         ('stop', 4, 'lift_stairs5'), ('walk', 4, 'lift_stairs5'), ('stop', 4, 'disabled_toilet')]


def build_stream():
    rows = {r['folder']: r for r in ws.manifest('sesi2') if r['phone'] == 'iphone'}
    parts, truth, t0 = {s: [] for s in live.SENSORS}, [], 0.0
    for kind, floor, node in ROUTE:
        r = next(r for r in rows.values() if r['type'] == kind and int(r['floor']) == floor
                 and (r['node'] if kind == 'stop' else r['from_node']) == node)
        rec = ws.read_folder(ws.session_dir('sesi2') / 'clean' / r['folder'] / 'iphone', r['device'])
        start = min(rec[s][0, 0] for s in live.SENSORS)
        for s in live.SENSORS:
            a = rec[s].copy(); a[:, 0] += t0 - start; parts[s].append(a)
        if kind == 'stop':
            truth.append((floor, node, t0))
        t0 += max(rec[s][-1, 0] for s in live.SENSORS) - start + 0.5
    return {s: np.vstack(parts[s]) for s in live.SENSORS}, truth, t0


class FakePhone(BaseHTTPRequestHandler):
    stream, t_start, end = None, None, 1e9

    def do_GET(self):
        u = urlparse(self.path)
        now = (time.time() - FakePhone.t_start) * SPEED
        if u.path == '/config':
            body = {'export': [{'set': SETS[s], 'sources': [{'label': 'Time (s)' if i == 0 else 'x', 'buffer': b}
                                                            for i, b in enumerate(NAMES[s])]} for s in live.SENSORS]}
        elif u.path == '/get':
            out = {}
            for name, value in parse_qsl(u.query):
                s, col = next((s, ns.index(name)) for s, ns in NAMES.items() if name in ns)
                a = FakePhone.stream[s]; a = a[a[:, 0] <= now - (BARO_LAG if s == 'baro' else 0)]
                if value != 'full':
                    thr = float(value.split('|')[0])
                    a = a[a[:, 0] > thr]
                out[name] = {'size': 0, 'updateMode': 'partial', 'buffer': a[:, col].tolist()}
            body = {'buffer': out, 'status': {'session': 'test1', 'measuring': bool(now < FakePhone.end), 'timedRun': False, 'countDown': 0}}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


class LiveTest(unittest.TestCase):
    def test_replayed_walk(self):
        stream, truth, end = build_stream()
        FakePhone.stream, FakePhone.t_start, FakePhone.end = stream, time.time(), end
        srv = ThreadingHTTPServer(('127.0.0.1', 0), FakePhone)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        live.POLL_S = 0.1
        with tempfile.TemporaryDirectory() as tmp:
            tracker = live.LiveTracker(ws.build_models(), 'iPhone17,4', 5)
            status, stop = {}, threading.Event()
            th = threading.Thread(target=live.run, args=(live.Phyphox(f'http://127.0.0.1:{srv.server_address[1]}'), tracker, status, stop, Path(tmp)))
            FakePhone.t_start = time.time()
            th.start()
            modes, steps, dots, first_guess = set(), 0, [], []
            while (time.time() - FakePhone.t_start) * SPEED < end + 4:
                st = status.get('state') or {}
                if st.get('dot'): dots.append(st['dot'])
                if st.get('mode') == 'stop' and len(first_guess) < len(st.get('stops', [])):
                    first_guess.append(st['still_s'])                                 # still seconds when the stop first showed a guess
                modes.add(st.get('mode')); steps = max(steps, st.get('steps', 0) if st.get('mode') == 'walking' else 0)
                time.sleep(0.1)
            stop.set(); th.join(); srv.shutdown()
            self.assertTrue(status.get('connected'), status.get('error'))
            self.assertEqual(status['buffers']['mag'], list(NAMES['mag']))          # found through /config
            stops = status['state']['stops']
            self.assertEqual(len(stops), len(truth), stops)                          # one per recorded stop
            for got, (floor, node, _) in zip(stops, truth):
                self.assertEqual(got['floor'], floor, (got, node))                 # 5F, 5F, then 4F after the stairs
                self.assertEqual(got['top3'][0][0], node)                           # trained on this data, so must be right
            self.assertTrue({'walking', 'stop'} <= modes, modes)
            self.assertTrue(first_guess and max(first_guess) <= 2.0, first_guess)    # a guess within 2 s of standing (entry 96)
            self.assertGreater(steps, 5)
            self.assertTrue(dots and dots[0]['from'] == 'canteen', dots[:1])        # walking dot starts at the named stop
            self.assertEqual(status['last_recording']['file'].split('/')[0], 'recordings')
            zips = list(Path(tmp).glob('*.zip'))                                     # play..pause saved once
            self.assertEqual(len(zips), 1)
            saved = ws.read_zip(zips[0].read_bytes())                                # and it uploads like a phyphox export
            self.assertEqual(saved['device'], 'iPhone17,4')
            self.assertTrue(all(len(saved[s]) > 1000 for s in ('acc', 'mag')))


if __name__ == '__main__':
    unittest.main()
