#!/usr/bin/env python3
"""Tune and compare the continuous place estimate (smooth.py) on the recorded 24-Nov sessions.

  python phase2/new/smoothing/tune.py   # ~10 min on 20 cores -> out/live_smoothing.json, .csv, figures

Offline analysis only (not wired into the app). Each session's iPhone recordings are streamed through
Tian's LiveTracker (../upload/live.py, unchanged; see replay.py) on their real clock (as in `live.py check`), with the place model of the OTHER session's iPhone (held out; also a different
handset: sesi1 = iPhone19,2 / ip18, sesi2 = iPhone17,4 / ip16). The replay logs, per tick, what the
tracker knew (floor, still/moving, tilt, steps, Tian's 3-s answer). The kNN probabilities for every
window W / pre-filter / calibration are then computed from the same stream with the same
smooth.window_feature() the tracker calls, and every estimator setting is run over them with the
classes in smooth.py (FIR/EMA are vectorised here and checked against smooth.Continuous).

Selection rule (written in PROCESS-LOG entry 60 before any result was computed):
  standing part of a stop = from 5 s after the stop recording starts to 5 s before it ends;
  the first stop of each stream is never scored (the 'start' calibration uses it).
  best = highest per-tick top-1 over the standing ticks, among settings with
         standing flips <= 1.0 per minute AND median lock time <= 5.0 s
         (lock time = from the stop's start until the shown place is right and stays right for 5 s;
         a stop that never locks counts as infinite);
  ties (top-1 equal to 0.1 percentage point) -> lower median lock time -> fewer flips ->
         simpler (none < ema < fir < guard < hmm; fewer taps) -> tick 0.5 before 1.0;
  if no setting is feasible: the setting with the fewest flips, then the same tie-breaks.
  Nested leave-one-session-out: choose on one stream, score on the other, both directions.
  Abstain threshold: on the chosen setting, the highest coverage with precision >= 0.80 on the tune
  stream (none reaches it: the highest precision); scored on the other stream.
"""
from __future__ import annotations

import csv
import itertools
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay          # noqa: E402  (puts ../upload on sys.path; Tian's files are imported unchanged)
import route           # noqa: E402
import smooth          # noqa: E402
import walksense as ws  # noqa: E402

STREAMS = {'sesi1': {'device': 'iPhone17,4', 'train': 'sesi2'}, 'sesi2': {'device': 'iPhone19,2', 'train': 'sesi1'}}
TICKS = (0.5, 1.0)
WINDOWS = (1.0, 2.0, 3.0)
PREFILTERS = (False, True)
CALIBS = ('none', 'start', 'median')
ALPHAS = tuple(round(a, 1) for a in np.arange(0.1, 1.0, 0.1))
GUARDS = (0, 2, 3, 4)
BETAS, EPSS, STAYS = (0.25, 0.5, 1.0, 2.0), (0.001, 0.01, 0.05), (0.9, 0.98, 0.995)
ABSTAIN = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
TRIM = 5.0
MAX_FLIPS, MAX_LOCK, LOCK_HOLD, PREC = 1.0, 5.0, 5.0, 0.80
SIMPLE = {'none': 0, 'ema': 1, 'fir': 2, 'guard': 3, 'hmm': 4}
OUT = HERE / 'out'
OUT_JSON, OUT_CSV = OUT / 'live_smoothing.json', OUT / 'live_smoothing.csv'


def fir_weights():
    """Non-increasing weights in steps of 0.1 summing to 1 with 2..6 taps (partitions of 10)."""
    out = []
    def parts(n, k, mx):
        if n == 0:
            yield ()
            return
        if k == 0:
            return
        for x in range(min(n, mx), 0, -1):
            for rest in parts(n - x, k - 1, x):
                yield (x,) + rest
    for p in parts(10, 6, 10):
        if len(p) >= 2:
            out.append(tuple(x / 10 for x in p))
    return out


# ============================================================================ replay
def replay_ticks(session, tick, models, graph):
    """Stream the session through Tian's LiveTracker (ContTracker, method none) and log every tick."""
    return replay.replay(session, smooth.Config(tick=tick, method='none'), models, graph, STREAMS[session]['device'])


# ============================================================================ features -> probabilities
def train_windows(device):
    """Training feature windows (x/y/z, 2 s) per place of a phone model's stops, as PlaceModel uses them."""
    out = {}
    for s in ws.training_stops(device=device):
        out.setdefault((s['floor'], s['place']), []).append(ws.stop_features(s['rec'], 'xyz'))
    return {k: np.vstack(v) for k, v in out.items()}


