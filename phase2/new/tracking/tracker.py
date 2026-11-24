#!/usr/bin/env python3
"""Route-aware tracker (proposal method D, HMM fusion) on the circles-on-lines graph.

State     = the checkpoint (node) you are at, plus, while walking, which line (path of
            1 or 2 edges, or "stay") you are on and how far along it.
Emission  = barometer floor (step tracking from crossday.py, threshold learned on the other
            day) + magnetic likelihood at stops (|B| + x/y/z window features from crossday.py;
            distance to each place's nearest training windows -> probability).
Transition= during a walk: stay, or move 1 or 2 edges along the graph, gated by the detected
            step count (pdr.py) against each path's expected steps. Between two stops with no
            walk recorded: stay or move up to 3 edges, no step information.
No compass heading is used. The filter is causal (only past data), like a live app.

Experiments
  23 Nov   replay in time order; leave-one-visit-out (LOVO): the magnetic model for stop k is
           trained on every 23-Nov stop except k, and the true line of each walk gets no step
           count from that same walk (leave-one-walk-out).
  17 Nov   cross-day: magnetic model and step lengths from 23 Nov, replay the 17-Nov loop.
Compared, on the same stops: the crossday.py snapshot classifier (barometer floor + |B|+xyz
kNN, majority vote) and the tracker's own emission with no graph ("emission only").

Run after pdr.py and ../graph/build_graph.py (or use run_all.sh).
Writes out/tracker_results.json, out/tracker_visits_23nov.csv, out/tracker_visits_17nov.csv,
out/replay_23nov.json (the UI interface) and out/replay_17nov.json.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
GRAPH = NEW / 'graph'
OUT = HERE / 'out'
sys.path.insert(0, str(NEW / 'cross-day'))
import crossday as cd   # noqa: E402

# ---- parameters, fixed before the first run (not tuned on the results; see "sensitivity")
TAU = 1.0              # magnetic: log-likelihood = -distance / TAU (standardised feature units)
BETA = 0.1             # weight per 2 s window (neighbouring windows are near-copies, ~30 per stop)
K_NEAR = 3             # distance to a place = mean of its K_NEAR nearest training windows
P_FLOOR_OK = 0.95      # barometer floor emission (v1; v2 below)
RELOC = 0.0            # share of belief spread uniformly after each move (v1 = none; v2 below)
CONFIRM_P = 0.6        # a stop frame is "confirmed" when the top node has at least this probability
WALK_PRIOR = {0: 0.02, 1: 0.85, 2: 0.13}             # stay / 1 edge / 2 edges during a walk
GAP_PRIOR = {0: 0.3, 1: 0.4, 2: 0.2, 3: 0.1}          # no walk recorded between two stops
FRAME_DT = 0.5         # replay export: 2 frames per second
FEATS = cd.MAG_XYZ
# v1 = the parameters above, fixed before the first run. It failed (see README): with no
# re-localisation term a wrong belief can never recover, and a 0.95 floor weight lost to the
# transition prior on 2 stops. v2 changes exactly these two things, chosen from that failure
# analysis, not by a search over results.
VARIANTS = {'v1_prespecified': {'P_FLOOR_OK': 0.95, 'RELOC': 0.0},
            'v2_relocalise_and_firm_floor': {'P_FLOOR_OK': 0.99, 'RELOC': 0.05}}


def set_variant(name):
    globals().update(VARIANTS[name])


# ============================================================================ graph
def load_graph():
    nodes = pd.read_csv(GRAPH / 'nodes.csv', dtype={'on_edge': str}).fillna({'area': '', 'on_edge': ''})
    edges = pd.read_csv(GRAPH / 'edges.csv')
    real = nodes[nodes['virtual'] == 0].reset_index(drop=True)
    ids = list(real['node_id'])
    adj = defaultdict(set)
    for a, b in zip(edges['from'], edges['to']):
        adj[a].add(b); adj[b].add(a)
    elen = {}
    for _, e in edges.iterrows():
        elen[frozenset((e['from'], e['to']))] = {'steps': e['median_steps'], 'dist': e['distance_m'],
                                                 'walks': str(e['walks_23nov']).split() if isinstance(e['walks_23nov'], str) else []}
    hops = {}
    for s in ids:                       # BFS hop distances
        d, frontier = {s: 0}, [s]
        while frontier:
            nxt = []
            for u in frontier:
                for v in adj[u]:
                    if v not in d:
                        d[v] = d[u] + 1; nxt.append(v)
            frontier = nxt
        hops[s] = d
    g = {'nodes': nodes, 'real': real, 'edges': edges, 'ids': ids, 'idx': {n: i for i, n in enumerate(ids)},
         'adj': adj, 'elen': elen, 'hops': hops,
         'floor': dict(zip(real['node_id'], real['floor'])), 'area': dict(zip(real['node_id'], real['area'])),
         'xy5': {r.node_id: (r.x, r.y) for r in real.itertuples() if r.xy_source == 'floor5_metres'}}
    return g


def paths_from(g, n, max_hops):
    """All simple paths starting at n with 0..max_hops edges."""
    out = [(n,)]
    frontier = [(n,)]
    for _ in range(max_hops):
        nxt = []
        for p in frontier:
            for v in sorted(g['adj'][p[-1]]):
                if v not in p:
                    nxt.append(p + (v,))
        out += nxt; frontier = nxt
    return out


# ============================================================================ data
def day_inputs(day):
    """Stops (with place), walks (with step times), magnetic windows, barometer floor per stop."""
    sessions = cd.load_sessions(day)
    mag, baro = cd.load_sensors(day)
    W = cd.magnetic_windows(mag, day)
    t0 = mag.groupby('stop_id')['timestamp_epoch_s'].min()
    W['t_end'] = [t0[k.split(':')[1]] + (w + 1) * cd.WINDOW_S for k, w in zip(W['key'], W['window'])]
    st = sessions[sessions['stop_id'].str.startswith('BM')].sort_values('start_epoch_s').reset_index(drop=True)
    if day == cd.D_23:
        lab = pd.read_csv(NEW / 'cross-day' / 'labels_23nov_confirmed.csv', dtype=str)
        place = dict(zip(lab['stop_id'], lab['label'].str.strip()))
    else:
        cw = pd.read_csv(NEW / 'cross-day' / 'crosswalk_17nov_to_23nov.csv', dtype=str).fillna('')
        tier = {s: c for s, c in zip(cw['stop_id_17nov'], cw['confidence'])}
        cw = cw[cw['confidence'].isin(['high', 'medium'])]
        place = dict(zip(cw['stop_id_17nov'], cw['place_23nov'].str.strip()))
        st['tier'] = st['stop_id'].map(tier)
    st['place'] = st['stop_id'].map(place)
    pw = pd.read_csv(HERE / 'out' / ('pdr_walks_23nov.csv' if day == cd.D_23 else 'pdr_walks_17nov.csv'))
    times = json.loads((HERE / 'out' / 'pdr_step_times.json').read_text())[day]
    ses = sessions.set_index('stop_id')
    pw['start'] = pw['walk_id'].map(ses['start_epoch_s']); pw['end'] = pw['walk_id'].map(ses['end_epoch_s'])
    pw['step_times'] = pw['walk_id'].map(times)
    return st, pw, W


def floor_obs():
    """Barometer step-tracking floor per stop, exactly as crossday.floors() (threshold from the other day)."""
    lab = pd.read_csv(NEW / 'cross-day' / 'labels_23nov_confirmed.csv')
    cw = pd.read_csv(NEW / 'cross-day' / 'crosswalk_17nov_to_23nov.csv', dtype=str)
    true_floor = {f'{cd.D_23}:{s}': int(f) for s, f in zip(lab['stop_id'], lab['floor'])}
    true_floor.update({f'{cd.D_17}:{s}': int(f) for s, f in zip(cw['stop_id_17nov'], cw['floor_17nov'])})
    press = {}
    for d in [cd.D_17, cd.D_23]:
        _, baro = cd.load_sensors(d)
        p = baro.groupby('stop_id').agg(hpa=('hpa', 'median'), t=('timestamp_epoch_s', 'min')).reset_index()
        p['key'] = d + ':' + p['stop_id']
        press[d] = p.sort_values('t').reset_index(drop=True)
    _, res, pred = cd.floors(press, true_floor, None)
    return pred, res


def timeline(st, pw):
    """Ordered segments: ('stop', row) / ('walk', row) / ('gap', None)."""
    seg = []
    for i, s in st.iterrows():
        seg.append(('stop', s))
        if i + 1 == len(st):
            break
        w = pw[pw['from_stop'] == s['stop_id']]
        if len(w):
            for _, r in w.iterrows():
                seg.append(('walk', r))
        else:
            seg.append(('gap', None))
    return seg


# ============================================================================ magnetic model
class MagModel:
    """Distance-based likelihood: for each place, mean distance to its K_NEAR nearest training windows."""

    def __init__(self, Wtr, place_of, ids):
        self.imp = SimpleImputer(strategy='median').fit(Wtr[FEATS])
        X = self.imp.transform(Wtr[FEATS])
        self.sc = StandardScaler().fit(X)
        X = self.sc.transform(X)
        y = np.array([place_of[k] for k in Wtr['key']])
        self.ids = ids
        self.by = {n: X[y == n] for n in ids if (y == n).any()}

    def loglik(self, Wte):
        X = self.sc.transform(self.imp.transform(Wte[FEATS]))
        D = np.full((len(X), len(self.ids)), np.nan)
        for j, n in enumerate(self.ids):
            if n in self.by:
                d = np.sqrt(((X[:, None, :] - self.by[n][None, :, :]) ** 2).sum(-1))
                k = min(K_NEAR, d.shape[1])
                D[:, j] = np.sort(d, axis=1)[:, :k].mean(1)
        # a place with no training data: "as plausible as a typical place" (median distance)
        med = np.nanmedian(D, axis=1, keepdims=True)
        D = np.where(np.isnan(D), med, D)
        return -D / TAU


def knn_snapshot(Wtr, Wte, place_of, floor_of_te, g):
    """crossday.py recipe: barometer floor picks a per-floor kNN (k=5, distance-weighted) on |B|+xyz; majority vote."""
    f = floor_of_te
    ytr = np.array([place_of[k] for k in Wtr['key']])
    on = np.array([g['floor'][y] == f for y in ytr])
    if not on.any():
        on[:] = True
    m = cd.make_model('knn', int(on.sum())).fit(Wtr[FEATS].to_numpy(float)[on], ytr[on])
    Xte = Wte[FEATS].to_numpy(float)
    pred = m.predict(Xte)
    proba = m.predict_proba(Xte).mean(0)
    pr = dict(zip(m.classes_, proba))
    votes = Counter(pred)
    rank = sorted(pr, key=lambda c: (-votes.get(c, 0), -pr[c], c))
    return rank, {c: round(float(pr[c]), 3) for c in rank}


# ============================================================================ tracker
def norm_log(v):
    v = v - np.max(v)
    p = np.exp(v)
    return np.log(p / p.sum())


class Tracker:
    def __init__(self, g, mu_fn):
        self.g, self.mu_fn = g, mu_fn
        self.lb = np.full(len(g['ids']), -math.log(len(g['ids'])))   # uniform start

    def floor_update(self, f):
        fl = np.array([self.g['floor'][n] for n in self.g['ids']])
        self.lb = norm_log(self.lb + np.where(fl == f, math.log(P_FLOOR_OK), math.log(1 - P_FLOOR_OK)))

    def mag_update(self, ll_row):
        self.lb = norm_log(self.lb + BETA * ll_row)

    def probs(self):
        return np.exp(self.lb)

    def hypotheses(self, prior, walk_id):
        g, b = self.g, self.probs()
        H = []
        maxh = max(prior)
        for i, n in enumerate(g['ids']):
            if b[i] < 1e-6:
                continue
            ps = paths_from(g, n, maxh)
            cnt = Counter(len(p) - 1 for p in ps)
            for p in ps:
                h = len(p) - 1
                mus = [self.mu_fn(p[j], p[j + 1], walk_id) for j in range(h)]
                mu = sum(m for m, _ in mus)
                var = sum(s ** 2 for _, s in mus) if h else 9.0
                H.append({'path': p, 'w0': b[i] * prior[h] / cnt[h], 'mu_hops': [m for m, _ in mus],
                          'mu': mu, 'sd': math.sqrt(var)})
        return H

    def set_from(self, H, w):
        nb = np.full(len(self.g['ids']), 1e-12)
        for h, x in zip(H, w):
            nb[self.g['idx'][h['path'][-1]]] += x
        nb = (1 - RELOC) * nb / nb.sum() + RELOC / len(nb)
        self.lb = norm_log(np.log(nb))


def position(h, k):
    """Where on the path after k steps: (edge_from, edge_to, progress on that edge, nearest node)."""
    p = h['path']
    if len(p) == 1:
        return None, None, None, p[0]
    acc = 0.0
    for j, m in enumerate(h['mu_hops']):
        if k <= acc + m or j == len(h['mu_hops']) - 1:
            prog = float(np.clip((k - acc) / m, 0, 1)) if m > 0 else 1.0
            return p[j], p[j + 1], round(prog, 3), (p[j] if prog < 0.5 else p[j + 1])
        acc += m


def top3(g, prob):
    o = np.argsort(-prob)[:3]
    return [[g['ids'][i], round(float(prob[i]), 3)] for i in o]


def run(day, g, st, pw, W, models, floor_of, mu_fn, export=False, true_place=None):
    """Replay one day in time order. models(stop_id) -> MagModel used for that stop's windows."""
    tr = Tracker(g, mu_fn)
    seg = timeline(st, pw)
    t_start = min(st['start_epoch_s'].min(), pw['start'].min())
    frames, visits = [], []
    steps_total = 0
    floor_now = None
    for kind, r in seg:
        if kind == 'stop':
            sid = r['stop_id']
            arrival = tr.probs()
            floor_now = int(floor_of[f'{day}:{sid}'])
            tr.floor_update(floor_now)
            ww = W[W['key'] == f'{day}:{sid}'].sort_values('window')
            ll = models(sid).loglik(ww) if len(ww) else np.zeros((0, len(g['ids'])))
            te = ww['t_end'].to_numpy()
            ts = np.arange(r['start_epoch_s'], r['end_epoch_s'] + 1e-9, FRAME_DT)
            j = 0
            for t in ts:
                while j < len(te) and te[j] <= t:
                    tr.mag_update(ll[j]); j += 1
                if export:
                    p = tr.probs()
                    frames.append(frame(t - t_start, floor_now, None, None, None, g['ids'][int(np.argmax(p))],
                                        bool(p.max() >= CONFIRM_P), top3(g, p), r['place'] if isinstance(r['place'], str) else None,
                                        steps_total, sid, g))
            while j < len(te):
                tr.mag_update(ll[j]); j += 1
            visits.append({'stop_id': sid, 'true': r['place'] if isinstance(r['place'], str) else None,
                           'floor_obs': floor_now, 'post': tr.probs(), 'arrival': arrival})
        elif kind == 'walk':
            reliable = bool(r['steps_reliable'])
            H = tr.hypotheses(WALK_PRIOR if reliable else GAP_PRIOR, r['walk_id'])
            w0 = np.array([h['w0'] for h in H])
            stimes = np.array(r['step_times'], float)
            ts = np.arange(r['start'], r['end'] + 1e-9, FRAME_DT)
            for t in ts:
                k = int((stimes <= t).sum())
                if export:
                    if reliable:
                        w = w0 * np.array([norm.sf((k - 0.5 - h['mu']) / h['sd']) if h['mu'] > 0 or k > 0 else 1.0 for h in H])
                        kk = [k] * len(H)
                    else:          # no usable steps: move along each path in proportion to time
                        w = w0.copy()
                        fr = (t - r['start']) / max(1e-6, r['end'] - r['start'])
                        kk = [fr * h['mu'] for h in H]
                    w = w / w.sum()
                    best = int(np.argmax(w))
                    ef, et, prog, nd = position(H[best], kk[best])
                    near = defaultdict(float)
                    for h, x, kx in zip(H, w, kk):
                        near[position(h, kx)[3]] += x
                    p = np.array([near.get(n, 0.0) for n in g['ids']])
                    frames.append(frame(t - t_start, floor_now, ef, et, prog, nd, False, top3(g, p), None,
                                        steps_total + k, r['walk_id'], g))
            n = len(stimes)
            if reliable:
                w = w0 * np.array([norm.pdf(n, h['mu'], h['sd']) + 1e-12 for h in H])
            else:
                w = w0
            tr.set_from(H, w / w.sum())
            steps_total += n
        else:   # gap: unrecorded move
            H = tr.hypotheses(GAP_PRIOR, None)
            w = np.array([h['w0'] for h in H])
            tr.set_from(H, w / w.sum())
    return visits, frames


