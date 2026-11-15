#!/usr/bin/env python3
"""Create a blank source-file relabeling sheet once, without old candidate names."""
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parent
target=root/'RELABEL_TEMPLATE.csv'
if target.exists():
    raise SystemExit('RELABEL_TEMPLATE.csv already exists; refusing to overwrite your relabeling work.')
with (root/'sessions.csv').open(newline='',encoding='utf-8') as f:
    sessions=list(csv.DictReader(f))
rows=[]
for s in sorted(sessions,key=lambda s:(Decimal(s['start_epoch_s']),s['session_id'])):
    dt=datetime.fromisoformat(s['chat_sent_hk'])
    display=f"{dt.strftime('%d %b %Y')}, {dt.hour%12 or 12}:{dt.minute:02} {'am' if dt.hour<12 else 'pm'}"
    rows.append({'source_recording_id':s['session_id'],'recording_kind':s['kind'],
        'source_zip':s['source_zip'],'source_zip_sha256':s['source_sha256'],
        'whatsapp_sender':'withheld; match source_recording_id and source_zip','chat_sent_hk':s['chat_sent_hk'],
        'whatsapp_sent_display':display,'actual_recording_start_hk':s['start_hk'],
        'actual_recording_end_hk':s['end_hk'],
        'confirmed_stop_name':'','confirmed_stop_number':'','confirmed_floor':'',
        'walking_from_stop_name':'','walking_from_stop_number':'',
        'walking_to_stop_name':'','walking_to_stop_number':'',
        'repeat_visit_of_source_id':'','recording_status':'','review_notes':''})
with target.open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
assert len(rows)==49
assert len({r['source_recording_id'] for r in rows})==49
assert sum(r['recording_kind']=='barometer_magnetometer_stop' for r in rows)==26
assert sum(r['recording_kind']=='accelerometer_movement' for r in rows)==23
byid={s['session_id']:s for s in sessions}
for r in rows:
    s=byid[r['source_recording_id']]
    assert r['source_zip']==s['source_zip'] and r['source_zip_sha256']==s['source_sha256']
    assert r['chat_sent_hk']==s['chat_sent_hk']
    assert r['actual_recording_start_hk']==s['start_hk'] and r['actual_recording_end_hk']==s['end_hk']
    assert r['whatsapp_sender']
    assert all(r[k]=='' for k in list(r)[9:])
report={'passed':True,'actual_source_rows':49,'stationary_baro_mag_rows':26,'walking_accelerometer_rows':23,
        'unique_source_ids':49,'sort_order':'actual recording START chronology',
        'source_identity_and_timestamp_fields_faithful':True,'old_candidate_names_copied':False,
        'synthetic_proxy_or_wifi_rows_included':False,'confirmation_fields_initially_blank':True}
(root/'relabel_template_validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
