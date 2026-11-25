"""Walking dot: dead reckoning along the recorded corridors from the last named stop.

The corridors are the recorded walks (from_node -> to_node, both directions). From training walks each
corridor gets a compass heading (tilt-compensated, so the local magnetic distortion of that corridor is
baked in) and a step count. While walking, the dot takes the corridor out of the current node whose
heading is closest to the last 2 s, and moves along it by steps walked / corridor steps.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import walksense as ws
from pdr import count_steps

HERE = Path(__file__).resolve().parent
PLACES = json.loads((HERE / 'map' / 'places.json').read_text(encoding='utf-8'))
HEAD_S = 2.0          # seconds of walking used for the current heading
REPICK_FRAC = 0.3     # the corridor can still be swapped during its first 30 % (turning out of a door)


def heading(acc, mag, bin_s=0.5):
    """Circular-mean compass heading (deg) of the phone's top edge over the samples given."""
    if len(acc) < 10 or len(mag) < 5:
        return None
    t0, t1 = max(acc[0, 0], mag[0, 0]), min(acc[-1, 0], mag[-1, 0])
    vecs = []
    for b in np.arange(t0, t1, bin_s):
        a = acc[(acc[:, 0] >= b) & (acc[:, 0] < b + bin_s), 1:4]
        m = mag[(mag[:, 0] >= b) & (mag[:, 0] < b + bin_s), 1:4]
        if len(a) < 3 or len(m) < 2:
            continue
        down = -a.mean(0)                       # averaged acc = gravity (points up), so down is minus
        east = np.cross(down, m.mean(0))
        north = np.cross(east, down)
        h = np.arctan2(east[1] / np.linalg.norm(east), north[1] / np.linalg.norm(north))
        vecs.append((np.cos(h), np.sin(h)))
    if not vecs:
        return None
    c, s = np.mean(vecs, 0)
    return float(np.degrees(np.arctan2(s, c)) % 360)


def diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def _middle(rec, lo=0.2, hi=0.8):
    t = rec['acc'][:, 0]; t0, t1 = t[0] + lo * (t[-1] - t[0]), t[0] + hi * (t[-1] - t[0])
    return {k: rec[k][(rec[k][:, 0] >= t0) & (rec[k][:, 0] <= t1)] for k in ('acc', 'mag')}


def walks(sessions=ws.SESSIONS):
    for s in sessions:
        for r in ws.manifest(s):
            if r['phone'] == 'iphone' and r['type'] == 'walk':
                yield r, ws.read_folder(ws.DATA / s / 'clean' / r['folder'] / 'iphone', r['device'])


def build(sessions=ws.SESSIONS):
    """{floor: {node: [(to_node, heading_deg, steps)]}} from the training walks, both directions."""
    acc = {}
    for r, rec in walks(sessions):
        h = heading(**_middle(rec))
        steps = count_steps(rec['acc'][:, 0], np.linalg.norm(rec['acc'][:, 1:4], axis=1))[0]
        if h is None or steps < 3:
            continue
        f = int(r['floor'])
        for a, b, hh in ((r['from_node'], r['to_node'], h), (r['to_node'], r['from_node'], (h + 180) % 360)):
            acc.setdefault((f, a, b), []).append((hh, steps))
    graph = {}
    for (f, a, b), v in acc.items():
        hs = np.radians([x[0] for x in v])
        h = float(np.degrees(np.arctan2(np.sin(hs).mean(), np.cos(hs).mean())) % 360)
        graph.setdefault(f, {}).setdefault(a, []).append((b, h, float(np.mean([x[1] for x in v]))))
    return graph


class Dot:
    """Position along the corridors since the walk started at `node`."""

    def __init__(self, graph, floor, node):
        self.graph, self.floor, self.node = graph.get(floor, {}), floor, node
        self.edge, self.edge_steps0 = None, 0

    def _pick(self, node, h, exclude=None):
        out = [e for e in self.graph.get(node, []) if e[0] != exclude] or self.graph.get(node, [])
        return min(out, key=lambda e: diff(e[1], h)) if out and h is not None else None

    def update(self, steps, h):
        """steps since the walk began, h = heading of the last few seconds. -> (from, to, fraction) or None."""
        if self.edge is None or (steps - self.edge_steps0 < REPICK_FRAC * self.edge[2]):
            e = self._pick(self.node, h)
            if e is not None:
                self.edge = e
        if self.edge is None:
            return None
        while steps - self.edge_steps0 >= self.edge[2]:     # walked past the end: next corridor
            nxt = self._pick(self.edge[0], h, exclude=self.node)
            if nxt is None:
                break
            self.edge_steps0 += self.edge[2]; self.node, self.edge = self.edge[0], nxt
        return self.node, self.edge[0], min(1.0, (steps - self.edge_steps0) / self.edge[2])

    def xy(self, pos):
        pl = PLACES[str(self.floor)]['places']
        a, b, f = pos
        if a not in pl or b not in pl:
            return None
        return (pl[a]['x'] + f * (pl[b]['x'] - pl[a]['x']), pl[a]['y'] + f * (pl[b]['y'] - pl[a]['y']))


def m_per_px(graph):
    """Map scale from the corridors: walked metres (steps x stride) / drawn pixels, median."""
    r = []
    for f, nodes in graph.items():
        pl = PLACES[str(f)]['places']
        for a, es in nodes.items():
            for b, _, steps in es:
                if a in pl and b in pl:
                    px = np.hypot(pl[a]['x'] - pl[b]['x'], pl[a]['y'] - pl[b]['y'])
                    r.append(steps * ws.STRIDE_M / px)
    return float(np.median(r))


def evaluate(train, test):
    """Replay each held-out walk from its known start node in 0.5 s steps."""
    graph = build((train,))
    scale = m_per_px(graph)
    first_ok = end_ok = n = 0
    errs = []
    for r, rec in walks((test,)):
        f, a, b = int(r['floor']), r['from_node'], r['to_node']
        if a not in graph.get(f, {}):
            continue
        n += 1
        dot, pos, first = Dot(graph, f, a), None, None
        acc, mag = rec['acc'], rec['mag']
        t0 = acc[0, 0]
        for t in np.arange(t0 + HEAD_S, acc[-1, 0] + 0.01, 0.5):
            w = acc[acc[:, 0] <= t]
            steps = count_steps(w[:, 0], np.linalg.norm(w[:, 1:4], axis=1))[0] if len(w) > 200 else 0
            h = heading(acc[(acc[:, 0] > t - HEAD_S) & (acc[:, 0] <= t)], mag[(mag[:, 0] > t - HEAD_S) & (mag[:, 0] <= t)])
            pos = dot.update(steps, h) or pos
            if first is None and pos and steps >= 3:
                first = pos[1]
        first_ok += first == b
        if pos:
            xy, pl = dot.xy(pos), PLACES[str(f)]['places']
            if xy and b in pl:
                e = np.hypot(xy[0] - pl[b]['x'], xy[1] - pl[b]['y']) * scale
                errs.append(e); end_ok += e <= 3.0
    return {'walks': n, 'first_corridor_right': int(first_ok), 'end_within_3m': int(end_ok),
            'end_error_m_median': round(float(np.median(errs)), 1) if errs else None,
            'end_error_m_p90': round(float(np.percentile(errs, 90)), 1) if errs else None,
            'm_per_px': round(scale, 4)}


if __name__ == '__main__':
    for tr, te in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
        print(tr, '->', te, evaluate(tr, te))
