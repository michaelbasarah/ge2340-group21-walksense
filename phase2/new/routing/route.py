"""Routing on graph.json: A*, Dijkstra, turn-by-turn instructions and the `route()` entry point.

    from route import route, plan, nearest_toilet
    path, metres, seconds, instructions = route('canteen', 'lt1a')      # graph.json as it is (research checks)
    p = plan('canteen', 'lt1a', mode='accessible')                       # route planner: lifts only
    t = nearest_toilet('lt1a', mode='standard', gender='female')         # nearest toilet for a filter

`route()` / `plan()` take graph ids (see graph.json). Only the standard library is used. The upload app
(phase2/new/upload/search.py) uses plan() and nearest_toilet().

Cost = seconds. Same-floor edges: metres / speed; escalator and stairs rides have their own times (graph.json).
Escalators are one way (5F down escalator -> 4F down escalator, 4F up escalator -> 5F up escalator).
Heuristic: straight-line distance on the same floor (coordinates shrunk per floor so that no edge is shorter
than the straight line, see `_scales`) divided by the speed; across floors the cheapest transfer edge is added
(distance to its start + its ride time + distance from its end to the goal). Never over-estimates.
"""
from __future__ import annotations

import heapq
import json
import math
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
Route = namedtuple('Route', 'path metres seconds instructions')
Plan = namedtuple('Plan', 'path legs metres seconds instructions connectors mode')
TURN_MIN_DEG = 40.0

# --- route planner (modes, connectors, toilets); see README "Route planner" -------------------------------------
# Connector costs, in seconds (the search cost; walking edges are metres / speed, so on one floor the fastest
# route is also the shortest). graph.json has one `lift_stairs` edge per lift core; it is split here into a
# stairs edge and a lift edge between the same two landings, so a mode can leave one out.
LIFT_WAIT_S = 30.0       # GUESS: average wait for the lift car (nobody has timed the AC1 lift)
LIFT_RIDE_S = 12.0       # GUESS: one floor, doors closing + ride + doors opening (not timed)
# stairs: graph.json's 30.0 s (timed once 5F -> 4F, walk ACC23; 4F -> 5F assumed the same) and its 28.6 m
# escalators: graph.json's 20 s ride (GUESS, no ride was timed), one way only
PROFILES = {
    'standard': frozenset({'walk', 'stairs', 'lift', 'escalator'}),
    'accessible': frozenset({'walk', 'lift'}),        # step-free: no stairs, no escalators
}
GENDERS = ('any', 'male', 'female')
# toilets in graph.json (kind = toilet). gender = who may use it; accessible = disabled toilet. Display names from
# phase2/new/day3/config.json place_display (user, 26 Nov): 5F disabled toilet = MALE, 4F one = MIXED (unisex).
TOILETS = {
    'male_toilet': {'gender': 'male', 'accessible': False},
    'female_toilet': {'gender': 'female', 'accessible': False},
    'disabled_toilet': {'gender': 'male', 'accessible': True},
    'disabled_toilet_4F': {'gender': 'mixed', 'accessible': True},
}


def connector_edges(data):
    """graph.json edges with an explicit `kind` (walk / stairs / lift / escalator); every `lift_stairs` edge becomes
    a stairs edge (graph.json's time and metres) plus a lift edge (LIFT_WAIT_S + LIFT_RIDE_S per floor, 0 m walked)."""
    out = []
    for e in data['edges']:
        if e['mode'] == 'lift_stairs':
            out.append(dict(e, kind='stairs', mode='stairs'))
            floors = abs(e.get('floor_change') or 1)
            out.append(dict(e, kind='lift', mode='lift', metres=0.0, steps=None, wait_s=LIFT_WAIT_S, ride_s=LIFT_RIDE_S * floors,
                            seconds=LIFT_WAIT_S + LIFT_RIDE_S * floors, length_source='lift ride (no walking)',
                            length_status='guess', seconds_status='guess',
                            seconds_source='GUESS: %.0f s wait + %.0f s ride per floor (lift not timed)' % (LIFT_WAIT_S, LIFT_RIDE_S),
                            note='same landing nodes as the stairs; the lift and the stairs are side by side'))
        else:
            out.append(dict(e, kind=e['mode']))
    return out


