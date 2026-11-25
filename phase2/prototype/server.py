#!/usr/bin/env python3
"""WalkSense simple prototype — local web app (text search + positioning replay).

Run:  python server.py     then open http://127.0.0.1:5173

Two features:
  1. "Where do you want to go?" — type a request; see the KEYWORD and EMBEDDING
     methods each pick a place (objective #9).
  2. "Replay a walk" — replays the real 17-Nov walk: the magnetic model's guessed
     checkpoint + barometer floor + step count, as a moving dot.

This is a SANITY PROTOTYPE to validate the pipeline before the real UI. Dot positions
are schematic (route order + floor), not metric map coordinates. The single-session
replay accuracy is optimistic, not a graded result.
"""
import json
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsClassifier
from model2vec import StaticModel

ROOT = Path(__file__).resolve().parent
DATA = ROOT / '..' / 'clean-data' / '2026-11-17'
REQ = ROOT / '..' / 'request-matching'
sys.path.insert(0, str(REQ))
import match as M  # noqa: E402  (reuse keyword + token matchers and destinations)

# ---------------- text matching ----------------
DESTS = M.load()[0]
BYID = {d['place_id']: d for d in DESTS}
DOCS, IDF = M.build_idf(DESTS)
print('loading embedding model (first run downloads ~30 MB)...')
MODEL = StaticModel.from_pretrained('minishlab/potion-base-8M')
DEST_TEXT = [f"{d['name']} {d['aliases'].replace(';', ' ')} {d['tags'].replace(';', ' ')}" for d in DESTS]
DV = MODEL.encode(DEST_TEXT).astype('float32')
DV /= (np.linalg.norm(DV, axis=1, keepdims=True) + 1e-9)

def embed_match(q):
    qv = MODEL.encode([q]).astype('float32')[0]
    qv /= (np.linalg.norm(qv) + 1e-9)
    sims = DV @ qv
    i = int(np.argmax(sims))
    return DESTS[i]['place_id'], float(sims[i])

EMBED_THRESHOLD = 0.35  # below this the embedding is just guessing -> say "(not sure)"

def match_all(q):
    nm = lambda pid: BYID[pid]['name'] if pid in BYID else None
    kw = M.keyword_match(q, DESTS)
    em, score = embed_match(q)
    sure = score >= EMBED_THRESHOLD
    return {'query': q,
            'keyword': {'id': kw, 'name': nm(kw)},
            'embedding': {'id': em if sure else None, 'name': nm(em) if sure else None, 'score': round(score, 3)}}

