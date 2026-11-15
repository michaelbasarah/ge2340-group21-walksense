#!/usr/bin/env python3
"""Clean the 2026-11-14 GE2340 sensor export without inventing measurements.

Standard library only. Raw archives remain byte-identical. Re-run outputs are
deterministic, except the source location recorded in summary.json.
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
DEFAULT_SOURCE = Path('raw/WhatsApp Chat with GE2340.zip')
HK = timezone(timedelta(hours=8))
CUTOFF = datetime(2026, 11, 14, 21, 10, tzinfo=HK)
CHAT = 'WhatsApp Chat with GE2340.txt'
MESSAGE = re.compile(r'^(\d+/\d+/\d+, \d+:\d+) - (.*?): (.*)$')
UNITS = {'barometer': 'hPa', 'magnetometer': 'uT', 'accelerometer': 'm/s^2'}
SENSORS = {'Barometer.csv': 'barometer', 'Magnetometer.csv': 'magnetometer', 'Accelerometer.csv': 'accelerometer'}

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
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def parse_messages(text):
    messages = []
    for line in text.splitlines():
        m = MESSAGE.match(line)
        if m:
            stamp, sender, body = m.groups()
            messages.append({'stamp': stamp, 'dt': datetime.strptime(stamp, '%d/%m/%Y, %H:%M').replace(tzinfo=HK), 'sender': sender, 'body': body})
        elif messages:
            messages[-1]['body'] += '\n' + line
    return messages

def location_rows(messages):
    msg = next(m for m in messages if m['stamp'] == '15/11/2026, 00:26' and m['body'].startswith('Dat 1 '))
    labels = {}
    for line in msg['body'].splitlines():
        m = re.match(r'(?:Dat\s+)?(\d+)\s+(.+)', line)
        if m:
            labels[int(m[1])] = m[2]
    english = {
        1:'Exit 5',2:"Men's toilet",3:'Y5 302',5:'Study room 11',6:'Study room 10',
        7:'Study room 9',8:'Study room 8',9:'Y5 302 (revisit)',10:"Women's toilet",
        11:'Exit 10',12:'Canteen',13:'Down escalator, 5F landing',14:'Vending machine 1',
        15:'Vending machine 2',16:'Down escalator, 4F landing',17:'Up escalator, 5F landing',
        18:'Up escalator, 4F landing',19:'Y4052',20:'Lecture theatre 1 B',21:'Lecture theatre 1 A',
        22:'Exit 10, 4F',23:'Exit / entrance',24:'Exit 5, 4F',25:'Lecture theatre 2 B',26:'Lecture theatre 2 A',
    }
    out=[]
    for n in range(1,27):
        floor=5 if n<=15 else (5 if n==17 else 4)
        corrected=n if n<=3 else (n-1 if n>=5 else '')
        out.append({'stop_id':f'BM{n:02}', 'stop_number':n, 'original_source_location_number':n if n in labels else '',
                    'corrected_location_number':corrected,'original_label':labels.get(n,''),
                    'location_label':english.get(n,''),
                    'label_status':'unmatched_recording_pending_repeat_test_alignment' if n not in labels else 'candidate_link_alignment_unresolved_26_recordings_25_locations',
                    'alignment_status':'unresolved_26_recordings_25_corrected_locations',
                    'label_source':'WhatsApp 15/11/2026 00:26', 'floor_candidate':floor,
                    'floor_status':'user_route_supported' if n in [13,16,17,18] else 'route_context_inferred',
                    'english_label_status':'inferred_expansion_of_lt_abbreviation' if n in [20,21,25,26] else ('unmatched_recording' if n==4 else 'translation_or_user_clarified'),
                    'x_m':'','y_m':'',
                    'notes':'Corrected Dat4 is study room 11; this raw recording remains unmatched in the current candidate mapping. Extra/repeat recording not identified.' if n==4 else 'User corrected source-list numbering: source5..26 becomes corrected4..25. Existing name-to-recording link remains a candidate; corrected number is not the raw BM ordinal.'})
    return out

def intervals(events):
    out=[]
    active=None
    for e in events:
        if e['event']=='START':
            if active:raise ValueError('Consecutive START events')
            active=e
        elif e['event']=='PAUSE':
            if active is None:raise ValueError('PAUSE without START')
            out.append((active,e));active=None
    if active:raise ValueError('Unclosed START event')
    if not out:raise ValueError('No acquisition intervals')
    return out

def clean(source, wifi_audit=None):
    source=source.resolve()
    raw=ROOT/'raw';raw.mkdir(exist_ok=True)
    data=source.read_bytes()
    preserved=raw/source.name
    if preserved.exists() and digest(preserved.read_bytes())!=digest(data):
        raise ValueError('Existing preserved source differs; refusing to overwrite it')
    if not preserved.exists():shutil.copy2(source,preserved)
    (raw/'source.sha256').write_text(digest(data)+'  '+source.name+'\n')
    audit=json.loads(wifi_audit.read_text()) if wifi_audit else {
        'timestamp_timezone':'UTC_verified_by_official_WiGLE_CSV_v1.6_format',
        'timestamp_semantics':'persisted_observation_location_time_not_radio_acquisition_time',
        'source_version_limitation':'Upstream behavior audited separately; exact installed 2.111 source/binary not matched.',
        'clock_alignment_status':'unverified_three_distinct_devices_no_offset_estimated',
        'complete_scan_snapshots':False,
        'sources':['https://api.wigle.net/csvFormat-1_6.html']}
    dump(ROOT/'wifi_timestamp_audit.json',audit)
    with ZipFile(io.BytesIO(data)) as outer:
        text=outer.read(CHAT).decode('utf-8-sig')
        messages=parse_messages(text)
        active=[m for m in messages if m['dt']>=CUTOFF]
        refs=[]
        for m in active:
            name=m['body'].splitlines()[0]
            if name.endswith(' (file attached)'):
                name=name[:-len(' (file attached)')]
                refs.append({**m,'name':name,'present':name in outer.namelist()})
        missing=[r['name'] for r in refs if not r['present']]
        if missing:raise ValueError('Referenced attachments missing: '+repr(missing))
        selected=[r for r in refs if r['name'].endswith('.zip') or r['name'].endswith('.gz')]
        # Keep only the acquisition conversation and location list, excluding homework and other chat material.
        evidence=[m for m in active if any(r['stamp']==m['stamp'] and r['sender']==m['sender'] and r['body']==m['body'] for r in selected) or m['stamp']=='15/11/2026, 00:26']
        (raw/'relevant_chat.txt').write_text('\n'.join(m['stamp']+' - '+m['sender']+': '+m['body'] for m in evidence)+'\n',encoding='utf-8')
        locations=location_rows(messages)
        by_stop={l['stop_id']:l for l in locations}
        corrected_locations=[{'corrected_location_number':l['corrected_location_number'],
            'original_source_location_number':l['original_source_location_number'],
            'original_label':l['original_label'],'location_label':l['location_label'],
            'candidate_recording_id':l['stop_id'],'recording_alignment_status':l['alignment_status'],
            'numbering_correction_source':'user: typo; drop subsequent labels by 1',
            'source_message_hk':'2026-11-15T00:26:00+08:00'} for l in locations if l['original_label']]
        sessions=[];all_samples=[];exclusions=[];quality=[];interval_output=[];hashes=[]
        bm=0;acc=0;wifi_ref=None
        for r in selected:
            name=r['name'];payload=outer.read(name)
            (raw/'attachments').mkdir(exist_ok=True)
            if Path(name).name!=name:raise ValueError('Unsafe archive path')
            (raw/'attachments'/name).write_bytes(payload)
            hashes.append({'file':str(Path('raw/attachments')/name),'sha256':digest(payload),'size_bytes':len(payload)})
            if name.endswith('.gz'):
                if wifi_ref:raise ValueError('Unexpected second Wi-Fi log')
                wifi_ref=(name,payload);continue
            with ZipFile(io.BytesIO(payload)) as z:
                if z.testzip():raise ValueError('Nested ZIP integrity failed')
                is_bm='Barometer.csv' in z.namelist()
                if is_bm:bm+=1;sid=f'BM{bm:02}';label=''
                else:acc+=1;sid=f'ACC{acc:02}';label=name.split(' 2026-',1)[0]
                events=list(csv.DictReader(io.StringIO(z.read('meta/time.csv').decode('utf-8-sig'))))
                ints=intervals(events)
                dev=dict(list(csv.reader(io.StringIO(z.read('meta/device.csv').decode('utf-8-sig'))))[1:])
                start=min(Decimal(a['system time']) for a,b in ints);end=max(Decimal(b['system time']) for a,b in ints)
                session={'session_id':sid,'kind':'barometer_magnetometer_stop' if is_bm else 'accelerometer_movement',
                    'source_zip':name,'source_sha256':digest(payload),'chat_sent_hk':r['dt'].isoformat(),
                    'device_model':dev.get('deviceModel',''),'device_brand':dev.get('deviceBrand',''),'app_version':dev.get('version',''),
                    'start_epoch_s':str(start),'end_epoch_s':str(end),'start_utc':iso(start),'end_utc':iso(end),
                    'start_hk':iso(start,HK),'end_hk':iso(end,HK),'recorded_duration_s':str(sum(Decimal(b['experiment time'])-Decimal(a['experiment time']) for a,b in ints)),
                    'interval_count':len(ints),'original_acc_label':label,'location_label':by_stop[sid]['location_label'] if is_bm else '',
                    'label_status':by_stop[sid]['label_status'] if is_bm else 'movement_endpoints_provisional',
                    'original_source_location_number':by_stop[sid]['original_source_location_number'] if is_bm else '',
                    'corrected_location_number':by_stop[sid]['corrected_location_number'] if is_bm else '',
                    'location_alignment_status':'unresolved_26_recordings_25_corrected_locations',
                    'clock_status':'device_wall_clock_not_independently_synchronized'}
                sessions.append(session)
                for k,(a,b) in enumerate(ints,1):
                    interval_output.append({'session_id':sid,'interval_id':k,'experiment_start_s':a['experiment time'],'experiment_end_s':b['experiment time'],
                        'start_epoch_s':a['system time'],'end_epoch_s':b['system time'],'start_utc':iso(a['system time']),'end_utc':iso(b['system time']),
                        'clock_end_minus_start_mapping_s':str(Decimal(b['system time'])-Decimal(a['system time'])-(Decimal(b['experiment time'])-Decimal(a['experiment time'])))})
                for filename,sensor in SENSORS.items():
                    if filename not in z.namelist():continue
                    rdr=csv.reader(io.StringIO(z.read(filename).decode('utf-8-sig')));header=next(rdr)
                    raw_rows=list(rdr);kept=[];excluded=Counter();seen=set();raw_values=[];nonmono=0;prev=None
                    for row_number,row in enumerate(raw_rows,2):
                        reasons=[]
                        try:
                            values=[float(x) for x in row]
                            if len(values)!=len(header) or len(values)!=(2 if sensor=='barometer' else 4):reasons.append('wrong_column_count')
                            if not all(math.isfinite(v) for v in values):reasons.append('nonfinite_value')
                            t=Decimal(row[0])
                            if not t.is_finite():reasons.append('nonfinite_time')
                            elif t<0:reasons.append('negative_experiment_time')
                            selected_int=None
                            if t.is_finite():
                                selected_int=next(((a,b,k) for k,(a,b) in enumerate(ints,1) if Decimal(a['experiment time'])<=t<=Decimal(b['experiment time'])),None)
                                if not selected_int:reasons.append('outside_recorded_interval')
                            if len(values)>1 and math.isfinite(values[1]):raw_values.append(values[1])
                        except (ValueError,ArithmeticError,IndexError):
                            reasons.append('unparseable_numeric_row');values=[];selected_int=None
                        key=tuple(row)
                        if key in seen:reasons.append('exact_duplicate_same_time_and_values')
                        seen.add(key)
                        if reasons:
                            reasons=list(dict.fromkeys(reasons));excluded.update(reasons)
                            exclusions.append({'session_id':sid,'sensor':sensor,'source_zip':name,'source_csv':filename,'source_row':row_number,
                                'reasons':';'.join(reasons),'source_columns_json':json.dumps(header,ensure_ascii=False),'source_values_json':json.dumps(row,ensure_ascii=False)})
                            continue
                        a,b,k=selected_int
                        if prev is not None and t<=prev:nonmono+=1
                        prev=t
                        epoch=Decimal(a['system time'])+t-Decimal(a['experiment time'])
                        record={'session_id':sid,'sensor':sensor,'source_zip':name,'source_csv':filename,'source_row':row_number,'interval_id':k,
                            'relative_time_s':row[0],'timestamp_epoch_s':str(epoch),'timestamp_utc':iso(epoch),'timestamp_hk':iso(epoch,HK),
                            'x':row[1],'y':row[2] if len(row)>2 else '', 'z':row[3] if len(row)>3 else '', 'unit':UNITS[sensor],
                            'vector_magnitude':format(math.sqrt(sum(v*v for v in values[1:4])),'.12g') if len(values)==4 else '',
                            'source_values_json':json.dumps(row,ensure_ascii=False),'quality_flags':'clock_not_independently_synchronized'}
                        kept.append(record);all_samples.append(record)
                    kept.sort(key=lambda q:(Decimal(q['relative_time_s']),q['source_row']))
                    vals=[float(q['x']) for q in kept]
                    diffs=[float(Decimal(b['relative_time_s'])-Decimal(a['relative_time_s'])) for a,b in zip(kept,kept[1:]) if Decimal(b['relative_time_s'])>Decimal(a['relative_time_s'])]
                    duration=float(session['recorded_duration_s']);span=float(Decimal(kept[-1]['relative_time_s'])-Decimal(kept[0]['relative_time_s'])) if len(kept)>1 else 0
                    flags=[]
                    if excluded:flags.append('rows_quarantined')
                    if span<0.8*duration:flags.append('samples_cover_less_than_80_percent_of_recorded_duration')
                    if nonmono:flags.append('nonmonotonic_source_order_sorted_in_clean_output')
                    quality.append({'session_id':sid,'sensor':sensor,'source_rows':len(raw_rows),'kept_rows':len(kept),'excluded_rows':len(raw_rows)-len(kept),
                        'exclusion_reason_counts':json.dumps(dict(excluded),sort_keys=True),'first_relative_time_s':kept[0]['relative_time_s'] if kept else '',
                        'last_relative_time_s':kept[-1]['relative_time_s'] if kept else '', 'observed_span_s':span,'recorded_duration_s':duration,
                        'median_sample_interval_s':statistics.median(diffs) if diffs else '', 'raw_x_median':statistics.median(raw_values) if raw_values else '',
                        'clean_x_median':statistics.median(vals) if vals else '', 'clean_x_min':min(vals) if vals else '', 'clean_x_max':max(vals) if vals else '',
                        'magnitude_median':statistics.median(float(q['vector_magnitude']) for q in kept) if sensor!='barometer' and kept else '',
                        'flags':';'.join(flags)})
        all_samples.sort(key=lambda q:(Decimal(q['timestamp_epoch_s']),q['session_id'],q['sensor'],q['source_row']))
        emit(ROOT/'sessions.csv',sessions)
        emit(ROOT/'recording_intervals.csv',interval_output)
        emit(ROOT/'locations_provisional.csv',locations)
        emit(ROOT/'corrected_location_list.csv',corrected_locations)
        emit(ROOT/'sensor_samples.csv',all_samples)
        emit(ROOT/'sensor_quality.csv',quality)
        emit(ROOT/'excluded_sensor_rows.csv',exclusions)
        emit(ROOT/'source_files.csv',hashes)
        for sensor in UNITS:
            emit(ROOT/'sensors'/f'{sensor}.csv',[r for r in all_samples if r['sensor']==sensor],list(all_samples[0]))
        edges=make_edges(sessions,by_stop)
        emit(ROOT/'accelerometer_edges.csv',edges)
        augmentation=make_requested_augmentation(all_samples,edges,by_stop)
        missing_edges=[{'from_stop_id':'BM15','to_stop_id':'BM16','status':'no_accelerometer_attachment_for_P15','notes':'Vending 2 to 4F down escalator landing; do not fabricate a transition.'},
                       {'from_stop_id':'BM13','to_stop_id':'BM17','status':'not_measured_derived_copy_available','notes':'User-requested copied proxy SYN_ACC_5F_CONNECTOR is in augmentation/. Assumed physical map connector, not a historical recorded visit.'}]
        emit(ROOT/'missing_movements.csv',missing_edges)
        wifi_summary=clean_wifi(wifi_ref,sessions,interval_output,audit)
        summary={'dataset_version':'v3_corrected_list_numbering_alignment_pending','augmentation':augmentation,
            'source':str(source),'source_sha256':digest(data),'source_bytes':len(data),'chat_cutoff_hk':CUTOFF.isoformat(),
            'all_referenced_attachments_after_cutoff':len(refs),'referenced_attachments_present':sum(r['present'] for r in refs),
            'sensor_zip_count':bm+acc,'barometer_magnetometer_stops':bm,'accelerometer_segments':acc,'location_labels_present':sum(bool(x['original_label']) for x in locations),
            'numbering_correction':'source1..3 unchanged; source5..26 -> corrected4..25',
            'corrected_location_count':len(corrected_locations),
            'recording_alignment_status':'unresolved_26_recordings_25_corrected_locations',
            'currently_unmatched_recording_ids':[x['stop_id'] for x in locations if not x['original_label']],
            'extra_repeat_recording_identified':False,
            'devices':sorted({(s['kind'],s['device_model']) for s in sessions}),
            'sensor_rows_source':sum(q['source_rows'] for q in quality),'sensor_rows_clean':len(all_samples),'sensor_rows_excluded':len(exclusions),
            'sensor_counts':dict(Counter(s['sensor'] for s in all_samples)),
            'exclusion_reason_counts':dict(Counter(reason for r in exclusions for reason in r['reasons'].split(';'))),
            'edge_timing_status_counts':dict(Counter(e['timing_status'] for e in edges)),
            'wifi':wifi_summary,
            'pressure_clean_medians_hpa':{q['session_id']:q['clean_x_median'] for q in quality if q['sensor']=='barometer'},
            'uncertainties':['Numbering typo corrected; 26 actual stop recordings versus 25 corrected named locations still require extra/repeat/test alignment','BM04 currently unmatched in retained candidate mapping; not identified as the actual extra recording','All file-to-location matches remain provisional; corrected list number is not raw BM ordinal','Device clocks were not independently synchronized','ACC16-18 measured after both BM endpoint visits; route-supported revisit, not simultaneous data','WiFi UTC format verified; stored location time is not radio acquisition time; selective persistence prevents complete fingerprints','Exact installed WiGLE 2.111 source/binary not matched to inspected upstream source','No numeric distances or map coordinates inferred','Upper-floor connector proxy copied from ACC15 at user request; target times unknown; same-distance/same-walker assumption unmeasured']}
        dump(ROOT/'summary.json',summary)
        make_svg(sessions,quality,edges)
        write_readme(summary)
        validate()
        print(json.dumps(summary,indent=2))

def make_edges(sessions,locations):
    stops={s['session_id']:s for s in sessions if s['session_id'].startswith('BM')}
    out=[]
    for s in sessions:
        if not s['session_id'].startswith('ACC'):continue
        label=s['original_acc_label'];m=re.match(r'P(\d+)(?:-(\d+))?',label)
        a=int(m[1]);b=int(m[2]) if m[2] else a+1
        before=stops[f'BM{a:02}'];after=stops[f'BM{b:02}']
        start=Decimal(s['start_epoch_s']);end=Decimal(s['end_epoch_s'])
        left=Decimal(before['end_epoch_s']);right=Decimal(after['start_epoch_s'])
        valid=left<=start<=end<=right
        status='between_endpoint_stop_windows' if valid else ('recorded_after_both_endpoint_stops' if start>Decimal(after['end_epoch_s']) else 'overlaps_or_outside_endpoint_windows')
        out.append({'acc_session_id':s['session_id'],'original_acc_label':label,'from_stop_id':f'BM{a:02}','to_stop_id':f'BM{b:02}',
            'from_corrected_location_number':locations[f'BM{a:02}']['corrected_location_number'],
            'to_corrected_location_number':locations[f'BM{b:02}']['corrected_location_number'],
            'location_alignment_status':'unresolved_26_recordings_25_corrected_locations',
            'from_location':locations[f'BM{a:02}']['location_label'],'to_location':locations[f'BM{b:02}']['location_label'],
            'start_hk':s['start_hk'],'end_hk':s['end_hk'],'start_epoch_s':s['start_epoch_s'],'end_epoch_s':s['end_epoch_s'],
            'timing_status':status,'seconds_after_from_stop_end':str(start-left),'seconds_before_to_stop_start':str(right-end),
            'endpoint_label_status':'provisional_user_route_supported' if a in [16,18] else 'provisional_filename_and_chronology',
            'clock_assumption':'Different iPhones; wall clocks not independently synchronized','is_synthetic':False,
            'notes':'Lower-floor down-to-up connector. BM17 upstairs side trip is bypassed. Recording time is retained; no clock offset applied.' if a==16 else ''})
    return out

def make_requested_augmentation(samples,edges,locations):
    """Apply the user's explicit lower-floor-to-upper-floor copy as a proxy."""
    folder=ROOT/'augmentation';folder.mkdir(exist_ok=True)
    parent_id='ACC15';derived_id='SYN_ACC_5F_CONNECTOR'
    source=[r for r in samples if r['session_id']==parent_id and r['sensor']=='accelerometer']
    parent=next(e for e in edges if e['acc_session_id']==parent_id)
    if (parent['from_stop_id'],parent['to_stop_id'])!=('BM16','BM18'):
        raise ValueError('Connector source changed; review explicit copy override')
    common={'is_synthetic':True,'derivation_type':'user_requested_copy','parent_acc_session_id':parent_id,
            'acquisition_group_id':parent_id,'from_stop_id':'BM13','to_stop_id':'BM17',
            'from_corrected_location_number':locations['BM13']['corrected_location_number'],
            'to_corrected_location_number':locations['BM17']['corrected_location_number'],
            'source_from_corrected_location_number':locations['BM16']['corrected_location_number'],
            'source_to_corrected_location_number':locations['BM18']['corrected_location_number'],
            'location_alignment_status':'unresolved_26_recordings_25_corrected_locations',
            'source_from_stop_id':'BM16','source_to_stop_id':'BM18','same_distance_as':'BM16->BM18','distance_m':'',
            'assumption':'user_states_same_distance_and_same_person_walking',
            'intended_use':'assumed_map_connector_or_simulation','historical_visit':False}
    copied=[]
    for n,r in enumerate(source,1):
        copied.append({'derived_sample_id':f'{derived_id}_{n:06}','derived_segment_id':derived_id,**common,
            'source_zip':r['source_zip'],'source_csv':r['source_csv'],'source_row':r['source_row'],
            'source_interval_id':r['interval_id'],'relative_time_s':r['relative_time_s'],
            'timestamp_epoch_s':'','timestamp_utc':'','timestamp_hk':'',
            'source_timestamp_epoch_s':r['timestamp_epoch_s'],'source_timestamp_utc':r['timestamp_utc'],'source_timestamp_hk':r['timestamp_hk'],
            'x':r['x'],'y':r['y'],'z':r['z'],'unit':r['unit'],'vector_magnitude':r['vector_magnitude'],
            'source_values_json':r['source_values_json'],
            'quality_flags':'copied_proxy_not_measured_at_target;absolute_target_time_unknown;shared_acquisition_group_with_parent'})
    emit(folder/'derived_accelerometer_samples.csv',copied)
    extra_fields=['segment_id','derivation_type','parent_acc_session_id','acquisition_group_id','source_from_stop_id','source_to_stop_id',
                  'source_from_corrected_location_number','source_to_corrected_location_number',
                  'same_distance_as','distance_m','assumption','intended_use','historical_visit','source_start_hk','source_end_hk','source_start_epoch_s','source_end_epoch_s']
    fields=list(edges[0])+extra_fields
    augmented=[]
    for e in edges:
        row={k:'' for k in fields};row.update(e)
        row.update({'segment_id':e['acc_session_id'],'derivation_type':'measured','acquisition_group_id':e['acc_session_id'],
                    'intended_use':'recorded_movement','historical_visit':True})
        augmented.append(row)
    row={k:'' for k in fields};row.update(common)
    row.update({'segment_id':derived_id,'acc_session_id':derived_id,
                'from_location':locations['BM13']['location_label'],'to_location':locations['BM17']['location_label'],
                'original_acc_label':'User-requested 5F connector proxy copied from P16-18',
                'timing_status':'target_not_recorded_no_absolute_acquisition_time',
                'endpoint_label_status':'assumed_physical_map_connector_not_chronological_walk',
                'source_start_hk':parent['start_hk'],'source_end_hk':parent['end_hk'],
                'source_start_epoch_s':parent['start_epoch_s'],'source_end_epoch_s':parent['end_epoch_s'],
                'notes':'Exact lower-floor sample copy authorized by user. Numeric distance unknown. Target times blank.'})
    augmented.append(row)
    emit(folder/'augmented_accelerometer_edges.csv',augmented,fields)
    override={'derived_segment_id':derived_id,**common,'source_original_acc_label':parent['original_acc_label'],
        'authorization':'explicit_user_instruction','user_instruction':'its okay, its same distance and same person walking, just dupe it for the escalator',
        'samples_copied':len(copied),'source_table':'sensors/accelerometer.csv',
        'target_absolute_times':'unknown_left_blank','independent_recording':False,
        'grouping_rule':'Derived segment shares acquisition_group_id ACC15 with its parent; keep together in any partition.',
        'note':'BM13->BM17 is an assumed 5F physical connector, not the actual consecutive chronological walk.'}
    dump(folder/'user_requested_override.json',override)
    return {'derived_segment_id':derived_id,'parent_acc_session_id':parent_id,'derived_accelerometer_segments':1,
            'derived_accelerometer_samples':len(copied),'augmented_edge_count':len(augmented),
            'observed_sample_tables_unchanged':True,'target_acquisition_times':'unknown_left_blank',
            'intended_use':common['intended_use'],'historical_visit':False}

