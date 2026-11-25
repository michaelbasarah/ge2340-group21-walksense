#!/usr/bin/env python3
"""Live mode: read phyphox's remote access while you walk, and guess the place at every stop.

  python live.py probe http://<phone-ip>:8080     # first: check the laptop can read the phone
  python server.py --live http://<phone-ip>:8080  # then: the map page updates live

phyphox REST calls used (from the official web interface's code, phyphox-webinterface/index.html):
  /get?<buf>=<last value of ref>%7C<ref>&<ref>=<last value>   -> only newer samples ("full" = all)
  response {"buffer": {name: {"buffer": [...], ...}}, "status": {"measuring", "session", ...}}
Buffer names are read from /config if the phone offers it (not confirmed in the docs we could
reach), otherwise common names are tried; `probe` shows what was found.

Rules (all checked on the 24-Nov iPhone data, PROCESS-LOG entry 26):
  standing = |acc| std over the last 3 s < 0.4 m/s^2 (stops 95% <= 0.29, walks >= 0.8)
  a stop is named after 10 s standing (top-1 16/26 and 17/27 with 10 s, vs 17/26 and 17/27 with 60 s)
  the floor is updated once per stop from its median pressure (27/27 and 26/26)
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

import walksense as ws
from pdr import count_steps

STILL_STD = 0.4        # m/s^2
MOTION_S = 3.0         # window for the still/moving test
NAME_AFTER_S = 10.0    # seconds standing before the first place guess
MAX_STOP_S = 60.0      # use at most the last 60 s of a stop (what the model was trained on)
POLL_S = 0.5
GAP_S = 5.0            # a break in the data (phyphox paused) ends the current stop or walk
KEEP_S = 180.0         # samples kept in memory (everything is also written to disk)
SENSORS = ('acc', 'gyr', 'mag', 'baro')
CSV = {'acc': ('Accelerometer.csv', '"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"'),
       'gyr': ('Gyroscope.csv', '"Time (s)","X (rad/s)","Y (rad/s)","Z (rad/s)"'),
       'mag': ('Magnetometer.csv', '"Time (s)","X (µT)","Y (µT)","Z (µT)"'),
       'baro': ('Barometer.csv', '"Time (s)","X (hPa)"')}
GUESSES = {'acc': ('acc_time', 'accX', 'accY', 'accZ'), 'gyr': ('gyr_time', 'gyrX', 'gyrY', 'gyrZ'),
           'mag': ('mag_time', 'magX', 'magY', 'magZ'), 'baro': ('baro_time', 'baro')}
KEYWORDS = {'acc': ('accel',), 'gyr': ('gyro',), 'mag': ('magnet',), 'baro': ('baro', 'pressure')}


# ============================================================================ phone
class Phyphox:
    def __init__(self, base, timeout=3.0):
        u = urllib.parse.urlparse(base if '://' in base else 'http://' + base)
        if u.scheme != 'http' or not u.hostname:
            raise ValueError('phyphox address must look like http://192.168.1.23:8080')
        self.base, self.timeout = f'http://{u.netloc}', timeout
        self.bufs, self.last = {}, {}

    def _json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))

    def discover(self):
        """sensor -> (time buffer, component buffers...). /config export sets, then inputs, then common names."""
        found = {}
        try:
            cfg = self._json('/config')
        except Exception:
            cfg = {}
        for s in cfg.get('export', []) if isinstance(cfg, dict) else []:      # sets named like the ZIP's CSVs
            name = str(s.get('set', '')).lower()
            bufs = [str(x.get('buffer', '')) for x in s.get('sources', []) if isinstance(x, dict)]
            for sensor, keys in KEYWORDS.items():
                if sensor not in found and any(k in name for k in keys) and len(bufs) >= (2 if sensor == 'baro' else 4):
                    found[sensor] = tuple(bufs[:2] if sensor == 'baro' else bufs[:4])
        for inp in cfg.get('inputs', []) if isinstance(cfg, dict) else []:
            src, outs = str(inp.get('source', '')).lower(), {}
            for o in inp.get('outputs', []):
                if isinstance(o, dict):
                    outs.update({str(k): str(v) for k, v in o.items()})
            for sensor, keys in KEYWORDS.items():
                if sensor not in found and any(k in src for k in keys) and 't' in outs:
                    comps = [outs[c] for c in ('x', 'y', 'z') if c in outs] or [v for k, v in outs.items() if k != 't'][:1]
                    found[sensor] = (outs['t'], *comps)
        for sensor, names in GUESSES.items():                                  # last resort: try common names
            if sensor not in found:
                try:
                    r = self._get({n: 'full' for n in names})
                    if all(n in r['buffer'] for n in names):
                        found[sensor] = names
                except Exception:
                    pass
        self.bufs = found
        return found

    def _get(self, params):
        q = '&'.join(f'{urllib.parse.quote(k)}={v}' for k, v in params.items())
        return self._json('/get?' + q)

    def fetch(self):
        """New samples since the last call: {sensor: array (t, values...)}, status dict."""
        params = {}
        for sensor, (tb, *comps) in self.bufs.items():
            last = self.last.get(sensor)
            params[tb] = 'full' if last is None else repr(last)
            for c in comps:
                params[c] = 'full' if last is None else f'{last!r}%7C{urllib.parse.quote(tb)}'
        r = self._get(params)
        out = {}
        for sensor, (tb, *comps) in self.bufs.items():
            cols = [r['buffer'].get(n, {}).get('buffer', []) for n in (tb, *comps)]
            n = min(len(c) for c in cols)
            if n == 0:
                continue
            a = np.array([[np.nan if v is None else float(v) for v in c[-n:]] for c in cols]).T
            a = a[np.isfinite(a).all(1)]
            last = self.last.get(sensor)
            if last is not None:
                a = a[a[:, 0] > last]
            if len(a):
                out[sensor] = a
                self.last[sensor] = float(a[-1, 0])
        return out, r.get('status', {})

    def restart(self):
        self.last = {}


# ============================================================================ tracker
class LiveTracker:
    def __init__(self, models, device='iPhone17,4', floor=5, save_dir: Path | None = None):
        self.models, self.device = models, device
        self.model, self.model_note = ws.pick_model(models, device)
        self.session = ws.Session(floor)
        self.data = {s: np.empty((0, 2 if s == 'baro' else 4)) for s in SENSORS}
        self.save_dir = save_dir
        self.still_since = None       # phone time the current stand started
        self.walk_since = None
        self.stop = None              # current stop: {'start', 'floor_done', 'top3', 'lit'}
        self.state = {'mode': 'waiting', 'steps': 0, 'still_s': 0.0, 'top3': [], 'lit': None,
                      'floor': floor, 'floor_note': '', 'stops': [], 'now': None}
        self.lock = threading.Lock()

    def set_floor(self, floor):
        with self.lock:
            self.session.set_floor(floor)
            self.state['floor'] = floor

    def add(self, chunk):
        with self.lock:
            if 'acc' in chunk and len(self.data['acc']) and chunk['acc'][0, 0] - self.data['acc'][-1, 0] > GAP_S:
                self.still_since = self.walk_since = self.stop = None
            for s, a in chunk.items():
                self.data[s] = np.vstack([self.data[s], a])
                self._save(s, a)
            now = max((self.data[s][-1, 0] for s in SENSORS if len(self.data[s])), default=None)
            if now is not None:
                for s in SENSORS:
                    self.data[s] = self.data[s][self.data[s][:, 0] >= now - KEEP_S]

    def _save(self, sensor, a):
        if self.save_dir is None:
            return
        self.save_dir.mkdir(parents=True, exist_ok=True)
        f = self.save_dir / CSV[sensor][0]
        new = not f.exists()
        with open(f, 'a', encoding='utf-8') as fh:
            if new:
                fh.write(CSV[sensor][1] + '\n')
            np.savetxt(fh, a, delimiter=',', fmt='%.9E')

    def _window(self, t0, t1):
        return {s: self.data[s][(self.data[s][:, 0] >= t0) & (self.data[s][:, 0] <= t1)] for s in SENSORS}

    def update(self):
        with self.lock:
            acc = self.data['acc']
            if len(acc) < 50:
                return dict(self.state)
            now = float(acc[-1, 0])
            recent = acc[acc[:, 0] >= now - MOTION_S]
            moving = np.linalg.norm(recent[:, 1:4], axis=1).std() >= STILL_STD
            st = self.state
            st['now'] = round(now, 1)
            if moving:
                if self.stop is not None or self.walk_since is None:
                    self.walk_since, self.stop = now, None
                self.still_since = None
                w = acc[acc[:, 0] >= self.walk_since]
                steps = int(count_steps(w[:, 0], np.linalg.norm(w[:, 1:4], axis=1))[0]) if len(w) > 200 else 0   # < 2 s: too short to count
                st.update(mode='walking', still_s=0.0, steps=steps)
                return dict(st)
            if self.still_since is None:
                self.still_since = now
            st['still_s'] = round(now - self.still_since, 1)
            if now - self.still_since < NAME_AFTER_S:
                st['mode'] = 'standing'
                return dict(st)
            win = self._window(max(self.still_since, now - MAX_STOP_S), now)
            if self.stop is None:                               # first look at this stop: floor, once
                p = win['baro'][:, 1] if len(win['baro']) else None
                note = self.session.track_floor(float(np.median(p)), float(np.median(p)), now, 0.0) if p is not None and len(p) \
                    else 'no barometer data: floor kept'
                self.stop = {'start': self.still_since}
                st.update(floor=self.session.floor, floor_note=note)
            top3 = self.model.top3(win, self.session.floor, trim=0.0) if len(win['mag']) >= 20 and len(win['acc']) >= 20 else []
            if top3:
                lit = top3[0][0] if top3 and top3[0][1] >= ws.LIGHT_P else None
                st.update(mode='stop', top3=top3, lit=lit)
                rec = {'t': round(self.still_since, 1), 'floor': self.session.floor, 'top3': top3, 'lit': lit}
                if st['stops'] and st['stops'][-1]['t'] == rec['t']:
                    st['stops'][-1] = rec
                else:
                    st['stops'] = (st['stops'] + [rec])[-50:]
            return dict(st)


def run(phone: Phyphox, tracker: LiveTracker, status: dict, stop_event: threading.Event):
    """Poll loop for a background thread. status gets 'connected', 'measuring', 'error', 'buffers'."""
    session = None
    while not stop_event.is_set():
        try:
            if not phone.bufs:
                status['buffers'] = {k: list(v) for k, v in phone.discover().items()}
                if not {'acc', 'mag'} <= set(phone.bufs):
                    raise RuntimeError('phyphox experiment has no accelerometer/magnetometer buffers we can find')
            chunk, s = phone.fetch()
            if s.get('session') not in (None, session):         # measurement cleared/restarted on the phone
                if session is not None:
                    phone.restart()
                session = s.get('session')
            tracker.add(chunk)
            status.update(connected=True, measuring=bool(s.get('measuring')), error='', state=tracker.update())
        except Exception as e:
            status.update(connected=False, error=f'{type(e).__name__}: {e}'[:200])
        stop_event.wait(POLL_S)


def probe(url):
    p = Phyphox(url)
    print('Reading', p.base, '...')
    found = p.discover()
    for s in SENSORS:
        print(f'  {s:5} -> {found.get(s, "NOT FOUND")}')
    chunk, status = p.fetch()
    print('status:', status)
    for s, a in chunk.items():
        print(f'  {s:5}: {len(a)} samples, last t = {a[-1, 0]:.2f} s, last values = {np.round(a[-1, 1:], 3).tolist()}')
    if not {'acc', 'mag'} <= set(found):
        print('Missing buffers: send the output of http://<phone>:8080/config so the names can be added.')


# ============================================================================ checks on recorded data
def _stream(session):
    """One session's iPhone recordings laid end to end on the real clock (no overlaps), like a live phone."""
    rows = sorted((r for r in ws.manifest(session) if r['phone'] == 'iphone'), key=lambda r: ws.hk_epoch(r['start_hk']))
    t_first, parts, truth, prev_end = ws.hk_epoch(rows[0]['start_hk']), {s: [] for s in SENSORS}, [], -1.0
    for r in rows:
        rec = ws.read_folder(ws.DATA / session / 'clean' / r['folder'] / 'iphone', r['device'])
        start = min(rec[s][0, 0] for s in SENSORS)
        t0 = max(ws.hk_epoch(r['start_hk']) - t_first, prev_end + 0.5)     # manifest start times can overlap by a few s
        prev_end = t0 + max(rec[s][-1, 0] for s in SENSORS) - start
        for s in SENSORS:
            a = rec[s].copy(); a[:, 0] += t0 - start; parts[s].append(a)
        if r['type'] == 'stop':
            truth.append((int(r['floor']), ws.MERGE.get(r['node'], r['node']), t0))
    return {s: np.vstack(parts[s]) for s in SENSORS}, truth, int(rows[0]['floor'])


