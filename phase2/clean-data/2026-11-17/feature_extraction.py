#!/usr/bin/env python3
"""Summarize the cleaned 2026-11-17 GE2340 readings; preserve all acquisition tables.

Descriptive statistics only: no two-second slicing, interpolation, double integration,
distances, step counts, calibration or model training. Unlike the 2026-11-14 pipeline
there is no synthetic/copied connector, so movement features come straight from the 23
measured accelerometer recordings.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'features'
INPUTS = ['sensor_samples.csv', 'sensors/barometer.csv', 'sensors/magnetometer.csv', 'sensors/accelerometer.csv',
          'sessions.csv', 'sensor_quality.csv', 'recording_intervals.csv', 'locations_provisional.csv', 'corrected_location_list.csv',
          'accelerometer_edges.csv', 'wifi/observations.csv', 'wifi/stop_associations_provisional.csv', 'excluded_sensor_rows.csv']

def read(path):
    with (ROOT / path).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def emit(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}

def stats(values, prefix):
    values = list(values)
    return {prefix + '_mean': statistics.mean(values), prefix + '_median': statistics.median(values),
            prefix + '_sample_sd': statistics.stdev(values) if len(values) > 1 else '',
            prefix + '_min': min(values), prefix + '_max': max(values), prefix + '_range': max(values) - min(values)}

def movement_stats(rows):
    values = [float(r['vector_magnitude']) for r in rows]; median = statistics.median(values)
    out = {'sample_count': len(rows), 'observed_sample_span_s': float(rows[-1]['relative_time_s']) - float(rows[0]['relative_time_s'])}
    for axis in ['x', 'y', 'z']:
        v = [float(r[axis]) for r in rows]
        out[f'{axis}_mean_m_s2'] = statistics.mean(v)
        out[f'{axis}_sample_sd_m_s2'] = statistics.stdev(v) if len(v) > 1 else ''
    out.update(stats(values, 'magnitude_m_s2'))
    out['magnitude_deviation_from_segment_median_rms_m_s2'] = math.sqrt(statistics.mean((v - median) ** 2 for v in values))
    return out

def preserve_review_fields(new_rows, existing_rows):
    """Keep human review entries across reruns without applying them as confirmed labels."""
    old = {r['raw_recording_id']: r for r in existing_rows}
    if len(old) != len(existing_rows):
        raise ValueError('Duplicate recording IDs in existing review table')
    expected = {r['raw_recording_id'] for r in new_rows}
    if set(old) - expected:
        raise ValueError('Existing review table has unknown acquisition IDs')
    out = []
    for row in new_rows:
        previous = old.get(row['raw_recording_id'])
        if previous:
            if previous.get('source_zip') != row['source_zip']:
                raise ValueError('Review source ZIP changed for ' + row['raw_recording_id'])
            if previous.get('source_zip_sha256') and previous['source_zip_sha256'] != row['source_zip_sha256']:
                raise ValueError('Review source hash changed for ' + row['raw_recording_id'])
            row = {**row, **{k: previous.get(k, '') for k in row if k.startswith('review_')}}
        out.append(row)
    return out

def build():
    before = hashes(); OUT.mkdir(exist_ok=True)
    sessions = {r['session_id']: r for r in read('sessions.csv')}
    locations = {r['stop_id']: r for r in read('locations_provisional.csv')}
    quality = {(r['session_id'], r['sensor']): r for r in read('sensor_quality.csv')}
    sensors = defaultdict(list)
    for r in read('sensor_samples.csv'):
        sensors[(r['session_id'], r['sensor'])].append(r)
    wifi = {r['wifi_observation_id']: r for r in read('wifi/observations.csv')}
    matches = read('wifi/stop_associations_provisional.csv')
    stop_wifi = defaultdict(list); wifi_groups = defaultdict(list)
    for m in matches:
        obs = wifi[m['wifi_observation_id']]
        stop_wifi[m['session_id']].append(obs)
        wifi_groups[(m['session_id'], obs['MAC'])].append(obs)
    stops = []
    for sid, session in sessions.items():
        if not sid.startswith('BM'):
            continue
        location = locations[sid]; baro = sensors[(sid, 'barometer')]; mag = sensors[(sid, 'magnetometer')]
        row = {'stop_id': sid, 'source_zip': session['source_zip'], 'start_hk': session['start_hk'], 'end_hk': session['end_hk'],
               'recorded_duration_s': session['recorded_duration_s'],
               'location_number': location['stop_number'], 'candidate_location_name': location['location_label'],
               'label_confidence': location['label_confidence'], 'label_source': location['label_source'],
               'floor_candidate': location['floor_candidate'], 'floor_status': location['floor_status'],
               'confidence_status': 'descriptive_statistics_only_location_and_cross_device_alignment_unverified',
               'barometer_sample_count': len(baro), 'magnetometer_sample_count': len(mag)}
        row.update(stats((float(r['x']) for r in baro), 'pressure_hpa'))
        for axis in ['x', 'y', 'z']:
            values = [float(r[axis]) for r in mag]
            row[f'magnetic_{axis}_mean_ut'] = statistics.mean(values)
            row[f'magnetic_{axis}_sample_sd_ut'] = statistics.stdev(values)
        row.update(stats((float(r['vector_magnitude']) for r in mag), 'magnetic_magnitude_ut'))
        for sensor in ['barometer', 'magnetometer']:
            q = quality[(sid, sensor)]
            row[sensor + '_first_relative_time_s'] = q['first_relative_time_s']
            row[sensor + '_last_relative_time_s'] = q['last_relative_time_s']
            row[sensor + '_observed_span_s'] = q['observed_span_s']
            row[sensor + '_time_span_fraction_of_recording'] = float(q['observed_span_s']) / float(q['recorded_duration_s']) if float(q['recorded_duration_s']) else ''
            row[sensor + '_qc_flags'] = q['flags']
        obs = stop_wifi[sid]
        row.update({'wifi_candidate_observation_count': len(obs),
                    'wifi_candidate_distinct_bssid_count': len({r['MAC'] for r in obs}),
                    'wifi_candidate_distinct_stored_timestamp_seconds': len({r['observation_epoch_s'] for r in obs}),
                    'wifi_association_status': 'provisional_persisted_location_time_not_fresh_scan_or_complete_fingerprint',
                    'clock_status': session['clock_status']})
        stops.append(row)
    emit(OUT / 'stop_features.csv', stops)
    groups = []
    for (sid, mac), rows in sorted(wifi_groups.items()):
        values = [float(r['RSSI']) for r in rows]
        groups.append({'stop_id': sid, 'bssid': mac, 'candidate_observation_count': len(rows),
                       'rssi_median_dbm': statistics.median(values), 'rssi_mean_dbm': statistics.mean(values),
                       'distinct_stored_timestamp_seconds': len({r['observation_epoch_s'] for r in rows}),
                       'first_observation_time_utc': min(r['observation_time_utc'] for r in rows),
                       'last_observation_time_utc': max(r['observation_time_utc'] for r in rows),
                       'source_observation_ids_json': json.dumps([r['wifi_observation_id'] for r in rows]),
                       'association_status': 'provisional_stop_window_match',
                       'coverage_status': 'selectively_persisted_not_complete_scan_no_absence_imputation'})
    emit(OUT / 'wifi_by_stop_bssid.csv', groups)
    movements = []
    for edge in read('accelerometer_edges.csv'):
        sid = edge['acc_session_id']; source_session = sessions[sid]
        row = {'segment_id': sid, 'source_acc_session_id': sid,
               'original_file_label': source_session['original_file_label'], 'source_zip': source_session['source_zip'],
               'from_stop_id': edge['from_stop_id'], 'to_stop_id': edge['to_stop_id'],
               'from_location': edge['from_location'], 'to_location': edge['to_location'],
               'target_start_hk': edge['start_hk'], 'target_end_hk': edge['end_hk'],
               'target_start_epoch_s': edge['start_epoch_s'], 'target_end_epoch_s': edge['end_epoch_s'],
               'source_recorded_duration_s': source_session['recorded_duration_s'],
               'timing_status': edge['timing_status'], 'endpoint_label_status': edge['endpoint_label_status'],
               'distance_m': '', 'step_count': '',
               'acceleration_semantics': 'raw_acceleration_includes_gravity_not_calibrated_linear_acceleration',
               'variation_semantics': 'segment_magnitude_deviation_descriptor_not_step_count_or_distance',
               **movement_stats(sensors[(sid, 'accelerometer')])}
        movements.append(row)
    emit(OUT / 'movement_features.csv', movements)
    review = []
    for sid, location in locations.items():
        session = sessions[sid]
        review.append({'raw_recording_id': sid, 'start_hk': session['start_hk'], 'end_hk': session['end_hk'],
                       'source_zip': session['source_zip'], 'source_zip_sha256': session['source_sha256'],
                       'location_number': location['stop_number'],
                       'candidate_location_name': location['location_label'], 'label_confidence': location['label_confidence'],
                       'review_confirmed_location_name': '', 'review_confirmed_floor': '', 'review_repeat_or_test': '', 'review_notes': ''})
    previous_review = read('recording_review.csv') if (ROOT / 'recording_review.csv').exists() else []
    review = preserve_review_fields(review, previous_review)
    emit(ROOT / 'recording_review.csv', review)
    assert hashes() == before, 'Feature extraction modified an input table'
    report = validate()
    manifest = {'dataset_version': 'v1_first_pass_descriptive_features', 'acquisition_date_hk': '2026-11-17',
                'stop_feature_rows': len(stops), 'movement_feature_rows': len(movements), 'synthetic_rows': 0,
                'wifi_stop_bssid_groups': len(groups), 'wifi_candidate_observations_summarized': len(matches),
                'wifi_groups_with_one_observation': sum(len(v) == 1 for v in wifi_groups.values()),
                'wifi_groups_with_multiple_observations': sum(len(v) > 1 for v in wifi_groups.values()),
                'source_table_sha256': before, 'source_tables_unchanged': True,
                'scope': 'whole_recording_descriptive_statistics_no_slicing_interpolation_training_distance_or_steps',
                'labels_status': 'provisional_route_inferred_pending_map_confirmation',
                'feature_validation_checks': report['check_count']}
    dump(OUT / 'feature_manifest.json', manifest)
    explain(stops, movements)
    log_steps()
    update_readme()
    summary = json.loads((ROOT / 'summary.json').read_text())
    summary.setdefault('core_cleaning_version', summary['dataset_version'])
    summary['dataset_version'] = 'v1_first_pass_features_route_labelled_provisional'
    summary['features'] = {k: v for k, v in manifest.items() if k != 'source_table_sha256'}
    dump(ROOT / 'summary.json', summary)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

def validate():
    stops = read('features/stop_features.csv'); moves = read('features/movement_features.csv'); groups = read('features/wifi_by_stop_bssid.csv')
    source = defaultdict(list)
    for r in read('sensor_samples.csv'):
        source[(r['session_id'], r['sensor'])].append(r)
    checks = []
    def check(name, ok):
        checks.append({'check': name, 'passed': bool(ok)})
        if not ok:
            raise AssertionError(name)
    def close(a, b):
        return math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10)
    total_baro = sum(len(source[(r['stop_id'], 'barometer')]) for r in stops)
    total_mag = sum(len(source[(r['stop_id'], 'magnetometer')]) for r in stops)
    check('26_unique_actual_stop_feature_rows', len(stops) == len({r['stop_id'] for r in stops}) == 26)
    check('stop_sample_counts_account_for_all_accepted_baro_and_mag',
          sum(int(r['barometer_sample_count']) for r in stops) == total_baro and sum(int(r['magnetometer_sample_count']) for r in stops) == total_mag)
    for sensor, prefix, field, countfield in [('barometer', 'pressure_hpa', 'x', 'barometer_sample_count'), ('magnetometer', 'magnetic_magnitude_ut', 'vector_magnitude', 'magnetometer_sample_count')]:
        ok = True
        for row in stops:
            values = [float(r[field]) for r in source[(row['stop_id'], sensor)]]
            mean = sum(values) / len(values)
            sd = math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))
            ok &= int(row[countfield]) == len(values) and close(row[prefix + '_mean'], mean) and close(row[prefix + '_sample_sd'], sd) and close(row[prefix + '_median'], statistics.median(values))
        check(sensor + '_statistics_recomputed_from_clean_samples', ok)
    associations = read('wifi/stop_associations_provisional.csv'); obs = {r['wifi_observation_id']: r for r in read('wifi/observations.csv')}
    expected = defaultdict(list)
    for r in associations:
        expected[(r['session_id'], obs[r['wifi_observation_id']]['MAC'])].append(obs[r['wifi_observation_id']])
    check('wifi_group_observation_counts_sum_to_associations', sum(int(r['candidate_observation_count']) for r in groups) == len(associations))
    check('wifi_only_actual_observed_stop_bssid_pairs', set((r['stop_id'], r['bssid']) for r in groups) == set(expected))
    check('wifi_group_stats_and_source_ids_recomputed', all(int(r['candidate_observation_count']) == len(expected[(r['stop_id'], r['bssid'])]) and close(r['rssi_median_dbm'], statistics.median(float(x['RSSI']) for x in expected[(r['stop_id'], r['bssid'])])) and set(json.loads(r['source_observation_ids_json'])) == {x['wifi_observation_id'] for x in expected[(r['stop_id'], r['bssid'])]} for r in groups))
    check('23_unique_movement_rows_no_synthetic', len(moves) == len({r['segment_id'] for r in moves}) == 23)
    check('movement_sample_counts_sum_to_accepted_accelerometer', sum(int(r['sample_count']) for r in moves) == sum(len(source[(r['segment_id'], 'accelerometer')]) for r in moves))
    ok = True
    for row in moves:
        values = [float(r['vector_magnitude']) for r in source[(row['source_acc_session_id'], 'accelerometer')]]
        mean = sum(values) / len(values); median = statistics.median(values)
        rms = math.sqrt(sum((x - median) ** 2 for x in values) / len(values))
        ok &= close(row['magnitude_m_s2_mean'], mean) and close(row['magnitude_deviation_from_segment_median_rms_m_s2'], rms)
    check('movement_magnitude_mean_and_deviation_rms_recomputed', ok)
    check('no_distance_steps_or_calibration_claims', all(r['distance_m'] == r['step_count'] == '' and 'includes_gravity' in r['acceleration_semantics'] for r in moves))
    review = read('recording_review.csv'); sessions = {r['session_id']: r for r in read('sessions.csv')}
    check('all_26_recordings_in_review_with_matching_source_identity', len(review) == len({r['raw_recording_id'] for r in review}) == 26 and {r['raw_recording_id'] for r in review} == {r['stop_id'] for r in stops} and all(r['source_zip'] == sessions[r['raw_recording_id']]['source_zip'] and r['source_zip_sha256'] == sessions[r['raw_recording_id']]['source_sha256'] for r in review))
    fixture_new = [{'raw_recording_id': 'BM01', 'source_zip': 'example.zip', 'source_zip_sha256': 'abc', 'review_notes': '', 'review_confirmed_location_name': ''}]
    fixture_old = [{'raw_recording_id': 'BM01', 'source_zip': 'example.zip', 'source_zip_sha256': 'abc', 'review_notes': 'User checked this visit', 'review_confirmed_location_name': 'Exit 5'}]
    preserved = preserve_review_fields(fixture_new, fixture_old)
    check('isolated_review_fixture_preserves_user_entries', preserved[0]['review_notes'] == 'User checked this visit' and preserved[0]['review_confirmed_location_name'] == 'Exit 5' and fixture_new[0]['review_notes'] == '')
    rejected = False
    try:
        preserve_review_fields(fixture_new, [{**fixture_old[0], 'source_zip_sha256': 'different-source'}])
    except ValueError:
        rejected = True
    check('review_merge_rejects_changed_source_identity', rejected)
    check('no_nan_or_infinity_feature_cells', not any(str(v).lower() in ['nan', 'inf', '-inf', 'infinity', '-infinity'] for r in stops + moves + groups for v in r.values()))
    result = {'passed': True, 'check_count': len(checks), 'checks': checks}
    dump(OUT / 'feature_validation.json', result)
    return result

def explain(stops, movements):
    stop = stops[0]; movement = movements[0]
    text = f'''# What the feature tables mean (17 November 2026)

A feature is a small summary of measurements. The original readings remain available. The current workflow is:

**Raw recordings → valid cleaned readings → summary statistics (features) → confirm location labels and map → baseline model and independent testing.**

We can summarize pressure, magnetism and acceleration now. Distances, map coordinates and compass calibration are not required for these descriptive calculations. No model has been trained and no accuracy result has been calculated.

## A real example: {stop['stop_id']}

{stop['stop_id']} is the actual ZIP `{stop['source_zip']}`, recorded from {stop['start_hk']}. Its provisional, route-inferred label is **{stop['candidate_location_name']}** ({stop['label_confidence']}).

- The barometer has **{stop['barometer_sample_count']} accepted readings** with mean **{float(stop['pressure_hpa_mean']):.6f} hPa**, median **{float(stop['pressure_hpa_median']):.5f} hPa**, and sample standard deviation **{float(stop['pressure_hpa_sample_sd']):.6f} hPa**.
- The magnetometer has **{stop['magnetometer_sample_count']} accepted vector readings**. For each vector we compute magnitude `sqrt(x*x + y*y + z*z)`. The mean magnitude is **{float(stop['magnetic_magnitude_ut_mean']):.5f} µT**, median **{float(stop['magnetic_magnitude_ut_median']):.5f} µT**, sample SD **{float(stop['magnetic_magnitude_ut_sample_sd']):.5f} µT**.
- These accepted readings become **one row** in `stop_features.csv`. They have not become many independent location visits. The Wi-Fi count for this window is **{stop['wifi_candidate_observation_count']}**; no RSSI values were invented.

## What the columns summarize

| Feature | Formula or rule | Unit | Meaning |
| --- | --- | --- | --- |
| Sample count | Number of accepted readings | readings | How much measured data supports the summary |
| Mean | `sum(values) / n` | Sensor's unit | Average observed value |
| Median | Middle sorted value (mean of middle two for even n) | Sensor's unit | Central value, robust to one outlier |
| Sample SD | `sqrt(sum((value - mean)^2) / (n - 1))` | Sensor's unit | Variation within this recording; not location accuracy |
| Range | `maximum - minimum` | Sensor's unit | Spread between the extremes |
| Vector magnitude | `sqrt(x*x + y*y + z*z)` per reading, then summarized | µT or m/s² | Overall vector strength |
| Sample time span | Last accepted relative time minus first | seconds | Span actually covered by readings |
| Wi-Fi per-BSSID median | Median of actually exported candidate RSSI rows for one stop window and MAC | dBm | Descriptive signal strength from selectively persisted observations |
| Acceleration magnitude deviation RMS | `sqrt(mean((magnitude - segment_median)^2))` | m/s² | A descriptive variation measure; not gravity-removed linear acceleration, a step count or a distance |

## A movement example

{movement['segment_id']} is the internal ID for the recording labelled **{movement['original_file_label']}** ({movement['from_location']} → {movement['to_location']}). It has **{movement['sample_count']} accepted readings**, recording duration **{float(movement['source_recorded_duration_s']):.3f} s**, mean magnitude **{float(movement['magnitude_m_s2_mean']):.5f} m/s²** and magnitude SD **{float(movement['magnitude_m_s2_sample_sd']):.5f} m/s²**. Raw XYZ means alone can hide movement because positive and negative fluctuations cancel; the variation columns describe that fluctuation while retaining gravity and phone-orientation effects.

`movement_features.csv` has all **23 measured** recordings and no synthetic rows. The two escalator double-landings (BM12→BM13 and BM23→BM24) have no walk recording between them and are listed in `../missing_movements.csv`; no transition was fabricated.

## What remains uncertain

- Stop labels are provisional, inferred only from adjacent movement filenames. Open `../recording_review.csv` to confirm names, floors and any repeat/test flags. Reruns preserve existing `review_*` entries and do not auto-apply them.
- One physical stop was exported twice (`poin 21-36-20` is a prefix of the resumed `poin 21-37-27`); the duplicated interval is quarantined in `../excluded_sensor_rows.csv` and recorded in `../duplicate_recordings.csv`, so it is summarized once.
- Wi-Fi FirstSeen is verified UTC but reflects selectively persisted stored observations, not complete scans. No unobserved BSSID is filled with a weak RSSI value. Three phones' clocks and co-location remain unverified.
- No two-second windows, interpolation, step detection, double integration, distance estimates, calibration or model training have been added.
'''
    (OUT / 'FEATURES_EXPLAINED.md').write_text(text, encoding='utf-8')

def log_steps():
    path = ROOT / 'PROCESSING_LOG.md'
    if path.exists():
        return  # Keep future human/agent log additions; never replace them on re-run.
    s = json.loads((ROOT / 'summary.json').read_text())
    path.write_text(f'''# Processing log — GE2340 acquisition of 17 November 2026

This is the record of meaningful processing decisions for the second acquisition. Add new
decisions/results below as work continues; do not rewrite the original acquisition evidence.
No training, upload or publication has been performed.

| Step | Completed work and reason | Evidence / result |
| --- | --- | --- |
| 1. Inventory the export | Read the loose phyphox ZIPs and the WiGLE GZIP in `Data (17-11)`. Preserve every file byte-for-byte in `raw/attachments/`. | {s['sensor_zip_count']} sensor ZIPs = {s['barometer_magnetometer_stops']} barometer/magnetometer stop recordings (`poin ...zip`) + {s['accelerometer_movements']} accelerometer movement recordings (route-named). One WiGLE GZIP. All ZIPs pass integrity checks. |
| 2. Read recording metadata | Use each phyphox `meta/time.csv` START/PAUSE event to map relative seconds to device epoch, UTC and HK. Preserve device identity. | Stops recorded on {dict(s['devices']).get('barometer_magnetometer_stop','?') if isinstance(s['devices'],dict) else 'iPhone17,4'}, movements on a different iPhone, Wi-Fi on a Samsung. Clocks not independently synchronized. |
| 3. Detect a double-exported stop | One recording (`poin 21-37-27`) has two intervals; its first interval is an exact re-export of the standalone `poin 21-36-20`. | The duplicated interval is quarantined (reason `duplicate_reexport_interval_superseded_by_BM19`), recorded in `duplicate_recordings.csv`. 26 distinct physical stops remain; the stop is counted once. |
| 4. Clean sensor readings | Keep finite parseable readings inside their actual acquisition interval. Quarantine negative-time, outside-interval, nonfinite and exact-duplicate rows with their full source values; no smoothing or resampling. | Input {s['sensor_rows_source']:,} readings = {s['sensor_rows_clean']:,} accepted + {s['sensor_rows_excluded']:,} quarantined. Accepted by sensor: {s['sensor_counts']}. |
| 5. Number and label stops | Number stops BM01..BM26 in recording order. Derive a provisional location label for each from the names of the adjacent movement recordings. | {s['stop_label_confidence_counts'].get('route_confirmed_both_sides',0)} labels confirmed on both sides; 4 escalator landings and 2 single-sided endpoints are lower-confidence. Floors left blank pending a map. |
| 6. Build the route | Assign each movement to the stop immediately before and after it in recording order; record consecutive stop pairs with no walk recording. | 23 measured movements, all within their endpoint windows; 2 unrecorded escalator double-landings in `missing_movements.csv`. Pressure medians drop ~0.6 hPa across the descent and recover on the way up. |
| 7. Audit and associate Wi-Fi | Separate WIFI from non-WIFI rows; verify UTC format; associate rows whose stored FirstSeen second falls inside a stop interval. No interpolation or absent-AP filling. | {s['wifi']['wifi_rows_clean']:,} WIFI observations, {s['wifi']['non_wifi_rows_separated']} LTE rows separated. {s['wifi']['provisionally_associated_rows']} provisional associations across {s['wifi']['stops_with_candidate_rows']} stops; {s['wifi']['unassigned_rows']:,} unassigned. |
| 8. Extract first-pass features | Summarize each cleaned recording with counts, means, medians, sample SDs, ranges and time coverage; summarize Wi-Fi candidate groups without missing-AP values. | `features/stop_features.csv` (26 rows), `features/movement_features.csv` (23 rows, no synthetic), `features/wifi_by_stop_bssid.csv`. Original readings unchanged. |

## Reproduce the completed stages

```bash
python3 clean.py --source "../../../../Data (17-11)"
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
```

## Pending work

1. Confirm stop labels, floor numbers and any repeat/test recording using `recording_review.csv` and the marked indoor plan.
2. Add map coordinates and distances when the plan is available; numeric fields remain blank until then.
3. Decide whether more complete Wi-Fi logging and independently synchronized repeat visits are needed for evaluation.
4. After confirmed labels, choose a baseline and independent evaluation visits. No training or train/test slicing has happened.

## Future entries

Append the next correction, processing action, command and verified result here. Feature extraction preserves existing `review_*` entries keyed by raw ID and source ZIP/hash; it does not automatically apply them as confirmed labels.
''', encoding='utf-8')

def update_readme():
    path = ROOT / 'README.md'; text = path.read_text(encoding='utf-8'); marker = '\n<!-- V1_FEATURES -->\n'
    text = text.split(marker, 1)[0]
    text += marker + '''## Processing history and first-pass feature tables

Start with [PROCESSING_LOG.md](PROCESSING_LOG.md) for every completed stage and pending decision. [features/FEATURES_EXPLAINED.md](features/FEATURES_EXPLAINED.md) explains an actual stop and movement example in plain language.

- `recording_review.csv`: 26 actual stop ZIPs, time, source filename/hash, provisional route-inferred label and confirmation fields. Open in Excel/LibreOffice to confirm names, floors and any repeat/test recording. Existing `review_*` entries survive reruns and are not automatically applied to labels.
- `features/stop_features.csv`: one summary row per actual stop (26), including pressure and magnetic statistics, time spans and Wi-Fi candidate counts.
- `features/movement_features.csv`: 23 measured movement summaries (no synthetic rows), each with its bounding stops and acceleration statistics.
- `features/wifi_by_stop_bssid.csv`: one row per observed stop/BSSID group, from the selectively persisted observations. No absent-AP filling.
- `features/feature_manifest.json`, `feature_validation.json`: source table hashes, counts and checks. The original cleaned readings and acquisition tables are unchanged by feature extraction.

Reproduce features after cleaning with `python3 feature_extraction.py`, verify with `python3 feature_extraction.py --validate-only`. The feature script adds descriptive statistics only: no two-second slicing, interpolation, double integration, distances, step counts, calibration or training.
'''
    path.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--validate-only', action='store_true'); args = p.parse_args()
    if args.validate_only:
        result = validate(); print(f"{result['check_count']} feature checks passed")
    else:
        build()
