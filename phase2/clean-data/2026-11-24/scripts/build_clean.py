import zipfile, csv, io, os, glob, statistics, shutil, json, gzip
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
UTC = timezone.utc
HK = timezone(timedelta(hours=8))
SRC = r"C:/Users/Admin/School/Year 3 Sem A/GE2340/Project/Data 24-11/Sesi 1"
OUT = r"C:/Users/Admin/School/Year 3 Sem A/GE2340/Project/WalkSense-Work/clean-data/2026-11-24-sesi1"
DEVMAP = {"iPhone19,2": "iphone", "SM-S9280": "s24", "SM-A556E": "a55", "SM-A566B": "a56"}


def gather(b, srcname, out):
    with zipfile.ZipFile(io.BytesIO(b)) as zf:
        names = zf.namelist()
        inner = [n for n in names if n.endswith('.zip')]
        if inner and 'meta/time.csv' not in names:
            for n in inner:
                gather(zf.read(n), os.path.basename(n), out)
            return
        if 'meta/time.csv' not in names:
            return
        dev = dict(list(csv.reader(io.TextIOWrapper(zf.open('meta/device.csv'), 'utf-8')))[1:])
        model = dev.get('deviceModel', '?')
        ev = list(csv.DictReader(io.TextIOWrapper(zf.open('meta/time.csv'), 'utf-8-sig')))
        st = [e for e in ev if e['event'] == 'START']
        pa = [e for e in ev if e['event'] == 'PAUSE']
        if not st or not pa:
            return
        start = Decimal(st[0]['system time']); end = Decimal(pa[-1]['system time'])
        base = {n: zf.read(n) for n in names if '/' not in n and n.endswith('.csv')}
        pmed = None
        for pf in ('Barometer.csv', 'Pressure.csv'):
            if pf in base:
                rr = list(csv.reader(io.StringIO(base[pf].decode('utf-8'))))[1:]
                vals = [float(r[1]) for r in rr if len(r) > 1]
                if vals:
                    pmed = statistics.median(vals)
        out.append(dict(src=srcname, model=model, phone=DEVMAP.get(model, model),
                        start=start, end=end, dur=float(end - start), base=base, pmed=pmed,
                        label=srcname.split(' 2026-', 1)[0]))


pool = []
for z in glob.glob(os.path.join(SRC, '*.zip')):
    gather(open(z, 'rb').read(), os.path.basename(z), pool)

# dedupe: same phone + same start (within 2s)
seen = {}
for r in pool:
    key = (r['phone'], int(r['start'] / 2))
    if key not in seen or len(r['base']) > len(seen[key]['base']):
        seen[key] = r
recs = sorted(seen.values(), key=lambda r: r['start'])

# classify + time-cluster
for r in recs:
    r['kind'] = 'stop' if r['dur'] >= 30 else 'walk'
clusters = []
for r in recs:
    for c in clusters:
        if r['kind'] == c['kind'] and abs(r['start'] - c['t0']) <= 75:
            c['recs'].append(r); c['t0'] = min(c['t0'], r['start']); break
    else:
        clusters.append(dict(kind=r['kind'], t0=r['start'], recs=[r]))
clusters.sort(key=lambda c: min(x['start'] for x in c['recs']))

# merge consecutive STOP clusters that both mention 'gate' (late s24 gate)
merged = []
for c in clusters:
    if (merged and c['kind'] == 'stop' and merged[-1]['kind'] == 'stop'
            and all('gate' in x['label'].lower() for x in c['recs'])
            and all('gate' in x['label'].lower() for x in merged[-1]['recs'])):
        merged[-1]['recs'] += c['recs']
    else:
        merged.append(c)
clusters = merged


def S(fl, slug, disp, kw):
    return dict(fl=fl, kind='stop', slug=slug, disp=disp, kw=kw)


def W(fl, frm, to, kw):
    return dict(fl=fl, kind='walk', frm=frm, to=to, kw=kw)


