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
NEW = HERE.parents[1] / 'new'        # v2 (entry 97) uses the shared code and data of phase2/new
sys.path.insert(0, str(NEW / 'tracking'))
import pdr                                   # noqa: E402  (also puts cross-day and the pilot on sys.path)
from pdr import count_steps, turns           # noqa: E402
from crossday import make_model              # noqa: E402
from sklearn.impute import SimpleImputer       # noqa: E402
from sklearn.neighbors import KNeighborsClassifier   # noqa: E402
from sklearn.pipeline import Pipeline          # noqa: E402
from sklearn.preprocessing import StandardScaler     # noqa: E402

DATA = NEW.parent / 'clean-data' / '2026-11-24'   # kept for ../smoothing/replay.py; new code uses session_dir()
CLEAN = NEW.parent / 'clean-data'
# Every session the app can train on: a name and the folder that holds its clean/ and raw/ folders.
ALL_SESSIONS = [{'name': 'sesi1', 'path': CLEAN / '2026-11-24' / 'sesi1'},
                {'name': 'sesi2', 'path': CLEAN / '2026-11-24' / 'sesi2'},
                {'name': '25nov', 'path': CLEAN / '2026-11-25'},
                # 25-Nov night run (PROCESS-LOG entry 72): Dicta iPhone19,2 + Chris SM-A566B together; Tian iPhone17,4 on his own
                {'name': '25night', 'path': CLEAN / '2026-11-25-night' / 'round'},
                {'name': '25night_tian', 'path': CLEAN / '2026-11-25-night' / 'tian'},
                # 26-Nov morning (PROCESS-LOG entry 74): Tian iPhone17,4 alone, labels from his chat captions
                {'name': '26tian', 'path': CLEAN / '2026-11-26-tian'},
                # 27-Nov evening (PROCESS-LOG entry 95): iPhone19,2 (iPhone 18 Pro), 11 stops, no walks
                {'name': '27nov', 'path': CLEAN / '2026-11-27'}]
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
# Floor rule (PROCESS-LOG entry 90). 'd' = the pre-registered winner of entry 74 (floor/PREREGISTRATION.md (d),
# floor/out/decision.json): the pressure rule R0 below, unchanged, while pressure is present and continuous; at a stop
# without pressure, and at the first VOTE_M stops with pressure after a gap > LONG_GAP_S, a magnetic floor vote (kNN on
# the stop's 2 s xyz windows, same phone model) is consulted, and VOTE_H confident (p >= VOTE_P) votes in a row for the
# other floor switch it. 'R0' = pressure only (the app before entry 90). WALKSENSE_FLOOR_RULE=R0 selects it.
FLOOR_RULES = ('d', 'R0')
FLOOR_RULE = os.environ.get('WALKSENSE_FLOOR_RULE', 'd')
if FLOOR_RULE not in FLOOR_RULES:
    raise SystemExit(f'WALKSENSE_FLOOR_RULE must be one of {FLOOR_RULES}')