def frame(t, floor, ef, et, prog, node, conf, t3, true_node, steps, rec, g):
    return {'t': round(float(t), 2), 'floor': floor, 'edge_from': ef, 'edge_to': et, 'progress': prog,
            'node': node, 'confirmed': conf, 'top3': t3, 'true_node': true_node, 'steps_total': int(steps), 'rec': rec}


# ============================================================================ step lengths
def mu_factory(g, pw23, mode):
    """Expected steps (mu, sd) for one edge.
    mode 'lowo'  : the edge's own 23-Nov walk is never used for the walk being tracked (fallback:
                   map distance / median stride of the OTHER floor-5 walks, else the median steps
                   of the OTHER walks, with a wide sd);
    mode 'graph' : edges.csv median_steps as is (optimistic on 23 Nov, honest for 17 Nov)."""
    ok = pw23[pw23['steps_reliable']]
    dist = {k: v['dist'] for k, v in g['elen'].items()}
    walk_edge = {w: frozenset((a, b)) for w, a, b in zip(pw23['walk_id'], pw23['from_place'], pw23['to_place'])}
    cache = {}

    def fallback(excl):
        if excl not in cache:
            o = ok[ok['walk_id'] != excl]
            strides = [dist[walk_edge[w]] / s for w, s in zip(o['walk_id'], o['steps'])
                       if not np.isnan(dist.get(walk_edge[w], np.nan)) and s > 0]
            cache[excl] = (float(np.median(strides)), float(np.median(o['steps'])))
        return cache[excl]

    def mu(a, b, walk_id):
        e = g['elen'][frozenset((a, b))]
        own = mode == 'lowo' and walk_id in e['walks']
        if not own and not np.isnan(e['steps']):
            m = float(e['steps']); return m, max(4.0, 0.3 * m)
        stride, typical = fallback(walk_id if mode == 'lowo' else None)
        if not np.isnan(e['dist']):
            m = e['dist'] / stride; return m, max(4.0, 0.4 * m)
        return typical, max(6.0, 0.6 * typical)
    return mu