def prob_series(stream, segs, rows, model, W, pf, calib, trainwin):
    """Per tick: (floor, classes, p or None) for one window / pre-filter / calibration."""
    mag, acc = stream['mag'], stream['acc']
    feats = [smooth.window_feature(mag, r['t'], W, pf) for r in rows]
    shift = [np.zeros(3)] * len(rows)
    if calib == 'start':                      # known first place: offset from 10 s of the first stop
        s0 = next(g for g in segs if g['type'] == 'stop')
        m = mag[(mag[:, 0] >= s0['t0'] + TRIM) & (mag[:, 0] < s0['t0'] + TRIM + 10), 1:4].mean(0)
        shift = [trainwin[(s0['floor'], s0['place'])].mean(0) - m] * len(rows)
    elif calib == 'median':                   # per-phone median: training median - running median of still+flat ticks so far
        mtr = np.median(np.vstack(list(trainwin.values())), axis=0)
        seen, shift = [], []
        for r, f in zip(rows, feats):
            if f is not None and smooth.gate_open('still_flat', r['still'], r['tilt']):
                seen.append(f)
            shift.append(mtr - np.median(seen, axis=0) if len(seen) >= 20 else np.zeros(3))
    out = []
    by_floor = {}
    for i, (r, f) in enumerate(zip(rows, feats)):
        if f is not None and r['floor'] in model.models:
            by_floor.setdefault(r['floor'], []).append(i)
    P = [None] * len(rows)
    for fl, ii in by_floor.items():
        X = np.array([feats[i] + shift[i] for i in ii])
        pr = model.models[fl].predict_proba(X)
        for i, p in zip(ii, pr):
            P[i] = p
    for r, p in zip(rows, P):
        m = model.models.get(r['floor'])
        out.append((r['floor'], list(m.classes_) if m is not None else [], p))
    return out


# ============================================================================ estimators over a series
def run_linear(series, gate_ok, weights=None, alpha=None):
    """Vectorised Linear over floor runs: returns list of s vectors (or None)."""
    n = len(series)
    S = [None] * n
    i = 0
    while i < n:
        fl = series[i][0]
        j = i
        while j < n and series[j][0] == fl:
            j += 1
        use = [k for k in range(i, j) if series[k][2] is not None and gate_ok[k]]
        if use:
            X = np.array([series[k][2] for k in use])
            if alpha is not None:
                Y = lfilter([alpha], [1, -(1 - alpha)], X, axis=0, zi=((1 - alpha) * X[:1]))[0]
            else:
                w = np.asarray(weights, float)
                Y = np.zeros_like(X); Z = np.zeros(len(X))
                for lag, wl in enumerate(w):
                    if lag:
                        Y[lag:] += wl * X[:-lag]; Z[lag:] += wl
                    else:
                        Y += wl * X; Z += wl
                Y = Y / Z[:, None]
            last, q = None, 0
            for k in range(i, j):
                while q < len(use) and use[q] <= k:
                    last = Y[q]; q += 1
                S[k] = last
        i = j
    return S


def run_hmm(series, gate_ok, dsteps, adj, steps, beta, eps, p_stay):
    n, S, est, fl, cls = len(series), [None] * len(series), None, None, None
    for k in range(n):
        f, c, p = series[k]
        if f != fl or c != cls:
            fl, cls = f, c
            est = smooth.HMM(c, adj.get(f, {}), steps.get(f, {}), beta, eps, p_stay) if c else None
        if est is not None:
            S[k] = est.step(p if gate_ok[k] else None, dsteps[k])
    return S


def display(series, S, guard, adj):
    """Shown place, its probability and top-3 per tick (guard via smooth.Guard)."""
    places, probs, top3 = [], np.zeros(len(S)), []
    g, fl = None, None
    for k, (f, c, _) in enumerate(series):
        if f != fl:
            fl = f
            g = smooth.Guard(guard, adj.get(f, {})) if guard else None
        s = S[k]
        if s is None:
            places.append(None); top3.append(()); continue
        order = np.argsort(-s, kind='stable')
        top = c[order[0]]
        pl = g.step(top) if g else top
        places.append(pl); probs[k] = s[c.index(pl)]
        top3.append(tuple(c[i] for i in order[:3]))
    return places, probs, top3


# ============================================================================ metrics
def scorer(segs, rows, tick):
    """Index arrays for scoring one stream on one tick grid."""
    t = np.array([r['t'] for r in rows])
    stops = [g for g in segs if g['type'] == 'stop'][1:]                 # first stop never scored
    walks = [g for g in segs if g['type'] == 'walk']
    return {'t': t, 'tick': tick, 'moving': np.array([r['moving'] for r in rows]),
            'stops': [(g, np.where((t >= g['t0']) & (t <= g['t1']))[0]) for g in stops],
            'walks': [(g, np.where((t >= g['t0']) & (t <= g['t1']))[0]) for g in walks]}