CANON = [
    S(5, 'canteen', 'Canteen', 'cant'), W(5, 'canteen', 'exit5_door', 'exit 5'),
    S(5, 'exit5_door', 'Exit 5 door', 'ex'), W(5, 'exit5_door', 'male_toilet', 'toi'),
    S(5, 'male_toilet', 'Male toilet', 'toi'), W(5, 'male_toilet', 'y5302', '5302'),
    S(5, 'y5302', 'Y5302', '530'), W(5, 'y5302', 'sr9', 'sr'),
    S(5, 'sr9', 'SR9 (study rooms)', 'sr'), W(5, 'sr9', 'y5202', '5202'),
    S(5, 'y5202', 'Y5202', '5202'), W(5, 'y5202', 'female_toilet', 'toi'),
    S(5, 'female_toilet', 'Female toilet', 'toi'), W(5, 'female_toilet', 'exit10_door', '10'),
    S(5, 'exit10_door', 'Exit 10 door', '10'), W(5, 'exit10_door', 'canteen', 'cant'),
    S(5, 'canteen_revisit', 'Canteen (revisit)', 'cant'), W(5, 'canteen', 'esca_down', 'esca'),
    S(5, 'esca_down', 'Escalator down', 'esc'), W(5, 'esca_up', 'canteen', 'esca'),
    S(5, 'esca_up', 'Escalator up', 'esc'), W(5, 'esca_up', 'esca_down', 'esc'),
    W(5, 'exit5_door', 'male_disabled_toilet', 'disab'),
    S(5, 'male_disabled_toilet', 'Male disabled toilet', 'dis'), W(5, 'male_disabled_toilet', 'lift_stairs5', 'lift'),
    S(5, 'lift_stairs5', 'Lift / stairs 5', 'lift'), W(5, 'lift_stairs5', 'y5401', '5401'),
    S(5, 'y5401', 'Y5401', '5401'), W(5, 'y5401', 'y5302_point2', '530'),
    S(5, 'y5302_point2', 'Y5302 (point 2 - other door)', '530'),
    # ---- floor change: lift/stairs DOWN to floor 4, no walk recorded ----
    S(4, 'lift_stairs5', 'Lift / stairs 5 (floor-4 landing)', 'lift'), W(4, 'lift_stairs5', 'disabled_toilet', 'disab'),
    S(4, 'disabled_toilet', 'Disabled toilet', 'dis'), W(4, 'disabled_toilet', 'exit5_door', 'ex5'),
    S(4, 'exit5_door', 'Exit 5 door', 'ex5'), W(4, 'exit5_door', 'lt2a', '2a'),
    S(4, 'lt2a', 'LT2A', '2a'), W(4, 'lt2a', 'lt2b', '2b'),
    S(4, 'lt2b', 'LT2B', '2b'), W(4, 'lt2b', 'esca_down', 'esc'),
    S(4, 'esca_down', 'Escalator down', 'esc'), W(4, 'esca_down', 'y4502', '4502'),
    S(4, 'y4502', 'Y4502', '4502'), W(4, 'y4502', 'esca_up', 'esca'),
    S(4, 'esca_up', 'Escalator up', 'esc'), W(4, 'esca_up', 'lt1b', '1b'),
    S(4, 'lt1b', 'LT1B', '1b'), W(4, 'lt1b', 'lt1a', '1a'),
    S(4, 'lt1a', 'LT1A', '1a'), W(4, 'lt1a', 'exit10_door', '10'),
    S(4, 'exit10_door', 'Exit 10 door', '10'), W(4, 'exit10_door', 'gate', 'gate'),
    S(4, 'gate', 'Gate (building entrance/exit)', 'gate'), W(4, 'gate', 'exit5_door', 'gate'),
    W(4, 'esca_down', 'esca_up', 'esc'),
]
assert len(clusters) == len(CANON), f"cluster/canon mismatch {len(clusters)} vs {len(CANON)}"

if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
manifest = []; warn = []
stop_no = {5: 0, 4: 0}; walk_no = {5: 0, 4: 0}
loc_rows = []; edge_rows = []; stop_windows = []


def count_rows(b):
    return max(0, b.decode('utf-8', 'ignore').count('\n') - 1)


