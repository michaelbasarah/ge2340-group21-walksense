#!/usr/bin/env python3
"""Validate source identity and report human label completion, without applying labels."""
import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'phase2/clean-data/2026-11-14'
IDENTITY = {'source_recording_id': 'session_id', 'recording_kind': 'kind',
            'source_zip': 'source_zip', 'source_zip_sha256': 'source_sha256',
            'chat_sent_hk': 'chat_sent_hk', 'actual_recording_start_hk': 'start_hk',
            'actual_recording_end_hk': 'end_hk'}
EDITABLE = ['confirmed_stop_name', 'confirmed_stop_number', 'confirmed_floor',
            'walking_from_stop_name', 'walking_from_stop_number',
            'walking_to_stop_name', 'walking_to_stop_number',
            'repeat_visit_of_source_id', 'recording_status', 'review_notes']

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def validate(path, require_complete=False):
    fields, rows = read(path)
    _, sources = read(DATA / 'sessions.csv')
    byid = {r['session_id']: r for r in sources}
    errors = []
    required = set(IDENTITY) | set(EDITABLE) | {'whatsapp_sender', 'whatsapp_sent_display'}
    if fields is None or len(fields) != len(set(fields)) or set(fields) != required:
        return ['Headers changed; preserve all original template columns.'], 0, 0
    ids = [r['source_recording_id'] for r in rows]
    if len(rows) != 49 or len(set(ids)) != 49 or set(ids) != set(byid):
        errors.append('Expected all 49 unique original source IDs, without added/deleted rows.')
    complete = 0
    for r in rows:
        sid = r['source_recording_id']
        if None in r or any(v is None for v in r.values()):
            errors.append(f'{sid}: malformed CSV row/column count'); continue
        s = byid.get(sid)
        if s is None: continue
        for field, source_field in IDENTITY.items():
            if r[field] != s[source_field]:
                errors.append(f'{sid}: immutable identity/time field changed: {field}')
        status = r['recording_status'].strip()
        if status not in {'', 'valid', 'repeat', 'test', 'uncertain'}:
            errors.append(f'{sid}: status must be valid/repeat/test/uncertain or blank')
        repeat = r['repeat_visit_of_source_id'].strip()
        if repeat and (repeat not in byid or repeat == sid or byid[repeat]['kind'] != s['kind']):
            errors.append(f'{sid}: repeat reference must name a different source of the same kind')
        if status in {'test', 'uncertain'} and not r['review_notes'].strip():
            errors.append(f'{sid}: test/uncertain requires review_notes')
        if s['kind'] == 'barometer_magnetometer_stop':
            named = bool(r['confirmed_stop_name'].strip() and r['confirmed_floor'].strip())
        else:
            named = bool(r['walking_from_stop_name'].strip() and r['walking_to_stop_name'].strip())
        done = (named and status != 'uncertain') or (status == 'test' and bool(r['review_notes'].strip()))
        complete += int(done)
    if require_complete and complete != 49:
        errors.append(f'Label completion required: only {complete}/49 rows confirmed or documented test.')
    return errors, complete, len(rows)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', nargs='?', type=Path, default=DATA/'RELABEL_TEMPLATE.csv')
    p.add_argument('--require-complete', action='store_true')
    args = p.parse_args()
    try: errors, complete, total = validate(args.csv, args.require_complete)
    except (OSError, UnicodeError, csv.Error) as e:
        print(f'ERROR: {e}', file=sys.stderr); return 1
    for error in errors: print('ERROR:', error, file=sys.stderr)
    print(f'Structural/source-identity check: {"FAIL" if errors else "PASS"}; human labeling: {complete}/{total} rows complete.')
    print('This does not verify physical label correctness or apply labels to measured tables/map.')
    return int(bool(errors))

if __name__ == '__main__': sys.exit(main())
