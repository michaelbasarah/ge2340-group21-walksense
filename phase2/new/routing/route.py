"""Routing on graph.json: A*, Dijkstra, turn-by-turn instructions and the `route()` entry point.

    from route import route
    path, metres, seconds, instructions = route('canteen', 'lt1a')

`route()` takes graph ids (see graph.json). Only the standard library is used. (Wiring this into the app is
out of scope for now.)

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
TURN_MIN_DEG = 40.0


class Graph:
    def __init__(self, data=None):
        data = data or json.loads((HERE / 'graph.json').read_text(encoding='utf-8'))
        self.data = data
        self.speed = data['speed_mps']
        self.nodes = {n['id']: n for n in data['nodes']}
        self.adj = {n: [] for n in self.nodes}          # node -> [(neighbour, seconds, metres, edge)]
        self.edge = {}                                    # (a, b) -> directed edge info
        for e in data['edges']:
            pairs = [(e['from'], e['to'])] + ([] if e.get('one_way') else [(e['to'], e['from'])])
            for a, b in pairs:
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
        return min(self._line(n, a) + s + self._line(b, goal) for a, b, s in self.transfers
                   if self.nodes[a]['floor'] == self.nodes[n]['floor'] and self.nodes[b]['floor'] == self.nodes[goal]['floor'])

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
                out.append('Take the escalator %s to floor %d (about %.0f s).' % (way, nb['floor'], e['seconds']))
                continue
            if e['mode'] == 'lift_stairs':
                way = 'down' if nb['floor'] < na['floor'] else 'up'
                out.append('Take the stairs (or the lift) %s to floor %d (about %.0f s).' % (way, nb['floor'], e['seconds']))
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


_G = None


def graph():
    global _G
    if _G is None:
        _G = Graph()
    return _G


def route(start_id, goal_id, turns=True):
    """-> Route(path, metres, seconds, instructions): fastest path by A*, walked metres (escalator rides count 0),
    total seconds, and a list of instruction strings. Raises KeyError for an unknown id."""
    g = graph()
    path, sec, _ = g.search(start_id, goal_id)
    cost = g.path_cost(path)
    return Route(path, round(cost[1], 1), round(sec, 1), g.instructions(path, turns))


if __name__ == '__main__':
    import sys
    r = route(sys.argv[1], sys.argv[2])
    print(' -> '.join(r.path), '| %.1f m, %.1f s' % (r.metres, r.seconds))
    print('\n'.join(r.instructions))