class Graph:
    def __init__(self, data=None, profile=None):
        """profile=None: graph.json as it is (one `lift_stairs` edge; what check_astar.py / evaluate.py / llm_baseline.py
        were run on). profile='standard' / 'accessible': connectors split into lift, stairs and escalator edges
        (`connector_edges`) and only the kinds in PROFILES[profile] are kept. Between two nodes only the cheapest
        allowed edge is kept (Dijkstra on a multigraph = Dijkstra on its cheapest parallel edges); all of them stay in
        `self.parallel` so the instructions can name the other connector."""
        data = data or json.loads((HERE / 'graph.json').read_text(encoding='utf-8'))
        self.data = data
        self.profile = profile
        self.speed = data['speed_mps']
        self.nodes = {n['id']: n for n in data['nodes']}
        self.adj = {n: [] for n in self.nodes}          # node -> [(neighbour, seconds, metres, edge)]
        self.edge = {}                                    # (a, b) -> directed edge info
        self.parallel = {}                                # (a, b) -> every directed edge of this pair (any kind)
        if profile is None:
            edges, allowed = data['edges'], None
        else:
            if profile not in PROFILES:
                raise KeyError('unknown mode %r (use one of %s)' % (profile, ', '.join(PROFILES)))
            edges, allowed = connector_edges(data), PROFILES[profile]
        for e in edges:
            pairs = [(e['from'], e['to'])] + ([] if e.get('one_way') else [(e['to'], e['from'])])
            for a, b in pairs:
                self.parallel.setdefault((a, b), []).append(e)
                if allowed is not None and e['kind'] not in allowed:
                    continue
                old = self.edge.get((a, b))
                if old is not None:
                    if old['seconds'] <= e['seconds']:
                        continue
                    self.adj[a] = [t for t in self.adj[a] if t[0] != b]
                self.adj[a].append((b, e['seconds'], e['metres'], e))
                self.edge[(a, b)] = e
        self.scale = self._scales()
        self.transfers = [(a, b, e['seconds']) for (a, b), e in self.edge.items()
                          if self.nodes[a]['floor'] != self.nodes[b]['floor']]

    def _scales(self):
        """Per floor: factor <= 1 applied to straight-line distances so they never exceed an edge length."""
        s = {}
        for (a, b), e in self.edge.items():
            na, nb = self.nodes[a], self.nodes[b]
            if na['floor'] != nb['floor']:
                continue
            d = math.hypot(na['x'] - nb['x'], na['y'] - nb['y'])
            if d > 0:
                s[na['floor']] = min(s.get(na['floor'], 1.0), e['seconds'] * self.speed / d)   # seconds, so rounding cannot break it
        return s

    def _line(self, a, b):
        na, nb = self.nodes[a], self.nodes[b]
        return self.scale.get(na['floor'], 1.0) * math.hypot(na['x'] - nb['x'], na['y'] - nb['y']) / self.speed

    def h(self, n, goal):
        if self.nodes[n]['floor'] == self.nodes[goal]['floor']:
            return self._line(n, goal)
        # cheapest way to change floor from n's floor toward the goal's floor (at least one transfer is needed)
        return min((self._line(n, a) + s + self._line(b, goal) for a, b, s in self.transfers
                    if self.nodes[a]['floor'] == self.nodes[n]['floor'] and self.nodes[b]['floor'] == self.nodes[goal]['floor']),
                   default=0.0)                       # no allowed transfer: the search finds no route anyway

    def search(self, start, goal, heuristic=True):
        """A* (heuristic=True) or Dijkstra (False). Returns (path, seconds, expansions)."""
        if start not in self.nodes or goal not in self.nodes:
            raise KeyError('unknown place: %r -> %r' % (start, goal))
        best = {start: 0.0}
        prev = {}
        heap = [(self.h(start, goal) if heuristic else 0.0, start)]
        done = set()
        expanded = 0
        while heap:
            _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            expanded += 1
            if u == goal:
                break
            for v, sec, _, _ in self.adj[u]:
                nd = best[u] + sec
                if nd < best.get(v, math.inf) - 1e-12:
                    best[v] = nd
                    prev[v] = u
                    done.discard(v)                       # re-open (safe even if the heuristic were inconsistent)
                    heapq.heappush(heap, (nd + (self.h(v, goal) if heuristic else 0.0), v))
        if goal not in best:
            raise ValueError('no route %s -> %s' % (start, goal))
        path = [goal]
        while path[-1] != start:
            path.append(prev[path[-1]])
        return path[::-1], best[goal], expanded

    def path_cost(self, path):
        """(seconds, metres) of a path, or None if some hop is not a directed edge."""
        sec = met = 0.0
        for a, b in zip(path, path[1:]):
            e = self.edge.get((a, b))
            if e is None:
                return None
            sec += e['seconds']
            met += e['metres']
        return sec, met

    def instructions(self, path, turns=True):
        nodes = self.nodes
        out = ['Start at %s (floor %d).' % (nodes[path[0]]['name'], nodes[path[0]]['floor'])]
        if len(path) == 1:
            return out + ['You are already there.']
        for i in range(1, len(path)):
            a, b = path[i - 1], path[i]
            e = self.edge[(a, b)]
            na, nb = nodes[a], nodes[b]
            if e['mode'] == 'escalator':
                way = 'down' if nb['floor'] < na['floor'] else 'up'
                out.append(('Take the escalator %s to floor %d (about %.0f s).' if self.profile is None else
                            'Take the %s escalator to %dF (about %.0f s).') % (way, nb['floor'], e['seconds']))
                continue
            if e['mode'] == 'lift_stairs':
                way = 'down' if nb['floor'] < na['floor'] else 'up'
                out.append('Take the stairs (or the lift) %s to floor %d (about %.0f s).' % (way, nb['floor'], e['seconds']))
                continue
            if e['mode'] == 'stairs':
                way = 'down' if nb['floor'] < na['floor'] else 'up'
                lift = [x for x in self.parallel.get((a, b), []) if x['kind'] == 'lift']
                out.append('Take the stairs %s to %dF (about %.0f s)%s.' % (way, nb['floor'], e['seconds'],
                                                                         '; the lift is next to them' if lift else ''))
                continue
            if e['mode'] == 'lift':
                way = 'down' if nb['floor'] < na['floor'] else 'up'
                out.append('Take the lift %s to %dF (about %.0f s: %.0f s waiting + %.0f s ride, both guesses).'
                           % (way, nb['floor'], e['seconds'], e['wait_s'], e['ride_s']))
                continue
            lead = ''
            if turns and i >= 2 and nodes[path[i - 2]]['floor'] == na['floor'] and self.edge[(path[i - 2], a)]['mode'] == 'walk':
                t = _turn(nodes[path[i - 2]], na, nb)
                if t:
                    lead = '%s at %s, then ' % (t[0].upper() + t[1:], na['name'])
            walk = 'walk to %s (about %.0f m, %.0f s).' % (nb['name'], e['metres'], e['seconds'])
            out.append(lead + walk if lead else walk[0].upper() + walk[1:])
        out.append('You have arrived at %s.' % nodes[path[-1]]['name'])
        return out