for c, meta in zip(clusters, CANON):
    fl = meta['fl']; labels = sorted(set(x['label'] for x in c['recs']))
    if not any(meta['kw'] in x['label'].lower() for x in c['recs']):
        warn.append(f"keyword '{meta['kw']}' not found in {labels}")
    hk = datetime.fromtimestamp(float(c['t0']), HK).strftime('%H:%M:%S')
    if meta['kind'] == 'stop':
        stop_no[fl] += 1; folder = f"s{stop_no[fl]:02d}_{meta['slug']}"
        reldir = f"floor{fl}/stops/{folder}"
        loc_rows.append(dict(floor=fl, stop_no=f"s{stop_no[fl]:02d}", node=meta['slug'],
                             label=meta['disp'], n_phones=len(set(x['phone'] for x in c['recs'])),
                             start_hk=hk, x_m='', y_m=''))
        stop_windows.append(dict(floor=fl, stop_no=f"s{stop_no[fl]:02d}", node=meta['slug'],
                                 folder=reldir, t0=min(x['start'] for x in c['recs']),
                                 t1=max(x['end'] for x in c['recs'])))
        node_disp = meta['disp']; typ = 'stop'; frm = to = ''
    else:
        walk_no[fl] += 1; folder = f"w{walk_no[fl]:02d}_{meta['frm']}__{meta['to']}"
        reldir = f"floor{fl}/walks/{folder}"
        edge_rows.append(dict(floor=fl, walk_no=f"w{walk_no[fl]:02d}", from_node=meta['frm'],
                              to_node=meta['to'], n_phones=len(set(x['phone'] for x in c['recs'])), start_hk=hk))
        node_disp = f"{meta['frm']} -> {meta['to']}"; typ = 'walk'; frm = meta['frm']; to = meta['to']
    for r in sorted(c['recs'], key=lambda r: r['phone']):
        pdir = os.path.join(OUT, reldir, r['phone'])
        os.makedirs(pdir, exist_ok=True)
        n = {'Accelerometer': 0, 'Gyroscope': 0, 'Magnetometer': 0, 'Barometer': 0, 'Pressure': 0}
        for fn, data in r['base'].items():
            with open(os.path.join(pdir, fn), 'wb') as f:
                f.write(data)
            k = fn.replace('.csv', '')
            if k in n:
                n[k] = count_rows(data)
        manifest.append(dict(floor=fl, type=typ, node=meta.get('slug', ''), from_node=frm, to_node=to,
                             place=node_disp, phone=r['phone'], device=r['model'],
                             start_hk=datetime.fromtimestamp(float(r['start']), HK).strftime('%H:%M:%S'),
                             duration_s=round(r['dur'], 1),
                             n_accel=n['Accelerometer'], n_gyro=n['Gyroscope'], n_mag=n['Magnetometer'],
                             n_baro=n['Barometer'] + n['Pressure'],
                             pressure_hpa=round(r['pmed'], 2) if r['pmed'] else '',
                             folder=reldir, source_zip=r['src']))


