#!/usr/bin/env python3
"""Exact and area accuracy per stop visit, graph v1 (out/) vs graph-v2 merged places (out-v2/).

Run after:  python phase2/new/cross-day/crossday.py  and  python phase2/new/cross-day/crossday.py --v2
Then:       python phase2/new/cross-day/compare_v1_v2.py
Writes out-v2/v1_vs_v2.json and out-v2/v1_vs_v2.csv. Nothing in out/ is written.

"Area" = the pre-registered area of the place (graph/nodes.csv for v1, graph-v2/nodes.csv for v2;
the area groups themselves are the same, the merges only rename places inside them).
Intervals are 95% Wilson intervals on the visit count.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
EXPERIMENTS = ['revisit_23', 'revisit_23_reverse', 'cross_core', 'cross_extended']
METHODS = [('mag', 'magnitude_knn'), ('mag', 'magnitude_knn_baro_floor'), ('mag', 'magnitude_xyz_knn'),
           ('mag', 'magnitude_xyz_knn_baro_floor'), ('wifi', 'rssi_knn'), ('wifi', 'rssi_rf'), ('wifi', 'rssi_rf_baro_floor')]


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def areas(path):
    with open(path, newline='') as f:
        return {r['node_id']: r['area'] for r in csv.DictReader(f) if r['virtual'] == '0'}


def main():
    res = {'v1': json.loads((HERE / 'out' / 'results.json').read_text()),
           'v2': json.loads((HERE / 'out-v2' / 'results.json').read_text())}
    area = {'v1': areas(NEW / 'graph' / 'nodes.csv'), 'v2': areas(NEW / 'graph-v2' / 'nodes.csv')}
    out, rows = {'what': 'Exact and area accuracy per stop visit, v1 places vs graph-v2 merged places. Computed by compare_v1_v2.py '
                         'from out/results.json and out-v2/results.json.', 'experiments': {}}, []
    for e in EXPERIMENTS:
        for ver in ['v1', 'v2']:
            R = res[ver]['results'][e]
            for mod, m in METHODS:
                vp = R[mod][m]['visit_predictions']
                n = len(vp)
                ex = sum(v['true'] == v['pred'] for v in vp.values())
                missing = sorted({v[k] for v in vp.values() for k in ('true', 'pred')} - set(area[ver]))
                ar = sum(area[ver].get(v['true']) == area[ver].get(v['pred']) for v in vp.values())
                ch = R[mod]['_split']['chance_accuracy']
                row = {'experiment': e, 'graph': ver, 'modality': mod, 'method': m, 'n_visits': n,
                       'exact': ex, 'exact_acc': round(ex / n, 3) if n else None, 'exact_ci95': wilson(ex, n),
                       'area': ar, 'area_acc': round(ar / n, 3) if n else None, 'area_ci95': wilson(ar, n),
                       'chance_exact': ch, 'n_train_places': R[mod]['_split']['train_places'],
                       'places_without_area': missing}
                rows.append(row)
                out['experiments'].setdefault(e, {}).setdefault(ver, {})[m] = row
        # Same test visits only (v2 adds extra revisit test visits because merging creates new "revisits").
        if e.startswith('revisit'):
            for mod, m in METHODS:
                v1p = res['v1']['results'][e][mod][m]['visit_predictions']
                v2p = res['v2']['results'][e][mod][m]['visit_predictions']
                common = sorted(set(v1p) & set(v2p))
                out['experiments'][e].setdefault('same_test_visits_v2', {})[m] = {
                    'visits': common, 'n': len(common),
                    'v1_exact': sum(v1p[k]['true'] == v1p[k]['pred'] for k in common),
                    'v2_exact': sum(v2p[k]['true'] == v2p[k]['pred'] for k in common),
                    'v2_only_test_visits': sorted(set(v2p) - set(v1p))}
    (HERE / 'out-v2' / 'v1_vs_v2.json').write_text(json.dumps(out, indent=1))
    with open(HERE / 'out-v2' / 'v1_vs_v2.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (' '.join(map(str, v)) if isinstance(v, list) else v) for k, v in r.items()})
    for r in rows:
        if r['method'] in ('magnitude_xyz_knn', 'magnitude_xyz_knn_baro_floor', 'magnitude_knn_baro_floor', 'rssi_rf_baro_floor'):
            print(f"{r['experiment']:20s} {r['graph']} {r['method']:30s} exact {r['exact']}/{r['n_visits']} area {r['area']}/{r['n_visits']} "
                  f"chance {r['chance_exact']} {r['places_without_area'] or ''}")


if __name__ == '__main__':
    main()
