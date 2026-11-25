#!/usr/bin/env python3
"""25 Nov 2026: raw phyphox ZIPs + WiGLE logs -> clean/ tree in the same layout as 2026-11-24 (build_clean.py there).

    python -I phase2/clean-data/2026-11-25-spots/scripts/build_clean.py        (a few seconds; rerun after adding files)

Unlike 24 Nov (one fixed route, labels from the route order), 25 Nov mixes a route round by two collectors with spot
recordings of single places, and the export lacks part of the day. So every recording is labelled from its OWN file
name by explicit rules (label_text below), never by its position, and the decision is written per recording:

  clean/labels_used.csv   every recording: file label, type, floor, place(s), source of the label (rule / override),
                          confidence, reason. Unknown or ambiguous names are listed with status 'unlabelled' and are
                          left out of the tree (never silently dropped).
  ../labels_override.csv  hand decisions that beat the rules (e.g. WhatsApp 'DOC-...' files whose names were stripped),
                          keyed by source file name. Edit it and rerun.

Adding data later: drop phyphox ZIPs / WiGLE .csv.gz into raw/attachments/, run scripts/index_sources.py (hashes,
optional sender from the chat) and this script, then the day-3 pipeline. Duplicates (the same recording sent twice,
e.g. a 'DOC-...' copy and the named re-export) are detected by (device model, START time within 2 s) and the named
copy wins; they are listed in clean/duplicates.csv.

Places are graph-v2 names (phase2/new/graph-v2/nodes.csv). Tracks: recordings are grouped by who walked together
(TRACK_OF_MODEL, from the chat and the START times): 'round' = the route round (Benedicta iPhone19,2 + Chris SM-A566B),
'spots' = the spot recordings (Tian iPhone17,4 + Michael SM-S9280; three of Michael's S24 recordings start within
10 s of Tian's and are the same stop). Barometer floor tracking and Wi-Fi assignment are done per track.
Sensor CSVs are copied verbatim.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import statistics
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'raw' / 'attachments'
OUT = ROOT / 'clean'
DAY = '2026-11-25'
UTC, HK = timezone.utc, timezone(timedelta(hours=8))
SLOT = {'iPhone19,2': 'iphone', 'iPhone17,4': 'iphone', 'SM-S9280': 's24', 'SM-A556E': 'a55', 'SM-A566B': 'a56'}
TRACK_OF_MODEL = {'iPhone19,2': 'round', 'SM-A566B': 'round', 'iPhone17,4': 'spots', 'SM-S9280': 'spots', 'SM-A556E': 'round'}
STOP_MIN_S = 30.0          # as 24 Nov: >= 30 s = stop, shorter = walk
SAME_VISIT_S = 75          # as 24 Nov: recordings of the same place within 75 s = one physical stop
FLOOR_JUMP_HPA = 0.3       # barometer cross-check only (iPhone): consecutive same-handset stops differing by more

# ----------------------------------------------------------------------------- label rules
# Order matters: each pattern replaces its match by a token, so later patterns cannot re-use those characters.
TOK = [
    ('DTOILET', r'\b(male\s+)?((toilet|tlt|tolet|tlet|toil\w*)\s+)?(disb|disab\w*|disable\w*|dis|sisb)\b(\s+(toilet|tlt|tolet|tlet|toil\w*|cowo|cwo|men|male|mix))*'),
    ('FTOILET', r'\b(toilet|tlt|tolet|tlet|toil\w*)\s+(cewe\w*|cwe\w*)\b|\b(female|girl|women)(\s+(toilet|tlt|toil\w*))?\b'),
    ('MTOILET', r'\b(toilet|tlt|tolet|tlet|toil\w*)\s+(cowo\w*|cwo\w*|cwk|male|men\w*)\b|\b(male|men|mens|boy)(\s+(toilet|tlt|toil\w*))?\b'),
    ('EXIT10', r'\b(exit|ext|ex|ezit)\s*10\b(\s+(door|dpor))?'),
    ('EXIT5', r'\b(exit|ext|ex|ezit)\s*5\b(\s+(door|dpor))?'),
    ('CANTEEN', r'\b(kantin|canteen|cantin|canten|kanti)\w*'),
    ('ESCUP', r'\b(esca|eska|esc|sk|escalator|eskalator)\s+(naik|nik|up)\b'),
    ('ESCDOWN', r'\b(esca|eska|esc|sk|escalator|eskalator)\s+(turun|trun|tueun|down|dwn)\b'),
    ('LIFT', r'\b(lift\s*stairs?|liftstairs?|lifstairs?|lidtstairs?|lift|stairs?|ls)\s*5?\b'),
    ('Y5302', r'\by\s*5\s*302\b'), ('Y5202', r'\by\s*5\s*202\b'), ('Y5401', r'\by\s*5\s*401\b'), ('Y4502', r'\by\s*4\s*502\b'),
    ('SR9', r'\b(sr\s*9|study\s*rooms?|studyroom)\b'),
    ('LT1A', r'\b(lt\s*)?1\s*a\b'), ('LT1B', r'\b(lt\s*)?1\s*b\b'), ('LT2A', r'\b(lt\s*)?2\s*a\b'), ('LT2B', r'\b(lt\s*)?2\s*b\b'),
    ('GATE', r'\b(gate|agte|pintu keluar|entrance)\b'),
]
FLOOR4 = r'\b(lantai\s*4|lt\s*4|lvl?\s*4|lv\s*4|4th(\s+floor)?|bawah|bwh|lower)\b'
FLOOR5 = r'\b(lantai\s*5|lt\s*5|lvl?\s*5|lv\s*5|5th(\s+floor)?|atas|ats|upper)\b'
# token -> {floor: graph-v2 place}; one entry = the place exists on one floor only
PLACE = {'CANTEEN': {5: 'canteen'}, 'MTOILET': {5: 'male_toilet'}, 'FTOILET': {5: 'female_toilet'}, 'SR9': {5: 'sr9'},
         'Y5302': {5: 'y5302'}, 'Y5202': {5: 'y5202'}, 'Y5401': {5: 'y5401'},
         'EXIT5': {5: 'exit_5', 4: 'exit_5_4F'}, 'EXIT10': {5: 'exit_10', 4: 'exit_10_4F'},
         'ESCUP': {5: 'escalator_up', 4: 'escalator_up_4F'}, 'ESCDOWN': {5: 'escalator_down', 4: 'escalator_down_4F'},
         'LIFT': {5: 'lift_stairs', 4: 'lift_stairs_4F'}, 'DTOILET': {5: 'disabled_toilet', 4: 'disabled_toilet_4F'},
         'LT1A': {4: 'lt1a'}, 'LT1B': {4: 'lt1b'}, 'LT2A': {4: 'lt2a'}, 'LT2B': {4: 'lt2b'}, 'Y4502': {4: 'y4502'},
         'GATE': {4: 'entrance_exit'}}


def label_text(label: str):
    """File label -> (tokens in order, explicit floor or None, normalised text)."""
    t = ' ' + re.sub(r'\s+', ' ', label.lower().replace('my experiment', ' ').replace('_', ' ')) + ' '
    floor = None
    if re.search(FLOOR4, t):
        floor = 4
    elif re.search(FLOOR5, t):
        floor = 5
    t = re.sub(FLOOR4, ' ', t)
    t = re.sub(FLOOR5, ' ', t)
    found = []
    for tok, pat in TOK:
        for m in re.finditer(pat, t):
            found.append((m.start(), tok))
        t = re.sub(pat, lambda m: ' ' * len(m.group(0)), t)
    leftover = re.sub(r'\b(ke|to|door|dpor|point|revisit|\d+)\b', ' ', t).strip()
    return [tok for _, tok in sorted(found)], floor, leftover


# ----------------------------------------------------------------------------- read recordings
def gather(b: bytes, srcname: str, outer: str, out: list):
    with zipfile.ZipFile(io.BytesIO(b)) as zf:
        names = zf.namelist()
        if 'meta/time.csv' not in names:
            for n in names:
                if n.endswith('.zip'):
                    gather(zf.read(n), Path(n).name, outer, out)
            return
        dev = dict(list(csv.reader(io.TextIOWrapper(zf.open('meta/device.csv'), 'utf-8')))[1:])
        ev = list(csv.DictReader(io.TextIOWrapper(zf.open('meta/time.csv'), 'utf-8-sig')))
        st = [e for e in ev if e['event'] == 'START']
        pa = [e for e in ev if e['event'] == 'PAUSE']
        if not st or not pa:
            out.append({'src': srcname, 'outer': outer, 'bad': 'no START/PAUSE event'})
            return
        start, end = Decimal(st[0]['system time']), Decimal(pa[-1]['system time'])
        base = {n: zf.read(n) for n in names if '/' not in n and n.endswith('.csv')}
        pmed = None
        for pf in ('Barometer.csv', 'Pressure.csv'):
            if pf in base:
                vals = [float(r[1]) for r in list(csv.reader(io.StringIO(base[pf].decode('utf-8'))))[1:] if len(r) > 1]
                if vals:
                    pmed = statistics.median(vals)
        lab = srcname.rsplit('.zip', 1)[0]
        lab = re.split(r' \d{4}-\d\d-\d\d \d\d-\d\d-\d\d', lab)[0]
        out.append({'src': srcname, 'outer': outer, 'model': dev.get('deviceModel', '?'), 'start': start, 'end': end,
                    'dur': float(end - start), 'base': base, 'pmed': pmed, 'label': lab, 'n_events': len(ev),
                    'named': not srcname.startswith('DOC-')})


def hk(t) -> str:
    return datetime.fromtimestamp(float(t), HK).strftime('%H:%M:%S')


def main():
    pool = []
    for z in sorted(RAW.glob('*.zip')):
        gather(z.read_bytes(), z.name, z.name, pool)
    bad = [r for r in pool if 'bad' in r]
    pool = [r for r in pool if 'bad' not in r]
    unknown_models = sorted({r['model'] for r in pool} - set(SLOT))
    assert not unknown_models, f'unknown device model(s) {unknown_models}: add them to SLOT and TRACK_OF_MODEL'

    # ---- duplicates: same handset model + same START (2 s); the named copy wins, then the one with more sensor files
    groups = defaultdict(list)
    for r in pool:
        groups[(r['model'], int(r['start'] // 2))].append(r)
    recs, dups = [], []
    for g in groups.values():
        g.sort(key=lambda r: (not r['named'], -len(r['base']), r['src']))
        recs.append(g[0])
        dups += [{'kept': g[0]['src'], 'dropped_duplicate': x['src'], 'device': x['model'], 'start_hk': hk(x['start'])} for x in g[1:]]
    recs.sort(key=lambda r: r['start'])

    # ---- overrides (hand decisions) beat the rules
    ov = {}
    ovf = ROOT / 'labels_override.csv'
    if ovf.exists():
        ov = {r['source_zip']: r for r in csv.DictReader(ovf.open()) if r['source_zip'].strip()}

    # ---- label every recording
    lastfloor = {}
    rows = []
    for r in recs:
        r['slot'] = SLOT[r['model']]
        r['track'] = TRACK_OF_MODEL[r['model']]
        r['type'] = 'stop' if r['dur'] >= STOP_MIN_S else 'walk'
        o = ov.get(r['src'])
        if o:
            r.update(source='override', confidence=o['confidence'], reason=o['reason'], status=o.get('status', 'ok') or 'ok')
            if r['status'] != 'ok':
                r.update(floor='', node='', frm='', to='')
            else:
                r['floor'] = int(o['floor']); r['node'] = o['node']; r['frm'] = o['from_node']; r['to'] = o['to_node']
                if o.get('type'):
                    r['type'] = o['type']
            rows.append(r)
            if r['status'] == 'ok':
                lastfloor[r['track']] = r['floor']
            continue
        toks, fl, left = label_text(r['label'])
        r['source'] = 'rule'
        reason, conf = [f"tokens {'+'.join(toks) or '-'}"], 'high'
        need = 1 if r['type'] == 'stop' else 2
        if r['label'].startswith('DOC-') or not toks:
            r.update(status='unlabelled', confidence='', floor='', node='', frm='', to='',
                     reason='file name carries no place (WhatsApp renamed it to DOC-...)' if r['label'].startswith('DOC-') else f'no place word in "{r["label"]}"')
            rows.append(r)
            continue
        if len(toks) != need:
            r.update(status='unlabelled', confidence='', floor='', node='', frm='', to='',
                     reason=f"{r['type']} ({r['dur']:.1f} s) but {len(toks)} place word(s) {toks}")
            rows.append(r)
            continue
        only = {f for tk in toks for f in PLACE[tk] if len(PLACE[tk]) == 1}
        if fl is not None:
            floor = fl; reason.append(f'floor {fl} written in the name')
            if only and only != {fl}:
                conf = 'low'; reason.append(f'CONFLICT: place exists only on floor {sorted(only)}')
        elif only:
            floor = next(iter(only)) if len(only) == 1 else None
            reason.append(f'floor {floor} from a place that exists on one floor only')
        else:
            floor = lastfloor.get(r['track'], 5)
            conf = 'medium'
            reason.append(f'floor {floor} from the track context (previous labelled recording of the {r["track"]} track; start = 5)')
        if floor is None or any(floor not in PLACE[tk] for tk in toks):
            r.update(status='unlabelled', confidence='', floor='', node='', frm='', to='', reason='; '.join(reason + ['place not on that floor']))
            rows.append(r)
            continue
        names = [PLACE[tk][floor] for tk in toks]
        if left:
            reason.append(f'unparsed words "{left}"')
            conf = 'medium' if conf == 'high' else conf
        r.update(status='ok', floor=floor, confidence=conf, reason='; '.join(reason))
        if r['type'] == 'stop':
            r.update(node=names[0], frm='', to='')
        else:
            r.update(node='', frm=names[0], to=names[1])
        lastfloor[r['track']] = floor
        rows.append(r)

    # ---- context rule (as 24 Nov, names_24nov.csv y5302_point2): a y5302 reached from y5401 is the back door y5302_back
    prev_stop = {}
    for r in rows:
        if r['status'] != 'ok':
            continue
        if r['source'] == 'rule':
            if r['type'] == 'stop' and r['node'] == 'y5302' and prev_stop.get(r['track']) == 'y5401':
                r['node'] = 'y5302_back'; r['confidence'] = 'medium'
                r['reason'] += '; y5302 right after y5401 in the same track = y5302_back (the 24-Nov "point 2 / other door")'
            if r['type'] == 'walk' and r['frm'] == 'y5401' and r['to'] == 'y5302':
                r['to'] = 'y5302_back'; r['confidence'] = 'medium'
                r['reason'] += '; walk y5401 -> y5302 ends at y5302_back (route, as 24 Nov)'
        if r['type'] == 'stop':
            prev_stop[r['track']] = r['node']

    # ---- barometer cross-check (iPhone): same handset, consecutive stops; label floor change vs pressure jump
    fcheck = []
    for model in sorted({r['model'] for r in rows if r['slot'] == 'iphone'}):
        seq = [r for r in rows if r['model'] == model and r['type'] == 'stop' and r['status'] == 'ok' and r['pmed']]
        for a, b in zip(seq, seq[1:]):
            d = b['pmed'] - a['pmed']
            jump = 4 if d > FLOOR_JUMP_HPA else 5 if d < -FLOOR_JUMP_HPA else None
            changed = b['floor'] != a['floor']
            ok = (jump is None and not changed) or (jump is not None and changed and b['floor'] == jump)
            fcheck.append({'device': model, 'from': f"{a['node']} {hk(a['start'])}", 'to': f"{b['node']} {hk(b['start'])}",
                           'hpa_from': round(a['pmed'], 2), 'hpa_to': round(b['pmed'], 2), 'jump_hpa': round(d, 3),
                           'label_floors': f"{a['floor']}->{b['floor']}", 'agrees': ok})

    # ---- physical stops: same track + same place within SAME_VISIT_S; walks likewise by (from, to)
    clusters = []
    for r in [x for x in rows if x['status'] == 'ok']:
        key = (r['track'], r['type'], r['floor'], r['node'], r['frm'], r['to'])
        for c in clusters:
            if c['key'] == key and abs(r['start'] - c['t0']) <= SAME_VISIT_S and r['slot'] not in {x['slot'] for x in c['recs']}:
                c['recs'].append(r); break
        else:
            clusters.append({'key': key, 't0': r['start'], 'recs': [r]})
    clusters.sort(key=lambda c: c['t0'])

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    manifest, loc_rows, edge_rows, stop_windows = [], [], [], []
    num = Counter()
    for c in clusters:
        track, typ, fl, node, frm, to = c['key']
        num[(track, typ)] += 1
        n = num[(track, typ)]
        if typ == 'stop':
            folder = f'floor{fl}/stops/{track}_s{n:02d}_{node}'
            loc_rows.append({'track': track, 'floor': fl, 'stop_no': f's{n:02d}', 'node': node, 'n_phones': len(c['recs']),
                             'phones': ' '.join(sorted(x['slot'] for x in c['recs'])), 'start_hk': hk(c['t0'])})
            stop_windows.append({'track': track, 'floor': fl, 'node': node, 'folder': folder,
                                 't0': float(min(x['start'] for x in c['recs'])), 't1': float(max(x['end'] for x in c['recs']))})
        else:
            folder = f'floor{fl}/walks/{track}_w{n:02d}_{frm}__{to}'
            edge_rows.append({'track': track, 'floor': fl, 'walk_no': f'w{n:02d}', 'from_node': frm, 'to_node': to,
                              'n_phones': len(c['recs']), 'phones': ' '.join(sorted(x['slot'] for x in c['recs'])), 'start_hk': hk(c['t0'])})
        for r in sorted(c['recs'], key=lambda x: x['slot']):
            d = OUT / folder / r['slot']
            d.mkdir(parents=True, exist_ok=True)
            cnt = {}
            for fn, b in r['base'].items():
                (d / fn).write_bytes(b)
                cnt[fn[:-4]] = max(0, b.decode('utf-8', 'ignore').count('\n') - 1)
            manifest.append({'floor': fl, 'type': typ, 'node': node, 'from_node': frm, 'to_node': to,
                             'place': node if typ == 'stop' else f'{frm} -> {to}', 'phone': r['slot'], 'device': r['model'],
                             'start_hk': hk(r['start']), 'duration_s': round(r['dur'], 1),
                             'n_accel': cnt.get('Accelerometer', 0), 'n_gyro': cnt.get('Gyroscope', 0), 'n_mag': cnt.get('Magnetometer', 0),
                             'n_baro': cnt.get('Barometer', 0) + cnt.get('Pressure', 0),
                             'pressure_hpa': round(r['pmed'], 2) if r['pmed'] else '', 'folder': folder, 'source_zip': r['src'],
                             'track': track, 'label_raw': r['label'], 'label_source': r['source'], 'confidence': r['confidence']})

    def emit(path, rws, fields=None):
        if not rws and not fields:
            path.write_text('')
            return
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rws[0].keys()))
            w.writeheader(); w.writerows(rws)

    emit(OUT / 'manifest.csv', manifest)
    emit(OUT / 'locations.csv', loc_rows)
    emit(OUT / 'edges.csv', edge_rows)
    lab_fields = ['source_zip', 'outer_file', 'label_raw', 'device', 'slot', 'track', 'start_hk', 'duration_s', 'type', 'floor',
                  'node', 'from_node', 'to_node', 'status', 'label_source', 'confidence', 'reason', 'pressure_hpa']
    emit(OUT / 'labels_used.csv', [{'source_zip': r['src'], 'outer_file': r['outer'], 'label_raw': r['label'], 'device': r['model'],
                                    'slot': r['slot'], 'track': r['track'], 'start_hk': hk(r['start']), 'duration_s': round(r['dur'], 1),
                                    'type': r['type'], 'floor': r['floor'], 'node': r['node'], 'from_node': r['frm'], 'to_node': r['to'],
                                    'status': r['status'], 'label_source': r['source'], 'confidence': r['confidence'],
                                    'reason': r['reason'], 'pressure_hpa': round(r['pmed'], 2) if r['pmed'] else ''} for r in rows], lab_fields)
    emit(OUT / 'duplicates.csv', dups, ['kept', 'dropped_duplicate', 'device', 'start_hk'])
    emit(OUT / 'floor_check.csv', fcheck, ['device', 'from', 'to', 'hpa_from', 'hpa_to', 'jump_hpa', 'label_floors', 'agrees'])
    wifi = clean_wifi(stop_windows)
    unl = [r for r in rows if r['status'] != 'ok']
    summary = {'dataset': f'{DAY} (route round on floor 5 by two collectors + spot recordings by two others)',
               'raw_files': sorted(p.name for p in RAW.iterdir() if p.is_file()),
               'recordings_found': len(pool) + len(bad), 'recordings_unreadable': [b['src'] for b in bad],
               'duplicates_dropped': len(dups), 'recordings_unique': len(rows),
               'recordings_labelled': len(rows) - len(unl), 'recordings_unlabelled': [f"{r['src']} ({r['model']}, {hk(r['start'])}, {r['dur']:.0f} s): {r['reason']}" for r in unl],
               'recordings_written': len(manifest),
               'per_track_device': {f'{t}/{m}': n for (t, m), n in sorted(Counter((r['track'], r['model']) for r in rows if r['status'] == 'ok').items())},
               'stops': len(loc_rows), 'walks': len(edge_rows),
               'stops_per_track_floor': {f'{t}/floor{f}': n for (t, f), n in sorted(Counter((x['track'], x['floor']) for x in loc_rows).items())},
               'places_with_a_stop': sorted({x['node'] for x in loc_rows}),
               'confidence': dict(Counter(r['confidence'] for r in rows if r['status'] == 'ok')),
               'stop_durations_s': [round(min(r['dur'] for r in rows if r['type'] == 'stop'), 1), round(max(r['dur'] for r in rows if r['type'] == 'stop'), 1)] if any(r['type'] == 'stop' for r in rows) else [],
               'walk_durations_s': [round(min(r['dur'] for r in rows if r['type'] == 'walk'), 1), round(max(r['dur'] for r in rows if r['type'] == 'walk'), 1)] if any(r['type'] == 'walk' for r in rows) else [],
               'recordings_with_more_than_2_time_events': [f"{r['src']} ({r['n_events']} events)" for r in rows if r['n_events'] > 2],
               'floor_check_disagreements': [f for f in fcheck if not f['agrees']], 'floor_check_pairs': len(fcheck),
               'wifi': wifi}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summary.items() if k != 'raw_files'}, indent=1, ensure_ascii=False))


# ----------------------------------------------------------------------------- Wi-Fi (as 24 Nov, per track)
WIFI_MODEL = {'SM-A556E': 'a55', 'SM-A566B': 'a56', 'SM-S9280': 's24'}
INFRA = ('ifl', 'eduroam', 'cityu wlan', 'hk tech 300', 'cityu alumni', 'cityu collaboration', 'wi-fi.hk via cityu', 'csl', 'cityu')


def clean_wifi(stop_windows, tol=120):
    wdir = OUT / 'wifi'
    wdir.mkdir(exist_ok=True)
    obs, seen, logs = [], set(), []
    for g in sorted(RAW.glob('*.gz')):
        text = gzip.decompress(g.read_bytes()).decode('utf-8-sig', 'replace')
        head, _, body = text.partition('\n')
        if not head.startswith('WigleWifi'):
            logs.append({'log': g.name, 'scanner_phone': '', 'track': '', 'wifi_rows_kept': 0, 'note': 'not a WiGLE log'})
            continue
        model = dict(kv.split('=', 1) for kv in head.split(',') if '=' in kv).get('model', '?')
        phone = WIFI_MODEL.get(model, 'iphone' if model.startswith('iPhone') else model)
        track = TRACK_OF_MODEL.get(model, '')
        k0, first, last = len(obs), None, None
        for row in csv.DictReader(io.StringIO(body)):
            if row.get('Type') != 'WIFI':
                continue
            fs = row.get('FirstSeen', '')
            try:
                dt = datetime.strptime(fs, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                rssi = float(row['RSSI'])
            except (ValueError, TypeError, KeyError):
                continue
            if dt.astimezone(HK).strftime('%Y-%m-%d') != DAY:
                continue
            key = (row.get('MAC'), fs, row.get('RSSI'))
            if key in seen:
                continue
            seen.add(key)
            first = dt if first is None else min(first, dt); last = dt if last is None else max(last, dt)
            ssid = row.get('SSID') or ''
            obs.append({'scanner_phone': phone, 'source_log': g.name, 'bssid': row.get('MAC'), 'ssid': ssid, 'rssi': rssi,
                        'channel': row.get('Channel'), 'frequency': row.get('Frequency'), 'authmode': row.get('AuthMode'),
                        'is_cityu_infra': any(k in ssid.lower() for k in INFRA), 'firstseen_utc': dt.isoformat(),
                        'firstseen_hk': dt.astimezone(HK).isoformat(), 'epoch': dt.timestamp(), 'track': track})
        logs.append({'log': g.name, 'scanner_phone': phone, 'track': track, 'wifi_rows_kept': len(obs) - k0,
                     'note': f"{first.astimezone(HK).strftime('%H:%M:%S')}-{last.astimezone(HK).strftime('%H:%M:%S')} HK" if first else 'no 25-Nov Wi-Fi rows'})
    for i, r in enumerate(obs, 1):
        r['wifi_id'] = f'W{i:05d}'
    assoc, cov = [], Counter()
    for r in obs:
        cand = [s for s in stop_windows if s['track'] == r['track']]           # only stops of the scanner's own track
        if not cand:
            continue
        gap = lambda s: 0.0 if s['t0'] <= r['epoch'] <= s['t1'] else min(abs(r['epoch'] - s['t0']), abs(r['epoch'] - s['t1']))
        best = min(cand, key=gap); d = gap(best)
        if d > tol:
            continue
        assoc.append({'wifi_id': r['wifi_id'], 'folder': best['folder'], 'node': best['node'], 'assoc_type': 'in_window' if d == 0 else 'approach',
                      'time_gap_s': round(d, 1), 'scanner_phone': r['scanner_phone'], 'bssid': r['bssid'], 'rssi': r['rssi']})
        cov[best['folder']] += 1
    fields = ['wifi_id', 'scanner_phone', 'source_log', 'bssid', 'ssid', 'rssi', 'channel', 'frequency', 'authmode', 'is_cityu_infra',
              'firstseen_utc', 'firstseen_hk', 'epoch', 'track']
    with (wdir / 'observations.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(obs)
    with (wdir / 'log_summary.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['log', 'scanner_phone', 'track', 'wifi_rows_kept', 'note']); w.writeheader(); w.writerows(logs)
    with (wdir / 'stop_coverage.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['folder', 'track', 'node', 'wifi_rows_within_120s'])
        w.writeheader(); w.writerows([{'folder': s['folder'], 'track': s['track'], 'node': s['node'], 'wifi_rows_within_120s': cov[s['folder']]} for s in stop_windows])
    return {'logs': logs, 'wifi_rows': len(obs), 'unique_bssids': len({o['bssid'] for o in obs}), 'rows_assigned_within_120s': len(assoc),
            'rows_in_window': sum(a['assoc_type'] == 'in_window' for a in assoc),
            'stops_with_wifi': sum(1 for s in stop_windows if cov[s['folder']]), 'stops_total': len(stop_windows)}


if __name__ == '__main__':
    main()
