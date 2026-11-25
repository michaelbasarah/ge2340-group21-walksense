#!/usr/bin/env python3
"""Magnetometer sanity check per phone and session: median |B| (uT) of the stop takes, and for the night run the mean
x/y/z offset against the same phone's take at the same place in Dicta's first 25-Nov run. Writes ../field_check.csv.
Earth's field here is about 40-45 uT; a phone whose stops sit far above that has an offset (uncalibrated sensor or a
magnet near it), which a kNN trained on other sessions cannot match. Numpy + stdlib.

    python -I phase2/clean-data/2026-11-25-night/scripts/check_field.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nightlib as nl          # noqa: E402

CD = nl.ROOT.parent
TREES = [('24s1', CD / '2026-11-24/sesi1/clean'), ('24s2', CD / '2026-11-24/sesi2/clean'), ('25nov', CD / '2026-11-25/clean'),
         ('25night', nl.ROOT / 'round/clean'), ('25night_tian', nl.ROOT / 'tian/clean')]


def stops(root, phone):
    out = {}
    for r in csv.DictReader((root / 'manifest.csv').open()):
        p = root / r['folder'] / phone / 'Magnetometer.csv'
        if r['type'] == 'stop' and r['phone'] == phone and p.exists():
            a = np.loadtxt(p, delimiter=',', skiprows=1)
            a = a[(a[:, 0] > 5) & (a[:, 0] < a[-1, 0] - 5)]
            out.setdefault((r['floor'], r['node']), []).append(a[:, 1:4])
    return out


rows = []
first = {ph: stops(CD / '2026-11-25/clean', ph) for ph in ('iphone', 'a56')}
for sid, root in TREES:
    phones = sorted({r['phone'] for r in csv.DictReader((root / 'manifest.csv').open())})
    for ph in phones:
        st = stops(root, ph)
        if not st:
            continue
        B = [float(np.linalg.norm(a, axis=1).mean()) for v in st.values() for a in v]
        row = {'session': sid, 'phone_folder': ph, 'stop_takes': len(B), 'B_median_uT': round(float(np.median(B)), 1),
               'B_min_uT': round(min(B), 1), 'B_max_uT': round(max(B), 1)}
        if sid == '25night' and ph in first:
            common = sorted(set(st) & set(first[ph]))
            d = np.array([np.mean([a.mean(0) for a in st[k]], 0) - np.mean([a.mean(0) for a in first[ph][k]], 0) for k in common])
            row.update({'places_vs_25nov': len(common), 'offset_vs_25nov_xyz_uT': ' '.join(f'{x:.1f}' for x in d.mean(0)),
                        'offset_sd_xyz_uT': ' '.join(f'{x:.1f}' for x in d.std(0)),
                        'median_xyz_distance_vs_25nov_uT': round(float(np.median(np.linalg.norm(d, axis=1))), 1)})
        rows.append(row)
keys = list(dict.fromkeys(k for r in rows for k in r))
with (nl.ROOT / 'field_check.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
for r in rows:
    print(r)