def replay(session, device, models):
    """Stream a recorded session through LiveTracker in 0.5 s steps and score every recorded stop."""
    stream, truth, floor = _stream(session)
    tr = LiveTracker(models, device, floor, None)
    end = max(a[-1, 0] for a in stream.values())
    for t in np.arange(0, end + 1, POLL_S):
        tr.add({s: a[(a[:, 0] > t - POLL_S) & (a[:, 0] <= t)] for s, a in stream.items()
                if ((a[:, 0] > t - POLL_S) & (a[:, 0] <= t)).any()})
        tr.update()
    stops, res = tr.state['stops'], dict(found=0, floor=0, top1=0, top3=0, lit=0, lit_right=0)
    for f, node, ts in truth:
        d = next((s for s in stops if ts - 1 <= s['t'] <= ts + 50), None)
        if d is None:
            continue
        res['found'] += 1; res['floor'] += d['floor'] == f; res['top1'] += d['top3'][0][0] == node
        res['top3'] += node in [p for p, _ in d['top3']]
        if d['lit']:
            res['lit'] += 1; res['lit_right'] += d['lit'] == node
    res['extra_stops'] = sum(not any(ts - 1 <= s['t'] <= ts + 50 for *_, ts in truth) for s in stops)
    return {'n_stops': len(truth), **res}