def metrics(sc, places, top3, lit):
    t, tick = sc['t'], sc['tick']
    n_st = ok1 = ok3 = flips = wl_ticks = wl_events = lit_events = 0
    locks, firsts = [], []
    for g, ii in sc['stops']:
        truth = g['place']
        stand = ii[(t[ii] >= g['t0'] + TRIM) & (t[ii] <= g['t1'] - TRIM)]
        c = np.array([places[i] == truth for i in ii], bool)
        for a, i in enumerate(stand):
            n_st += 1; ok1 += places[i] == truth; ok3 += truth in top3[i]
            if a and places[i] != places[stand[a - 1]]:
                flips += 1
            wl_ticks += lit[i] is not None and lit[i] != truth
        prev = None
        for i in ii:
            if lit[i] is not None and lit[i] != prev:
                lit_events += 1; wl_events += lit[i] != truth
            prev = lit[i]
        tt = t[ii]
        first = next((tt[a] - g['t0'] for a in range(len(ii)) if c[a]), np.inf)
        lock = np.inf
        for a in range(len(ii)):
            if c[a]:
                hold = (tt >= tt[a]) & (tt <= min(tt[a] + LOCK_HOLD, g['t1']))
                if c[hold].all():
                    lock = tt[a] - g['t0']; break
        firsts.append(first); locks.append(lock)
    n_w = on = wflips = wlit = 0
    for g, ii in sc['walks']:
        ok = {g['from'], g['to']}
        for a, i in enumerate(ii):
            n_w += 1; on += places[i] in ok
            if a and places[i] != places[ii[a - 1]]:
                wflips += 1
            if lit[i] is not None and lit[i] not in ok and (a == 0 or lit[ii[a - 1]] != lit[i]):
                wlit += 1
    return {'n_stand_ticks': n_st, 'ok1': ok1, 'ok3': ok3, 'flips': flips, 'stand_min': n_st * tick / 60,
            'wrong_lit_ticks': wl_ticks, 'lit_events': lit_events, 'wrong_lit_events': wl_events,
            'locks': locks, 'firsts': firsts, 'n_walk_ticks': n_w, 'walk_on': on, 'walk_flips': wflips,
            'walk_min': n_w * tick / 60, 'walk_wrong_lits': wlit, 'n_stops': len(sc['stops'])}


def summary(m):
    lk, fs = np.array(m['locks']), np.array(m['firsts'])
    fin = lambda x: None if not np.isfinite(x) else float(x)
    return {'top1': round(m['ok1'] / max(m['n_stand_ticks'], 1), 4), 'top3': round(m['ok3'] / max(m['n_stand_ticks'], 1), 4),
            'flips_per_min': round(m['flips'] / max(m['stand_min'], 1e-9), 3),
            'lock_median_s': fin(np.median(lk)) if len(lk) else None, 'locked_stops': int(np.isfinite(lk).sum()),
            'first_correct_median_s': fin(np.median(fs)) if len(fs) else None, 'ever_correct_stops': int(np.isfinite(fs).sum()),
            'n_stops': m['n_stops'], 'lit_events': m['lit_events'], 'wrong_lit_events': m['wrong_lit_events'],
            'wrong_lit_tick_share': round(m['wrong_lit_ticks'] / max(m['n_stand_ticks'], 1), 4),
            'walk_on_corridor': round(m['walk_on'] / max(m['n_walk_ticks'], 1), 4),
            'walk_flips_per_min': round(m['walk_flips'] / max(m['walk_min'], 1e-9), 3), 'walk_wrong_lits': m['walk_wrong_lits'],
            'n_stand_ticks': m['n_stand_ticks']}


def pooled(ms):
    out = {k: sum(m[k] for m in ms) for k in ms[0] if not isinstance(ms[0][k], list)}
    out['locks'] = sum((m['locks'] for m in ms), []); out['firsts'] = sum((m['firsts'] for m in ms), [])
    return out


def sort_key(cfg, s):
    lock = s['lock_median_s'] if s['lock_median_s'] is not None else np.inf
    fam = 'guard' if cfg['guard'] else cfg['method']
    return (-round(s['top1'] * 1000), lock, s['flips_per_min'], SIMPLE[fam], len(cfg['weights']) if cfg['method'] == 'fir' else 0,
            cfg['tick'])


