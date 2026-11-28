#!/usr/bin/env python3
"""27 Nov 2026 evening (iPhone19,2 = iPhone 18 Pro): raw/ phyphox ZIPs -> labels_27nov.csv + clean/.

    python -I phase2/clean-data/2026-11-27/scripts/build_27nov.py      (a few seconds; stdlib only)

11 stops of 60 s, no walks, 17:15 to 17:42. Labels come from the file names (NAME below); the floor of each name is
checked against the recording's pressure (5F ~1014.30 hPa, 4F +0.6 to 0.8 hPa); a mismatch stops the build.
Layout as ../../2026-11-26-tian/clean/ (floorN/stops/sNN_<node>/iphone/<Sensor>.csv, manifest.csv, summary.json),
so walksense.py reads it like the other sessions. Sensor CSVs are copied verbatim; the sensor folders are gitignored.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent                       # phase2/clean-data/2026-11-27
RAW, OUT, LABELS = ROOT / 'raw', ROOT / 'clean', ROOT / 'labels_27nov.csv'
sys.path.insert(0, str(ROOT.parent / '2026-11-25-night' / 'scripts'))
from nightlib import STOP_MIN_S, place_label, read_meta              # noqa: E402  (same node names as every session)

HK = timezone(timedelta(hours=8))
DAY = datetime(2026, 11, 27, tzinfo=HK)
DEVICE, SLOT = 'iPhone19,2', 'iphone'
# file-name prefix -> (floor, node, confidence). medium = the name needs interpreting (which disabled toilet / escalator spot)
NAME = {'Sr9': (5, 'sr9', 'high'), 'Male tolet': (5, 'male_toilet', 'high'), 'Esca up': (5, 'esca_up', 'medium'),
        'Esca down': (5, 'esca_down', 'medium'), 'Y5302': (5, 'y5302', 'high'), 'Tolet cewe': (5, 'female_toilet', 'high'),
        'Disable tolet': (5, 'male_disabled_toilet', 'medium'), 'Lift stair 5': (5, 'lift_stairs5', 'high'),
        'Disabil tolet umum': (4, 'disabled_toilet', 'medium'), 'Lt1a': (4, 'lt1a', 'high'), 'Lt2b': (4, 'lt2b', 'high')}
FLOOR4_ABOVE = 0.40      # hPa above the first (5F) stop = floor 4 (FLOOR_JUMP_HPA of the app)


def clock(epoch):
    s = int(round(epoch - DAY.timestamp()))
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def rows_of(b):
    return max(0, b.count(b'\n') - 1)


def main():
    takes = []
    for p in sorted(RAW.glob('*.zip')):
        name = p.name.split(' 2026-11-27')[0]
        if name not in NAME:
            sys.exit(f'{p.name}: no label for "{name}"')
        b = p.read_bytes()
        meta = read_meta(b)
        if meta is None or meta['device'] != DEVICE:
            sys.exit(f'{p.name}: not a phyphox {DEVICE} recording')
        if meta['dur'] < STOP_MIN_S:
            sys.exit(f'{p.name}: {meta["dur"]} s is a walk, expected a stop')
        takes.append((p, b, meta, *NAME[name]))
    takes.sort(key=lambda t: t[2]['start'])
    p5 = takes[0][2]['pressure']
    for p, _, meta, floor, node, _ in takes:                         # pressure must agree with the name's floor
        if (meta['pressure'] - p5 > FLOOR4_ABOVE) != (floor == 4):
            sys.exit(f'{p.name}: pressure {meta["pressure"]} hPa does not fit floor {floor}')

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    labels, manifest = [], []
    order = sorted(takes, key=lambda t: (-t[3], t[2]['start']))      # floor 5 then 4, in time order
    for i, (p, b, meta, floor, node, conf) in enumerate(order, 1):
        no, folder = f's{i:02d}', f'floor{floor}/stops/s{i:02d}_{node}'
        d = OUT / folder / SLOT
        d.mkdir(parents=True)
        for fn, data in meta['sensors'].items():
            (d / fn).write_bytes(data)
        se, start = meta['sensors'], clock(meta['start'])
        iso = datetime.fromtimestamp(meta['start'], HK).strftime('%Y-%m-%d %H:%M:%S')
        labels.append({'source_zip': p.name, 'sha256': hashlib.sha256(b).hexdigest(), 'caption': p.name.split(' 2026-11-27')[0],
                       'device': DEVICE, 'start_hk': start, 'duration_s': round(meta['dur'], 1), 'kind': 'stop',
                       'floor': floor, 'no': no, 'node': node, 'confidence': conf, 'pressure_hpa': meta['pressure']})
        manifest.append({'floor': floor, 'type': 'stop', 'node': node, 'from_node': '', 'to_node': '',
                         'place': place_label(floor, node), 'phone': SLOT, 'device': DEVICE, 'start_hk': start,
                         'start_iso': iso, 'duration_s': round(meta['dur'], 1),
                         'n_accel': rows_of(se.get('Accelerometer.csv', b'')), 'n_gyro': rows_of(se.get('Gyroscope.csv', b'')),
                         'n_mag': rows_of(se.get('Magnetometer.csv', b'')), 'n_baro': rows_of(se.get('Barometer.csv', b'')),
                         'pressure_hpa': meta['pressure'], 'folder': folder, 'source_zip': p.name,
                         'label_raw': p.name.split(' 2026-11-27')[0], 'confidence': conf})
    for path, rows in ((LABELS, labels), (OUT / 'manifest.csv', manifest)):
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {'dataset': '2026-11-27 evening, iPhone19,2 (iPhone 18 Pro), stops only',
               'recordings_written': len(manifest), 'stops_floor5': sum(m['floor'] == 5 for m in manifest),
               'stops_floor4': sum(m['floor'] == 4 for m in manifest), 'walks': 0,
               'medium_confidence': [f"{m['folder']} ('{m['label_raw']}')" for m in manifest if m['confidence'] != 'high'],
               'pressure_hpa': {m['folder']: m['pressure_hpa'] for m in manifest}, 'labels_not_built': []}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1))
    (OUT / 'README.md').write_text('# Cleaned 27-Nov stops (iPhone19,2)\n\nGenerated by `../scripts/build_27nov.py`; see `../README.md`. '
                                   'The sensor folders are gitignored; rebuild them with the script.\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('recordings_written', 'stops_floor5', 'stops_floor4', 'medium_confidence',
                                              'labels_not_built')}, indent=1))


if __name__ == '__main__':
    main()
