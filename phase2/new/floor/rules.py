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
