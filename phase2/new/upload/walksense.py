#!/usr/bin/env python3
"""WalkSense upload pipeline: one phyphox ZIP in, floor + steps + place guess out.

Reused unchanged: step detector (old/positioning-pilot/step_detection.py), gyro turns
(new/tracking/pdr.py), kNN set-up (new/cross-day/crossday.py make_model).
New here: a pressure floor tracker (jump from the median of recent readings), per-phone-model
training on the 24-Nov stops, and a comparison of magnetic features (xyz / tilt / |B|).

  python walksense.py evaluate      # leave one session out over the sessions -> out/eval.json
  WALKSENSE_SESSIONS=24nov python walksense.py evaluate   # the old 24-Nov-only behaviour -> out/eval_24nov.json
Needs: numpy pandas scikit-learn matplotlib (same as crossday.py).
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
sys.path.insert(0, str(NEW / 'tracking'))
import pdr                                   # noqa: E402  (also puts cross-day and the pilot on sys.path)
from pdr import count_steps, turns           # noqa: E402
from crossday import make_model              # noqa: E402

DATA = NEW.parent / 'clean-data' / '2026-11-24'   # kept for ../smoothing/replay.py; new code uses session_dir()
CLEAN = NEW.parent / 'clean-data'
# Every session the app can train on: a name and the folder that holds its clean/ and raw/ folders.
ALL_SESSIONS = [{'name': 'sesi1', 'path': CLEAN / '2026-11-24' / 'sesi1'},
                {'name': 'sesi2', 'path': CLEAN / '2026-11-24' / 'sesi2'},
                {'name': '25nov', 'path': CLEAN / '2026-11-25'}]
# WALKSENSE_SESSIONS=24nov (or a comma list of names) limits the sessions; unset = all of them.
_ENV = os.environ.get('WALKSENSE_SESSIONS', '').strip()
TAG = _ENV.lower()
_WANT = {'': None, 'all': None, '24nov': {'sesi1', 'sesi2'}}.get(TAG, set(TAG.split(',')) if TAG else None)
SESSION_LIST = [s for s in ALL_SESSIONS if _WANT is None or s['name'] in _WANT]
SESSIONS = tuple(s['name'] for s in SESSION_LIST)
SESSION_PATH = {s['name']: s['path'] for s in ALL_SESSIONS}
OUT = HERE / 'out'
WINDOW_S = 2.0          # same window as crossday.py
TRIM_S = 5.0            # skip the first/last 5 s of a stop (phone being placed or picked up)
EDGE_S = 3.0            # pressure at the start/end of a recording = median of its first/last 3 s
FLOOR_JUMP_HPA = 0.40   # one floor is ~0.58-0.68 hPa (results.json); 0.30-0.50 all give 27/27 and 26/26 on 24 Nov
REF_N = 6               # floor reference = median of the last 6 pressure readings on the current floor
LONG_GAP_S = 15 * 60    # weather drifts ~0.2-0.3 hPa/h: across a longer gap, keep the floor instead of guessing
WALK_CADENCE = 0.5      # steps/s above this = a walk, below = a stop
LIGHT_P = 0.8           # light the map circle only this sure: held-out lit 33/44 right, unlit 1/9 (out/eval.json)
STRIDE_M = 0.54         # median stride on 23 Nov (PROCESS-LOG entry 19); rough
MAX_MEMBER_BYTES = 60_000_000   # biggest phyphox CSV on 24 Nov is ~3 MB; refuses zip bombs
FILES = {'acc': ('Accelerometer.csv',), 'gyr': ('Gyroscope.csv',), 'mag': ('Magnetometer.csv',),
         'baro': ('Barometer.csv', 'Pressure.csv')}
MERGE = {'canteen_revisit': 'canteen'}   # session 1 visited the canteen twice


# ============================================================================ reading
def _table(text):
    rows = [r for r in csv.reader(io.StringIO(text))][1:]
    return np.array([[float(v) for v in r] for r in rows if r], dtype=float).reshape(-1, len(rows[0]) if rows else 1)


def read_zip(data: bytes) -> dict:
    """A phyphox export ZIP (bytes) -> {'acc','gyr','mag','baro': array(t, ...), 'device', 'start_epoch'}."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('not a ZIP file')
    by_name = {Path(i.filename).name: i for i in zf.infolist() if not i.is_dir()}
    rec = {'device': '', 'start_epoch': None}
    for key, names in FILES.items():
        info = next((by_name[n] for n in names if n in by_name), None)
        if info is None:
            continue
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f'{info.filename} is too large')
        rec[key] = _table(zf.read(info).decode('utf-8', 'replace'))
    for key in ('acc', 'mag'):
        if key not in rec or len(rec[key]) < 50:
            raise ValueError(f'the ZIP has no usable {FILES[key][0]} (record with phyphox and export as CSV)')
    if 'meta/device.csv' in {i.filename for i in zf.infolist()}:
        meta = dict(r[:2] for r in csv.reader(io.StringIO(zf.read('meta/device.csv').decode('utf-8', 'replace'))) if len(r) >= 2)
        rec['device'] = meta.get('deviceModel', '')
    if 'meta/time.csv' in {i.filename for i in zf.infolist()}:
        for r in csv.reader(io.StringIO(zf.read('meta/time.csv').decode('utf-8', 'replace'))):
            if r and r[0] == 'START':
                rec['start_epoch'] = float(r[2])
                break
    return rec