def _turn(p, a, b):
    """'turn left' / 'turn right' / 'turn around' / '' from three node positions (x east, y north on the map)."""
    v1 = (a['x'] - p['x'], a['y'] - p['y'])
    v2 = (b['x'] - a['x'], b['y'] - a['y'])
    if not (math.hypot(*v1) and math.hypot(*v2)):
        return ''
    ang = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))   # + = anticlockwise = left
    if abs(ang) >= 150:
        return 'turn around'
    if abs(ang) < TURN_MIN_DEG:
        return ''
    return 'turn left' if ang > 0 else 'turn right'


_G = {}


def graph(profile=None):
    """Cached Graph. profile=None = graph.json as it is (the research checks); 'standard' / 'accessible' = planner."""
    if profile not in _G:
        _G[profile] = Graph(profile=profile)
    return _G[profile]


def route(start_id, goal_id, turns=True):
    """-> Route(path, metres, seconds, instructions): fastest path by A*, walked metres (escalator rides count 0),
    total seconds, and a list of instruction strings. Raises KeyError for an unknown id. Uses graph.json as it is
    (one lift_stairs edge); the app uses plan() instead."""
    g = graph()
    path, sec, _ = g.search(start_id, goal_id)
    cost = g.path_cost(path)
    return Route(path, round(cost[1], 1), round(sec, 1), g.instructions(path, turns))


