#!/usr/bin/env python3
"""Compile ALL 49 recordings (stops + movements) into one human-readable review sheet.

Unlike RELABEL_TEMPLATE in the 2026-11-14 set this is pre-filled with the provisional
labels and a few sanity numbers (pressure, magnetic and acceleration medians, sample
counts) so a human can read the walk top-to-bottom and judge whether the cleaning and
labelling look right. Confirmation columns at the end are blank for you to fill in.
Re-running preserves anything you typed in the CONFIRM_* / NOTES columns.
"""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'review_all_recordings.csv'
CONFIRM_COLS = ['CONFIRM_label', 'CONFIRM_floor', 'CONFIRM_ok_or_fix', 'NOTES']

def read(name):
    with (ROOT / name).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

sessions = {s['session_id']: s for s in read('sessions.csv')}
quality = {(q['session_id'], q['sensor']): q for q in read('sensor_quality.csv')}
edges = {e['acc_session_id']: e for e in read('accelerometer_edges.csv')}
missing_after = {m['from_stop_id'] for m in read('missing_movements.csv')}
dup_sessions = {d['session_id']: d for d in read('duplicate_recordings.csv')}

def hhmmss(iso):
    return datetime.fromisoformat(iso).strftime('%H:%M:%S')

def num(value, nd):
    return f'{float(value):.{nd}f}' if value not in ('', None) else ''

def accepted_samples(sid, kind):
    sensors = ['barometer', 'magnetometer'] if kind == 'barometer_magnetometer_stop' else ['accelerometer']
    return sum(int(quality[(sid, s)]['kept_rows']) for s in sensors if (sid, s) in quality)

rows = []
ordered = sorted(sessions.values(), key=lambda s: (Decimal(s['start_epoch_s']), s['session_id']))
for seq, s in enumerate(ordered, 1):
    sid = s['session_id']; is_stop = s['kind'] == 'barometer_magnetometer_stop'
    if is_stop:
        provisional = s['location_label']
        from_loc = to_loc = s['location_label']
        pressure = num(quality[(sid, 'barometer')]['clean_x_median'], 4)
        mag = num(quality[(sid, 'magnetometer')]['magnitude_median'], 2)
        accel = ''
    else:
        e = edges[sid]
        from_loc = e['from_location']; to_loc = e['to_location']
        provisional = f"{from_loc}  →  {to_loc}"
        pressure = ''; mag = ''
        accel = num(quality[(sid, 'accelerometer')]['magnitude_median'], 3)
    flags = []
    if sid in dup_sessions:
        flags.append(f"interval 1 is a DUPLICATE re-export of {dup_sessions[sid]['duplicate_of_session_id']} (quarantined)")
    if sid in missing_after:
        flags.append('no walk recording to the next stop (escalator landing)')
    row = {'seq': seq, 'recording_id': sid, 'kind': 'stop' if is_stop else 'movement',
           'start_hk': hhmmss(s['start_hk']), 'dur_s': num(s['recorded_duration_s'], 1),
           'device': s['device_model'], 'source_zip': s['source_zip'],
           'provisional_label': provisional, 'from_location': from_loc, 'to_location': to_loc,
           'label_confidence': s['label_confidence'],
           'pressure_median_hpa': pressure, 'magnetic_magnitude_median_uT': mag,
           'accel_magnitude_median_ms2': accel, 'accepted_samples': accepted_samples(sid, s['kind']),
           'flags': '; '.join(flags)}
    for c in CONFIRM_COLS:
        row[c] = ''
    rows.append(row)

# Preserve anything already typed into the confirmation columns on a previous run.
if TARGET.exists():
    old = {r['recording_id']: r for r in read('review_all_recordings.csv')}
    for r in rows:
        prev = old.get(r['recording_id'])
        if prev:
            for c in CONFIRM_COLS:
                if prev.get(c):
                    r[c] = prev[c]

with TARGET.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

assert len(rows) == 49
print(f'Wrote {TARGET.name}: {len(rows)} recordings '
      f"({sum(r['kind']=='stop' for r in rows)} stops + {sum(r['kind']=='movement' for r in rows)} movements), walk order.")
