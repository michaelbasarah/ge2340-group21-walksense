#!/usr/bin/env python3
"""Orientation (tilt) correction test on the 23-Nov WALK recordings.

Stops (BM*) logged only barometer + magnetometer, so they cannot be tilt-corrected.
The 23-Nov walks (ACC*) logged accelerometer + gyroscope + magnetometer in one file on
one clock, so for each walk we:
  1. estimate gravity in the phone frame (a) the mean accelerometer over the window
     ("low-pass") and (b) a complementary filter that turns the gyro into gravity
     updates and pulls slowly towards the accelerometer ("gyro-aided");
  2. split the magnetic field into B_vertical (along gravity) and B_horizontal;
  3. use the first and last 2 s of each walk as fingerprints of its start and end
     place (labels from labels_23nov_confirmed.csv via the stop before / after it).
Then compare feature sets on exactly the same samples:
  |B| only, raw x/y/z, tilt-corrected (B_vertical, B_horizontal).

Run after crossday.py (it builds the 23-Nov cache):  python phase2/cross-day/tilt.py
Writes out/tilt_results.json, out/tilt_endpoints.csv, out/fig_tilt.png.
17-Nov walks logged only the accelerometer, so they cannot be used here.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

import crossday as cd

WIN_S = 2.0            # endpoint window at the start / end of each walk
MIN_WALK_S = 5.0       # shorter walks would make start and end windows overlap
ALPHA = 0.98           # complementary filter: weight on the gyro-propagated gravity
FEATS = {'|B| only': ['B'], 'raw x/y/z': ['x', 'y', 'z'],
         'tilt-corrected (low-pass gravity)': ['Bv_lp', 'Bh_lp'],
         'tilt-corrected (gyro-aided gravity)': ['Bv_gy', 'Bh_gy']}


def load_walk_sensors():
    out = {}
    for s in ['accelerometer', 'gyroscope', 'magnetometer']:
        d = pd.read_csv(cd.CACHE23 / 'sensors' / f'{s}.csv', usecols=['stop_id', 'timestamp_epoch_s', 'x', 'y', 'z'])
        out[s] = d[d['stop_id'].str.startswith('ACC')]
    return out


def gravity_gyro(t, acc, gyr):
    """Complementary filter: g' = -w x g (body frame), blended with the accelerometer."""
    g = acc[0] / np.linalg.norm(acc[0])
    res = np.empty_like(acc)
    for i in range(len(t)):
        if i:
            dt = t[i] - t[i - 1]
            g = g - dt * np.cross(gyr[i], g)
            g = ALPHA * g + (1 - ALPHA) * acc[i] / np.linalg.norm(acc[i])
            g /= np.linalg.norm(g)
        res[i] = g
    return res


def split_field(B, g):
    """B_vertical = component along gravity; B_horizontal = the rest."""
    g = g / np.linalg.norm(g, axis=-1, keepdims=True)
    bv = np.sum(B * g, axis=-1)
    bh = np.linalg.norm(B - bv[..., None] * g, axis=-1)
    return bv, bh