def select(cands):
    """cands: list of (cfg dict, summary) -> the chosen one by the rule in the docstring."""
    feas = [c for c in cands if c[1]['flips_per_min'] <= MAX_FLIPS and c[1]['lock_median_s'] is not None and c[1]['lock_median_s'] <= MAX_LOCK]
    if feas:
        return min(feas, key=lambda c: sort_key(*c)), True
    return min(cands, key=lambda c: (c[1]['flips_per_min'],) + sort_key(*c)), False


# ============================================================================ the search
G = {}


def estimator_grid():
    lin = [('none', {})] + [('ema', {'alpha': a}) for a in ALPHAS] + [('fir', {'weights': w}) for w in fir_weights()]
    out = []
    for gate in smooth.GATES:
        for (meth, kw), guard in itertools.product(lin, GUARDS):
            out.append({'method': meth, 'guard': guard, 'gate': gate, **kw})
        for b, e, s in itertools.product(BETAS, EPSS, STAYS):
            out.append({'method': 'hmm', 'guard': 0, 'gate': gate, 'beta': b, 'eps': e, 'p_stay': s})
    return out


def evaluate_series(job):
    """All estimators for one (session, tick, window, pre-filter, calibration)."""
    session, tick, W, pf, calib = job
    d = G[(session, tick)]
    series = prob_series(d['stream'], d['segs'], d['rows'], G['models'][STREAMS[session]['device']], W, pf, calib,
                         G['trainwin'][STREAMS[session]['device']])
    rows, sc = d['rows'], d['scorer']
    adj, steps = G['adj'][session]
    gates = {g: [smooth.gate_open(g, r['still'], r['tilt']) for r in rows] for g in smooth.GATES}
    dsteps = [r['dsteps'] for r in rows]
    out, cache = [], {}
    for e in estimator_grid():
        key = (e['method'], e.get('alpha'), e.get('weights'), e.get('beta'), e.get('eps'), e.get('p_stay'), e['gate'])
        if key not in cache:
            if e['method'] == 'hmm':
                cache[key] = run_hmm(series, gates[e['gate']], dsteps, adj, steps, e['beta'], e['eps'], e['p_stay'])
            else:
                cache[key] = run_linear(series, gates[e['gate']], e.get('weights', (1.0,)) if e['method'] != 'ema' else None,
                                        e.get('alpha') if e['method'] == 'ema' else None)
        S = cache[key]
        places, probs, top3 = display(series, S, e['guard'], adj)
        lit = [p if (p is not None and not r['moving'] and pr >= ws.LIGHT_P) else None for p, pr, r in zip(places, probs, rows)]
        cfg = smooth.Config(tick=tick, window=W, prefilter=pf, **e).as_dict()
        cfg['calib'] = calib
        m = metrics(sc, places, top3, lit)
        out.append((cfg, m))
    return session, out


def run_cfg(session, cfg):
    """Shown place / probability / top-3 per tick for one setting (as in evaluate_series)."""
    d = G[(session, cfg['tick'])]
    series = prob_series(d['stream'], d['segs'], d['rows'], G['models'][STREAMS[session]['device']], cfg['window'],
                         cfg['prefilter'], cfg['calib'], G['trainwin'][STREAMS[session]['device']])
    rows = d['rows']
    adj, steps = G['adj'][session]
    gate = [smooth.gate_open(cfg['gate'], r['still'], r['tilt']) for r in rows]
    if cfg['method'] == 'hmm':
        S = run_hmm(series, gate, [r['dsteps'] for r in rows], adj, steps, cfg['beta'], cfg['eps'], cfg['p_stay'])
    else:
        S = run_linear(series, gate, cfg['weights'] if cfg['method'] != 'ema' else None, cfg['alpha'] if cfg['method'] == 'ema' else None)
    places, probs, top3 = display(series, S, cfg['guard'], adj)
    return places, probs, top3, d


def abstain_curve(session, cfg):
    """Coverage / precision on the standing ticks for each abstain threshold, for one chosen setting."""
    places, probs, top3, d = run_cfg(session, cfg)
    sc = d['scorer']
    t = sc['t']
    curve = []
    for th in ABSTAIN:
        shown = right = n = wrong_lit_ev = 0
        for g, ii in sc['stops']:
            stand = ii[(t[ii] >= g['t0'] + TRIM) & (t[ii] <= g['t1'] - TRIM)]
            for i in stand:
                n += 1
                if places[i] is not None and probs[i] >= th:
                    shown += 1; right += places[i] == g['place']
        curve.append({'threshold': th, 'coverage': round(shown / max(n, 1), 4), 'precision': round(right / max(shown, 1), 4),
                      'shown_ticks': shown, 'right_ticks': right, 'standing_ticks': n})
    return curve