VOTE_K, VOTE_P, VOTE_H, VOTE_M = 15, 0.7, 2, 3   # frozen on the tuning sessions (floor/out/params.json k_d, P, H, M)
# (d) treats this barometer as absent (PREREGISTRATION.md (d)): on 24 s1 its floor step is -0.014 hPa against a
# within-stop SD of 0.234-0.438 hPa (day3 README). R0 still uses it.
BARO_IGNORED = {'SM-S9280': 'S24 barometer too noisy for floors (PROCESS-LOG 74): floor from the magnetic vote'}
NO_BAROMETER = {'SM-A556E', 'SM-A566B'}           # a55 / a56: no pressure file in any session
# The pre-registered decision rule passed for the iPhone only (entry 74 with day-3 features and entry 90 with the app's
# own features): on phones without a (usable) barometer (d) was not better than "start floor kept" on the held-out a56
# (19 vs 19 of 32) and lost stops that rule gets right (25 spots S24: 3). So by default those phones keep R0 (for the S24
# that means its own pressure); WALKSENSE_FLOOR_VOTE_NO_BARO=1 turns the vote on for them too (full pre-registered (d)).
VOTE_NO_BARO = os.environ.get('WALKSENSE_FLOOR_VOTE_NO_BARO', '') == '1'
# (session, phone folder) never used to TRAIN the app's models (build_models, the evaluate folds and the floor vote).
# The data stays on disk and is still a test fold in evaluate.
TRAIN_EXCLUDE = {('25night', 'a56'): "Chris's a56 on the 25-Nov night: magnetometer hard-iron offset (about 85 uT off, "
                                     "drifting after 22:59); team decision option B, PROCESS-LOG 77 "
                                     "(clean-data/2026-11-25-night/field_check.csv)"}


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
    held flat facing the door (24-Nov protocol). tilt = (B along gravity, B across gravity).
    Cached in the rec dict (the eval folds reuse the same stops many times)."""
    cache = rec.setdefault('_features', {})
    if (kind, trim) not in cache:
        cache[(kind, trim)] = _stop_features(rec, kind, trim)
    return cache[(kind, trim)]


def _stop_features(rec, kind, trim):
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
class FloorVote:
    """Magnetic floor vote of rule (d) (PREREGISTRATION.md (a)): median imputer + scaler + kNN(VOTE_K, distance) on the
    xyz windows of the training stops, label = floor; a stop's vote = argmax of the mean probability over its windows.
    Entry 74 used the day-3 5 s windows; the app uses its own 2 s windows, first/last 5 s trimmed (entry 90)."""

    def __init__(self, stops, k=VOTE_K):
        X, y = [], []
        for s in stops:
            f = stop_features(s['rec'], 'xyz')
            if len(f):
                X.append(f); y += [s['floor']] * len(f)
        self.model = None
        if y:
            self.model = Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler()),
                                   ('clf', KNeighborsClassifier(n_neighbors=min(k, len(y)), weights='distance'))]).fit(np.vstack(X), y)

    def vote(self, rec, trim=TRIM_S):
        """(floor, probability) or None (no model or no usable window)."""
        if self.model is None:
            return None
        f = stop_features(rec, 'xyz', trim)
        if not len(f):
            return None
        p = self.model.predict_proba(f).mean(0)
        j = int(np.argmax(p))
        return int(self.model.classes_[j]), float(p[j])


class PlaceModel:
    """Magnetic kNN per floor, trained on the stops of one phone model (plus the floor vote of rule (d) on xyz)."""

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
        self.floor_vote = FloorVote(stops) if kind == 'xyz' else None

    def vote_floor(self, rec, trim=TRIM_S):
        return self.floor_vote.vote(rec, trim) if self.floor_vote is not None else None

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


def training_stops(device=None, sessions=SESSIONS, phone=None, exclude=()):
    """Stops from the session manifests, filtered by phone model (device) or phone folder name.
    exclude = (session, phone folder) pairs to leave out (the app passes TRAIN_EXCLUDE)."""
    out = []
    for s in sessions:
        for r in manifest(s):
            if r['type'] != 'stop' or (device and r['device'] != device) or (phone and r['phone'] != phone) \
                    or (s, r['phone']) in exclude:
                continue
            folder = session_dir(s) / 'clean' / r['folder'] / r['phone']
            rec = read_folder(folder, r['device'])
            if 'mag' not in rec:                     # PROCESS-LOG 81: the cleaned sensor CSVs are gitignored
                raise RuntimeError(f'{folder} has no Magnetometer.csv: the cleaned sensor CSVs are not built in this tree. '
                                   'Run phase2/clean-data/2026-11-25-night/scripts/build_night.py and '
                                   'phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py first (upload README, "Run it")')
            out.append({'session': s, 'floor': int(r['floor']), 'place': MERGE.get(r['node'], r['node']),
                        'device': r['device'], 'start': hk_epoch(r['start_hk']), 'rec': rec})
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
    (weather moved floor-5 pressure by 0.46 hPa within one evening, PROCESS-LOG entry 11).
    rule 'd' (default, FLOOR_RULE) adds the magnetic floor vote where pressure is missing or follows a long gap;
    track_floor itself is R0 and stays unchanged (floor/rules.py reproduces R0 and (d) from it)."""

    def __init__(self, floor=5, rule=None):
        self.floor, self.recent, self.last_t = floor, [], None   # recent = last pressures seen on this floor
        self.history, self.tally = [], Counter()
        self.rule = rule or FLOOR_RULE
        self.streak_f, self.streak, self.consult_left = None, 0, 0   # (d): confident votes in a row, stops left to ask
        self.vote_pending, self._vote_p = False, None

    def set_floor(self, floor):
        self.floor, self.recent, self.streak = floor, [], 0

    def update_floor(self, p_start, p_end, t_start=None, duration=0.0, is_stop=True, vote=None, rule=None):
        """One recording under rule (default self.rule). vote = (floor, p), a callable returning it, or None.
        Returns the note."""
        note = self.pressure_step(p_start, p_end, t_start, duration, is_stop, rule)
        if self.vote_pending and vote is not None:
            v = vote() if callable(vote) else vote
            if v is not None:
                note = self.apply_vote(*v) or note
        return note

    def pressure_step(self, p_start, p_end, t_start=None, duration=0.0, is_stop=True, rule=None):
        """R0 (track_floor); under rule 'd' also decide whether this recording asks the magnetic vote
        (floor/rules.py comb, step for step): it does at a stop without pressure, and at the first VOTE_M stops
        with pressure after a gap > LONG_GAP_S since the last pressure reading. A pressure floor change ends that."""
        if (rule or self.rule) != 'd':
            self.vote_pending = False
            return self.track_floor(p_start, p_end, t_start, duration)
        has_p = p_start is not None
        if has_p and self.last_t is not None and t_start is not None and t_start - self.last_t > LONG_GAP_S:
            self.consult_left = VOTE_M
        before = self.floor
        note = self.track_floor(p_start, p_end, t_start, duration)
        if self.floor != before:                     # pressure saw a floor change: trust it
            self.streak, self.consult_left = 0, 0
        self.vote_pending = is_stop and (not has_p or self.consult_left > 0)
        self._vote_p = (p_start, p_end) if has_p else None
        if has_p and is_stop and self.consult_left > 0:
            self.consult_left -= 1
        return note

    def apply_vote(self, floor, p):
        """The magnetic vote of the stop pressure_step marked; VOTE_H confident votes in a row switch the floor."""
        if not self.vote_pending:
            return ''
        self.vote_pending = False
        if p < VOTE_P:
            return ''
        if floor == self.floor:                      # a confident vote for the current floor resets the count
            self.streak = 0
            return ''
        self.streak = self.streak + 1 if self.streak_f == floor else 1
        self.streak_f = floor
        if self.streak < VOTE_H:
            return f'magnetic floor vote says {floor}F (p {p:.2f}), {self.streak} of {VOTE_H} in a row: floor kept'
        self.set_floor(floor)
        if self._vote_p is not None:                 # the pressure reference restarts from this recording
            self.recent = list(self._vote_p)
        self.consult_left = 0
        return f'magnetic floor vote: {VOTE_H} confident votes in a row for {floor}F (p {p:.2f}): moved to {floor}F'

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
    model, model_note = pick_model(models, rec.get('device', ''))
    rule = floor_rule_for(rec.get('device', ''), session.rule)
    fp0, fp1 = floor_pressure(rec, rule, (p0, p1))
    note = session.update_floor(fp0, fp1, rec.get('start_epoch'), mo['duration_s'], is_stop=not is_walk,
                                vote=lambda: model.vote_floor(rec) if model else None, rule=rule)
    if fp0 is None and p0 is not None and not note.startswith('magnetic'):
        note = BARO_IGNORED[rec.get('device', '')]
    res = {'device': rec.get('device', ''), 'kind': 'walk' if is_walk else 'stop', **mo,
           'pressure_hpa': None if p1 is None else round(p1, 2), 'floor_before': floor_before,
           'floor': session.floor, 'floor_note': note, 'top3': [], 'lit': None, 'model_note': '', 'truth': truth, 'correct': None}
    if not is_walk:
        res['model_note'] = model_note
        res['top3'] = model.top3(rec, session.floor) if model else []
        res['lit'] = res['top3'][0][0] if res['top3'] and res['top3'][0][1] >= LIGHT_P else None
        if truth and res['top3']:
            res['correct'] = res['top3'][0][0] == truth
            session.tally['stops'] += 1
            session.tally['correct'] += res['correct']
            session.tally['top3'] += truth in [p for p, _ in res['top3']]
    session.history.append(res)
    return res


