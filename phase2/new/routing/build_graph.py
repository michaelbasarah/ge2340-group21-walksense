"""Build graph.json (the one routing graph) from graph-v2 plus the best edge lengths we have.

Run from anywhere:  python phase2/new/routing/build_graph.py

Length priority per edge (the source is stored on the edge, guesses are marked):
  1. measured  : pin-to-pin metres from phase2/map/edges_floor5.csv (the two study-room legs are the sums of the
                 measured legs through the study-room cluster, because graph-v2 merged sr8..sr11 into sr9)
  2. steps     : median step count of the 23-Nov walk (graph-v2/edges.csv) x STRIDE_M (median 23-Nov stride,
                 tracking/out/pdr_summary.json); NOT surveyed, to be confirmed
  3. guess     : nothing measured for this edge (value says how it was made up)
Cross-floor edges carry a time, not a distance from a map.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent.parent                      # phase2/
SPEED_MPS = 1.3                              # walking speed given for this task
ESCALATOR_RIDE_S = 20.0                      # GUESS (no timed ride exists), the team must time one
STAIRS_REVERSE_ASSUMED = True                # only 5F -> 4F was timed (ACC23); 4F -> 5F uses the same time

NAMES = {
    'canteen': 'Canteen entrance', 'exit_5': 'Exit 5 (emergency exit)', 'male_toilet': 'Male toilet',
    'y5302': 'Room Y5-302 (front door)', 'sr9': 'Study rooms (Y5-511 to Y5-514)', 'y5202': 'Room Y5-202',
    'female_toilet': 'Female toilet', 'exit_10': 'Exit 10 (by the toilets)', 'escalator_up': 'Up escalator (5F)',
    'escalator_down': 'Down escalator (5F)', 'disabled_toilet': 'Disabled toilet (5F)', 'y5401': 'Room Y5-401',
    'y5302_back': 'Room Y5-302 (back door)', 'lift_stairs': 'Lift and stairs (5F)',
    'disabled_toilet_4F': 'Disabled toilet (4F)', 'exit_5_4F': 'Exit 5 (4F)', 'lt2a': 'LT2a', 'lt2b': 'LT2b',
    'escalator_down_4F': 'Down escalator (4F)', 'y4502': 'Room Y4-502', 'escalator_up_4F': 'Up escalator (4F)',
    'lt1b': 'LT1b', 'lt1a': 'LT1a', 'exit_10_4F': 'Exit 10 (4F)', 'entrance_exit': 'Entrance gate (4F)',
    'lift_stairs_4F': 'Lift and stairs (4F)',
}
MAP_NAME = {'Exit 5 (emergency exit)': 'exit_5', 'Exit by bathroom (emergency)': 'exit_10',
            'Canteen (entrance)': 'canteen', 'Male toilet': 'male_toilet', 'Female toilet': 'female_toilet',
            'Y5-202': 'y5202', 'Y5-302': 'y5302', 'Study Room 8 (Y5-511)': 'sr8', 'Study Room 9 (Y5-512)': 'sr9',
            'Study Room 10 (Y5-513)': 'sr10', 'Study Room 11 (Y5-514)': 'sr11'}


def rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    stride = json.loads((P2 / 'new/tracking/out/pdr_summary.json').read_text())['23Nov']['floor5_map_edges']['median_m_per_step']
    nodes_in = [r for r in rows(P2 / 'new/graph-v2/nodes.csv') if r['virtual'] == '0']
    edges_in = rows(P2 / 'new/graph-v2/edges.csv')
    walks = {r['walk_id']: r for r in rows(P2 / 'new/tracking/out/pdr_walks_23nov.csv')}

    # measured legs from the floor-5 map, keyed by unordered pair of old ids (sr8..sr11 still separate here)
    meas = {}
    for r in rows(P2 / 'map/edges_floor5.csv'):
        meas[frozenset((MAP_NAME[r['from']], MAP_NAME[r['to']]))] = float(r['distance_m'])
    # graph-v2 merged sr8..sr11 into sr9: the measured walk y5302 -> sr11 -> sr10 -> sr9 and sr9 -> sr8 -> y5202
    chain_a = ['y5302', 'sr11', 'sr10', 'sr9']
    chain_b = ['sr9', 'sr8', 'y5202']
    m_y5302_sr9 = sum(meas[frozenset(p)] for p in zip(chain_a, chain_a[1:]))
    m_sr9_y5202 = sum(meas[frozenset(p)] for p in zip(chain_b, chain_b[1:]))
    measured = {frozenset(k): v for k, v in meas.items() if not (set(k) & {'sr8', 'sr10', 'sr11'})}
    measured[frozenset(('y5302', 'sr9'))] = round(m_y5302_sr9, 1)
    measured[frozenset(('sr9', 'y5202'))] = round(m_sr9_y5202, 1)
    chain_note = {frozenset(('y5302', 'sr9')): 'sum of measured legs y5302-sr11, sr11-sr10, sr10-sr9 (%s)' % ' + '.join(str(meas[frozenset(p)]) for p in zip(chain_a, chain_a[1:])),
                  frozenset(('sr9', 'y5202')): 'sum of measured legs sr9-sr8, sr8-y5202 (%s)' % ' + '.join(str(meas[frozenset(p)]) for p in zip(chain_b, chain_b[1:]))}

    nodes = {}
    for r in nodes_in:
        nodes[r['node_id']] = {'id': r['node_id'], 'name': NAMES[r['node_id']], 'floor': int(r['floor']),
                               'x': float(r['x']), 'y': float(r['y']), 'kind': r['kind'], 'xy_source': r['xy_source']}
    assert set(NAMES) == set(nodes), set(NAMES) ^ set(nodes)

    edges = []
    for r in edges_in:
        a, b = r['from'], r['to']
        key = frozenset((a, b))
        steps = float(r['median_steps']) if r['median_steps'] else None
        e = {'from': a, 'to': b, 'floor_change': int(r['floor_change']), 'one_way': False, 'steps': steps,
             'walk': r['walks_23nov'] or None}
        if e['floor_change']:
            if a == 'lift_stairs':                        # lift/stairs: stairs walk ACC23 (5F -> 4F), timed
                w = walks[r['walks_23nov']]
                e.update(metres=round(steps * stride, 1), seconds=float(w['duration_s']), length_source='steps',
                         length_status='steps', seconds_source='timed walk %s (5F -> 4F); same time assumed for 4F -> 5F (guess)' % r['walks_23nov'],
                         seconds_status='measured_one_way', mode='lift_stairs',
                         note='metres = steps x stride along the stairs; the lift is not timed')
            else:                                          # escalator, one way only
                e.update(metres=0.0, seconds=ESCALATOR_RIDE_S, length_source='guess', length_status='guess',
                         seconds_source='GUESS: %.0f s ride (no escalator ride was timed)' % ESCALATOR_RIDE_S,
                         seconds_status='guess', mode='escalator', one_way=True,
                         note='one way only (%s); 17-Nov pressure jump, no walk file' % r['note'])
        else:
            if key in measured:
                m = measured[key]
                e.update(metres=m, length_source='phase2/map/edges_floor5.csv' + (' (' + chain_note[key] + ')' if key in chain_note else ''), length_status='measured')
            elif steps is not None:
                e.update(metres=round(steps * stride, 1), length_source='%g steps (23-Nov walk %s) x %.2f m' % (steps, r['walks_23nov'], stride), length_status='steps')
            else:
                a_, b_ = nodes[a], nodes[b]
                d = ((a_['x'] - b_['x']) ** 2 + (a_['y'] - b_['y']) ** 2) ** 0.5
                e.update(metres=round(d, 1), length_source='GUESS: straight line between the schematic positions of the two nodes (no map distance, walk %s has no usable step count)' % r['walks_23nov'], length_status='guess')
            e['seconds'] = round(e['metres'] / SPEED_MPS, 2)
            e['seconds_source'] = 'metres / %.1f m/s' % SPEED_MPS
            e['seconds_status'] = e['length_status']
            e['mode'] = 'walk'
            # cross-check of steps against map metres where both exist (not used for the length)
            if key in measured and steps and key not in chain_note:
                e['m_per_step_check'] = round(measured[key] / steps, 2)
        edges.append(e)

    out = {
        'about': 'WalkSense routing graph, built by build_graph.py from graph-v2 + measured/step-count lengths. Internal team data.',
        'speed_mps': SPEED_MPS, 'stride_m': stride, 'escalator_ride_s': ESCALATOR_RIDE_S,
        'floors': [4, 5],
        'cost': 'seconds (same floor: metres / speed; escalator and stairs have their own times)',
        'nodes': list(nodes.values()), 'edges': edges,
    }
    (HERE / 'graph.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    n = {}
    for e in edges:
        n[e['length_status']] = n.get(e['length_status'], 0) + 1
    print('nodes', len(nodes), 'edges', len(edges), 'by length status', n)


if __name__ == '__main__':
    main()