def pick_abstain(curve):
    ok = [c for c in curve if c['precision'] >= PREC]
    return max(ok, key=lambda c: (c['coverage'], -c['threshold'])) if ok else max(curve, key=lambda c: (c['precision'], c['coverage']))


def baseline(session, tick):
    d = G[(session, tick)]
    rows = d['rows']
    places = [r['base_top3'][0] if r['base_top3'] else None for r in rows]
    top3 = [tuple(r['base_top3']) for r in rows]
    lit = [r['base_lit'] for r in rows]
    return metrics(d['scorer'], places, top3, lit)


def visit_calibration():
    """Visit-level check (as walksense.evaluate, iPhone x/y/z, true floor): does a per-phone offset help across handsets?"""
    st = {s: ws.training_stops(sessions=(s,), phone='iphone') for s in ws.SESSIONS}
    out = {}
    for tr, te in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
        m = ws.PlaceModel(st[tr])
        Xtr = np.vstack([ws.stop_features(s['rec'], 'xyz') for s in st[tr]])
        Xte = [ws.stop_features(s['rec'], 'xyz') for s in st[te]]
        trm = {}
        for s in st[tr]:
            trm.setdefault((s['floor'], s['place']), []).append(ws.stop_features(s['rec'], 'xyz'))
        first = st[te][0]
        shifts = {'none': np.zeros(3), 'median (whole test session)': np.median(Xtr, 0) - np.median(np.vstack(Xte), 0),
                  'start (first stop known)': np.vstack(trm[(first['floor'], first['place'])]).mean(0) - Xte[0].mean(0)}
        for name, sh in shifts.items():
            ok = n = 0
            for s, X in list(zip(st[te], Xte))[1:]:                    # first stop not scored (used by 'start')
                mm = m.models[s['floor']]
                p = mm.predict_proba(X + sh).mean(0)
                n += 1; ok += mm.classes_[np.argmax(p)] == s['place']
            out[f'{tr}->{te} ({st[tr][0]["device"]} -> {st[te][0]["device"]}) {name}'] = f'{ok}/{n}'
    return out


