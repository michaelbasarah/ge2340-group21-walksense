#!/usr/bin/env python3
"""Evidence for Tian's two doubtful 4F stops (22:50 'lt2b', 22:53 'lt2a'): mean magnetic field (phone x/y/z, uT, first
and last 5 s trimmed) of every 4F stop of Tian's iPhone17,4 in the night run, compared with the same handset's 4F stops
of 24 Nov session 2 (../../2026-11-24/sesi2/clean, iphone slot = iPhone17,4). Writes ../tian_lt_check.csv:
one row per night stop with its three nearest takes (x/y/z distance). Numpy + stdlib.

    python -I phase2/clean-data/2026-11-25-night/scripts/check_tian_lt.py

This is a check of a label, not a label: the takes stay out of training until Tian names the rooms.
"""
import csv
import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nightlib as nl          # noqa: E402

S2 = nl.ROOT.parent / '2026-11-24' / 'sesi2' / 'clean'


def feat(text: str) -> np.ndarray:
    a = np.array([[float(v) for v in r] for r in list(csv.reader(io.StringIO(text)))[1:] if r])
    a = a[(a[:, 0] > 5) & (a[:, 0] < a[-1, 0] - 5)]
    return np.r_[a[:, 1:4].mean(0), np.linalg.norm(a[:, 1:4], axis=1).mean()]


ref = {}
for r in csv.DictReader((S2 / 'manifest.csv').open()):
    if r['type'] == 'stop' and r['phone'] == 'iphone' and r['floor'] == '4' and r['device'] == 'iPhone17,4':
        ref[f"24s2 {r['node']}"] = feat((S2 / r['folder'] / 'iphone' / 'Magnetometer.csv').read_text())
night = {}
for r in nl.read_labels():
    if r['track'] == 'tian' and r['type'] == 'stop' and (r['floor'] == '4' or r['status'] != 'ok'):
        m = nl.read_meta((nl.RAW / r['source_zip']).read_bytes())
        tag = r['node'] if r['status'] == 'ok' else f"UNSURE '{r['label_raw']}'"
        night[f"night {r['start_hk'][:5]} {tag}"] = feat(m['sensors']['Magnetometer.csv'].decode())
rows = []
allf = {**ref, **night}
for k, v in night.items():
    near = sorted((float(np.linalg.norm(v[:3] - w[:3])), kk) for kk, w in allf.items() if kk != k)[:3]
    rows.append({'night_stop': k, 'B_mean_uT': round(float(v[3]), 1), 'x': round(float(v[0]), 1), 'y': round(float(v[1]), 1),
                 'z': round(float(v[2]), 1), **{f'nearest{i + 1}': f'{n} ({d:.1f})' for i, (d, n) in enumerate(near)}})
with (nl.ROOT / 'tian_lt_check.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows:
    print(r)
