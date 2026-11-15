#!/usr/bin/env python3
"""Summarize existing cleaned GE2340 readings; preserve all acquisition tables."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'features'
INPUTS=['sensor_samples.csv','sensors/barometer.csv','sensors/magnetometer.csv','sensors/accelerometer.csv',
        'sessions.csv','sensor_quality.csv','recording_intervals.csv','locations_provisional.csv','corrected_location_list.csv',
        'accelerometer_edges.csv','augmentation/augmented_accelerometer_edges.csv','augmentation/derived_accelerometer_samples.csv',
        'wifi/observations.csv','wifi/stop_associations_provisional.csv','excluded_sensor_rows.csv']

def read(path):
    with (ROOT/path).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def emit(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def dump(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in INPUTS}

def stats(values,prefix):
    values=list(values)
    return {prefix+'_mean':statistics.mean(values),prefix+'_median':statistics.median(values),
            prefix+'_sample_sd':statistics.stdev(values) if len(values)>1 else '',
            prefix+'_min':min(values),prefix+'_max':max(values),prefix+'_range':max(values)-min(values)}

def movement_stats(rows):
    values=[float(r['vector_magnitude']) for r in rows];median=statistics.median(values)
    out={'sample_count':len(rows),
         'observed_sample_span_s':float(rows[-1]['relative_time_s'])-float(rows[0]['relative_time_s'])}
    for axis in ['x','y','z']:
        v=[float(r[axis]) for r in rows]
        out[f'{axis}_mean_m_s2']=statistics.mean(v)
        out[f'{axis}_sample_sd_m_s2']=statistics.stdev(v) if len(v)>1 else ''
    out.update(stats(values,'magnitude_m_s2'))
    out['magnitude_deviation_from_segment_median_rms_m_s2']=math.sqrt(statistics.mean((v-median)**2 for v in values))
    return out

def preserve_review_fields(new_rows,existing_rows):
    """Keep human review entries without applying them as confirmed labels."""
    old={r['raw_recording_id']:r for r in existing_rows}
    if len(old)!=len(existing_rows):raise ValueError('Duplicate recording IDs in existing review table')
    expected={r['raw_recording_id'] for r in new_rows}
    if set(old)-expected:raise ValueError('Existing review table has unknown acquisition IDs')
    out=[]
    for row in new_rows:
        previous=old.get(row['raw_recording_id'])
        if previous:
            if previous.get('source_zip')!=row['source_zip']:
                raise ValueError('Review source ZIP changed for '+row['raw_recording_id'])
            if previous.get('source_zip_sha256') and previous['source_zip_sha256']!=row['source_zip_sha256']:
                raise ValueError('Review source hash changed for '+row['raw_recording_id'])
            row={**row,**{k:previous.get(k,'') for k in row if k.startswith('review_')}}
        out.append(row)
    return out

def build():
    before=hashes();OUT.mkdir(exist_ok=True)
    sessions={r['session_id']:r for r in read('sessions.csv')}
    locations={r['stop_id']:r for r in read('locations_provisional.csv')}
    quality={(r['session_id'],r['sensor']):r for r in read('sensor_quality.csv')}
    sensors=defaultdict(list)
    for r in read('sensor_samples.csv'):sensors[(r['session_id'],r['sensor'])].append(r)
    wifi={r['wifi_observation_id']:r for r in read('wifi/observations.csv')}
    matches=read('wifi/stop_associations_provisional.csv')
    stop_wifi=defaultdict(list);wifi_groups=defaultdict(list)
    for m in matches:
        obs=wifi[m['wifi_observation_id']]
        stop_wifi[m['session_id']].append(obs)
        wifi_groups[(m['session_id'],obs['MAC'])].append(obs)
    stops=[]
    for sid,session in sessions.items():
        if not sid.startswith('BM'):continue
        location=locations[sid];baro=sensors[(sid,'barometer')];mag=sensors[(sid,'magnetometer')]
        row={'stop_id':sid,'source_zip':session['source_zip'],'start_hk':session['start_hk'],'end_hk':session['end_hk'],
             'recorded_duration_s':session['recorded_duration_s'],
             'candidate_corrected_location_number':location['corrected_location_number'],
             'candidate_location_name':location['location_label'],'location_association_status':location['label_status'],
             'location_alignment_status':location['alignment_status'],'floor_candidate':location['floor_candidate'],
             'floor_candidate_status':location['floor_status'],
             'confidence_status':'descriptive_statistics_only_location_and_cross_device_alignment_unverified',
             'barometer_sample_count':len(baro),'magnetometer_sample_count':len(mag)}
        row.update(stats((float(r['x']) for r in baro),'pressure_hpa'))
        for axis in ['x','y','z']:
            values=[float(r[axis]) for r in mag]
            row[f'magnetic_{axis}_mean_ut']=statistics.mean(values)
            row[f'magnetic_{axis}_sample_sd_ut']=statistics.stdev(values)
        row.update(stats((float(r['vector_magnitude']) for r in mag),'magnetic_magnitude_ut'))
        for sensor in ['barometer','magnetometer']:
            q=quality[(sid,sensor)]
            row[sensor+'_first_relative_time_s']=q['first_relative_time_s']
            row[sensor+'_last_relative_time_s']=q['last_relative_time_s']
            row[sensor+'_observed_span_s']=q['observed_span_s']
            row[sensor+'_time_span_fraction_of_recording']=float(q['observed_span_s'])/float(q['recorded_duration_s'])
            row[sensor+'_qc_flags']=q['flags']
        obs=stop_wifi[sid]
        row.update({'wifi_candidate_observation_count':len(obs),
                    'wifi_candidate_distinct_bssid_count':len({r['MAC'] for r in obs}),
                    'wifi_candidate_distinct_stored_timestamp_seconds':len({r['observation_epoch_s'] for r in obs}),
                    'wifi_association_status':'provisional_persisted_location_time_not_fresh_scan_or_complete_fingerprint',
                    'clock_status':session['clock_status']})
        stops.append(row)
    emit(OUT/'stop_features.csv',stops)
    groups=[]
    for (sid,mac),rows in sorted(wifi_groups.items()):
        values=[float(r['RSSI']) for r in rows]
        groups.append({'stop_id':sid,'bssid':mac,'candidate_observation_count':len(rows),
            'rssi_median_dbm':statistics.median(values),'rssi_mean_dbm':statistics.mean(values),
            'distinct_stored_timestamp_seconds':len({r['observation_epoch_s'] for r in rows}),
            'first_observation_time_utc':min(r['observation_time_utc'] for r in rows),
            'last_observation_time_utc':max(r['observation_time_utc'] for r in rows),
            'source_observation_ids_json':json.dumps([r['wifi_observation_id'] for r in rows]),
            'association_status':'provisional_stop_window_match',
            'coverage_status':'selectively_persisted_not_complete_scan_no_absence_imputation'})
    emit(OUT/'wifi_by_stop_bssid.csv',groups)
    movements=[];measured_stats={}
    edges=read('augmentation/augmented_accelerometer_edges.csv')
    for edge in edges:
        derived=edge['is_synthetic']=='True'
        parent_id=edge['parent_acc_session_id'] if derived else edge['acc_session_id']
        source_session=sessions[parent_id]
        if parent_id not in measured_stats:measured_stats[parent_id]=movement_stats(sensors[(parent_id,'accelerometer')])
        row={'segment_id':edge['segment_id'],'source_acc_session_id':parent_id,
            'original_source_acc_label':source_session['original_acc_label'],'source_zip':source_session['source_zip'],
            'is_synthetic':derived,'derivation_type':edge['derivation_type'],
            'parent_acc_session_id':edge['parent_acc_session_id'],'acquisition_group_id':edge['acquisition_group_id'],
            'from_stop_id':edge['from_stop_id'],'to_stop_id':edge['to_stop_id'],
            'candidate_from_corrected_location_number':edge['from_corrected_location_number'],
            'candidate_to_corrected_location_number':edge['to_corrected_location_number'],
            'location_alignment_status':edge['location_alignment_status'],
            'target_start_hk':'' if derived else edge['start_hk'],'target_end_hk':'' if derived else edge['end_hk'],
            'target_start_epoch_s':'' if derived else edge['start_epoch_s'],'target_end_epoch_s':'' if derived else edge['end_epoch_s'],
            'source_start_hk':source_session['start_hk'],'source_end_hk':source_session['end_hk'],
            'source_recorded_duration_s':source_session['recorded_duration_s'],
            'historical_visit':edge['historical_visit'],'intended_use':edge['intended_use'],
            'timing_status':edge['timing_status'],'distance_m':'','step_count':'',
            'acceleration_semantics':'raw_acceleration_includes_gravity_not_calibrated_linear_acceleration',
            'variation_semantics':'segment_magnitude_deviation_descriptor_not_step_count_or_distance',
            **measured_stats[parent_id]}
        movements.append(row)
    emit(OUT/'movement_features.csv',movements)
    review=[]
    for sid,location in locations.items():
        session=sessions[sid]
        review.append({'raw_recording_id':sid,'start_hk':session['start_hk'],'end_hk':session['end_hk'],
            'source_zip':session['source_zip'],'source_zip_sha256':session['source_sha256'],
            'original_source_location_number':location['original_source_location_number'],
            'candidate_corrected_location_number':location['corrected_location_number'],
            'candidate_location_name':location['location_label'],'candidate_status':location['label_status'],
            'alignment_status':location['alignment_status'],'review_confirmed_location_number':'',
            'review_confirmed_location_name':'','review_repeat_or_test':'','review_notes':''})
    previous_review=read('recording_review.csv') if (ROOT/'recording_review.csv').exists() else []
    review=preserve_review_fields(review,previous_review)
    emit(ROOT/'recording_review.csv',review)
    assert hashes()==before,'Feature extraction modified an input table'
    report=validate()
    manifest={'dataset_version':'v4_first_pass_descriptive_features','stop_feature_rows':len(stops),
              'movement_feature_rows':len(movements),'measured_movement_feature_rows':23,'copied_movement_feature_rows':1,
              'wifi_stop_bssid_groups':len(groups),'wifi_candidate_observations_summarized':len(matches),
              'wifi_groups_with_one_observation':sum(len(v)==1 for v in wifi_groups.values()),
              'wifi_groups_with_multiple_observations':sum(len(v)>1 for v in wifi_groups.values()),
              'source_table_sha256':before,'source_tables_unchanged':True,
              'scope':'whole_recording_descriptive_statistics_no_slicing_interpolation_training_distance_or_steps',
              'labels_status':'pending_alignment_of_26_recordings_to_25_corrected_locations',
              'feature_validation_checks':report['check_count']}
    actual_stops=[r for r in sessions.values() if r['session_id'].startswith('BM')]
    manifest['recording_count_proof']={'barometer_magnetometer_recordings':len(actual_stops),
        'unique_source_zip_names':len({r['source_zip'] for r in actual_stops}),
        'unique_source_zip_sha256':len({r['source_sha256'] for r in actual_stops}),
        'unique_recording_start_times':len({r['start_epoch_s'] for r in actual_stops}),
        'corrected_ordered_description_entries':len(read('corrected_location_list.csv')),
        'description_entries_include_revisits':True}
    dump(OUT/'feature_manifest.json',manifest)
    explain(stops[0],movements[0])
    log_steps()
    update_readme()
    summary=json.loads((ROOT/'summary.json').read_text())
    summary.setdefault('core_cleaning_version',summary['dataset_version'])
    summary['dataset_version']='v4_first_pass_features_alignment_pending'
    summary['features']={k:v for k,v in manifest.items() if k!='source_table_sha256'}
    dump(ROOT/'summary.json',summary)
    print(json.dumps(manifest,indent=2))

def validate():
    stops=read('features/stop_features.csv');moves=read('features/movement_features.csv');groups=read('features/wifi_by_stop_bssid.csv')
    source=defaultdict(list)
    for r in read('sensor_samples.csv'):source[(r['session_id'],r['sensor'])].append(r)
    checks=[]
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10)
    check('26_unique_actual_stop_feature_rows',len(stops)==len({r['stop_id'] for r in stops})==26)
    check('stop_sample_counts_account_for_all_accepted_baro_and_mag',sum(int(r['barometer_sample_count']) for r in stops)==208 and sum(int(r['magnetometer_sample_count']) for r in stops)==25981)
    for sensor,prefix,field,countfield in [('barometer','pressure_hpa','x','barometer_sample_count'),('magnetometer','magnetic_magnitude_ut','vector_magnitude','magnetometer_sample_count')]:
        ok=True
        for row in stops:
            values=[float(r[field]) for r in source[(row['stop_id'],sensor)]]
            mean=sum(values)/len(values)
            sd=math.sqrt(sum((x-mean)**2 for x in values)/(len(values)-1))
            ok &= int(row[countfield])==len(values) and close(row[prefix+'_mean'],mean) and close(row[prefix+'_sample_sd'],sd) and close(row[prefix+'_median'],statistics.median(values))
        check(sensor+'_statistics_recomputed_from_clean_samples',ok)
    associations=read('wifi/stop_associations_provisional.csv');obs={r['wifi_observation_id']:r for r in read('wifi/observations.csv')}
    expected=defaultdict(list)
    for r in associations:expected[(r['session_id'],obs[r['wifi_observation_id']]['MAC'])].append(obs[r['wifi_observation_id']])
    check('wifi_group_observation_counts_sum_to664',sum(int(r['candidate_observation_count']) for r in groups)==len(associations)==664)
    check('wifi_only_actual_observed_stop_bssid_pairs',set((r['stop_id'],r['bssid']) for r in groups)==set(expected))
    check('wifi_group_stats_and_source_ids_recomputed',all(int(r['candidate_observation_count'])==len(expected[(r['stop_id'],r['bssid'])]) and close(r['rssi_median_dbm'],statistics.median(float(x['RSSI']) for x in expected[(r['stop_id'],r['bssid'])])) and set(json.loads(r['source_observation_ids_json']))=={x['wifi_observation_id'] for x in expected[(r['stop_id'],r['bssid'])]} for r in groups))
    check('no_imputed_wifi_rows_at_zero_coverage_stops',not any(r['stop_id'] in ['BM01','BM12','BM14','BM22'] for r in groups))
    measured=[r for r in moves if r['is_synthetic']=='False'];copied=[r for r in moves if r['is_synthetic']=='True']
    check('24_unique_movement_rows_23_measured1proxy',len(moves)==len({r['segment_id'] for r in moves})==24 and len(measured)==23 and len(copied)==1)
    check('movement_measured_sample_counts_sum19935',sum(int(r['sample_count']) for r in measured)==19935)
    ok=True
    for row in measured:
        values=[float(r['vector_magnitude']) for r in source[(row['source_acc_session_id'],'accelerometer')]]
        mean=sum(values)/len(values);median=statistics.median(values)
        rms=math.sqrt(sum((x-median)**2 for x in values)/len(values))
        ok &= close(row['magnitude_m_s2_mean'],mean) and close(row['magnitude_deviation_from_segment_median_rms_m_s2'],rms)
    check('movement_magnitude_mean_and_deviation_rms_recomputed',ok)
    proxy=copied[0];parent=next(r for r in measured if r['segment_id']==proxy['parent_acc_session_id'])
    numeric_fields=list(movement_stats(source[('ACC15','accelerometer')]))
    check('proxy_features_exactly_equal_parent',all(proxy[k]==parent[k] for k in numeric_fields) and proxy['sample_count']=='664')
    check('proxy_group_parent_provenance_preserved',proxy['source_acc_session_id']==proxy['parent_acc_session_id']==proxy['acquisition_group_id']=='ACC15' and proxy['original_source_acc_label']=='P16-18 (esca bawah)')
    check('proxy_target_times_blank_source_times_retained',all(proxy[k]=='' for k in ['target_start_hk','target_end_hk','target_start_epoch_s','target_end_epoch_s']) and proxy['source_start_hk']==parent['source_start_hk'])
    check('no_distance_steps_or_calibration_claims',all(r['distance_m']==r['step_count']=='' and 'includes_gravity' in r['acceleration_semantics'] for r in moves))
    review=read('recording_review.csv');sessions={r['session_id']:r for r in read('sessions.csv')}
    check('all_26_recordings_in_review_with_matching_source_identity',len(review)==len({r['raw_recording_id'] for r in review})==26 and {r['raw_recording_id'] for r in review}=={r['stop_id'] for r in stops} and all(r['source_zip']==sessions[r['raw_recording_id']]['source_zip'] and r['source_zip_sha256']==sessions[r['raw_recording_id']]['source_sha256'] for r in review))
    fixture_new=[{'raw_recording_id':'BM01','source_zip':'example.zip','source_zip_sha256':'abc','review_notes':'','review_confirmed_location_number':''}]
    fixture_old=[{'raw_recording_id':'BM01','source_zip':'example.zip','source_zip_sha256':'abc','review_notes':'User checked this visit','review_confirmed_location_number':'7'}]
    preserved=preserve_review_fields(fixture_new,fixture_old)
    check('isolated_review_fixture_preserves_user_entries',preserved[0]['review_notes']=='User checked this visit' and preserved[0]['review_confirmed_location_number']=='7' and fixture_new[0]['review_notes']=='')
    rejected=False
    try:preserve_review_fields(fixture_new,[{**fixture_old[0],'source_zip_sha256':'different-source'}])
    except ValueError:rejected=True
    check('review_merge_rejects_changed_source_identity',rejected)
    check('no_nan_or_infinity_feature_cells',not any(str(v).lower() in ['nan','inf','-inf','infinity','-infinity'] for r in stops+moves+groups for v in r.values()))
    check('all_feature_location_links_remain_unresolved',all('unresolved' in r['location_alignment_status'] for r in stops+moves))
    result={'passed':True,'check_count':len(checks),'checks':checks}
    dump(OUT/'feature_validation.json',result)
    return result

def explain(stop,movement):
    text=f'''# What the feature tables mean

A feature is a small summary of measurements. The original readings remain available. The current workflow is:

**Raw recordings → valid cleaned readings → summary statistics (features) → confirm location labels and map → baseline model and independent testing.**

We can summarize pressure, magnetism and acceleration now. Distances, map coordinates and compass calibration are not required for these descriptive calculations. No model has been trained and no accuracy result has been calculated.

## A real example: BM01

BM01 is the actual ZIP `point 2026-11-14 21-10-09.zip`, recorded from 21:09:41.933 Hong Kong time. Its candidate label is Exit 5; recording-to-location alignment remains provisional.

- The barometer originally has 9 readings. One has a negative experiment time and remains in quarantine. The **8 accepted readings** have mean **{stop['pressure_hpa_mean']:.9f} hPa**, median **{stop['pressure_hpa_median']:.5f} hPa**, and sample standard deviation **{stop['pressure_hpa_sample_sd']:.8f} hPa**. Their sample span is approximately 0.49–6.98 seconds.
- The magnetometer has **{stop['magnetometer_sample_count']} accepted vector readings** across roughly 10 seconds. For each vector we calculate magnitude `sqrt(x*x + y*y + z*z)`. The mean of these magnitudes is **{stop['magnetic_magnitude_ut_mean']:.5f} µT**, median **{stop['magnetic_magnitude_ut_median']:.5f} µT**, and sample standard deviation **{stop['magnetic_magnitude_ut_sample_sd']:.5f} µT**.
- These 1,008 accepted sensor readings become **one row** in `stop_features.csv`. They have not become 1,008 independent location visits. There are no exported Wi-Fi observations in this exact stop window; the Wi-Fi count is zero, and no RSSI values were invented.

## What the columns summarize

| Feature | Formula or rule | Unit | Meaning |
| --- | --- | --- | --- |
| Sample count | Number of accepted readings | readings | How much measured data supports the summary |
| Mean | `sum(values) / n` | Sensor's unit | Average observed value |
| Median | Middle sorted value, averaging the middle two for even n | Sensor's unit | Central value less sensitive to one extreme reading |
| Sample SD | `sqrt(sum((value - mean)^2) / (n - 1))` | Sensor's unit | Variation within this particular recording; not location accuracy |
| Range | `maximum - minimum` | Sensor's unit | Spread between the extremes |
| Vector magnitude | `sqrt(x*x + y*y + z*z)` per reading, then summarized | µT or m/s² | Overall vector strength; magnitude mean differs from magnitude of XYZ means |
| Sample time span | Last accepted relative time minus first | seconds | Span actually covered by readings; not a guarantee of uninterrupted sampling |
| Wi-Fi per-BSSID median | Median of actually exported candidate RSSI rows for one BM window and MAC | dBm | Descriptive signal strength from selectively persisted observations |
| Acceleration magnitude deviation RMS | `sqrt(mean((magnitude - segment_median_magnitude)^2))` | m/s² | A descriptive variation measure; not gravity-removed linear acceleration, a step count or distance |

## A movement example

ACC01 is the internal stable ID for original file label **P1**. It has **{movement['sample_count']} accepted readings**, recording duration **{float(movement['source_recorded_duration_s']):.3f} seconds**, mean magnitude **{movement['magnitude_m_s2_mean']:.5f} m/s²** and magnitude SD **{movement['magnitude_m_s2_sample_sd']:.5f} m/s²**. Raw XYZ means alone can hide movement because positive and negative fluctuations cancel around the average. The variation columns describe that fluctuation while retaining gravity and phone-orientation effects.

`movement_features.csv` has 23 real recordings plus the one explicitly requested copy. The copied 5F connector uses ACC15, whose original filename says **P16–18**, not P15. Its feature numbers are exactly the parent's; its target acquisition times remain blank. Parent and copy share acquisition group ACC15 and are not independent recordings.

## What remains uncertain

- Twenty-six actual barometer/magnetometer ZIPs are present, with distinct names, SHA-256 hashes and recording start times: these are not byte-duplicate exports. The source list has twenty-five ordered description entries (including two Y5 302 visits), not necessarily twenty-five unique physical places. Original numbers are 1, 2, 3, 5…26; the user's typo correction makes a complete list 1…25. The repeat/test/extra recording is not identified yet; corrected list number is not raw BM ordinal. All location links remain candidate links.
- Open `../recording_review.csv` in Excel or LibreOffice. Each row is one actual ZIP with time, current candidate label and review fields. Confirm a location or flag a repeat/test there; rerunning feature extraction preserves existing `review_*` entries and does not automatically apply them to labels. The blank BM04 candidate is a placeholder from the previous ordinal mapping, not proof BM04 is the extra visit.
- Wi-Fi FirstSeen is verified UTC, but the export contains selective stored location observations, not complete scan snapshots. Exact installed WiGLE 2.111 source/binary was not matched to the audited current upstream source. No unobserved BSSID is filled with a weak RSSI value. Three phones' clocks and co-location remain unverified.
- The 664 Wi-Fi candidate observations form 663 stop/BSSID groups: **662 groups contain just one row**, and one contains two. Nearly every per-BSSID median therefore equals one exported reading, not an average of repeated scans throughout ten seconds.
- No two-second windows, interpolation, step detection, double integration, distance estimates, calibration or model training have been added.
'''
    (OUT/'FEATURES_EXPLAINED.md').write_text(text,encoding='utf-8')

def log_steps():
    path=ROOT/'PROCESSING_LOG.md'
    if path.exists():return  # Keep future human/agent log additions; never replace them on re-run.
    path.write_text('''# Processing log — GE2340 acquisition of 14 November 2026

This is the record of meaningful processing decisions. Add new decisions/results below as work continues; do not rewrite the original acquisition evidence. Versions v1–v4 are completed local artifacts. No training, upload or publication has been performed.

| Step | Completed work and reason | Evidence / result |
| --- | --- | --- |
| 1. Find the export | Read `WhatsApp Chat with GE2340.zip` from Windows Downloads. Start at messages sent 21:10 on 14 November; use internal recording times rather than sending times. | Source SHA-256 `7f7e42c00513de2abf974d98b58bd2a56fe24d18c29542ae56b6da6fdc356a34`. First included recording actually starts 21:09:41.933 HK. |
| 2. Inventory the actual files | Check each referenced attachment and each nested sensor ZIP. Preserve original source and selected sensor attachments byte-for-byte. | 49 sensor ZIPs = 26 barometer/magnetometer recordings + 23 accelerometer recordings. One Wi-Fi GZIP. All 52 attachment references after the cutoff exist; unrelated homework is not processed. |
| 3. Read recording metadata | Use each phyphox `meta/time.csv` START/PAUSE event to map relative seconds to device epoch time, UTC and HK. Preserve actual device identity. | Two iPhones record the sensor streams; Samsung records Wi-Fi. No independent inter-phone clock calibration or offset is claimed. |
| 4. Clean sensor readings (v1) | Keep finite parseable readings inside their actual acquisition interval. Quarantine negative-time/outside-window rows with their full source values; no smoothing or resampling. | 46,171 original readings = 46,124 accepted + 47 quarantined negative-time readings. Accepted: 208 pressure, 25,981 magnetic and 19,935 acceleration readings. |
| 5. Explain different sampling rates | Keep separate pressure and magnetic readings rather than forcing rows to align by index. | Each barometer file has 9 original readings including one negative time; 8 accepted readings span approximately 0.5–7 seconds. Magnetic recordings last about 10 seconds at approximately 100 Hz. |
| 6. Inspect route and accelerators | Treat accelerometer files as movements between candidate stops. Use original P filenames and actual intervals. | 22 movements fall between candidate endpoint stop windows. Original `P16–18` is stable ID ACC15 and is recorded after both candidate endpoint visits; retain it as a later connector visit. No separate P15 file is present. |
| 7. Incorporate escalator explanation | User clarified: 5F down landing → vending 1 → vending 2 → 4F down landing. Barometer/magnetometer include upstairs/downstairs side trip; accelerometer covers lower-floor down-to-up connector. | Retained candidate BM15/16/17/18 clean pressure medians: 1010.4649 / 1011.0469 / 1010.4795 / 1011.0655 hPa. Rise/fall/rise supports the floor-change sequence. This does not independently establish all location labels. |
| 8. Audit Wi-Fi export | Separate 6,196 WIFI from 15 LTE rows; keep provenance. Confirm UTC format and inspect observation persistence in official format/upstream code. | Zero exact duplicate Wi-Fi rows. FirstSeen is stored location-observation time; selective persistence is consistent with 98.22% of repeated-BSSID changes being RSSI improvements ≥5 dB. Exact installed 2.111 source/binary was not matched to current upstream. See `wifi/AUDIT.md`. |
| 9. Candidate Wi-Fi-to-stop association | Normalize UTC/HK display, then retain rows whose exported second falls inside an actual stop interval. Do not interpolate or infer absent access points. | 664 candidate observations across 22 stops. BM01/BM12/BM14/BM22 have no exported row in the exact window. 2,244 inter-stop rows and 3,288 outside the full sensor span remain unassigned. No fresh-scan or complete-fingerprint claim. |
| 10. Preserve and package v1 | Generate readable CSVs, manifests, QC, timeline and reproducible cleaner. | Source-level row accounting/hashes validated. Private full-chat source stays local; shareable archive omits the whole chat and transcript. |
| 11. Apply user's requested copy (v2) | User explicitly allowed duplicating the lower-floor accelerometer connector for the assumed 5F connector, stating same distance and same person. | Copy all 664 accepted ACC15 samples into separate `SYN_ACC_5F_CONNECTOR`; retain parent/provenance and acquisition group ACC15. Mark synthetic, user-requested, nonhistorical, intended for assumed map connector/simulation. Target acquisition times and numeric distance remain blank. Measured tables unchanged. |
| 12. Correct numbering typo (v3) | User explained the skipped 4 in the source list was a typo. Keep source 1–3 and shift original 5–26 to corrected 4–25. Preserve original numbers and filenames. | `corrected_location_list.csv` is complete 1–25. Corrected Dat4 is study room 11. There are still 26 real stop ZIPs versus 25 descriptions. All location-to-recording links remain candidates. BM04 was the unmatched slot in the earlier ordinal mapping, not proof of which recording is extra. |
| 13. Prepare review table (v4) | Make `recording_review.csv` with one row per actual stop ZIP, internal start/end, source name, candidate association and blank review fields. | Twenty-six rows let the group identify the repeat/test/extra recording. No file is deleted or relabeled as confirmed while that alignment is unknown. |
| 14. Extract first-pass features (v4) | Summarize each complete cleaned recording using counts, means, medians, sample SDs, ranges and time coverage. Summarize actual Wi-Fi candidate groups without missing-AP values. | `features/stop_features.csv`: 26 rows. `wifi_by_stop_bssid.csv`: 663 actual groups, counts sum to 664; 662 contain a single row and one contains two. These medians usually equal one exported reading, not repeated ten-second scan averages. `movement_features.csv`: 23 measured rows + one proxy with features copied from its parent. Original readings unchanged. |
| 15. Validate and explain v4 | Check feature source counts/statistics, grouping totals, copied-feature identity and blank proxy times. Document an actual BM01/ACC01 worked example. | `features/feature_validation.json`, `feature_manifest.json`, `FEATURES_EXPLAINED.md`. No NaN, invented distance/steps or false calibration claims. |

## How 26 versus 25 was counted

The **26** comes directly from 26 distinct nested `point ...zip` files containing `Barometer.csv` and `Magnetometer.csv`: 26 unique filenames, 26 unique ZIP SHA-256 hashes and 26 unique recording start times. They are not byte-duplicate exports. The count excludes the 23 accelerometer ZIPs and the later synthetic copy. The **25** comes from the 25 ordered description lines in the source message: numbers 1,2,3,5…26. This is a count of description entries, not unique physical places: both Y5 302 visits are included. Renumbering fixes their displayed sequence but does not change the file count. The reason for the extra recording remains pending. The initial BM04 blank was a processing placeholder, not evidence that location 4 is missing.

## Reproduce the completed stages

```bash
python3 clean.py --source 'raw/WhatsApp Chat with GE2340.zip'
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
python3 package.py
```

The shareable ZIP excludes the private whole-chat export; recipients need that source separately for the source-level cleaner. Feature extraction reads the supplied cleaned CSVs and can be rerun without the chat. V1, v2 and v3 ZIPs remain preserved; the current package is v4.

## Pending work

1. Identify which of the 26 stop recordings is a repeat/test/extra and confirm recording-to-location links using `recording_review.csv`.
2. Confirm map coordinates and distances when the marked indoor plan is available; numeric fields remain blank until then.
3. Decide whether complete Wi-Fi logging and independently synchronized repeat visits are needed for model evaluation.
4. After confirmed labels, choose a simple baseline and independent evaluation visits. No training or train/test slicing has happened.

## Future entries

Append the next user correction, processing action, command and verified result here. Feature extraction preserves existing `review_*` entries keyed by raw ID and source ZIP/hash; it does not automatically apply them as confirmed labels.
''',encoding='utf-8')

def update_readme():
    path=ROOT/'README.md';text=path.read_text();marker='\n<!-- V4_FEATURES -->\n'
    text=text.split(marker,1)[0]
    text=text.replace('14 November 2026 — v3','14 November 2026 — v4',1)
    text=text.replace('Original v1 and v2 archives remain intact; `package.py` creates `ge2340-cleaned-2026-11-14-v3.zip`.','Original v1, v2 and v3 archives remain intact; `package.py` creates `ge2340-cleaned-2026-11-14-v4.zip`.')
    text+=marker+'''## Processing history and first-pass feature tables

Start with [PROCESSING_LOG.md](PROCESSING_LOG.md) for every completed stage and pending decision. [features/FEATURES_EXPLAINED.md](features/FEATURES_EXPLAINED.md) explains an actual stop and movement example in plain language.

- `recording_review.csv`: 26 actual stop ZIPs, time, source filename/hash, provisional candidate label and confirmation fields. Open in Excel/LibreOffice to identify the extra/repeat/test recording. Existing `review_*` entries survive reruns and are not automatically applied to labels. The corrected location list has 25 description entries (including revisits); this difference is unrelated to the copied connector.
- `features/stop_features.csv`: one summary row per actual stop (26), including pressure and magnetic statistics, time spans, uncertainty and Wi-Fi candidate counts.
- `features/wifi_by_stop_bssid.csv`: 663 observed stop/BSSID groups summarize 664 candidate observations; 662 groups have only one row, so their medians are single exported readings. No absent-AP filling.
- `features/movement_features.csv`: 23 measured movement summaries and one explicitly copied proxy, with shared parent/group provenance and blank target times for the proxy.
- `features/feature_manifest.json`, `feature_validation.json`: source table hashes, counts and checks. The original cleaned readings and acquisition tables are unchanged by feature extraction.

Reproduce features after cleaning with `python3 feature_extraction.py`, verify with `python3 feature_extraction.py --validate-only`, then rebuild v4 with `python3 package.py`. The feature script adds descriptive statistics only: no two-second slicing, interpolation, double integration, distances, step counts, calibration or training. Processing can proceed to these summaries before compass/map-distance work.
'''
    path.write_text(text,encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--validate-only',action='store_true');args=p.parse_args()
    if args.validate_only:
        result=validate();print(f"{result['check_count']} feature checks passed")
    else:build()