def main():
    t_start = time.time()
    OUT.mkdir(exist_ok=True)
    models = ws.build_models()
    G['models'] = models
    G['trainwin'] = {STREAMS[s]['device']: train_windows(STREAMS[s]['device']) for s in STREAMS}
    timing = {}
    gate_stats = {}
    for s, info in STREAMS.items():
        graph = route.build((info['train'],))
        G.setdefault('adj', {})[s] = smooth.adjacency(graph)
        for tick in TICKS:
            stream, segs, rows, ms = replay_ticks(s, tick, models, graph)
            G[(s, tick)] = {'stream': stream, 'segs': segs, 'rows': rows, 'scorer': scorer(segs, rows, tick), 'graph': graph}
            timing[f'{s} tick {tick}'] = {'ticks': len(ms), 'ms_median': round(float(np.median(ms)), 3),
                                          'ms_p95': round(float(np.percentile(ms, 95)), 3), 'ms_max': round(float(np.max(ms)), 2)}
            print(f'replayed {s} tick {tick}: {len(rows)} ticks, {time.time() - t_start:.0f} s', flush=True)
        rows, segs = G[(s, 0.5)]['rows'], G[(s, 0.5)]['segs']
        t = np.array([r['t'] for r in rows])
        for kind in ('stop', 'walk'):
            sel = np.zeros(len(t), bool)
            for g in segs:
                if g['type'] == kind:
                    sel |= (t >= g['t0'] + (TRIM if kind == 'stop' else 0)) & (t <= g['t1'] - (TRIM if kind == 'stop' else 0))
            still = np.array([r['still'] for r in rows])[sel]
            tilt = np.array([r['tilt'] if r['tilt'] is not None else np.nan for r in rows])[sel]
            gate_stats[f'{s} {kind}'] = {'ticks': int(sel.sum()), 'still_share': round(float(still.mean()), 4),
                                         'tilt_p50_p95_p99': np.round(np.nanpercentile(tilt, [50, 95, 99]), 1).tolist(),
                                         'still_flat_share': round(float(np.mean(still & (tilt <= smooth.FLAT_DEG))), 4)}
    jobs = [(s, tick, W, pf, c) for s in STREAMS for tick in TICKS for W in WINDOWS for pf in PREFILTERS for c in CALIBS]
    res = {s: [] for s in STREAMS}
    with mp.get_context('fork').Pool(min(len(jobs), max(1, mp.cpu_count() - 2))) as pool:
        for n, (s, out) in enumerate(pool.imap_unordered(evaluate_series, jobs), 1):
            res[s] += out
            print(f'series {n}/{len(jobs)} done, {time.time() - t_start:.0f} s', flush=True)
    # align the two sessions' results by config
    key = lambda c: json.dumps(c, sort_keys=True)
    by = {s: {key(c): (c, m) for c, m in res[s]} for s in STREAMS}
    keys = sorted(by['sesi1'])
    base = {s: {tick: baseline(s, tick) for tick in TICKS} for s in STREAMS}
    fam_of = lambda c: 'guard' if c['guard'] else c['method']
    families = {'none (control, N=1)': lambda c: c['method'] == 'none' and not c['guard'],
                'fir (a,b,c weights)': lambda c: c['method'] == 'fir' and not c['guard'],
                'ema': lambda c: c['method'] == 'ema' and not c['guard'],
                'fir/ema/none + jump guard': lambda c: bool(c['guard']),
                'hmm': lambda c: c['method'] == 'hmm',
                'overall': lambda c: True}
    families_extra = {f'gate={g}': (lambda g: lambda c: c['gate'] == g)(g) for g in smooth.GATES}
    families_extra.update({f'prefilter={p}': (lambda p: lambda c: c['prefilter'] == p)(p) for p in PREFILTERS})
    families_extra.update({f'calib={c}': (lambda cc: lambda c: c['calib'] == cc)(c) for c in CALIBS})
    families_extra.update({f'fir, calib={c}': (lambda cc: lambda c: c['calib'] == cc and c['method'] == 'fir' and not c['guard'])(c) for c in CALIBS})
    families_extra.update({f'hmm, gate={g}': (lambda g: lambda c: c['gate'] == g and c['method'] == 'hmm')(g) for g in smooth.GATES})
    nested = {}
    for name, f in {**families, **families_extra}.items():
        ks = [k for k in keys if f(by['sesi1'][k][0])]
        rows = {}
        for tune, test in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
            (cfg, s_tune), feas = select([(by[tune][k][0], summary(by[tune][k][1])) for k in ks])
            rows[f'tune {tune} -> score {test}'] = {'config': cfg, 'label': smooth.Config(**{k: v for k, v in cfg.items() if k != 'calib'}).label() + f' calib={cfg["calib"]}',
                                                    'feasible_on_tune': feas, 'tune': s_tune, 'test': summary(by[test][key(cfg)][1])}
        (cfg, s_pool), feas = select([(by['sesi1'][k][0], summary(pooled([by['sesi1'][k][1], by['sesi2'][k][1]]))) for k in ks])
        rows['pooled choice (deploy)'] = {'config': cfg, 'label': smooth.Config(**{k: v for k, v in cfg.items() if k != 'calib'}).label() + f' calib={cfg["calib"]}',
                                          'feasible': feas, 'pooled': s_pool,
                                          'sesi1': summary(by['sesi1'][key(cfg)][1]), 'sesi2': summary(by['sesi2'][key(cfg)][1])}
        nested[name] = rows
    # abstain on the overall choice
    abst = {}
    for tune, test in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
        cfg = nested['overall'][f'tune {tune} -> score {test}']['config']
        ct, cs = abstain_curve(tune, cfg), abstain_curve(test, cfg)
        pick = pick_abstain(ct)
        abst[f'tune {tune} -> score {test}'] = {'config': cfg, 'tune_curve': ct, 'test_curve': cs, 'chosen_threshold': pick['threshold'],
                                                'test_at_chosen': next(c for c in cs if c['threshold'] == pick['threshold'])}
    dep = nested['overall']['pooled choice (deploy)']['config']
    abst['pooled choice'] = {'config': dep, 'sesi1': abstain_curve('sesi1', dep), 'sesi2': abstain_curve('sesi2', dep)}
    pc = [{'threshold': a['threshold'], 'coverage': round((a['shown_ticks'] + b['shown_ticks']) / (a['standing_ticks'] + b['standing_ticks']), 4),
           'precision': round((a['right_ticks'] + b['right_ticks']) / max(a['shown_ticks'] + b['shown_ticks'], 1), 4)}
          for a, b in zip(abst['pooled choice']['sesi1'], abst['pooled choice']['sesi2'])]
    abst['pooled choice']['pooled_curve'] = pc
    abst['pooled choice']['chosen_threshold'] = pick_abstain(pc)['threshold']
    # check: the vectorised search == smooth.Continuous inside LiveTracker, end to end, for the deploy choice
    check = end_to_end(dep, by)
    figs = figures(nested, base)
    out = {'what': __doc__.split('\n\n')[1].strip(), 'rule': __doc__.split('Selection rule')[1].strip(),
           'streams': {s: {'model': STREAMS[s]['device'], 'model_trained_on': STREAMS[s]['train'],
                           'scored_stops': len(G[(s, 0.5)]['scorer']['stops']), 'walks': len(G[(s, 0.5)]['scorer']['walks'])} for s in STREAMS},
           'gate_stats': gate_stats, 'ms_per_tick_in_replay': timing,
           'baseline_tian_3s': {f'{s} tick {tick}': summary(base[s][tick]) for s in STREAMS for tick in TICKS},
           'baseline_pooled_tick_0.5': summary(pooled([base['sesi1'][0.5], base['sesi2'][0.5]])),
           'nested': nested, 'abstain': abst, 'visit_level_calibration': visit_calibration(),
           'end_to_end_check': check, 'figures': figs, 'n_configs_per_session': len(keys), 'seconds': round(time.time() - t_start)}
    OUT.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=float))
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        r3 = lambda v: round(v, 3) if isinstance(v, float) else v      # CSV only; selection used full precision
        cols = ['top1', 'top3', 'flips_per_min', 'lock_median_s', 'locked_stops', 'first_correct_median_s', 'wrong_lit_events',
                'lit_events', 'walk_on_corridor', 'walk_flips_per_min', 'walk_wrong_lits']
        w = csv.writer(f)
        w.writerow(['label', 'family', 'tick', 'window', 'prefilter', 'calib', 'gate', 'method', 'weights', 'alpha', 'guard', 'beta', 'eps', 'p_stay'] +
                   [f'{s}_{c}' for s in STREAMS for c in cols] + [f'pooled_{c}' for c in cols])
        w.writerow(['BASELINE Tian 3 s', 'baseline', 0.5, '', '', '', '', '', '', '', '', '', '', ''] +
                   [summary(base[s][0.5])[c] for s in STREAMS for c in cols] + [summary(pooled([base['sesi1'][0.5], base['sesi2'][0.5]]))[c] for c in cols])
        for k in keys:
            c = by['sesi1'][k][0]
            ss = {s: summary(by[s][k][1]) for s in STREAMS}
            sp = summary(pooled([by['sesi1'][k][1], by['sesi2'][k][1]]))
            w.writerow([smooth.Config(**{a: b for a, b in c.items() if a != 'calib'}).label(), fam_of(c), c['tick'], c['window'], c['prefilter'], c['calib'],
                        c['gate'], c['method'], ' '.join(f'{x:g}' for x in c['weights']), c['alpha'] if c['method'] == 'ema' else '',
                        c['guard'], *(c[x] if c['method'] == 'hmm' else '' for x in ('beta', 'eps', 'p_stay'))] +
                       [r3(ss[s][col]) for s in STREAMS for col in cols] + [r3(sp[col]) for col in cols])
    print(json.dumps({k: out[k] for k in ('baseline_pooled_tick_0.5', 'end_to_end_check', 'visit_level_calibration', 'seconds')}, indent=1))
    return out


