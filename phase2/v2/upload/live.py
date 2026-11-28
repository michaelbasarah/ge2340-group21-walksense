#!/usr/bin/env python3
"""Live mode: read phyphox's remote access while you walk, and guess the place at every stop.

  python live.py probe http://<phone-ip>     # first: check the laptop can read the phone (port 80 on our iPhones, entry 86)
  python server.py --live http://<phone-ip> --device iPhone19,2  # then: the map page updates live

phyphox REST calls used (from the official web interface's code, phyphox-webinterface/index.html):
  /get?<buf>=<last value of ref>%7C<ref>&<ref>=<last value>   -> only newer samples ("full" = all)
  response {"buffer": {name: {"buffer": [...], ...}}, "status": {"measuring", "session", ...}}
Buffer names are read from /config if the phone offers it (not confirmed in the docs we could
reach), otherwise common names are tried; `probe` shows what was found.

Rules (all checked on the 24-Nov iPhone data, PROCESS-LOG entry 26):
  standing = |acc| std over the last 3 s < 0.4 m/s^2 (stops 95% <= 0.29, walks >= 0.8)
  a stop is named once the last 3 s are still (3 s of stop gives the same top-1 as 10 s; entry 27)
  the floor is updated once per stop from its median pressure (27/27 and 26/26); under floor rule (d) (default,
  PROCESS-LOG 90) a stop without pressure, or one of the first stops after a 15-min gap, also asks the magnetic
  floor vote once it has lasted VOTE_AFTER_S (2 confident votes in a row switch the floor)
  while walking, a dot moves along the recorded corridors from the last named stop (route.py)
  phyphox play -> pause is saved as a phyphox-style ZIP in recordings/ (uploadable on the page)
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

import route
import walksense as ws
from pdr import count_steps

STILL_STD = 0.4        # m/s^2
MOTION_S = 1.0         # window for the still/moving test (entry 96; was 3 s). 1 s still: 98.6% / 99.8% of stop seconds, 0% of walk seconds (entry 61)
NAME_AFTER_S = 1.0     # seconds of stillness before the first place guess = a guess as soon as 1 s is still (entry 96; was 3 s)
LIT_AFTER_S = 3.0      # the red circle may light only after 3 s still (the tested 3 s rule); before that the guess shows unlit
WALK_CONFIRM_S = 1.0   # at a stop, motion must last 1 s before it counts as walking (one shuffle does not end the stop)
BARO_WAIT_S = 8.0      # a stop waits this long for the iPhone's late pressure (entry 28) before the no-pressure path
WALK_FLOOR = True      # floor change while walking: 5 s median pressure 0.40 hPa off the floor reference for 5 s (entry 96)
WALK_FLOOR_S = 5.0
MAX_STOP_S = 60.0      # use at most the last 60 s of a stop (what the model was trained on)
VOTE_AFTER_S = 10.0    # floor rule (d): ask the magnetic floor vote once a stop has lasted 10 s (several 2 s windows)
POLL_S = 0.5
GAP_S = 5.0            # a break in the data (phyphox paused) ends the current stop or walk
KEEP_S = 180.0         # samples kept in memory
RECORDINGS = Path(__file__).resolve().parent / 'recordings'
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
            raise ValueError('phyphox address must look like http://192.168.137.23 (add :port only if phyphox shows one)')
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
        except (urllib.error.HTTPError, ValueError):
            cfg = {}
        except OSError as e:                            # cannot reach the phone at all
            raise ConnectionError(f'cannot reach {self.base} ({getattr(e, "reason", e)}): same network? VPN off? phyphox remote access on?')
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
    def __init__(self, models, device='iPhone17,4', floor=5, graph=None):
        self.models, self.device = models, device
        self.model, self.model_note = ws.pick_model(models, device)
        self.session = ws.Session(floor, rule=ws.floor_rule_for(device))   # (d) for barometer phones (entry 90)
        self.data = {s: np.empty((0, 2 if s == 'baro' else 4)) for s in SENSORS}
        self.graph = route.build() if graph is None else graph
        self.anchor = None            # last named place (floor, place): where the walking dot starts
        self.dot = None
        self.still_since = None       # phone time the current stand started
        self.walk_since = None
        self.stop = None              # current stop: {'start', 'floor_done'}
        self.moving_since = None      # phone time the motion at a stop began (WALK_CONFIRM_S)
        self.jump_since = None        # phone time the walking pressure first sat a floor away (WALK_FLOOR)
        self.keep_stops = 50          # stops kept in state (the page); replay keeps all to score them
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
            now = max((self.data[s][-1, 0] for s in SENSORS if len(self.data[s])), default=None)
            if now is not None:
                for s in SENSORS:
                    self.data[s] = self.data[s][self.data[s][:, 0] >= now - KEEP_S]

    def _window(self, t0, t1):
        return {s: self.data[s][(self.data[s][:, 0] >= t0) & (self.data[s][:, 0] <= t1)] for s in SENSORS}

    def _guess(self, win, floor):
        """Place top-3 of the stand so far: the app's visit answer (mean over 2 s windows) once 2 s exist, before that
        the mean magnetic x/y/z of the stand fed to the same kNN (the 1 s estimate of entry 61)."""
        if self.model is None or floor not in self.model.models or len(win['mag']) < 5:
            return []
        if win['mag'][-1, 0] - win['mag'][0, 0] >= ws.WINDOW_S:
            t3 = self.model.top3(win, floor, trim=0.0)
            if t3:
                return t3
        m = self.model.models[floor]
        p = m.predict_proba(win['mag'][:, 1:4].mean(0)[None, :])[0]
        return [(str(m.classes_[i]), round(float(p[i]), 3)) for i in np.argsort(-p)[:3]]

    def _walk_floor(self):
        """While walking: the last WALK_FLOOR_S of pressure sat FLOOR_JUMP_HPA off this floor's reference for
        WALK_FLOOR_S -> the floor tracker's own step (R0 / d) with that pressure. Returns its note, '' otherwise."""
        s, b = self.session, self.data['baro']
        if not s.recent or not len(b) or (s.rule == 'd' and self.device in ws.BARO_IGNORED):
            self.jump_since = None
            return ''
        t_b = float(b[-1, 0])
        w = b[b[:, 0] > t_b - WALK_FLOOR_S, 1]
        if len(w) < 3:
            return ''
        p = float(np.median(w))
        d = p - float(np.median(s.recent))
        if not ((d > ws.FLOOR_JUMP_HPA and s.floor == 5) or (d < -ws.FLOOR_JUMP_HPA and s.floor == 4)):
            self.jump_since = None
            return ''
        if self.jump_since is None:
            self.jump_since = t_b
        if t_b - self.jump_since < WALK_FLOOR_S:
            return ''
        self.jump_since = None
        return s.pressure_step(p, p, t_b, 0.0, is_stop=False)

    def update(self):
        with self.lock:
            acc = self.data['acc']
            if len(acc) < 50:
                return dict(self.state)
            now = float(acc[-1, 0])
            recent = acc[acc[:, 0] >= now - MOTION_S]
            moving = bool(np.linalg.norm(recent[:, 1:4], axis=1).std() >= STILL_STD)
            st = self.state
            st['now'] = round(now, 1)
            self.moving_since = (self.moving_since if self.moving_since is not None else now) if moving else None
            if moving and self.stop is not None and now - self.moving_since < WALK_CONFIRM_S:
                moving = False                                  # one shuffle at a stop: still the same stop
            if moving:
                if self.stop is not None or self.walk_since is None:
                    self.walk_since, self.stop = now, None
                    self.dot = route.Dot(self.graph, *self.anchor) if self.anchor and self.anchor[0] == self.session.floor else None
                self.still_since = None
                w = acc[acc[:, 0] >= self.walk_since]
                steps = int(count_steps(w[:, 0], np.linalg.norm(w[:, 1:4], axis=1))[0]) if len(w) > 200 else 0   # < 2 s: too short to count
                dot = None
                if self.dot is not None:
                    h = route.heading(acc[acc[:, 0] > now - route.HEAD_S], self.data['mag'][self.data['mag'][:, 0] > now - route.HEAD_S])
                    pos = self.dot.update(steps, h)
                    xy = self.dot.xy(pos) if pos else None
                    if xy:
                        dot = {'x': round(xy[0], 1), 'y': round(xy[1], 1), 'floor': self.dot.floor, 'from': pos[0], 'to': pos[1]}
                note = self._walk_floor() if WALK_FLOOR else ''
                if note:                                        # escalator / stairs: show the new floor at once
                    self.dot = dot = None                       # the dot waits for the next stand on the new floor
                    st.update(floor=self.session.floor, floor_note=note)
                st.update(mode='walking', still_s=0.0, steps=steps, dot=dot)
                return dict(st)
            self.jump_since = None
            if self.still_since is None:
                self.still_since = now - MOTION_S               # the whole last MOTION_S were already still
            st['still_s'] = round(now - self.still_since, 1)
            if now - self.still_since < NAME_AFTER_S:
                st['mode'] = 'standing'
                return dict(st)
            win = self._window(max(self.still_since, now - MAX_STOP_S), now)
            if self.stop is None:
                self.stop = {'start': self.still_since, 'floor_done': False}
            if not self.stop['floor_done']:                     # floor once per stop, once its pressure has arrived
                p = win['baro'][:, 1] if len(win['baro']) else None
                ignored = self.session.rule == 'd' and self.device in ws.BARO_IGNORED
                waited = now - self.still_since >= BARO_WAIT_S or self.device in ws.NO_BAROMETER
                if p is not None and len(p) and not ignored:
                    note = self.session.pressure_step(float(np.median(p)), float(np.median(p)), now, 0.0, is_stop=True)
                elif ignored or waited:
                    self.session.pressure_step(None, None, now, 0.0, is_stop=True)    # (d): this stop may ask the vote
                    note = ws.BARO_IGNORED[self.device] if ignored else 'no barometer data: floor kept'
                else:
                    note = None
                    st['floor_note'] = 'checking the floor (waiting for pressure)'
                if note is not None:
                    self.stop['floor_done'] = True
                    st.update(floor=self.session.floor, floor_note=note)
            if self.session.vote_pending and now - self.still_since >= VOTE_AFTER_S and len(win['mag']) >= 20:
                v = self.model.vote_floor(win, trim=0.0) if self.model else None      # once per stop
                note = self.session.apply_vote(*v) if v else ''
                self.session.vote_pending = False
                if note:
                    st.update(floor=self.session.floor, floor_note=note)
            top3 = self._guess(win, self.session.floor)
            if top3:
                lit = top3[0][0] if top3[0][1] >= ws.LIGHT_P and now - self.still_since >= LIT_AFTER_S else None
                st.update(mode='stop', top3=top3, lit=lit, dot=None)
                self.anchor = (self.session.floor, top3[0][0])
                rec = {'t': round(self.still_since, 1), 'floor': self.session.floor, 'top3': top3, 'lit': lit}
                if st['stops'] and st['stops'][-1]['t'] == rec['t']:
                    rec['first'], rec['first_s'] = st['stops'][-1].get('first', top3), st['stops'][-1].get('first_s')
                    st['stops'][-1] = rec
                else:
                    rec['first'], rec['first_s'] = top3, round(now - self.still_since, 1)   # the first guess and its still seconds, for scoring
                    st['stops'] = (st['stops'] + [rec])[-self.keep_stops:]
            return dict(st)


