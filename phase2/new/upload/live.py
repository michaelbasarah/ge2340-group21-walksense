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
from collections import Counter
from pathlib import Path

import numpy as np

import route
import walksense as ws
from pdr import count_steps

STILL_STD = 0.4        # m/s^2
MOTION_S = 3.0         # window for the still/moving test
NAME_AFTER_S = 3.0     # seconds of stillness before the first place guess (counted from the start of the still 3 s)
MAX_STOP_S = 60.0      # use at most the last 60 s of a stop (what the model was trained on)
VOTE_AFTER_S = 10.0    # floor rule (d): ask the magnetic floor vote once a stop has lasted 10 s (several 2 s windows)
WATCH_S = 3.0          # pressure watch between stop steps: median of the last 3 s of pressure (~3 samples at 1 Hz)
BARO_MIN_N = 3         # pressure samples of this stop needed before its floor step (~3 s at 1 Hz, like EDGE_S for uploads)
BARO_WAIT_S = 8.0      # ...but decide at the latest this long into the stop. The iPhone's newest pressure sample runs
                       # ~3.2 s behind its newest acc sample (PROCESS-LOG 95), so at 3 s the stop had 0-1 samples
POLL_S = 0.5
GAP_S = 5.0            # a break in the data (phyphox paused) ends the current stop or walk
KEEP_S = 180.0         # samples kept in memory
FIRST_S = 30.0         # the first read of a phone that has been measuring a while asks only for this much
RECORDINGS = Path(__file__).resolve().parent / 'recordings'
SENSORS = ('acc', 'gyr', 'mag', 'baro')
CSV = {'acc': ('Accelerometer.csv', '"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"'),
       'gyr': ('Gyroscope.csv', '"Time (s)","X (rad/s)","Y (rad/s)","Z (rad/s)"'),
       'mag': ('Magnetometer.csv', '"Time (s)","X (µT)","Y (µT)","Z (µT)"'),
       'baro': ('Barometer.csv', '"Time (s)","X (hPa)"')}