def end_to_end(cfg, by):
    """Run the chosen setting inside LiveTracker on both streams; its shown place must match the search."""
    if cfg['calib'] == 'median':
        return {'skipped': 'median calibration is time-varying; not wired into LiveTracker'}
    res = {}
    for s in STREAMS:
        d = G[(s, cfg['tick'])]
        shift = (0.0, 0.0, 0.0)
        if cfg['calib'] == 'start':
            s0 = next(g for g in d['segs'] if g['type'] == 'stop'); mag = d['stream']['mag']
            m = mag[(mag[:, 0] >= s0['t0'] + TRIM) & (mag[:, 0] < s0['t0'] + TRIM + 10), 1:4].mean(0)
            shift = tuple(G['trainwin'][STREAMS[s]['device']][(s0['floor'], s0['place'])].mean(0) - m)
        c = smooth.Config(**{**{k: v for k, v in cfg.items() if k != 'calib'}, 'shift': shift})
        stream, segs, rows, ms = replay.replay(s, c, G['models'], d['graph'], STREAMS[s]['device'])
        places, top3, lit = [r['place'] for r in rows], [r['top3'] for r in rows], [r['lit'] for r in rows]
        m = metrics(scorer(segs, rows, cfg['tick']), places, top3, lit)
        want = summary(by[s][json.dumps(cfg, sort_keys=True)][1])
        got = summary(m)
        res[s] = {'live_tracker': got, 'matches_search': all(got[k] == want[k] for k in want), 'ticks': len(rows),
                  'ms_per_tick_median': round(float(np.median(ms)), 3)}
    return res