def read_folder(folder: Path, device: str) -> dict:
    rec = {'device': device, 'start_epoch': None}
    for key, names in FILES.items():
        for n in names:
            if (folder / n).exists():
                rec[key] = _table((folder / n).read_text(encoding='utf-8'))
                break
    return rec


def session_dir(session):
    return SESSION_PATH[session]


def manifest(session):
    with open(session_dir(session) / 'clean' / 'manifest.csv', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def hk_epoch(hhmmss):
    h, m, s = (int(x) for x in hhmmss.split(':'))
    return h * 3600 + m * 60 + s           # seconds since midnight; only differences are used


# ============================================================================ features
def stop_features(rec, kind='xyz', trim=TRIM_S):
    """One row per 2 s window of a stop. xyz = mean field in phone axes: works when the phone is
    held flat facing the door (24-Nov protocol). tilt = (B along gravity, B across gravity)."""
    mag, acc = rec['mag'], rec['acc']
    t0, t1 = mag[0, 0], mag[-1, 0]
    lo, hi = t0 + trim, t1 - trim
    if hi - lo < WINDOW_S:            # short recording: use all of it
        lo, hi = t0, t1
    rows = []
    for a in np.arange(lo, hi - WINDOW_S + 1e-9, WINDOW_S):
        m = mag[(mag[:, 0] >= a) & (mag[:, 0] < a + WINDOW_S), 1:4]
        g = acc[(acc[:, 0] >= a) & (acc[:, 0] < a + WINDOW_S), 1:4]
        if len(m) < 10 or len(g) < 10:
            continue
        b, up = m.mean(0), g.mean(0) / np.linalg.norm(g.mean(0))
        bv = float(b @ up)
        if kind == 'tilt':
            rows.append([bv, float(np.linalg.norm(b - bv * up))])
        elif kind == 'xyz':
            rows.append(list(b))
        else:
            rows.append([float(np.linalg.norm(b))])
    return np.array(rows)


def edge_pressure(rec):
    if 'baro' not in rec or len(rec['baro']) < 2:
        return None, None
    t, p = rec['baro'][:, 0], rec['baro'][:, 1]
    return float(np.median(p[t <= t[0] + EDGE_S])), float(np.median(p[t >= t[-1] - EDGE_S]))


def motion(rec):
    """Steps (team detector), cadence, rough distance and gyro turns (team turn finder)."""
    acc = rec['acc']
    t = acc[:, 0]
    dur = float(t[-1] - t[0])
    steps, _, _ = count_steps(t, np.linalg.norm(acc[:, 1:4], axis=1))
    out = {'duration_s': round(dur, 1), 'steps': int(steps), 'cadence': round(steps / dur, 2) if dur > 0 else 0.0,
           'distance_m': round(steps * STRIDE_M, 1), 'turns': [], 'net_turn_deg': None}
    if 'gyr' in rec and len(rec['gyr']) > 10:
        gyr = np.column_stack([np.interp(t, rec['gyr'][:, 0], rec['gyr'][:, i]) for i in (1, 2, 3)])
        tl, net, _ = turns(t, acc[:, 1:4], gyr)
        out['turns'] = [{'t_s': x['t_s'], 'deg': x['deg'], 'side': 'left' if x['deg'] > 0 else 'right'} for x in tl]
        out['net_turn_deg'] = round(net)
    return out


# ============================================================================ model
class PlaceModel:
    """Magnetic kNN per floor, trained on the stops of one phone model."""

    def __init__(self, stops, kind='xyz'):
        self.kind, self.models, self.places = kind, {}, {}
        for floor in sorted({s['floor'] for s in stops}):
            X, y = [], []
            for s in (s for s in stops if s['floor'] == floor):
                f = stop_features(s['rec'], kind)
                X.append(f); y += [s['place']] * len(f)
            X = np.vstack(X)
            self.models[floor] = make_model('knn', len(y)).fit(X, y)
            self.places[floor] = sorted(set(y))

    def top3(self, rec, floor, trim=TRIM_S):
        if floor not in self.models:
            return []
        f = stop_features(rec, self.kind, trim)
        if not len(f):
            return []
        m = self.models[floor]
        p = m.predict_proba(f).mean(0)          # average of the 2 s windows = this visit's answer
        order = np.argsort(-p)[:3]
        return [(str(m.classes_[i]), round(float(p[i]), 3)) for i in order]


def training_stops(device=None, sessions=SESSIONS, phone=None):
    """Stops from the session manifests, filtered by phone model (device) or phone folder name."""
    out = []
    for s in sessions:
        for r in manifest(s):
            if r['type'] != 'stop' or (device and r['device'] != device) or (phone and r['phone'] != phone):
                continue
            out.append({'session': s, 'floor': int(r['floor']), 'place': MERGE.get(r['node'], r['node']),
                        'device': r['device'], 'start': hk_epoch(r['start_hk']),
                        'rec': read_folder(session_dir(s) / 'clean' / r['folder'] / r['phone'], r['device'])})
    return out


def place_labels():
    """Readable names from the manifests, e.g. lt1a -> 'LT1A'."""
    return {MERGE.get(r['node'], r['node']): r['place'] for s in SESSIONS for r in manifest(s)
            if r['type'] == 'stop' and r['node'] not in MERGE}


def known_devices():
    return sorted({r['device'] for s in SESSIONS for r in manifest(s)})


# ============================================================================ session (one walker)
class Session:
    """Floor by pressure JUMPS between consecutive recordings, never by absolute pressure
    (weather moved floor-5 pressure by 0.46 hPa within one evening, PROCESS-LOG entry 11)."""

    def __init__(self, floor=5):
        self.floor, self.recent, self.last_t = floor, [], None   # recent = last pressures seen on this floor
        self.history, self.tally = [], Counter()

    def set_floor(self, floor):
        self.floor, self.recent = floor, []

    def track_floor(self, p_start, p_end, t_start=None, duration=0.0):
        """A floor change = pressure moves FLOOR_JUMP_HPA away from the median of the last
        REF_N readings on this floor (one odd reading, e.g. by a vent, can't flip the floor)."""
        note = ''
        if p_start is None:
            return 'no barometer in this recording: floor kept'
        if self.recent and t_start is not None and self.last_t is not None and t_start - self.last_t > LONG_GAP_S:
            note, self.recent = 'long gap since the last upload: floor kept (correct it if you changed floor)', []
        for p in (p_start, p_end):
            if self.recent:
                d = p - float(np.median(self.recent))
                if d > FLOOR_JUMP_HPA and self.floor == 5:
                    self.floor, self.recent, note = 4, [], f'pressure rose {d:.2f} hPa: moved down to 4F'
                elif d < -FLOOR_JUMP_HPA and self.floor == 4:
                    self.floor, self.recent, note = 5, [], f'pressure fell {-d:.2f} hPa: moved up to 5F'
            self.recent = (self.recent + [p])[-REF_N:]
        if t_start is not None:
            self.last_t = t_start + duration
        return note


def analyse(rec, session: Session, models: dict, kind='auto', truth=''):
    """Everything the result page shows for one upload."""
    mo = motion(rec)
    is_walk = kind == 'walk' or (kind == 'auto' and mo['cadence'] > WALK_CADENCE)
    p0, p1 = edge_pressure(rec)
    floor_before = session.floor
    note = session.track_floor(p0, p1, rec.get('start_epoch'), mo['duration_s'])
    res = {'device': rec.get('device', ''), 'kind': 'walk' if is_walk else 'stop', **mo,
           'pressure_hpa': None if p1 is None else round(p1, 2), 'floor_before': floor_before,
           'floor': session.floor, 'floor_note': note, 'top3': [], 'lit': None, 'model_note': '', 'truth': truth, 'correct': None}
    if not is_walk:
        model, res['model_note'] = pick_model(models, rec.get('device', ''))
        res['top3'] = model.top3(rec, session.floor) if model else []
        res['lit'] = res['top3'][0][0] if res['top3'] and res['top3'][0][1] >= LIGHT_P else None
        if truth and res['top3']:
            res['correct'] = res['top3'][0][0] == truth
            session.tally['stops'] += 1
            session.tally['correct'] += res['correct']
            session.tally['top3'] += truth in [p for p, _ in res['top3']]
    session.history.append(res)
    return res


def build_models():
    """One PlaceModel per phone model seen in the sessions, plus an all-phones fallback."""
    models = {d: PlaceModel(training_stops(device=d)) for d in known_devices()}
    models['*'] = PlaceModel(training_stops())
    return models


def pick_model(models, device):
    if device in models:
        return models[device], f'trained on this phone model ({device}), all sessions'
    # shortcut: unknown phones get the all-phones model; record a training session with that phone to fix it
    return models['*'], f'no training data for {device or "this phone"}: using all phones, expect low accuracy'


# ============================================================================ evaluation
def out_file(name):
    """out/<name>.json normally; out/<name>_<tag>.json when WALKSENSE_SESSIONS limits the sessions."""
    return OUT / (f'{name}_{TAG}.json' if TAG not in ('', 'all') else f'{name}.json')


def eval_folds(stops):
    """Leave-one-session-out folds. stops = {(session, phone): [stops]}. For each held-out session and phone:
    same_model = train on the other sessions where this phone MODEL was recorded (Tian's rule);
    cross_handset = train on the other sessions' stops of the same phone folder but a different model
    (e.g. iPhone17,4 has only 24 s2, so it can only be tested this way)."""
    for test in SESSIONS:
        for (s, phone), te in stops.items():
            if s != test or not te:
                continue
            dev = te[0]['device']
            others = [(o, stops[(o, phone)]) for o in SESSIONS if o != test and stops.get((o, phone))]
            for mode, keep in (('same_model', lambda d: d == dev), ('cross_handset', lambda d: d != dev)):
                tr = [(o, x) for o, x in others if keep(x[0]['device'])]
                if tr:
                    yield phone, mode, [o for o, _ in tr], [r for _, x in tr for r in x], te


def evaluate():
    """Leave one session out (visit level, true floor given), per phone folder and phone model."""
    OUT.mkdir(exist_ok=True)
    res = {'what': 'Leave one session out. Train on the other sessions\' stops (same phone model = same_model; a '
                   'different handset of the same phone = cross_handset), test every stop of the held-out session. '
                   'Visit answer = mean kNN probability over its 2 s windows, among places on the true floor.',
           'sessions': {s['name']: str(s['path'].relative_to(CLEAN.parent.parent)) for s in SESSION_LIST},
           'place': {}, 'floor_tracking': {}}
    stops = {(s, ph): training_stops(sessions=(s,), phone=ph) for s in SESSIONS for ph in ('iphone', 's24', 'a55', 'a56')}
    for phone, mode, tr_names, tr, te in eval_folds(stops):
        devs = f"{'+'.join(sorted({r['device'] for r in tr}))} -> {te[0]['device']}"
        for kind in ('tilt', 'xyz', 'magnitude'):
            m = PlaceModel(tr, kind)
            top1 = top3 = 0
            rows = []
            for st in te:
                t3 = m.top3(st['rec'], st['floor']) or [('', 0.0)]
                top1 += t3[0][0] == st['place']; top3 += st['place'] in [p for p, _ in t3]
                rows.append({'floor': st['floor'], 'truth': st['place'], 'guess': t3[0][0], 'p': t3[0][1]})
            n = len(te)
            res['place'][f"{phone} {'+'.join(tr_names)}->{te[0]['session']} {kind}"] = {
                'mode': mode, 'devices': devs, 'n_train_stops': len(tr), 'n_test_stops': n, 'top1': f'{top1}/{n}', 'top1_acc': round(top1 / n, 3),
                'top3': f'{top3}/{n}', 'top3_acc': round(top3 / n, 3),
                'chance_top1': round(float(np.mean([1 / len(m.places[r['floor']]) for r in rows if r['floor'] in m.places])), 3),
                **({'visits': rows} if kind == 'xyz' else {})}
    for s in SESSIONS:                       # floor tracker over each session's iPhone recordings in time order
        rows = sorted((r for r in manifest(s) if r['phone'] == 'iphone'), key=lambda r: hk_epoch(r['start_hk']))
        sess, ok, n = Session(floor=int(rows[0]['floor'])), 0, 0
        for r in rows:
            rec = read_folder(session_dir(s) / 'clean' / r['folder'] / r['phone'], r['device'])
            p0, p1 = edge_pressure(rec)
            sess.track_floor(p0, p1, hk_epoch(r['start_hk']), float(r['duration_s']))
            if r['type'] == 'stop':
                n += 1; ok += sess.floor == int(r['floor'])
        res['floor_tracking'][f'{s} iphone'] = {'stops_correct': f'{ok}/{n}', 'acc': round(ok / n, 3)}
    out_file('eval').write_text(json.dumps(res, indent=1))
    return res


if __name__ == '__main__':
    if sys.argv[1:] == ['evaluate']:
        r = evaluate()
        for k, v in r['place'].items():
            print(f"{k:36} {v['mode']:13} {v['devices']:28} top1 {v['top1']:>6}  top3 {v['top3']:>6}  chance {v['chance_top1']}")
        for k, v in r['floor_tracking'].items():
            print(f'floor tracking {k}: {v["stops_correct"]}')
    else:
        print(__doc__)