GUESSES = {'acc': ('acc_time', 'accX', 'accY', 'accZ'), 'gyr': ('gyro_time', 'gyroX', 'gyroY', 'gyroZ'),
           'mag': ('mag_time', 'magX', 'magY', 'magZ'), 'baro': ('baro_time', 'baroX')}   # names on Dicta's iPhone (entry 86)
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
        new = [tb for sensor, (tb, *_) in self.bufs.items() if sensor not in self.last]
        if new:     # first read: only the last FIRST_S, not 'full' (a 20-min session timed out at 3 s, entry 95)
            try:
                head = self._get({tb: '' for tb in new})['buffer']
                for sensor, (tb, *_) in self.bufs.items():
                    b = head.get(tb, {}).get('buffer') or []
                    if sensor not in self.last and b and b[-1] is not None:
                        self.last[sensor] = float(b[-1]) - FIRST_S
            except (KeyError, TypeError, ValueError):
                pass
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

    def device_model(self):
        """The phone model phyphox reports at /meta (e.g. iPhone19,2), or '' if it does not say."""
        try:
            return str(self._json('/meta').get('deviceModel', ''))
        except Exception:
            return ''


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
        self.stop = None              # current stop: {'start', 'floor_done', 'top3', 'lit'}
        self.state = {'mode': 'waiting', 'steps': 0, 'still_s': 0.0, 'top3': [], 'lit': None,
                      'floor': floor, 'floor_note': '', 'stops': [], 'now': None}
        self.lock = threading.Lock()

    def use_device(self, device):
        """Switch to another phone model's place model and floor rule (the phone reported a different model)."""
        with self.lock:
            self.device = device
            self.model, self.model_note = ws.pick_model(self.models, device)
            self.session.rule = ws.floor_rule_for(device)

    def _watch_pressure(self, st):
        """Every update, walking or standing: median of the last WATCH_S of pressure against this floor's reference
        (Session.watch_pressure). Catches an escalator or lift ride within seconds of the pressure crossing 0.40 hPa."""
        b = self.data['baro']
        if not len(b) or (self.session.rule == 'd' and self.device in ws.BARO_IGNORED):
            return
        last = b[b[:, 0] > b[-1, 0] - WATCH_S, 1]
        if len(last) >= 2:
            note = self.session.watch_pressure(float(np.median(last)), float(b[-1, 0]))
            if note:
                st.update(floor=self.session.floor, floor_note=note)
            return note
        return ''

    def _floor_step(self, baro, now, final=False):
        """The stop's one pressure floor step, once BARO_MIN_N pressure samples of the stop have arrived or the stop has
        lasted BARO_WAIT_S (final = the stop is ending). Returns the note, or None while still waiting."""
        ignored = self.session.rule == 'd' and self.device in ws.BARO_IGNORED
        p = baro[baro[:, 0] >= self.still_since, 1]
        no_baro_phone = not len(self.data['baro'])        # nothing from the barometer in the last KEEP_S
        if not (ignored or no_baro_phone or final or len(p) >= BARO_MIN_N or now - self.still_since >= BARO_WAIT_S):
            return None
        if final and not len(p):
            return ''                                     # stop too short to read its pressure: no floor step at all
        if len(p) and not ignored:
            return self.session.pressure_step(float(np.median(p)), float(np.median(p)), now, 0.0, is_stop=True)
        self.session.pressure_step(None, None, now, 0.0, is_stop=True)        # (d): this stop may ask the vote
        return ws.BARO_IGNORED[self.device] if ignored else 'no barometer data: floor kept'

    def set_floor(self, floor):
        with self.lock:
            self.session.set_floor(floor)
            b = self.data['baro']                 # "I'm on 4F/5F": the pressure now is this floor's reference (entry 95)
            last = b[b[:, 0] > b[-1, 0] - WATCH_S, 1] if len(b) else []
            if len(last):
                self.session.recent = [float(np.median(last))]
            self.state.update(floor=floor, floor_note=f'floor set by hand to {floor}F')

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
            watched = self._watch_pressure(st)
            if moving:
                if self.stop is not None and not self.stop['floor_done']:     # short stop: use the pressure it has
                    note = self._floor_step(self.data['baro'], now, final=True)
                    if note:
                        st.update(floor=self.session.floor, floor_note=note)
                    if st['stops'] and st['stops'][-1]['t'] == round(self.still_since, 1):
                        st['stops'][-1]['floor_note'] = note or 'stop too short to read its own pressure'
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
                st.update(mode='walking', still_s=0.0, steps=steps, dot=dot)
                return dict(st)
            if self.still_since is None:
                self.still_since = now - MOTION_S               # the whole last 3 s were already still
            st['still_s'] = round(now - self.still_since, 1)
            if now - self.still_since < NAME_AFTER_S:
                st['mode'] = 'standing'
                return dict(st)
            win = self._window(max(self.still_since, now - MAX_STOP_S), now)
            if self.stop is None:
                self.stop = {'start': self.still_since, 'floor_done': False}
            if not self.stop['floor_done']:                     # the floor, once per stop, from its own pressure
                note = self._floor_step(win['baro'], now)
                if note is None:
                    st['floor_note'] = 'waiting for this stop\'s pressure (the barometer runs ~3 s behind)'
                else:
                    self.stop['floor_done'] = True
                    st['floor'] = self.session.floor
                    if note or not watched:                     # keep the pressure watch's note of this same update
                        st['floor_note'] = note
            if self.session.vote_pending and now - self.still_since >= VOTE_AFTER_S and len(win['mag']) >= 20:
                v = self.model.vote_floor(win, trim=0.0) if self.model else None      # once per stop
                note = self.session.apply_vote(*v) if v else ''
                self.session.vote_pending = False
                if note:
                    st.update(floor=self.session.floor, floor_note=note)
            top3 = self.model.top3(win, self.session.floor, trim=0.0) if len(win['mag']) >= 20 and len(win['acc']) >= 20 else []
            top3 = [(p, q) for p, q in top3 if q > 0]          # no 0% fillers (entry 95): they were just the first names A-Z
            if top3:
                lit = top3[0][0] if top3 and top3[0][1] >= ws.LIGHT_P else None
                st.update(mode='stop', top3=top3, lit=lit, dot=None)
                self.anchor = (self.session.floor, top3[0][0])
                rec = {'t': round(self.still_since, 1), 'floor': self.session.floor, 'top3': top3, 'lit': lit,
                       'floor_note': st['floor_note']}
                if st['stops'] and st['stops'][-1]['t'] == rec['t']:
                    rec['first_floor'] = st['stops'][-1]['first_floor']    # the floor shown with the stop's first answer
                    st['stops'][-1] = rec
                else:
                    rec['first_floor'] = rec['floor']
                    st['stops'] = (st['stops'] + [rec])[-50:]
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
                model = phone.device_model()                  # entry 95: use the model the phone says it is
                status['phone_model'] = model
                if model and model != tracker.device and model in tracker.models:
                    status['device_note'] = f'phone reports {model}, --device said {tracker.device}: using {model}'
                    tracker.use_device(model)
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