# ---------------- positioning replay ----------------
def build_replay():
    samples = pd.read_csv(DATA / 'sensor_samples.csv')
    loc = pd.read_csv(DATA / 'locations_provisional.csv')
    edges = pd.read_csv(DATA / 'accelerometer_edges.csv')
    order = [f'BM{n:02}' for n in range(1, 27)]
    place = dict(zip(loc['stop_id'], loc['location_label']))
    feats = ['mag_mean', 'mag_std', 'mag_min', 'mag_max', 'x_mean', 'y_mean', 'z_mean']

    mag = samples[samples['sensor'] == 'magnetometer']
    rows = []
    for sid, g in mag.groupby('session_id'):
        g = g.sort_values('relative_time_s')
        for w, gw in g.groupby((g['relative_time_s'] // 2.0).astype(int)):
            if len(gw) < 40:
                continue
            m = gw['vector_magnitude'].to_numpy()
            rows.append({'stop_id': sid, 'mag_mean': m.mean(), 'mag_std': m.std(), 'mag_min': m.min(),
                         'mag_max': m.max(), 'x_mean': gw['x'].mean(), 'y_mean': gw['y'].mean(), 'z_mean': gw['z'].mean()})
    df = pd.DataFrame(rows)
    X = StandardScaler().fit_transform(df[feats].to_numpy())
    knn = KNeighborsClassifier(n_neighbors=5).fit(X, df['stop_id'].to_numpy())
    df['guess'] = knn.predict(X)
    guess = {s: g['guess'].value_counts().idxmax() for s, g in df.groupby('stop_id')}

    baro = samples[samples['sensor'] == 'barometer']
    pstop = baro.groupby('session_id')['x'].median()
    thr = (pstop.max() + pstop.min()) / 2
    floor = {s: ('upper' if pstop[s] < thr else 'lower') for s in order}

    acc = samples[samples['sensor'] == 'accelerometer']
    def steps(t, mg):
        if len(t) < 3:
            return 0
        fs = 1.0 / np.median(np.diff(t)); win = max(1, int(round(0.4 * fs)))
        dyn = mg - np.convolve(mg, np.ones(win) / win, mode='same')
        gap = int(round(0.30 * fs)); c = 0; last = -gap - 1
        for i in range(1, len(dyn) - 1):
            if dyn[i] > 0.9 and dyn[i] >= dyn[i - 1] and dyn[i] > dyn[i + 1] and (i - last) >= gap:
                c += 1; last = i
        return c
    steps_by_acc = {sid: steps(g.sort_values('relative_time_s')['relative_time_s'].to_numpy(),
                               g.sort_values('relative_time_s')['vector_magnitude'].to_numpy())
                    for sid, g in acc.groupby('session_id')}
    steps_to = {e['to_stop_id']: steps_by_acc.get(e['acc_session_id'], 0) for _, e in edges.iterrows()}

    nodes = []; cum = 0
    for i, s in enumerate(order):
        cum += steps_to.get(s, 0); gpred = guess[s]
        nodes.append({'id': s, 'n': int(s[2:]), 'place': place[s], 'floor': floor[s],
                      'guess_place': place[gpred], 'correct': bool(gpred == s),
                      'cum_steps': cum, 'x': 44 + i * 44, 'y': 90 if floor[s] == 'upper' else 190})
    return nodes

print('building positioning replay from the 17-Nov session...')
REPLAY = build_replay()

# Real checkpoint map (metres), if the coordinates have been processed.
FLOOR_PTS = []
cm = ROOT / '..' / 'map' / 'coordinates_meters.csv'
cw = ROOT / '..' / 'map' / 'coordinates.csv'
if cm.exists():
    mdf = pd.read_csv(cm)
    wide = {}
    if cw.exists():
        cwdf = pd.read_csv(cw)
        wide = dict(zip(cwdf['checkpoint'], cwdf['door_width'].astype(str) == 'wide'))
    import re as _re
    def short_and_cat(name):
        n = name.lower()
        if 'canteen' in n:
            return 'Canteen', 'food'
        if 'female toilet' in n:
            return 'Women', 'wc'
        if 'male toilet' in n:
            return 'Men', 'wc'
        if 'toilet' in n:
            return 'WC', 'wc'
        if 'exit 10' in n:
            return 'Exit 10', 'exit'
        if 'exit 5' in n:
            return 'Exit 5', 'exit'
        if 'exit' in n or 'gate' in n:
            return 'Exit', 'exit'
        if 'escalator up' in n:
            return 'Esc up', 'stairs'
        if 'escalator down' in n:
            return 'Esc down', 'stairs'
        if 'escalator' in n:
            return 'Escalator', 'stairs'
        m = _re.search(r'study room (\d+)', n)
        if m:
            return 'SR' + m.group(1), 'study'
        if n.startswith('y5') or n.startswith('y4'):
            return name.split()[0].upper(), 'study'
        return name[:9], 'room'
    for _, r in mdf.iterrows():
        s, c = short_and_cat(str(r['checkpoint']))
        FLOOR_PTS.append({'name': r['checkpoint'], 'x': float(r['x_m']), 'y': float(r['y_m']),
                          'floor': int(r['floor']), 'wide': bool(wide.get(r['checkpoint'], False)),
                          'short': s, 'cat': c})

PAGE = ((ROOT / 'index.html').read_text(encoding='utf-8')
        .replace('__REPLAY__', json.dumps(REPLAY))
        .replace('__FLOOR_PTS__', json.dumps(FLOOR_PTS)))

# ---------------- route planning (A*) ----------------
import heapq

def build_graph(pts, k=3):
    """Connect each checkpoint to its k nearest neighbours; join any separate clusters."""
    n = len(pts)
    adj = {i: {} for i in range(n)}
    if n < 2:
        return adj
    P = np.array([[p['x'], p['y']] for p in pts])
    D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
    for i in range(n):
        for j in np.argsort(D[i])[1:k + 1]:
            adj[i][int(j)] = float(D[i][j]); adj[int(j)][i] = float(D[i][j])

    def components():
        seen, comps = set(), []
        for s in range(n):
            if s in seen:
                continue
            stack, c = [s], set()
            while stack:
                u = stack.pop()
                if u in c:
                    continue
                c.add(u); seen.add(u); stack += list(adj[u])
            comps.append(c)
        return comps

    comps = components()
    while len(comps) > 1:
        best = None
        for a in range(len(comps)):
            for b in range(a + 1, len(comps)):
                for i in comps[a]:
                    for j in comps[b]:
                        if best is None or D[i][j] < best[0]:
                            best = (D[i][j], i, j)
        _, i, j = best
        adj[i][j] = float(D[i][j]); adj[j][i] = float(D[i][j])
        comps = components()
    return adj

def load_corridor_graph(pts):
    """Use the editable corridor edge list (../map/edges_floor5.csv) if present; else auto-connect."""
    ef = ROOT / '..' / 'map' / 'edges_floor5.csv'
    if not ef.exists():
        return build_graph(pts, 3)
    name2i = {p['name']: i for i, p in enumerate(pts)}
    adj = {i: {} for i in range(len(pts))}
    for _, e in pd.read_csv(ef).iterrows():
        a, b = str(e['from']), str(e['to'])
        if a in name2i and b in name2i:
            i, j = name2i[a], name2i[b]
            d = float(((pts[i]['x'] - pts[j]['x']) ** 2 + (pts[i]['y'] - pts[j]['y']) ** 2) ** 0.5)
            adj[i][j] = d; adj[j][i] = d
    return adj

ADJ = load_corridor_graph(FLOOR_PTS)
NAME2I = {p['name']: i for i, p in enumerate(FLOOR_PTS)}
EDGES = []
_seen = set()
for _i in ADJ:
    for _j in ADJ[_i]:
        _k = tuple(sorted((_i, _j)))
        if _k not in _seen:
            _seen.add(_k); EDGES.append([FLOOR_PTS[_i]['name'], FLOOR_PTS[_j]['name']])

def astar(si, gi):
    P = [(p['x'], p['y']) for p in FLOOR_PTS]
    h = lambda i: ((P[i][0] - P[gi][0]) ** 2 + (P[i][1] - P[gi][1]) ** 2) ** 0.5
    pq = [(h(si), 0.0, si, [si])]; best = {si: 0.0}
    while pq:
        _, g, u, path = heapq.heappop(pq)
        if u == gi:
            return path, g
        for v, w in ADJ[u].items():
            ng = g + w
            if v not in best or ng < best[v]:
                best[v] = ng; heapq.heappush(pq, (ng + h(v), ng, v, path + [v]))
    return None, None

def route(a, b):
    if a not in NAME2I or b not in NAME2I:
        return {'path': [], 'error': 'unknown place'}
    path, dist = astar(NAME2I[a], NAME2I[b])
    if not path:
        return {'path': [], 'error': 'no route'}
    coords = [{'name': FLOOR_PTS[i]['name'], 'x': FLOOR_PTS[i]['x'], 'y': FLOOR_PTS[i]['y']} for i in path]
    return {'path': [FLOOR_PTS[i]['name'] for i in path], 'distance_m': round(dist, 1), 'coords': coords}

# ---------------- server ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype='application/json'):
        b = body.encode('utf-8')
        self.send_response(200); self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/':
            self._send(PAGE, 'text/html; charset=utf-8')
        elif u.path == '/api/match':
            q = parse_qs(u.query).get('q', [''])[0]
            self._send(json.dumps(match_all(q)) if q.strip() else json.dumps({'query': q, 'keyword': {}, 'embedding': {}}))
        elif u.path == '/api/route':
            qs = parse_qs(u.query)
            self._send(json.dumps(route(qs.get('from', [''])[0], qs.get('to', [''])[0])))
        elif u.path == '/api/graph':
            self._send(json.dumps({'edges': EDGES}))
        elif u.path == '/floor5.jpg':
            img = ROOT / 'floor5.jpg'
            if img.exists():
                b = img.read_bytes()
                self.send_response(200); self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
            else:
                self.send_response(404); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

if __name__ == '__main__':
    port = 5173
    print(f'\nWalkSense prototype running ->  http://127.0.0.1:{port}\n(Ctrl+C to stop)')
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