# ============================================================================ scoring
def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def metric(hits):
    k, n = int(sum(hits)), len(hits)
    return {'k': k, 'n': n, 'rate': round(k / n, 3) if n else None, 'wilson95': wilson(k, n)}


def score(g, rows, pred_key):
    """rows: dicts with 'true' and a ranked list under pred_key."""
    R = [r for r in rows if r['true']]
    t = [r['true'] for r in R]
    p1 = [r[pred_key][0] for r in R]
    out = {'exact': metric([a == b for a, b in zip(t, p1)]),
           'area': metric([g['area'][a] == g['area'][b] for a, b in zip(t, p1)]),
           'within_one_neighbour': metric([a == b or b in g['adj'][a] for a, b in zip(t, p1)]),
           'top3': metric([a in r[pred_key][:3] for a, r in zip(t, R)]),
           'floor': metric([g['floor'][a] == g['floor'][b] for a, b in zip(t, p1)])}
    w5 = [(a, b) for a, b in zip(t, p1) if a in g['xy5']]
    out['within_5m_floor5'] = metric([b in g['xy5'] and math.dist(g['xy5'][a], g['xy5'][b]) <= 5.0 for a, b in w5])
    return out


def ranked(g, p):
    return [g['ids'][i] for i in np.argsort(-p)]