def stream_through(tracker, stream, baro_lag=0.0):
    """Feed a recorded stream to a LiveTracker in POLL_S steps, as the poll loop would. baro_lag: a pressure sample
    stamped t reaches the laptop only at t + baro_lag (Dicta's iPhone: about 3.2 s, PROCESS-LOG 95); 0 = at once."""
    end = max(a[-1, 0] for a in stream.values())
    for t in np.arange(0, end + 1 + baro_lag, POLL_S):
        chunk = {}
        for s, a in stream.items():           # samples in (t - POLL_S, t]; the stream is sorted in time
            lag = baro_lag if s == 'baro' else 0.0
            i, j = np.searchsorted(a[:, 0], [t - POLL_S - lag, t - lag], side='right')
            if j > i:
                chunk[s] = a[i:j]
        tracker.add(chunk)
        tracker.update()
    return tracker.state['stops']


def replay(session, device, models, rule=None, baro_lag=0.0, details=False):
    """Stream a recorded session through LiveTracker in 0.5 s steps and score every recorded stop."""
    stream, truth, floor = _stream(session)
    tr = LiveTracker(models, device, floor, graph={})
    if rule:
        tr.session.rule = rule
    stops = stream_through(tr, stream, baro_lag)
    res, rows = dict(found=0, floor=0, top1=0, top3=0, lit=0, lit_right=0), []
    for f, node, ts in truth:
        d = next((s for s in stops if ts - 5 <= s['t'] <= ts + 50), None)
        rows.append({'truth_floor': f, 'truth': node, 'floor': d and d['floor'], 'first_floor': d and d.get('first_floor'),
                     'top3': d and d['top3'],
                     'lit': d and d['lit'], 'floor_note': d and d.get('floor_note')})
        if d is None:
            continue
        res['found'] += 1; res['floor'] += d['floor'] == f; res['top1'] += d['top3'][0][0] == node
        res['top3'] += node in [p for p, _ in d['top3']]
        if d['lit']:
            res['lit'] += 1; res['lit_right'] += d['lit'] == node
    res['extra_stops'] = sum(not any(ts - 5 <= s['t'] <= ts + 50 for *_, ts in truth) for s in stops)
    out = {'n_stops': len(truth), **res}
    return (out, rows) if details else out


IP18 = 'iPhone19,2'
IP18_SESSIONS = ('sesi1', '25nov', '25night')    # Dicta's iPhone 18 (manifests); the demo phone (entry 89: ip18 only)
PHONE_BARO_LAG_S = 3.2                          # median lag of the newest pressure sample behind the newest acc sample, polled live 27 Nov


