#!/usr/bin/env python3
"""25 Nov 2026 night run: raw/ phyphox ZIPs + labels_night.csv -> one clean tree per track, in the layout of Dicta's 25-Nov tree.

    python -I phase2/clean-data/2026-11-25-night/scripts/build_night.py      (a few seconds; stdlib only)

Same layout and columns as ../../2026-11-25/scripts/build25.py, per track: <track>/clean/floor5|floor4/stops/sNN_<node>/<phone>/
<Sensor>.csv and walks/wNN_<from>__<to>/<phone>/<Sensor>.csv, manifest.csv, locations.csv, edges.csv, summary.json, ROUTE.md,
ROUTE.html, README.md, wifi/observations.csv (when the track has a WiGLE log in ../wifi_logs.csv). Sensor CSVs are copied verbatim.
Also writes ../build_summary.json (all tracks, and the rows left out).

Difference from build25.py: the route is not typed into the script. Every recording has one row in ../labels_night.csv
(track, floor, slot number, node or from/to, confidence, reason). Rows with status 'ok' are built; 'review' and 'exclude'
rows are listed and left out. A track's anchor rows (anchor = yes: Dicta's iPhone19,2 in 'round', Tian's iPhone17,4 in
'tian') define its slots; other phones' rows (added by ingest_export.py) join a slot by its number. Times after midnight
are written as 24:mm:ss in start_hk (nightlib.clock), with the real date-time in start_iso.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nightlib as nl          # noqa: E402

SENS_FILES = ('Accelerometer.csv', 'Barometer.csv', 'Gyroscope.csv', 'Magnetometer.csv', 'Pressure.csv')


def row_count(b: bytes) -> int:
    return max(0, b.count(b'\n') - 1)


TRACK_NOTES = {
    'round': ["Dicta (iphone = iPhone19,2) and Chris (a56 = SM-A566B) walked together; Dicta's named sequence defines the slots, "
              "Chris's takes join by START time (within 150 s) and his own file names (ingest_export.py).",
              'No 5F walk male_toilet -> y5302 and no 5F escalator STOP in either phone (the three 5F escalator walks are there; '
              'the gaps 22:23-22:31 and 22:33-22:38 would fit the two stops of the first run).',
              '"Exit 4 lt4" (23:17, both phones) is read as the exit 5 door on 4F (typo in both names; confidence medium).',
              'After the loop (00:15 to 00:40) 8 extra stops at weak places: sr9, y5202, exit10_door, male disabled toilet, '
              'lift/stairs, y5302 point 2, y5401 on 5F, then lift/stairs 4F (s13 to s19 on 5F, s13 on 4F).'],
    'tian': ["Tian (iPhone17,4, folder `iphone` in this tree) walked the loop on his own, 21:40 to 23:00, in his own order; "
             "his named sequence defines the slots.",
             'No 4F exit 5 door stop (he walked disabled toilet 4F -> LT2A directly).',
             "His 22:50 'lt2b' and 22:53 'lt2a' stops (and the walks 'eska naik bawah lt2 b', 'lt2b lt2a', 'lt2a exit10') sit where "
             "the route has LT1B and LT1A; they are left out (status review), see ../README.md."],
}


def wifi_rows(track: str, members: list[dict]):
    """WiGLE logs of this track (../wifi_logs.csv) -> observations with epoch (FirstSeen is UTC, as in wifi_docs25.py)."""
    import gzip
    from datetime import datetime, timezone
    obs, logs = [], []
    if not nl.WIFI_LOGS.exists():
        return obs, logs
    for w in csv.DictReader(nl.WIFI_LOGS.open(encoding='utf-8')):
        if w['track'] != track or w['status'] != 'ok':
            continue
        lines = gzip.decompress((nl.RAW / w['log']).read_bytes()).decode('utf-8', 'replace').splitlines()
        rows = list(csv.reader(lines[1:]))
        hdr, n = rows[0], 0
        for r in rows[1:]:
            d = dict(zip(hdr, r))
            if d.get('Type') != 'WIFI':
                continue
            t = datetime.strptime(d['FirstSeen'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
            if not nl.WINDOW[0].timestamp() <= t <= nl.WINDOW[1].timestamp():
                continue
            obs.append({'scanner_phone': w['scanner_phone'], 'source_log': w['log'], 'bssid': d['MAC'].lower(), 'ssid': d['SSID'],
                        'rssi': d['RSSI'], 'epoch': t, 'firstseen_hk': nl.iso(t)}); n += 1
        logs.append({'log': w['log'], 'scanner_phone': w['scanner_phone'], 'wifi_rows_in_window': n})
    return obs, logs


def main():
    labels = nl.read_labels()
    if not labels:
        sys.exit(f'no {nl.LABELS}')
    tracks = sorted({r['track'] for r in labels if r['status'] == 'ok'})
    raw_zips = sorted(p.name for p in nl.RAW.glob('*.zip'))
    labelled = {r['source_zip'] for r in labels}
    overview = {'tracks': {}, 'raw_zips': len(raw_zips), 'raw_without_label_row': [z for z in raw_zips if z not in labelled],
                'labels_not_built': [{'source_zip': r['source_zip'], 'slot': r['slot'], 'track': r['track'], 'status': r['status'],
                                      'reason': r['reason']} for r in labels if r['status'] != 'ok']}
    for track in tracks:
        overview['tracks'][track] = build_track(track, [r for r in labels if r['track'] == track])
    (nl.ROOT / 'build_summary.json').write_text(json.dumps(overview, indent=1))
    print(json.dumps({t: {k: v for k, v in s.items() if k in ('phones', 'recordings_written', 'stops', 'walks', 'per_phone', 'wifi')}
                      for t, s in overview['tracks'].items()}, indent=1))
    print('raw without a label row:', overview['raw_without_label_row'])
    for r in overview['labels_not_built']:
        print('  not built:', r['status'], r['slot'], r['source_zip'], '-', r['reason'])


def build_track(track: str, labels: list[dict]) -> dict:
    out = nl.ROOT / track / 'clean'
    ok = [r for r in labels if r['status'] == 'ok']
    slots = {}
    for r in ok:                                   # slots from this track's anchor rows
        if r['anchor'] != 'yes':
            continue
        f = int(r['floor'])
        folder = (f"floor{f}/stops/{r['no']}_{r['node']}" if r['type'] == 'stop'
                  else f"floor{f}/walks/{r['no']}_{r['from_node']}__{r['to_node']}")
        if folder in slots:
            sys.exit(f'{track}: two anchors for {folder}')
        slots[folder] = {'floor': f, 'type': r['type'], 'no': r['no'], 'node': r['node'], 'from': r['from_node'],
                         'to': r['to_node'], 'anchor': nl.clock_epoch(r['start_hk']), 'members': {}}
    by_no = {(s['floor'], s['type'], s['no']): k for k, s in slots.items()}
    dropped = []
    for r in ok:
        k = by_no.get((int(r['floor']), r['type'], r['no']))
        if k is None:
            sys.exit(f"{r['source_zip']}: slot {track} {r['floor']} {r['no']} has no anchor row")
        s = slots[k]
        if s['type'] == 'stop' and r['node'] != s['node'] or s['type'] == 'walk' and (r['from_node'], r['to_node']) != (s['from'], s['to']):
            sys.exit(f"{r['source_zip']}: node differs from its slot {k}")
        cur = s['members'].get(r['slot'])
        d = abs(nl.clock_epoch(r['start_hk']) - s['anchor'])
        if cur is not None:                     # one recording per phone per slot: keep the one nearer the anchor (build25 rule)
            if abs(nl.clock_epoch(cur['start_hk']) - s['anchor']) <= d:
                dropped.append(r); continue
            dropped.append(cur)
        s['members'][r['slot']] = r

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    order = sorted(slots, key=lambda k: (-slots[k]['floor'], slots[k]['anchor']))   # floor 5 then 4, in walk order (as build25)
    manifest, per_phone = [], defaultdict(Counter)
    for k in order:
        s = slots[k]
        for ph, r in sorted(s['members'].items()):
            meta = nl.read_meta((nl.RAW / r['source_zip']).read_bytes())
            d = out / k / ph
            d.mkdir(parents=True, exist_ok=True)
            for fn, b in meta['sensors'].items():
                (d / fn).write_bytes(b)
            per_phone[ph][s['type']] += 1
            se = meta['sensors']
            manifest.append({'floor': s['floor'], 'type': s['type'], 'node': s['node'], 'from_node': s['from'], 'to_node': s['to'],
                             'place': nl.place_label(s['floor'], s['node']) if s['type'] == 'stop' else '',
                             'phone': ph, 'device': r['device'], 'start_hk': r['start_hk'], 'start_iso': r['start_iso'],
                             'duration_s': r['duration_s'],
                             'n_accel': row_count(se.get('Accelerometer.csv', b'')), 'n_gyro': row_count(se.get('Gyroscope.csv', b'')),
                             'n_mag': row_count(se.get('Magnetometer.csv', b'')),
                             'n_baro': row_count(se.get('Barometer.csv', se.get('Pressure.csv', b''))),
                             'pressure_hpa': meta['pressure'], 'folder': k, 'source_zip': r['source_zip'],
                             'label_raw': r['label_raw'], 'confidence': r['confidence']})
    cols = list(manifest[0])
    with (out / 'manifest.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(manifest)
    with (out / 'locations.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['floor', 'stop_no', 'node', 'label', 'n_phones', 'start_hk', 'x_m', 'y_m'])
        for k in order:
            s = slots[k]
            if s['type'] == 'stop':
                w.writerow([s['floor'], s['no'], s['node'], nl.place_label(s['floor'], s['node']), len(s['members']), nl.clock(s['anchor']), '', ''])
    with (out / 'edges.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['floor', 'walk_no', 'from_node', 'to_node', 'n_phones', 'start_hk'])
        for k in order:
            s = slots[k]
            if s['type'] == 'walk':
                w.writerow([s['floor'], s['no'], s['from'], s['to'], len(s['members']), nl.clock(s['anchor'])])
    obs, logs = wifi_rows(track, manifest)
    if obs:
        (out / 'wifi').mkdir()
        with (out / 'wifi' / 'observations.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(obs[0])); w.writeheader(); w.writerows(obs)

    n = lambda f, t: sum(1 for s in slots.values() if s['floor'] == f and s['type'] == t)
    no_baro = sorted(f"{m['folder']} ({m['phone']})" for m in manifest if m['phone'] == 'iphone' and not m['n_baro'])
    no_baro_stops = [f for f in no_baro if '/stops/' in f]
    partial = [f"{k}: missing {', '.join(sorted(set(per_phone) - set(slots[k]['members'])))}"
               for k in order if set(per_phone) - set(slots[k]['members'])]
    summary = {
        'dataset': f'2026-11-25 night run, track {track} (floor 5 + floor 4)',
        'phones': sorted(per_phone),
        'devices': {ph: sorted({m['device'] for m in manifest if m['phone'] == ph}) for ph in sorted(per_phone)},
        'recordings_written': len(manifest),
        'stops': n(5, 'stop') + n(4, 'stop'), 'walks': n(5, 'walk') + n(4, 'walk'),
        'stops_floor5': n(5, 'stop'), 'stops_floor4': n(4, 'stop'), 'walks_floor5': n(5, 'walk'), 'walks_floor4': n(4, 'walk'),
        'per_phone': {ph: dict(c) for ph, c in sorted(per_phone.items())},
        'confidence': dict(Counter(m['confidence'] for m in manifest)),
        'slots_missing_a_phone': partial,
        'dropped_second_take_same_slot': [r['source_zip'] for r in dropped],
        'iphone_takes_without_barometer': len(no_baro), 'iphone_stops_without_barometer': no_baro_stops,
        'wifi': {'logs': logs, 'observations': len(obs)} if logs else 'none',
        'warnings': TRACK_NOTES.get(track, []) + [
            f'{len(no_baro)} of the iphone takes ({len(no_baro_stops)} stops) have no Barometer.csv (phyphox did not log '
            'pressure); those stops have no floor reading from the iPhone.'] * bool(no_baro),
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=1))
    write_docs(out, track, slots, order, summary)
    return summary


def write_docs(out, track, slots, order, summary):
    def table(f):
        out = ['| # | time | type | place | phones |', '|---|------|------|-------|--------|']
        for k in order:
            s = slots[k]
            if s['floor'] != f:
                continue
            what = nl.place_label(f, s['node']) if s['type'] == 'stop' else f"{s['from']} → {s['to']}"
            out.append(f"| {k.split('/')[-1]} | {nl.clock(s['anchor'])} | {'STOP' if s['type'] == 'stop' else 'walk'} | {what} | "
                       f"{','.join(sorted(s['members']))} ({len(s['members'])}) |")
        return '\n'.join(out)
    pp = summary['per_phone']
    ptab = '\n'.join(['| phone | stops | walks |', '|---|---|---|'] + [f"| {p} | {c.get('stop', 0)} | {c.get('walk', 0)} |" for p, c in pp.items()])
    md = f"""# WalkSense route — 25 November 2026, night run, track `{track}` (floor 5 + floor 4)