# ============================================================================ experiments
def experiment_23(g, floor_of, mode, export=False, tau=None, beta=None):
    global TAU, BETA
    keep = TAU, BETA
    if tau is not None:
        TAU, BETA = tau, beta
    st, pw, W = day_inputs(cd.D_23)
    place_of = {f'{cd.D_23}:{s}': p for s, p in zip(st['stop_id'], st['place'])}
    lovo = {}

    def model(sid):
        if sid not in lovo:
            lovo[sid] = MagModel(W[W['key'] != f'{cd.D_23}:{sid}'], place_of, g['ids'])
        return lovo[sid]
    visits, frames = run(cd.D_23, g, st, pw, W, model, floor_of, mu_factory(g, pw, mode), export)
    TAU, BETA = keep
    return st, pw, W, place_of, visits, frames


def snapshots(g, W, place_of_tr, Wtr_fn, visits, day, floor_of, mag_fn):
    for v in visits:
        ww = W[W['key'] == f'{day}:{v["stop_id"]}']
        Wtr = Wtr_fn(v['stop_id'])
        rank, _ = knn_snapshot(Wtr, ww, place_of_tr, v['floor_obs'], g)
        v['knn_rank'] = rank + [n for n in g['ids'] if n not in rank]
        ll = mag_fn(v['stop_id']).loglik(ww).sum(0) * BETA
        fl = np.array([g['floor'][n] for n in g['ids']])
        ll = ll + np.where(fl == v['floor_obs'], math.log(P_FLOOR_OK), math.log(1 - P_FLOOR_OK))
        v['emis_rank'] = ranked(g, ll)
        v['trk_rank'] = ranked(g, v['post'])
        v['arr_rank'] = ranked(g, v['arrival'])


