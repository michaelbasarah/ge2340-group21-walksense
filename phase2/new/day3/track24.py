#!/usr/bin/env python3
"""Route-aware HMM tracker (../tracking/tracker.py, v2 parameters, code reused unchanged) on 24 Nov.

Test = 24-Nov session 2 (ip16 = iPhone17,4), replayed in time order. Everything the tracker learns comes from
session 1 only: the magnetic fingerprints (ip18 = iPhone19,2 stops, |B|+xyz 2 s windows as in crossday.py),
the expected steps per line (session-1 iPhone walks, same step detector as pdr.py) and the barometer
floor-jump threshold. Graph = graph-v2 (merged study rooms and lift/stairs). Compared on the same stops
with the snapshot kNN and the emission-only model, exactly as tracker.py does.

This main run is CROSS-HANDSET (fingerprints from ip18, test on ip16). A SAME-handset variant (fingerprints and
floor threshold from the 23-Nov ip16 stops, line lengths still from session 1 walks) is written next to it.

Run after data.py:  python phase2/new/day3/track24.py
Writes out/track24_results.json, out/track24_visits.csv and out/replay_24nov_s2.json (the circle-UI format;
open phase2/new/circle-ui/index.html?data=../day3/out/replay_24nov_s2.json over http). The 23-Nov replay
in ../tracking/out/ is not touched.

With DAY3_VARIANT=split20 (data.py) the TRAINING fingerprints keep only the 2 s windows inside kept 20 s pieces
(out-split20/pieces.csv: excluded 23-Nov stairs/study-room stops, outlier and incomplete pieces dropped). The test
replay is a time-ordered stream scored per stop and is not cut into pieces; its windows get the same filter.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import data

sys.path.insert(0, str(data.NEW / 'tracking'))
sys.path.insert(0, str(data.NEW.parent / 'old' / 'positioning-pilot'))
import tracker as tk                       # noqa: E402  (reused unchanged)
from step_detection import count_steps     # noqa: E402  (reused unchanged, as pdr.py)

TRAIN, TEST = '24s1', '24s2'
PHONE = 'iphone'
WIN = 2.0                                  # tracker's magnetic window (crossday.py WINDOW_S)
COL = {'B_mean': 'mag_mean', 'B_std': 'mag_std', 'B_p10': 'mag_p10', 'B_p90': 'mag_p90'}


def session_inputs(sid):
    s = next(x for x in data.config()['sessions'] if x['id'] == sid)
    root = (data.HERE / s['path']).resolve()
    names = pd.read_csv(data.HERE / s['names'], dtype={'floor': int}).fillna('')
    nm = names.set_index(['floor', 'node_24nov'])['place_v2'].to_dict()
    m = pd.read_csv(root / 'manifest.csv', dtype=str).fillna('')
    m = m[m['phone'] == PHONE].copy()
    hs = sorted({data.handset(d) for d in m['device']})
    assert len(hs) == 1, f'{sid}: the {PHONE} slot has several handsets {hs}'
    m['floor'] = m['floor'].astype(int)
    D = data.load()
    V = D['V'][D['V']['session'] == sid].set_index('visit')
    rec = [(r, data._csv(root / r['folder'] / PHONE / 'Magnetometer.csv'), data._csv(root / r['folder'] / PHONE / 'Accelerometer.csv'), None)
           for _, r in m.iterrows()]
    # absolute clock: manifest start (1 s resolution) + phyphox relative time
    day = datetime.fromisoformat(s['day']).replace(tzinfo=data.HK)
    abs0 = lambda hms: (day + timedelta(hours=int(hms[:2]), minutes=int(hms[3:5]), seconds=int(hms[6:8]))).timestamp()
    st_rows, W_rows, pw_rows = [], [], []
    for r, mag, acc, _ in rec:
        a0 = abs0(r['start_hk'])
        if r['type'] == 'stop':
            sidk = r['folder']
            st_rows.append({'stop_id': sidk, 'start_epoch_s': a0, 'end_epoch_s': a0 + float(r['duration_s']),
                            'place': nm[(r['floor'], r['node'])], 'floor_true': r['floor']})
            for w in data.window_features(mag[:, 0], mag[:, 1:4], win=WIN):
                W_rows.append({'key': f'{sid}:{sidk}', 'window': w['window'], 't_end': a0 + mag[0, 0] + (w['window'] + 1) * WIN,
                               **{COL.get(c, c): w[c] for c in ['B_mean', 'B_std', 'B_p10', 'B_p90', 'x_mean', 'y_mean', 'z_mean']}})
        else:
            t = acc[:, 0]
            n, fs, times = count_steps(t, np.linalg.norm(acc[:, 1:4], axis=1))
            dur = float(t[-1] - t[0])
            cover = len(t) / (100.0 * dur) if dur > 0 else 0
            pw_rows.append({'walk_id': r['folder'], 'start': a0, 'end': a0 + float(r['duration_s']), 'steps': n,
                            'steps_reliable': bool(cover >= 0.5), 'step_times': [a0 + x for x in times],
                            'from_place': nm.get((r['floor'], r['from_node']), ''), 'to_place': nm.get((r['floor'], r['to_node']), '')})
    st = pd.DataFrame(st_rows).sort_values('start_epoch_s').reset_index(drop=True)
    pw = pd.DataFrame(pw_rows).sort_values('start').reset_index(drop=True)
    # walk -> the last stop that started before it (the tracker's timeline groups walks by from_stop)
    pw['from_stop'] = [st[st['start_epoch_s'] <= s0]['stop_id'].iloc[-1] if (st['start_epoch_s'] <= s0).any() else None
                       for s0 in pw['start']]
    pw = pw[pw['from_stop'].notna()].reset_index(drop=True)
    return st, pw, keep_pieces(pd.DataFrame(W_rows)), V, hs[0]


def windows_23nov():
    """2 s windows of the 23-Nov stops (all ip16, checked), keyed '23nov:<stop>', and the stop -> place map."""
    D = data.load()
    V23 = D['V'][D['V']['session'] == '23nov']
    assert set(V23['iphone_handset']) == {'ip16'}, set(V23['iphone_handset'])
    sys.path.insert(0, str(data.NEW / 'cross-day'))
    import crossday as cd
    mag, _ = cd.load_sensors(cd.D_23)
    rows = []
    for sid, g in mag.groupby('stop_id'):
        g = g.sort_values('timestamp_epoch_s')
        for w in data.window_features(g['timestamp_epoch_s'].to_numpy(), g[['x', 'y', 'z']].to_numpy(), win=WIN):
            rows.append({'key': f'23nov:{sid}', 'window': w['window'],
                         **{COL.get(c, c): w[c] for c in ['B_mean', 'B_std', 'B_p10', 'B_p90', 'x_mean', 'y_mean', 'z_mean']}})
    place = {f'23nov:{v.split(":", 1)[1]}': pl for v, pl in zip(V23['visit'], V23['place'])}
    vt = V23.sort_values('start')
    p, f = vt['hpa_iphone'].to_numpy(), vt['floor'].to_numpy()
    return keep_pieces(pd.DataFrame(rows)), place, float(np.median(np.abs(np.diff(p))[np.diff(f) != 0])) / 2


def keep_pieces(Wt, slot=PHONE):
    """split20: keep only the 2 s windows that fall inside a kept 20 s piece of their take (no-op without a variant)."""
    if not data.VARIANT:
        return Wt
    D = data.load()
    P = D['pieces']
    kept = set(zip(P.loc[P['status'] == 'kept', 'take'], P.loc[P['status'] == 'kept', 'piece']))
    per = int(round(D['variant']['piece_s'] / WIN))
    ok = [(f'{k}:{slot}', int(w) // per) in kept for k, w in zip(Wt['key'], Wt['window'])]
    return Wt[ok].reset_index(drop=True)


def mu_from_walks(g, pw_train):
    """Expected steps per graph line from the TRAINING session's walks (median over walks on that line)."""
    ok = pw_train[pw_train['steps_reliable']]
    by = {}
    for a, b, n in zip(ok['from_place'], ok['to_place'], ok['steps']):
        by.setdefault(frozenset((a, b)), []).append(n)
    typical = float(np.median(ok['steps']))

    def mu(a, b, walk_id):
        e = by.get(frozenset((a, b)))
        if e:
            m = float(np.median(e)); return m, max(4.0, 0.3 * m)
        return typical, max(6.0, 0.6 * typical)
    return mu, {f'{sorted(k)[0]}|{sorted(k)[1]}': v for k, v in by.items()}, typical