def check():
    """Every number behind the live rules -> out/live_checks.json (PROCESS-LOG entry 26)."""
    models, out = ws.build_models(), {}
    motion = {}
    for s in ws.SESSIONS:                         # 10 s windows: |acc| std and steps, stops vs walks
        stds = {'stop': [], 'walk': []}
        for r in ws.manifest(s):
            if r['phone'] != 'iphone':
                continue
            acc = ws.read_folder(ws.DATA / s / 'clean' / r['folder'] / 'iphone', r['device'])['acc']
            t, a = acc[:, 0], np.linalg.norm(acc[:, 1:4], axis=1)
            for t0 in np.arange(t[0] + 3, t[-1] - 10, 5):
                w = (t >= t0) & (t < t0 + 10)
                if w.sum() >= 500:
                    stds[r['type']].append(float(a[w].std()))
        motion[s] = {k: {'n_windows': len(v), 'std_p5_p50_p95': np.round(np.percentile(v, [5, 50, 95]), 3).tolist()}
                     for k, v in stds.items() if v}
    out['acc_std_10s_windows'] = motion
    standing = {}
    st = {s: ws.training_stops(sessions=(s,), phone='iphone') for s in ws.SESSIONS}
    for tr, te in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
        m = ws.PlaceModel(st[tr])
        for secs in (10, 20, 30, 60):             # place guess from the first N s of each held-out stop
            ok = 0
            for s in st[te]:
                t0 = s['rec']['mag'][0, 0] + ws.TRIM_S
                win = {k: s['rec'][k][(s['rec'][k][:, 0] >= t0) & (s['rec'][k][:, 0] < t0 + secs)] for k in ('mag', 'acc')}
                ok += m.top3(win, s['floor'], trim=0.0)[0][0] == s['place']
            standing[f'{tr}->{te} {secs}s'] = f'{ok}/{len(st[te])}'
    out['top1_by_standing_time'] = standing
    out['live_replay'] = {f'{s} streamed, model {d}': replay(s, d, models)
                          for s, d in (('sesi1', 'iPhone17,4'), ('sesi2', 'iPhone19,2'))}
    ws.OUT.mkdir(exist_ok=True)
    (ws.OUT / 'live_checks.json').write_text(json.dumps(out, indent=1))
    return out


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'probe':
        probe(sys.argv[2])
    elif sys.argv[1:] == ['check']:
        print(json.dumps(check(), indent=1))
    else:
        print(__doc__)
