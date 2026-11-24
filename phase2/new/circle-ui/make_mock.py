#!/usr/bin/env python3
"""Build a MOCK replay for the circle UI (stdlib only).

Reads  ../cross-day/labels_23nov_confirmed.csv   (the 23-Nov route in stop order, 42 stops, 31 places)
Writes mock_replay.json   (same format the tracker will produce: graph, destination, frames)
       mock_replay.js     (same JSON as `window.MOCK_REPLAY = ...`, so the page also works from file://)
       places_data.js     (Dicta's destinations.csv aliases as `window.PLACES`, for the offline keyword search)

Everything here is FAKE except the place names/floors and their visiting order:
 - x,y are a hand-made schematic (arbitrary units), not map coordinates
 - distance_m / median_steps come from that schematic
 - steps, progress and top3 are random (fixed seed), not model output

Run:  python make_mock.py
"""
import csv
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = HERE.parent / 'cross-day' / 'labels_23nov_confirmed.csv'
DESTS = HERE.parent.parent / 'request-matching' / 'destinations.csv'
DESTINATION = 'lt1a'          # green circle in the mock
RNG = random.Random(23)

# schematic layout (arbitrary units; the page fits each floor to its panel)
XY = {
    # floor 5
    'y5302': (20, 25), 'sr11': (80, 25), 'sr10': (140, 25), 'sr9': (200, 25), 'sr8': (260, 25),
    'y5202': (295, 75), 'female_toilet': (295, 120), 'exit_10': (295, 170),
    'escalator_up': (235, 135), 'escalator_down': (175, 135), 'canteen': (160, 80),
    'male_toilet': (20, 75), 'exit_5': (20, 125), 'disabled_toilet': (20, 180), 'lift_5': (20, 235),
    'exit_5_stairs': (90, 265), 'y5401': (180, 265), 'y5302_back': (135, 218),
    # floor 4
    'exit_5_stairs_4F': (25, 40), 'lift_5_4F': (25, 95), 'disabled_toilet_4F': (25, 150),
    'exit_5_4F': (25, 205), 'lt2a': (95, 245), 'lt2b': (175, 245), 'escalator_down_4F': (255, 215),
    'y4502': (292, 150), 'escalator_up_4F': (270, 85), 'lt1b': (215, 30), 'lt1a': (150, 30),
    'exit_10_4F': (100, 70), 'entrance_exit': (110, 130),
}
UNIT_M = 0.18      # schematic unit -> fake metres
STEP_M = 0.7       # fake step length
FLOOR_CHANGE_M = 12.0


def kind_of(i):
    if 'toilet' in i: return 'toilet'
    if 'stairs' in i: return 'stairs'
    if i.startswith('lift'): return 'lift'
    if i.startswith('escalator'): return 'escalator'
    if 'exit' in i: return 'exit'
    if i == 'canteen': return 'food'
    if i.startswith('lt'): return 'lecture'
    if i.startswith('sr'): return 'study'
    return 'room'


# AREAS: groups of neighbouring checkpoints (the node "zone" field holds the area id)
AREAS = {
    '5F-canteen': ['canteen', 'escalator_up', 'escalator_down'],
    '5F-lift-lobby': ['exit_5', 'male_toilet', 'disabled_toilet', 'lift_5'],
    '5F-study-corridor': ['y5302', 'sr11', 'sr10', 'sr9', 'sr8'],
    '5F-east-wing': ['y5202', 'female_toilet', 'exit_10'],
    '5F-stairs-y5401': ['exit_5_stairs', 'y5401', 'y5302_back'],
    '4F-stairs-lift': ['exit_5_stairs_4F', 'lift_5_4F', 'disabled_toilet_4F', 'exit_5_4F'],
    '4F-lecture-theatres-2': ['lt2a', 'lt2b'],
    '4F-escalators': ['escalator_down_4F', 'y4502', 'escalator_up_4F'],
    '4F-lecture-theatres-1': ['lt1b', 'lt1a'],
    '4F-entrance': ['exit_10_4F', 'entrance_exit'],
}
ZONE = {n: z for z, ns in AREAS.items() for n in ns}


def zone_of(node_id):
    return ZONE[node_id]