def figures(nested, base):
    """fig_heldout.png: held-out score of each family's choice; fig_timeline.png: shown place over time."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fams = ['none (control, N=1)', 'fir (a,b,c weights)', 'ema', 'fir/ema/none + jump guard', 'hmm', 'overall']
    dirs = [('tune sesi2 -> score sesi1', 'sesi1'), ('tune sesi1 -> score sesi2', 'sesi2')]
    names = ['Tian 3 s'] + ['none', 'FIR a,b,c', 'EMA', '+ guard', 'HMM', 'overall']
    fig, axs = plt.subplots(1, 3, figsize=(13, 4))
    for ax, key, title in zip(axs, ('top1', 'flips_per_min', 'lock_median_s'),
                              ('per-tick top-1 while standing', 'flips per minute while standing', 'median lock time (s)')):
        x = np.arange(len(names))
        for j, (dk, sess) in enumerate(dirs):
            vals = [summary(base[sess][0.5])[key]] + [nested[f][dk]['test'][key] for f in fams]
            vals = [np.nan if v is None else v for v in vals]
            ax.bar(x + (j - 0.5) * 0.38, vals, 0.38, label=f'scored on {sess} ({STREAMS[sess]["device"]} model)')
        ax.set_xticks(x, names, rotation=35, ha='right'); ax.set_title(title, fontsize=10)
        if key == 'flips_per_min':
            ax.axhline(MAX_FLIPS, color='k', lw=0.8, ls='--')
        if key == 'lock_median_s':
            ax.axhline(MAX_LOCK, color='k', lw=0.8, ls='--')
    axs[0].legend(fontsize=8, loc='lower left')
    fig.suptitle('Held out (chosen on the other session): Tian 3 s baseline vs smoothed estimates, 24 Nov', fontsize=11)
    fig.tight_layout(); fig.savefig(OUT / 'fig_heldout.png', dpi=130); plt.close(fig)
    # timeline: sesi2 scored with settings chosen on sesi1
    sess, dk = 'sesi2', 'tune sesi1 -> score sesi2'
    d = G[(sess, 0.5)]
    stops = [g for g in d['segs'] if g['type'] == 'stop' and g['floor'] == 5][1:7]
    t0, t1 = stops[0]['t0'] - 5, stops[-1]['t1'] + 5
    show = {'Tian 3 s': None, 'none': nested['none (control, N=1)'][dk]['config'], 'FIR a,b,c': nested['fir (a,b,c weights)'][dk]['config'],
            'HMM': nested['hmm'][dk]['config'], 'overall': nested['overall'][dk]['config']}
    places5 = sorted(G['models'][STREAMS[sess]['device']].models[5].classes_)
    yi = {p: i for i, p in enumerate(places5)}
    fig, axs = plt.subplots(len(show), 1, figsize=(12, 1.9 * len(show)), sharex=True)
    for ax, (name, cfg) in zip(axs, show.items()):
        if cfg is None:
            rows = d['rows']; t = np.array([r['t'] for r in rows]); pl = [r['base_top3'][0] if r['base_top3'] else None for r in rows]
        else:
            pl, _, _, dd = run_cfg(sess, cfg); t = np.array([r['t'] for r in dd['rows']])
        sel = (t >= t0) & (t <= t1)
        y = np.array([yi.get(p, np.nan) if p is not None else np.nan for p in pl], float)
        for g in stops:
            ax.plot([g['t0'], g['t1']], [yi[g['place']]] * 2, color='0.75', lw=7, solid_capstyle='butt')
        for g in d['segs']:
            if g['type'] == 'walk' and g['t1'] > t0 and g['t0'] < t1:
                ax.axvspan(g['t0'], g['t1'], color='C0', alpha=0.12, lw=0)
        ax.plot(t[sel], y[sel], '.', ms=2.5, color='C3')
        ax.set_yticks(range(len(places5)), places5, fontsize=6); ax.set_title(name + ('' if cfg is None else ': ' + smooth.Config(**{k: v for k, v in cfg.items() if k != 'calib'}).label()), fontsize=8, loc='left')
        ax.set_xlim(t0, t1)
    axs[-1].set_xlabel('session-2 stream time (s); grey = true stop place, blue band = walk, red = shown place every tick')
    fig.tight_layout(); fig.savefig(OUT / 'fig_timeline.png', dpi=130); plt.close(fig)
    return ['out/fig_heldout.png', 'out/fig_timeline.png']


if __name__ == '__main__':
    main()