def save_recording(parts, device, started, folder=RECORDINGS):
    """Samples from one phyphox play..pause -> folder/<time>.zip, laid out like a phyphox export."""
    data = {s: np.vstack(v) for s, v in parts.items() if v}
    if 'acc' not in data or len(data['acc']) < 50:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (time.strftime('%Y%m%d-%H%M%S', time.localtime(started)) + '.zip')
    t0 = min(a[0, 0] for a in data.values())
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for s, a in data.items():
            buf = io.StringIO(); buf.write(CSV[s][1] + '\n'); np.savetxt(buf, a, delimiter=',', fmt='%.9E')
            z.writestr(CSV[s][0], buf.getvalue())
        z.writestr('meta/device.csv', f'"property","value"\n"deviceModel","{device}"\n')
        z.writestr('meta/time.csv', f'"event","experiment time","system time"\n"START",{t0!r},{started!r}\n')
    return {'file': f'recordings/{path.name}', 'seconds': round(float(data['acc'][-1, 0] - data['acc'][0, 0]), 1)}


def run(phone: Phyphox, tracker: LiveTracker, status: dict, stop_event: threading.Event, record_to=RECORDINGS):
    """Poll loop for a background thread. status gets 'connected', 'measuring', 'error', 'buffers',
    'recording' and 'last_recording' (each phyphox play..pause is saved to record_to)."""
    session, rec, started = None, None, None

    def flush():
        nonlocal rec
        if rec is not None:
            saved = save_recording(rec, tracker.device, started, record_to)
            if saved:
                status['last_recording'] = saved
        rec = None

    while not stop_event.is_set():
        try:
            if not phone.bufs:
                status['buffers'] = {k: list(v) for k, v in phone.discover().items()}
                if not {'acc', 'mag'} <= set(phone.bufs):
                    raise RuntimeError('phyphox experiment has no accelerometer/magnetometer buffers we can find')
            chunk, s = phone.fetch()
            if s.get('session') not in (None, session):         # measurement cleared/restarted on the phone
                if session is not None:
                    phone.restart(); flush()
                session = s.get('session')
            measuring = bool(s.get('measuring'))
            if measuring and rec is None:
                rec, started = {k: [] for k in SENSORS}, time.time()
            if rec is not None:
                for k, a in chunk.items():
                    rec[k].append(a)
            if not measuring:
                flush()
            tracker.add(chunk)
            status.update(connected=True, measuring=measuring, recording=rec is not None, error='', state=tracker.update())
        except Exception as e:
            status.update(connected=False, error=f'{type(e).__name__}: {e}'[:200])
        stop_event.wait(POLL_S)
    flush()                                             # server stopping mid-measurement: keep what we have


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
        print('Missing buffers: send the output of http://<phone>/config (the same address as above + /config) so the names can be added.')