def endpoints(sensors, sessions, place):
    stops = sessions[sessions['stop_id'].str.startswith('BM')].sort_values('start_epoch_s')
    walks = sessions[sessions['kind'] == 'movement'].sort_values('start_epoch_s')
    rows, align = [], []
    for _, w in walks.iterrows():
        wid = w['stop_id']
        m = sensors['magnetometer'][sensors['magnetometer']['stop_id'] == wid].sort_values('timestamp_epoch_s')
        a = sensors['accelerometer'][sensors['accelerometer']['stop_id'] == wid].sort_values('timestamp_epoch_s')
        gy = sensors['gyroscope'][sensors['gyroscope']['stop_id'] == wid].sort_values('timestamp_epoch_s')
        t = m['timestamp_epoch_s'].to_numpy()
        align.append(abs(a['timestamp_epoch_s'].iloc[0] - t[0]))
        # Accelerometer and gyro resampled onto the magnetometer clock (same file, ~100 Hz each).
        acc = np.column_stack([np.interp(t, a['timestamp_epoch_s'], a[c]) for c in 'xyz'])
        gyr = np.column_stack([np.interp(t, gy['timestamp_epoch_s'], gy[c]) for c in 'xyz'])
        B = m[['x', 'y', 'z']].to_numpy()
        g_gy = gravity_gyro(t, acc, gyr)
        before = stops[stops['end_epoch_s'] <= w['start_epoch_s'] + 30].iloc[-1]['stop_id']
        after_ = stops[stops['start_epoch_s'] >= w['start_epoch_s']]
        after = after_.iloc[0]['stop_id'] if len(after_) else None
        dur = t[-1] - t[0]
        if dur < MIN_WALK_S:
            continue
        for end, sid, sel in [('start', before, t <= t[0] + WIN_S), ('end', after, t >= t[-1] - WIN_S)]:
            if sid is None or sid not in place:
                continue
            bv_lp, bh_lp = split_field(B[sel].mean(0), acc[sel].mean(0))
            bv_gy, bh_gy = split_field(B[sel], g_gy[sel])
            rows.append({'walk': wid, 'endpoint': end, 'pass_stop': sid, 'place': place[sid], 'time': t[sel].mean(),
                         'B': np.linalg.norm(B[sel], axis=1).mean(), 'x': B[sel, 0].mean(), 'y': B[sel, 1].mean(), 'z': B[sel, 2].mean(),
                         'Bv_lp': bv_lp, 'Bh_lp': bh_lp, 'Bv_gy': bv_gy.mean(), 'Bh_gy': bh_gy.mean(),
                         'acc_sd': float(np.linalg.norm(acc[sel], axis=1).std()),
                         'tilt_deg_from_flat': float(np.degrees(np.arccos(abs(acc[sel].mean(0)[2]) / np.linalg.norm(acc[sel].mean(0)))))})
    return pd.DataFrame(rows), float(np.max(align))


def one_nn(xtr, ytr, xte):
    sc = StandardScaler().fit(xtr)
    a, b = sc.transform(xtr), sc.transform(xte)
    d = ((b[:, None, :] - a[None, :, :]) ** 2).sum(-1)
    return np.asarray(ytr)[d.argmin(1)]


