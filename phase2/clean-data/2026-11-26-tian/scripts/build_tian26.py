#!/usr/bin/env python3
"""26 Nov 2026 morning (Tian, iPhone17,4): raw/ phyphox ZIPs + labels_tian26.csv -> clean/, in the layout of Dicta's 25-Nov tree.

    python -I phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py      (a few seconds; stdlib only)

The build of ../../2026-11-25-night/scripts/build_night.py for one phone and one track: clean/floor5|floor4/stops/sNN_<node>/
iphone/<Sensor>.csv and walks/wNN_<from>__<to>/iphone/<Sensor>.csv, manifest.csv (same columns as the night trees),
locations.csv, edges.csv, summary.json, ROUTE.md, README.md. Sensor CSVs are copied verbatim. Rows of labels_tian26.csv
with status 'ok' are built; any other status is listed in summary.json (labels_not_built) and left out. No Wi-Fi log.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tianlib as tl          # noqa: E402

OUT = tl.ROOT / 'clean'


def row_count(b: bytes) -> int:
    return max(0, b.count(b'\n') - 1)


def folder(r: dict) -> str:
    f = int(r['floor'])
    return (f"floor{f}/stops/{r['no']}_{r['node']}" if r['kind'] == 'stop'
            else f"floor{f}/walks/{r['no']}_{r['from_node']}__{r['to_node']}")


def main():
    labels = tl.read_labels()
    ok = [r for r in labels if r['status'] == 'ok']
    raw = sorted(p.name for p in tl.RAW.glob('*.zip'))
    if len({folder(r) for r in ok}) != len(ok):
        sys.exit('two recordings in one slot')
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    ok.sort(key=lambda r: (-int(r['floor']), tl.clock_epoch(r['start_hk'])))      # floor 5 then 4, in walk order
    manifest = []
    for r in ok:
        meta = tl.read_meta((tl.RAW / r['source_zip']).read_bytes())
        if meta['device'] != r['device']:
            sys.exit(f"{r['source_zip']}: device {meta['device']} != label row {r['device']}")
        d = OUT / folder(r) / r['slot']
        d.mkdir(parents=True)
        for fn, b in meta['sensors'].items():
            (d / fn).write_bytes(b)
        se = meta['sensors']
        f = int(r['floor'])
        manifest.append({'floor': f, 'type': r['kind'], 'node': r['node'], 'from_node': r['from_node'], 'to_node': r['to_node'],
                         'place': tl.place_label(f, r['node']) if r['kind'] == 'stop' else '',
                         'phone': r['slot'], 'device': r['device'], 'start_hk': r['start_hk'], 'start_iso': r['start_iso'],
                         'duration_s': r['duration_s'],
                         'n_accel': row_count(se.get('Accelerometer.csv', b'')), 'n_gyro': row_count(se.get('Gyroscope.csv', b'')),
                         'n_mag': row_count(se.get('Magnetometer.csv', b'')),
                         'n_baro': row_count(se.get('Barometer.csv', se.get('Pressure.csv', b''))),
                         'pressure_hpa': meta['pressure'], 'folder': folder(r), 'source_zip': r['source_zip'],
                         'label_raw': r['tian_caption'], 'confidence': r['confidence']})
    with (OUT / 'manifest.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0])); w.writeheader(); w.writerows(manifest)
    with (OUT / 'locations.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['floor', 'stop_no', 'node', 'label', 'n_phones', 'start_hk', 'x_m', 'y_m'])
        for m, r in zip(manifest, ok):
            if m['type'] == 'stop':
                w.writerow([m['floor'], r['no'], m['node'], m['place'], 1, m['start_hk'], '', ''])
    with (OUT / 'edges.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['floor', 'walk_no', 'from_node', 'to_node', 'n_phones', 'start_hk'])
        for m, r in zip(manifest, ok):
            if m['type'] == 'walk':
                w.writerow([m['floor'], r['no'], m['from_node'], m['to_node'], 1, m['start_hk']])

    n = Counter((m['floor'], m['type']) for m in manifest)
    summary = {
        'dataset': '2026-11-26 morning, track tian26 (Tian alone, floor 5 + floor 4)',
        'phones': [tl.SLOT], 'devices': {tl.SLOT: sorted({m['device'] for m in manifest})},
        'recordings_written': len(manifest),
        'stops': n[(5, 'stop')] + n[(4, 'stop')], 'walks': n[(5, 'walk')] + n[(4, 'walk')],
        'stops_floor5': n[(5, 'stop')], 'stops_floor4': n[(4, 'stop')], 'walks_floor5': n[(5, 'walk')], 'walks_floor4': n[(4, 'walk')],
        'per_phone': {tl.SLOT: {'stop': n[(5, 'stop')] + n[(4, 'stop')], 'walk': n[(5, 'walk')] + n[(4, 'walk')]}},
        'confidence': dict(Counter(m['confidence'] for m in manifest)),
        'medium_confidence': [f"{m['folder']} ('{m['label_raw']}')" for m in manifest if m['confidence'] != 'high'],
        'takes_without_barometer': sum(1 for m in manifest if not m['n_baro']),
        'raw_zips': len(raw), 'raw_without_label_row': sorted(set(raw) - {r['source_zip'] for r in labels}),
        'labels_not_built': [{'source_zip': r['source_zip'], 'status': r['status'], 'reason': r['reason']}
                             for r in labels if r['status'] != 'ok'],
        'wifi': 'none',
        'warnings': ['No canteen stop (the run starts at the exit 5 door) and no 5F exit 5 -> ... walk from the escalators: '
                     'between the 5F escalator-up stop and "esit 5 toilet disabled men" nothing was recorded.',
                     'Two captions contradict their neighbours and were resolved from the sequence (confidence medium): '
                     '"lift turun bawah" = escalator down 4F stop, "lt1b exit 10" = walk LT1A -> exit 10 door 4F.'],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1))

    def table(f):
        t = ['| # | time | type | place | caption |', '|---|------|------|-------|---------|']
        for m, r in zip(manifest, ok):
            if m['floor'] == f:
                what = m['place'] if m['type'] == 'stop' else f"{m['from_node']} → {m['to_node']}"
                t.append(f"| {r['no']} | {m['start_hk']} | {'STOP' if m['type'] == 'stop' else 'walk'} | {what} | {m['label_raw']} "
                         f"{'(medium)' if m['confidence'] != 'high' else ''}|")
        return '\n'.join(t)
    (OUT / 'ROUTE.md').write_text(
        f"# WalkSense route — 26 November 2026 morning, Tian (ip16 = iPhone17,4), floor 5 + floor 4\n\n"
        f"Built by `../scripts/build_tian26.py` from `../labels_tian26.csv` (labels = Tian's chat captions).\n\n"
        f"## Floor 5\n\n{summary['stops_floor5']} stops, {summary['walks_floor5']} walks.\n\n{table(5)}\n\n"
        f"## Floor 4\n\n{summary['stops_floor4']} stops, {summary['walks_floor4']} walks.\n\n{table(4)}\n\n## Notes\n\n"
        + '\n'.join(f'- {w}' for w in summary['warnings']) + '\n', encoding='utf-8')
    (OUT / 'README.md').write_text(
        '# Cleaned acquisition — 26 November 2026 morning, Tian\n\nGenerated by `../scripts/build_tian26.py`; see `../README.md`. '
        "Layout as Dicta's `../../2026-11-25/clean/` (floorN/stops|walks/<slot>/<phone>/<Sensor>.csv, manifest.csv, "
        'locations.csv, edges.csv, summary.json, ROUTE.md). The sensor folders are gitignored; rebuild them with the script.\n',
        encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('recordings_written', 'stops', 'walks', 'confidence', 'medium_confidence',
                                              'takes_without_barometer', 'raw_without_label_row', 'labels_not_built')}, indent=1))


if __name__ == '__main__':
    main()
