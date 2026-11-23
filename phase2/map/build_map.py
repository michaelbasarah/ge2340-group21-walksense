#!/usr/bin/env python3
"""Convert checkpoint lat/long -> local metres, plot the map, and check distances.

Reads coordinates.csv, writes coordinates_meters.csv + a labelled map PNG, and prints
a few real distances so the scale can be sanity-checked against tape/Google measurements.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
df = pd.read_csv(ROOT / 'coordinates.csv')

# Equirectangular projection around the centroid -> metres east (x) / north (y).
lat0, lon0 = df['lat'].mean(), df['long'].mean()
df['x_m'] = (df['long'] - lon0) * np.cos(np.radians(lat0)) * 111320.0
df['y_m'] = (df['lat'] - lat0) * 111320.0
df[['checkpoint', 'floor', 'x_m', 'y_m']].round(2).to_csv(ROOT / 'coordinates_meters.csv', index=False)

def dist(a, b):
    ra = df[df['checkpoint'].str.contains(a, case=False)].iloc[0]
    rb = df[df['checkpoint'].str.contains(b, case=False)].iloc[0]
    return float(np.hypot(ra['x_m'] - rb['x_m'], ra['y_m'] - rb['y_m']))

print('Distance sanity checks (metres):')
for a, b in [('Study Room 8', 'Study Room 11'), ('Study Room 8', 'Study Room 9'),
             ('Exit 5', 'Canteen'), ('Male toilet', 'Canteen'), ('Y5-202', 'Y5-302')]:
    try:
        print(f'  {a:14} <-> {b:14} = {dist(a, b):5.1f} m')
    except Exception:
        pass

fig, ax = plt.subplots(figsize=(9, 8))
for _, r in df.iterrows():
    wide = str(r.get('door_width')) == 'wide'
    ax.scatter(r['x_m'], r['y_m'], s=180 if wide else 90, c='#126782', zorder=3)
    ax.annotate(r['checkpoint'], (r['x_m'], r['y_m']), fontsize=8,
                xytext=(6, 4), textcoords='offset points')
ax.set_aspect('equal'); ax.grid(True, ls=':', alpha=.5)
ax.set_xlabel('metres east'); ax.set_ylabel('metres north')
ax.set_title('CityU floor 5 — checkpoints at real relative positions (from Google coordinates)')
fig.tight_layout(); fig.savefig(ROOT / 'floor5_map.png', dpi=130); plt.close(fig)

# Corridor edges as a Gabriel graph (planar, corridor-like): connect two checkpoints only
# if no other checkpoint lies inside the circle whose diameter is the segment between them.
# This is a SEED you can edit - remove any edge that crosses a wall, add any real corridor missed.
P = df[['x_m', 'y_m']].to_numpy()
names = df['checkpoint'].tolist()
n = len(P)
edges = []
for i in range(n):
    for j in range(i + 1, n):
        mid = (P[i] + P[j]) / 2.0
        rad = np.hypot(*(P[i] - P[j])) / 2.0
        if all(k in (i, j) or np.hypot(*(P[k] - mid)) >= rad - 1e-6 for k in range(n)):
            edges.append((names[i], names[j], round(float(np.hypot(*(P[i] - P[j]))), 1)))
ef = ROOT / 'edges_floor5.csv'
if ef.exists():
    print(f'\nwrote coordinates_meters.csv and floor5_map.png; KEPT your edited edges_floor5.csv '
          f'(delete it to regenerate a {len(edges)}-edge seed)')
else:
    pd.DataFrame(edges, columns=['from', 'to', 'distance_m']).to_csv(ef, index=False)
    print(f'\nwrote coordinates_meters.csv, floor5_map.png, and edges_floor5.csv ({len(edges)} corridor edges - edit to match the real plan)')
