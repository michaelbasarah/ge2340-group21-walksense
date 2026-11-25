#!/usr/bin/env python3
"""Which recordings of this folder (2026-11-25-spots, the partial WhatsApp export) are already in Dicta's complete
25-Nov dataset (../2026-11-25/raw, including the nested raw/attachments.zip)?

    python -I phase2/clean-data/2026-11-25-spots/scripts/find_duplicates.py

For every phyphox ZIP and WiGLE log in raw/attachments/ (ours) it checks, against every recording in Dicta's raw/:
  1. byte-identical: same SHA-256 of the recording ZIP (for her nested bundle: of the inner ZIP's bytes);
  2. same recording: same deviceModel and phyphox START time within 2 s (a re-export of the same take);
and writes duplicates_vs_2026-11-25.csv (folder root, next to labels_override.csv; clean/ is rebuilt by build_clean.py), one row per file of ours, with status 'byte_identical',
'same_recording' or 'unique', the matching file of hers and her clean-tree folder (from her clean/manifest.csv).
The day-3 session `25spots` (phase2/new/day3/config.json, `exclude_sources`) leaves every non-unique recording out of
the training set. Nothing is deleted or modified: both raw folders are only read.

NOTE 26 Nov: the 36 byte_identical ZIPs were deleted from raw/attachments/ (PROCESS-LOG entry 68). Do not rerun this script
now: it would see only the 16 files left and overwrite the CSV, losing the 36 rows day3 `exclude_sources` reads and the
column `deleted_2026-11-26`. The CSV is the record.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT / 'raw' / 'attachments'
THEIRS_ROOT = ROOT.parent / '2026-11-25'
THEIRS = THEIRS_ROOT / 'raw'
OUT = ROOT / 'duplicates_vs_2026-11-25.csv'          # not in clean/: build_clean.py rewrites clean/ from scratch
HK = timezone(timedelta(hours=8))
SAME_START_S = 2.0


def phyphox_meta(b: bytes):
    """(deviceModel, START epoch) of one phyphox ZIP, or None if it is not a recording (e.g. a bundle of ZIPs)."""
    zf = zipfile.ZipFile(io.BytesIO(b))
    if 'meta/device.csv' not in zf.namelist():
        return None
    dev = dict(r for r in csv.reader(io.TextIOWrapper(zf.open('meta/device.csv'), 'utf-8')) if len(r) >= 2).get('deviceModel', '?')
    start = None
    for r in list(csv.reader(io.TextIOWrapper(zf.open('meta/time.csv'), 'utf-8')))[1:]:
        if r and r[0].upper() == 'START':
            start = float(r[2])
            break
    return dev, start


def recordings(folder: Path, nested: bool):
    out = []

    def handle(b: bytes, name: str, container: str):
        meta = phyphox_meta(b)
        if meta is None:
            if nested:
                zf = zipfile.ZipFile(io.BytesIO(b))
                for n in zf.namelist():
                    if n.lower().endswith('.zip'):
                        handle(zf.read(n), Path(n).name, name)
            return
        out.append({'file': name, 'container': container, 'sha256': hashlib.sha256(b).hexdigest(),
                    'device_model': meta[0], 'start_epoch': meta[1], 'kind': 'phyphox'})

    for p in sorted(folder.iterdir()):
        b = p.read_bytes()
        if p.suffix.lower() == '.zip':
            handle(b, p.name, '')
        elif p.suffix.lower() == '.gz':          # WiGLE log: hash only (compressed and decompressed)
            out.append({'file': p.name, 'container': '', 'sha256': hashlib.sha256(b).hexdigest(),
                        'sha256_gunzip': hashlib.sha256(gzip.decompress(b)).hexdigest(),
                        'device_model': '', 'start_epoch': None, 'kind': 'wigle'})
    return out


def main():
    ours, theirs = recordings(OURS, nested=False), recordings(THEIRS, nested=True)
    for t in theirs:
        if t['kind'] == 'wigle':
            t['sha256_gunzip'] = hashlib.sha256(gzip.decompress((THEIRS / t['file']).read_bytes())).hexdigest()
    folder_of = {}
    for r in csv.DictReader(open(THEIRS_ROOT / 'clean' / 'manifest.csv')):
        folder_of[r['source_zip']] = f"{r['folder']}/{r['phone']}"
    by_sha = {t['sha256']: t for t in theirs}
    by_gz = {t['sha256_gunzip']: t for t in theirs if t['kind'] == 'wigle'}
    rows = []
    for o in ours:
        m, status = by_sha.get(o['sha256']), 'unique'
        if m:
            status = 'byte_identical'
        elif o['kind'] == 'wigle' and o['sha256_gunzip'] in by_gz:
            m, status = by_gz[o['sha256_gunzip']], 'byte_identical_after_gunzip'
        elif o['kind'] == 'phyphox':
            near = [t for t in theirs if t['kind'] == 'phyphox' and t['device_model'] == o['device_model']
                    and t['start_epoch'] is not None and abs(t['start_epoch'] - o['start_epoch']) <= SAME_START_S]
            if near:
                m, status = near[0], 'same_recording'
        st = o['start_epoch']
        rows.append({'source_zip': o['file'], 'kind': o['kind'], 'device_model': o['device_model'],
                     'start_hk': datetime.fromtimestamp(st, HK).strftime('%H:%M:%S') if st else '',
                     'start_epoch': f'{st:.3f}' if st else '', 'sha256': o['sha256'], 'status': status,
                     'dicta_file': m['file'] if m else '', 'dicta_container': m['container'] if m else '',
                     'dicta_start_diff_s': f"{m['start_epoch'] - st:.3f}" if m and st and m['start_epoch'] else '',
                     'dicta_clean_folder': folder_of.get(m['file'], '') if m else ''})
    with OUT.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f'ours {len(ours)} files, Dicta {len(theirs)} recordings/logs (nested included)')
    print(dict(Counter((r['status'], r['device_model']) for r in rows)))
    print('wrote', OUT)


if __name__ == '__main__':
    main()
