#!/usr/bin/env python3
"""Evidence for Tian's five doubtful 4F night takes (25 Nov 22:49 to 22:55, named "lt2b"/"lt2a" a second time, status
review in ../../2026-11-25-night/labels_night.csv): their magnetic field against this morning's four lecture-theatre stops
of the SAME phone (Tian's iPhone17,4, 26 Nov: lt2a 10:16, lt2b 10:19, lt1b 10:29, lt1a 10:32). Writes ../lt_night_check.csv.
A check of a label, not a label: nothing is relabelled here.

    python -I phase2/clean-data/2026-11-26-tian/scripts/check_lt_night.py        (numpy + stdlib)

Features (phone frame, uT; the protocol holds the phone flat facing the landmark, so x/y/z are comparable for stops):
  stop  mean x/y/z and |B| with the first and last 5 s trimmed (as ../../2026-11-25-night/scripts/check_tian_lt.py)
  walk  the first and the last 1.5 s (mean x/y/z): where the walk starts and ends, compared with the reference stops.
        A walk's direction turns the phone, so its x/y/z are less comparable than a stop's; |B| does not depend on it.
Controls, same rules: his night takes labelled ok at LT2A 22:34 and LT2B 22:37 (should match today's lt2a / lt2b), and
this morning's lt1b -> lt1a walk (should start at lt1b and end at lt1a).
Also writes ../medium_label_check.csv: this morning's stop captioned "lift turun bawah" (labelled escalator down 4F from the
sequence, confidence medium) against the same phone's 4F lift/stairs and escalator stops (this morning and the night run).
"""
import csv
import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tianlib as tl          # noqa: E402

NIGHT = tl.ROOT.parent / '2026-11-25-night'
REFS = ('lt2a', 'lt2b', 'lt1b', 'lt1a')
EDGE_S = 1.5


def mag(b: bytes) -> np.ndarray:
    return np.array([[float(v) for v in r] for r in list(csv.reader(io.StringIO(b.decode())))[1:] if r])


def stop_feat(a):
    a = a[(a[:, 0] > 5) & (a[:, 0] < a[-1, 0] - 5)]
    return a[:, 1:4].mean(0), float(np.linalg.norm(a[:, 1:4], axis=1).mean())


def walk_feat(a):
    head, tail = a[a[:, 0] <= a[0, 0] + EDGE_S], a[a[:, 0] >= a[-1, 0] - EDGE_S]
    return (head[:, 1:4].mean(0), float(np.linalg.norm(head[:, 1:4], axis=1).mean()),
            tail[:, 1:4].mean(0), float(np.linalg.norm(tail[:, 1:4], axis=1).mean()))


