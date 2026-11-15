#!/usr/bin/env python3
"""Package the local app; no sensor exports or browser-local media are included."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parent
target=root.parent/'wayfind-prototype.zip'
allowed=['package.json','server.mjs','build.mjs','package.py','README.md','BUILD_LOG.md','ROUTING.md']
with ZipFile(target,'w',ZIP_DEFLATED) as out:
    for name in allowed:
        path=root/name
        if path.is_file():out.write(path,'wayfind-prototype/'+name)
    for folder in ['dist','tests','qa']:
        for path in sorted((root/folder).rglob('*')):
            if path.is_file():out.write(path,'wayfind-prototype/'+str(path.relative_to(root)))
with ZipFile(target) as check:
    assert check.testzip() is None
print(f'{target} ({target.stat().st_size:,} bytes)')
