#!/usr/bin/env python3
"""Package cleaned data without the full personal chat archive/transcript."""
from pathlib import Path
import hashlib
from zipfile import ZIP_DEFLATED, ZipFile

root=Path(__file__).resolve().parent
target=root.parent/'ge2340-cleaned-2026-11-14-v4.zip'
excluded={Path('raw/WhatsApp Chat with GE2340.zip'),Path('raw/relevant_chat.txt')}
with ZipFile(target,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not p.is_file() or rel in excluded or '__pycache__' in rel.parts:
            continue
        z.write(p,arcname=str(Path('ge2340-cleaned-2026-11-14')/rel))
with ZipFile(target) as z:
    assert z.testzip() is None
    assert not any(n.endswith('/raw/WhatsApp Chat with GE2340.zip') or n.endswith('/raw/relevant_chat.txt') for n in z.namelist())
    assert sum('/raw/attachments/' in n for n in z.namelist())==50
print(target)
print('bytes:',target.stat().st_size)
print('sha256:',hashlib.sha256(target.read_bytes()).hexdigest())