# ============================================================================ checks on recorded data
def _stream(session):
    """One session's iPhone recordings laid end to end on the real clock (no overlaps), like a live phone."""
    rows = sorted((r for r in ws.manifest(session) if r['phone'] == 'iphone'), key=lambda r: ws.hk_epoch(r['start_hk']))
    t_first, parts, truth, prev_end = ws.hk_epoch(rows[0]['start_hk']), {s: [] for s in SENSORS}, [], -1.0
    for r in rows:
        rec = ws.read_folder(ws.session_dir(session) / 'clean' / r['folder'] / 'iphone', r['device'])
        have = [s for s in SENSORS if s in rec and len(rec[s])]           # 25 night: some takes have no barometer
        start = min(rec[s][0, 0] for s in have)
        t0 = max(ws.hk_epoch(r['start_hk']) - t_first, prev_end + 0.5)     # manifest start times can overlap by a few s
        prev_end = t0 + max(rec[s][-1, 0] for s in have) - start
        for s in have:
            a = rec[s].copy(); a[:, 0] += t0 - start; parts[s].append(a)
        if r['type'] == 'stop':
            truth.append((int(r['floor']), ws.MERGE.get(r['node'], r['node']), t0))
    return {s: np.vstack(parts[s]) for s in SENSORS if parts[s]}, truth, int(rows[0]['floor'])