def main():
    sessions = cd.load_sessions(cd.D_23)
    lab = pd.read_csv(cd.HERE / 'labels_23nov_confirmed.csv', dtype=str).fillna('')
    lab = lab[lab['confirmed'].str.lower().isin(['yes', 'y', 'true', '1'])]
    place = dict(zip(lab['stop_id'], lab['label'].str.strip()))
    E, max_offset = endpoints(load_walk_sensors(), sessions, place)
    E.to_csv(cd.OUT / 'tilt_endpoints.csv', index=False)

    res = {'what': 'Tilt-correction test on 23-Nov walk endpoints (first/last 2 s of each walk). Computed by tilt.py.',
           'walk_device': sessions[sessions['kind'] == 'movement']['device_model'].unique().tolist(),
           'stop_device': sessions[sessions['kind'] == 'stop']['device_model'].unique().tolist(),
           'max_start_offset_accel_vs_mag_s': round(max_offset, 3),
           'n_endpoints': len(E), 'n_places': int(E['place'].nunique()),
           'walks_skipped_shorter_than_s': MIN_WALK_S,
           'phone_tilt_from_flat_deg_median': round(float(E['tilt_deg_from_flat'].median()), 1),
           'phone_tilt_from_flat_deg_range': [round(float(E['tilt_deg_from_flat'].min()), 1), round(float(E['tilt_deg_from_flat'].max()), 1)],
           'accel_magnitude_sd_median_ms2': round(float(E['acc_sd'].median()), 2)}

    # (a) Separability: silhouette over places with at least two endpoints.
    multi = E[E['place'].map(E['place'].value_counts()) >= 2]
    res['silhouette_places_with_2plus_endpoints'] = {
        'n_samples': len(multi), 'n_places': int(multi['place'].nunique()),
        **{k: round(float(silhouette_score(StandardScaler().fit_transform(multi[f]), multi['place'])), 3) for k, f in FEATS.items()}}

    # (b) Revisit test: pass = the stop an endpoint brackets. Test one pass, train on every other pass.
    passes = E.groupby('place')['pass_stop'].unique()
    revisited = {p: sorted(v, key=lambda s: E[E['pass_stop'] == s]['time'].min()) for p, v in passes.items() if len(v) > 1}
    splits = {'leave_one_pass_out': [(p, s) for p, v in revisited.items() for s in v],
              'latest_pass': [(p, v[-1]) for p, v in revisited.items()]}
    res['revisited_places'] = {p: list(v) for p, v in revisited.items()}
    res['revisit_tests'] = {}
    for name, tests in splits.items():
        out = {}
        for fname, f in FEATS.items():
            hits, preds = [], []
            for p, s in tests:
                te = E['pass_stop'] == s
                pred = one_nn(E.loc[~te, f].to_numpy(), E.loc[~te, 'place'], E.loc[te, f].to_numpy())
                hits += list(pred == p)
                preds.append({'pass_stop': s, 'true': p, 'pred': Counter(pred).most_common(1)[0][0]})
            out[fname] = {'endpoint_accuracy': round(float(np.mean(hits)), 3), 'n_test_endpoints': len(hits),
                          'pass_accuracy': round(float(np.mean([q['true'] == q['pred'] for q in preds])), 3), 'n_test_passes': len(preds),
                          'chance': round(1 / E['place'].nunique(), 3), 'predictions': preds}
        res['revisit_tests'][name] = out

    # Device check: walk phone vs stop phone, |B| per place.
    st = cd.magnetic_windows(cd.load_sensors(cd.D_23)[0], cd.D_23)
    st['place'] = st['key'].str.split(':').str[1].map(place)
    sp = st.groupby('place')['mag_mean'].mean()
    wp = E.groupby('place')['B'].mean()
    common = sorted(set(sp.index) & set(wp.index))
    res['device_check_walk_vs_stop_mean_B'] = {
        'n_places': len(common), 'correlation': round(float(np.corrcoef(sp[common], wp[common])[0, 1]), 3),
        'median_abs_difference_uT': round(float(np.median(np.abs(sp[common] - wp[common]))), 2)}

    (cd.OUT / 'tilt_results.json').write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))

    # Figure: silhouette and leave-one-pass-out accuracy per feature set.
    names = list(FEATS)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    sil = [res['silhouette_places_with_2plus_endpoints'][k] for k in names]
    acc = [res['revisit_tests']['leave_one_pass_out'][k]['endpoint_accuracy'] for k in names]
    short = ['|B| only', 'raw x/y/z', 'tilt: low-pass', 'tilt: gyro-aided']
    for ax, vals, title, pct in [(axes[0], sil, 'Separation of places (silhouette, higher = better)', False),
                                 (axes[1], acc, 'Other-pass accuracy (1-NN, leave one pass out)', True)]:
        cols = ['#8a8983', '#8a8983', cd.C_MAIN, cd.C_MAIN]
        ax.bar(range(4), vals, color=cols, width=0.6)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.01 if v >= 0 else v / 2, f'{v:.0%}' if pct else f'{v:.2f}', ha='center', fontsize=8,
                    color=cd.INK if v >= 0 else 'white')
        ax.set_xticks(range(4)); ax.set_xticklabels(short, fontsize=8)
        ax.axhline(0, color='#b5b4ad', linewidth=0.8)
        ax.set_title(title, fontsize=10, loc='left', color=cd.INK); cd.style(ax)
        if pct:
            ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
            ax.axhline(res['revisit_tests']['leave_one_pass_out'][names[0]]['chance'], color=cd.INK, linewidth=1, linestyle=(0, (1.5, 1.5)))
    n = res['revisit_tests']['leave_one_pass_out'][names[0]]['n_test_endpoints']
    fig.suptitle(f'23 Nov walk endpoints (first/last 2 s of each walk, iPhone19,2): {len(E)} endpoints, '
                 f'{E["place"].nunique()} places; accuracy on {n} test endpoints', fontsize=9, x=0.01, ha='left', color=cd.INK2)
    fig.tight_layout(); fig.savefig(cd.OUT / 'fig_tilt.png', dpi=150); plt.close(fig)

    print(json.dumps({k: v for k, v in res.items() if k != 'revisit_tests'}, indent=1))
    for name, out in res['revisit_tests'].items():
        print(name, {k: (v['endpoint_accuracy'], v['n_test_endpoints'], v['pass_accuracy'], v['n_test_passes']) for k, v in out.items()})


if __name__ == '__main__':
    main()
