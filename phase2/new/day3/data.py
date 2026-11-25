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
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
CACHE = HERE / 'cache'
OUT = HERE / 'out'
HK = timezone(timedelta(hours=8))
PRESSURE_FILE = {'iphone': 'Barometer', 's24': 'Pressure'}
ENDPOINT_S, MIN_WALK_S = 2.0, 5.0          # same as cross-day/tilt.py
MAG_B = ['B_mean', 'B_std', 'B_p10', 'B_p90']
MAG_XYZ = ['x_mean', 'y_mean', 'z_mean']
TILT = ['Bv', 'Bh']
V2_MERGE = {'sr8': 'sr9', 'sr10': 'sr9', 'sr11': 'sr9', 'lift_5': 'lift_stairs', 'exit_5_stairs': 'lift_stairs',
            'lift_5_4F': 'lift_stairs_4F', 'exit_5_stairs_4F': 'lift_stairs_4F'}


def config() -> dict:
    return json.loads((HERE / 'config.json').read_text())


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
                          'floor': int(r['floor']), **w})
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
               'start': g['start'].min(), 'end': g['end'].max(), 'phones': ' '.join(sorted(g['phone']))}
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
        o = pd.read_csv(wf, usecols=['scanner_phone', 'source_log', 'bssid', 'rssi', 'epoch'])
        o = o.rename(columns={'scanner_phone': 'scanner'})
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
        for w in window_features(g['timestamp_epoch_s'].to_numpy(), g[['x', 'y', 'z']].to_numpy(), win=win):
            W.append({'session': s['id'], 'day': s['day'], 'visit': visit, 'key': f'{visit}:iphone', 'phone': handset(dev), 'slot': 'iphone',
                      'device': dev, 'place': place[sid], 'floor': floor[sid], **w})
    hpa = baro.groupby('stop_id')['hpa'].agg(['median', 'std'])
    for _, r in stops.iterrows():
        sid = r['stop_id']
        vrows.append({'session': s['id'], 'day': s['day'], 'visit': f"{s['id']}:{sid}", 'place': place[sid], 'floor': floor[sid],
                      'start': r['start_epoch_s'], 'end': r['end_epoch_s'], 'phones': 'iphone',
                      'hpa_iphone': float(hpa.loc[sid, 'median']), 'hpa_sd_iphone': float(hpa.loc[sid, 'std']),
                      'hpa_s24': np.nan, 'hpa_sd_s24': np.nan, 'devices': r['device_model'],
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
                          'Bv': t['Bv_lp'], 'Bh': t['Bh_lp']})
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
        return pickle.loads(pk.read_bytes())
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
    return D


if __name__ == '__main__':
    D = load(rebuild='--rebuild' in sys.argv)
    for k in ['W', 'V', 'O', 'E', 'A']:
        print(k, D[k].shape)
    print(D['W'].groupby(['session', 'phone', 'device']).agg(windows=('key', 'size'), recordings=('key', 'nunique'), tilt=('Bv', lambda x: x.notna().mean())))
    print(D['V'].groupby('session').agg(visits=('visit', 'size'), places=('place', 'nunique')))
    print('unmapped:', sorted({(u['floor'], u['node'], u['kind']) for u in D['unmapped']}))