def upload_answers(session, device, model):
    """The upload path on the same data: every iPhone take of the session analysed in time order as one upload each."""
    rows = sorted((r for r in ws.manifest(session) if r['phone'] == 'iphone'), key=lambda r: ws.hk_epoch(r['start_hk']))
    sess, out = ws.Session(int(rows[0]['floor']), rule=ws.floor_rule_for(device)), []
    for r in rows:
        rec = ws.read_folder(ws.session_dir(session) / 'clean' / r['folder'] / 'iphone', r['device'])
        rec['start_epoch'] = float(ws.hk_epoch(r['start_hk']))
        res = ws.analyse(rec, sess, {device: model}, kind=r['type'])
        if r['type'] == 'stop':
            out.append({'truth_floor': int(r['floor']), 'truth': ws.MERGE.get(r['node'], r['node']), 'floor': res['floor'],
                        'top3': res['top3'], 'lit': res['lit'], 'floor_note': res['floor_note']})
    return out


def _score(rows):
    found = [r for r in rows if r['top3']]
    return {'n_stops': len(rows), 'found': len(found), 'floor': sum(r['floor'] == r['truth_floor'] for r in found),
            'floor_at_first_answer': sum(r.get('first_floor', r['floor']) == r['truth_floor'] for r in found),
            'top1': sum(r['top3'][0][0] == r['truth'] for r in found),
            'top3': sum(r['truth'] in [p for p, _ in r['top3']] for r in found),
            'lit': sum(bool(r['lit']) for r in found), 'lit_right': sum(r['lit'] == r['truth'] for r in found if r['lit']),
            'top1_p_1.0': sum(r['top3'][0][1] >= 0.999 for r in found)}


def compare(tag='', lags=(0.0, PHONE_BARO_LAG_S)):
    """Live path vs upload path on Dicta's iPhone 18 sessions, each held out (model = the other ip18 sessions, as
    the demo phone's model is trained, entry 89). Live = the session streamed through LiveTracker with the pressure
    arriving at once (lag 0, what `check` does) and with the lag the real phone shows. -> out/live_vs_upload_ip18.json"""
    out = {'what': compare.__doc__.split('->')[0].strip(), 'device': IP18, 'sessions': {}}
    for held in IP18_SESSIONS:
        if held not in ws.SESSIONS:
            continue
        train = tuple(s for s in IP18_SESSIONS if s != held and s in ws.SESSIONS)
        model = ws.PlaceModel(ws.training_stops(sessions=train, device=IP18, exclude=ws.TRAIN_EXCLUDE))
        up = upload_answers(held, IP18, model)
        res = {'trained_on': list(train), 'upload': _score(up)}
        for lag in lags:
            _, lv = replay(held, IP18, {IP18: model}, baro_lag=lag, details=True)
            both = [(u, l) for u, l in zip(up, lv) if l['top3'] and u['top3']]
            res[f'live_baro_lag_{lag:g}s'] = {
                **_score(lv), 'same_top1_as_upload': f"{sum(u['top3'][0][0] == l['top3'][0][0] for u, l in both)}/{len(both)}",
                'same_floor_as_upload': f"{sum(u['floor'] == l['floor'] for u, l in both)}/{len(both)}",
                'floor_notes': dict(Counter(_note_kind(l['floor_note']) for l in lv if l['top3'])),
                'stops': [{'truth': f"{u['truth_floor']}F {u['truth']}", 'upload': f"{u['floor']}F {u['top3'][0][0] if u['top3'] else '-'}",
                           'live': f"{l['floor']}F {l['top3'][0][0]}" if l['top3'] else 'not found'} for u, l in zip(up, lv)]}
        out['sessions'][held] = res
    ws.OUT.mkdir(exist_ok=True)
    (ws.OUT / f'live_vs_upload_ip18{tag}.json').write_text(json.dumps(out, indent=1))
    return out