def clean_wifi(wifi_ref,sessions,recording_intervals,audit):
    if not wifi_ref:raise ValueError('Wi-Fi log missing')
    name,payload=wifi_ref
    text=gzip.decompress(payload).decode('utf-8-sig')
    metadata,table=text.split('\n',1)
    (ROOT/'raw'/'wifi_decompressed.csv').write_text(text,encoding='utf-8')
    (ROOT/'wifi').mkdir(exist_ok=True)
    (ROOT/'wifi'/'export_metadata.txt').write_text(metadata+'\n',encoding='utf-8')
    reader=csv.DictReader(io.StringIO(table));source_fields=reader.fieldnames
    obs=[];excluded=[];nonwifi=[];seen=set();reason_counts=Counter()
    for source_row,row in enumerate(reader,3):
        raw=json.dumps(row,ensure_ascii=False,sort_keys=True)
        common={'source_log':name,'source_row':source_row,'source_values_json':raw}
        if row.get('Type')!='WIFI':
            nonwifi.append({**common,**row});continue
        reasons=[]
        key=tuple(row.get(k) for k in source_fields)
        if key in seen:reasons.append('exact_duplicate_export_row')
        seen.add(key)
        try:
            dt=datetime.strptime(row['FirstSeen'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if not math.isfinite(float(row['RSSI'])):reasons.append('nonfinite_rssi')
        except (ValueError,TypeError,KeyError):reasons.append('unparseable_timestamp_or_rssi');dt=None
        if reasons:
            excluded.append({**common,'reasons':';'.join(reasons)});reason_counts.update(reasons);continue
        obs.append({'wifi_observation_id':f'W{source_row:06}','source_log':name,'source_row':source_row,
            **row,'observation_epoch_s':str(int(dt.timestamp())),'observation_time_utc':dt.isoformat(),
            'observation_time_hk':dt.astimezone(HK).isoformat(),'timestamp_interpretation':'UTC verified by official WiGLE CSV v1.6 specification',
            'timestamp_semantics':'persisted_observation_location_time',
            'quality_flags':'radio_acquisition_time_unavailable;cross_device_clock_alignment_unverified;selectively_persisted_not_complete_scan;gps_not_indoor_ground_truth',
            'clock_status':'Samsung wall clock not independently synchronized to iPhones',
            'source_values_json':raw})
    intervals=[i for i in recording_intervals if i['session_id'].startswith('BM')]
    associations=[];orphans=[];counts=Counter();seconds=defaultdict(set)
    earliest=min(Decimal(i['start_epoch_s']) for i in intervals);latest=max(Decimal(i['end_epoch_s']) for i in intervals)
    for r in obs:
        t=Decimal(r['observation_epoch_s'])
        matches=[i for i in intervals if Decimal(i['start_epoch_s'])<=t<=Decimal(i['end_epoch_s'])]
        for i in matches:
            associations.append({'wifi_observation_id':r['wifi_observation_id'],'session_id':i['session_id'],'interval_id':i['interval_id'],
                'observation_epoch_s':str(t),'observation_time_hk':r['observation_time_hk'],
                'association_status':'provisional_FirstSeen_within_stop_recording_interval',
                'limitations':'Not proof of fresh scan, complete fingerprint, synchronized clocks, or known phone position.'})
            counts[i['session_id']]+=1;seconds[i['session_id']].add(t)
        if not matches:
            orphans.append({'wifi_observation_id':r['wifi_observation_id'],'observation_epoch_s':str(t),
                'reason':'outside_stop_session_time_span' if not earliest<=t<=latest else 'between_stop_recording_windows',
                'notes':'Retained observation; not assigned by nearest-neighbor or interpolation.'})
    coverage=[{'session_id':i['session_id'],'interval_id':i['interval_id'],'provisional_wifi_rows':counts[i['session_id']],
               'distinct_FirstSeen_seconds':len(seconds[i['session_id']]),'coverage_status':'no_FirstSeen_rows_in_exact_window' if not counts[i['session_id']] else 'FirstSeen_rows_present_not_verified_scan_coverage'} for i in intervals]
    emit(ROOT/'wifi'/'observations.csv',obs)
    emit(ROOT/'wifi'/'excluded_rows.csv',excluded,['source_log','source_row','source_values_json','reasons'])
    emit(ROOT/'wifi'/'non_wifi_rows.csv',nonwifi)
    emit(ROOT/'wifi'/'stop_associations_provisional.csv',associations)
    emit(ROOT/'wifi'/'unassigned_observations.csv',orphans)
    emit(ROOT/'wifi'/'stop_coverage_provisional.csv',coverage)
    return {'source_log':name,'source_data_rows':len(obs)+len(excluded)+len(nonwifi),'wifi_rows_clean':len(obs),'wifi_rows_excluded':len(excluded),
        'non_wifi_rows_separated':len(nonwifi),'wifi_exclusion_reasons':dict(reason_counts),'unique_bssids':len({r['MAC'] for r in obs}),
        'provisionally_associated_rows':len(associations),'stops_with_candidate_rows':sum(bool(r['provisional_wifi_rows']) for r in coverage),
        'unassigned_rows':len(orphans),'unassigned_reason_counts':dict(Counter(r['reason'] for r in orphans)),
        'zero_row_stops':[r['session_id'] for r in coverage if not r['provisional_wifi_rows']],
        'timestamp_audit_file':'wifi_timestamp_audit.json','first_seen_min':min(r['FirstSeen'] for r in obs),'first_seen_max':max(r['FirstSeen'] for r in obs)}

def make_svg(sessions,quality,edges):
    stops=[s for s in sessions if s['session_id'].startswith('BM')]
    pressures={q['session_id']:q['clean_x_median'] for q in quality if q['sensor']=='barometer'}
    mags={q['session_id']:q['magnitude_median'] for q in quality if q['sensor']=='magnetometer'}
    lo=min(float(s['start_epoch_s']) for s in sessions);hi=max(float(s['end_epoch_s']) for s in sessions)
    width=1200;height=690;left=80;right=1160
    x=lambda t:left+(float(t)-lo)/(hi-lo)*(right-left)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Arial,sans-serif;fill:#18212b} .small{font-size:11px}.axis{stroke:#bac2cc;stroke-width:1}</style>',
        '<text x="40" y="30" font-size="22">GE2340 — measured stops and movement recordings</text>',
        '<text x="40" y="52" font-size="13">14 Nov 2026, Hong Kong time. Point labels are provisional; device clocks were not independently synchronized.</text>']
    def panel(values,top,bottom,title,color):
        mn=min(values.values());mx=max(values.values());pad=max((mx-mn)*.1,.001);mn-=pad;mx+=pad
        y=lambda v:bottom-(v-mn)/(mx-mn)*(bottom-top)
        out.append(f'<text x="40" y="{top-12}" font-size="14">{title}</text>')
        for j in range(4):
            v=mn+(mx-mn)*j/3;yy=y(v)
            out.append(f'<line x1="{left}" y1="{yy}" x2="{right}" y2="{yy}" class="axis"/><text x="5" y="{yy+4}" class="small">{v:.2f}</text>')
        for s in stops:
            xx=x(s['start_epoch_s']);yy=y(values[s['session_id']]);lab=s['session_id']
            out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="4" fill="{color}"><title>{lab}: {values[lab]:.5f}; {html.escape(s["location_label"])}</title></circle>')
            out.append(f'<text x="{xx:.2f}" y="{yy-8:.2f}" class="small" text-anchor="middle">{lab[2:]}</text>')
    panel(pressures,105,265,'Pressure median per stop (hPa); separate dots, no invented readings between stops','#126782')
    panel(mags,330,465,'Magnetic field magnitude median per stop (µT)','#7654a3')
    out.append('<text x="40" y="505" font-size="14">Recorded intervals: teal = stationary barometer/magnetometer; orange = accelerometer movement</text>')
    for s in sessions:
        is_bm=s['session_id'].startswith('BM');yy=530 if is_bm else 570;xx=x(s['start_epoch_s']);ww=max(x(s['end_epoch_s'])-xx,2)
        out.append(f'<rect x="{xx:.2f}" y="{yy}" width="{ww:.2f}" height="12" fill="{"#126782" if is_bm else "#d97915"}"><title>{s["session_id"]} {html.escape(s["original_acc_label"] or s["location_label"])}</title></rect>')
        out.append(f'<text x="{xx:.2f}" y="{yy-4}" class="small">{s["session_id"][2:] if is_bm else html.escape(s["original_acc_label"].split()[0])}</text>')
    for j in range(9):
        t=lo+(hi-lo)*j/8;xx=x(t)
        out.append(f'<line x1="{xx}" y1="595" x2="{xx}" y2="601" class="axis"/><text x="{xx}" y="617" class="small" text-anchor="middle">{datetime.fromtimestamp(t,HK).strftime("%H:%M:%S")}</text>')
    out.extend(['<text x="40" y="650" font-size="13">BM16 (4F) → BM17 (5F) → BM18 (4F): pressure supports the extra upstairs visit.</text>',
                '<text x="40" y="673" font-size="13">ACC P16–18 is a later visit; its user-requested 5F copy is separate augmentation with no timeline acquisition time.</text>','</svg>'])
    (ROOT/'diagnostic_timeline.svg').write_text('\n'.join(out),encoding='utf-8')

def write_readme(s):
    p=s['pressure_clean_medians_hpa'];w=s['wifi']
    text=f'''# GE2340 cleaned acquisition, 14 November 2026 — v3

The exported files are readable and internally coherent enough for analysis. This is a cleaned acquisition with provisional location associations, not a fully labeled or independently tested training set.

## Evidence and scope

- Starts at WhatsApp messages at 21:10 HK, retaining the first attached recording's actual start at 21:09:41.933. Chat send times and filenames never replace recording metadata.
- {s['barometer_magnetometer_stops']} actual barometer/magnetometer stop recordings, {s['accelerometer_segments']} actual accelerometer movement recordings, and one WiGLE export. All 49 sensor ZIPs pass integrity checks. All {s['all_referenced_attachments_after_cutoff']} attachments referenced after the cutoff are present; unrelated homework is excluded from processing.
- The user corrected a numbering typo: source Dat1–3 remain 1–3, source Dat5 becomes corrected Dat4, and source Dat26 becomes corrected Dat25. `corrected_location_list.csv` contains the complete corrected sequence **1–25**; corrected Dat4 is **study room 11**.
- There are still **26 real stop recordings versus 25 named locations**. The extra/repeat/test recording has not been identified. All recording-to-name links are explicitly provisional. Raw BM IDs, original chat and P filenames are unchanged; corrected location numbers are separate display fields, not raw recording ordinals. In the retained candidate mapping BM04 is currently unmatched, pending alignment. This does not identify BM04 as the actual extra visit.
- Measured values, units and sample tables remain unchanged; metadata tables receive separate corrected display-number fields. Derived timestamps and magnitudes are separate fields; the requested copied 5F connector is in `augmentation/`. No smoothing, resampling, numeric distance estimation or model training was performed.
- Three distinct phones: barometer/magnetometer and accelerometer use different iPhones, Wi-Fi uses Samsung. Their wall clocks were not independently synchronized.

## What the escalator readings show

Under the retained candidate alignment, pressure medians are BM15 vending 2 **{p['BM15']:.4f} hPa**; BM16 4F down landing **{p['BM16']:.4f}**; BM17 5F up landing **{p['BM17']:.4f}**; BM18 4F up landing **{p['BM18']:.4f}**. The rise, fall, rise supports the user's descent / return upstairs / descent route. Floor labels come from route context and user clarification; pressure supports consistency rather than independently proving exact floor identities. The numbering correction does not force shifted location names onto raw chronological recording ordinals while the extra-recording alignment remains unresolved.

`P16-18 (esca bawah)` retains its original filename and recording time 21:27:39, after BM18 at 21:24:33. Its candidate raw endpoints remain BM16→BM18 (corrected display Dat15→Dat17). At the user's explicit request, its **{s['augmentation']['derived_accelerometer_samples']} accepted ACC15 samples are copied exactly** into `SYN_ACC_5F_CONNECTOR`, representing the assumed physical map connector BM13→BM17 (corrected display Dat12→Dat16, 5F down→up). All display-number associations remain provisional pending recording alignment. The copy is labeled `is_synthetic=true`, `derivation_type=user_requested_copy`, `historical_visit=false`, and `intended_use=assumed_map_connector_or_simulation`. This physical connector is not the actual chronological walk, which included vending machines and floor changes.

Same distance and same walker are recorded as user assumptions; numeric distance remains blank. Target acquisition times remain blank, with original times retained in explicit `source_*` columns. The copy shares `acquisition_group_id=ACC15` with its parent, so both remain together in any partition. Measured tables still have 23 accelerometer segments and {s['sensor_rows_clean']:,} total sensor readings; the augmented manifest has 24 edges, including one proxy. No separate P15 recording is present for vending 2 → 4F down landing. `accelerometer_edges.csv` contains only measured segments and timing checks.

## Cleaning rules and row accounting

- Recorded START/PAUSE intervals map experiment-relative seconds to device wall-clock epoch, UTC and HK. Every event is retained in `recording_intervals.csv`.
- Negative experiment times, outside-interval samples, nonfinite/unparseable values, and exact duplicate time-and-value rows are quarantined in `excluded_sensor_rows.csv` with the original values and source row. Repeated values at different timestamps are retained.
- Input sensor readings: **{s['sensor_rows_source']:,}**; accepted: **{s['sensor_rows_clean']:,}**; quarantined: **{s['sensor_rows_excluded']:,}**. Readings are never silently discarded. `sensor_quality.csv` includes raw and cleaned medians and per-sensor time coverage.
- Barometer files contain nine original readings each, including one negative-time reading. Accepted pressure readings therefore cover approximately 0.5–7 seconds, shorter than the roughly ten-second magnetometer interval. Rates are not forced to match.
- Accelerometer magnitude includes gravity; it is not linear acceleration, distance, or a step count. Magnetic vector axes depend on phone orientation. Magnitudes are derived for inspection, not a calibration claim.

## Wi-Fi limitations

The WiGLE CSV has {w['source_data_rows']:,} original data rows; {w['wifi_rows_clean']:,} accepted Wi-Fi observations and {w['non_wifi_rows_separated']} non-Wi-Fi rows separated. Original metadata and column values are retained. See `wifi_timestamp_audit.json` for source-code audit results and clock limitations.

`FirstSeen` is retained under its original name. **UTC is verified by the official WiGLE v1.6 format**; converting it to Hong Kong time adds eight hours and is not a phone-clock adjustment. The audit identifies upstream export time as `persisted_observation_location_time`, rather than radio acquisition time. The exact installed 2.111 source/binary was not matched to the inspected upstream source. Observation persistence is selective: 98.22% of consecutive repeated-BSSID records improve by at least 5 dB. These are incomplete, change-selected observations, not complete fresh fingerprints; do not fill missing access points with -100 dBm or any other assumed absence value.

Visible quality flags are `radio_acquisition_time_unavailable`, `cross_device_clock_alignment_unverified`, `selectively_persisted_not_complete_scan`, and `gps_not_indoor_ground_truth`. GPS coordinates and accuracy are original WiGLE metadata only, **not indoor ground truth or map coordinates**. The original `lt1`/`lt2` labels were retained; English lecture-theatre expansions are explicitly marked as inferred and do not determine floor numbers.

The provisional association file uses exact containment in each recorded stop interval with no nearest-time assignment or interpolation. {w['provisionally_associated_rows']} rows are provisionally associated across {w['stops_with_candidate_rows']} stops, {w['unassigned_rows']:,} remain unassigned. Stops with no exported FirstSeen row in their exact window: **{', '.join(w['zero_row_stops'])}**. An empty window is not proof the phone saw no access points. Presence of a row is not proof of a complete scan. No static stop label is embedded in the Wi-Fi observation table. Timestamp seconds also have up-to-one-second boundary precision; `wifi/audit_per_stop_coverage.csv` keeps any boundary-overlap candidates separate from the exact stored-second matches.

## Files

- `sessions.csv`: source, device, actual recorded times and provisional labels for each ZIP.
- `sensor_samples.csv`, `sensors/*.csv`: accepted samples with units, original relative times, UTC/HK timestamps, source values and vector magnitudes.
- `sensor_quality.csv`, `excluded_sensor_rows.csv`: per-sensor checks and full quarantine records.
- `locations_provisional.csv`: source descriptions, translated labels, floor candidates and uncertainty; coordinates remain blank.
- `corrected_location_list.csv`: corrected 1–25 list, original source numbers and explicit unresolved candidate-recording links.
- `accelerometer_edges.csv`, `missing_movements.csv`: actual movement recordings, candidate endpoints, timing checks and gaps.
- `augmentation/derived_accelerometer_samples.csv`: 664 exact copied proxy samples, provenance and blank target times.
- `augmentation/augmented_accelerometer_edges.csv`, `augmentation/user_requested_override.json`: 23 measured edges plus the copied proxy and its authorization/assumptions.
- `wifi/observations.csv`: accepted exported Wi-Fi rows; `non_wifi_rows.csv` and `excluded_rows.csv` keep other input rows accountable.
- `wifi/stop_associations_provisional.csv`, `stop_coverage_provisional.csv`, `unassigned_observations.csv`: provisional exact-window matches and gaps.
- `diagnostic_timeline.svg`: self-contained plot of measured pressure, magnetic magnitude and recording intervals.
- `summary.json`, `validation.json`, `source_files.csv`: machine-readable counts and integrity evidence.
- `raw/`: byte-identical original export and selected sensor attachments, relevant chat, original decompressed Wi-Fi CSV, checksum. **The full preserved export contains unrelated personal chat and homework; keep it private.**

## Reproduce and verify

From this directory:

```bash
python3 clean.py --source 'raw/WhatsApp Chat with GE2340.zip'
python3 clean.py --validate-only
```

These commands work in the original local folder, where the full source export is preserved. **Recipients of the shareable ZIP must separately obtain the original export** and run `python3 clean.py --source '/path/to/WhatsApp Chat with GE2340.zip'` before source-level validation can run; the selected sensor-only attachments in the shareable ZIP do not replace that private source archive. The existing validation record describes the local full-source validation.

To incorporate a completed external timestamp audit, add `--wifi-audit /path/to/audit.json`; the audit is copied into this dataset. Rerunning without that option preserves an existing audit automatically.

Validation checks source/attachment hashes, row accounting, finite values and intervals, Wi-Fi associations, complete corrected numbering 1–25, preserved original source numbers/raw BM IDs, explicit unresolved alignment, unchanged measured counts, exact authorized proxy copy, shared parent/group IDs and blank target acquisition times. It does not certify location ground truth, device clock synchronization, or Wi-Fi scan completeness. Original v1 and v2 archives remain intact; `package.py` creates `ge2340-cleaned-2026-11-14-v3.zip`.

Remaining work is identifying the extra/repeat/test recording to reconcile 26 stop recordings with 25 corrected named locations, independent device-clock alignment, more complete Wi-Fi acquisition if needed, and map coordinates/distances. Preserve one visit as one acquisition unit: adjacent samples from one stop do not constitute independent train/test visits. The shareable ZIP deliberately excludes the full-chat archive and relevant chat transcript; the original remains preserved privately in the local raw folder.
'''
    (ROOT/'README.md').write_text(text,encoding='utf-8')

def load(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def validate():
    s=json.loads((ROOT/'summary.json').read_text());checks=[]
    def check(name,condition):
        checks.append({'check':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    raw=ROOT/'raw'/'WhatsApp Chat with GE2340.zip'
    check('preserved_export_sha256',digest(raw.read_bytes())==s['source_sha256'])
    files=load(ROOT/'source_files.csv')
    check('all_selected_attachment_sha256',all(digest((ROOT/r['file']).read_bytes())==r['sha256'] for r in files))
    ss=load(ROOT/'sessions.csv');ints=load(ROOT/'recording_intervals.csv');samples=load(ROOT/'sensor_samples.csv');excluded=load(ROOT/'excluded_sensor_rows.csv');quality=load(ROOT/'sensor_quality.csv')
    check('49_real_sensor_sessions',len(ss)==49 and sum(r['kind']=='barometer_magnetometer_stop' for r in ss)==26)
    check('sensor_reading_row_accounting',s['sensor_rows_source']==len(samples)+len(excluded)==sum(int(q['source_rows']) for q in quality))
    expected={(r['session_id'],f) for r in ss for f in (['Barometer.csv','Magnetometer.csv'] if r['kind']=='barometer_magnetometer_stop' else ['Accelerometer.csv'])}
    actual=Counter((r['session_id'],r['source_csv']) for r in samples+excluded)
    check('all_75_sensor_csvs_accounted',set(actual)==expected and len(expected)==75)
    with ZipFile(raw) as z:
        original={}
        for session in ss:
            with ZipFile(io.BytesIO(z.read(session['source_zip']))) as inner:
                check('zip_integrity_'+session['session_id'],inner.testzip() is None)
                for f in SENSORS:
                    if f in inner.namelist():
                        rows=list(csv.reader(io.StringIO(inner.read(f).decode('utf-8-sig'))))[1:]
                        original[(session['session_id'],f)]=rows
        accounted=defaultdict(list)
        for r in samples+excluded:
            key=(r['session_id'],r['source_csv']);rn=int(r['source_row'])
            check_values=json.loads(r['source_values_json'])==original[key][rn-2]
            if not check_values:raise AssertionError('Source value mismatch')
            accounted[key].append(rn)
        check('every_original_sensor_row_exactly_once',all(sorted(accounted[k])==list(range(2,len(v)+2)) for k,v in original.items()))
    ib={(r['session_id'],str(r['interval_id'])):r for r in ints}
    valid=True
    for r in samples:
        i=ib[(r['session_id'],r['interval_id'])];t=Decimal(r['relative_time_s']);ep=Decimal(r['timestamp_epoch_s'])
        valid &= t>=0 and Decimal(i['experiment_start_s'])<=t<=Decimal(i['experiment_end_s'])
        valid &= ep==Decimal(i['start_epoch_s'])+t-Decimal(i['experiment_start_s'])
        valid &= all(math.isfinite(float(r[k])) for k in ['x','y','z'] if r[k]!='')
    check('accepted_samples_finite_in_interval_and_exact_epoch_mapping',valid)
    check('per_sensor_partitions',sum(len(load(ROOT/'sensors'/f'{sensor}.csv')) for sensor in UNITS)==len(samples))
    check('all_nonnegative_sensor_times',all(Decimal(r['relative_time_s'])>=0 for r in samples))
    loc=load(ROOT/'locations_provisional.csv')
    corrected=load(ROOT/'corrected_location_list.csv')
    check('corrected_list_complete_unique_1_to_25',[int(r['corrected_location_number']) for r in corrected]==list(range(1,26)))
    check('corrected_source_numbers_preserved',[int(r['original_source_location_number']) for r in corrected]==[1,2,3]+list(range(5,27)))
    check('corrected_Dat4_is_study_room11',next(r for r in corrected if r['corrected_location_number']=='4')['original_label']=='study room 11')
    check('BM04_unmatched_not_missing_location4',next(r for r in loc if r['stop_id']=='BM04')['label_status']=='unmatched_recording_pending_repeat_test_alignment')
    check('raw_BM_ids_not_renumbered',[r['stop_id'] for r in loc]==[f'BM{n:02}' for n in range(1,27)])
    check('all_location_links_explicitly_unresolved',all(r['alignment_status']=='unresolved_26_recordings_25_corrected_locations' for r in loc))
    edges=load(ROOT/'accelerometer_edges.csv')
    check('only_23_real_accelerometer_segments_no_synthetic',len(edges)==23 and {r['acc_session_id'] for r in edges}=={r['session_id'] for r in ss if r['kind']=='accelerometer_movement'} and all(r['is_synthetic']=='False' for r in edges))
    check('measured_lower_floor_connector_not_relabelled_upstairs',sum(r['from_stop_id']=='BM16' and r['to_stop_id']=='BM18' for r in edges)==1 and not any(r['from_stop_id']=='BM13' and r['to_stop_id']=='BM17' for r in edges))
    derived=load(ROOT/'augmentation'/'derived_accelerometer_samples.csv')
    augmented=load(ROOT/'augmentation'/'augmented_accelerometer_edges.csv')
    parent_samples=[r for r in samples if r['session_id']=='ACC15' and r['sensor']=='accelerometer']
    fields=['source_zip','source_csv','source_row','relative_time_s','x','y','z','unit','vector_magnitude','source_values_json']
    check('proxy_exact_copy_of_all_664_accepted_ACC15_samples',len(derived)==len(parent_samples)==664 and all(all(d[k]==p[k] for k in fields) for d,p in zip(derived,parent_samples)))
    check('proxy_unique_sample_ids',len({r['derived_sample_id'] for r in derived})==len(derived))
    check('proxy_target_times_blank_source_times_preserved',all(all(d[k]=='' for k in ['timestamp_epoch_s','timestamp_utc','timestamp_hk']) and all(d['source_'+k]==p[k] for k in ['timestamp_epoch_s','timestamp_utc','timestamp_hk']) for d,p in zip(derived,parent_samples)))
    check('proxy_authorized_derived_target_parent',all(r['is_synthetic']=='True' and r['derivation_type']=='user_requested_copy' and r['parent_acc_session_id']==r['acquisition_group_id']=='ACC15' and r['from_stop_id']=='BM13' and r['to_stop_id']=='BM17' and r['historical_visit']=='False' and r['intended_use']=='assumed_map_connector_or_simulation' and r['distance_m']=='' for r in derived))
    check('proxy_corrected_display_numbers_separate_from_raw_ids',all((r['from_corrected_location_number'],r['to_corrected_location_number'],r['source_from_corrected_location_number'],r['source_to_corrected_location_number'])==('12','16','15','17') for r in derived))
    copied_edges=[r for r in augmented if r['is_synthetic']=='True']
    check('augmented_23_measured_plus_1_proxy_unique_edges',len(augmented)==24 and len(copied_edges)==1 and len({r['segment_id'] for r in augmented})==24)
    check('proxy_edge_no_target_acquisition_times',all(copied_edges[0][k]=='' for k in ['start_hk','end_hk','start_epoch_s','end_epoch_s']))
    check('measured_readings_unchanged_by_augmentation',len(samples)==46124 and len(ss)==49 and s['sensor_counts']=={'barometer':208,'magnetometer':25981,'accelerometer':19935})
    obs=load(ROOT/'wifi'/'observations.csv');assoc=load(ROOT/'wifi'/'stop_associations_provisional.csv');orphan=load(ROOT/'wifi'/'unassigned_observations.csv');others=load(ROOT/'wifi'/'non_wifi_rows.csv');wx=load(ROOT/'wifi'/'excluded_rows.csv')
    check('wifi_input_row_accounting',len(obs)+len(others)+len(wx)==s['wifi']['source_data_rows'])
    wi={r['wifi_observation_id']:r for r in obs}
    check('wifi_association_exact_interval_containment',all(Decimal(ib[(r['session_id'],r['interval_id'])]['start_epoch_s'])<=Decimal(wi[r['wifi_observation_id']]['observation_epoch_s'])<=Decimal(ib[(r['session_id'],r['interval_id'])]['end_epoch_s']) for r in assoc))
    matched={r['wifi_observation_id'] for r in assoc};unmatched={r['wifi_observation_id'] for r in orphan}
    check('wifi_every_observation_matched_or_unassigned',not matched&unmatched and matched|unmatched==set(wi))
    check('wifi_all_associations_explicitly_provisional',all(r['association_status'].startswith('provisional_') for r in assoc))
    dump(ROOT/'validation.json',{'passed':True,'check_count':len(checks),'checks':checks})
    return checks

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--wifi-audit',type=Path)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    if args.validate_only:
        result=validate();print(f'{len(result)} validation checks passed')
    else:
        audit=args.wifi_audit
        if audit is None and (ROOT/'wifi_timestamp_audit.json').exists():audit=ROOT/'wifi_timestamp_audit.json'
        clean(args.source,audit)
