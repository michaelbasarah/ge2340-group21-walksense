#!/usr/bin/env python3
"""GE2340 WalkSense - leakage-reduced and cross-day positioning evaluation.

23 Nov is the reference dataset: its stop IDs, place names and clean.py pipeline.
Labels come from labels_23nov_confirmed.csv (editable; pre-filled with the provisional
labels). 17 Nov is mapped onto 23-Nov places by crosswalk_17nov_to_23nov.csv.

  MAIN       23 Nov only. Places visited more than once: train on every other stop,
             test on the LATEST visit of each revisited place (different time, same day).
  SECONDARY  Train on 23 Nov, test on 17 Nov, for places both days share (true cross-day).
  BASELINE   Same-day block split: inside every stop, the first 60% of the time trains
             and the last 40% tests (one 2 s window gap). This is the leaky number.

Run (from anywhere):   python phase2/new/cross-day/crossday.py
Needs: numpy pandas scikit-learn matplotlib.   Everything is written to ./out/.

  --v2   score on the graph-v2 merged places instead (../graph-v2/labels_23nov_merged.csv:
         study rooms sr8/sr10/sr11 -> sr9, lift+stairs -> lift_stairs / lift_stairs_4F).
         The 17-Nov crosswalk and the floor-5 map names are merged the same way.
         Writes to ./out-v2/ and leaves ./out/ untouched.

The 23-Nov sensor CSVs are gitignored. On the first run this script copies the team's
unmodified clean-data/2026-11-23/clean.py into ./cache/2026-11-23/ and runs it there with
--source pointing at the repo's raw/attachments, so nothing in clean-data/ is rewritten.

Reused from the unmerged 16-Nov prep/training branch (phase2/training/pipeline.py): the
model set-up (median impute + StandardScaler, distance-weighted kNN, 200-tree
class-balanced random forest with seed 21) and the per-recording majority vote.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
PHASE2 = HERE.parent.parent   # phase2/ (this folder is phase2/new/cross-day/)
D17 = PHASE2 / 'clean-data' / '2026-11-17'
D23 = PHASE2 / 'clean-data' / '2026-11-23'
CACHE23 = HERE / 'cache' / '2026-11-23'
OUT = HERE / 'out'
LABELS = HERE / 'labels_23nov_confirmed.csv'
# graph-v2 merges (copied from ../graph-v2/merge_v2.py MERGE; used only with --v2)
V2_MERGE = {'sr8': 'sr9', 'sr10': 'sr9', 'sr11': 'sr9',
            'lift_5': 'lift_stairs', 'exit_5_stairs': 'lift_stairs',
            'lift_5_4F': 'lift_stairs_4F', 'exit_5_stairs_4F': 'lift_stairs_4F'}
PLACE_MAP = {}            # empty = v1 names; set to V2_MERGE by --v2
D_17, D_23 = '17Nov', '23Nov'

WINDOW_S = 2.0            # magnetometer window (same as the pilot and the prep pipeline)
MIN_MAG_READINGS = 100    # both days log the magnetometer at ~100 Hz -> ~200 per window
WIFI_CHUNK_S = 10.0       # Wi-Fi rows of one stop grouped into 10 s chunks
TRAIN_FRACTION = 0.6      # block-split baseline: first 60% of each stop trains
SEED = 21
MAG_ONLY = ['mag_mean', 'mag_std', 'mag_p10', 'mag_p90']   # field strength only: orientation-free
MAG_XYZ = MAG_ONLY + ['x_mean', 'y_mean', 'z_mean']        # depends on how the phone is held
FEATURES = {'mag': {'magnitude': MAG_ONLY, 'magnitude_xyz': MAG_XYZ}, 'wifi': {'rssi': 'rssi', 'presence': 'presence'}}

# Colours: validated categorical slots 1-2, greys for the leaky baselines.
C_BLOCK17, C_BLOCK23, C_MAIN, C_CROSS = '#c3c2b7', '#8a8983', '#2a78d6', '#eb6834'
C_F5, C_F4 = '#2a78d6', '#eb6834'
INK, INK2 = '#0b0b0b', '#52514e'


# ============================================================================ data
def ensure_23nov_cache():
    if (CACHE23 / 'sensors' / 'magnetometer.csv').exists() and (CACHE23 / 'sensors' / 'barometer.csv').exists():
        return
    CACHE23.mkdir(parents=True, exist_ok=True)
    shutil.copy2(D23 / 'clean.py', CACHE23 / 'clean.py')
    print('Regenerating 23-Nov sensor CSVs with an unmodified copy of clean-data/2026-11-23/clean.py ...')
    subprocess.run([sys.executable, str(CACHE23 / 'clean.py'), '--source', str(D23 / 'raw' / 'attachments')],
                   check=True, cwd=CACHE23, stdout=subprocess.DEVNULL)
    a = (CACHE23 / 'sessions.csv').read_text().replace('\r\n', '\n')
    b = (D23 / 'sessions.csv').read_text().replace('\r\n', '\n')
    if a != b:
        raise SystemExit('Regenerated 23-Nov sessions.csv differs from the committed one - stopping.')


def load_sensors(day):
    base, col = (D17, 'session_id') if day == D_17 else (CACHE23, 'stop_id')
    mag = pd.read_csv(base / 'sensors' / 'magnetometer.csv', usecols=[col, 'timestamp_epoch_s', 'x', 'y', 'z', 'vector_magnitude'])
    baro = pd.read_csv(base / 'sensors' / 'barometer.csv', usecols=[col, 'timestamp_epoch_s', 'x'])
    mag, baro = mag.rename(columns={col: 'stop_id'}), baro.rename(columns={col: 'stop_id', 'x': 'hpa'})
    return mag[mag['stop_id'].str.startswith('BM')], baro[baro['stop_id'].str.startswith('BM')]


def load_wifi(day):
    if day == D_17:
        obs = pd.read_csv(D17 / 'wifi' / 'observations.csv', usecols=['wifi_observation_id', 'MAC', 'RSSI', 'observation_epoch_s'])
        assoc = pd.read_csv(D17 / 'wifi' / 'stop_associations_provisional.csv', usecols=['wifi_observation_id', 'session_id'])
        w = assoc.drop_duplicates('wifi_observation_id').merge(obs, on='wifi_observation_id').rename(
            columns={'session_id': 'stop_id', 'observation_epoch_s': 'epoch'})
    else:
        w = pd.read_csv(D23 / 'wifi' / 'stop_associations_provisional.csv').drop_duplicates('wifi_observation_id')
        w['epoch'] = (pd.to_datetime(w['observation_time_hk'], utc=True) - pd.Timestamp('1970-01-01', tz='UTC')).dt.total_seconds().astype(int)
    return w[['stop_id', 'epoch', 'MAC', 'RSSI']]


def load_sessions(day):
    s = pd.read_csv((D17 if day == D_17 else D23) / 'sessions.csv')
    return s[['session_id', 'kind', 'source_zip', 'device_model', 'start_epoch_s', 'end_epoch_s']].rename(columns={'session_id': 'stop_id'})


def walk_files_23(sessions):
    """For every 23-Nov stop: did a walk file ('From X') start before the next stop?"""
    s = sessions.sort_values('start_epoch_s').reset_index(drop=True)
    stops = s[s['stop_id'].str.startswith('BM')].reset_index(drop=True)
    walks = s[s['kind'] == 'movement']
    info = {}
    for i, r in stops.iterrows():
        nxt = stops['start_epoch_s'].iloc[i + 1] if i + 1 < len(stops) else np.inf
        prv = stops['end_epoch_s'].iloc[i - 1] if i > 0 else -np.inf
        after = walks[(walks['start_epoch_s'] >= r['end_epoch_s'] - 30) & (walks['start_epoch_s'] < nxt)]
        before = walks[(walks['start_epoch_s'] >= prv - 30) & (walks['start_epoch_s'] < r['start_epoch_s'])]
        info[r['stop_id']] = {'own_walk_file': after['source_zip'].iloc[0] if len(after) else '',
                              'walk_before': before['source_zip'].iloc[0] if len(before) else '',
                              'start': r['start_epoch_s'], 'end': r['end_epoch_s']}
    return info


def load_labels(walks):
    lab = pd.read_csv(LABELS, dtype=str).fillna('')
    lab['place'] = lab['label'].str.strip()
    lab['floor'] = lab['floor'].astype(int)
    lab['confirmed'] = lab['confirmed'].str.strip().str.lower().isin(['yes', 'y', 'true', '1'])
    lab['own_walk_file'] = lab['stop_id'].map(lambda s: walks[s]['own_walk_file'])
    lab['label_ok'] = (lab['place'] != '') & ~lab['place'].str.startswith('(')
    # Rule: a label is used if the team confirmed it, or if the stop has its own 'From X' walk file
    # (labels of stops without one were copied from the next stop by clean.py).
    lab['usable'] = lab['label_ok'] & (lab['confirmed'] | (lab['own_walk_file'] != ''))
    lab['reason_if_excluded'] = np.where(~lab['label_ok'], 'no label', np.where(lab['usable'], '', 'label copied from next stop; not confirmed'))
    return lab


# ============================================================================ features
def magnetic_windows(mag, day):
    rows = []
    for sid, g in mag.groupby('stop_id'):
        t = g['timestamp_epoch_s'].to_numpy()
        w = ((t - t.min()) // WINDOW_S).astype(int)
        for k in np.unique(w):
            gw = g[w == k]
            if len(gw) < MIN_MAG_READINGS:
                continue
            m = gw['vector_magnitude'].to_numpy()
            rows.append({'key': f'{day}:{sid}', 'window': int(k), 'mag_mean': m.mean(), 'mag_std': m.std(),
                         'mag_p10': np.percentile(m, 10), 'mag_p90': np.percentile(m, 90),
                         'x_mean': gw['x'].mean(), 'y_mean': gw['y'].mean(), 'z_mean': gw['z'].mean()})
    return pd.DataFrame(rows)


def wifi_chunks(wifi, day):
    """One sample per 10 s chunk of a stop: strongest RSSI per access point (BSSID)."""
    rows = []
    for sid, g in wifi.groupby('stop_id'):
        k = ((g['epoch'] - g['epoch'].min()) // WIFI_CHUNK_S).astype(int)
        for c, gc in g.groupby(k):
            rows.append({'key': f'{day}:{sid}', 'window': int(c), 'aps': gc.groupby('MAC')['RSSI'].max().to_dict()})
    return pd.DataFrame(rows)


def matrix(df, fs, vocab):
    if fs not in ('rssi', 'presence'):
        return df[fs].to_numpy(float)
    x = np.full((len(df), len(vocab)), -100.0 if fs == 'rssi' else 0.0)   # -100 = "not heard", a modelling choice
    idx = {m: i for i, m in enumerate(vocab)}
    for r, aps in enumerate(df['aps']):
        for mac, rssi in aps.items():
            if mac in idx:
                x[r, idx[mac]] = rssi if fs == 'rssi' else 1.0
    return x


# ============================================================================ models
def make_model(kind, n_train):
    """Adapted from prep/training pipeline.py fit_model()."""
    clf = KNeighborsClassifier(n_neighbors=max(1, min(5, n_train)), weights='distance') if kind == 'knn' else \
        RandomForestClassifier(n_estimators=200, random_state=SEED, class_weight='balanced', n_jobs=1)
    return Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler()), ('clf', clf)])


def fit_predict(kind, xtr, ytr, xte, ftr=None, fte=None):
    """Plain model, or fusion: one model per floor, chosen by the barometer floor."""
    if ftr is None:
        return make_model(kind, len(ytr)).fit(xtr, ytr).predict(xte)
    pred = np.empty(len(xte), dtype=object)
    for f in np.unique(fte):
        te, tr = fte == f, ftr == f
        if not tr.any():
            tr = np.ones(len(ytr), bool)
        pred[te] = make_model(kind, int(tr.sum())).fit(xtr[tr], ytr[tr]).predict(xte[te])
    return pred


def score(keys, truth, pred, place_floor, adj, full=True):
    keys, truth, pred = np.asarray(keys), np.asarray(truth, dtype=object), np.asarray(pred, dtype=object)
    votes = defaultdict(list)
    for k, p in zip(keys, pred):
        votes[k].append(p)
    voted = {k: sorted(Counter(v).items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, v in votes.items()}  # ties: alphabetical
    tmap = dict(zip(keys, truth))
    vk = sorted(voted)
    vt, vp = [tmap[k] for k in vk], [voted[k] for k in vk]
    near = lambda t, p: p == t or p in adj.get(t, set())
    classes = sorted(set(truth) | set(pred))
    res = {'n_test_visits': len(vk), 'n_test_windows': int(len(truth)),
           'visit_place_accuracy': round(float(np.mean([a == b for a, b in zip(vt, vp)])), 3),
           'visit_within_one_neighbour': round(float(np.mean([near(a, b) for a, b in zip(vt, vp)])), 3),
           'visit_floor_accuracy': round(float(np.mean([place_floor[a] == place_floor[b] for a, b in zip(vt, vp)])), 3),
           'window_place_accuracy': round(float(np.mean(truth == pred)), 3),
           'window_within_one_neighbour': round(float(np.mean([near(a, b) for a, b in zip(truth, pred)])), 3),
           'window_floor_accuracy': round(float(np.mean([place_floor[a] == place_floor[b] for a, b in zip(truth, pred)])), 3),
           'test_visits_per_class': dict(sorted(Counter(vt).items()))}
    if full:
        res['visit_predictions'] = {k: {'true': tmap[k], 'pred': voted[k]} for k in vk}
        res['window_confusion'] = {'labels': classes, 'matrix': pd.crosstab(
            pd.Categorical(truth, categories=classes), pd.Categorical(pred, categories=classes), dropna=False).values.tolist()}
    return res


def evaluate(F, modality, tr_mask, te_mask, place_of, floor_of, place_floor, adj, full=True):
    """All feature sets x {kNN, RF} x {plain, barometer-floor fusion} for one train/test split."""
    tr, te = F[tr_mask].reset_index(drop=True), F[te_mask].reset_index(drop=True)
    ytr = np.array([place_of[k] for k in tr['key']], dtype=object)
    yte = np.array([place_of[k] for k in te['key']], dtype=object)
    ftr = np.array([place_floor[y] for y in ytr])
    fte = np.array([floor_of[k] for k in te['key']])
    vocab = sorted({m for aps in tr['aps'] for m in aps}) if modality == 'wifi' else None
    n_cls = len(set(ytr))
    out = {'_split': {'train_visits': int(tr['key'].nunique()), 'train_places': n_cls,
                      'chance_accuracy': round(1 / n_cls, 3) if n_cls else None,
                      'test_visits': sorted(te['key'].unique().tolist())}}
    for fs_name, fs in FEATURES[modality].items():
        xtr, xte = matrix(tr, fs, vocab), matrix(te, fs, vocab)
        for kind in ['knn', 'rf']:
            for fused in [False, True]:
                pred = fit_predict(kind, xtr, ytr, xte, ftr if fused else None, fte if fused else None)
                out[f'{fs_name}_{kind}' + ('_baro_floor' if fused else '')] = score(te['key'], yte, pred, place_floor, adj, full)
    return out


def block_masks(F, keys, gap):
    """Inside each stop: earliest 60% of windows -> train, skip `gap` windows, rest -> test."""
    tr, te = np.zeros(len(F), bool), np.zeros(len(F), bool)
    for k in keys:
        idx = np.where(F['key'].to_numpy() == k)[0]
        idx = idx[np.argsort(F['window'].to_numpy()[idx])]
        if len(idx) < 2 + gap:
            tr[idx] = True
            continue
        n = max(1, int(round(len(idx) * TRAIN_FRACTION)))
        tr[idx[:n]] = True
        te[idx[n + gap:]] = True
    return tr, te


# ============================================================================ floor
def floors(press, true_floor, sessions):
    """Barometer: within-day sanity check and floor estimates trained on the other day."""
    stats, res, pred = {}, {}, {}
    for d in [D_17, D_23]:
        p = press[d]
        f = p['key'].map(true_floor).to_numpy()
        dp, ch = np.diff(p['hpa'].to_numpy()), np.diff(f) != 0
        f5 = p[f == 5]
        srt = np.sort(p['hpa'].to_numpy()); i = int(np.argmax(np.diff(srt)))
        within = np.where(p['hpa'] > (srt[i] + srt[i + 1]) / 2, 4, 5)
        stats[d] = {'f5_median_hpa': round(float(f5['hpa'].median()), 3),
                    'f4_median_hpa': round(float(p[f == 4]['hpa'].median()), 3),
                    'floor_step_hpa_median': round(float(np.median(np.abs(dp[ch]))), 3),
                    'largest_same_floor_consecutive_change_hpa': round(float(np.max(np.abs(dp[~ch]))), 3),
                    'f5_drift_hpa_per_hour': round(float(np.polyfit((f5['t'] - f5['t'].min()) / 3600, f5['hpa'], 1)[0]), 3),
                    'f5_range_hpa': round(float(f5['hpa'].max() - f5['hpa'].min()), 3),
                    'within_day_largest_gap_split_agrees_with_label_floor': f'{int((within == f).sum())}/{len(p)}',
                    'n_stops': len(p)}
    for tr, te in [(D_17, D_23), (D_23, D_17)]:
        a, b = press[tr], press[te]
        fa, fb = a['key'].map(true_floor).to_numpy(), b['key'].map(true_floor).to_numpy()
        f5a, f4a = a['hpa'][fa == 5].median(), a['hpa'][fa == 4].median()
        thr = (f5a + f4a) / 2
        absolute = np.where(b['hpa'] > thr, 4, 5)
        offset = b['hpa'].iloc[0] - f5a                    # app knows the first stop is on floor 5 (true both days)
        calibrated = np.where(b['hpa'] - offset > thr, 4, 5)
        T = stats[tr]['floor_step_hpa_median'] / 2         # floor change if consecutive stops differ by > half a step
        cur, prev, trk = 5, None, []
        for h in b['hpa']:
            if prev is not None:
                cur = max(4, cur - 1) if h - prev > T else min(5, cur + 1) if prev - h > T else cur
            trk.append(cur); prev = h
        trk = np.array(trk)
        ok = lambda x: {'stops_correct': f'{int((x == fb).sum())}/{len(fb)}', 'accuracy': round(float(np.mean(x == fb)), 3)}
        res[f'train_{tr}_test_{te}'] = {
            'absolute_threshold_from_train_day': {'threshold_hpa': round(float(thr), 3), **ok(absolute)},
            'start_calibrated_threshold': {'offset_hpa': round(float(offset), 3), **ok(calibrated)},
            'step_tracking': {'jump_threshold_hpa': round(float(T), 3), **ok(trk)}}
        pred.update(dict(zip(b['key'], trk)))
    return stats, res, pred


# ============================================================================ adjacency
MAP_NAMES = {'Exit 5 (emergency exit)': 'exit_5', 'Exit by bathroom (emergency)': 'exit_10',
             'Canteen (entrance)': 'canteen', 'Male toilet': 'male_toilet', 'Female toilet': 'female_toilet',
             'Y5-302': 'y5302', 'Y5-202': 'y5202', 'Study Room 8 (Y5-511)': 'sr8', 'Study Room 9 (Y5-512)': 'sr9',
             'Study Room 10 (Y5-513)': 'sr10', 'Study Room 11 (Y5-514)': 'sr11'}


def adjacency(routes):
    """Neighbours = consecutive labelled stops on either route + floor-5 map edges (map/edges_floor5.csv)."""
    adj = defaultdict(set)
    for seq in routes:
        for a, b in zip(seq, seq[1:]):
            if a and b and a != b:
                adj[a].add(b); adj[b].add(a)
    e = pd.read_csv(PHASE2 / 'map' / 'edges_floor5.csv')
    for a, b in zip(e['from'], e['to']):
        if a in MAP_NAMES and b in MAP_NAMES:
            na, nb = (PLACE_MAP.get(MAP_NAMES[x], MAP_NAMES[x]) for x in (a, b))
            if na != nb:
                adj[na].add(nb); adj[nb].add(na)
    return adj


# ============================================================================ figures
def style(ax):
    for s in ['top', 'right']:
        ax.spines[s].set_visible(False)
    for s in ['left', 'bottom']:
        ax.spines[s].set_color('#b5b4ad')
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis='y', color='#e6e5e0', linewidth=0.8); ax.set_axisbelow(True)


def fig_pressure(press, true_floor):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, d in zip(axes, [D_23, D_17]):
        p = press[d]
        fl = p['key'].map(true_floor)
        mins = (p['t'] - p['t'].min()) / 60
        ax.plot(mins, p['hpa'], color='#b5b4ad', linewidth=1, zorder=1)
        for f, c in [(5, C_F5), (4, C_F4)]:
            m = (fl == f).to_numpy()
            ax.scatter(mins[m], p['hpa'][m], s=36, color=c, edgecolor='white', linewidth=1.5, zorder=2, label=f'floor {f} stop')
        ax.invert_yaxis()
        ax.set_title(f'{d[:2]} Nov: median pressure per stop', fontsize=10, color=INK, loc='left')
        ax.set_xlabel('minutes since first stop', fontsize=9, color=INK2)
        ax.set_ylabel('hPa (higher = lower floor)', fontsize=9, color=INK2)
        style(ax); ax.legend(frameon=False, fontsize=8, loc='center right')
    fig.tight_layout(); fig.savefig(OUT / 'fig_pressure_by_stop.png', dpi=150); plt.close(fig)


def fig_overview(R):
    methods = [('mag', 'magnitude_knn', 'Magnetic |B|\nkNN'), ('mag', 'magnitude_knn_baro_floor', 'Baro floor +\nmagnetic |B| kNN'),
               ('mag', 'magnitude_xyz_knn', 'Magnetic |B|+xyz\nkNN'), ('mag', 'magnitude_xyz_knn_baro_floor', 'Baro floor +\nmagnetic |B|+xyz kNN'),
               ('wifi', 'rssi_knn', 'Wi-Fi RSSI\nkNN'), ('wifi', 'rssi_rf', 'Wi-Fi RSSI\nRF'), ('wifi', 'rssi_rf_baro_floor', 'Baro floor +\nWi-Fi RSSI RF')]
    series = [('block_23', 'Same visit, time split (23 Nov, leaky)', C_BLOCK23),
              ('revisit_23', 'Later revisit, same day (23 Nov, main)', C_MAIN),
              ('block_17', 'Same visit, time split (17 Nov, core places, leaky)', C_BLOCK17),
              ('cross_core', 'Other day: train 23 Nov, test 17 Nov (core places)', C_CROSS)]
    fig, ax = plt.subplots(figsize=(11.5, 5.4))
    w = 0.19
    for j, (sk, lab, col) in enumerate(series):
        xs = np.arange(len(methods)) + (j - 1.5) * w
        for x, (mod, m, _) in zip(xs, methods):
            block = R[sk][mod]
            v = block[m]['visit_place_accuracy']
            ax.bar(x, v, width=w - 0.02, color=col, edgecolor='white', linewidth=1, label=lab if x == xs[0] else None)
            ch = block['_split']['chance_accuracy']
            ax.plot([x - w / 2 + 0.01, x + w / 2 - 0.01], [ch, ch], color=INK, linewidth=1, linestyle=(0, (1.5, 1.5)))
            if sk in ('revisit_23', 'cross_core'):
                ax.text(x, v + 0.015, f'{v:.0%}', ha='center', va='bottom', fontsize=7, color=INK)
    ax.set_xticks(range(len(methods))); ax.set_xticklabels([n for _, _, n in methods], fontsize=8)
    ax.set_ylim(0, 1.1); ax.set_ylabel('place accuracy per stop visit', fontsize=9, color=INK2)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title('Place accuracy: same visit vs later revisit vs other day (dotted tick = chance for that split)',
                 fontsize=10, loc='left', color=INK)
    style(ax); ax.legend(frameon=False, fontsize=8, ncol=2, loc='upper left', bbox_to_anchor=(0, -0.16))
    fig.tight_layout(); fig.savefig(OUT / 'fig_accuracy_overview.png', dpi=150); plt.close(fig)


def fig_confusion(panels, title, fname):
    fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 6.2), gridspec_kw={'wspace': 0.75})
    axes = np.atleast_1d(axes)
    for ax, (sub, r) in zip(axes, panels):
        labels = r['window_confusion']['labels']; m = np.array(r['window_confusion']['matrix'], float)
        rows = m.sum(1) > 0
        cols = m.sum(0) > 0
        m = m[rows][:, cols]
        ylab = [l for l, k in zip(labels, rows) if k]; xlab = [l for l, k in zip(labels, cols) if k]
        n = m.sum(1, keepdims=True)
        im = ax.imshow(m / n, cmap='Blues', vmin=0, vmax=1, aspect='auto')
        ax.set_xticks(range(len(xlab))); ax.set_xticklabels(xlab, rotation=90, fontsize=7)
        ax.set_yticks(range(len(ylab))); ax.set_yticklabels([f'{l}  (n={int(k)})' for l, k in zip(ylab, n.ravel())], fontsize=7)
        ax.set_xlabel('predicted place', fontsize=8, color=INK2); ax.set_ylabel('true place (n = test windows)', fontsize=8, color=INK2)
        ax.set_title(f'{sub}\nvisit acc {r["visit_place_accuracy"]:.0%} (n={r["n_test_visits"]}), window acc {r["window_place_accuracy"]:.0%}',
                     fontsize=9, loc='left', color=INK)
    fig.colorbar(im, ax=list(axes), shrink=0.6, label='share of the row')
    fig.suptitle(title, fontsize=10, x=0.01, ha='left', color=INK)
    fig.savefig(OUT / fname, dpi=150, bbox_inches='tight'); plt.close(fig)


def fig_mag_stability(M, place_of, shared, place_floor):
    pts = []
    for pid in shared:
        v = [M[M['key'].str.startswith(d) & (M['key'].map(place_of) == pid)]['mag_mean'].mean() for d in [D_17, D_23]]
        pts.append((pid, v[0], v[1], place_floor[pid]))
    fig, ax = plt.subplots(figsize=(6, 5.6))
    lo = min(min(p[1], p[2]) for p in pts) - 3; hi = max(max(p[1], p[2]) for p in pts) + 3
    ax.plot([lo, hi], [lo, hi], color='#b5b4ad', linewidth=1, linestyle=(0, (3, 3)))
    for f, c in [(5, C_F5), (4, C_F4)]:
        sel = [p for p in pts if p[3] == f]
        ax.scatter([p[1] for p in sel], [p[2] for p in sel], s=48, color=c, edgecolor='white', linewidth=1.5, label=f'floor {f}', zorder=2)
    for p in pts:
        ax.annotate(p[0], (p[1], p[2]), fontsize=7, color=INK2, xytext=(4, 3), textcoords='offset points')
    r = np.corrcoef([p[1] for p in pts], [p[2] for p in pts])[0, 1]
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_xlabel('17 Nov mean |B| (uT)', fontsize=9, color=INK2); ax.set_ylabel('23 Nov mean |B| (uT)', fontsize=9, color=INK2)
    ax.set_title(f'Field strength per shared place, 17 vs 23 Nov (r = {r:.2f})', fontsize=10, loc='left', color=INK)
    style(ax); ax.grid(axis='x', color='#e6e5e0', linewidth=0.8); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / 'fig_magnetic_17_vs_23.png', dpi=150); plt.close(fig)
    return round(float(r), 3), pts


# ============================================================================ main
def main():
    global OUT, LABELS, PLACE_MAP
    if '--v2' in sys.argv[1:]:
        OUT, LABELS, PLACE_MAP = HERE / 'out-v2', HERE.parent / 'graph-v2' / 'labels_23nov_merged.csv', V2_MERGE
    OUT.mkdir(exist_ok=True)
    ensure_23nov_cache()

    sessions = {d: load_sessions(d) for d in [D_17, D_23]}
    walks = walk_files_23(sessions[D_23])
    lab = load_labels(walks)
    cw = pd.read_csv(HERE / 'crosswalk_17nov_to_23nov.csv', dtype=str).fillna('')
    rank = {'high': 3, 'medium': 2, 'low': 1, 'none': 0}
    cw['rank'] = cw['confidence'].map(rank)

    # Place table (23-Nov names) and per-visit place labels.
    use23 = lab[lab['usable']]
    place_of = {f'{D_23}:{s}': p for s, p in zip(use23['stop_id'], use23['place'])}
    place_floor = dict(zip(use23['place'], use23['floor']))
    places23 = set(use23['place'])
    cw['place'] = cw['place_23nov'].str.strip().map(lambda p: PLACE_MAP.get(p, p))
    cw_ok = cw[(cw['rank'] >= 2) & cw['place'].isin(places23)]
    for s, p in zip(cw_ok['stop_id_17nov'], cw_ok['place']):
        place_of[f'{D_17}:{s}'] = p
    tier_of = cw_ok.groupby('place')['rank'].min()
    shared = {'core': sorted(tier_of[tier_of == 3].index), 'extended': sorted(tier_of.index)}

    # True floors (from labels/route) for every stop, used for the barometer checks.
    true_floor = {f'{D_23}:{s}': f for s, f in zip(lab['stop_id'], lab['floor'])}
    true_floor.update({f'{D_17}:{s}': int(f) for s, f in zip(cw['stop_id_17nov'], cw['floor_17nov'])})

    mags, wifis, press = [], [], {}
    for d in [D_17, D_23]:
        mag, baro = load_sensors(d)
        mags.append(magnetic_windows(mag, d))
        wifis.append(wifi_chunks(load_wifi(d), d))
        p = baro.groupby('stop_id').agg(hpa=('hpa', 'median'), t=('timestamp_epoch_s', 'min')).reset_index()
        p['key'] = d + ':' + p['stop_id']
        press[d] = p.sort_values('t').reset_index(drop=True)
    M, W = pd.concat(mags, ignore_index=True), pd.concat(wifis, ignore_index=True)
    floor_stats, floor_res, floor_of = floors(press, true_floor, sessions)

    routes = [[place_of.get(f'{D_23}:{s}') for s in lab['stop_id']],
              [place_of.get(f'{D_17}:{s}') if r >= 2 else None for s, r in zip(cw['stop_id_17nov'], cw['rank'])]]
    adj = adjacency(routes)

    # ---- revisit check (route order, timing, barometer) for every repeated 23-Nov label
    hpa23 = dict(zip(press[D_23]['stop_id'], press[D_23]['hpa']))
    rev_rows = []
    for place, g in lab[lab['label_ok']].groupby('place'):
        if len(g) < 2:
            continue
        for s in g['stop_id']:
            r = lab[lab['stop_id'] == s].iloc[0]
            first = walks[g['stop_id'].iloc[0]]['start']
            rev_rows.append({'place': place, 'stop_id': s, 'start_hk': pd.Timestamp(walks[s]['start'], unit='s', tz='Asia/Hong_Kong').strftime('%H:%M'),
                             'minutes_after_first_visit': round((walks[s]['start'] - first) / 60, 1),
                             'median_hpa': round(hpa23[s], 2), 'walk_file_before': walks[s]['walk_before'],
                             'own_walk_file_after': walks[s]['own_walk_file'],
                             'confirmed': bool(r['confirmed']),
                             'verdict': ('used: confirmed' if r['confirmed'] else 'used: own walk file') if r['usable'] else
                                        'excluded: no own walk file and not confirmed',
                             'used': bool(r['usable'])})
    prov = pd.read_csv(D23 / 'locations_provisional.csv', dtype=str).set_index('stop_id')
    srt = np.sort(press[D_23]['hpa'].to_numpy()); gi = int(np.argmax(np.diff(srt)))
    baro_floor = {s: (4 if h > (srt[gi] + srt[gi + 1]) / 2 else 5) for s, h in hpa23.items()}
    norm = lambda t: ''.join(ch for ch in t.lower() if ch.isalnum())
    same = {('canteen', 'canteen'), ('exitlift5', 'exit5'), ('exitlift10', 'exit10'), ('escanaik', 'escalatorup'),
            ('escanaikatas', 'escalatorup'), ('escaturunatas', 'escalatordown'), ('maletoilet', 'maletoilet'),
            ('femaletoilet', 'femaletoilet'), ('disabledtoilet', 'disabledtoilet'), ('lift5', 'lift5'),
            ('exit5stairs', 'exit5stairs'), ('exit5stairsbawah', 'exit5stairs4f'), ('lift5bawah', 'lift54f'),
            ('disabledtoiletbawah', 'disabledtoilet4f'), ('exitlift5bawah', 'exit54f'), ('escaturunbawah', 'escalatordown4f'),
            ('escanaikbawah', 'escalatorup4f'), ('exitlift10bawah', 'exit104f'), ('pintukeluar', 'entranceexit'),
            }
    cmp_rows = []
    for _, r in lab.iterrows():
        old = prov.loc[r['stop_id'], 'location_label']
        agree = norm(old) == norm(r['label']) or (norm(old), norm(r['label'])) in same
        cmp_rows.append({'stop_id': r['stop_id'], 'provisional_label_dicta': old, 'label_now': r['label'],
                         'labels_agree': agree, 'floor_now': r['floor'], 'floor_dicta': prov.loc[r['stop_id'], 'floor'],
                         'floor_from_barometer_gap': baro_floor[r['stop_id']], 'floor_agrees_with_barometer': baro_floor[r['stop_id']] == r['floor'],
                         'confirmed': bool(r['confirmed']), 'used': bool(r['usable'])})
    pd.DataFrame(cmp_rows).to_csv(OUT / 'label_changes_vs_provisional.csv', index=False)
    revisit_check = pd.DataFrame(rev_rows)
    revisit_check.to_csv(OUT / 'revisit_check_23nov.csv', index=False)

    R, splits = {}, {}
    keys23 = [k for k in place_of if k.startswith(D_23)]
    # MAIN: latest visit of each revisited place = test; everything else from 23 Nov = train.
    by_place = defaultdict(list)
    for k in sorted(keys23, key=lambda k: walks[k.split(':')[1]]['start']):
        by_place[place_of[k]].append(k)
    revisited = {p: ks for p, ks in by_place.items() if len(ks) > 1}
    test_late = {ks[-1] for ks in revisited.values()}
    test_early = {ks[0] for ks in revisited.values()}
    gaps = {p: {'train_visits': ks[:-1], 'test_visit': ks[-1],
                'gap_min_from_latest_train_visit': round((walks[ks[-1].split(':')[1]]['start'] - walks[ks[-2].split(':')[1]]['end']) / 60, 1)}
            for p, ks in revisited.items()}
    for mod, F in [('mag', M), ('wifi', W)]:
        k = F['key']
        in23 = k.isin(keys23)
        R.setdefault('revisit_23', {})[mod] = evaluate(F, mod, in23 & ~k.isin(test_late), k.isin(test_late), place_of, floor_of, place_floor, adj)
        R.setdefault('revisit_23_reverse', {})[mod] = evaluate(F, mod, in23 & ~k.isin(test_early), k.isin(test_early), place_of, floor_of, place_floor, adj)
        tr, te = block_masks(F, keys23, 1 if mod == 'mag' else 0)
        R.setdefault('block_23', {})[mod] = evaluate(F, mod, tr, te, place_of, floor_of, place_floor, adj, full=False)
        # Same-day block split restricted to the revisited places' test visits, for a like-for-like gap.
        tr2, te2 = tr.copy(), te & k.isin(test_late).to_numpy()
        R.setdefault('block_23_revisit_places', {})[mod] = evaluate(F, mod, tr2, te2, place_of, floor_of, place_floor, adj, full=False)

    # SECONDARY: train 23 Nov (shared places), test 17 Nov; same-day block split on 17 Nov for comparison.
    for tier, cls in shared.items():
        k17 = [k for k in place_of if k.startswith(D_17) and place_of[k] in cls]
        k23 = [k for k in keys23 if place_of[k] in cls]
        for mod, F in [('mag', M), ('wifi', W)]:
            k = F['key']
            if mod == 'wifi':      # Wi-Fi only where both days heard access points at that place
                heard = {d: {place_of[x] for x in k.unique() if x.startswith(d) and x in place_of} for d in [D_17, D_23]}
                ok_cls = set(cls) & heard[D_17] & heard[D_23]
                splits.setdefault('wifi_coverage', {})[tier] = {'places': len(cls), 'with_wifi_both_days': len(ok_cls),
                                                               'missing': sorted(set(cls) - ok_cls)}
                kk17, kk23 = [x for x in k17 if place_of[x] in ok_cls], [x for x in k23 if place_of[x] in ok_cls]
            else:
                kk17, kk23 = k17, k23
            R.setdefault(f'cross_{tier}', {})[mod] = evaluate(F, mod, k.isin(kk23), k.isin(kk17), place_of, floor_of, place_floor, adj)
            R.setdefault(f'cross_{tier}_reverse_train17_test23', {})[mod] = evaluate(
                F, mod, k.isin(kk17), k.isin(kk23), place_of, floor_of, place_floor, adj, full=False)
            tr, te = block_masks(F, kk17, 1 if mod == 'mag' else 0)
            R.setdefault(f'block_17_{tier}' if tier != 'core' else 'block_17', {})[mod] = evaluate(
                F, mod, tr, te, place_of, floor_of, place_floor, adj, full=False)

    # ---- outputs
    r_hint, pts = fig_mag_stability(M, place_of, shared['extended'], place_floor)
    plc = pd.DataFrame([{'place_23nov': p, 'floor': place_floor[p], 'tier': 'core' if p in shared['core'] else 'extended' if p in shared['extended'] else '23 Nov only',
                         'stops_23nov': ' '.join(k.split(':')[1] for k in keys23 if place_of[k] == p),
                         'stops_17nov': ' '.join(k.split(':')[1] for k in place_of if k.startswith(D_17) and place_of[k] == p)}
                        for p in sorted(places23, key=lambda p: (-place_floor[p], p))])
    plc.to_csv(OUT / 'places.csv', index=False)
    pd.DataFrame([{'experiment': e, 'modality': mod, 'method': m, **{c: v[c] for c in ['n_test_visits', 'n_test_windows', 'visit_place_accuracy',
                    'visit_within_one_neighbour', 'visit_floor_accuracy', 'window_place_accuracy']}, 'chance': R[e][mod]['_split']['chance_accuracy']}
                  for e in R for mod in R[e] for m, v in R[e][mod].items() if not m.startswith('_')]).to_csv(OUT / 'summary_table.csv', index=False)

    devices = {d: sessions[d][sessions[d]['stop_id'].str.startswith('BM')]['device_model'].unique().tolist() for d in [D_17, D_23]}
    results = {
        'what': 'GE2340 WalkSense positioning evaluation. Every number here is computed by crossday.py from committed data.',
        'reference_dataset': '2026-11-23 (labels from labels_23nov_confirmed.csv)' if not PLACE_MAP else
                             '2026-11-23 (labels from ../graph-v2/labels_23nov_merged.csv)',
        **({'place_merge_applied_to_crosswalk_and_map': PLACE_MAP} if PLACE_MAP else {}),
        'labels': {'n_23nov_stops': len(lab), 'n_usable': int(lab['usable'].sum()), 'n_confirmed_by_team': int(lab['confirmed'].sum()),
                   'excluded': {s: r for s, r in zip(lab['stop_id'], lab['reason_if_excluded']) if r},
                   'n_places_23nov': len(places23)},
        'settings': {'magnetic_window_s': WINDOW_S, 'wifi_chunk_s': WIFI_CHUNK_S, 'block_split_train_fraction': TRAIN_FRACTION,
                     'knn': 'k=5 (fewer if fewer training samples), distance-weighted, standardised',
                     'random_forest': '200 trees, class_weight=balanced, seed 21',
                     'visit_level': 'majority vote over all windows/chunks of one stop',
                     'fusion': 'barometer step-tracking floor (threshold learned on the other day) picks a per-floor model',
                     'wifi_features': 'rssi = strongest RSSI per BSSID in a 10 s chunk, -100 if not heard; presence = heard or not'},
        'devices': {'stops_magnetometer_barometer': devices, 'walks': 'iPhone19,2 on both days',
                    'wifi_logger': {'17Nov': 'Samsung SM-A556E, Android 15, WiGLE 2.111', '23Nov': 'Samsung SM-S9280, Android 16, WiGLE 2.111'},
                    'normalisation': 'no per-device calibration; magnitude-only magnetic features ignore phone orientation; '
                                     'Wi-Fi presence features ignore RSSI offsets between the two Samsung phones'},
        'revisits_23nov': {'places': gaps, 'check_table': 'out/revisit_check_23nov.csv'},
        'crosswalk': {'core': shared['core'], 'extended': shared['extended'],
                      'mapped_17nov_stops': {k.split(':')[1]: v for k, v in place_of.items() if k.startswith(D_17)},
                      'unmapped_or_low_17nov_stops': cw[cw['rank'] < 2]['stop_id_17nov'].tolist(),
                      'magnetic_field_strength_correlation_17_vs_23': r_hint},
        'floor': {'per_day': floor_stats, 'cross_day': floor_res},
        'wifi_coverage_cross_day': splits.get('wifi_coverage'),
        'adjacency_for_within_one': {k: sorted(v) for k, v in sorted(adj.items())},
        'results': R,
    }
    (OUT / 'results.json').write_text(json.dumps(results, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))

    fig_pressure(press, true_floor)
    fig_overview(R)
    fig_confusion([('Baro floor + magnetic |B|+xyz kNN', R['revisit_23']['mag']['magnitude_xyz_knn_baro_floor']),
                   ('Wi-Fi RSSI kNN', R['revisit_23']['wifi']['rssi_knn'])],
                  '23 Nov: train on earlier visits, test on the latest revisit (rows normalised)', 'fig_confusion_revisit_23nov.png')
    fig_confusion([('Baro floor + magnetic |B| kNN', R['cross_core']['mag']['magnitude_knn_baro_floor']),
                   ('Baro floor + Wi-Fi RSSI RF', R['cross_core']['wifi']['rssi_rf_baro_floor'])],
                  'Cross-day: train 23 Nov, test 17 Nov, core shared places (rows normalised)', 'fig_confusion_cross_day.png')

    # ---- console summary
    print(f"\n23-Nov stops usable: {int(lab['usable'].sum())}/{len(lab)}; places: {len(places23)}; revisited: {len(revisited)}")
    print('Shared with 17 Nov: core', len(shared['core']), '| extended', len(shared['extended']))
    for k, v in floor_res.items():
        print('Floor', k, {m: r['stops_correct'] for m, r in v.items()})
    show = ['magnitude_knn', 'magnitude_knn_baro_floor', 'magnitude_xyz_knn', 'magnitude_xyz_knn_baro_floor',
            'rssi_knn', 'rssi_rf', 'rssi_rf_baro_floor']
    for e in ['block_23', 'block_23_revisit_places', 'revisit_23', 'revisit_23_reverse', 'block_17', 'cross_core', 'cross_extended',
              'cross_core_reverse_train17_test23']:
        for mod in ['mag', 'wifi']:
            blk = R[e][mod]
            line = ' '.join(f"{m}={blk[m]['visit_place_accuracy']:.2f}/{blk[m]['window_place_accuracy']:.2f}" for m in show if m in blk)
            any_m = next(m for m in blk if not m.startswith('_'))
            print(f"{e:34s} {mod:4s} n={blk[any_m]['n_test_visits']:2d} chance={blk['_split']['chance_accuracy']} | {line}")
    print('\nWrote', OUT)


if __name__ == '__main__':
    main()