Second collection run of 25 Nov (times after midnight are written 24:mm:ss in `start_hk`; `start_iso` has the
real date). Built by `../../scripts/build_night.py` from `../../labels_night.csv`.

{ptab}

## Floor 5

{summary['stops_floor5']} stops, {summary['walks_floor5']} walks.

{table(5)}

## Floor 4

{summary['stops_floor4']} stops, {summary['walks_floor4']} walks.

{table(4)}

## Notes

""" + '\n'.join(f'- {w}' for w in summary['warnings']) + '\n'
    (out / 'ROUTE.md').write_text(md, encoding='utf-8')
    (out / 'README.md').write_text(
        f'# Cleaned acquisition — 25 November 2026 night run, track {track}\n\nGenerated by `../../scripts/build_night.py`; see `../../README.md` '
        'for the folder, the labels and how to add more phones. Layout as Dicta\'s `../../2026-11-25/clean/` '
        '(floorN/stops|walks/<slot>/<phone>/<Sensor>.csv, manifest.csv, locations.csv, edges.csv, summary.json, ROUTE.md, wifi/).\n',
        encoding='utf-8')
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;')
    H = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>WalkSense route 25 Nov night {track}</title>',
         '<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#1b2430;'
         'line-height:1.5;background:#fff}h2{border-bottom:2px solid #e4e8ee;padding-bottom:6px}.stop{background:#eef4ff;'
         'border-left:4px solid #2f6feb;padding:8px 12px;margin:8px 0;border-radius:6px}.walk{color:#5a6472;padding:2px 0 2px 20px;'
         'font-size:14px}.t{color:#9aa4b2;font-size:12px;margin-right:8px}.ph{float:right;font-size:12px;color:#2f6feb}</style>',
         f'<h1>WalkSense route — 25 Nov 2026 night run, track {track}</h1>']
    for f in (5, 4):
        H.append(f'<h2>Floor {f}</h2>')
        for k in order:
            s = slots[k]
            if s['floor'] != f:
                continue
            ph = ','.join(sorted(s['members']))
            if s['type'] == 'stop':
                H.append(f'<div class=stop><span class=t>{nl.clock(s["anchor"])}</span><b>{esc(nl.place_label(f, s["node"]))}</b> '
                         f'<span class=t>{k.split("/")[-1]}</span><span class=ph>{ph}</span></div>')
            else:
                H.append(f'<div class=walk><span class=t>{nl.clock(s["anchor"])}</span>{esc(s["from"])} &rarr; {esc(s["to"])}</div>')
    (out / 'ROUTE.html').write_text('\n'.join(H), encoding='utf-8')


if __name__ == '__main__':
    main()
