#!/usr/bin/env python3
"""Wi-Fi diagnosis: does WiGLE's CSV give repeated scans, and do two visits of one place share access points?

Run:  python phase2/new/day3/wifi_check.py      writes out/wifi_diagnosis.json
Uses every session in config.json (Wi-Fi rows from each session's WiGLE logs).
"""
from __future__ import annotations

import json
from itertools import combinations

import numpy as np
import pandas as pd

import data


def log_stats(A: pd.DataFrame) -> list[dict]:
    """Per WiGLE log: how often is one BSSID written, and is a repeat always stronger than before?"""
    out = []
    for (sess, log), g in A.groupby(['session', 'source_log']):
        g = g.sort_values('epoch')
        per = g.groupby('bssid').size()
        rep_stronger, rep_gap = [], []
        for _, h in g.groupby('bssid'):
            if len(h) < 2:
                continue
            r, e = h['rssi'].to_numpy(), h['epoch'].to_numpy()
            best = np.maximum.accumulate(r)
            rep_stronger += list(r[1:] > best[:-1])
            rep_gap += list(np.diff(e))
        out.append({'session': sess, 'log': log, 'scanner': g['scanner'].iloc[0] if 'scanner' in g else '',
                    'rows': len(g), 'unique_bssids': int(per.size),
                    'rows_per_bssid_median': float(per.median()), 'rows_per_bssid_mean': round(float(per.mean()), 2),
                    'share_bssids_with_one_row': round(float((per == 1).mean()), 3),
                    'repeat_rows': len(rep_stronger),
                    'share_repeats_stronger_than_all_earlier_rows': round(float(np.mean(rep_stronger)), 3) if rep_stronger else None,
                    'repeat_gap_s_median': float(np.median(rep_gap)) if rep_gap else None,
                    'distinct_timestamps': int(g['epoch'].nunique()),
                    'span_min': round(float((g['epoch'].max() - g['epoch'].min()) / 60), 1)})
    return out


def dwell_stats(O: pd.DataFrame, V: pd.DataFrame) -> dict:
    """Inside each 60 s stop: how many scan timestamps, BSSIDs, rows per BSSID."""
    out = {}
    for sess, Vs in V.groupby('session'):
        o = O[(O['session'] == sess) & O['in_window']]
        per = []
        for v in Vs['visit']:
            g = o[o['visit'] == v]
            for sc, h in g.groupby('scanner'):
                per.append({'scans': h['epoch'].nunique(), 'bssids': h['bssid'].nunique(), 'rows': len(h),
                            'rows_per_bssid': len(h) / max(1, h['bssid'].nunique())})
        p = pd.DataFrame(per)
        out[sess] = {'stop_visits': len(Vs), 'stop_x_scanner_pairs_with_in_window_rows': len(p),
                     'distinct_scan_timestamps_per_60s_stop_median': float(p['scans'].median()) if len(p) else 0,
                     'bssids_per_stop_median': float(p['bssids'].median()) if len(p) else 0,
                     'rows_per_bssid_inside_one_stop_median': round(float(p['rows_per_bssid'].median()), 2) if len(p) else 0,
                     'rows_per_bssid_inside_one_stop_max': round(float(p['rows_per_bssid'].max()), 2) if len(p) else 0}
    return out


def spread(O: pd.DataFrame, V: pd.DataFrame, in_window_only: bool) -> dict:
    """Within one session: how many stop visits does a BSSID appear at?"""
    out = {}
    for sess in V['session'].unique():
        o = O[(O['session'] == sess) & (O['in_window'] if in_window_only else True)]
        n = o.groupby('bssid')['visit'].nunique()
        out[sess] = {'bssids': int(n.size), 'share_heard_at_one_stop_only': round(float((n == 1).mean()), 3),
                     'share_heard_at_3plus_stops': round(float((n >= 3).mean()), 3)}
    return out


def cross_session_overlap(O: pd.DataFrame, V: pd.DataFrame, in_window_only: bool, scanner: str | None) -> dict:
    """For each pair of sessions: Jaccard of BSSID sets, same place vs other places; share of test BSSIDs ever seen in training."""
    o = O[O['in_window']] if in_window_only else O
    if scanner:
        o = o[o['scanner'] == scanner]
    sets = {}
    for (sess, v), g in o.groupby(['session', 'visit']):
        sets[(sess, v)] = set(g['bssid'])
    place = dict(zip(V['visit'], V['place']))
    res = {}
    for a, b in combinations(sorted(V['session'].unique()), 2):
        A = {v: s for (ss, v), s in sets.items() if ss == a}
        B = {v: s for (ss, v), s in sets.items() if ss == b}
        if not A or not B:
            continue
        seen_a = set().union(*A.values())
        same, other, rank1, seen = [], [], [], []
        for vb, sb in B.items():
            js = {va: len(sa & sb) / max(1, len(sa | sb)) for va, sa in A.items()}
            s_same = [j for va, j in js.items() if place[va] == place[vb]]
            s_oth = [j for va, j in js.items() if place[va] != place[vb]]
            if s_same:
                same.append(max(s_same)); other.append(float(np.mean(s_oth)))
                rank1.append(place[max(js, key=js.get)] == place[vb])
            seen.append(len(sb & seen_a) / max(1, len(sb)))
        res[f'{a}_vs_{b}'] = {'test_visits_with_wifi': len(B), 'train_visits_with_wifi': len(A),
                              'jaccard_same_place_median': round(float(np.median(same)), 3) if same else None,
                              'jaccard_other_places_median': round(float(np.median(other)), 3) if other else None,
                              'nearest_by_jaccard_is_same_place': f'{int(np.sum(rank1))}/{len(rank1)}',
                              'share_of_test_bssids_ever_heard_in_train_session_median': round(float(np.median(seen)), 3)}
    return res


def main():
    D = data.load()
    A, O, V = D['A'], D['O'], D['V']
    res = {'what': 'Wi-Fi diagnosis on WiGLE CSV logs. Computed by wifi_check.py.',
           'assignment': f"each row -> nearest stop in time, kept if <= {D['config']['wifi_nearest_stop_max_gap_s']} s away; in_window = inside the stop dwell",
           'per_log': log_stats(A),
           'inside_one_stop': dwell_stats(O, V),
           'bssid_spread_within_session': {'in_window': spread(O, V, True), 'nearest_stop_120s': spread(O, V, False)},
           'cross_session_overlap': {
               'in_window_all_scanners': cross_session_overlap(O, V, True, None),
               'nearest_stop_120s_all_scanners': cross_session_overlap(O, V, False, None),
               'nearest_stop_120s_s24_only': cross_session_overlap(O, V, False, 's24')},
           'rows_assigned': {s: {'in_window': int(g['in_window'].sum()), 'within_120s': len(g)} for s, g in O.groupby('session')},
           'stops_with_any_wifi': {s: f"{O[O['session'] == s]['visit'].nunique()}/{int((V['session'] == s).sum())}" for s in V['session'].unique()}}
    data.OUT.mkdir(exist_ok=True)
    (data.OUT / 'wifi_diagnosis.json').write_text(json.dumps(res, indent=1, default=float))
    print(pd.DataFrame(res['per_log']).to_string())
    for k in ['inside_one_stop', 'bssid_spread_within_session', 'cross_session_overlap', 'rows_assigned', 'stops_with_any_wifi']:
        print(k, json.dumps(res[k], indent=1, default=float))


if __name__ == '__main__':
    main()
