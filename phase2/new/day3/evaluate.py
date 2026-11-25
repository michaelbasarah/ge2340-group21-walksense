#!/usr/bin/env python3
"""Day-3 (24 Nov) evaluation: cross-session, cross-day, walk-endpoint tilt and barometer floor.

Run:  python phase2/new/day3/evaluate.py         writes out/results.json and out/summary_table.csv

Every split is by whole recordings: train and test never share a session, so no recording or window
is in both. Accuracy is per stop recording (window votes summed, see gknn.py). Chance = 1 / number of
places in training. Places are graph-v2 names (names_24nov.csv). kNN k = 5, equal group weights; the
learned-weight model is in fused_knn.py.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import data
import gknn

FEATURE_SETS = {
    '|B|': {'B': 1}, '|B|+xyz': {'B': 1, 'xyz': 1}, 'tilt': {'tilt': 1}, '|B|+tilt': {'B': 1, 'tilt': 1},
    '|B|+xyz+tilt': {'B': 1, 'xyz': 1, 'tilt': 1}, 'Wi-Fi': {'wifi': 1}, '|B|+xyz+Wi-Fi': {'B': 1, 'xyz': 1, 'wifi': 1},
    '|B|+tilt+Wi-Fi': {'B': 1, 'tilt': 1, 'wifi': 1}}
K = 5


def run_split(bank, tr, te, train_sessions, area, feature_sets=FEATURE_SETS, note=''):
    tr, te = np.asarray(tr), np.asarray(te)
    assert not set(bank.rec[tr]) & set(bank.rec[te]), 'recording in both train and test'
    assert not set(bank.vis[tr]) & set(bank.vis[te]), 'stop visit in both train and test'
    groups = sorted({g for fs in feature_sets.values() for g in fs})
    thr = bank.floor_threshold(train_sessions)
    dd = bank.dists(tr, te, groups + ['baro'], thr)
    ytr = bank.y[tr]
    classes = sorted(set(ytr))
    truth = dict(zip(bank.rec[te], bank.y[te]))
    out = {'_split': {'train_recordings': int(len(set(bank.rec[tr]))), 'test_recordings': int(len(set(bank.rec[te]))),
                      'train_places': len(classes), 'chance': round(1 / len(classes), 3),
                      'test_places_not_in_train': sorted(set(bank.y[te]) - set(classes)),
                      'floor_jump_threshold_hpa': round(thr, 3), 'note': note}}
    gate = dd['baro'][0] == 0
    for name, w in feature_sets.items():
        if any(g not in dd or not dd[g][1].any() or not dd[g][2].any() for g in w):
            out[name] = {'skipped': 'a feature group is missing in train or test (e.g. no accelerometer at 23-Nov stops)'}
            continue
        D = bank.combine(dd, w)
        for fused, gt in [('', None), (' + baro floor', gate)]:
            S, _ = gknn.knn_scores(D, ytr, classes, [K], gt)
            pred = gknn.aggregate(S[K], bank.rec[te], classes)
            win_acc = float(np.mean(np.array(classes, dtype=object)[S[K].argmax(1)] == bank.y[te]))
            r = gknn.score_records(pred, truth, area)
            r['window_acc'] = round(win_acc, 3)
            r['predictions'] = {k: [truth[k], pred[k]] for k in sorted(pred)}
            out[name + fused] = r
    return out


def block_split(bank, keys, area):
    """LEAKY reference: inside each recording, first 60% of windows train, skip one, rest test."""
    W = bank.W
    tr, te = [], []
    for k in keys:
        idx = np.where(bank.rec == k)[0]
        idx = idx[np.argsort(W.loc[idx, 'window'].to_numpy())]
        n = max(1, int(round(len(idx) * 0.6)))
        tr += list(idx[:n]); te += list(idx[n + 1:])
    tr, te = np.array(tr), np.array(te)
    dd = bank.dists(tr, te, ['B', 'xyz', 'tilt'])
    ytr = bank.y[tr]; classes = sorted(set(ytr))
    truth = dict(zip(bank.rec[te], bank.y[te]))
    out = {'_split': {'chance': round(1 / len(classes), 3), 'note': 'LEAKY: same recording in train and test (time split)'}}
    for name in ['|B|', '|B|+xyz', 'tilt', '|B|+xyz+tilt']:
        S, _ = gknn.knn_scores(bank.combine(dd, FEATURE_SETS[name]), ytr, classes, [K])
        out[name] = gknn.score_records(gknn.aggregate(S[K], bank.rec[te], classes), truth, area)
    return out


def endpoint_test(E, tr_mask, te_mask, area):
    """Walk endpoints (first/last 2 s of walks), 1-NN as in cross-day/tilt.py, per endpoint."""
    tr, te = E[tr_mask], E[te_mask]
    te = te[te['place'].isin(set(tr['place']))]
    out = {'n_train_endpoints': len(tr), 'n_test_endpoints': len(te), 'train_places': int(tr['place'].nunique()),
           'chance': round(1 / tr['place'].nunique(), 3)}
    for name, cols in [('|B|', ['B']), ('raw x/y/z', ['x', 'y', 'z']), ('tilt (Bv,Bh)', ['Bv', 'Bh']), ('|B|+tilt', ['B', 'Bv', 'Bh'])]:
        A, B = tr[cols].to_numpy(float), te[cols].to_numpy(float)
        mu, sd = A.mean(0), A.std(0) + 1e-9
        d = (((B - mu) / sd)[:, None, :] - ((A - mu) / sd)[None, :, :]) ** 2
        pred = tr['place'].to_numpy()[d.sum(-1).argmin(1)]
        ok = pred == te['place'].to_numpy()
        ar = np.array([area.get(p) == area.get(t) for p, t in zip(pred, te['place'])])
        out[name] = {'exact': int(ok.sum()), 'exact_acc': round(float(ok.mean()), 3), 'exact_ci95': gknn.wilson(int(ok.sum()), len(ok)),
                     'area': int(ar.sum()), 'area_acc': round(float(ar.mean()), 3)}
    return out


def floor_eval(V):
    """Barometer floor per stop. iPhone: step tracking with a threshold learned on the other sessions."""
    res, stats = {}, {}
    for ph in ['iphone', 's24']:
        col = f'hpa_{ph}'
        for s, v in V.groupby('session'):
            v = v.sort_values('start')
            if v[col].notna().sum() < 2:
                continue
            p, f = v[col].to_numpy(), v['floor'].to_numpy()
            ch = np.diff(f) != 0
            f5 = v[v['floor'] == 5]
            stats[f'{s}_{ph}'] = {'floor_step_hpa': [round(float(x), 3) for x in np.diff(p)[ch]],
                                  'largest_same_floor_consecutive_change_hpa': round(float(np.nanmax(np.abs(np.diff(p))[~ch])), 3),
                                  'within_stop_sd_hpa_median': round(float(v[f'hpa_sd_{ph}'].median()), 3),
                                  'f5_range_hpa': round(float(f5[col].max() - f5[col].min()), 3),
                                  'f5_median_hpa': round(float(f5[col].median()), 3),
                                  'f4_median_hpa': round(float(v[v['floor'] == 4][col].median()), 3), 'n_stops': len(v)}
        for s, v in V.groupby('session'):
            v = v.sort_values('start')
            if v[col].notna().sum() < 2:
                continue
            others = [o for o in V['session'].unique() if o != s and V[V['session'] == o][col].notna().sum() >= 2]
            if not others:
                continue
            steps, f5s, f4s = [], [], []
            for o in others:
                w = V[V['session'] == o].sort_values('start')
                pp, ff = w[col].to_numpy(), w['floor'].to_numpy()
                steps += list(np.abs(np.diff(pp))[np.diff(ff) != 0])
                f5s.append(w[w['floor'] == 5][col].median()); f4s.append(w[w['floor'] == 4][col].median())
            T = float(np.median(steps)) / 2
            p, f = v[col].to_numpy(), v['floor'].to_numpy()
            trk = data.track_floor(p, T)
            thr = (np.mean(f5s) + np.mean(f4s)) / 2
            absolute = np.where(p > thr, 4, 5)
            hk = lambda e: pd.Timestamp(e, unit='s', tz='Asia/Hong_Kong').strftime('%H:%M')
            res[f'{ph}_test_{s}'] = {'trained_on': others, 'jump_threshold_hpa': round(T, 3),
                                     'step_tracking': f'{int((trk == f).sum())}/{len(f)}',
                                     'step_tracking_wrong_stops': [{'start_hk': hk(t0), 'place': pl, 'true': int(a), 'pred': int(b),
                                                                    'jump_from_previous_stop_hpa': round(float(d), 3)}
                                                                   for t0, pl, a, b, d in zip(v['start'], v['place'], f, trk, np.r_[0, np.diff(p)]) if a != b],
                                     'absolute_threshold_hpa': round(float(thr), 3),
                                     'absolute_threshold': f'{int((absolute == f).sum())}/{len(f)}'}
    return res, stats


def main():
    D = data.load()
    area = data.places()['area'].to_dict()
    bank = gknn.Bank(D, wifi_rows='near', wifi_scanner='s24')
    bank_in = gknn.Bank(D, wifi_rows='in_window', wifi_scanner='s24')
    W = bank.W
    sel = lambda s, ph: np.where((W['session'] == s) & (W['phone'] == ph))[0]
    devices = W.groupby(['session', 'phone'])['device'].first().to_dict()
    R = {}
    # ---- 2a cross-session, same phone role
    for ph in ['iphone', 's24']:
        for a, b in [('24s1', '24s2'), ('24s2', '24s1')]:
            same = devices[(a, ph)] == devices[(b, ph)]
            note = f"{ph}: train {devices[(a, ph)]}, test {devices[(b, ph)]} ({'same handset' if same else 'DIFFERENT handsets'})"
            R[f'xsession_{a}_to_{b}_{ph}'] = run_split(bank, sel(a, ph), sel(b, ph), [a], area, note=note)
            R[f'xsession_{a}_to_{b}_{ph}']['Wi-Fi (in-window rows only)'] = run_split(
                bank_in, sel(a, ph), sel(b, ph), [a], area, {'Wi-Fi': {'wifi': 1}})['Wi-Fi']
    # ---- 2b cross-day, iPhone stops
    for a, b, tag in [('23nov', '24s2', 'same handset iPhone17,4'), ('24s2', '23nov', 'same handset iPhone17,4'),
                      ('23nov', '24s1', 'DIFFERENT handsets: 23nov iPhone17,4, 24s1 iPhone19,2')]:
        R[f'xday_{a}_to_{b}_iphone'] = run_split(bank, sel(a, 'iphone'), sel(b, 'iphone'), [a], area, note=tag)
    tr = np.concatenate([sel('23nov', 'iphone'), sel('24s1', 'iphone')])
    R['xday_23nov+24s1_to_24s2_iphone'] = run_split(bank, tr, sel('24s2', 'iphone'), ['23nov', '24s1'], area,
                                                    note='train two earlier sessions (two iPhone handsets), test 24s2 iPhone17,4')
    # ---- leaky reference
    R['LEAKY_same_recording_time_split_24s2_iphone'] = block_split(bank, sorted(set(bank.rec[sel('24s2', 'iphone')])), area)
    R['LEAKY_same_recording_time_split_24s2_s24'] = block_split(bank, sorted(set(bank.rec[sel('24s2', 's24')])), area)
    # ---- walk endpoints (tilt), same handset
    E = D['E']
    m = lambda s, ph: (E['session'] == s) & (E['phone'] == ph)
    EP = {'23nov_to_24s1_iphone (iPhone19,2 both days)': (m('23nov', 'iphone'), m('24s1', 'iphone')),
          '24s1_to_23nov_iphone (iPhone19,2 both days)': (m('24s1', 'iphone'), m('23nov', 'iphone')),
          '24s1_to_24s2_s24 (same handset)': (m('24s1', 's24'), m('24s2', 's24')),
          '24s2_to_24s1_s24 (same handset)': (m('24s2', 's24'), m('24s1', 's24')),
          '24s1_to_24s2_iphone (DIFFERENT handsets)': (m('24s1', 'iphone'), m('24s2', 'iphone'))}
    R_ep = {k: endpoint_test(E, a, b, area) for k, (a, b) in EP.items()}
    fl, fstats = floor_eval(D['V'])
    med = D['W'].groupby(['session', 'phone', 'place'])['B_mean'].median()
    outliers = [{'session': s, 'phone': ph, 'place': pl, 'median_B_uT': round(float(x), 1)} for (s, ph, pl), x in med.items() if x > 100]
    rng = {f'{s}/{ph}': [round(float(x.min()), 1), round(float(x.max()), 1)] for (s, ph), x in med.groupby(level=[0, 1])}
    results = {'what': 'Day-3 (24 Nov) evaluation, computed by phase2/new/day3/evaluate.py. Accuracy per stop recording unless noted.',
               'settings': {'window_s': D['config']['window_s'], 'k': K, 'weights': 'equal per feature group',
                            'wifi': 'nearest stop within 120 s, s24 scanner only (the same scanner phone in every session)',
                            'places': 'graph-v2 names via names_24nov.csv', 'area': 'graph-v2/nodes.csv area column'},
               'devices': {f'{s}/{p}': d for (s, p), d in devices.items()},
               'unmapped_names': D['unmapped'],
               'magnetic_check': {'stops_with_median_B_above_100uT': outliers, 'per_session_phone_range_of_place_median_B_uT': rng},
               'stop_results': R, 'walk_endpoint_results': R_ep, 'floor': fl, 'floor_stats': fstats}
    data.OUT.mkdir(exist_ok=True)
    (data.OUT / 'results.json').write_text(json.dumps(results, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    rows = []
    for e, blk in R.items():
        for fs, r in blk.items():
            if fs.startswith('_') or 'exact' not in r:
                continue
            rows.append({'experiment': e, 'feature_set': fs, 'n': r['n_recordings'], 'exact': r['exact'], 'exact_acc': r['exact_acc'],
                         'exact_ci95': r['exact_ci95'], 'area': r.get('area'), 'area_acc': r.get('area_acc'),
                         'window_acc': r.get('window_acc'), 'chance': blk['_split']['chance']})
    for e, r in R_ep.items():
        for fs in ['|B|', 'raw x/y/z', 'tilt (Bv,Bh)', '|B|+tilt']:
            rows.append({'experiment': 'walk_endpoints_' + e, 'feature_set': fs, 'n': r['n_test_endpoints'], 'exact': r[fs]['exact'],
                         'exact_acc': r[fs]['exact_acc'], 'exact_ci95': r[fs]['exact_ci95'], 'area': r[fs]['area'],
                         'area_acc': r[fs]['area_acc'], 'window_acc': None, 'chance': r['chance']})
    T = pd.DataFrame(rows)
    T.to_csv(data.OUT / 'summary_table.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 400)
    print(T.drop(columns=['exact_ci95']).to_string())
    print(json.dumps(fl, indent=1)); print(json.dumps(fstats, indent=1))


if __name__ == '__main__':
    main()
