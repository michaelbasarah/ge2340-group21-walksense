#!/usr/bin/env python3
"""Add a teammate's WhatsApp export of the 25-Nov NIGHT run to this folder: new recordings -> raw/, proposed labels.

    python -I phase2/clean-data/2026-11-25-night/scripts/ingest_export.py "/path/WhatsApp Chat - GE2340 (Tian).zip" [--dry-run]
    python -I phase2/clean-data/2026-11-25-night/scripts/ingest_export.py /path/folder/of/loose/files [--since "2026-11-26 02:40"] [--dry-run]

The source is a WhatsApp export ZIP or a folder of loose downloaded files (not recursive; --since keeps only files
modified after that local time, e.g. to skip older downloads). Byte-identical copies inside the source (a browser's
'name (1).zip' second download) are kept once, under the name without the '(1)'.

Safe with an untrusted export: the export is read with zipfile in memory; nothing in it is extracted, executed or
imported. Only phyphox recordings (meta/device.csv inside) and WiGLE logs are copied; the chat text (_chat.txt),
photos, audio and every other file are ignored.

Steps
1. SHA-256 of every recording in the export against every ZIP / .gz already in the repo (nested members of container
   ZIPs such as attachments.zip included). Byte-identical = already in the repo, skipped.
2. New phyphox ZIPs whose START lies in the night run (25 Nov 21:00 to 26 Nov 01:30 HK) are copied byte-identical to
   raw/, with the WhatsApp '00001999-' prefix removed (Dicta's raw convention). New ones outside that window are only
   listed (another day). WiGLE logs (WigleWifi_YYYYMMDDhhmmss.csv.gz) in the window are copied too and get a row in
   ../wifi_logs.csv with status 'review' (set track, scanner_phone and status ok; build_night.py then writes
   <track>/clean/wifi/observations.csv).
3. One row per copied recording is appended to ../labels_night.csv with a PROPOSED slot: the nearest anchor slot
   (rows with anchor = yes, any track) of the same type (stop >= 40 s) within 150 s of its START (the build25.py
   rule for her a55/a56); the row takes that slot's track. The teammate's own file name is then checked against that slot (nightlib.name_nodes):
     ok      the name names the same place(s) as the slot -> built on the next build_night.py run
     review  no slot within 150 s, the name cannot be read, the name names another place, or the phone already has a
             recording in that slot -> NOT built until someone edits the row (set floor/no/node/from/to, status ok)
   File names are ground truth (team rule): when a name disagrees with the time slot, fix the row from the name.
   A phone that walked on its OWN (not in step with an anchor phone, e.g. Tian on 25 Nov) gets mostly 'review' rows:
   label it as its own track instead (anchor = yes, track = <name>, slot = iphone/a55/..., floor and slot numbers in
   walk order, a reason per row), as done for Tian (PROCESS-LOG entry 72).
4. Then: python -I scripts/build_night.py, and the day-3 pipeline (sh phase2/new/day3/run_all.sh, both variants).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nightlib as nl          # noqa: E402

REPO = nl.ROOT.parent.parent.parent
SKIP_DIRS = {'.git', '.venv', 'node_modules', 'cache', '__pycache__'}


def repo_hashes() -> set[str]:
    out = set()
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.lower().endswith(('.zip', '.gz')):
                continue
            b = Path(root, fn).read_bytes()
            out.add(hashlib.sha256(b).hexdigest())
            if fn.lower().endswith('.zip'):
                try:
                    with zipfile.ZipFile(io.BytesIO(b)) as z:
                        for n in z.namelist():
                            if n.lower().endswith(('.zip', '.gz')):
                                out.add(hashlib.sha256(z.read(n)).hexdigest())
                except zipfile.BadZipFile:
                    pass
    return out


def wigle_time(name: str):
    m = re.search(r'WigleWifi_(\d{14})', name)
    return datetime.strptime(m.group(1), '%Y%m%d%H%M%S').replace(tzinfo=nl.HK).timestamp() if m else None


def safe_name(name: str) -> str:
    base = nl.strip_prefix(Path(name.replace('\\', '/')).name)
    if not base or base.startswith('.') or base in ('..',):
        raise ValueError(f'unsafe member name {name!r}')
    return base


def source_items(src: str, since: str | None):
    """(member name or None, bytes) for every file of a WhatsApp export ZIP or a folder of loose files.
    None = not a .zip / .gz (chat text, photos, audio): never read."""
    p = Path(src)
    if p.is_dir():
        cut = datetime.strptime(since, '%Y-%m-%d %H:%M').timestamp() if since else None
        for f in sorted(p.iterdir()):
            if not f.is_file() or (cut and f.stat().st_mtime < cut):
                continue
            yield (f.name, f.read_bytes()) if f.name.lower().endswith(('.zip', '.gz')) else (None, b'')
        return
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            yield (info.filename, z.read(info)) if info.filename.lower().endswith(('.zip', '.gz')) else (None, b'')


def propose(r: dict, labels: list[dict]) -> dict:
    t = nl.clock_epoch(r['start_hk'])
    anchors = [a for a in labels if a['anchor'] == 'yes' and a['status'] == 'ok' and a['type'] == r['type']]
    best = min(anchors, key=lambda a: abs(nl.clock_epoch(a['start_hk']) - t), default=None)
    d = abs(nl.clock_epoch(best['start_hk']) - t) if best else None
    toks = nl.name_nodes(r['label_raw'], r['type'])
    if best is None or d > nl.MATCH_S:
        r.update(status='review', confidence='', reason=f"no {r['type']} slot of Dicta's within {nl.MATCH_S:.0f} s; name reads as {toks}")
        return r
    nodes = [best['node']] if r['type'] == 'stop' else [best['from_node'], best['to_node']]
    r.update(track=best['track'], floor=best['floor'], no=best['no'], node=best['node'], from_node=best['from_node'], to_node=best['to_node'])
    taken = [x for x in labels if x['slot'] == r['slot'] and x['status'] == 'ok' and x['track'] == best['track'] and x['floor'] == best['floor']
             and x['type'] == r['type'] and x['no'] == best['no']]
    where = f"START {d:.0f} s from Dicta's '{best['label_raw']}' (slot floor {best['floor']} {best['no']} = {'/'.join(nodes)})"
    if taken:
        r.update(status='review', confidence='', reason=f"{where}, but {r['slot']} already has {taken[0]['source_zip']} there; own file name reads as {toks}")
    elif nl.agrees(toks, nodes):
        r.update(status='ok', confidence='high', reason=f"{where}; own file name agrees")
    else:
        r.update(status='review', confidence='', reason=f"{where}; own file name reads as {toks}: check and fix by the name")
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('export', help='WhatsApp export ZIP (e.g. "WhatsApp Chat - GE2340.zip") or a folder of loose files')
    ap.add_argument('--since', help='folder only: keep files modified after this local time, "YYYY-MM-DD HH:MM"')
    ap.add_argument('--dry-run', action='store_true', help='report only; copy nothing, write nothing')
    a = ap.parse_args()
    known = repo_hashes()
    labels = nl.read_labels()
    stat, new_rows, other_day, wigle = Counter(), [], [], []
    seen = {}
    for name0, b in sorted(source_items(a.export, a.since), key=lambda x: (nl.plain_name(x[0]) != x[0], x[0])):
        n = name0
        if n is None:
            stat['ignored (not .zip/.gz: chat text, photos, audio, ...)'] += 1
            continue
        h = hashlib.sha256(b).hexdigest()
        if h in known:
            stat['already in the repo (byte-identical)'] += 1
            continue
        if h in seen:
            stat[f'byte-identical copy inside the source (kept once)'] += 1
            print(f'  same bytes: {n!r} = {seen[h]!r} (kept once)')
            continue
        seen[h] = n
        name = nl.plain_name(safe_name(n))
        if n.lower().endswith('.gz'):
            t = wigle_time(name)
            if t and nl.WINDOW[0].timestamp() <= t <= nl.WINDOW[1].timestamp():
                wigle.append((name, b))
            else:
                stat['new .gz outside the night run (skipped)'] += 1
            continue
        m = nl.read_meta(b)
        if m is None:
            stat['new .zip, not a phyphox recording (skipped)'] += 1
            continue
        if not nl.WINDOW[0].timestamp() <= m['start'] <= nl.WINDOW[1].timestamp():
            other_day.append(f"{name} ({m['device']}, {nl.iso(m['start'])})")
            continue
        if m['device'] not in nl.SLOT:
            sys.exit(f'{name}: device model {m["device"]!r} unknown; add it to nightlib.SLOT and day3 config.json phones first')
        dest = name
        k = 2
        while (nl.RAW / dest).exists() or dest in {x[0] for x in new_rows}:
            dest = re.sub(r'(\.zip)$', f' ({k})\\1', name); k += 1
        row = {'source_zip': dest, 'label_raw': nl.label_of(name), 'device': m['device'], 'slot': nl.SLOT[m['device']],
               'track': '', 'anchor': 'no', 'start_hk': nl.clock(m['start']), 'start_iso': nl.iso(m['start']),
               'duration_s': round(m['dur'], 1), 'type': nl.kind_of(m['dur']), 'floor': '', 'no': '', 'node': '',
               'from_node': '', 'to_node': '', 'pressure_hpa': m['pressure'], 'sha256': h}
        new_rows.append((dest, b, row))
    for dest, b, row in sorted(new_rows, key=lambda x: x[2]['start_hk']):
        propose(row, labels + [r for _, _, r in new_rows if r.get('status') == 'ok'])
    print(dict(stat))
    print(f'new night-run recordings: {len(new_rows)}; WiGLE logs in the window: {len(wigle)}; new recordings of other days: {len(other_day)}')
    for x in other_day:
        print('  other day (not copied):', x)
    st = Counter((r['slot'], r['status']) for _, _, r in new_rows)
    print('by phone and status:', dict(st))
    for _, _, r in sorted(new_rows, key=lambda x: x[2]['start_hk']):
        print(f"  {r['status']:6} {r['slot']:6} {r['track']:5} {r['start_hk']} {r['type']:4} {r['label_raw']!r:45} -> {r['floor']} {r['no']} "
              f"{r['node'] or r['from_node'] + '->' + r['to_node']}  {r['reason'] if r['status'] != 'ok' else ''}")
    if a.dry_run:
        print('dry run: nothing written')
        return
    nl.RAW.mkdir(exist_ok=True)
    for dest, b, _ in new_rows:
        (nl.RAW / dest).write_bytes(b)
    for name, b in wigle:
        if not (nl.RAW / name).exists():
            (nl.RAW / name).write_bytes(b)
    if wigle:
        old = list(csv.DictReader(nl.WIFI_LOGS.open(encoding='utf-8'))) if nl.WIFI_LOGS.exists() else []
        have = {w['log'] for w in old}
        old += [{'log': name, 'track': '', 'scanner_phone': '', 'status': 'review',
                 'note': 'added by ingest_export.py; set track + scanner_phone (deviceModel in the log header) and status ok'}
                for name, _ in wigle if name not in have]
        with nl.WIFI_LOGS.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['log', 'track', 'scanner_phone', 'status', 'note']); w.writeheader(); w.writerows(old)
    if new_rows:
        nl.write_labels(labels + [r for _, _, r in new_rows])
    print(f'copied {len(new_rows)} recordings + {len(wigle)} WiGLE logs to {nl.RAW}; labels: {nl.LABELS}')
    print('next: fix the review rows (from the file names), then python -I scripts/build_night.py and the day-3 run_all.sh')


if __name__ == '__main__':
    main()