def main():
    tk.GRAPH = data.NEW / 'graph-v2'
    tk.set_variant('v2_relocalise_and_firm_floor')
    g = tk.load_graph()
    st_tr, pw_tr, W_tr, V_tr, h_tr = session_inputs(TRAIN)
    st, pw, W, V, h_te = session_inputs(TEST)
    D_tr, D_te = data.display_names()[h_tr], data.display_names()[h_te]
    unknown = sorted((set(st['place']) | set(st_tr['place'])) - set(g['ids']))
    assert not unknown, unknown
    edges_missing = sorted({f'{a}|{b}' for a, b in zip(pw['from_place'], pw['to_place'])
                            if frozenset((a, b)) not in g['elen']})
    # floor: iPhone step tracking, threshold = half the floor step of the training session
    vt = V_tr.sort_values('start')
    p, f = vt['hpa_iphone'].to_numpy(), vt['floor'].to_numpy()
    thr = float(np.median(np.abs(np.diff(p))[np.diff(f) != 0])) / 2
    vs = V.sort_values('start')
    trk = data.track_floor(vs['hpa_iphone'].to_numpy(), thr)
    fl_by_folder = dict(zip([v.split(':', 1)[1] for v in vs.index], trk))
    floor_of = {f'{TEST}:{s}': int(fl_by_folder[s]) for s in st['stop_id']}
    place_tr = {f'{TRAIN}:{s}': p for s, p in zip(st_tr['stop_id'], st_tr['place'])}
    model = tk.MagModel(W_tr, place_tr, g['ids'])
    mu, mu_table, typical = mu_from_walks(g, pw_tr)
    visits, frames = tk.run(TEST, g, st, pw, W, lambda sid: model, floor_of, mu, export=True)
    tk.snapshots(g, W, place_tr, lambda sid: W_tr, visits, TEST, floor_of, lambda sid: model)
    res = tk.table(g, visits, {'all_26_stops': lambda v: True})
    tk.visits_csv(visits, data.OUT / 'track24_visits.csv')
    t0 = min(st['start_epoch_s'].min(), pw['start'].min())
    replay = {'graph': tk.export_graph(g), 'destination': st['place'].iloc[-1], 'frames': frames,
              'meta': {'day': '2026-11-24 session 2', 't0_epoch_s': float(t0), 'frame_dt_s': tk.FRAME_DT,
                       'method': 'route-aware HMM tracker v2 (tracking/tracker.py unchanged) on graph-v2; magnetic fingerprints, '
                                 f'line lengths and floor threshold from 24-Nov session 1 only ({D_tr} = iPhone19,2); replayed on session 2 ({D_te} = iPhone17,4)',
                       'note': 'frames exist only while a stop or walk was recording; t jumps over the gaps. '
                               'Stop frames: edge_from/edge_to/progress are null. Walk frames: true_node is null.'}}
    (data.OUT / 'replay_24nov_s2.json').write_text(json.dumps(replay, separators=(',', ':')))
    # ---- SAME-handset variant: fingerprints + floor threshold from the 23-Nov stops (ip16, like the test), line lengths from s1 walks
    W23, place23, thr23 = windows_23nov()
    model23 = tk.MagModel(W23, place23, g['ids'])
    trk23 = data.track_floor(vs['hpa_iphone'].to_numpy(), thr23)
    floor23 = {f'{TEST}:{s}': int(f) for s, f in zip([v.split(':', 1)[1] for v in vs.index], trk23)}
    visits23, _ = tk.run(TEST, g, st, pw, W, lambda sid: model23, floor23, mu, export=False)
    tk.snapshots(g, W, place23, lambda sid: W23, visits23, TEST, floor23, lambda sid: model23)
    res23 = tk.table(g, visits23, {'all_26_stops': lambda v: True})
    variant = {'train_fingerprints': f'23 Nov stops ({data.display_names()["ip16"]} = iPhone17,4, same handset as the test)',
               'floor_jump_threshold_hpa': round(thr23, 3),
               'floor_tracking_test': f"{int((trk23 == vs['floor'].to_numpy()).sum())}/{len(trk23)}",
               'line_lengths_from': 'session 1 walks (step counts; the walker is the same, the handset differs)',
               'results': res23}
    out = {'what': 'Tracker on 24 Nov: train session 1, replay session 2 (track24.py). Per stop visit.',
           'graph': 'graph-v2', 'n_places': len(g['ids']), 'train': TRAIN, 'test': TEST, 'phone': PHONE,
           'handsets': {'train': h_tr, 'test': h_te, 'same_handset': h_tr == h_te},
           'devices': {'train': 'iPhone19,2', 'test': 'iPhone17,4 (different handset)'},
           'same_handset_variant': variant,
           'floor_jump_threshold_hpa': round(thr, 3),
           'floor_tracking_test': f"{int((trk == vs['floor'].to_numpy()).sum())}/{len(trk)}",
           'expected_steps_per_line_from_train_walks': mu_table, 'typical_steps_fallback': typical,
           'test_walks': len(pw), 'test_walks_on_a_line_missing_from_graph_v2': edges_missing,
           'test_walk_steps_total': int(pw['steps'].sum()), 'test_walks_steps_unreliable': int((~pw['steps_reliable']).sum()),
           'results': res, 'replay_frames': len(frames),
           'confirmed_frames': {'stop_frames': sum(1 for f in frames if f['true_node']),
                                'confirmed': sum(1 for f in frames if f['confirmed']),
                                'confirmed_and_correct': sum(1 for f in frames if f['confirmed'] and f['node'] == f['true_node'])},
           'caveats': ['the graph and the walk order come from the same route that both sessions walked',
                       'session 2 walks were matched to the last stop that started before them; a few walks in session 2 are '
                       'out of route order (see README)']}
    (data.OUT / 'track24_results.json').write_text(json.dumps(out, indent=1))
    blk = res['all_26_stops']
    for meth in ['tracker', 'snapshot_knn_crossday_recipe', 'emission_only_no_graph', 'tracker_arrival_before_stop_data']:
        print(f'{meth:34s}', ' '.join(f"{m}={blk[meth][m]['k']}/{blk[meth][m]['n']}" for m in blk[meth]))
    b2 = res23['all_26_stops']
    for meth in ['tracker', 'snapshot_knn_crossday_recipe', 'emission_only_no_graph']:
        print('SAME-handset variant', f'{meth:30s}', ' '.join(f"{m}={b2[meth][m]['k']}/{b2[meth][m]['n']}" for m in b2[meth]))
    print({k: v for k, v in out.items() if k not in ('results', 'expected_steps_per_line_from_train_walks', 'same_handset_variant')})


if __name__ == '__main__':
    main()
