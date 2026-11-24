#!/usr/bin/env python3
"""Build edges.csv for the circles-on-lines graph and check nodes.csv / the area rule.

Edges:
  * every 23-Nov walk is an edge between the stop before and the stop after it
    (stops labelled by ../cross-day/labels_23nov_confirmed.csv; walks matched by time in
    ../tracking/pdr.py, which also gives the step counts);
  * the floor-5 map edges (phase2/map/edges_floor5.csv) add their distances (all of them
    were also walked on 23 Nov);
  * floor changes: exit_5_stairs <-> exit_5_stairs_4F (walked 23 Nov), plus the two
    escalators, whose rides show up on 17 Nov as back-to-back stops at the top and bottom
    landings with a one-floor pressure jump (no walk file). No lift ride was recorded,
    so the lifts get no floor-change edge.
Writes edges.csv and area_check.csv. Run after ../tracking/pdr.py.
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
sys.path.insert(0, str(NEW / 'cross-day'))
import crossday as cd   # noqa: E402

PDR = NEW / 'tracking' / 'out'
LONG_M, LONG_STEPS = 10.0, 20          # long edge -> display-only virtual midpoint
AREA_RADIUS_M, AREA_JOIN_STEPS, AREA_SPAN_STEPS = 6.0, 20, 36   # pre-registered area rule (README)
ESCALATOR_RIDES = [('escalator_down', 'escalator_down_4F', '17-Nov BM12 -> BM13 (no walk file; pressure jump)'),
                   ('escalator_up_4F', 'escalator_up', '17-Nov BM23 -> BM24 (no walk file; pressure jump)')]


def load_nodes():
    n = pd.read_csv(HERE / 'nodes.csv', dtype={'on_edge': str}).fillna({'area': '', 'on_edge': ''})
    real = n[n['virtual'] == 0]
    labels = pd.read_csv(NEW / 'cross-day' / 'labels_23nov_confirmed.csv')
    want = set(labels['label'])
    if set(real['node_id']) != want:
        raise SystemExit(f'nodes.csv and labels disagree: {sorted(set(real["node_id"]) ^ want)}')
    return n


def build_edges(nodes):
    w23 = pd.read_csv(PDR / 'pdr_walks_23nov.csv')
    w17 = pd.read_csv(PDR / 'pdr_walks_17nov.csv')
    floor = dict(zip(nodes['node_id'], nodes['floor']))
    mapd = {}
    for a, b, m in pd.read_csv(cd.PHASE2 / 'map' / 'edges_floor5.csv').itertuples(index=False):
        mapd[frozenset((cd.MAP_NAMES[a], cd.MAP_NAMES[b]))] = float(m)
    E = {}

    def get(a, b):
        k = frozenset((a, b))
        if k not in E:
            E[k] = {'from': a, 'to': b, 'walks': [], 'steps': [], 'walks_17': [], 'steps_17': [], 'source': set()}
        return E[k]

    for _, w in w23.iterrows():
        e = get(w['from_place'], w['to_place'])
        e['walks'].append(w['walk_id']); e['source'].add('walk_23nov')
        if w['steps_reliable']:
            e['steps'].append(int(w['steps']))
    for _, w in w17.dropna(subset=['from_place', 'to_place']).iterrows():
        k = frozenset((w['from_place'], w['to_place']))
        if k in E:
            E[k]['walks_17'].append(w['walk_id'])
            if w['steps_reliable']:
                E[k]['steps_17'].append(int(w['steps']))
    for k in mapd:
        a, b = sorted(k)
        get(a, b)['source'].add('map_floor5')
    for a, b, why in ESCALATOR_RIDES:
        e = get(a, b); e['source'].add('escalator_17nov'); e['note'] = why
    rows = []
    for k, e in E.items():
        a, b = e['from'], e['to']
        rows.append({'from': a, 'to': b, 'floor_change': int(floor[a] != floor[b]),
                     'distance_m': mapd.get(k, np.nan),
                     'median_steps': float(np.median(e['steps'])) if e['steps'] else np.nan,
                     'n_walks': len(e['walks']), 'walks_23nov': ' '.join(e['walks']),
                     'median_steps_17nov': float(np.median(e['steps_17'])) if e['steps_17'] else np.nan,
                     'walks_17nov': ' '.join(e['walks_17']),
                     'source': '+'.join(sorted(e['source'])), 'note': e.get('note', '')})
    df = pd.DataFrame(rows)
    df['long_edge'] = ((df['distance_m'] >= LONG_M) | (df['median_steps'] >= LONG_STEPS)) & (df['floor_change'] == 0)
    bad = df[(df['floor_change'] == 1) & ~df['from'].isin(['exit_5_stairs', 'escalator_down', 'escalator_up_4F'])]
    if len(bad):
        raise SystemExit(f'unexpected floor change edges:\n{bad}')
    return df


def check_virtual(nodes, edges):
    v = nodes[nodes['virtual'] == 1]
    longk = {frozenset((a, b)) for a, b in zip(edges.loc[edges['long_edge'], 'from'], edges.loc[edges['long_edge'], 'to'])}
    have = {frozenset(s.split('|')) for s in v['on_edge']}
    if have != longk:
        raise SystemExit(f'virtual midpoints vs long edges differ: {[sorted(x) for x in have ^ longk]}')
    xy = nodes.set_index('node_id')[['x', 'y']]
    for _, r in v.iterrows():
        a, b = r['on_edge'].split('|')
        mid = (xy.loc[a] + xy.loc[b]) / 2
        if np.hypot(*(mid - r[['x', 'y']].astype(float))) > 0.05:
            raise SystemExit(f'{r["node_id"]} is not at the midpoint of {a}-{b}')


def area_check(nodes, edges):
    """Recompute the pre-registered rule's quantities for each area (does not change nodes.csv)."""
    real = nodes[nodes['virtual'] == 0].set_index('node_id')
    # steps per edge; where a walk's steps are unreliable but the floor-5 map distance exists,
    # convert metres to steps with the median 23-Nov stride (out/pdr_summary.json)
    m_per_step = json.loads((PDR / 'pdr_summary.json').read_text())['23Nov']['floor5_map_edges']['median_m_per_step']
    steps = {}
    for _, e in edges.iterrows():
        s = e['median_steps']
        if np.isnan(s) and not np.isnan(e['distance_m']):
            s = round(e['distance_m'] / m_per_step, 1)
        if not np.isnan(s):
            steps[frozenset((e['from'], e['to']))] = s
    rows = []
    for area, g in real.groupby('area'):
        mem = list(g.index)
        co = g[g['xy_source'] == 'floor5_metres']
        rad = float(np.max(np.hypot(co['x'] - co['x'].mean(), co['y'] - co['y'].mean()))) if len(co) else 0.0
        # shortest step paths inside the area (Floyd-Warshall on the area's own edges)
        idx = {m: i for i, m in enumerate(mem)}
        D = np.full((len(mem), len(mem)), np.inf); np.fill_diagonal(D, 0)
        for k, s in steps.items():
            a, b = tuple(k)
            if a in idx and b in idx:
                D[idx[a], idx[b]] = D[idx[b], idx[a]] = min(D[idx[a], idx[b]], s)
        for k_, i, j in itertools.product(range(len(mem)), repeat=3):
            if D[i, k_] + D[k_, j] < D[i, j]:
                D[i, j] = D[i, k_] + D[k_, j]
        span = float(D.max()) if len(mem) > 1 else 0.0
        nocoord_join = []
        for m in (g[g['xy_source'] != 'floor5_metres'].index if len(mem) > 1 else []):
            nb = [steps[k] for k in steps if m in k and (set(k) - {m}) <= set(mem)]
            nocoord_join.append(min(nb) if nb else np.inf)
        rows.append({'area': area, 'floor': int(g['floor'].iloc[0]), 'n_checkpoints': len(mem), 'checkpoints': ' '.join(mem),
                     'radius_m_coordinate_members': round(rad, 2),
                     'longest_step_path': span if np.isfinite(span) else 'not connected by step-counted walks',
                     'worst_join_steps_no_coordinates': max(nocoord_join) if nocoord_join else '',
                     'rule_ok': bool(rad <= AREA_RADIUS_M and (not nocoord_join or max(nocoord_join) <= AREA_JOIN_STEPS)
                                     and (len(mem) == 1 or (np.isfinite(span) and span <= AREA_SPAN_STEPS)))})
    return pd.DataFrame(rows)


def main():
    nodes = load_nodes()
    edges = build_edges(nodes)
    check_virtual(nodes, edges)
    cols = ['from', 'to', 'floor_change', 'distance_m', 'median_steps', 'n_walks', 'source', 'walks_23nov',
            'median_steps_17nov', 'walks_17nov', 'long_edge', 'note']
    edges[cols].to_csv(HERE / 'edges.csv', index=False)
    ac = area_check(nodes, edges)
    ac.to_csv(HERE / 'area_check.csv', index=False)
    real = nodes[nodes['virtual'] == 0]
    fl = dict(zip(real['node_id'], real['floor']))
    for f in [5, 4]:
        ne = sum(1 for a, b, c in zip(edges['from'], edges['to'], edges['floor_change']) if not c and fl[a] == f)
        print(f'floor {f}: {int((real["floor"] == f).sum())} nodes, {ne} same-floor edges')
    print('floor-change edges:', int(edges['floor_change'].sum()), '| total edges', len(edges), '| long edges', int(edges['long_edge'].sum()))
    print(ac.to_string(index=False))


if __name__ == '__main__':
    main()
