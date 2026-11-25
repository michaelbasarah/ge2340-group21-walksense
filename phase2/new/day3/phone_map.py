#!/usr/bin/env python3
"""Handset identity per RECORDING, read from the phyphox metadata inside every raw ZIP (meta/device.csv, `deviceModel`).

Why: the day-3 pipeline used to call every iPhone recording "iphone", but two different iPhones were used
(iPhone17,4 and iPhone19,2). This script reads the device model of every recording straight from the raw archives
(not from the cleaned manifest), checks that it agrees with what the cleaned manifests/sessions say, checks that
the handset is consistent inside each session, and writes phone_map.csv (recording -> model id -> phone label).

The label per model id comes from `phones` in config.json (rename the `display` field there to e.g. "Michael's iPhone";
`id` is the stable key used in files and results).

Run:  python phase2/new/day3/phone_map.py        (about 1 min; exits non-zero if a model is unknown or a check fails)
Writes phone_map.csv and out/phone_map_summary.json. Raw ZIPs are only read.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import data

CD = data.HERE.parent.parent / 'clean-data'
SES = [('23nov', CD / '2026-11-23', 'raw/attachments'), ('24s1', CD / '2026-11-24/sesi1', 'raw'),
       ('24s2', CD / '2026-11-24/sesi2', 'raw')]
OTHER = [('14nov', CD / '2026-11-14', 'raw'), ('17nov', CD / '2026-11-17', 'raw')]   # not used by day3, counted only


def raw_models(raw: Path) -> dict[str, set]:
    """basename of every recording ZIP (outer or nested) -> set of deviceModel values found in it."""
    out: dict[str, set] = defaultdict(set)

    def walk(b: bytes, name: str):
        zf = zipfile.ZipFile(io.BytesIO(b))
        names = zf.namelist()
        if 'meta/device.csv' in names:
            rows = list(csv.reader(io.TextIOWrapper(zf.open('meta/device.csv'), 'utf-8')))[1:]
            out[Path(name).name].add(dict(rows).get('deviceModel', '?'))
            return
        for n in names:
            if n.endswith('.zip'):
                walk(zf.read(n), n)

    for z in sorted(raw.glob('**/*.zip')):
        walk(z.read_bytes(), z.name)
    return out


def main():
    phones = data.config()['phones']
    rows, problems = [], []
    for sid, root, rawdir in SES:
        models = raw_models(root / rawdir)
        if sid == '23nov':
            src = [{'recording': r['session_id'], 'type': 'stop' if r['kind'] == 'stop' else 'walk', 'source_zip': r['source_zip'],
                    'slot': 'iphone', 'manifest_model': r['device_model']} for r in csv.DictReader(open(root / 'sessions.csv'))]
        else:
            src = [{'recording': f"{sid}:{r['folder']}:{r['phone']}", 'type': r['type'], 'source_zip': r['source_zip'],
                    'slot': r['phone'], 'manifest_model': r['device']} for r in csv.DictReader(open(root / 'clean' / 'manifest.csv'))]
        for r in src:
            found = models.get(r['source_zip'], set())
            mm = r['manifest_model']
            if mm in found:
                model = mm
                status = 'ok' if len(found) == 1 else 'ok (ZIP name shared by several phones; manifest model is among them)'
            elif len(found) == 1:
                model = next(iter(found)); status = 'MISMATCH raw vs manifest'
            else:
                model = ''; status = 'UNDETERMINED (source ZIP not found in raw)' if not found else 'UNDETERMINED (ambiguous)'
            h = phones.get(model)
            if status.startswith(('MISMATCH', 'UNDETERMINED')) or h is None:
                problems.append({**r, 'session': sid, 'status': status if h or not model else f'UNKNOWN MODEL {model}'})
            rows.append({'session': sid, 'recording': r['recording'], 'type': r['type'], 'sensor_slot': r['slot'],
                         'source_zip': r['source_zip'], 'device_model': model, 'phone': h['id'] if h else '',
                         'display': h['display'] if h else '', 'manifest_model': mm, 'status': status})
    # consistency per session and per type
    summ = {'recordings': len(rows), 'per_session': {}, 'per_session_type': {}, 'mixed_sessions': [], 'undetermined': []}
    for sid, _, _ in SES:
        c = Counter((r['phone'], r['device_model']) for r in rows if r['session'] == sid)
        summ['per_session'][sid] = {f'{p} ({m})': n for (p, m), n in sorted(c.items())}
        for t in ('stop', 'walk'):
            ct = Counter(r['phone'] for r in rows if r['session'] == sid and r['type'] == t and r['sensor_slot'] == 'iphone')
            summ['per_session_type'][f'{sid}/{t}/iphone slot'] = dict(ct)
        iph = {r['phone'] for r in rows if r['session'] == sid and r['sensor_slot'] == 'iphone'}
        if len(iph) > 1:
            summ['mixed_sessions'].append({'session': sid, 'iphone_handsets': sorted(iph)})
    # same slot -> same model? (slot "s24" must always be one model, etc.)
    slot_models = defaultdict(set)
    for r in rows:
        slot_models[r['sensor_slot']].add(r['device_model'])
    summ['models_per_sensor_slot'] = {k: sorted(v) for k, v in slot_models.items()}
    summ['undetermined'] = [p for p in problems]
    # every raw iPhone model other than the configured ones is flagged (never guessed)
    other = {}
    for sid, root, rawdir in OTHER:
        other[sid] = dict(Counter(m for s in raw_models(root / rawdir).values() for m in s))
    summ['not_used_by_day3_raw_zip_counts'] = other
    summ['other_models_in_raw_not_in_config'] = sorted({m for v in other.values() for m in v if m not in phones} |
                                                       {r['device_model'] for r in rows if r['device_model'] and r['device_model'] not in phones})
    # the iPhone-slot of 23-Nov: stops vs walks
    out = data.HERE / 'phone_map.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    data.OUT.mkdir(exist_ok=True)
    (data.OUT / 'phone_map_summary.json').write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    print(f'wrote {out} ({len(rows)} recordings), problems: {len(problems)}')
    sys.exit(1 if problems or summ['other_models_in_raw_not_in_config'] else 0)


if __name__ == '__main__':
    main()