def main():
    ref = {}
    for r in tl.read_labels():
        if r['kind'] == 'stop' and r['floor'] == '4' and r['node'] in REFS:
            ref[r['node']] = (stop_feat(mag(tl.read_meta((tl.RAW / r['source_zip']).read_bytes())['sensors']['Magnetometer.csv'])),
                              r['start_hk'][:5])
    assert set(ref) == set(REFS), ref.keys()
    takes = []
    for r in csv.DictReader((NIGHT / 'labels_night.csv').open(encoding='utf-8')):
        if r['track'] != 'tian':
            continue
        doubt = r['status'] == 'review' and '22:49' <= r['start_hk'] <= '22:56'
        control = r['status'] == 'ok' and r['type'] == 'stop' and r['floor'] == '4' and r['node'] in ('lt2a', 'lt2b')
        if doubt or control:
            takes.append(('25 Nov night ' + ('DOUBTFUL' if doubt else f"control (ok: {r['node']})"), r['start_hk'][:5],
                          r['label_raw'], r['type'], (NIGHT / 'raw' / r['source_zip']).read_bytes()))
    for r in tl.read_labels():
        if r['kind'] == 'walk' and (r['from_node'], r['to_node']) == ('lt1b', 'lt1a'):
            takes.append(('26 Nov control (lt1b -> lt1a)', r['start_hk'][:5], r['tian_caption'], 'walk',
                          (tl.RAW / r['source_zip']).read_bytes()))
    if sum(t[0].endswith('DOUBTFUL') for t in takes) != 5:
        sys.exit('expected 5 doubtful night takes')

    rows = []
    for what, t, cap, kind, b in takes:
        a = mag(tl.read_meta(b)['sensors']['Magnetometer.csv'])
        parts = [('whole (stop)',) + stop_feat(a)] if kind == 'stop' else \
            [('start 1.5 s',) + walk_feat(a)[:2], ('end 1.5 s',) + walk_feat(a)[2:]]
        for part, xyz, B in parts:
            d = {n: float(np.linalg.norm(xyz - ref[n][0][0])) for n in REFS}
            order = sorted(REFS, key=d.get)
            rows.append({'take': what, 'time': t, 'tian_name': cap, 'type': kind, 'part': part,
                         'x': round(float(xyz[0]), 1), 'y': round(float(xyz[1]), 1), 'z': round(float(xyz[2]), 1), 'B_uT': round(B, 1),
                         **{f'dxyz_{n}': round(d[n], 1) for n in REFS},
                         **{f'dB_{n}': round(abs(B - ref[n][0][1]), 1) for n in REFS},
                         'nearest_xyz': order[0], 'second_xyz': order[1], 'margin_uT': round(d[order[1]] - d[order[0]], 1)})
    for n in REFS:
        (xyz, B), t = ref[n]
        rows.append({'take': f'26 Nov reference stop {n}', 'time': t, 'tian_name': n, 'type': 'stop', 'part': 'whole (stop)',
                     'x': round(float(xyz[0]), 1), 'y': round(float(xyz[1]), 1), 'z': round(float(xyz[2]), 1), 'B_uT': round(B, 1)})
    out = tl.ROOT / 'lt_night_check.csv'
    with out.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r['take'], r['time'], repr(r['tian_name']), r['part'], 'B', r['B_uT'],
              {n: r.get(f'dxyz_{n}') for n in REFS}, '->', r.get('nearest_xyz', ''), r.get('margin_uT', ''))


def medium_check():
    lab = {r['tian_caption']: r for r in tl.read_labels()}
    feat = lambda p: stop_feat(mag(tl.read_meta(p.read_bytes())['sensors']['Magnetometer.csv']))
    x = feat(tl.RAW / lab['lift turun bawah']['source_zip'])
    refs = [(f"26 Nov {lab[c]['start_hk'][:5]} '{c}'", lab[c]['place_v2'], tl.RAW / lab[c]['source_zip'])
            for c in ('stair lift bawah', 'esc naik bawah')]
    names = {r['node_25night']: r['place_v2'] for r in csv.DictReader(tl.NAMES.open(encoding='utf-8')) if r['floor'] == '4'}
    for r in csv.DictReader((NIGHT / 'labels_night.csv').open(encoding='utf-8')):
        if r['track'] == 'tian' and r['status'] == 'ok' and r['type'] == 'stop' and r['floor'] == '4' and \
                r['node'] in ('esca_down', 'esca_up', 'lift_stairs5'):
            refs.append((f"25 Nov night {r['start_hk'][:5]} '{r['label_raw']}'", names[r['node']], NIGHT / 'raw' / r['source_zip']))
    rows = []
    for what, place, p in refs:
        y = feat(p)
        rows.append({'take': "26 Nov 10:22 'lift turun bawah'", 'B_uT': round(x[1], 1), 'reference': what, 'reference_place': place,
                     'reference_B_uT': round(y[1], 1), 'dxyz_uT': round(float(np.linalg.norm(x[0] - y[0])), 1),
                     'dB_uT': round(abs(x[1] - y[1]), 1)})
    rows.sort(key=lambda r: r['dxyz_uT'])
    with (tl.ROOT / 'medium_label_check.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == '__main__':
    main()
    medium_check()