def main():
    rows = list(csv.DictReader(LABELS.open(encoding='utf-8')))
    order = [r['label'] for r in rows]
    floor_of = {r['label']: int(r['floor']) for r in rows}
    missing = [k for k in floor_of if k not in XY]
    assert not missing, missing

    nodes = [{'id': k, 'floor': floor_of[k], 'x': XY[k][0], 'y': XY[k][1], 'kind': kind_of(k),
              'zone': zone_of(k), 'virtual': False} for k in floor_of]

    edges, seen = [], {}
    for a, b in zip(order, order[1:]):
        if a == b:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        fc = floor_of[a] != floor_of[b]
        d = FLOOR_CHANGE_M if fc else math.dist(XY[a], XY[b]) * UNIT_M
        e = {'from': a, 'to': b, 'floor_change': fc, 'distance_m': round(d, 1),
             'median_steps': max(4, round(d / STEP_M))}
        seen[key] = e
        edges.append(e)
    nbrs = {}
    for e in edges:
        nbrs.setdefault(e['from'], []).append(e['to'])
        nbrs.setdefault(e['to'], []).append(e['from'])

    def edge(a, b):
        return seen[tuple(sorted((a, b)))]

    frames, t, steps = [], 0.0, 0

    def wrong_guess(n):
        return RNG.choice(nbrs[n])

    def top3_at(n, good):
        top = n if good else wrong_guess(n)
        p = round(RNG.uniform(0.62, 0.95) if good else RNG.uniform(0.40, 0.55), 2)
        others = [x for x in nbrs[n] + [n] if x != top]
        RNG.shuffle(others)
        if not good and n not in [top]:
            others = [n] + [x for x in others if x != n]
        o1, o2 = others[0], others[1] if len(others) > 1 else others[0]
        r = 1 - p
        return [[top, p], [o1, round(r * 0.6, 2)], [o2, round(r * 0.25, 2)]]

    for i, node in enumerate(order):
        nxt = order[i + 1] if i + 1 < len(order) and order[i + 1] != node else None
        fl = floor_of[node]
        # dwell at the stop: first frame is sometimes still a wrong tentative guess
        for k in range(RNG.randint(3, 5)):
            tentative = (k == 0 and i > 0 and RNG.random() < 0.18)
            good = not tentative
            frames.append({'t': round(t, 1), 'floor': fl, 'edge_from': node, 'edge_to': nxt,
                           'progress': 0.0 if nxt else None,
                           'node': node if good else wrong_guess(node), 'confirmed': good,
                           'top3': top3_at(node, good), 'true_node': node, 'steps_total': steps})
            t += 1.0
        if not nxt:
            continue
        e = edge(node, nxt)
        med = e['median_steps']
        actual = max(3, round(med * RNG.uniform(0.85, 1.2)))
        in_edge = 0
        while in_edge < actual:
            inc = max(1, round(RNG.gauss(1.7, 0.4)))
            inc = min(inc, actual - in_edge)
            in_edge += inc
            steps += inc
            if in_edge >= actual:
                break
            p = min(0.97, in_edge / med)
            f = fl
            if e['floor_change'] and p > 0.5:
                f = floor_of[nxt]
            pn = round(0.18 + 0.7 * p, 2)
            third = [x for x in nbrs[nxt] if x != node]
            frames.append({'t': round(t, 1), 'floor': f, 'edge_from': node, 'edge_to': nxt,
                           'progress': round(p, 2), 'node': None, 'confirmed': False,
                           'top3': [[nxt, pn], [node, round(max(0.05, 0.9 - pn) * 0.7, 2)],
                                    [RNG.choice(third) if third else node, 0.04]] if p > 0.5 else
                                   [[node, round(1 - pn, 2)], [nxt, pn], [RNG.choice(nbrs[node]), 0.04]],
                           'true_node': None, 'steps_total': steps})
            t += 1.0

    out = {'graph': {'nodes': nodes, 'edges': edges}, 'destination': DESTINATION, 'frames': frames}
    (HERE / 'mock_replay.json').write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    (HERE / 'mock_replay.js').write_text('window.MOCK_REPLAY = ' + json.dumps(out, separators=(',', ':')) + ';\n',
                                         encoding='utf-8')

    # Dicta's destination table -> JS (offline keyword search)
    places = list(csv.DictReader(DESTS.open(encoding='utf-8')))
    (HERE / 'places_data.js').write_text(
        '// From phase2/request-matching/destinations.csv (Dicta). Regenerate with make_mock.py.\n'
        'window.PLACES = ' + json.dumps(places, indent=0) + ';\n', encoding='utf-8')
    print(f'{len(nodes)} nodes, {len(edges)} edges, {len(frames)} frames, {t:.0f} s, {steps} steps')


if __name__ == '__main__':
    main()
