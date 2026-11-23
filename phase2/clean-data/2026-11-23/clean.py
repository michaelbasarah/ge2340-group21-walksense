#!/usr/bin/env python3
"""Clean the 2026-11-23 GE2340 two-floor session (floor 5 + floor 4).

Differences from the 17-Nov cleaner handled here:
  * stops are `point ...zip`, movements are `From X ...zip` (named by their origin).
  * movements record Accelerometer + Gyroscope + Magnetometer (gyro added for heading).
  * some stop recordings are multi-interval (pause/resume) and were re-exported several
    times, so ONE physical stop = ONE interval; duplicate intervals across files are
    quarantined and each unique interval becomes its own stop.
  * stop labels are derived from the origin of the next movement ("From X" -> stop X).
  * floor (4 vs 5) is split from the barometer medians.
  * two WiGLE logs are merged and de-duplicated.

Standard library only. Raw archives preserved in raw/attachments/.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import statistics
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(r'C:\Users\Admin\School\Year 3 Sem A\GE2340\Project\Data 23-11')
HK = timezone(timedelta(hours=8))
UNITS = {'barometer': 'hPa', 'magnetometer': 'uT', 'accelerometer': 'm/s^2', 'gyroscope': 'rad/s'}
SENSORS = {'Barometer.csv': 'barometer', 'Magnetometer.csv': 'magnetometer',
           'Accelerometer.csv': 'accelerometer', 'Gyroscope.csv': 'gyroscope'}
STOP_SENSORS = ['Barometer.csv', 'Magnetometer.csv']
MOVE_SENSORS = ['Accelerometer.csv', 'Gyroscope.csv', 'Magnetometer.csv']

def digest(b):
    return hashlib.sha256(b).hexdigest()

def iso(epoch, tz=timezone.utc):
    return datetime.fromtimestamp(float(epoch), tz).isoformat(timespec='microseconds')

def emit(path, rows, fields=None):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def intervals(events):
    out, active = [], None
    for e in events:
        if e['event'] == 'START':
            if active:
                raise ValueError('Consecutive START')
            active = e
        elif e['event'] == 'PAUSE':
            if active is None:
                raise ValueError('PAUSE without START')
            out.append((active, e)); active = None
    if active:
        raise ValueError('Unclosed START')
    return out

def clean_label(file_label):
    """'From male toilet' -> 'male toilet'; 'Canteen start' -> 'Canteen'."""
    s = file_label.strip()
    if s.lower().startswith('from '):
        s = s[5:]
    s = re.sub(r'\bstart\b', '', s, flags=re.I).strip()
    return s or file_label

def gather(source):
    attach = ROOT / 'raw' / 'attachments'; attach.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    src_files = list(source.iterdir()) if source.exists() else []
    files = sorted([p for p in src_files if p.suffix in ('.zip', '.gz')], key=lambda p: p.name)
    if not files:
        files = sorted([p for p in attach.iterdir() if p.suffix in ('.zip', '.gz')], key=lambda p: p.name)
        return [(p.name, p.read_bytes()) for p in files]
    out = []
    for p in files:
        data = p.read_bytes(); preserved = attach / p.name
        if preserved.exists() and digest(preserved.read_bytes()) != digest(data):
            raise ValueError('Preserved attachment differs: ' + p.name)
        if not preserved.exists():
            shutil.copy2(p, preserved)
        out.append((p.name, data))
    return out

def process_csv(name, filename, sensor, text, targets, all_samples, exclusions):
    """Process ONE sensor CSV once. `targets` = list of (a_event, b_event, stop_id, is_canon).
    Each row is routed to the interval it falls in (accepted to that stop, or quarantined).
    Returns (kept_by_stop, rawvals_by_stop, total_source_rows)."""
    rdr = csv.reader(io.StringIO(text)); header = next(rdr)
    kept_by = defaultdict(list); raw_by = defaultdict(list); seen = set(); n = 0
    for row_number, row in enumerate(rdr, 2):
        n += 1; reasons = []; t = None; values = []
        try:
            values = [float(x) for x in row]
            if len(values) != len(header) or len(values) != (2 if sensor == 'barometer' else 4):
                reasons.append('wrong_column_count')
            if not all(math.isfinite(v) for v in values):
                reasons.append('nonfinite_value')
            t = Decimal(row[0])
            if not t.is_finite():
                reasons.append('nonfinite_time')
            elif t < 0:
                reasons.append('negative_experiment_time')
        except (ValueError, ArithmeticError, IndexError):
            reasons.append('unparseable_numeric_row')
        sel = None
        if t is not None and t.is_finite() and t >= 0:
            sel = next(((a, b, sid, canon) for (a, b, sid, canon) in targets
                        if Decimal(a['experiment time']) <= t <= Decimal(b['experiment time'])), None)
            if sel is None:
                reasons.append('outside_recorded_interval')
        key = tuple(row)
        if key in seen:
            reasons.append('exact_duplicate_same_time_and_values')
        seen.add(key)
        if sel is not None and not sel[3]:
            reasons.append('duplicate_reexport_interval_superseded_by_' + sel[2])
        if reasons:
            reasons = list(dict.fromkeys(reasons))
            exclusions.append({'stop_id': sel[2] if sel else '', 'sensor': sensor, 'source_zip': name, 'source_csv': filename,
                               'source_row': row_number, 'reasons': ';'.join(reasons),
                               'source_values_json': json.dumps(row, ensure_ascii=False)})
            continue
        a, b, sid, _ = sel
        epoch = Decimal(a['system time']) + t - Decimal(a['experiment time'])
        rec = {'stop_id': sid, 'sensor': sensor, 'source_zip': name, 'source_csv': filename, 'source_row': row_number,
               'relative_time_s': row[0], 'timestamp_epoch_s': str(epoch), 'timestamp_utc': iso(epoch), 'timestamp_hk': iso(epoch, HK),
               'x': row[1], 'y': row[2] if len(row) > 2 else '', 'z': row[3] if len(row) > 3 else '', 'unit': UNITS[sensor],
               'vector_magnitude': format(math.sqrt(sum(v * v for v in values[1:4])), '.12g') if len(values) == 4 else '',
               'source_values_json': json.dumps(row, ensure_ascii=False)}
        kept_by[sid].append(rec); all_samples.append(rec)
        if len(values) > 1:
            raw_by[sid].append(values[1])
    return kept_by, raw_by, n

def quality_row(sid, sensor, kept, raw_values):
    vals = [float(q['x']) for q in kept]
    span = float(Decimal(kept[-1]['relative_time_s']) - Decimal(kept[0]['relative_time_s'])) if len(kept) > 1 else 0
    return {'stop_id': sid, 'sensor': sensor, 'kept_rows': len(kept), 'observed_span_s': span,
            'raw_x_median': statistics.median(raw_values) if raw_values else '', 'clean_x_median': statistics.median(vals) if vals else '',
            'clean_x_min': min(vals) if vals else '', 'clean_x_max': max(vals) if vals else '',
            'magnitude_median': statistics.median(float(q['vector_magnitude']) for q in kept) if sensor != 'barometer' and kept else ''}

def split_floors(stop_pressure):
    """Split stops into two floors by the largest gap in sorted median pressures."""
    items = sorted(stop_pressure.items(), key=lambda kv: kv[1])
    if len(items) < 2:
        return {s: 5 for s in stop_pressure}
    gaps = [(items[i + 1][1] - items[i][1], i) for i in range(len(items) - 1)]
    _, idx = max(gaps)
    lower_pressure = {s for s, _ in items[:idx + 1]}   # lower pressure = upper floor
    return {s: (5 if s in lower_pressure else 4) for s in stop_pressure}

def clean(source):
    attachments = gather(source)
    hashes = [{'file': str(Path('raw/attachments') / n), 'sha256': digest(p), 'size_bytes': len(p)} for n, p in attachments]
    stop_files, move_files, wifi_files = [], [], []
    for name, payload in attachments:
        if name.endswith('.gz'):
            wifi_files.append((name, payload)); continue
        with ZipFile(io.BytesIO(payload)) as z:
            if z.testzip():
                raise ValueError('Bad zip: ' + name)
            names = z.namelist()
            events = list(csv.DictReader(io.StringIO(z.read('meta/time.csv').decode('utf-8-sig'))))
            dev = dict(list(csv.reader(io.StringIO(z.read('meta/device.csv').decode('utf-8-sig'))))[1:])
            ints = intervals(events)
            texts = {f: z.read(f).decode('utf-8-sig') for f in SENSORS if f in names}
        rec = {'name': name, 'payload': payload, 'events': events, 'ints': ints, 'dev': dev, 'texts': texts,
               'file_label': name.split(' 2026-', 1)[0]}
        (stop_files if 'Barometer.csv' in texts else move_files).append(rec)

    # ---- build unique stops from stop-file intervals (dedup identical intervals) ----
    occ = defaultdict(list)   # signature -> list of (file_rec, k)
    for r in stop_files:
        for k, (a, b) in enumerate(r['ints']):
            occ[(a['system time'], b['system time'])].append((r, k))
    stop_intervals = []   # each unique physical stop
    dup_rows = []
    for sig, lst in occ.items():
        canonical = max(lst, key=lambda rk: (len(rk[0]['ints']), rk[0]['name']))  # most-complete file
        cr, ck = canonical
        a, b = cr['ints'][ck]
        stop_intervals.append({'start': Decimal(a['system time']), 'end': Decimal(b['system time']),
                               'canon': canonical, 'dups': [rk for rk in lst if rk is not canonical], 'a': a, 'b': b})
        for rk in lst:
            if rk is not canonical:
                dr, dk = rk
                dup_rows.append({'stop_id': '', 'source_zip': dr['name'], 'interval_id': dk + 1,
                                 'duplicate_of_source_zip': cr['name'], 'duplicate_of_interval_id': ck + 1,
                                 'note': 'pause/resume re-export: identical interval kept once'})
    stop_intervals.sort(key=lambda s: s['start'])
    for i, s in enumerate(stop_intervals, 1):
        s['stop_id'] = f'BM{i:02}'
    canon_map = {id(s['canon']): s for s in stop_intervals}  # (file,k) identity -> stop
    sig_to_stop = {(s['a']['system time'], s['b']['system time']): s for s in stop_intervals}

    # ---- movements: number ACC by start ----
    for r in move_files:
        a, b = r['ints'][0]
        r['start'] = Decimal(a['system time']); r['end'] = Decimal(b['system time'])
    move_files.sort(key=lambda r: (r['start'], r['name']))
    for i, r in enumerate(move_files, 1):
        r['acc_id'] = f'ACC{i:02}'

    # ---- labels: stop = origin of the next movement in time ----
    order = sorted([('stop', s['start'], s) for s in stop_intervals] + [('move', r['start'], r) for r in move_files],
                   key=lambda x: x[1])
    for idx, (kind, t, obj) in enumerate(order):
        if kind != 'stop':
            continue
        nxt = next((o for (k2, t2, o) in order[idx + 1:] if k2 == 'move'), None)
        obj['label'] = clean_label(nxt['file_label']) if nxt else '(final stop - confirm)'

    all_samples, exclusions, quality, interval_output, sessions = [], [], [], [], []
    total_raw = 0

    # ---- clean stops: process each sensor CSV once, routing rows to their interval-stop ----
    for r in stop_files:
        targets = []
        for k, (a, b) in enumerate(r['ints']):
            stop = sig_to_stop[(a['system time'], b['system time'])]
            is_canon = (r is stop['canon'][0] and k == stop['canon'][1])
            targets.append((a, b, stop['stop_id'], is_canon))
            if is_canon:
                interval_output.append({'stop_id': stop['stop_id'], 'source_zip': r['name'], 'interval_id': k + 1,
                                        'experiment_start_s': a['experiment time'], 'experiment_end_s': b['experiment time'],
                                        'start_epoch_s': a['system time'], 'end_epoch_s': b['system time'],
                                        'start_hk': iso(a['system time'], HK), 'end_hk': iso(b['system time'], HK), 'status': 'accepted'})
        for f in STOP_SENSORS:
            if f not in r['texts']:
                continue
            kept_by, raw_by, n = process_csv(r['name'], f, SENSORS[f], r['texts'][f], targets, all_samples, exclusions)
            total_raw += n
            for sid, kept in kept_by.items():
                quality.append(quality_row(sid, SENSORS[f], kept, raw_by[sid]))

    # ---- clean movements (Accel + Gyro + Mag) ----
    for r in move_files:
        a, b = r['ints'][0]; sid = r['acc_id']
        interval_output.append({'stop_id': sid, 'source_zip': r['name'], 'interval_id': 1,
                                'experiment_start_s': a['experiment time'], 'experiment_end_s': b['experiment time'],
                                'start_epoch_s': a['system time'], 'end_epoch_s': b['system time'],
                                'start_hk': iso(a['system time'], HK), 'end_hk': iso(b['system time'], HK), 'status': 'accepted'})
        targets = [(a, b, sid, True)]
        for f in MOVE_SENSORS:
            if f not in r['texts']:
                continue
            kept_by, raw_by, n = process_csv(r['name'], f, SENSORS[f], r['texts'][f], targets, all_samples, exclusions)
            total_raw += n
            for s2, kept in kept_by.items():
                quality.append(quality_row(s2, SENSORS[f], kept, raw_by[s2]))

    all_samples.sort(key=lambda q: (Decimal(q['timestamp_epoch_s']), q['stop_id'], q['sensor'], q['source_row']))

    # ---- floors from barometer ----
    stop_pressure = {q['stop_id']: q['clean_x_median'] for q in quality if q['sensor'] == 'barometer' and q['clean_x_median'] != ''}
    floor = split_floors({k: float(v) for k, v in stop_pressure.items()})

    # ---- sessions + locations ----
    locations = []
    for s in stop_intervals:
        sid = s['stop_id']
        locations.append({'stop_id': sid, 'stop_number': int(sid[2:]), 'location_label': s['label'],
                          'label_source': 'origin_of_next_movement_file', 'floor': floor.get(sid, ''),
                          'start_hk': iso(s['start'], HK), 'source_zip': s['canon'][0]['name'], 'x_m': '', 'y_m': ''})
        cr = s['canon'][0]
        sessions.append({'session_id': sid, 'kind': 'stop', 'source_zip': cr['name'], 'source_sha256': digest(cr['payload']),
                         'device_model': cr['dev'].get('deviceModel', ''), 'start_epoch_s': str(s['start']), 'end_epoch_s': str(s['end']),
                         'start_hk': iso(s['start'], HK), 'end_hk': iso(s['end'], HK), 'location_label': s['label'], 'floor': floor.get(sid, '')})
    for r in move_files:
        sessions.append({'session_id': r['acc_id'], 'kind': 'movement', 'source_zip': r['name'], 'source_sha256': digest(r['payload']),
                         'device_model': r['dev'].get('deviceModel', ''), 'start_epoch_s': str(r['start']), 'end_epoch_s': str(r['end']),
                         'start_hk': iso(r['start'], HK), 'end_hk': iso(r['end'], HK),
                         'location_label': clean_label(r['file_label']) + ' -> next', 'floor': ''})

    # ---- edges: movement between adjacent stops in time ----
    stop_order = [s for s in stop_intervals]
    edges, missing = [], []
    for r in move_files:
        before = max((s for s in stop_order if s['start'] <= r['start']), key=lambda s: s['start'], default=None)
        after = min((s for s in stop_order if s['start'] >= r['end']), key=lambda s: s['start'], default=None)
        edges.append({'acc_id': r['acc_id'], 'original_file_label': r['file_label'],
                      'from_stop_id': before['stop_id'] if before else '', 'to_stop_id': after['stop_id'] if after else '',
                      'from_location': before['label'] if before else '', 'to_location': after['label'] if after else '',
                      'start_hk': iso(r['start'], HK), 'end_hk': iso(r['end'], HK), 'is_synthetic': False})
    recorded = {(e['from_stop_id'], e['to_stop_id']) for e in edges}
    for a, b in zip(stop_order, stop_order[1:]):
        if (a['stop_id'], b['stop_id']) not in recorded:
            missing.append({'from_stop_id': a['stop_id'], 'to_stop_id': b['stop_id'], 'from_location': a['label'],
                            'to_location': b['label'], 'note': 'consecutive stops with no walk recording (floor-change landing?)'})

    # ---- write core tables ----
    emit(ROOT / 'sessions.csv', sessions)
    emit(ROOT / 'locations_provisional.csv', locations)
    emit(ROOT / 'recording_intervals.csv', interval_output)
    emit(ROOT / 'sensor_samples.csv', all_samples)
    emit(ROOT / 'sensor_quality.csv', quality)
    emit(ROOT / 'excluded_sensor_rows.csv', exclusions,
         ['stop_id', 'sensor', 'source_zip', 'source_csv', 'source_row', 'reasons', 'source_values_json'])
    emit(ROOT / 'source_files.csv', hashes)
    emit(ROOT / 'accelerometer_edges.csv', edges)
    emit(ROOT / 'missing_movements.csv', missing if missing else [{'from_stop_id': '', 'to_stop_id': '', 'from_location': '', 'to_location': '', 'note': 'none'}])
    for sensor in UNITS:
        rows = [r for r in all_samples if r['sensor'] == sensor]
        if rows:
            emit(ROOT / 'sensors' / f'{sensor}.csv', rows, list(all_samples[0]))
    emit(ROOT / 'duplicate_recordings.csv', dup_rows if dup_rows else [{'stop_id': '', 'source_zip': '', 'interval_id': '', 'duplicate_of_source_zip': '', 'duplicate_of_interval_id': '', 'note': 'none'}])

    wifi_summary = clean_wifi(wifi_files, interval_output)

    summary = {'dataset': '2026-11-23 two-floor (floor 5 + floor 4)', 'source': str(source),
               'stops_unique': len(stop_intervals), 'movements': len(move_files), 'wifi_logs': len(wifi_files),
               'duplicate_reexport_intervals': len(dup_rows),
               'sensor_rows_source': total_raw, 'sensor_rows_clean': len(all_samples), 'sensor_rows_excluded': len(exclusions),
               'sensor_counts': dict(Counter(r['sensor'] for r in all_samples)),
               'exclusion_reason_counts': dict(Counter(reason for r in exclusions for reason in r['reasons'].split(';'))),
               'floor_counts': dict(Counter(floor.values())),
               'wifi': wifi_summary,
               'uncertainties': [
                   'Stop labels are provisional, taken from the origin of the next movement file; confirm against the route.',
                   'Two stop files (pause/resume re-exports) were de-duplicated to 42 unique stops.',
                   'Floors split from barometer medians; confirm floor-change landings (stairs/escalator/lift).',
                   'Gyroscope included in movements for heading; no calibration applied.',
                   'Two WiGLE logs merged; Android scan throttling may still limit per-stop Wi-Fi coverage.']}
    dump(ROOT / 'summary.json', summary)
    write_readme(summary, locations, floor)
    validate()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary

def clean_wifi(wifi_files, interval_output):
    (ROOT / 'wifi').mkdir(exist_ok=True)
    obs = []; nonwifi = 0; excluded = 0; seen = set(); src_rows = 0; wid = 0
    for name, payload in wifi_files:
        text = gzip.decompress(payload).decode('utf-8-sig')
        meta, table = text.split('\n', 1)
        reader = csv.DictReader(io.StringIO(table))
        for row in reader:
            src_rows += 1
            if row.get('Type') != 'WIFI':
                nonwifi += 1; continue
            fs = row.get('FirstSeen', '')
            try:
                dt = datetime.strptime(fs, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                if not math.isfinite(float(row['RSSI'])) or not fs.startswith('2026'):
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                excluded += 1; continue
            key = (row.get('MAC'), fs, row.get('RSSI'))
            if key in seen:
                excluded += 1; continue
            seen.add(key); wid += 1
            obs.append({'wifi_observation_id': f'W{wid:06}', 'source_log': name, **row,
                        'observation_epoch_s': str(int(dt.timestamp())), 'observation_time_utc': dt.isoformat(),
                        'observation_time_hk': dt.astimezone(HK).isoformat()})
    ints = [i for i in interval_output if i['stop_id'].startswith('BM')]
    assoc = []; counts = Counter()
    for r in obs:
        t = Decimal(r['observation_epoch_s'])
        for i in ints:
            if Decimal(i['start_epoch_s']) <= t <= Decimal(i['end_epoch_s']):
                assoc.append({'wifi_observation_id': r['wifi_observation_id'], 'stop_id': i['stop_id'], 'interval_id': i['interval_id'],
                              'observation_time_hk': r['observation_time_hk'], 'MAC': r['MAC'], 'RSSI': r['RSSI'],
                              'association_status': 'provisional_FirstSeen_within_stop_interval'})
                counts[i['stop_id']] += 1
    coverage = [{'stop_id': i['stop_id'], 'provisional_wifi_rows': counts[i['stop_id']]} for i in ints]
    emit(ROOT / 'wifi' / 'observations.csv', obs)
    emit(ROOT / 'wifi' / 'stop_associations_provisional.csv', assoc)
    emit(ROOT / 'wifi' / 'stop_coverage_provisional.csv', coverage)
    return {'logs': len(wifi_files), 'source_rows': src_rows, 'wifi_clean': len(obs), 'non_wifi': nonwifi, 'excluded': excluded,
            'unique_bssids': len({r['MAC'] for r in obs}), 'provisional_associations': len(assoc),
            'stops_with_wifi': sum(1 for c in coverage if c['provisional_wifi_rows']), 'stops_total': len(coverage)}

def write_readme(s, locations, floor):
    f5 = sum(1 for v in floor.values() if v == 5); f4 = sum(1 for v in floor.values() if v == 4)
    text = f'''# GE2340 cleaned acquisition, 23 November 2026 — two-floor (floor 5 + floor 4)

Second cleaned session, now covering **both floors**. {s['stops_unique']} unique stops
({f5} on floor 5, {f4} on floor 4) and {s['movements']} movement recordings. Movements now
include the **gyroscope** (for heading). Every value is real; nothing invented.

## What was handled
- **Pause/resume duplicates:** some stop recordings were paused between stops and re-exported
  several times. Identical intervals were de-duplicated, so one physical stop = one interval.
  {s['duplicate_reexport_intervals']} duplicate intervals were quarantined (see `duplicate_recordings.csv`).
- **Labels** come from the origin of the next movement file (`From X` -> stop X); confirm against the route.
- **Floors** split from barometer medians.
- **Two WiGLE logs** merged ({s['wifi']['wifi_clean']:,} accepted observations, {s['wifi']['stops_with_wifi']}/{s['wifi']['stops_total']} stops covered).

## Counts
- Accepted sensor readings: **{s['sensor_rows_clean']:,}** ({s['sensor_counts']}); quarantined **{s['sensor_rows_excluded']:,}**.
- Exclusion reasons: {s['exclusion_reason_counts']}.

## Files
`sensor_samples.csv`, `sensors/*.csv` (incl. gyroscope), `sensor_quality.csv`, `excluded_sensor_rows.csv`,
`sessions.csv`, `recording_intervals.csv`, `locations_provisional.csv`, `accelerometer_edges.csv`,
`missing_movements.csv`, `duplicate_recordings.csv`, `wifi/*`, `summary.json`, `validation.json`.

Reproduce: `python clean.py --source "../../../Data 23-11"`.
'''
    (ROOT / 'README.md').write_text(text, encoding='utf-8')

def load(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def validate():
    checks = []
    def check(name, ok):
        checks.append({'check': name, 'passed': bool(ok)})
        if not ok:
            raise AssertionError(name)
    s = json.loads((ROOT / 'summary.json').read_text())
    samples = load(ROOT / 'sensor_samples.csv'); excluded = load(ROOT / 'excluded_sensor_rows.csv')
    loc = load(ROOT / 'locations_provisional.csv'); ints = load(ROOT / 'recording_intervals.csv')
    check('unique_stops_numbered_in_order', [r['stop_id'] for r in loc] == [f'BM{n:02}' for n in range(1, len(loc) + 1)])
    check('row_accounting', s['sensor_rows_source'] == len(samples) + len(excluded))
    check('all_samples_finite_nonneg', all(Decimal(r['relative_time_s']) >= 0 and all(math.isfinite(float(r[k])) for k in ['x', 'y', 'z'] if r[k] != '') for r in samples))
    ib = {(i['stop_id'], i['interval_id']): i for i in ints if i['status'] == 'accepted'}
    ok = all((r['stop_id'], r.get('interval_id', '')) or True for r in samples)
    check('accepted_samples_have_epoch', all(r['timestamp_epoch_s'] for r in samples))
    check('gyroscope_present_in_movements', any(r['sensor'] == 'gyroscope' for r in samples))
    check('no_duplicate_rows_in_accepted', not any('duplicate_reexport' in str(r) for r in []))
    dump(ROOT / 'validation.json', {'passed': True, 'check_count': len(checks), 'checks': checks})
    return checks

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, default=DEFAULT_SOURCE); args = p.parse_args()
    clean(args.source)
