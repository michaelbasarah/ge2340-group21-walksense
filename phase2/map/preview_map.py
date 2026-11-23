#!/usr/bin/env python3
"""Static preview of the wayfinding map design (mirrors the prototype's SVG)."""
import heapq
import re
from collections import defaultdict
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent
df = pd.read_csv(ROOT / 'coordinates_meters.csv')
edges = pd.read_csv(ROOT / 'edges_floor5.csv')
CAT = {'food': '#e0a43b', 'study': '#4a63b0', 'room': '#8893a6', 'wc': '#2f9c8f', 'exit': '#3a9d6a', 'stairs': '#8e6bb0'}

def sc(name):
    n = name.lower()
    if 'canteen' in n: return 'Canteen', 'food'
    if 'male toilet' in n: return 'Men', 'wc'
    if 'female toilet' in n: return 'Women', 'wc'
    if 'toilet' in n: return 'WC', 'wc'
    if 'exit' in n or 'gate' in n: return 'Exit', 'exit'
    m = re.search(r'study room (\d+)', n)
    if m: return 'SR' + m.group(1), 'study'
    if n.startswith('y5') or n.startswith('y4'): return name.split()[0].upper(), 'study'
    return name[:9], 'room'

pos = {r['checkpoint']: (r['x_m'], r['y_m']) for _, r in df.iterrows()}
adj = defaultdict(dict)
for _, e in edges.iterrows():
    adj[e['from']][e['to']] = e['distance_m']; adj[e['to']][e['from']] = e['distance_m']

def dijkstra(a, b):
    pq = [(0, a, [a])]; seen = set()
    while pq:
        d, u, path = heapq.heappop(pq)
        if u == b: return path
        if u in seen: continue
        seen.add(u)
        for v, w in adj[u].items():
            if v not in seen: heapq.heappush(pq, (d + w, v, path + [v]))
    return []

route = dijkstra('Exit 5 (emergency exit)', 'Study Room 11 (Y5-514)')

fig, ax = plt.subplots(figsize=(7.6, 6.2))
ax.set_facecolor('#eef1f6')
for _, e in edges.iterrows():
    x = [pos[e['from']][0], pos[e['to']][0]]; y = [pos[e['from']][1], pos[e['to']][1]]
    ax.plot(x, y, color='#dbe2ea', lw=16, solid_capstyle='round', zorder=1)
    ax.plot(x, y, color='#ffffff', lw=11, solid_capstyle='round', zorder=2)
if route:
    rx = [pos[p][0] for p in route]; ry = [pos[p][1] for p in route]
    ax.plot(rx, ry, color='#e8306b', lw=4.5, solid_capstyle='round', zorder=3)
    ax.scatter([rx[0]], [ry[0]], s=120, color='#1c6dd0', zorder=5, edgecolor='white', lw=2)
    ax.scatter([rx[-1]], [ry[-1]], s=200, marker='v', color='#e8306b', zorder=5, edgecolor='white', lw=1.5)
SIZE = {'food': (4.0, 2.6), 'study': (2.8, 2.0), 'room': (2.7, 1.9), 'wc': (2.5, 1.7), 'exit': (2.2, 1.6), 'stairs': (2.8, 1.8)}
for _, r in df.iterrows():
    short, cat = sc(r['checkpoint']); x, y = r['x_m'], r['y_m']
    w, h = SIZE.get(cat, (2.6, 1.8))
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle='round,pad=0.02,rounding_size=0.3',
                                fc=CAT.get(cat, '#8893a6'), ec='#00000022', lw=0.8, zorder=4))
    ax.text(x, y, short, ha='center', va='center', color='white', fontsize=8, fontweight='bold', zorder=5)
ax.set_aspect('equal'); ax.axis('off')
ax.set_title('Floor 5 — directions: Exit 5 → Study Room 11', fontsize=11)
fig.tight_layout(); fig.savefig(ROOT / 'map_preview_v2.png', dpi=130, facecolor='#eef1f6'); plt.close(fig)
print('wrote map_preview.png · route:', ' -> '.join(sc(p)[0] for p in route))
