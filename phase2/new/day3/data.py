"""Shared data layer for the day-3 (24-Nov) evaluation. Config-driven: see config.json.

Builds, for every session in config.json:
  windows   one row per WINDOW_S magnetometer window of every STOP recording (every phone):
            |B| mean/sd/p10/p90, mean x/y/z, and tilt-corrected B_vertical / B_horizontal
            (gravity = mean accelerometer in the window; NaN when no accelerometer was logged)
  visits    one row per physical stop (all phones together): place, true floor, start/end,
            median pressure per phone, Wi-Fi rows assigned to that stop
  wifi      every Wi-Fi observation with the stop it was assigned to (nearest stop in time,
            at most wifi_nearest_stop_max_gap_s away; in_window = inside the stop's dwell)
  endpoints first/last 2 s of every WALK recording (for the walk-endpoint tilt test)

The big CSVs are parsed once and cached under ./cache/ (gitignored). Nothing outside ./cache and
./out is written. Rebuild everything with:  python phase2/new/day3/data.py --rebuild

Variants (config.json `variants`, chosen with the environment variable DAY3_VARIANT, e.g. `run_all.sh --split20`):
the default (no variant) is the original pipeline, writing to ./out. A variant writes to ./out-<name> and changes
only the stop windows, after loading (see apply_variant): split20 cuts every stop take into 20 s pieces (each piece
= one sample, key '<take>#p<j>', its parent take in column `take`; `visit` stays the physical stop, so every
grouped split keeps the pieces of one take together), drops the stops in the exclusion list and removes obvious
outlier pieces by pre-set rules. Every piece and its status is written to out-<name>/pieces.csv.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
CACHE = HERE / 'cache'
VARIANT = os.environ.get('DAY3_VARIANT', '').strip()      # '' = original pipeline
OUT = HERE / (f'out-{VARIANT}' if VARIANT else 'out')
HK = timezone(timedelta(hours=8))
PRESSURE_FILE = {'iphone': 'Barometer', 's24': 'Pressure'}
ENDPOINT_S, MIN_WALK_S = 2.0, 5.0          # same as cross-day/tilt.py
MAG_B = ['B_mean', 'B_std', 'B_p10', 'B_p90']
MAG_XYZ = ['x_mean', 'y_mean', 'z_mean']
TILT = ['Bv', 'Bh']
V2_MERGE = {'sr8': 'sr9', 'sr10': 'sr9', 'sr11': 'sr9', 'lift_5': 'lift_stairs', 'exit_5_stairs': 'lift_stairs',
            'lift_5_4F': 'lift_stairs_4F', 'exit_5_stairs_4F': 'lift_stairs_4F'}


def config() -> dict:
    # DAY3_CONFIG=<path> reads another config (e.g. to run two session sets side by side); default config.json
    return json.loads((HERE / os.environ.get('DAY3_CONFIG', 'config.json')).read_text())


def handset(model: str) -> str:
    """Handset id (config.json `phones`) of a phyphox deviceModel. An unknown model stops the pipeline (never guessed)."""
    ph = config()['phones']
    if model not in ph:
        raise KeyError(f'device model {model!r} is not in config.json "phones": add it there (id + display)')
    return ph[model]['id']


def display_names() -> dict:
    """handset id -> display name used in the HTML pages, figures and tables (rename `display` in config.json)."""
    return {v['id']: v['display'] for k, v in config()['phones'].items() if not k.startswith('_')}


def places() -> pd.DataFrame:
    n = pd.read_csv((HERE / config()['places_graph']).resolve())
    return n[n['virtual'] == 0].set_index('node_id')


# ----------------------------------------------------------------------------- features
def window_features(t, B, ta=None, A=None, win=5.0):
    """Windows of `win` s over one stop recording. t in s, B (n,3) uT, A (m,3) m/s^2 on the same clock."""
    if len(t) < 10:
        return []
    rate = (len(t) - 1) / max(t[-1] - t[0], 1e-6)
    need = max(10, int(0.5 * rate * win))
    k = ((t - t[0]) // win).astype(int)
    rows = []
    for w in np.unique(k):
        sel = k == w
        if sel.sum() < need:
            continue
        b = B[sel]
        m = np.linalg.norm(b, axis=1)
        r = {'window': int(w), 't0': float(t[sel][0]), 'n': int(sel.sum()), 'B_mean': m.mean(), 'B_std': m.std(),
             'B_p10': np.percentile(m, 10), 'B_p90': np.percentile(m, 90),
             'x_mean': b[:, 0].mean(), 'y_mean': b[:, 1].mean(), 'z_mean': b[:, 2].mean(), 'Bv': np.nan, 'Bh': np.nan}
        if A is not None:
            sa = (ta >= t[sel][0]) & (ta <= t[sel][-1])
            if sa.sum() >= 5:
                g = A[sa].mean(0)
                g = g / np.linalg.norm(g)
                bm = b.mean(0)
                r['Bv'] = float(bm @ g)
                r['Bh'] = float(np.linalg.norm(bm - r['Bv'] * g))
        rows.append(r)
    return rows


def endpoint_features(t, B, ta, A):
    """First and last ENDPOINT_S of a walk (low-pass gravity, as tilt.py)."""
    if t[-1] - t[0] < MIN_WALK_S:
        return {}
    out = {}
    for end, sel, sa in [('start', t <= t[0] + ENDPOINT_S, ta <= ta[0] + ENDPOINT_S),
                         ('end', t >= t[-1] - ENDPOINT_S, ta >= ta[-1] - ENDPOINT_S)]:
        b, g = B[sel].mean(0), A[sa].mean(0)
        g = g / np.linalg.norm(g)
        bv = float(b @ g)
        out[end] = {'B': float(np.linalg.norm(B[sel], axis=1).mean()), 'x': b[0], 'y': b[1], 'z': b[2],
                    'Bv': bv, 'Bh': float(np.linalg.norm(b - bv * g))}
    return out


def track_floor(hpa, threshold, start_floor=5):
    """Barometer step tracking: floor changes when consecutive stops differ by > threshold hPa."""
    cur, prev, out = start_floor, None, []
    for h in hpa:
        if prev is not None and np.isfinite(h):
            cur = max(4, cur - 1) if h - prev > threshold else min(5, cur + 1) if prev - h > threshold else cur
        out.append(cur)
        if np.isfinite(h):
            prev = h
    return np.array(out)


# ----------------------------------------------------------------------------- loaders
def _csv(src: Path) -> np.ndarray | None:
    if not src.exists():
        return None
    c = CACHE / 'csv' / hashlib.md5(str(src).encode()).hexdigest()[:16]
    c = c.with_suffix('.npy')
    if c.exists() and c.stat().st_mtime >= src.stat().st_mtime:
        return np.load(c)
    a = pd.read_csv(src).to_numpy(dtype=np.float64)
    c.parent.mkdir(parents=True, exist_ok=True)
    np.save(c, a)
    return a


def assign_wifi(obs: pd.DataFrame, V: pd.DataFrame, max_gap: float) -> pd.DataFrame:
    """Each observation -> nearest stop visit in time (0 s if inside the dwell), kept if <= max_gap."""
    st, en = V['start'].to_numpy(), V['end'].to_numpy()
    e = obs['epoch'].to_numpy()[:, None]
    gap = np.maximum(0, np.maximum(st[None, :] - e, e - en[None, :]))
    j = gap.argmin(1)
    g = gap[np.arange(len(e)), j]
    obs = obs.assign(visit=V['visit'].to_numpy()[j], gap_s=g, in_window=g == 0)
    return obs[g <= max_gap].reset_index(drop=True)


def load_clean_tree(s: dict, win: float, max_gap: float):
    root = (HERE / s['path']).resolve()
    names = pd.read_csv(HERE / s['names'], dtype={'floor': int}).fillna('')
    nm = names.set_index(['floor', 'node_24nov'])['place_v2'].to_dict()
    m = pd.read_csv(root / 'manifest.csv', dtype=str).fillna('')
    m['floor'] = m['floor'].astype(int)
    day = datetime.fromisoformat(s['day']).replace(tzinfo=HK)
    m['start'] = [(day + timedelta(hours=int(h), minutes=int(mi), seconds=int(sec))).timestamp()
                  for h, mi, sec in (t.split(':') for t in m['start_hk'])]
    m['end'] = m['start'] + m['duration_s'].astype(float)
    m['visit'] = s['id'] + ':' + m['folder']
    # track = the stops one group walked in order (barometer step tracking and Wi-Fi assignment run per track);
    # a manifest without a `track` column (24 Nov) is one track = the session
    m['track'] = s['id'] + ':' + m['track'] if 'track' in m.columns else s['id']
    unmapped = []
    W, E, vrows = [], [], []
    for _, r in m.iterrows():
        folder = root / r['folder'] / r['phone']
        mag = _csv(folder / 'Magnetometer.csv')
        acc = _csv(folder / 'Accelerometer.csv')
        if r['type'] == 'stop':
            place = nm.get((r['floor'], r['node']), '')
            if not place:
                unmapped.append({'session': s['id'], 'floor': int(r['floor']), 'node': r['node'], 'kind': 'stop'})
                continue
            if mag is None:
                continue
            for w in window_features(mag[:, 0], mag[:, 1:4], None if acc is None else acc[:, 0],
                                     None if acc is None else acc[:, 1:4], win):
                W.append({'session': s['id'], 'day': s['day'], 'visit': r['visit'], 'key': f"{r['visit']}:{r['phone']}",
                          'phone': handset(r['device']), 'slot': r['phone'], 'device': r['device'], 'place': place,
                          'floor': int(r['floor']), 'rec_span_s': float(mag[-1, 0] - mag[0, 0]), **w})
        else:
            fp, tp = nm.get((r['floor'], r['from_node']), ''), nm.get((r['floor'], r['to_node']), '')
            for nd, p in [(r['from_node'], fp), (r['to_node'], tp)]:
                if not p:
                    unmapped.append({'session': s['id'], 'floor': int(r['floor']), 'node': nd, 'kind': 'walk end'})
            if mag is None or acc is None:
                continue
            ep = endpoint_features(mag[:, 0], mag[:, 1:4], acc[:, 0], acc[:, 1:4])
            for end, f in ep.items():
                E.append({'session': s['id'], 'day': s['day'], 'walk': r['visit'], 'phone': handset(r['device']), 'slot': r['phone'], 'device': r['device'],
                          'endpoint': end, 'place': fp if end == 'start' else tp, 'floor': int(r['floor']),
                          'walk_start': r['start'], **f})
    stops = m[m['type'] == 'stop']
    for v, g in stops.groupby('visit'):
        place = nm.get((int(g['floor'].iloc[0]), g['node'].iloc[0]), '')
        if not place:
            continue
        row = {'session': s['id'], 'day': s['day'], 'visit': v, 'place': place, 'floor': int(g['floor'].iloc[0]),
               'start': g['start'].min(), 'end': g['end'].max(), 'phones': ' '.join(sorted(g['phone'])), 'track': g['track'].iloc[0]}
        for ph, fn in PRESSURE_FILE.items():
            p = _csv(root / g['folder'].iloc[0] / ph / f'{fn}.csv')
            row[f'hpa_{ph}'] = float(np.median(p[:, 1])) if p is not None and len(p) else np.nan
            row[f'hpa_sd_{ph}'] = float(np.std(p[:, 1])) if p is not None and len(p) else np.nan
        row['devices'] = ' '.join(sorted(set(g['device'])))
        row['handsets'] = ' '.join(sorted(handset(d) for d in set(g['device'])))
        row['iphone_handset'] = ' '.join(sorted({handset(d) for d, sl in zip(g['device'], g['phone']) if sl == 'iphone'}))
        vrows.append(row)
    V = pd.DataFrame(vrows).sort_values('start').reset_index(drop=True)
    wf = root / 'wifi' / 'observations.csv'
    obs = pd.DataFrame()
    if wf.exists():
        cols = pd.read_csv(wf, nrows=0).columns
        o = pd.read_csv(wf, usecols=['scanner_phone', 'source_log', 'bssid', 'rssi', 'epoch'] + (['track'] if 'track' in cols else []))
        o = o.rename(columns={'scanner_phone': 'scanner'})
        if 'track' in o.columns:          # the scanner walked with one track only: assign its rows to that track's stops
            o['track'] = s['id'] + ':' + o['track'].astype(str)
            parts = [assign_wifi(g.drop(columns='track'), V[V['track'] == t].reset_index(drop=True), max_gap)
                     for t, g in o.groupby('track') if (V['track'] == t).any()]
            obs = pd.concat(parts, ignore_index=True) if parts else o.iloc[:0].drop(columns='track').assign(visit='', gap_s=0.0, in_window=False)
            o = o.drop(columns='track')
        else:
            obs = assign_wifi(o, V, max_gap)
        obs['session'] = s['id']
        allobs = o.assign(session=s['id'])
    else:
        allobs = pd.DataFrame()
    return pd.DataFrame(W), V, obs, pd.DataFrame(E), unmapped, allobs


def load_crossday_23nov(s: dict, win: float, max_gap: float):
    sys.path.insert(0, str(NEW / 'cross-day'))
    import crossday as cd
    cd.ensure_23nov_cache()
    lab = pd.read_csv(HERE / s['labels'], dtype=str).fillna('')
    place = dict(zip(lab['stop_id'], lab['label'].str.strip()))
    floor = dict(zip(lab['stop_id'], lab['floor'].astype(int)))
    sess = cd.load_sessions(cd.D_23)
    sessions = sess
    stops = sess[sess['stop_id'].str.startswith('BM')]
    mag, baro = cd.load_sensors(cd.D_23)
    W, vrows = [], []
    for sid, g in mag.groupby('stop_id'):
        g = g.sort_values('timestamp_epoch_s')
        visit = f"{s['id']}:{sid}"
        dev = stops.set_index('stop_id').loc[sid, 'device_model']
        ts = g['timestamp_epoch_s'].to_numpy()
        for w in window_features(ts, g[['x', 'y', 'z']].to_numpy(), win=win):
            W.append({'session': s['id'], 'day': s['day'], 'visit': visit, 'key': f'{visit}:iphone', 'phone': handset(dev), 'slot': 'iphone',
                      'device': dev, 'place': place[sid], 'floor': floor[sid], 'rec_span_s': float(ts[-1] - ts[0]), **w})
    hpa = baro.groupby('stop_id')['hpa'].agg(['median', 'std'])
    for _, r in stops.iterrows():
        sid = r['stop_id']
        vrows.append({'session': s['id'], 'day': s['day'], 'visit': f"{s['id']}:{sid}", 'place': place[sid], 'floor': floor[sid],
                      'start': r['start_epoch_s'], 'end': r['end_epoch_s'], 'phones': 'iphone',
                      'hpa_iphone': float(hpa.loc[sid, 'median']), 'hpa_sd_iphone': float(hpa.loc[sid, 'std']),
                      'hpa_s24': np.nan, 'hpa_sd_s24': np.nan, 'devices': r['device_model'], 'track': s['id'],
                      'handsets': handset(r['device_model']), 'iphone_handset': handset(r['device_model'])})
    V = pd.DataFrame(vrows).sort_values('start').reset_index(drop=True)
    o = pd.read_csv(cd.CACHE23 / 'wifi' / 'observations.csv', usecols=['source_log', 'MAC', 'RSSI', 'Type', 'observation_epoch_s'])
    o = o[o['Type'] == 'WIFI'].rename(columns={'MAC': 'bssid', 'RSSI': 'rssi', 'observation_epoch_s': 'epoch'}).drop(columns='Type')
    o['scanner'] = 's24'          # 23 Nov: one WiGLE log on a Samsung SM-S9280 (crossday.py results.json 'devices')
    obs = assign_wifi(o, V, max_gap)
    obs['session'] = s['id']
    # Walk endpoints from tilt.py (23-Nov walks), v1 labels merged to graph-v2 names. The handset of each walk is read
    # per recording (sessions.csv device_model), not assumed.
    walk_dev = dict(zip(sessions['stop_id'], sessions['device_model']))
    E = pd.DataFrame()
    te = NEW / 'cross-day' / 'out' / 'tilt_endpoints.csv'
    if te.exists():
        t = pd.read_csv(te)
        E = pd.DataFrame({'session': s['id'], 'day': s['day'], 'walk': s['id'] + ':' + t['walk'],
                          'phone': t['walk'].map(lambda w: handset(walk_dev[w])), 'slot': 'iphone',
                          'device': t['walk'].map(walk_dev), 'endpoint': t['endpoint'], 'place': t['place'].map(lambda p: V2_MERGE.get(p, p)),
                          'floor': np.nan, 'walk_start': t['time'], 'B': t['B'], 'x': t['x'], 'y': t['y'], 'z': t['z'],
                          'Bv': t['Bv_lp'], 'Bh': t['Bh_lp'], 'stop_v1': t['pass_stop']})
    return pd.DataFrame(W), V, obs, E, [], o.assign(session=s['id'])


LOADERS = {'clean_tree': load_clean_tree, 'crossday_23nov': load_crossday_23nov}


def load(rebuild=False):
    """Returns dict with W (windows), V (visits), O (assigned Wi-Fi), E (walk endpoints), unmapped, A (all Wi-Fi rows)."""
    cfg = config()
    key = hashlib.md5(json.dumps(cfg, sort_keys=True).encode() + (HERE / 'data.py').read_bytes()
                      + b''.join((HERE / s['names']).read_bytes() for s in cfg['sessions'] if 'names' in s)).hexdigest()[:12]
    pk = CACHE / f'features_{key}.pkl'
    # The pickle is this script's own local cache (written below, gitignored), never downloaded data.
    if pk.exists() and not rebuild:
        return _finish(pickle.loads(pk.read_bytes()))
    parts = {k: [] for k in ['W', 'V', 'O', 'E', 'unmapped', 'A']}
    for s in cfg['sessions']:
        print('loading', s['id'], '...', flush=True)
        res = LOADERS[s['loader']](s, cfg['window_s'], cfg['wifi_nearest_stop_max_gap_s'])
        for k, v in zip(['W', 'V', 'O', 'E', 'unmapped', 'A'], res):
            parts[k].append(v if k != 'unmapped' else v)
    D = {k: pd.concat([p for p in parts[k] if len(p)], ignore_index=True) for k in ['W', 'V', 'O', 'E', 'A']}
    D['unmapped'] = [u for p in parts['unmapped'] for u in p]
    D['config'] = cfg
    CACHE.mkdir(exist_ok=True)
    pk.write_bytes(pickle.dumps(D))
    return _finish(D)


def _finish(D):
    """Default: the original tables (helper columns rec_span_s / stop_v1 dropped). With DAY3_VARIANT: apply_variant."""
    if VARIANT:
        return apply_variant(D, D['config']['variants'][VARIANT])
    D = dict(D)
    D['W'] = D['W'].drop(columns=['rec_span_s'], errors='ignore')
    D['E'] = D['E'].drop(columns=['stop_v1'], errors='ignore')
    return D


# ----------------------------------------------------------------------------- variants (split20)
def apply_variant(D: dict, vc: dict) -> dict:
    """Pieces, exclusions and outlier removal on the stop windows (rules fixed in config.json before any accuracy was seen).

    1. piece j of a take = its windows j*P .. j*P+P-1 (P = piece_s / window_s), i.e. [j*piece_s, (j+1)*piece_s) from the
       take's first magnetometer sample. A piece is 'incomplete' if the take is shorter than (j+1)*piece_s - span_tolerance_s
       or the piece lacks one of its P windows (sensor dropout).
    2. 'excluded': the take's stop is in the exclusion list (session, stop_id); walk endpoints at those stops are dropped too.
    3. 'flat': every window of the piece has an |B| standard deviation below flat_B_std_uT (stuck magnetometer).
    4. outliers, among the complete pieces of one take (needs >= 2): reference = median over the take's pieces of the
       piece |B| median, and the component-wise median of the piece mean field vector.
         'outlier_B'   | piece |B| median - reference | > outlier_B_uT
         'outlier_dir' angle between the piece mean field vector and the reference vector > outlier_angle_deg
    The barometer floor sequence (V) and Wi-Fi are per physical stop and are not changed.
    """
    cfg = D['config']
    win, ps = cfg['window_s'], vc['piece_s']
    per = int(round(ps / win))
    assert abs(per * win - ps) < 1e-9, 'piece_s must be a multiple of window_s'
    W = D['W'].copy()
    W['take'] = W['key']
    W['piece'] = (W['window'] // per).astype(int)
    ex_visits = set()
    if vc.get('exclude'):
        ex = pd.read_csv(HERE / vc['exclude'], dtype=str)
        ex_visits = set(ex['session'] + ':' + ex['stop_id'])
    rows = []
    for (take, j), g in W.groupby(['take', 'piece'], sort=True):
        b = g['B_mean'].to_numpy()
        rows.append({'take': take, 'piece': int(j), 'key': f'{take}#p{j}', 'session': g['session'].iloc[0], 'visit': g['visit'].iloc[0],
                     'phone': g['phone'].iloc[0], 'slot': g['slot'].iloc[0], 'place': g['place'].iloc[0], 'floor': int(g['floor'].iloc[0]),
                     'take_span_s': round(float(g['rec_span_s'].iloc[0]), 2), 'n_windows': len(g),
                     'B_median_uT': float(np.median(b)), 'x': float(g['x_mean'].mean()), 'y': float(g['y_mean'].mean()),
                     'z': float(g['z_mean'].mean()), 'max_window_B_std_uT': float(g['B_std'].max())})
    P = pd.DataFrame(rows)
    P['status'], P['rule_value'], P['rule'] = 'kept', np.nan, ''

    def mark(mask, status, rule, value=None):
        m = mask & (P['status'] == 'kept')
        P.loc[m, 'status'] = status
        P.loc[m, 'rule'] = rule
        if value is not None:
            P.loc[m, 'rule_value'] = np.asarray(value)[m.to_numpy()]

    mark(P['visit'].isin(ex_visits), 'excluded', f"stop in {vc['exclude']}")
    short = (P['piece'] + 1) * ps > P['take_span_s'] + vc['span_tolerance_s']
    mark(short, 'incomplete', f"take shorter than (piece+1)*{ps:g} s - {vc['span_tolerance_s']} s", P['take_span_s'])
    mark(P['n_windows'] < per, 'incomplete', f'dropout: fewer than {per} windows of {win:g} s', P['n_windows'])
    if vc.get('flat_B_std_uT') is not None:
        mark(P['max_window_B_std_uT'] < vc['flat_B_std_uT'], 'flat', f"every window |B| sd < {vc['flat_B_std_uT']} uT", P['max_window_B_std_uT'])
    ok = P['status'] == 'kept'
    P['dev_B_uT'], P['angle_deg'] = np.nan, np.nan
    for take, g in P[ok].groupby('take'):
        if len(g) < 2:
            continue
        v = g[['x', 'y', 'z']].to_numpy()
        ref = np.median(v, 0)
        cos = (v @ ref) / (np.linalg.norm(v, axis=1) * np.linalg.norm(ref))
        P.loc[g.index, 'dev_B_uT'] = g['B_median_uT'] - g['B_median_uT'].median()
        P.loc[g.index, 'angle_deg'] = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    if vc.get('outlier_B_uT') is not None:
        mark(P['dev_B_uT'].abs() > vc['outlier_B_uT'], 'outlier', f"|piece |B| median - take median| > {vc['outlier_B_uT']} uT", P['dev_B_uT'])
    if vc.get('outlier_angle_deg') is not None:
        mark(P['angle_deg'] > vc['outlier_angle_deg'], 'outlier', f"field direction > {vc['outlier_angle_deg']} deg from the take median", P['angle_deg'])
    keep = set(P.loc[P['status'] == 'kept', 'key'])
    W['key'] = W['take'] + '#p' + W['piece'].astype(str)
    W = W[W['key'].isin(keep)].drop(columns=['rec_span_s']).reset_index(drop=True)
    E = D['E']
    if 'stop_v1' in E:
        drop = E['stop_v1'].notna() & (E['session'] + ':' + E['stop_v1'].astype(str)).isin(ex_visits)
        E = E[~drop].drop(columns=['stop_v1']).reset_index(drop=True)
    else:
        drop = pd.Series(False, index=E.index)
    out = dict(D)
    out.update({'W': W, 'E': E, 'pieces': P, 'variant': {'name': VARIANT, **vc, 'walk_endpoints_dropped': int(drop.sum())}})
    return out


def _spread(P):
    """Noise scale the outlier thresholds were set against: deviations of piece |B| medians from their take median
    (pieces that are not the take median itself) and direction changes, over all complete, non-excluded pieces."""
    Q = P[P['dev_B_uT'].notna()]
    d = Q.loc[Q['dev_B_uT'] != 0, 'dev_B_uT'].to_numpy()
    a = Q['angle_deg'].to_numpy()
    q = lambda x, p: round(float(np.quantile(x, p)), 3)
    return {'n_pieces': len(Q), 'dev_B_uT_mad': round(float(np.median(np.abs(d - np.median(d)))), 3),
            'abs_dev_B_uT_quantiles': {'0.5': q(np.abs(d), .5), '0.9': q(np.abs(d), .9), '0.95': q(np.abs(d), .95), '0.99': q(np.abs(d), .99), 'max': q(np.abs(d), 1)},
            'angle_deg_quantiles': {'0.5': q(a, .5), '0.9': q(a, .9), '0.95': q(a, .95), '0.99': q(a, .99), 'max': q(a, 1)}}


def write_variant_report(D):
    """out-<variant>/pieces.csv (every piece, its status and rule value) and variant_summary.json (counts per dataset)."""
    P = D['pieces']
    OUT.mkdir(exist_ok=True)
    cols = ['session', 'take', 'piece', 'key', 'phone', 'slot', 'place', 'floor', 'take_span_s', 'n_windows', 'B_median_uT',
            'dev_B_uT', 'angle_deg', 'status', 'rule', 'rule_value']
    P[cols].round(3).to_csv(OUT / 'pieces.csv', index=False)
    P[P['status'] == 'outlier'][cols].round(3).to_csv(OUT / 'outliers.csv', index=False)
    cnt = lambda g: {k: int(v) for k, v in g['status'].value_counts().items()}
    summ = {'variant': {k: v for k, v in D['variant'].items()},
            'takes': int(P['take'].nunique()), 'pieces_total': len(P), 'pieces_by_status': cnt(P),
            'by_session': {s: {'takes': int(g['take'].nunique()), **cnt(g)} for s, g in P.groupby('session')},
            'by_session_phone': {f'{s}/{ph}': {'takes': int(g['take'].nunique()), **cnt(g)} for (s, ph), g in P.groupby(['session', 'phone'])},
            'take_span_s': {s: [round(float(g['take_span_s'].min()), 2), round(float(g['take_span_s'].max()), 2)] for s, g in P.groupby('session')},
            'kept_pieces_per_take': {str(k): int(v) for k, v in P[P['status'] == 'kept'].groupby('take').size().value_counts().sort_index().items()},
            'takes_with_no_kept_piece': sorted(set(P['take']) - set(P.loc[P['status'] == 'kept', 'take'])),
            'windows_kept': int(len(D['W'])), 'places_kept': int(D['W']['place'].nunique()),
            'within_take_spread': _spread(P)}
    (OUT / 'variant_summary.json').write_text(json.dumps(summ, indent=1))
    return summ


if __name__ == '__main__':
    D = load(rebuild='--rebuild' in sys.argv)
    if VARIANT:
        print(json.dumps(write_variant_report(D), indent=1))
    for k in ['W', 'V', 'O', 'E', 'A']:
        print(k, D[k].shape)
    print(D['W'].groupby(['session', 'phone', 'device']).agg(windows=('key', 'size'), recordings=('key', 'nunique'), tilt=('Bv', lambda x: x.notna().mean())))
    print(D['V'].groupby('session').agg(visits=('visit', 'size'), places=('place', 'nunique')))
    print('unmapped:', sorted({(u['floor'], u['node'], u['kind']) for u in D['unmapped']}))
