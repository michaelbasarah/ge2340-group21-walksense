#!/usr/bin/env python3
"""Index the raw files of 25 Nov: sha256, size, and who sent each file in the group chat (first name only) and when.

    python -I phase2/clean-data/2026-11-25/scripts/index_sources.py [path/to/WhatsApp Chat with GE2340.txt]

The chat export is private and is never copied into the repo; only "first name + chat time" per file name is kept
(raw/source_files.csv). Without the chat path the sender columns stay as they are in the existing CSV (or blank),
so new ZIPs dropped into raw/attachments/ are still hashed and listed.
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATT = ROOT / 'raw' / 'attachments'
OUT = ROOT / 'raw' / 'source_files.csv'
MISSING = ROOT / 'raw' / 'missing_from_export.csv'
OMIT = re.compile(r'^(\d\d)/(\d\d)/(\d{4}), (\d\d:\d\d) - ([^:]+): <Media omitted>\s*$')
CAPTION = re.compile(r'^(.+ 2026-11-25 \d\d-\d\d-\d\d|.+\.xlsx)\s*$')
LINE = re.compile(r'^(\d\d)/(\d\d)/(\d{4}), (\d\d:\d\d) - ([^:]+): (.+?) \(file attached\)\s*$')


def first_name(sender: str) -> str:
    return sender.split('|')[0].strip().split()[0]


def main():
    known = {}
    if OUT.exists():
        known = {r['file']: r for r in csv.DictReader(OUT.open())}
    sent, missing = {}, []
    if len(sys.argv) > 1:
        lines = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace').splitlines()
        for i, ln in enumerate(lines):
            m = LINE.match(ln)
            if m:
                d, mo, y, hm, who, fn = m.groups()
                sent[fn.strip()] = {'sender': first_name(who), 'chat_time_hk': f'{y}-{mo}-{d} {hm}'}
            m = OMIT.match(ln)
            if m and f'{m.group(3)}-{m.group(2)}-{m.group(1)}' == '2026-11-25' and m.group(4) >= '17:30':
                nxt = lines[i + 1] if i + 1 < len(lines) else ''
                cap = CAPTION.match(nxt)
                missing.append({'chat_time_hk': f'2026-11-25 {m.group(4)}', 'sender': first_name(m.group(5)),
                                'caption': cap.group(1).strip() if cap else '',
                                'note': 'not in the export (WhatsApp wrote <Media omitted>)' + ('' if cap else '; no caption, file name unknown')})
        with MISSING.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['chat_time_hk', 'sender', 'caption', 'note'])
            w.writeheader(); w.writerows(missing)
        print(f'wrote {MISSING} ({len(missing)} media messages missing from the export)')
    rows = []
    for f in sorted(ATT.iterdir()):
        if not f.is_file():
            continue
        b = f.read_bytes()
        prev = known.get(f.name, {})
        s = sent.get(f.name, {'sender': prev.get('sender', ''), 'chat_time_hk': prev.get('chat_time_hk', '')})
        rows.append({'file': f.name, 'sha256': hashlib.sha256(b).hexdigest(), 'size_bytes': len(b), **s})
    with OUT.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'sha256', 'size_bytes', 'sender', 'chat_time_hk'])
        w.writeheader(); w.writerows(rows)
    print(f'wrote {OUT} ({len(rows)} files, {sum(1 for r in rows if r["sender"])} with a sender)')


if __name__ == '__main__':
    main()
