"""Floor rules. Each takes one session+slot's recordings (floorlib.recordings() rows, time order) and returns the
floor it shows for every recording. Rules R0/R1 are the current ones (reproduced, not changed); the candidates
are the ones pre-registered in PREREGISTRATION.md (written and committed before any candidate was scored)."""
from __future__ import annotations

import numpy as np

import floorlib as fl

ws = fl.ws
d3 = fl.d3
INF = float('inf')


def _p(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


# ----------------------------------------------------------------------------- R0: upload app (walksense.py)
def r0(rows, start_floor, long_gap_s=ws.LONG_GAP_S, use_pressure=True):
    """walksense.Session.track_floor on every recording (stops and walks), unchanged; long_gap_s only for c1."""
    sess = ws.Session(floor=start_floor)
    out = []
    old = ws.LONG_GAP_S
    ws.LONG_GAP_S = long_gap_s            # c1 varies the gap; R0 = the app's 15 min
    try:
        for r in rows.itertuples():
            p0, p1 = (_p(r.p0), _p(r.p1)) if use_pressure else (None, None)
            sess.track_floor(p0, p1, r.start, r.dur)
            out.append(sess.floor)
    finally:
        ws.LONG_GAP_S = old
    return np.array(out)


# ----------------------------------------------------------------------------- R1: day-3 step tracking
def r1_threshold(V, sid, slot):
    """evaluate.floor_eval: half the median |pressure step| at floor changes, over the other sessions' tracks."""
    col = f'hpa_{slot}'
    V = V.assign(session=V['track'])
    steps = []
    for o, w in V.groupby('session'):
        if o.split(':')[0] == sid or w[col].notna().sum() < 2:
            continue
        w = w.sort_values('start')
        pp, ff = w[col].to_numpy(), w['floor'].to_numpy()
        steps += list(np.abs(np.diff(pp))[np.diff(ff) != 0])
    return float(np.nanmedian(steps)) / 2


def r1(rows, start_floor, thr):
    """data.track_floor over the slot's stops (stop median pressure); walks show the floor of the last stop."""
    stops = rows['type'].to_numpy() == 'stop'
    h = np.array([np.nan if _p(x) is None else x for x in rows['pmed']], float)[stops]
    trk = d3.track_floor(h, thr, start_floor=start_floor)
    out, cur, j = [], start_floor, 0
    for s in stops:
        if s:
            cur = int(trk[j]); j += 1
        out.append(cur)
    return np.array(out)


# ----------------------------------------------------------------------------- (a) magnetic floor vote
XYZ = ['x_mean', 'y_mean', 'z_mean']
_VOTES = {}


def mag_votes(test_sid, device, k, pool):
    """{window key -> (floor, prob)} for every stop recording of test_sid, trained on the other sessions in `pool`,
    same device model (all models if that model has no window in the pool). PREREGISTRATION.md (a)."""
    ck = (test_sid, device, k, tuple(pool))
    if ck in _VOTES:
        return _VOTES[ck]
    from sklearn.impute import SimpleImputer
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    W = fl.day3()['W']
    tr = W[(W['session'] != test_sid) & W['session'].isin(pool)]
    same = tr[tr['device'] == device]
    tr = same if len(same) else tr
    m = Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler()),
                  ('clf', KNeighborsClassifier(n_neighbors=min(k, len(tr)), weights='distance'))])
    m.fit(tr[XYZ].to_numpy(), tr['floor'].to_numpy())
    te = W[(W['session'] == test_sid) & (W['device'] == device)]
    out = {}
    if len(te):
        P = m.predict_proba(te[XYZ].to_numpy())
        cls = m.classes_
        for key, idx in te.groupby('key').indices.items():
            p = P[idx].mean(0)
            j = int(np.argmax(p))
            out[key] = (int(cls[j]), float(p[j]))
    _VOTES[ck] = (out, 'same model' if len(same) else 'all models')
    return _VOTES[ck]


def mag(rows, start_floor, votes):
    out, cur = [], start_floor
    for r in rows.itertuples():
        if r.type == 'stop' and r.key in votes:
            cur = votes[r.key][0]
        out.append(cur)
    return np.array(out)


# ----------------------------------------------------------------------------- (c2) drift-extrapolated reference
def c2(rows, start_floor, jump=0.40, ref_n=6, slope_win_s=1800, min_span_s=600, max_slope_h=1.0):
    F, L, out = start_floor, [], []          # L = (t, p) readings on the current floor, never emptied on a gap
    for r in rows.itertuples():
        p0, p1 = _p(r.p0), _p(r.p1)
        if p0 is not None:
            for t, p in ((r.start, p0), (r.start + r.dur, p1)):
                if L:
                    last = L[-ref_n:]
                    ref, tref = float(np.median([x[1] for x in last])), float(np.median([x[0] for x in last]))
                    win = [x for x in L if x[0] >= L[-1][0] - slope_win_s]
                    slope = 0.0
                    if len(win) >= 2 and win[-1][0] - win[0][0] >= min_span_s:
                        tt, pp = np.array(win, float).T
                        slope = float(np.clip(np.polyfit(tt, pp, 1)[0], -max_slope_h / 3600, max_slope_h / 3600))
                    d = p - (ref + slope * (t - tref))
                    if d > jump and F == 5:
                        F, L = 4, []
                    elif d < -jump and F == 4:
                        F, L = 5, []
                L.append((t, p))
        out.append(F)
    return np.array(out)


# ----------------------------------------------------------------------------- (d) pressure + magnetic vote, hysteresis
def comb(rows, start_floor, votes, P, H, M, use_pressure=True, long_gap_s=ws.LONG_GAP_S):
    sess = ws.Session(floor=start_floor)
    streak_f, streak, consult_left, out = None, 0, 0, []
    for r in rows.itertuples():
        p0, p1 = (_p(r.p0), _p(r.p1)) if use_pressure else (None, None)
        has_p = p0 is not None
        if has_p:
            if sess.last_t is not None and r.start - sess.last_t > long_gap_s:
                consult_left = M
            before = sess.floor
            sess.track_floor(p0, p1, r.start, r.dur)
            if sess.floor != before:                 # pressure saw a floor change: trust it
                streak, consult_left = 0, 0
        consult = (not has_p) or consult_left > 0
        if r.type == 'stop' and consult and r.key in votes:
            f, pf = votes[r.key]
            if pf >= P and f != sess.floor:
                streak = streak + 1 if streak_f == f else 1
                streak_f = f
                if streak >= H:
                    sess.set_floor(f)
                    if has_p:
                        sess.recent = [p0, p1]
                    streak, consult_left = 0, 0
            elif pf >= P:
                streak = 0
        if has_p and r.type == 'stop' and consult_left > 0:
            consult_left -= 1
        out.append(sess.floor)
    return np.array(out)