def plan(start_id, goal_id, mode='standard', turns=True):
    """Route planner: -> Plan(path, legs, metres, seconds, instructions, connectors, mode).
    legs = the directed edge used for each hop (kind walk / stairs / lift / escalator, metres, seconds);
    connectors = the floor changes on the way [{kind, from, to, from_floor, to_floor, seconds}].
    mode 'standard' = every connector, 'accessible' = lifts only. KeyError: unknown id or mode; ValueError: no route."""
    g = graph(mode)
    path, sec, _ = g.search(start_id, goal_id)
    legs = [g.edge[(a, b)] for a, b in zip(path, path[1:])]
    conn = [{'kind': e['kind'], 'from': a, 'to': b, 'from_floor': g.nodes[a]['floor'], 'to_floor': g.nodes[b]['floor'],
             'seconds': e['seconds']} for (a, b), e in zip(zip(path, path[1:]), legs) if e['kind'] != 'walk']
    return Plan(path, legs, round(sum(e['metres'] for e in legs), 1), round(sec, 1), g.instructions(path, turns), conn, mode)


def toilet_allowed(toilet_id, mode='standard', gender='any', toilets=TOILETS):
    """'' if this toilet suits the mode and gender filter, else the reason it does not."""
    t = toilets[toilet_id]
    if mode == 'accessible' and not t['accessible']:
        return 'not a disabled toilet'
    if gender in ('male', 'female') and t['gender'] not in (gender, 'mixed'):
        return '%s only' % t['gender']
    return ''


def nearest_toilet(start_id, mode='standard', gender='any', floor=None, accessible_only=False, toilets=TOILETS):
    """Nearest suitable toilet by route cost (seconds; on one floor that is also the shortest walk).
    gender: any / male / female (male -> male toilets + mixed; female -> female toilets + mixed).
    mode 'accessible' (or accessible_only) -> disabled toilets only. floor: only toilets on that floor.
    -> {'choice': Plan or None, 'toilet': id or None, 'options': [...], 'excluded': [...], 'message': str}"""
    if mode not in PROFILES:
        raise KeyError('unknown mode %r' % mode)
    if gender not in GENDERS:
        raise KeyError('unknown gender %r (use any, male or female)' % gender)
    g = graph(mode)
    options, excluded = [], []
    for tid in toilets:
        why = toilet_allowed(tid, 'accessible' if accessible_only else mode, gender, toilets)
        if not why and floor is not None and g.nodes[tid]['floor'] != floor:
            why = 'not on %dF' % floor
        if not why:
            try:
                p = plan(start_id, tid, mode)
            except ValueError:
                why = 'no %s route' % ('step-free' if mode == 'accessible' else '')
        if why:
            excluded.append({'id': tid, 'name': g.nodes[tid]['name'], 'floor': g.nodes[tid]['floor'], 'reason': why.replace('  ', ' ')})
        else:
            options.append({'id': tid, 'name': g.nodes[tid]['name'], 'floor': g.nodes[tid]['floor'], 'metres': p.metres,
                            'seconds': p.seconds, 'plan': p})
    options.sort(key=lambda o: (o['seconds'], o['metres'], o['id']))
    want = ' '.join(w for w in (('disabled' if mode == 'accessible' or accessible_only else ''),
                                (gender if gender != 'any' else ''), 'toilet') if w)
    if not options:
        msg = 'No %s%s in the area WalkSense covers (AC1 5F and 4F). Toilets we know: %s.' % (
            want, (' on %dF' % floor) if floor is not None else '',
            '; '.join('%s (%s)' % (x['name'], x['reason']) for x in excluded))
        return {'choice': None, 'toilet': None, 'options': [], 'excluded': excluded, 'message': msg}
    best = options[0]
    msg = 'Nearest %s: %s, about %.0f m walking, %.0f s.' % (want, best['name'], best['metres'], best['seconds'])
    return {'choice': best['plan'], 'toilet': best['id'], 'options': options, 'excluded': excluded, 'message': msg}


