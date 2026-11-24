#!/usr/bin/env python3
"""Pedestrian dead reckoning (PDR) on the walk recordings: steps and gyro turns.

Steps: the detector from phase2/old/positioning-pilot/step_detection.py, reused unchanged
(|a| minus a 0.40 s moving average, peaks above 0.9 m/s^2, at least 0.30 s apart).
Turns (23 Nov only, 17-Nov walks have no gyroscope): yaw rate = gyro projected on gravity
(gravity = 1 s moving average of the accelerometer), integrated to a heading; a turn is a
run where the smoothed yaw rate stays above 30 deg/s, kept if it turns at least 45 deg.
Positive angle = anticlockwise seen from above (left), assuming the accelerometer reads +g up.

Each walk is matched to the stop before and after it in time (labels_23nov_confirmed.csv,
crosswalk_17nov_to_23nov.csv). Writes out/pdr_walks_23nov.csv, out/pdr_walks_17nov.csv,
out/pdr_summary.json. Run after crossday.py has built its 23-Nov cache.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
sys.path.insert(0, str(NEW / 'cross-day'))
sys.path.insert(0, str(NEW.parent / 'old' / 'positioning-pilot'))
import crossday as cd                      # noqa: E402  (paths + 23-Nov cache)
from step_detection import count_steps     # noqa: E402  (reused unchanged)

OUT = HERE / 'out'
TURN_RATE = np.deg2rad(30)    # rad/s, smoothed yaw rate that counts as turning
TURN_MIN = 45.0               # deg, smallest turn reported
SMOOTH_S = 0.5
NOMINAL_HZ = 100.0         # both walk phones log ~100 Hz
MIN_COVERAGE = 0.5        # walks with fewer than half the expected readings have sampling gaps: steps unreliable


def movavg(a, w):
    w = max(1, int(w))
    k = np.ones(w) / w
    if a.ndim == 1:
        return np.convolve(a, k, mode='same')
    return np.column_stack([np.convolve(a[:, i], k, mode='same') for i in range(a.shape[1])])


def stop_sequence(day):
    """Stops in time order with their place (None if unmapped)."""
    s = cd.load_sessions(day)
    if day == cd.D_23:
        lab = pd.read_csv(NEW / 'cross-day' / 'labels_23nov_confirmed.csv', dtype=str)
        place = dict(zip(lab['stop_id'], lab['label'].str.strip()))
    else:
        cw = pd.read_csv(NEW / 'cross-day' / 'crosswalk_17nov_to_23nov.csv', dtype=str).fillna('')
        cw = cw[cw['confidence'].isin(['high', 'medium'])]
        place = dict(zip(cw['stop_id_17nov'], cw['place_23nov'].str.strip()))
    st = s[s['stop_id'].str.startswith('BM')].sort_values('start_epoch_s').reset_index(drop=True)
    st['place'] = st['stop_id'].map(place)
    wk = s[~s['stop_id'].str.startswith('BM')].sort_values('start_epoch_s').reset_index(drop=True)
    return st, wk


def match_walks(st, wk):
    """Walk -> (stop before, stop after): last stop starting before the walk, first stop starting after it."""
    rows = []
    for _, w in wk.iterrows():
        before = st[st['start_epoch_s'] < w['start_epoch_s']]
        after = st[st['start_epoch_s'] >= w['start_epoch_s']]
        rows.append({'walk_id': w['stop_id'], 'walk_file': w['source_zip'],
                     'from_stop': before['stop_id'].iloc[-1] if len(before) else '',
                     'to_stop': after['stop_id'].iloc[0] if len(after) else '',
                     'from_place': before['place'].iloc[-1] if len(before) else None,
                     'to_place': after['place'].iloc[0] if len(after) else None,
                     'start_epoch_s': w['start_epoch_s'], 'end_epoch_s': w['end_epoch_s']})
    return pd.DataFrame(rows)


def turns(t, acc, gyr):
    fs = 1.0 / np.median(np.diff(t))
    g = movavg(acc, round(1.0 * fs))
    g /= np.linalg.norm(g, axis=1, keepdims=True)
    yaw = np.sum(gyr * g, axis=1)
    ys = movavg(yaw, round(SMOOTH_S * fs))
    dt = np.gradient(t)
    on = np.abs(ys) > TURN_RATE
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            ang = float(np.degrees(np.sum(yaw[i:j] * dt[i:j])))
            if abs(ang) >= TURN_MIN:
                out.append({'t_s': round(float(t[i] - t[0]), 2), 'deg': round(ang, 0)})
            i = j
        else:
            i += 1
    net = float(np.degrees(np.sum(yaw * dt)))
    return out, net, ys


def walk_signals(day):
    """Per walk: time, accelerometer (and gyroscope on 23 Nov), resampled onto the accelerometer clock."""
    if day == cd.D_23:
        a = pd.read_csv(cd.CACHE23 / 'sensors' / 'accelerometer.csv', usecols=['stop_id', 'timestamp_epoch_s', 'x', 'y', 'z'])
        g = pd.read_csv(cd.CACHE23 / 'sensors' / 'gyroscope.csv', usecols=['stop_id', 'timestamp_epoch_s', 'x', 'y', 'z'])
    else:
        a = pd.read_csv(cd.D17 / 'sensors' / 'accelerometer.csv', usecols=['session_id', 'timestamp_epoch_s', 'x', 'y', 'z']).rename(columns={'session_id': 'stop_id'})
        g = None
    sig = {}
    for wid, ga in a.groupby('stop_id'):
        ga = ga.sort_values('timestamp_epoch_s').drop_duplicates('timestamp_epoch_s')
        t = ga['timestamp_epoch_s'].to_numpy()
        acc = ga[['x', 'y', 'z']].to_numpy(float)
        gyr = None
        if g is not None:
            gg = g[g['stop_id'] == wid].sort_values('timestamp_epoch_s').drop_duplicates('timestamp_epoch_s')
            if len(gg) > 10:
                gyr = np.column_stack([np.interp(t, gg['timestamp_epoch_s'], gg[c]) for c in 'xyz'])
        sig[wid] = (t, acc, gyr)
    return sig


def analyse(day):
    st, wk = stop_sequence(day)
    walks = match_walks(st, wk)
    sig = walk_signals(day)
    rows, step_times = [], {}
    for _, w in walks.iterrows():
        t, acc, gyr = sig[w['walk_id']]
        n, fs, times = count_steps(t, np.linalg.norm(acc, axis=1))
        dur = float(t[-1] - t[0])
        cover = len(t) / (NOMINAL_HZ * dur) if dur > 0 else 0.0
        r = {**w.to_dict(), 'readings': len(t), 'sampling_hz': round(fs), 'duration_s': round(dur, 1),
             'coverage': round(cover, 2), 'steps_reliable': bool(cover >= MIN_COVERAGE),
             'steps': n, 'cadence_steps_per_s': round(n / dur, 2) if dur > 0 else None}
        if gyr is not None:
            tl, net, _ = turns(t, acc, gyr)
            r.update({'net_heading_change_deg': round(net, 0), 'n_turns_45deg': len(tl),
                      'turns': ' '.join(f"{x['deg']:+.0f}@{x['t_s']}s" for x in tl)})
        rows.append(r)
        step_times[w['walk_id']] = [round(x, 3) for x in times]
    return pd.DataFrame(rows), step_times


def floor5_distances():
    e = pd.read_csv(cd.PHASE2 / 'map' / 'edges_floor5.csv')
    d = {}
    for a, b, m in zip(e['from'], e['to'], e['distance_m']):
        d[frozenset((cd.MAP_NAMES[a], cd.MAP_NAMES[b]))] = float(m)
    return d


STRAIGHT = {frozenset(p) for p in [('sr11', 'sr10'), ('sr10', 'sr9'), ('sr9', 'sr8')]}   # one straight corridor (floor-5 map)


def summary(res):
    dist = floor5_distances()
    out = {'settings': {'step_detector': 'phase2/old/positioning-pilot/step_detection.py count_steps (unchanged): '
                                         '|a| minus 0.40 s moving average, peak > 0.9 m/s^2, >= 0.30 s apart',
                        'turns': f'yaw rate = gyro . gravity (1 s moving-average accelerometer), smoothed {SMOOTH_S} s; '
                                 f'turn = run above 30 deg/s, kept if >= {TURN_MIN} deg; + = anticlockwise (left)',
                        'reliable_if_coverage_at_least': MIN_COVERAGE}}
    for d, r in res.items():
        df = r['df']
        ok = df[df['steps_reliable']]
        o = {'walks': len(df), 'walks_reliable': int(len(ok)), 'unreliable_walks': df.loc[~df['steps_reliable'], 'walk_id'].tolist(),
             'steps_total': int(df['steps'].sum()), 'median_cadence_reliable': float(ok['cadence_steps_per_s'].median())}
        rows = []
        for _, w in ok.iterrows():
            k = frozenset((w['from_place'], w['to_place']))
            if k in dist and w['steps'] > 0:
                rows.append({'walk': w['walk_id'], 'edge': f"{w['from_place']}-{w['to_place']}", 'map_m': dist[k],
                             'steps': int(w['steps']), 'm_per_step': round(dist[k] / w['steps'], 2)})
        mps = [x['m_per_step'] for x in rows]
        o['floor5_map_edges'] = {'n_walks': len(rows), 'median_m_per_step': round(float(np.median(mps)), 2) if mps else None,
                                 'min_m_per_step': min(mps) if mps else None, 'max_m_per_step': max(mps) if mps else None,
                                 'note': 'map distance is the straight line between pins, so real strides are a bit longer',
                                 'walks': rows}
        if 'turns' in df:
            straight = df[np.array([frozenset((a, b)) in STRAIGHT for a, b in zip(df['from_place'], df['to_place'])]) & df['steps_reliable'].to_numpy()]
            stairs = df[(df['from_place'] == 'exit_5_stairs') & (df['to_place'] == 'exit_5_stairs_4F')]
            o['turn_checks'] = {
                'straight_corridor_walks_sr11_to_sr8': {'walks': straight['walk_id'].tolist(),
                                                        'turns_detected': straight['n_turns_45deg'].astype(int).tolist(),
                                                        'net_heading_deg': straight['net_heading_change_deg'].tolist(),
                                                        'expected': 'no turn'},
                'stairs_walk_5F_to_4F': {'walk': stairs['walk_id'].tolist(), 'turns': stairs['turns'].tolist(),
                                         'net_heading_deg': stairs['net_heading_change_deg'].tolist(),
                                         'expected': 'at least one U-turn on the landing (not verified on site)'},
                'walks_with_a_turn': int((df['n_turns_45deg'] > 0).sum()),
                'note': 'only these two checks have a known expected answer; the floor-5 map has straight edges between pins '
                        'and floor 4 has no map, so other turns cannot be checked against the route without the collector'}
        out[d] = o
    return out


def main():
    OUT.mkdir(exist_ok=True)
    cd.ensure_23nov_cache()
    res = {}
    for day, fname in [(cd.D_23, 'pdr_walks_23nov.csv'), (cd.D_17, 'pdr_walks_17nov.csv')]:
        df, times = analyse(day)
        df.drop(columns=['start_epoch_s', 'end_epoch_s']).to_csv(OUT / fname, index=False)
        res[day] = {'df': df, 'step_times': times}
    (OUT / 'pdr_step_times.json').write_text(json.dumps({d: r['step_times'] for d, r in res.items()}))
    (OUT / 'pdr_summary.json').write_text(json.dumps(summary(res), indent=1))
    for d, r in res.items():
        df = r['df']
        print(d, 'walks', len(df), 'steps total', int(df['steps'].sum()), 'median cadence', df['cadence_steps_per_s'].median())
        print(df[['walk_id', 'from_place', 'to_place', 'duration_s', 'coverage', 'steps', 'cadence_steps_per_s'] +
                 (['net_heading_change_deg', 'turns'] if 'turns' in df else [])].to_string(index=False))
    return res


if __name__ == '__main__':
    main()
