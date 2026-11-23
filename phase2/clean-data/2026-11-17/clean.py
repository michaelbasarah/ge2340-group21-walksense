#!/usr/bin/env python3
"""Clean the 2026-11-17 GE2340 sensor acquisition without inventing measurements.

Standard library only. Raw archives are preserved byte-identically in raw/attachments/.
Re-run outputs are deterministic. Unlike the 2026-11-14 acquisition this input is a
folder of loose phyphox ZIPs plus one WiGLE GZIP (no WhatsApp chat export), the 23
movement recordings are already route-labelled by their filenames, and there is no
numbering typo and no user-requested synthetic connector copy. Stops are numbered
BM01..BM26 in recording order and also carry a provisional location label derived
from the adjacent movement filenames; every location link is marked provisional.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import gzip
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import shutil
import statistics
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(r'C:\Users\Admin\School\Year 3 Sem A\GE2340\Project\Data (17-11)')
HK = timezone(timedelta(hours=8))
UNITS = {'barometer': 'hPa', 'magnetometer': 'uT', 'accelerometer': 'm/s^2'}
SENSORS = {'Barometer.csv': 'barometer', 'Magnetometer.csv': 'magnetometer', 'Accelerometer.csv': 'accelerometer'}

# Provisional stop labels, derived only from the names of the movement recordings
# immediately before and after each stop in recording order. "route_confirmed_both_sides"
# means the preceding movement's destination and the following movement's origin agree.
# The four escalator-landing stops sit between two escalator movements and the two
# recording-order endpoints are bounded on one side only; all remain provisional.
STOP_LABELS = [
    ('Exit 5',                              'route_inferred_single_sided_start',   '',  'First stop; only the following movement (to the toilet) constrains it.'),
    ('Toilet',                              'route_confirmed_both_sides',          '',  ''),
    ('Y5',                                  'route_confirmed_both_sides',          '',  ''),
    ('Study room 11',                       'route_confirmed_both_sides',          '',  ''),
    ('Study room 10',                       'route_confirmed_both_sides',          '',  ''),
    ('Study room 9',                        'route_confirmed_both_sides',          '',  ''),
    ('Study room 8',                        'route_confirmed_both_sides',          '',  ''),
    ('Y5 (revisit)',                        'route_confirmed_both_sides',          '',  'Second visit to Y5 on the return leg.'),
    ('Toilet (revisit)',                    'route_confirmed_both_sides',          '',  'Second visit to the toilet.'),
    ('Exit 5 (revisit)',                    'route_confirmed_both_sides',          '',  'Second visit to the exit before heading to the canteen.'),
    ('Canteen',                             'route_confirmed_both_sides',          '',  ''),
    ('Escalator, upper landing (going down)','route_inferred_escalator_landing',   '',  'Between the canteen->escalator and escalator->Y4 movements; floor change, exact landing provisional.'),
    ('Escalator, lower landing (going down)','route_inferred_escalator_landing',   '',  'No movement recording separates this landing from the one above it.'),
    ('Y4',                                  'route_confirmed_both_sides',          '',  ''),
    ('Lecture theatre 1 B',                 'route_confirmed_both_sides',          '',  'English expansion of "lt 1b"; floor digit not independently confirmed.'),
    ('Lecture theatre 1 A',                 'route_confirmed_both_sides',          '',  'English expansion of "lt 1a".'),
    ('Exit 5 (revisit)',                    'route_confirmed_both_sides',          '',  ''),
    ('Exit gate (pintu keluar)',            'route_confirmed_both_sides',          '',  '"Pintu keluar" = exit gate/door.'),
    ('Exit 5 (revisit)',                    'route_confirmed_both_sides',          '',  'Return to the exit before the LT2 corridor.'),
    ('Lecture theatre 2 A',                 'route_confirmed_both_sides',          '',  'Preceding file label "Exig lt 2a" reads as Exit->LT 2A.'),
    ('Lecture theatre 2 B',                 'route_confirmed_both_sides',          '',  ''),
    ('Y4 (revisit)',                        'route_confirmed_both_sides',          '',  ''),
    ('Escalator, lower landing (going up)', 'route_inferred_escalator_landing',   '',  'Between Y4->escalator and escalator->canteen movements on the way back up.'),
    ('Escalator, upper landing (going up)', 'route_inferred_escalator_landing',   '',  'No movement recording separates this landing from the one below it.'),
    ('Canteen (revisit)',                   'route_confirmed_both_sides',          '',  ''),
    ('Exit 5 (final)',                      'route_inferred_single_sided_end',     '',  'Final stop; only the preceding movement (from the canteen) constrains it.'),
]

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
        w.writeheader()
        w.writerows(rows)

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def intervals(events):
    out = []
    active = None
    for e in events:
        if e['event'] == 'START':
            if active:
                raise ValueError('Consecutive START events')
            active = e
        elif e['event'] == 'PAUSE':
            if active is None:
                raise ValueError('PAUSE without START')
            out.append((active, e)); active = None
    if active:
        raise ValueError('Unclosed START event')
    if not out:
        raise ValueError('No acquisition intervals')
    return out

def gather_attachments(source):
    """Copy loose ZIPs and the WiGLE GZIP into raw/attachments byte-for-byte and return them."""
    attach = ROOT / 'raw' / 'attachments'
    attach.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    files = sorted([p for p in source.iterdir() if p.suffix in ('.zip', '.gz')], key=lambda p: p.name)
    if not files:
        # Fall back to the already-preserved copies (reproduce without the external folder).
        files = sorted([p for p in attach.iterdir() if p.suffix in ('.zip', '.gz')], key=lambda p: p.name)
        return [(p.name, p.read_bytes()) for p in files]
    out = []
    for p in files:
        data = p.read_bytes()
        preserved = attach / p.name
        if preserved.exists() and digest(preserved.read_bytes()) != digest(data):
            raise ValueError(f'Existing preserved attachment differs; refusing to overwrite {p.name}')
        if not preserved.exists():
            shutil.copy2(p, preserved)
        out.append((p.name, data))
    return out

def clean(source, wifi_audit=None):
    attachments = gather_attachments(source)
    audit = json.loads(wifi_audit.read_text()) if wifi_audit else {
        'timestamp_timezone': 'UTC_verified_by_official_WiGLE_CSV_v1.6_format',
        'timestamp_semantics': 'persisted_observation_location_time_not_radio_acquisition_time',
        'source_version_limitation': 'Upstream behavior audited separately; exact installed 2.111 source/binary not matched.',
        'clock_alignment_status': 'unverified_three_distinct_devices_no_offset_estimated',
        'complete_scan_snapshots': False,
        'sources': ['https://api.wigle.net/csvFormat-1_6.html']}
    dump(ROOT / 'wifi_timestamp_audit.json', audit)

    # First pass: read every ZIP's recording start so we can number stops/movements in time order.
    parsed = []
    wifi_ref = None
    hashes = []
    for name, payload in attachments:
        hashes.append({'file': str(Path('raw/attachments') / name), 'sha256': digest(payload), 'size_bytes': len(payload)})
        if name.endswith('.gz'):
            if wifi_ref:
                raise ValueError('Unexpected second Wi-Fi log')
            wifi_ref = (name, payload); continue
        if Path(name).name != name:
            raise ValueError('Unsafe archive path')
        with ZipFile(io.BytesIO(payload)) as z:
            if z.testzip():
                raise ValueError('Nested ZIP integrity failed: ' + name)
            is_bm = 'Barometer.csv' in z.namelist()
            events = list(csv.DictReader(io.StringIO(z.read('meta/time.csv').decode('utf-8-sig'))))
            ints = intervals(events)
            dev = dict(list(csv.reader(io.StringIO(z.read('meta/device.csv').decode('utf-8-sig'))))[1:])
            start = min(Decimal(a['system time']) for a, b in ints)
            end = max(Decimal(b['system time']) for a, b in ints)
            parsed.append({'name': name, 'payload': payload, 'is_bm': is_bm, 'events': events,
                           'ints': ints, 'dev': dev, 'start': start, 'end': end,
                           'file_label': name.split(' 2026-', 1)[0]})
    # Detect intervals that are exact re-exports of an interval already present in another
    # file (phyphox was paused, exported, then resumed and exported again). The signature is
    # the START/PAUSE system and experiment epochs; the canonical copy is the most atomic file
    # (fewest intervals), so a duplicated interval inside a resumed multi-interval recording is
    # superseded by the standalone single-interval export. Its readings are quarantined, never
    # silently dropped, so each distinct physical stop is counted exactly once.
    sig_occurrences = defaultdict(list)
    for r in parsed:
        r['interval_sigs'] = [(a['system time'], b['system time'], a['experiment time'], b['experiment time']) for a, b in r['ints']]
        for sig in r['interval_sigs']:
            sig_occurrences[sig].append(r)
    dup_canonical = {}  # (file_name, interval_index0) -> canonical file_name
    for sig, rs in sig_occurrences.items():
        if len({id(r) for r in rs}) > 1:
            canonical = min(rs, key=lambda r: (len(r['ints']), r['name']))
            for r in rs:
                if r is not canonical:
                    dup_canonical[(r['name'], r['interval_sigs'].index(sig))] = canonical['name']
    for r in parsed:
        r['dup_intervals'] = {k for k in range(len(r['ints'])) if (r['name'], k) in dup_canonical}
        r['canonical_for_dup'] = {k: dup_canonical[(r['name'], k)] for k in r['dup_intervals']}
        eff = [k for k in range(len(r['ints'])) if k not in r['dup_intervals']]
        r['eff_start'] = min(Decimal(r['ints'][k][0]['system time']) for k in eff)
        r['eff_end'] = max(Decimal(r['ints'][k][1]['system time']) for k in eff)
        r['eff_duration'] = sum(Decimal(r['ints'][k][1]['experiment time']) - Decimal(r['ints'][k][0]['experiment time']) for k in eff)

    parsed.sort(key=lambda r: (r['eff_start'], r['name']))

    bm = 0; acc = 0
    for r in parsed:
        if r['is_bm']:
            bm += 1; r['session_id'] = f'BM{bm:02}'
        else:
            acc += 1; r['session_id'] = f'ACC{acc:02}'
    session_of_file = {r['name']: r['session_id'] for r in parsed}

    # Provisional location table (stops only).
    locations = []
    for i, r in enumerate([p for p in parsed if p['is_bm']]):
        sid = r['session_id']; n = i + 1
        label, confidence, floor, note = STOP_LABELS[i]
        locations.append({'stop_id': sid, 'stop_number': n, 'original_file_label': r['file_label'],
                          'location_label': label, 'label_confidence': confidence,
                          'label_source': 'route_context_from_adjacent_movement_filenames',
                          'floor_candidate': floor, 'floor_status': 'not_determined_pending_indoor_map',
                          'x_m': '', 'y_m': '', 'notes': note})
    by_stop = {l['stop_id']: l for l in locations}

    sessions = []; all_samples = []; exclusions = []; quality = []; interval_output = []
    for r in parsed:
        sid = r['session_id']; name = r['name']; payload = r['payload']; ints = r['ints']; dev = r['dev']
        is_bm = r['is_bm']
        session = {'session_id': sid, 'kind': 'barometer_magnetometer_stop' if is_bm else 'accelerometer_movement',
                   'source_zip': name, 'source_sha256': digest(payload),
                   'device_model': dev.get('deviceModel', ''), 'device_brand': dev.get('deviceBrand', ''), 'app_version': dev.get('version', ''),
                   'start_epoch_s': str(r['eff_start']), 'end_epoch_s': str(r['eff_end']), 'start_utc': iso(r['eff_start']), 'end_utc': iso(r['eff_end']),
                   'start_hk': iso(r['eff_start'], HK), 'end_hk': iso(r['eff_end'], HK),
                   'recorded_duration_s': str(r['eff_duration']),
                   'interval_count': len(ints), 'duplicate_interval_count': len(r['dup_intervals']),
                   'original_file_label': r['file_label'],
                   'location_label': by_stop[sid]['location_label'] if is_bm else '',
                   'label_confidence': by_stop[sid]['label_confidence'] if is_bm else 'movement_route_label_from_filename',
                   'label_source': 'route_context_from_adjacent_movement_filenames' if is_bm else 'phyphox_filename',
                   'clock_status': 'device_wall_clock_not_independently_synchronized'}
        sessions.append(session)
        for k, (a, b) in enumerate(ints, 1):
            is_dup = (k - 1) in r['dup_intervals']
            interval_output.append({'session_id': sid, 'interval_id': k, 'experiment_start_s': a['experiment time'], 'experiment_end_s': b['experiment time'],
                                    'start_epoch_s': a['system time'], 'end_epoch_s': b['system time'], 'start_utc': iso(a['system time']), 'end_utc': iso(b['system time']),
                                    'clock_end_minus_start_mapping_s': str(Decimal(b['system time']) - Decimal(a['system time']) - (Decimal(b['experiment time']) - Decimal(a['experiment time']))),
                                    'interval_status': 'duplicate_reexport_superseded' if is_dup else 'accepted',
                                    'superseded_by_session_id': session_of_file[r['canonical_for_dup'][k - 1]] if is_dup else ''})
        with ZipFile(io.BytesIO(payload)) as z:
            for filename, sensor in SENSORS.items():
                if filename not in z.namelist():
                    continue
                rdr = csv.reader(io.StringIO(z.read(filename).decode('utf-8-sig'))); header = next(rdr)
                raw_rows = list(rdr); kept = []; excluded = Counter(); seen = set(); raw_values = []; nonmono = 0; prev = None
                for row_number, row in enumerate(raw_rows, 2):
                    reasons = []
                    selected_int = None
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
                        if t.is_finite():
                            selected_int = next(((a, b, k) for k, (a, b) in enumerate(ints, 1) if Decimal(a['experiment time']) <= t <= Decimal(b['experiment time'])), None)
                            if not selected_int:
                                reasons.append('outside_recorded_interval')
                        if len(values) > 1 and math.isfinite(values[1]):
                            raw_values.append(values[1])
                    except (ValueError, ArithmeticError, IndexError):
                        reasons.append('unparseable_numeric_row'); values = []; selected_int = None
                    if selected_int is not None and (selected_int[2] - 1) in r['dup_intervals']:
                        reasons.append('duplicate_reexport_interval_superseded_by_' + session_of_file[r['canonical_for_dup'][selected_int[2] - 1]])
                    key = tuple(row)
                    if key in seen:
                        reasons.append('exact_duplicate_same_time_and_values')
                    seen.add(key)
                    if reasons:
                        reasons = list(dict.fromkeys(reasons)); excluded.update(reasons)
                        exclusions.append({'session_id': sid, 'sensor': sensor, 'source_zip': name, 'source_csv': filename, 'source_row': row_number,
                                           'reasons': ';'.join(reasons), 'source_columns_json': json.dumps(header, ensure_ascii=False), 'source_values_json': json.dumps(row, ensure_ascii=False)})
                        continue
                    a, b, k = selected_int
                    if prev is not None and t <= prev:
                        nonmono += 1
                    prev = t
                    epoch = Decimal(a['system time']) + t - Decimal(a['experiment time'])
                    record = {'session_id': sid, 'sensor': sensor, 'source_zip': name, 'source_csv': filename, 'source_row': row_number, 'interval_id': k,
                              'relative_time_s': row[0], 'timestamp_epoch_s': str(epoch), 'timestamp_utc': iso(epoch), 'timestamp_hk': iso(epoch, HK),
                              'x': row[1], 'y': row[2] if len(row) > 2 else '', 'z': row[3] if len(row) > 3 else '', 'unit': UNITS[sensor],
                              'vector_magnitude': format(math.sqrt(sum(v * v for v in values[1:4])), '.12g') if len(values) == 4 else '',
                              'source_values_json': json.dumps(row, ensure_ascii=False), 'quality_flags': 'clock_not_independently_synchronized'}
                    kept.append(record); all_samples.append(record)
                kept.sort(key=lambda q: (Decimal(q['relative_time_s']), q['source_row']))
                vals = [float(q['x']) for q in kept]
                diffs = [float(Decimal(b['relative_time_s']) - Decimal(a['relative_time_s'])) for a, b in zip(kept, kept[1:]) if Decimal(b['relative_time_s']) > Decimal(a['relative_time_s'])]
                duration = float(session['recorded_duration_s']); span = float(Decimal(kept[-1]['relative_time_s']) - Decimal(kept[0]['relative_time_s'])) if len(kept) > 1 else 0
                flags = []
                if excluded:
                    flags.append('rows_quarantined')
                if duration and span < 0.8 * duration:
                    flags.append('samples_cover_less_than_80_percent_of_recorded_duration')
                if nonmono:
                    flags.append('nonmonotonic_source_order_sorted_in_clean_output')
                quality.append({'session_id': sid, 'sensor': sensor, 'source_rows': len(raw_rows), 'kept_rows': len(kept), 'excluded_rows': len(raw_rows) - len(kept),
                                'exclusion_reason_counts': json.dumps(dict(excluded), sort_keys=True), 'first_relative_time_s': kept[0]['relative_time_s'] if kept else '',
                                'last_relative_time_s': kept[-1]['relative_time_s'] if kept else '', 'observed_span_s': span, 'recorded_duration_s': duration,
                                'median_sample_interval_s': statistics.median(diffs) if diffs else '', 'raw_x_median': statistics.median(raw_values) if raw_values else '',
                                'clean_x_median': statistics.median(vals) if vals else '', 'clean_x_min': min(vals) if vals else '', 'clean_x_max': max(vals) if vals else '',
                                'magnitude_median': statistics.median(float(q['vector_magnitude']) for q in kept) if sensor != 'barometer' and kept else '',
                                'flags': ';'.join(flags)})

    all_samples.sort(key=lambda q: (Decimal(q['timestamp_epoch_s']), q['session_id'], q['sensor'], q['source_row']))
    emit(ROOT / 'sessions.csv', sessions)
    emit(ROOT / 'recording_intervals.csv', interval_output)
    emit(ROOT / 'locations_provisional.csv', locations)
    corrected = [{'location_number': l['stop_number'], 'stop_id': l['stop_id'], 'location_label': l['location_label'],
                  'label_confidence': l['label_confidence'], 'is_revisit': 'revisit' in l['location_label'].lower(),
                  'label_source': l['label_source'], 'notes': l['notes']} for l in locations]
    emit(ROOT / 'corrected_location_list.csv', corrected)
    emit(ROOT / 'sensor_samples.csv', all_samples)
    emit(ROOT / 'sensor_quality.csv', quality)
    emit(ROOT / 'excluded_sensor_rows.csv', exclusions,
         ['session_id', 'sensor', 'source_zip', 'source_csv', 'source_row', 'reasons', 'source_columns_json', 'source_values_json'])
    emit(ROOT / 'source_files.csv', hashes)
    for sensor in UNITS:
        emit(ROOT / 'sensors' / f'{sensor}.csv', [r for r in all_samples if r['sensor'] == sensor], list(all_samples[0]))

    edges, missing = make_edges(parsed, sessions, by_stop)
    emit(ROOT / 'accelerometer_edges.csv', edges)
    emit(ROOT / 'missing_movements.csv', missing)

    dup_rows = []
    for r in parsed:
        for k in sorted(r['dup_intervals']):
            canon_name = r['canonical_for_dup'][k]
            tag = 'duplicate_reexport_interval_superseded_by_' + session_of_file[canon_name]
            q = sum(1 for e in exclusions if e['source_zip'] == r['name'] and tag in e['reasons'])
            dup_rows.append({'session_id': r['session_id'], 'source_zip': r['name'], 'interval_id': k + 1,
                             'duplicate_of_session_id': session_of_file[canon_name], 'duplicate_of_source_zip': canon_name,
                             'rows_quarantined': q,
                             'note': 'phyphox resume re-export: this interval repeats the canonical standalone recording; its readings are quarantined to avoid double-counting one physical stop.'})
    emit(ROOT / 'duplicate_recordings.csv', dup_rows,
         ['session_id', 'source_zip', 'interval_id', 'duplicate_of_session_id', 'duplicate_of_source_zip', 'rows_quarantined', 'note'])

    wifi_summary = clean_wifi(wifi_ref, interval_output, audit)

    devices = sorted({(s['kind'], s['device_model']) for s in sessions})
    summary = {'dataset_version': 'v1_cleaned_route_labelled_provisional',
               'acquisition_date_hk': '2026-11-17', 'source': str(source),
               'sensor_zip_count': bm + acc, 'barometer_magnetometer_stops': bm, 'accelerometer_movements': acc,
               'wifi_logs': 1, 'devices': devices,
               'sensor_rows_source': sum(q['source_rows'] for q in quality), 'sensor_rows_clean': len(all_samples), 'sensor_rows_excluded': len(exclusions),
               'sensor_counts': dict(Counter(s['sensor'] for s in all_samples)),
               'exclusion_reason_counts': dict(Counter(reason for r in exclusions for reason in r['reasons'].split(';'))),
               'edge_timing_status_counts': dict(Counter(e['timing_status'] for e in edges)),
               'measured_movement_recordings': len(edges), 'unrecorded_consecutive_stop_gaps': len(missing),
               'duplicate_reexport_intervals': len(dup_rows), 'duplicate_reexport_detail': dup_rows,
               'wifi': wifi_summary,
               'pressure_clean_medians_hpa': {q['session_id']: q['clean_x_median'] for q in quality if q['sensor'] == 'barometer'},
               'stop_label_confidence_counts': dict(Counter(l['label_confidence'] for l in locations)),
               'uncertainties': [
                   'One stop was exported twice: poin 21-36-20 is an exact prefix of the resumed recording poin 21-37-27. The duplicated first interval of 21-37-27 is quarantined so the physical stop is counted once; 26 distinct stops remain.',
                   'Stop location labels are provisional, inferred only from adjacent movement filenames; they are not independently confirmed against an indoor map.',
                   'The four escalator-landing stops (BM12, BM13, BM23, BM24) sit between two escalator movements; their exact landing/floor is provisional.',
                   'Floor numbers are not assigned; no marked indoor plan or map coordinates are available yet.',
                   'Device clocks of the two iPhones and the Samsung were not independently synchronized.',
                   'WiFi UTC format is verified; the stored FirstSeen time is a persisted observation time, not radio acquisition time; selective persistence prevents complete fingerprints.',
                   'Exact installed WiGLE 2.111 source/binary was not matched to the inspected upstream source.',
                   'No smoothing, resampling, numeric distance, step counts, calibration or model training were performed.']}
    dump(ROOT / 'summary.json', summary)
    make_svg(sessions, quality, edges, by_stop)
    write_readme(summary, locations)
    validate()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary

def make_edges(parsed, sessions, locations):
    """Assign each movement to the stop immediately before and after it in recording order."""
    order = sorted(parsed, key=lambda r: (r['eff_start'], r['name']))
    sess = {s['session_id']: s for s in sessions}
    stop_ids = [r['session_id'] for r in order if r['is_bm']]
    edges = []
    for idx, r in enumerate(order):
        if r['is_bm']:
            continue
        before = next((order[j] for j in range(idx - 1, -1, -1) if order[j]['is_bm']), None)
        after = next((order[j] for j in range(idx + 1, len(order)) if order[j]['is_bm']), None)
        if before is None or after is None:
            raise ValueError('Movement without a bounding stop on both sides: ' + r['name'])
        a_id = before['session_id']; b_id = after['session_id']
        s = sess[r['session_id']]
        start = Decimal(s['start_epoch_s']); end = Decimal(s['end_epoch_s'])
        left = Decimal(sess[a_id]['end_epoch_s']); right = Decimal(sess[b_id]['start_epoch_s'])
        valid = left <= start <= end <= right
        status = 'between_endpoint_stop_windows' if valid else 'overlaps_or_outside_endpoint_windows'
        edges.append({'acc_session_id': r['session_id'], 'original_file_label': r['file_label'],
                      'from_stop_id': a_id, 'to_stop_id': b_id,
                      'from_location': locations[a_id]['location_label'], 'to_location': locations[b_id]['location_label'],
                      'start_hk': s['start_hk'], 'end_hk': s['end_hk'], 'start_epoch_s': s['start_epoch_s'], 'end_epoch_s': s['end_epoch_s'],
                      'timing_status': status, 'seconds_after_from_stop_end': str(start - left), 'seconds_before_to_stop_start': str(right - end),
                      'endpoint_label_status': 'provisional_route_order_and_filename', 'is_synthetic': False, 'notes': ''})
    # Consecutive stop pairs with no movement recording between them (the escalator double-landings).
    recorded_pairs = {(e['from_stop_id'], e['to_stop_id']) for e in edges}
    missing = []
    for a_id, b_id in zip(stop_ids, stop_ids[1:]):
        if (a_id, b_id) not in recorded_pairs:
            missing.append({'from_stop_id': a_id, 'to_stop_id': b_id,
                            'from_location': locations[a_id]['location_label'], 'to_location': locations[b_id]['location_label'],
                            'status': 'no_accelerometer_recording_between_consecutive_stops',
                            'notes': 'Two escalator landings recorded back-to-back without a walk recording between them; do not fabricate a transition.'})
    return edges, missing

def clean_wifi(wifi_ref, recording_intervals, audit):
    if not wifi_ref:
        raise ValueError('Wi-Fi log missing')
    name, payload = wifi_ref
    text = gzip.decompress(payload).decode('utf-8-sig')
    metadata, table = text.split('\n', 1)
    (ROOT / 'raw' / 'wifi_decompressed.csv').write_text(text, encoding='utf-8')
    (ROOT / 'wifi').mkdir(exist_ok=True)
    (ROOT / 'wifi' / 'export_metadata.txt').write_text(metadata + '\n', encoding='utf-8')
    reader = csv.DictReader(io.StringIO(table)); source_fields = reader.fieldnames
    obs = []; excluded = []; nonwifi = []; seen = set(); reason_counts = Counter()
    for source_row, row in enumerate(reader, 3):
        raw = json.dumps(row, ensure_ascii=False, sort_keys=True)
        common = {'source_log': name, 'source_row': source_row, 'source_values_json': raw}
        if row.get('Type') != 'WIFI':
            nonwifi.append({**common, **row}); continue
        reasons = []
        key = tuple(row.get(k) for k in source_fields)
        if key in seen:
            reasons.append('exact_duplicate_export_row')
        seen.add(key)
        try:
            dt = datetime.strptime(row['FirstSeen'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if not math.isfinite(float(row['RSSI'])):
                reasons.append('nonfinite_rssi')
        except (ValueError, TypeError, KeyError):
            reasons.append('unparseable_timestamp_or_rssi'); dt = None
        if reasons:
            excluded.append({**common, 'reasons': ';'.join(reasons)}); reason_counts.update(reasons); continue
        obs.append({'wifi_observation_id': f'W{source_row:06}', 'source_log': name, 'source_row': source_row,
                    **row, 'observation_epoch_s': str(int(dt.timestamp())), 'observation_time_utc': dt.isoformat(),
                    'observation_time_hk': dt.astimezone(HK).isoformat(), 'timestamp_interpretation': 'UTC verified by official WiGLE CSV v1.6 specification',
                    'timestamp_semantics': 'persisted_observation_location_time',
                    'quality_flags': 'radio_acquisition_time_unavailable;cross_device_clock_alignment_unverified;selectively_persisted_not_complete_scan;gps_not_indoor_ground_truth',
                    'clock_status': 'Samsung wall clock not independently synchronized to iPhones',
                    'source_values_json': raw})
    ints = [i for i in recording_intervals if i['session_id'].startswith('BM')]
    associations = []; orphans = []; counts = Counter(); seconds = defaultdict(set)
    earliest = min(Decimal(i['start_epoch_s']) for i in ints); latest = max(Decimal(i['end_epoch_s']) for i in ints)
    for r in obs:
        t = Decimal(r['observation_epoch_s'])
        matches = [i for i in ints if Decimal(i['start_epoch_s']) <= t <= Decimal(i['end_epoch_s'])]
        for i in matches:
            associations.append({'wifi_observation_id': r['wifi_observation_id'], 'session_id': i['session_id'], 'interval_id': i['interval_id'],
                                 'observation_epoch_s': str(t), 'observation_time_hk': r['observation_time_hk'],
                                 'association_status': 'provisional_FirstSeen_within_stop_recording_interval',
                                 'limitations': 'Not proof of fresh scan, complete fingerprint, synchronized clocks, or known phone position.'})
            counts[i['session_id']] += 1; seconds[i['session_id']].add(t)
        if not matches:
            orphans.append({'wifi_observation_id': r['wifi_observation_id'], 'observation_epoch_s': str(t),
                            'reason': 'outside_stop_session_time_span' if not earliest <= t <= latest else 'between_stop_recording_windows',
                            'notes': 'Retained observation; not assigned by nearest-neighbor or interpolation.'})
    coverage = [{'session_id': i['session_id'], 'interval_id': i['interval_id'], 'provisional_wifi_rows': counts[i['session_id']],
                 'distinct_FirstSeen_seconds': len(seconds[i['session_id']]),
                 'coverage_status': 'no_FirstSeen_rows_in_exact_window' if not counts[i['session_id']] else 'FirstSeen_rows_present_not_verified_scan_coverage'} for i in ints]
    emit(ROOT / 'wifi' / 'observations.csv', obs)
    emit(ROOT / 'wifi' / 'excluded_rows.csv', excluded, ['source_log', 'source_row', 'source_values_json', 'reasons'])
    emit(ROOT / 'wifi' / 'non_wifi_rows.csv', nonwifi)
    emit(ROOT / 'wifi' / 'stop_associations_provisional.csv', associations)
    emit(ROOT / 'wifi' / 'unassigned_observations.csv', orphans)
    emit(ROOT / 'wifi' / 'stop_coverage_provisional.csv', coverage)
    write_wifi_audit_md(name, metadata, len(obs), len(nonwifi), len(excluded))
    return {'source_log': name, 'source_data_rows': len(obs) + len(excluded) + len(nonwifi), 'wifi_rows_clean': len(obs), 'wifi_rows_excluded': len(excluded),
            'non_wifi_rows_separated': len(nonwifi), 'wifi_exclusion_reasons': dict(reason_counts), 'unique_bssids': len({r['MAC'] for r in obs}),
            'provisionally_associated_rows': len(associations), 'stops_with_candidate_rows': sum(bool(r['provisional_wifi_rows']) for r in coverage),
            'unassigned_rows': len(orphans), 'unassigned_reason_counts': dict(Counter(r['reason'] for r in orphans)),
            'zero_row_stops': [r['session_id'] for r in coverage if not r['provisional_wifi_rows']],
            'timestamp_audit_file': 'wifi_timestamp_audit.json', 'first_seen_min': min(r['FirstSeen'] for r in obs), 'first_seen_max': max(r['FirstSeen'] for r in obs)}

def write_wifi_audit_md(name, metadata, obs, nonwifi, excluded):
    (ROOT / 'wifi' / 'AUDIT.md').write_text(f'''# Wi-Fi export audit — 2026-11-17

Source log: `{name}`
Export header: `{metadata}`

- {obs} accepted WIFI observations, {nonwifi} non-WIFI rows (LTE) separated into `non_wifi_rows.csv`, {excluded} excluded.
- `FirstSeen` is interpreted as **UTC**, verified by the official WiGLE CSV v1.6 format. Converting to Hong Kong time adds eight hours; this is a display conversion, not a phone-clock adjustment.
- `FirstSeen` records a persisted observation location time, not the radio acquisition time. The exact installed WiGLE 2.111 source/binary was not matched to inspected upstream source.
- Observations are selectively persisted (improved-signal updates), so they are **not** complete fresh scans. Do not fill unobserved access points with -100 dBm or any assumed absence value.
- GPS latitude/longitude/accuracy are original WiGLE metadata only, **not** indoor ground truth or map coordinates.
- Stop association uses exact containment of the stored FirstSeen second inside a recorded stop interval. No nearest-time assignment or interpolation is used.
''', encoding='utf-8')

def make_svg(sessions, quality, edges, locations):
    stops = [s for s in sessions if s['session_id'].startswith('BM')]
    pressures = {q['session_id']: q['clean_x_median'] for q in quality if q['sensor'] == 'barometer'}
    mags = {q['session_id']: q['magnitude_median'] for q in quality if q['sensor'] == 'magnetometer'}
    lo = min(float(s['start_epoch_s']) for s in sessions); hi = max(float(s['end_epoch_s']) for s in sessions)
    width = 1200; height = 700; left = 80; right = 1160
    x = lambda t: left + (float(t) - lo) / (hi - lo) * (right - left)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#18212b} .small{font-size:11px}.axis{stroke:#bac2cc;stroke-width:1}</style>',
           '<text x="40" y="30" font-size="22">GE2340 — measured stops and movement recordings (17 Nov 2026)</text>',
           '<text x="40" y="52" font-size="13">Hong Kong time. Stop labels are provisional (route-inferred); device clocks were not independently synchronized.</text>']
    def panel(values, top, bottom, title, color):
        mn = min(values.values()); mx = max(values.values()); pad = max((mx - mn) * .1, .001); mn -= pad; mx += pad
        y = lambda v: bottom - (v - mn) / (mx - mn) * (bottom - top)
        out.append(f'<text x="40" y="{top-12}" font-size="14">{title}</text>')
        for j in range(4):
            v = mn + (mx - mn) * j / 3; yy = y(v)
            out.append(f'<line x1="{left}" y1="{yy}" x2="{right}" y2="{yy}" class="axis"/><text x="5" y="{yy+4}" class="small">{v:.2f}</text>')
        for s in stops:
            xx = x(s['start_epoch_s']); yy = y(values[s['session_id']]); lab = s['session_id']
            out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="4" fill="{color}"><title>{lab}: {values[lab]:.5f}; {html.escape(locations[lab]["location_label"])}</title></circle>')
            out.append(f'<text x="{xx:.2f}" y="{yy-8:.2f}" class="small" text-anchor="middle">{lab[2:]}</text>')
    panel(pressures, 105, 265, 'Pressure median per stop (hPa); separate dots, no invented readings between stops', '#126782')
    panel(mags, 330, 465, 'Magnetic field magnitude median per stop (µT)', '#7654a3')
    out.append('<text x="40" y="505" font-size="14">Recorded intervals: teal = stationary barometer/magnetometer stop; orange = accelerometer movement</text>')
    for s in sessions:
        is_bm = s['session_id'].startswith('BM'); yy = 530 if is_bm else 570; xx = x(s['start_epoch_s']); ww = max(x(s['end_epoch_s']) - xx, 2)
        out.append(f'<rect x="{xx:.2f}" y="{yy}" width="{ww:.2f}" height="12" fill="{"#126782" if is_bm else "#d97915"}"><title>{s["session_id"]} {html.escape(s["original_file_label"])}</title></rect>')
        out.append(f'<text x="{xx:.2f}" y="{yy-4}" class="small">{s["session_id"][2:] if is_bm else html.escape(s["original_file_label"].split()[0])}</text>')
    for j in range(9):
        t = lo + (hi - lo) * j / 8; xx = x(t)
        out.append(f'<line x1="{xx}" y1="595" x2="{xx}" y2="601" class="axis"/><text x="{xx}" y="617" class="small" text-anchor="middle">{datetime.fromtimestamp(t,HK).strftime("%H:%M:%S")}</text>')
    out.extend(['<text x="40" y="650" font-size="13">The walk revisits Y5, the toilet, the exit, the canteen and Y4; pressure dips across the escalator descent and recovers on the way up.</text>',
                '<text x="40" y="673" font-size="13">Two escalator double-landings (BM12-BM13, BM23-BM24) have no walk recording between them; see missing_movements.csv.</text>', '</svg>'])
    (ROOT / 'diagnostic_timeline.svg').write_text('\n'.join(out), encoding='utf-8')

def write_readme(s, locations):
    p = s['pressure_clean_medians_hpa']; w = s['wifi']
    text = f'''# GE2340 cleaned acquisition, 17 November 2026 — v1

The exported files are readable and internally coherent enough for analysis. This is a cleaned acquisition with **provisional, route-inferred** location labels, not an independently map-verified or model-tested training set.

This is the second GE2340 acquisition. Unlike the 14 November set, the 23 movement recordings were already labelled by their filenames (e.g. `Sr11 10` = study room 11 → study room 10), the stops form one continuous walk, there is no numbering typo, and no synthetic/duplicated connector was added. Every measurement here is real.

## Evidence and scope

- {s['barometer_magnetometer_stops']} actual barometer/magnetometer stop recordings (`poin ...zip`), {s['accelerometer_movements']} actual accelerometer movement recordings (named by route), and one WiGLE export. All {s['sensor_zip_count']} sensor ZIPs pass integrity checks.
- Stops are numbered **BM01–BM26** in recording order. Each stop also carries a provisional location label inferred only from the names of the movement recordings immediately before and after it. {s['stop_label_confidence_counts'].get('route_confirmed_both_sides',0)} stop labels are confirmed on both sides (the preceding movement's destination equals the following movement's origin); the rest are escalator landings or the two single-sided route endpoints.
- The walk is a loop that revisits Y5, the toilet, Exit 5, the canteen and Y4. `corrected_location_list.csv` lists all 26 ordered checkpoints; `locations_provisional.csv` carries the per-stop confidence and notes.
- Three distinct phones: the barometer/magnetometer stops use one iPhone, the accelerometer movements use a different iPhone, and Wi-Fi uses a Samsung. Their wall clocks were not independently synchronized.
- No smoothing, resampling, numeric distance estimation, step counting, calibration or model training was performed. Raw archives are preserved byte-identically in `raw/attachments/`.

## What the escalator readings show

Pressure medians across the descent are BM11 canteen **{p.get('BM11','')} hPa**, BM12 upper landing **{p.get('BM12','')}**, BM13 lower landing **{p.get('BM13','')}**, BM14 Y4 **{p.get('BM14','')}**. On the way back up, BM22 Y4 **{p.get('BM22','')}**, BM23 lower landing **{p.get('BM23','')}**, BM24 upper landing **{p.get('BM24','')}**, BM25 canteen **{p.get('BM25','')}**. The pressure change across the escalator supports a real floor change; it does not independently prove exact floor identities. Floor numbers are left blank pending a marked indoor map.

## Cleaning rules and row accounting

- Recorded START/PAUSE intervals map experiment-relative seconds to device wall-clock epoch, UTC and HK. Every event is retained in `recording_intervals.csv`.
- Negative experiment times, outside-interval samples, nonfinite/unparseable values, and exact duplicate time-and-value rows are quarantined in `excluded_sensor_rows.csv` with the original values and source row. Repeated values at different timestamps are retained.
- Input sensor readings: **{s['sensor_rows_source']:,}**; accepted: **{s['sensor_rows_clean']:,}**; quarantined: **{s['sensor_rows_excluded']:,}**. Readings are never silently discarded. `sensor_quality.csv` includes raw and cleaned medians and per-sensor time coverage.
- Accepted counts by sensor: {s['sensor_counts']}.
- Each barometer file begins with one negative-experiment-time reading (quarantined); the remaining pressure readings span the recording. Magnetometer runs at roughly 100 Hz. Accelerometer magnitude includes gravity; it is not linear acceleration, distance, or a step count. Magnetic vector axes depend on phone orientation.

## Wi-Fi limitations

The WiGLE CSV has {w['source_data_rows']:,} original data rows; {w['wifi_rows_clean']:,} accepted Wi-Fi observations and {w['non_wifi_rows_separated']} non-Wi-Fi (LTE) rows separated. Original metadata and column values are retained. See `wifi/AUDIT.md` and `wifi_timestamp_audit.json`.

`FirstSeen` is retained under its original name and interpreted as **UTC** (official WiGLE v1.6 format); Hong Kong time adds eight hours. It is a persisted observation time, not radio acquisition time. These are selectively persisted observations, not complete fresh scans; do not fill missing access points with -100 dBm or any assumed absence value. GPS coordinates are original metadata only, **not indoor ground truth**.

The provisional association uses exact containment of the stored FirstSeen second inside a recorded stop interval, with no nearest-time assignment or interpolation. {w['provisionally_associated_rows']} rows are provisionally associated across {w['stops_with_candidate_rows']} stops; {w['unassigned_rows']:,} remain unassigned. Stops with no exported FirstSeen row in their exact window: **{', '.join(w['zero_row_stops']) if w['zero_row_stops'] else 'none'}**. An empty window is not proof the phone saw no access points; a present row is not proof of a complete scan.

## Files

- `sessions.csv`: source, device, actual recorded times and provisional labels for each ZIP.
- `sensor_samples.csv`, `sensors/*.csv`: accepted samples with units, original relative times, UTC/HK timestamps, source values and vector magnitudes.
- `sensor_quality.csv`, `excluded_sensor_rows.csv`: per-sensor checks and full quarantine records.
- `locations_provisional.csv`, `corrected_location_list.csv`: the 26 ordered stops, route-inferred labels and confidence.
- `accelerometer_edges.csv`, `missing_movements.csv`: the 23 measured movements with their bounding stops and timing checks, and the 2 consecutive-stop gaps with no walk recording.
- `wifi/observations.csv`, `stop_associations_provisional.csv`, `stop_coverage_provisional.csv`, `unassigned_observations.csv`, `non_wifi_rows.csv`, `excluded_rows.csv`, `AUDIT.md`: Wi-Fi cleaning and provisional exact-window matches.
- `diagnostic_timeline.svg`: self-contained plot of measured pressure, magnetic magnitude and recording intervals.
- `summary.json`, `validation.json`, `source_files.csv`: machine-readable counts and integrity evidence.
- `features/`: first-pass descriptive statistics (see `features/FEATURES_EXPLAINED.md`).
- `raw/`: byte-identical source ZIPs/GZIP (`raw/attachments/`) and the decompressed Wi-Fi CSV.

## Reproduce and verify

From this directory:

```bash
python3 clean.py --source "../../../../Data (17-11)"
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
```

The first run copies the loose ZIPs and the WiGLE GZIP into `raw/attachments/` byte-for-byte; later runs can reproduce from those preserved copies without the external folder. Validation checks attachment hashes, row accounting, finite values and intervals, Wi-Fi associations, the 26/23 recording split, movement-to-stop adjacency and that no synthetic rows exist. It does not certify location ground truth, device clock synchronization, or Wi-Fi scan completeness.

## Remaining work

Confirm stop labels and floor numbers against a marked indoor plan; add map coordinates and distances; decide whether complete Wi-Fi logging and independently synchronized repeat visits are needed; then choose a baseline and independent evaluation visits. No training or train/test slicing has happened. Preserve one visit as one acquisition unit: adjacent samples from one stop are not independent train/test visits.

<!-- V1_FEATURES -->
'''
    (ROOT / 'README.md').write_text(text, encoding='utf-8')

def load(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def validate():
    s = json.loads((ROOT / 'summary.json').read_text()); checks = []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)
    files = load(ROOT / 'source_files.csv')
    check('all_attachment_sha256', all(digest((ROOT / r['file']).read_bytes()) == r['sha256'] for r in files))
    ss = load(ROOT / 'sessions.csv'); ints = load(ROOT / 'recording_intervals.csv'); samples = load(ROOT / 'sensor_samples.csv'); excluded = load(ROOT / 'excluded_sensor_rows.csv'); quality = load(ROOT / 'sensor_quality.csv')
    check('49_real_sensor_sessions', len(ss) == 49 and sum(r['kind'] == 'barometer_magnetometer_stop' for r in ss) == 26 and sum(r['kind'] == 'accelerometer_movement' for r in ss) == 23)
    check('sensor_reading_row_accounting', s['sensor_rows_source'] == len(samples) + len(excluded) == sum(int(q['source_rows']) for q in quality))
    expected = {(r['session_id'], f) for r in ss for f in (['Barometer.csv', 'Magnetometer.csv'] if r['kind'] == 'barometer_magnetometer_stop' else ['Accelerometer.csv'])}
    actual = Counter((r['session_id'], r['source_csv']) for r in samples + excluded)
    check('all_sensor_csvs_accounted', set(actual) == expected and len(expected) == 75)
    # Re-read each preserved ZIP and prove every original row is accounted for exactly once with unchanged values.
    by_zip = {r['session_id']: r['source_zip'] for r in ss}
    original = {}
    for sid, zipname in by_zip.items():
        with ZipFile(ROOT / 'raw' / 'attachments' / zipname) as inner:
            check('zip_integrity_' + sid, inner.testzip() is None)
            for f in SENSORS:
                if f in inner.namelist():
                    rows = list(csv.reader(io.StringIO(inner.read(f).decode('utf-8-sig'))))[1:]
                    original[(sid, f)] = rows
    accounted = defaultdict(list)
    for r in samples + excluded:
        key = (r['session_id'], r['source_csv']); rn = int(r['source_row'])
        if json.loads(r['source_values_json']) != original[key][rn - 2]:
            raise AssertionError('Source value mismatch at ' + str(key) + ' row ' + str(rn))
        accounted[key].append(rn)
    check('every_original_sensor_row_exactly_once', all(sorted(accounted[k]) == list(range(2, len(v) + 2)) for k, v in original.items()))
    ib = {(r['session_id'], str(r['interval_id'])): r for r in ints}
    valid = True
    for r in samples:
        i = ib[(r['session_id'], r['interval_id'])]; t = Decimal(r['relative_time_s']); ep = Decimal(r['timestamp_epoch_s'])
        valid &= t >= 0 and Decimal(i['experiment_start_s']) <= t <= Decimal(i['experiment_end_s'])
        valid &= ep == Decimal(i['start_epoch_s']) + t - Decimal(i['experiment_start_s'])
        valid &= all(math.isfinite(float(r[k])) for k in ['x', 'y', 'z'] if r[k] != '')
    check('accepted_samples_finite_in_interval_and_exact_epoch_mapping', valid)
    check('per_sensor_partitions', sum(len(load(ROOT / 'sensors' / f'{sensor}.csv')) for sensor in UNITS) == len(samples))
    check('all_nonnegative_sensor_times', all(Decimal(r['relative_time_s']) >= 0 for r in samples))
    loc = load(ROOT / 'locations_provisional.csv')
    check('26_stops_numbered_in_order', [r['stop_id'] for r in loc] == [f'BM{n:02}' for n in range(1, 27)])
    corrected = load(ROOT / 'corrected_location_list.csv')
    check('corrected_list_1_to_26', [int(r['location_number']) for r in corrected] == list(range(1, 27)))
    edges = load(ROOT / 'accelerometer_edges.csv')
    check('23_real_movements_no_synthetic', len(edges) == 23 and {r['acc_session_id'] for r in edges} == {r['session_id'] for r in ss if r['kind'] == 'accelerometer_movement'} and all(r['is_synthetic'] == 'False' for r in edges))
    order = [r['session_id'] for r in sorted(ss, key=lambda q: Decimal(q['start_epoch_s'])) if r['session_id'].startswith('BM')]
    pos = {sid: n for n, sid in enumerate(order)}
    check('movements_bound_adjacent_stops', all(pos[e['to_stop_id']] == pos[e['from_stop_id']] + 1 for e in edges))
    missing = load(ROOT / 'missing_movements.csv')
    check('missing_gaps_are_unrecorded_adjacent_pairs', all(pos[m['to_stop_id']] == pos[m['from_stop_id']] + 1 for m in missing) and len(edges) + len(missing) == 25)
    dups = load(ROOT / 'duplicate_recordings.csv')
    dup_excluded = [e for e in excluded if 'duplicate_reexport_interval' in e['reasons']]
    dup_intervals = {(i['session_id'], i['interval_id']) for i in ints if i['interval_status'] == 'duplicate_reexport_superseded'}
    check('duplicate_reexport_intervals_quarantined_not_double_counted',
          len(dups) == s['duplicate_reexport_intervals'] and sum(int(d['rows_quarantined']) for d in dups) == len(dup_excluded)
          and not any((r['session_id'], r['interval_id']) in dup_intervals for r in samples))
    obs = load(ROOT / 'wifi' / 'observations.csv'); assoc = load(ROOT / 'wifi' / 'stop_associations_provisional.csv'); orphan = load(ROOT / 'wifi' / 'unassigned_observations.csv'); others = load(ROOT / 'wifi' / 'non_wifi_rows.csv'); wx = load(ROOT / 'wifi' / 'excluded_rows.csv')
    check('wifi_input_row_accounting', len(obs) + len(others) + len(wx) == s['wifi']['source_data_rows'])
    wi = {r['wifi_observation_id']: r for r in obs}
    check('wifi_association_exact_interval_containment', all(Decimal(ib[(r['session_id'], r['interval_id'])]['start_epoch_s']) <= Decimal(wi[r['wifi_observation_id']]['observation_epoch_s']) <= Decimal(ib[(r['session_id'], r['interval_id'])]['end_epoch_s']) for r in assoc))
    matched = {r['wifi_observation_id'] for r in assoc}; unmatched = {r['wifi_observation_id'] for r in orphan}
    check('wifi_every_observation_matched_or_unassigned', not matched & unmatched and matched | unmatched == set(wi))
    check('wifi_all_associations_explicitly_provisional', all(r['association_status'].startswith('provisional_') for r in assoc))
    dump(ROOT / 'validation.json', {'passed': True, 'check_count': len(checks), 'checks': checks})
    return checks

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--wifi-audit', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if args.validate_only:
        result = validate(); print(f'{len(result)} validation checks passed')
    else:
        audit = args.wifi_audit
        if audit is None and (ROOT / 'wifi_timestamp_audit.json').exists():
            audit = ROOT / 'wifi_timestamp_audit.json'
        clean(args.source, audit)