def replay(session, device, models, rule=None, baro_lag=0.0):
    """Stream a recorded session through LiveTracker in 0.5 s steps and score every recorded stop.
    baro_lag: pressure reaches the tracker this many seconds after acc/mag (the real iPhone does, entry 28)."""
    stream, truth, floor = _stream(session)
    tr = LiveTracker(models, device, floor, graph={})
    tr.keep_stops = 10 ** 6                  # entry 96: with 1 s stands a session can pass 50 stops
    if rule:
        tr.session.rule = rule
    end = max(a[-1, 0] for a in stream.values())
    for t in np.arange(0, end + baro_lag + 1, POLL_S):
        ch = {}
        for s, a in stream.items():
            lag = baro_lag if s == 'baro' else 0.0
            m = (a[:, 0] > t - POLL_S - lag) & (a[:, 0] <= t - lag)
            if m.any():
                ch[s] = a[m]
        tr.add(ch)
        tr.update()
    stops, res = tr.state['stops'], dict(found=0, floor=0, top1=0, first_top1=0, top3=0, lit=0, lit_right=0)
    for f, node, ts in truth:
        d = next((s for s in stops if ts - 5 <= s['t'] <= ts + 50), None)
        if d is None:
            continue
        res['found'] += 1; res['floor'] += d['floor'] == f; res['top1'] += d['top3'][0][0] == node
        res['first_top1'] += bool(d.get('first')) and d['first'][0][0] == node
        res['top3'] += node in [p for p, _ in d['top3']]
        if d['lit']:
            res['lit'] += 1; res['lit_right'] += d['lit'] == node
    res['extra_stops'] = sum(not any(ts - 5 <= s['t'] <= ts + 50 for *_, ts in truth) for s in stops)
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
            acc = ws.read_folder(ws.session_dir(s) / 'clean' / r['folder'] / 'iphone', r['device'])['acc']
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
    pairs = [(tr, te) for tr in ws.SESSIONS for te in ws.SESSIONS if tr != te]     # every ordered pair of sessions
    for tr, te in pairs:
        m = ws.PlaceModel(st[tr])
        for secs in (3, 6, 10, 60):               # place guess from the first N s of each held-out stop
            ok = 0
            for s in st[te]:
                t0 = s['rec']['mag'][0, 0] + ws.TRIM_S
                win = {k: s['rec'][k][(s['rec'][k][:, 0] >= t0) & (s['rec'][k][:, 0] < t0 + secs)] for k in ('mag', 'acc')}
                ok += m.top3(win, s['floor'], trim=0.0)[0][0] == s['place']
            standing[f'{tr}->{te} {secs}s'] = f'{ok}/{len(st[te])}'
    out['top1_by_standing_time'] = standing
    out['walking_dot'] = {f'{tr}->{te}': route.evaluate(tr, te) for tr, te in pairs}
    out['live_replay'] = {f'{s} streamed, model {d}': replay(s, d, models)
                          for s, d in (('sesi1', 'iPhone17,4'), ('sesi2', 'iPhone19,2')) if s in ws.SESSIONS}
    if '25nov' in ws.SESSIONS:                    # the 25-Nov iPhone (iPhone19,2) as a held-out stream
        out['live_replay']['25nov streamed, model iPhone17,4'] = replay('25nov', 'iPhone17,4', models)
        for held, other in (('sesi1', '25nov'), ('25nov', 'sesi1')):       # same handset, other session only
            if held in ws.SESSIONS:
                out['live_replay'][f'{held} streamed, model iPhone19,2 from {other} only'] = replay(
                    held, 'iPhone19,2', {'iPhone19,2': ws.PlaceModel(ws.training_stops(sessions=(other,), device='iPhone19,2'))})
    if '25night' in ws.SESSIONS:                  # Dicta's pressure dropout (entries 74, 90): floor rule per stop, held-out model
        m = {'iPhone19,2': ws.PlaceModel(ws.training_stops(sessions=('sesi1', '25nov'), device='iPhone19,2'))}
        for rule in ws.FLOOR_RULES:
            out['live_replay'][f'25night streamed, model iPhone19,2 from sesi1+25nov, floor rule {rule}'] = replay(
                '25night', 'iPhone19,2', m, rule=rule)
    ws.OUT.mkdir(exist_ok=True)
    ws.out_file('live_checks').write_text(json.dumps(out, indent=1))
    return out


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'probe':
        probe(sys.argv[2])
    elif sys.argv[1:] == ['check']:
        print(json.dumps(check(), indent=1))
    else:
        print(__doc__)