def table(g, visits, subsets):
    out = {}
    for name, sel in subsets.items():
        rows = [v for v in visits if sel(v)]
        out[name] = {'n_visits': len([r for r in rows if r['true']]),
                     'tracker': score(g, rows, 'trk_rank'),
                     'snapshot_knn_crossday_recipe': score(g, rows, 'knn_rank'),
                     'emission_only_no_graph': score(g, rows, 'emis_rank'),
                     'tracker_arrival_before_stop_data': score(g, rows, 'arr_rank')}
    return out


def visits_csv(visits, path, extra=None):
    rows = []
    for v in visits:
        r = {'stop_id': v['stop_id'], 'true': v['true'], 'floor_obs': v['floor_obs'],
             'tracker': v['trk_rank'][0], 'tracker_p': round(float(v['post'].max()), 3),
             'tracker_top3': ' '.join(v['trk_rank'][:3]), 'arrival': v['arr_rank'][0],
             'snapshot_knn': v['knn_rank'][0], 'emission_only': v['emis_rank'][0]}
        if extra:
            r.update(extra(v))
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False)


def export_graph(g):
    n = g['nodes']
    nodes = [{'id': r.node_id, 'floor': int(r.floor), 'x': float(r.x), 'y': float(r.y), 'kind': r.kind,
              'zone': r.area if r.area else None, 'virtual': bool(r.virtual),
              **({'on_edge': r.on_edge.split('|')} if r.virtual else {})} for r in n.itertuples()]
    nn = lambda x: None if (isinstance(x, float) and np.isnan(x)) else float(x)
    edges = [{'from': e['from'], 'to': e['to'], 'floor_change': bool(e['floor_change']),
              'distance_m': nn(e['distance_m']), 'median_steps': nn(e['median_steps'])} for _, e in g['edges'].iterrows()]
    return {'nodes': nodes, 'edges': edges}