def emit(name, rows):
    with open(os.path.join(OUT, name), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


emit('manifest.csv', manifest)
emit('locations.csv', loc_rows)
emit('edges.csv', edge_rows)

# ---------------- WiFi (WiGLE) cleaning ----------------
WIFI_MODEL = {"SM-A556E": "a55", "SM-A566B": "a56", "SM-S9280": "s24", "iPhone": "iphone"}
INFRA = ("ifl", "eduroam", "cityu wlan", "hk tech 300", "cityu alumni",
         "cityu collaboration", "wi-fi.hk via cityu", "csl", "cityu")


def is_infra(ssid):
    s = (ssid or "").lower()
    return any(k in s for k in INFRA)


def clean_wifi(stop_windows):
    wdir = os.path.join(OUT, 'wifi'); os.makedirs(wdir, exist_ok=True)
    gzs = sorted(glob.glob(os.path.join(SRC, '*.csv.gz')))
    obs = []; seen = set(); src_rows = 0; nonwifi = 0; empty_logs = []; log_stats = []
    for g in gzs:
        text = gzip.decompress(open(g, 'rb').read()).decode('utf-8-sig')
        head, _, body = text.partition('\n')
        model = dict(kv.split('=', 1) for kv in head.split(',') if '=' in kv).get('model', '?')
        phone = WIFI_MODEL.get(model, model)
        rdr = csv.DictReader(io.StringIO(body)); kept0 = len(obs)
        for row in rdr:
            src_rows += 1
            if row.get('Type') != 'WIFI':
                nonwifi += 1; continue
            fs = row.get('FirstSeen', '')
            try:
                dt = datetime.strptime(fs, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                rssi = float(row['RSSI'])
            except (ValueError, TypeError, KeyError):
                continue
            key = (row.get('MAC'), fs, row.get('RSSI'))
            if key in seen:
                continue
            seen.add(key)
            obs.append(dict(scanner_phone=phone, source_log=os.path.basename(g),
                            bssid=row.get('MAC'), ssid=row.get('SSID'), rssi=rssi,
                            channel=row.get('Channel'), frequency=row.get('Frequency'),
                            authmode=row.get('AuthMode'), is_cityu_infra=is_infra(row.get('SSID')),
                            firstseen_utc=dt.isoformat(), firstseen_hk=dt.astimezone(HK).isoformat(),
                            epoch=dt.timestamp()))
        n = len(obs) - kept0
        log_stats.append(dict(log=os.path.basename(g), scanner_phone=phone, wifi_rows_kept=n))
        if n == 0:
            empty_logs.append(os.path.basename(g))
    for i, r in enumerate(obs, 1):
        r['wifi_id'] = f'W{i:05d}'

    # Associate each observation to its NEAREST stop in time: 'in_window' if its FirstSeen
    # falls inside the 60s dwell, else 'approach' if within TOL seconds of that stop
    # (WiGLE scans in bursts between stops; a burst just before a stop is that stop's wifi).
    TOL = 120

    def gap(t, s):
        if float(s['t0']) <= t <= float(s['t1']):
            return 0.0
        return min(abs(t - float(s['t0'])), abs(t - float(s['t1'])))

    assoc = []; inwin = Counter(); appr = Counter(); bssid_by_stop = defaultdict(set)
    for r in obs:
        t = r['epoch']
        best = min(stop_windows, key=lambda s: gap(t, s)); d = gap(t, best)
        atype = 'in_window' if d == 0 else ('approach' if d <= TOL else None)
        if atype is None:
            continue
        k = (best['floor'], best['stop_no'], best['node'])
        assoc.append(dict(wifi_id=r['wifi_id'], floor=best['floor'], stop_no=best['stop_no'],
                          node=best['node'], assoc_type=atype, time_gap_s=round(d, 1),
                          scanner_phone=r['scanner_phone'], bssid=r['bssid'], ssid=r['ssid'],
                          rssi=r['rssi'], is_cityu_infra=r['is_cityu_infra'], firstseen_hk=r['firstseen_hk']))
        (inwin if atype == 'in_window' else appr)[k] += 1
        bssid_by_stop[k].add(r['bssid'])
    coverage = []
    for s in stop_windows:
        k = (s['floor'], s['stop_no'], s['node'])
        coverage.append(dict(floor=s['floor'], stop_no=s['stop_no'], node=s['node'],
                             wifi_in_window=inwin[k], wifi_approach=appr[k],
                             unique_bssids=len(bssid_by_stop[k])))

    def w(name, rows, fields=None):
        with open(os.path.join(wdir, name), 'w', newline='', encoding='utf-8') as f:
            wr = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()))
            wr.writeheader(); wr.writerows(rows)
    ofields = ['wifi_id', 'scanner_phone', 'source_log', 'bssid', 'ssid', 'rssi', 'channel',
               'frequency', 'authmode', 'is_cityu_infra', 'firstseen_utc', 'firstseen_hk', 'epoch']
    w('observations.csv', obs, ofields)
    w('stop_associations.csv', assoc if assoc else [dict.fromkeys(
        ['wifi_id', 'floor', 'stop_no', 'node', 'assoc_type', 'time_gap_s', 'scanner_phone',
         'bssid', 'ssid', 'rssi', 'is_cityu_infra', 'firstseen_hk'], '')])
    w('stop_coverage.csv', coverage)
    w('log_summary.csv', log_stats)
    return dict(logs=len(gzs), empty_logs=empty_logs, source_rows=src_rows, non_wifi=nonwifi,
                wifi_clean=len(obs), unique_bssids=len({r['bssid'] for r in obs}),
                associations=len(assoc), in_window=sum(inwin.values()), approach=sum(appr.values()),
                stops_with_wifi=sum(1 for c in coverage if c['wifi_in_window'] or c['wifi_approach']),
                stops_total=len(coverage), infra_obs=sum(1 for r in obs if r['is_cityu_infra']))


wifi_summary = clean_wifi(stop_windows)

summary = dict(dataset='2026-11-24 Sesi 1 (floor 5 + floor 4)',
               phones=sorted(set(r['phone'] for r in recs)),
               recordings_raw=len(pool), recordings_unique=len(recs),
               recordings_written=len(manifest),
               stops=sum(1 for m in CANON if m['kind'] == 'stop'),
               walks=sum(1 for m in CANON if m['kind'] == 'walk'),
               stops_floor5=stop_no[5], stops_floor4=stop_no[4],
               walks_floor5=walk_no[5], walks_floor4=walk_no[4], wifi=wifi_summary, warnings=warn)
with open(os.path.join(OUT, 'summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(json.dumps(summary, indent=2, ensure_ascii=False))
print("\nWARNINGS:")
for w0 in warn:
    print("  " + w0)
if not warn:
    print("  none")
