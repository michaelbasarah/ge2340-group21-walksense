#!/usr/bin/env python3
"""26 Nov 2026 morning: Tian's 52 phyphox ZIPs (loose downloads) + his WhatsApp captions -> raw/ + labels_tian26.csv.

    python -I phase2/clean-data/2026-11-26-tian/scripts/ingest_tian26.py <downloads folder> <chat.txt> [--dry-run]

Why the chat: Tian's phone saved every recording under the generic name "point <date time>.zip" (only the first one is
named, "exit 5"), and he sent each file to the group right after recording it with the place as the caption. The chat
line is "[11/26/26, 9:32:52 AM] Tian: <document omitted> exit 5 toilet men".

Safe with untrusted input: the ZIPs are read as bytes (zipfile in memory, nothing extracted or executed); the chat text is
read only for Tian's "<document omitted>" lines in the run window, and only the time and caption of those lines end up in
labels_tian26.csv. The chat text itself is never copied into the repo.

Steps (fails loudly at any mismatch, nothing is written then):
1. The recordings: every '<name> 2026-11-26 HH-MM-SS.zip' in the folder with a phyphox START in the run window
   (09:00 to 11:00 HK). Each must be an iPhone17,4 recording; SHA-256 against every .zip/.gz already in the repo (the
   night run's ingest_export.repo_hashes): byte-identical = already in the repo -> stop (all should be new).
2. Captions: Tian's document lines between the first and the last file of the run. Each file (in save-time order, the
   time in its name) is matched to Tian's FIRST document line at or after its save time. The match must be strict
   one-to-one and in order, every gap 0..60 s, and every caption must come before the next file was saved.
3. Labels: each caption -> place(s) through the table CAPTIONS below (Tian's names are ground truth: atas = 5F,
   bawah = 4F, esc/eska turun = escalator down, naik = up, cewe = female, men = male, esit = exit, two places = walk
   A -> B, one place = stop). The table's kind (stop/walk) must agree with the duration (>= 40 s = stop). Node names are
   the 25-Nov / night-run names (names_25night.csv maps them to graph-v2 places), so the IDs match Tian's night track.
4. Copy the ZIPs byte-identical to raw/ (same file names) and write labels_tian26.csv; then run build_tian26.py.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tianlib as tl          # noqa: E402

sys.path.insert(0, str(tl.NIGHT_SCRIPTS))
from ingest_export import repo_hashes   # noqa: E402  (every .zip/.gz in the repo, members of container zips included)

MAX_GAP_S = 60          # observed 5 to 45 s; the strict order and "before the next file" checks do the real work
HIGH = 'high'
# caption -> (kind, floor, node | (from, to), confidence, reason). Context-resolved rows say why.
CAPTIONS = {
    'exit 5': ('stop', 5, 'exit5_door', HIGH, "file name 'exit 5' (the only named file; caption = the file name): exit 5 door 5F, pressure as his 5F stops"),
    'exit 5 toilet men': ('walk', 5, ('exit5_door', 'male_toilet'), HIGH, 'exit 5 -> male toilet (men = male)'),
    'toilet men': ('stop', 5, 'male_toilet', HIGH, 'toilet men = male toilet'),
    'toilet men y5302': ('walk', 5, ('male_toilet', 'y5302'), HIGH, 'male toilet -> y5302'),
    'y5302': ('stop', 5, 'y5302', HIGH, 'y5302 (first door; the back door has its own caption later)'),
    'y5302 sr9': ('walk', 5, ('y5302', 'sr9'), HIGH, 'y5302 -> sr9'),
    'sr9': ('stop', 5, 'sr9', HIGH, 'sr9'),
    'sr9 y5202': ('walk', 5, ('sr9', 'y5202'), HIGH, 'sr9 -> y5202'),
    'y5202': ('stop', 5, 'y5202', HIGH, 'y5202'),
    'y5202 toilet cewe': ('walk', 5, ('y5202', 'female_toilet'), HIGH, 'y5202 -> female toilet (cewe = female)'),
    'toilet cewe': ('stop', 5, 'female_toilet', HIGH, 'toilet cewe = female toilet'),
    'toilet cewe exit 10': ('walk', 5, ('female_toilet', 'exit10_door'), HIGH, 'female toilet -> exit 10 door 5F'),
    'exit 10': ('stop', 5, 'exit10_door', HIGH, 'exit 10 door 5F (no "bawah")'),
    'exit 10 canteen': ('walk', 5, ('exit10_door', 'canteen'), HIGH, 'exit 10 -> canteen'),
    'canteen esc turun atas': ('walk', 5, ('canteen', 'esca_down'), HIGH, 'canteen -> escalator down 5F (turun = down, atas = 5F)'),
    'eska naik atas kantin': ('walk', 5, ('esca_up', 'canteen'), HIGH, 'escalator up 5F -> canteen (naik = up, kantin = canteen)'),
    'eska naik atas eska turun atas': ('walk', 5, ('esca_up', 'esca_down'), HIGH, '5F escalator up -> escalator down'),
    'eska turun atas': ('stop', 5, 'esca_down', HIGH, 'escalator down 5F'),
    'eska naik atas': ('stop', 5, 'esca_up', HIGH, 'escalator up 5F'),
    'esit 5 toilet disabled men': ('walk', 5, ('exit5_door', 'male_disabled_toilet'), HIGH, 'esit = exit: exit 5 -> male disabled toilet 5F'),
    'toilet disabled men': ('stop', 5, 'male_disabled_toilet', HIGH, 'male disabled toilet 5F'),
    'toilet disabled men lift stair': ('walk', 5, ('male_disabled_toilet', 'lift_stairs5'), HIGH, 'male disabled toilet -> lift/stairs 5F'),
    'stair lift': ('stop', 5, 'lift_stairs5', HIGH, 'stair lift without "bawah" = 5F (pressure as his 5F stops; the "bawah" stops are about 0.6 hPa higher)'),
    'lift stair y5401': ('walk', 5, ('lift_stairs5', 'y5401'), HIGH, 'lift/stairs 5F -> y5401'),
    'y5401': ('stop', 5, 'y5401', HIGH, 'y5401'),
    'y5401 y5302 back': ('walk', 5, ('y5401', 'y5302_point2'), HIGH, 'y5302 back = y5302_point2 (y5302_back), as in his night labels'),
    'y5302 back': ('stop', 5, 'y5302_point2', HIGH, 'y5302 back = y5302_point2 (y5302_back)'),
    'stair lift bawah': ('stop', 4, 'lift_stairs5', HIGH, 'bawah = 4F: lift/stairs 4F landing'),
    'lift stair bawah toilet disabled bawah': ('walk', 4, ('lift_stairs5', 'disabled_toilet'), HIGH, '4F lift/stairs -> 4F (mixed) disabled toilet'),
    'toilet disabled bawah': ('stop', 4, 'disabled_toilet', HIGH, 'disabled toilet 4F (mixed)'),
    'disabled bawah exit 5 bawah': ('walk', 4, ('disabled_toilet', 'exit5_door'), HIGH, '4F disabled toilet -> exit 5 door 4F'),
    'exit 5 bawah': ('stop', 4, 'exit5_door', HIGH, 'exit 5 door 4F'),
    'exit 5 bawah lt 2a': ('walk', 4, ('exit5_door', 'lt2a'), HIGH, 'exit 5 door 4F -> LT2A'),
    'lt2a': ('stop', 4, 'lt2a', HIGH, 'LT2A'),
    'lt2a 2b': ('walk', 4, ('lt2a', 'lt2b'), HIGH, 'LT2A -> (LT)2B'),
    'lt 2b': ('stop', 4, 'lt2b', HIGH, 'LT2B'),
    'lt2b esc turun bawah': ('walk', 4, ('lt2b', 'esca_down'), HIGH, 'LT2B -> escalator down 4F'),
    'lift turun bawah': ('stop', 4, 'esca_down', 'medium',
                         'caption says "lift" but the sequence says escalator down 4F: a 60 s stop right after the walk '
                         '"lt2b esc turun bawah" and before the walks "esc turun bawah esc naik bawah" and "esc turun bawah '
                         'y4502", which both start at the 4F down escalator (advisor rule; the 4F lift/stairs stop was '
                         '"stair lift bawah" at 10:09)'),
    'esc turun bawah esc naik bawah': ('walk', 4, ('esca_down', 'esca_up'), HIGH, '4F escalator down -> up'),
    'esc turun bawah y4502': ('walk', 4, ('esca_down', 'y4502'), HIGH, '4F escalator down -> Y4502'),
    'y4502': ('stop', 4, 'y4502', HIGH, 'Y4502'),
    'y4502 esc naik bawah': ('walk', 4, ('y4502', 'esca_up'), HIGH, 'Y4502 -> escalator up 4F'),
    'esc naik bawah': ('stop', 4, 'esca_up', HIGH, 'escalator up 4F'),
    'esc naik bawah lt 1 b': ('walk', 4, ('esca_up', 'lt1b'), HIGH, 'escalator up 4F -> LT1B'),
    'lt1b': ('stop', 4, 'lt1b', HIGH, 'LT1B'),
    'lt1b lt1a': ('walk', 4, ('lt1b', 'lt1a'), HIGH, 'LT1B -> LT1A'),
    'lt1a': ('stop', 4, 'lt1a', HIGH, 'LT1A'),
    'lt1b exit 10': ('walk', 4, ('lt1a', 'exit10_door'), 'medium',
                     'caption says "lt1b" but the walk starts right after the "lt1a" stop (10:32) and ends before the '
                     '"exit 10 bawah" stop: LT1A -> exit 10 door 4F (advisor rule; the route corridor is lt1a - exit 10)'),
    'exit 10 bawah': ('stop', 4, 'exit10_door', HIGH, 'exit 10 door 4F'),
    'exit 10 bawah main gate': ('walk', 4, ('exit10_door', 'gate'), HIGH, 'exit 10 door 4F -> main gate (gate = entrance_exit)'),
    'main gate bawah': ('stop', 4, 'gate', HIGH, 'main gate = gate (building entrance/exit, entrance_exit)'),
    'main gate bawah exit 5 bawah': ('walk', 4, ('gate', 'exit5_door'), HIGH, 'main gate -> exit 5 door 4F'),
}
NAME_RE = re.compile(r'^(?P<label>.+?) (?P<t>2026-11-26 \d{2}-\d{2}-\d{2})\.zip$')
CHAT_RE = re.compile(r'^\[(?P<d>\d+/\d+/\d+), (?P<t>\d+:\d{2}:\d{2}\s[AP]M)\] (?P<who>[^:]+): (?P<msg>.*)$')


def chat_docs(chat: Path) -> list[tuple[float, str]]:
    """(epoch, caption) of every Tian '<document omitted>' line of 26 Nov in the run window."""
    out = []
    for line in chat.read_text(encoding='utf-8', errors='replace').splitlines():
        m = CHAT_RE.match(line.replace(' ', ' ').replace('‎', '').strip())
        if not m or m['who'].strip() != 'Tian' or '<document omitted>' not in m['msg']:
            continue
        t = datetime.strptime(f"{m['d']} {m['t']}", '%m/%d/%y %I:%M:%S %p').replace(tzinfo=tl.HK).timestamp()
        if tl.WINDOW[0].timestamp() <= t <= tl.WINDOW[1].timestamp():
            out.append((t, m['msg'].split('<document omitted>', 1)[1].strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('chat')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    files = []
    for f in sorted(Path(a.folder).iterdir()):
        m = NAME_RE.match(f.name)
        if not (f.is_file() and m):
            continue
        b = f.read_bytes()
        meta = tl.read_meta(b)
        if meta is None or not tl.WINDOW[0].timestamp() <= meta['start'] <= tl.WINDOW[1].timestamp():
            continue
        saved = datetime.strptime(m['t'], '%Y-%m-%d %H-%M-%S').replace(tzinfo=tl.HK).timestamp()
        files.append({'path': f, 'bytes': b, 'meta': meta, 'saved': saved, 'file_label': m['label']})
    files.sort(key=lambda x: x['saved'])
    print(f'{len(files)} recordings in the window')
    bad_dev = [x['path'].name for x in files if x['meta']['device'] != tl.DEVICE]
    if bad_dev:
        sys.exit(f'not {tl.DEVICE}: {bad_dev}')

    known = repo_hashes()
    for x in files:
        x['sha256'] = hashlib.sha256(x['bytes']).hexdigest()
    dup = [x['path'].name for x in files if x['sha256'] in known]
    if dup:
        sys.exit(f'already in the repo (byte-identical): {dup}')
    if len({x['sha256'] for x in files}) != len(files):
        sys.exit('byte-identical copies among the recordings')

    docs = chat_docs(Path(a.chat))
    docs = [d for d in docs if d[0] >= files[0]['saved']]
    print(f'{len(docs)} Tian document lines from the first file on')
    if len(docs) != len(files):
        sys.exit(f'{len(docs)} chat documents for {len(files)} files: not one-to-one')
    j = 0
    for i, x in enumerate(files):
        while j < len(docs) and docs[j][0] < x['saved']:
            j += 1
        if j >= len(docs):
            sys.exit(f"{x['path'].name}: no Tian document at or after its save time")
        if j != i:
            sys.exit(f"{x['path'].name}: matched document #{j}, expected #{i} (not in order / one-to-one)")
        t, cap = docs[j]
        gap = t - x['saved']
        nxt = files[i + 1]['saved'] if i + 1 < len(files) else float('inf')
        if not 0 <= gap <= MAX_GAP_S or t >= nxt:
            sys.exit(f"{x['path'].name}: caption '{cap}' {gap:.0f} s after saving (max {MAX_GAP_S}) or after the next file")
        if cap.endswith('.zip'):                       # the first file was sent with its own file name as the caption
            if cap != x['path'].name:
                sys.exit(f"{x['path'].name}: caption is another file name '{cap}'")
            cap = x['file_label']
        x['chat_t'], x['gap'], x['caption'] = t, gap, cap
        j += 1

    names = {(int(r['floor']), r['node_25night']): r['place_v2'] for r in csv.DictReader(tl.NAMES.open(encoding='utf-8'))}
    rows, counter = [], Counter()
    for x in files:
        if x['caption'] not in CAPTIONS:
            sys.exit(f"{x['path'].name}: caption '{x['caption']}' not in the table")
        kind, floor, nodes, conf, reason = CAPTIONS[x['caption']]
        meta = x['meta']
        if tl.kind_of(meta['dur']) != kind:
            sys.exit(f"{x['path'].name}: caption '{x['caption']}' is a {kind} but the take lasts {meta['dur']:.1f} s")
        counter[(floor, kind)] += 1
        r = {'source_zip': x['path'].name, 'sha256': x['sha256'], 'chat_time': tl.iso(x['chat_t']), 'chat_gap_s': f"{x['gap']:.0f}",
             'tian_caption': x['caption'], 'device': meta['device'], 'slot': tl.SLOT, 'track': tl.TRACK,
             'start_hk': tl.clock(meta['start']), 'start_iso': tl.iso(meta['start']), 'duration_s': round(meta['dur'], 1),
             'kind': kind, 'floor': floor, 'no': f"{'s' if kind == 'stop' else 'w'}{counter[(floor, kind)]:02d}",
             'status': 'ok', 'confidence': conf, 'reason': f"Tian's caption: {reason}", 'pressure_hpa': meta['pressure']}
        if kind == 'stop':
            r['node'] = nodes
            r['place_v2'] = names[(floor, nodes)]
        else:
            r['from_node'], r['to_node'] = nodes
            r['place_v2'] = f'{names[(floor, nodes[0])]} -> {names[(floor, nodes[1])]}'
        rows.append(r)
    unused = set(CAPTIONS) - {x['caption'] for x in files}
    if unused:
        sys.exit(f'table rows not used: {unused}')
    for r in rows:
        print(r['start_hk'], r['chat_time'][11:], f"+{r['chat_gap_s']:>2}s", r['kind'], r['floor'], r['no'], r['tian_caption'], '->', r['place_v2'], r['confidence'])
    print(dict(counter), 'gaps', min(x['gap'] for x in files), '..', max(x['gap'] for x in files), 's')
    if a.dry_run:
        return
    tl.RAW.mkdir(exist_ok=True)
    for x in files:
        dst = tl.RAW / x['path'].name
        if dst.exists() and dst.read_bytes() != x['bytes']:
            sys.exit(f'{dst} exists with other bytes')
        shutil.copyfile(x['path'], dst)
        if hashlib.sha256(dst.read_bytes()).hexdigest() != x['sha256']:
            sys.exit(f'{dst}: copy differs')
    tl.write_labels(rows)
    print(f'copied {len(files)} to raw/, wrote {tl.LABELS.name}')


if __name__ == '__main__':
    main()
