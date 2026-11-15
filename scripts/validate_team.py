#!/usr/bin/env python3
"""Check included raw/hash provenance, privacy exclusions, and current template structure."""
import csv
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile
from validate_labels import validate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'phase2/clean-data/2026-11-14'

def main():
    errors = []
    with (DATA/'source_files.csv').open(newline='') as f: raw = list(csv.DictReader(f))
    for entry in raw:
        p = DATA/entry['file']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != entry['sha256']:
            errors.append(f'Included raw attachment hash mismatch: {entry["file"]}')
        elif p.suffix == '.zip':
            with ZipFile(p) as z:
                if z.testzip() is not None: errors.append(f'Invalid source ZIP: {entry["file"]}')
    feature_manifest = json.loads((DATA/'features/feature_manifest.json').read_text())
    for rel, expected in feature_manifest['source_table_sha256'].items():
        if hashlib.sha256((DATA/rel).read_bytes()).hexdigest() != expected:
            errors.append(f'Feature source table hash mismatch: {rel}')
    forbidden = {'WhatsApp Chat with GE2340.zip', 'relevant_chat.txt', 'WhatsApp Chat with GE2340.txt', 'Groups-26A.xlsx'}
    for p in ROOT.rglob('*'):
        if not p.is_file() or '.git' in p.relative_to(ROOT).parts: continue
        if p.name in forbidden: errors.append(f'Private source must not be present: {p.relative_to(ROOT)}')
        if p.stat().st_size >= 100_000_000: errors.append(f'File exceeds conservative 100 MB limit: {p.relative_to(ROOT)}')
    label_errors, complete, total = validate(DATA/'RELABEL_TEMPLATE.csv')
    errors.extend(label_errors)
    print(f'Included raw attachments: {len(raw)}; feature source hashes: {len(feature_manifest["source_table_sha256"])}')
    print(f'Label rows: {total}; human labeling complete: {complete}/{total} (blank template expected).')
    for error in errors: print('ERROR:', error, file=sys.stderr)
    print('Team checkout integrity:', 'FAIL' if errors else 'PASS')
    print('Private full-source cleaning validation is not rerun by this check.')
    return int(bool(errors))

if __name__ == '__main__': sys.exit(main())