def floor_rule_for(device, rule=None):
    """The rule the app uses for this phone model: rule (default FLOOR_RULE), but R0 for phones without a usable
    barometer unless VOTE_NO_BARO."""
    rule = rule or FLOOR_RULE
    if rule == 'd' and device in (NO_BAROMETER | set(BARO_IGNORED)) and not VOTE_NO_BARO:
        return 'R0'
    return rule


def floor_pressure(rec, rule=None, edges=None):
    """Edge pressures the floor rule may use: (None, None) for a BARO_IGNORED phone under rule 'd'."""
    p0, p1 = edges if edges is not None else edge_pressure(rec)
    if (rule or FLOOR_RULE) == 'd' and rec.get('device', '') in BARO_IGNORED:
        return None, None
    return p0, p1


def build_models():
    """One PlaceModel per phone model seen in the sessions, plus an all-phones fallback (TRAIN_EXCLUDE left out)."""
    models = {d: PlaceModel(training_stops(device=d, exclude=TRAIN_EXCLUDE)) for d in known_devices()}
    models['*'] = PlaceModel(training_stops(exclude=TRAIN_EXCLUDE))
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
    (e.g. iPhone17,4 has only 24 s2, so it can only be tested this way). TRAIN_EXCLUDE units are tested, never trained on."""
    for test in SESSIONS:
        for (s, phone), te in stops.items():
            if s != test or not te:
                continue
            dev = te[0]['device']
            others = [(o, stops[(o, phone)]) for o in SESSIONS if o != test and stops.get((o, phone))
                      and (o, phone) not in TRAIN_EXCLUDE]
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
    res['floor_rule'] = {'rule': FLOOR_RULE, 'rules': {'R0': 'pressure only: 0.40 hPa from the median of the last 6 readings, '
                         'reference emptied after a 15-min gap, no pressure = floor kept', 'd': 'R0 while pressure is present and '
                         f'continuous; magnetic floor vote (k {VOTE_K}, 2 s xyz windows, same phone model, other sessions) at stops '
                         f'without pressure and the first {VOTE_M} stops after a gap; {VOTE_H} votes with p >= {VOTE_P} in a row '
                         f'switch; barometer ignored for {sorted(BARO_IGNORED)}',
                         'app_default': f'what the app does by default: {FLOOR_RULE} for phones with a barometer, '
                                        + ('d' if VOTE_NO_BARO else 'R0') + f' for {sorted(NO_BAROMETER | set(BARO_IGNORED))} '
                                        '(WALKSENSE_FLOOR_VOTE_NO_BARO=1 gives them d)'},
                         'train_exclude': {f'{s} {ph}': why for (s, ph), why in TRAIN_EXCLUDE.items()},
                         'floor_tracking': f'iPhone stops under the app default ({FLOOR_RULE}); floor_tracking_by_rule has every '
                                           'phone, R0, d (pre-registered, every phone) and app_default, stops and walks; '
                                           'every unit starts on its true first floor'}
    res['floor_tracking_by_rule'] = floor_eval(stops)
    for s in SESSIONS:                       # floor tracker over each session's iPhone recordings in time order
        u = res['floor_tracking_by_rule'][f'{s} iphone']
        r = u['app_default']
        ok, n = (int(x) for x in r['stops'].split('/'))
        res['floor_tracking'][f'{s} iphone'] = {'stops_correct': r['stops'], 'acc': round(ok / n, 3), 'rule': r['rule']}
    out_file('eval').write_text(json.dumps(res, indent=1))
    return res


def floor_votes(stops, test, device):
    """FloorVote for one held-out session and phone model: the other sessions' stops of that model (TRAIN_EXCLUDE
    left out); all models if there are none (PREREGISTRATION.md (a) pool rule)."""
    pool = [x for (o, ph), xs in stops.items() if o != test and (o, ph) not in TRAIN_EXCLUDE for x in xs]
    same = [x for x in pool if x['device'] == device]
    return FloorVote(same or pool), ('same model' if same else 'all models')


def floor_eval(stops):
    """Both floor rules over every session x phone folder, recordings in time order, start on the true first floor."""
    out = {}
    for s in SESSIONS:
        for ph in ('iphone', 's24', 'a55', 'a56'):
            rows = sorted((r for r in manifest(s) if r['phone'] == ph), key=lambda r: hk_epoch(r['start_hk']))
            if not rows:
                continue
            dev = rows[0]['device']
            fv, pool = floor_votes(stops, s, dev)
            recs = [read_folder(session_dir(s) / 'clean' / r['folder'] / ph, r['device']) for r in rows]
            unit = {'device': dev, 'vote_pool': pool, 'pressure_recordings': f"{sum(edge_pressure(x)[0] is not None for x in recs)}/{len(recs)}"}
            for key, rule in (('R0', 'R0'), ('d', 'd'), ('app_default', floor_rule_for(dev))):
                sess, wrong = Session(floor=int(rows[0]['floor']), rule=rule), []
                ok = {'stop': 0, 'walk': 0}; n = {'stop': 0, 'walk': 0}
                for r, rec in zip(rows, recs):
                    stop = r['type'] == 'stop'
                    p0, p1 = floor_pressure(rec, rule)
                    note = sess.update_floor(p0, p1, hk_epoch(r['start_hk']), float(r['duration_s']), is_stop=stop,
                                             vote=(lambda rec=rec: fv.vote(rec)) if stop else None)
                    n[r['type']] += 1; ok[r['type']] += sess.floor == int(r['floor'])
                    if stop and sess.floor != int(r['floor']):
                        wrong.append(f"{r['start_hk'][:5]} {r['node']} true {r['floor']}F shown {sess.floor}F")
                unit[key] = {'rule': rule, 'stops': f"{ok['stop']}/{n['stop']}", 'walks': f"{ok['walk']}/{n['walk']}",
                             'wrong_stops': wrong}
            out[f'{s} {ph}'] = unit
    return out


if __name__ == '__main__':
    if sys.argv[1:] == ['evaluate']:
        r = evaluate()
        for k, v in r['place'].items():
            print(f"{k:36} {v['mode']:13} {v['devices']:28} top1 {v['top1']:>6}  top3 {v['top3']:>6}  chance {v['chance_top1']}")
        for k, v in r['floor_tracking'].items():
            print(f'floor tracking {k}: {v["stops_correct"]}')
    else:
        print(__doc__)