def experiment_17(g, floor_of, W, place_of, pw, export=False):
    st17, pw17, W17 = day_inputs(cd.D_17)
    full = MagModel(W, place_of, g['ids'])
    vis17, frames17 = run(cd.D_17, g, st17, pw17, W17, lambda sid: full, floor_of, mu_factory(g, pw, 'graph'), export)
    snapshots(g, W17, place_of, lambda sid: W, vis17, cd.D_17, floor_of, lambda sid: full)
    return st17, pw17, vis17, frames17


def main():
    OUT.mkdir(exist_ok=True)
    cd.ensure_23nov_cache()
    g = load_graph()
    floor_of, floor_res = floor_obs()
    by_variant, keep = {}, {}
    for vname in VARIANTS:
        set_variant(vname)
        export = vname.startswith('v2')
        # ---------------- 23 Nov, LOVO
        st, pw, W, place_of, visits, frames = experiment_23(g, floor_of, 'lowo', export=export)
        lovo_fit = lambda sid: MagModel(W[W['key'] != f'{cd.D_23}:{sid}'], place_of, g['ids'])
        snapshots(g, W, place_of, lambda sid: W[W['key'] != f'{cd.D_23}:{sid}'], visits, cd.D_23, floor_of, lovo_fit)
        n_vis = Counter(st['place'])
        latest = st.sort_values('start_epoch_s').groupby('place')['stop_id'].last()
        revisit_test = {latest[p] for p, c in n_vis.items() if c > 1}
        subsets = {'all_42_stops': lambda v: True,
                   'place_has_another_visit_in_training': lambda v: n_vis[v['true']] > 1,
                   'place_has_no_fingerprint_in_training': lambda v: n_vis[v['true']] == 1,
                   'latest_revisit_9_crossday_main_test_set': lambda v: v['stop_id'] in revisit_test}
        res23 = table(g, visits, subsets)
        # ---------------- cross-day: train 23 Nov, replay 17 Nov
        st17, pw17, vis17, frames17 = experiment_17(g, floor_of, W, place_of, pw, export=export)
        tier = dict(zip(st17['stop_id'], st17['tier']))
        res17 = table(g, vis17, {'core_high_confidence_17_visits': lambda v: tier[v['stop_id']] == 'high',
                                 'extended_high_and_medium_25_visits': lambda v: tier[v['stop_id']] in ('high', 'medium')})
        sfx = '' if export else '_v1'
        visits_csv(visits, OUT / f'tracker_visits_23nov{sfx}.csv', lambda v: {'n_visits_of_place': n_vis[v['true']]})
        visits_csv(vis17, OUT / f'tracker_visits_17nov{sfx}.csv', lambda v: {'crosswalk_confidence': tier[v['stop_id']]})
        by_variant[vname] = {'parameters': dict(VARIANTS[vname]), 'day_23nov_lovo': res23, 'cross_day_train23_test17': res17}
        if export:
            keep = dict(st=st, pw=pw, frames=frames, st17=st17, pw17=pw17, frames17=frames17, subsets=subsets)
    set_variant('v2_relocalise_and_firm_floor')
    st, pw, frames, subsets = keep['st'], keep['pw'], keep['frames'], keep['subsets']

    # optimistic variant (v2): step lengths from the same walks (graph median_steps as is)
    _, _, _, _, vis_g, _ = experiment_23(g, floor_of, 'graph')
    for v in vis_g:
        v['trk_rank'] = ranked(g, v['post'])
    res23_graph = {k: score(g, [v for v in vis_g if s(v)], 'trk_rank') for k, s in subsets.items()}

    # sensitivity of v2 to the two emission parameters fixed before the first run (reported, not used to pick)
    sens = {}
    for tau in [0.5, 1.0, 2.0]:
        for beta in [0.05, 0.1, 0.2]:
            _, _, _, _, vs, _ = experiment_23(g, floor_of, 'lowo', tau=tau, beta=beta)
            for v in vs:
                v['trk_rank'] = ranked(g, v['post'])
            sc = score(g, vs, 'trk_rank')
            sens[f'tau={tau},beta={beta}'] = {m: sc[m]['rate'] for m in ['exact', 'area', 'top3']}

    # replay export (the UI interface), from v2
    t0 = min(st['start_epoch_s'].min(), pw['start'].min())
    replay = {'graph': export_graph(g), 'destination': st.sort_values('start_epoch_s')['place'].iloc[-1], 'frames': frames,
              'meta': {'day': '2026-11-23', 't0_epoch_s': float(t0), 'frame_dt_s': FRAME_DT,
                       'method': 'route-aware HMM tracker v2, leave-one-visit-out magnetic model, leave-one-walk-out step lengths',
                       'note': 'frames exist only while a stop or walk was recording; t jumps over the gaps. '
                               'Stop frames: edge_from/edge_to/progress are null. Walk frames: true_node is null.'}}
    (OUT / 'replay_23nov.json').write_text(json.dumps(replay, separators=(',', ':')))
    st17, pw17, frames17 = keep['st17'], keep['pw17'], keep['frames17']
    t017 = min(st17['start_epoch_s'].min(), pw17['start'].min())
    (OUT / 'replay_17nov.json').write_text(json.dumps(
        {'graph': export_graph(g), 'destination': None, 'frames': frames17,
         'meta': {'day': '2026-11-17', 't0_epoch_s': float(t017), 'frame_dt_s': FRAME_DT,
                  'method': 'tracker v2, cross-day: magnetic model and step lengths from 23 Nov only',
                  'note': 'last stop (BM26) has no confirmed place, so there is no destination'}}, separators=(',', ':')))

    cd_ref = json.loads((NEW / 'cross-day' / 'out' / 'results.json').read_text())['results']
    results = {
        'what': 'Route-aware tracker (HMM on the circles-on-lines graph) vs independent snapshot classifiers. '
                'Every number is computed by tracker.py from committed data.',
        'parameters_common': {'tau': TAU, 'beta_per_window': BETA, 'k_near': K_NEAR, 'confirm_p': CONFIRM_P,
                              'walk_prior_by_hops': WALK_PRIOR, 'gap_prior_by_hops': GAP_PRIOR,
                              'step_sd': 'max(4, 0.3 x mu) for a measured edge; 0.4 x mu from map distance; 0.6 x mu for unknown length',
                              'features': FEATS, 'start_belief': 'uniform over the 31 places',
                              'floor': 'crossday.py step tracking, threshold from the other day, first stop assumed on floor 5 (as in crossday.py)'},
        'variants': by_variant,
        'graph': {'nodes': len(g['ids']), 'edges': len(g['edges'])},
        'floor_tracking_check': floor_res,
        'v2_day_23nov_tracker_with_step_lengths_from_the_same_walks_optimistic': res23_graph,
        'reference_crossday_py_cross_core_15_place_classifier': {
            m: cd_ref['cross_core']['mag'][m]['visit_place_accuracy'] for m in ['magnitude_xyz_knn', 'magnitude_xyz_knn_baro_floor']},
        'v2_sensitivity_23nov_all_42_tracker': sens,
        'v2_confirmed_frames_23nov': {'stop_frames': sum(1 for f in frames if f['true_node']),
                                      'confirmed': sum(1 for f in frames if f['confirmed']),
                                      'confirmed_and_correct': sum(1 for f in frames if f['confirmed'] and f['node'] == f['true_node'])},
        'replay_frames': {'23nov': len(frames), '17nov': len(frames17)},
    }
    (OUT / 'tracker_results.json').write_text(json.dumps(results, indent=1))

    def show(title, R):
        print(f'\n{title}')
        for sub, blk in R.items():
            print(f'  {sub} (n={blk["n_visits"]})')
            for meth in ['tracker', 'snapshot_knn_crossday_recipe', 'emission_only_no_graph', 'tracker_arrival_before_stop_data']:
                s = blk[meth]
                print(f'    {meth:34s} ' + ' '.join(f'{m}={s[m]["k"]}/{s[m]["n"]}' for m in s))
    for vname, blk in by_variant.items():
        show(f'{vname}: 23 Nov LOVO', blk['day_23nov_lovo'])
        show(f'{vname}: cross-day 23 -> 17', blk['cross_day_train23_test17'])
    print('\nv2, 23 Nov, step lengths from the same walks (optimistic):', {k: v['exact']['rate'] for k, v in res23_graph.items()})
    print('v2 sensitivity', sens)
    print('frames', results['replay_frames'], results['v2_confirmed_frames_23nov'])


if __name__ == '__main__':
    main()