def trace(src, floor=5, baro_lag=PHONE_BARO_LAG_S, device=IP18, models=None):
    """A live capture folder (live-walk/evidence/*/) or a live recording ZIP streamed through LiveTracker with the
    phone's pressure lag; returns the stops and every floor change with its phone time."""
    src = Path(src)
    if src.is_dir():
        import live_phone_check
        rec, _ = live_phone_check.read_capture(src)
    else:
        rec = ws.read_zip(src.read_bytes())
    stream = {s: rec[s] for s in SENSORS if s in rec and len(rec[s])}
    tr = LiveTracker(models or ws.build_models(), device, floor, graph={})
    end = max(a[-1, 0] for a in stream.values())
    changes, prev = [], tr.session.floor
    for t in np.arange(0, end + 1 + baro_lag, POLL_S):
        chunk = {}
        for s, a in stream.items():
            lag = baro_lag if s == 'baro' else 0.0
            i, j = np.searchsorted(a[:, 0], [t - POLL_S - lag, t - lag], side='right')
            if j > i:
                chunk[s] = a[i:j]
        tr.add(chunk)
        st = tr.update()
        if st.get('floor') != prev:
            changes.append({'t': st.get('now'), 'to': st.get('floor'), 'mode': st.get('mode'), 'note': st.get('floor_note')})
            prev = st.get('floor')
    out = {'source': src.name, 'baro_lag_s': baro_lag, 'floor_changes': changes, 'rides': []}
    for r in rides(stream.get('baro', np.empty((0, 2))), stream['acc']):
        after = next((c for c in changes if c['t'] >= r['start'] - 1), None)   # first floor change from the ride on
        r['floor_change'] = after
        r['latency_after_ride_end_s'] = round(after['t'] - r['end'], 1) if after else None
        out['rides'].append(r)
    out['stops'] = [{k: v for k, v in s.items() if k != 'lit'} for s in tr.state['stops']]
    return out


def rides(baro, acc, half=3.0, rate=0.08, min_hpa=0.4):
    """Floor rides found in the pressure alone: samples where pressure 3 s later differs from 3 s earlier by more
    than `rate` hPa, joined into runs; a run that moves >= min_hpa is a ride (rise = down). still_share = part of the
    ride with |acc| std < STILL_STD over 1 s (standing on the escalator or in the lift reads as still)."""
    if len(baro) < 10:
        return []
    t, p = baro[:, 0], baro[:, 1]
    moving = np.array([abs(np.median(p[(t > x) & (t <= x + half)]) - np.median(p[(t >= x - half) & (t < x)]))
                       > rate if ((t > x) & (t <= x + half)).any() and ((t >= x - half) & (t < x)).any() else False
                       for x in t])
    out, i = [], 0
    while i < len(t):
        if not moving[i]:
            i += 1; continue
        j = i
        while j + 1 < len(t) and moving[j + 1]:
            j += 1
        p0 = float(np.median(p[(t >= t[i] - half) & (t < t[i])])); p1 = float(np.median(p[(t > t[j]) & (t <= t[j] + half)]))
        if abs(p1 - p0) >= min_hpa:
            a = acc[(acc[:, 0] >= t[i]) & (acc[:, 0] <= t[j])]
            sd = [np.linalg.norm(a[(a[:, 0] >= x) & (a[:, 0] < x + 1), 1:4], axis=1).std() for x in np.arange(t[i], t[j], 1.0)]
            out.append({'start': round(float(t[i]), 1), 'end': round(float(t[j]), 1), 'seconds': round(float(t[j] - t[i]), 1),
                        'hpa': round(p1 - p0, 2), 'direction': '5F->4F (pressure rose)' if p1 > p0 else '4F->5F (pressure fell)',
                        'still_share': round(float(np.mean([x < STILL_STD for x in sd])), 2) if sd else None})
        i = j + 1
    return out


def _note_kind(note):
    note = note or ''
    for k in ('no barometer data', 'waiting for the barometer', 'magnetic floor vote', 'pressure rose', 'pressure fell', 'long gap'):
        if note.startswith(k):
            return k
    return note or '(no note: pressure used, floor kept)'


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
    elif sys.argv[1:2] == ['compare']:
        r = compare(*sys.argv[2:3])
        print(json.dumps({s: {k: ({kk: vv for kk, vv in v.items() if kk != 'stops'} if isinstance(v, dict) else v) for k, v in x.items()} for s, x in r['sessions'].items()}, indent=1))
    elif sys.argv[1:2] == ['trace']:
        print(json.dumps(trace(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5), indent=1))
    elif sys.argv[1:] == ['check']:
        print(json.dumps(check(), indent=1))
    else:
        print(__doc__)
