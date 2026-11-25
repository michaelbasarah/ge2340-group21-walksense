#!/usr/bin/env python3
"""WalkSense upload server: open it on the phone, send a phyphox ZIP, get floor + steps + place.

  python server.py            # then open the printed http://<laptop-ip>:8000 on the phone
Phone and laptop must be on the same network (the phone's hotspot works best).
Anyone on that network can upload: use it on your own hotspot only.
"""
from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import walksense as ws

HERE = Path(__file__).resolve().parent
UPLOADS = HERE / 'uploads'
MAX_UPLOAD = 40_000_000          # a 60 s iPhone stop is ~1 MB, a 4-phone S24 stop ~4 MB
LOCK = threading.Lock()
STATE = {'session': ws.Session(5), 'models': None}
NAME_OK = re.compile(r'^[a-z0-9_]{0,40}$')


def places():
    return {f: sorted(set().union(*(m.places.get(f, []) for m in STATE['models'].values()))) for f in (5, 4)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def _state(self):
        s = STATE['session']
        return {'floor': s.floor, 'tally': dict(s.tally), 'places': places(), 'history': s.history[-20:],
                'eval': _eval_summary()}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self._send(200, (HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/state':
            with LOCK:
                return self._send(200, self._state())
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == '/api/reset':
            floor = q.get('floor', '5')
            if floor not in ('4', '5'):
                return self._send(400, {'error': 'floor must be 4 or 5'})
            with LOCK:
                STATE['session'] = ws.Session(int(floor))
                return self._send(200, self._state())
        if u.path == '/api/floor':
            if q.get('floor') not in ('4', '5'):
                return self._send(400, {'error': 'floor must be 4 or 5'})
            with LOCK:
                STATE['session'].set_floor(int(q['floor']))
                return self._send(200, self._state())
        if u.path != '/api/upload':
            return self._send(404, {'error': 'not found'})
        kind, truth = q.get('kind', 'auto'), q.get('truth', '')
        if kind not in ('auto', 'stop', 'walk') or not NAME_OK.match(truth):
            return self._send(400, {'error': 'bad kind or place name'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            n = -1
        if not 0 < n <= MAX_UPLOAD:
            return self._send(413, {'error': f'upload must be a ZIP under {MAX_UPLOAD // 1_000_000} MB'})
        data = self.rfile.read(n)
        try:
            rec = ws.read_zip(data)
        except ValueError as e:
            return self._send(400, {'error': str(e)})
        except Exception:                                   # malformed CSV inside a valid ZIP
            return self._send(400, {'error': 'could not read the sensor files in this ZIP'})
        UPLOADS.mkdir(exist_ok=True)
        dev = re.sub(r'[^A-Za-z0-9,]', '', rec.get('device', ''))[:20] or 'unknown'
        (UPLOADS / f"{time.strftime('%Y%m%d-%H%M%S')}_{dev}.zip").write_bytes(data)   # keep every upload
        with LOCK:
            res = ws.analyse(rec, STATE['session'], STATE['models'], kind, truth)
            with open(UPLOADS / 'log.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'time': time.strftime('%Y-%m-%d %H:%M:%S'), **res}) + '\n')
            return self._send(200, {'result': res, **self._state()})

    def log_message(self, fmt, *args):
        sys.stderr.write(f'{self.address_string()} {fmt % args}\n')


def _eval_summary():
    f = ws.OUT / 'eval.json'
    if not f.exists():
        return None
    e = json.loads(f.read_text())
    return {k: {'top1': v['top1'], 'top3': v['top3'], 'devices': v['devices']} for k, v in e['place'].items() if k.endswith(' xyz')}


def lan_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith('127.'))


def main(port=8000):
    print('Training the place models on the 24-Nov stops ...')
    STATE['models'] = ws.build_models()
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print('Open one of these on the phone (same network):')
    for ip in lan_ips():
        print(f'  http://{ip}:{port}')
    print(f'  (this laptop: http://127.0.0.1:{port})   Ctrl+C to stop')
    srv.serve_forever()


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