SAMPLE_ROUTES = [('y5302', 'female_toilet'), ('canteen', 'lt1a'), ('y5302', 'lt2b'), ('lt1a', 'canteen'),
                 ('lift_stairs', 'lift_stairs_4F'), ('lift_stairs_4F', 'lift_stairs'), ('escalator_up', 'escalator_down_4F')]
SAMPLE_STARTS = ['canteen', 'y5202', 'y5401', 'exit_10', 'lt1a', 'y4502', 'lt2b', 'entrance_exit']


def samples(path=HERE / 'out' / 'planner_samples.json'):
    """python route.py samples -> out/planner_samples.json: example routes in both modes, the connector costs and the
    nearest toilet for every mode x gender from 8 starts (4 per floor). The README and PROCESS-LOG quote this file."""
    def brief(p):
        return {'path': p.path, 'metres': p.metres, 'seconds': p.seconds,
                'legs': [{'from': a, 'to': b, 'kind': e['kind'], 'metres': e['metres'], 'seconds': e['seconds'], 'length_status': e['length_status']}
                         for a, b, e in zip(p.path, p.path[1:], p.legs)],
                'connectors': [c['kind'] for c in p.connectors], 'instructions': p.instructions}
    out = {'about': 'route planner samples (routing/route.py plan / nearest_toilet), written by `python route.py samples`',
           'speed_mps': graph().speed,
           'connector_costs_s': {'lift_wait_guess': LIFT_WAIT_S, 'lift_ride_per_floor_guess': LIFT_RIDE_S,
                                 'lift_total_one_floor': LIFT_WAIT_S + LIFT_RIDE_S,
                                 'stairs_graph_json': graph().edge[('lift_stairs', 'lift_stairs_4F')]['seconds'],
                                 'escalator_graph_json': graph().edge[('escalator_down', 'escalator_down_4F')]['seconds']},
           'routes': [], 'toilets': [], 'toilet_table': {k: dict(v, name=graph().nodes[k]['name'], floor=graph().nodes[k]['floor'])
                                                         for k, v in TOILETS.items()}}
    for a, b in SAMPLE_ROUTES:
        out['routes'].append({'from': a, 'to': b, **{m: brief(plan(a, b, m)) for m in PROFILES}})
    for st in SAMPLE_STARTS:
        for m in PROFILES:
            for gd in GENDERS:
                t = nearest_toilet(st, m, gd)
                out['toilets'].append({'from': st, 'from_floor': graph().nodes[st]['floor'], 'mode': m, 'gender': gd, 'toilet': t['toilet'],
                                       'metres': t['choice'].metres if t['choice'] else None, 'seconds': t['choice'].seconds if t['choice'] else None,
                                       'connectors': [c['kind'] for c in t['choice'].connectors] if t['choice'] else [],
                                       'options': [{'id': o['id'], 'metres': o['metres'], 'seconds': o['seconds']} for o in t['options']], 'message': t['message']})
    use = {}
    for m in PROFILES:                                   # which connector the cross-floor pairs use, per mode
        g = graph(m)
        cnt = {}
        for a in g.nodes:
            for b in g.nodes:
                if g.nodes[a]['floor'] != g.nodes[b]['floor']:
                    k = '+'.join(c['kind'] for c in plan(a, b, m).connectors)
                    cnt[k] = cnt.get(k, 0) + 1
        use[m] = cnt
    out['cross_floor_pairs_by_connector'] = use
    t = nearest_toilet('canteen', 'accessible', 'female', floor=5)
    out['no_option_example'] = {'from': 'canteen', 'mode': 'accessible', 'gender': 'female', 'floor': 5, 'message': t['message']}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    return out


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['samples']:
        samples()
        print('wrote', HERE / 'out' / 'planner_samples.json')
        sys.exit()
    if len(sys.argv) > 3:
        r = plan(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        r = route(sys.argv[1], sys.argv[2])
    print(' -> '.join(r.path), '| %.1f m, %.1f s' % (r.metres, r.seconds))
    print('\n'.join(r.instructions))
