import csv, json, os
from collections import defaultdict
OUT = r"C:/Users/Admin/School/Year 3 Sem A/GE2340/Project/WalkSense-Work/clean-data/2026-11-24-sesi1"

man = list(csv.DictReader(open(os.path.join(OUT, 'manifest.csv'), encoding='utf-8')))
summ = json.load(open(os.path.join(OUT, 'summary.json'), encoding='utf-8'))

# group by folder, keep route order via first-seen
order = []
byfolder = defaultdict(list)
for r in man:
    if r['folder'] not in byfolder:
        order.append(r['folder'])
    byfolder[r['folder']].append(r)

ARROW = ' → '

def phones_str(rows):
    ph = sorted(set(x['phone'] for x in rows))
    return ','.join(ph)

lines = []
lines.append('# WalkSense route — 24 November 2026, Session 1 (floor 5 + floor 4)\n')
lines.append('Four phones (**iphone, s24, a55, a56**) walked the route together, each recording '
             'every stop (~60s) and every walk. `iphone` and `s24` also log pressure (floor); '
             '`a55`/`a56` give extra accel/gyro/mag only.\n')
lines.append('- **Stops:** stand still ~60s, phone **facing the door/landmark**.')
lines.append('- **Walks:** phone **pointing in the walking direction** '
             '(so a door facing the travel direction makes the end-of-walk heading ≈ the stop heading).')
lines.append('- **Floor change:** Y5302 → down the lift/stairs → "Lift/stairs-5 (floor-4 landing)". '
             'No walk was recorded for the descent (taken on stairs/lift).\n')

for fl in ('5', '4'):
    stops = [f for f in order if f.startswith(f'floor{fl}/stops/')]
    walks = [f for f in order if f.startswith(f'floor{fl}/walks/')]
    lines.append(f'\n## Floor {fl}\n')
    lines.append(f'{len(stops)} stops, {len(walks)} walks.\n')
    # interleaved timeline in route order
    seq = [f for f in order if f.startswith(f'floor{fl}/')]
    lines.append('| # | time | type | place | phones |')
    lines.append('|---|------|------|-------|--------|')
    for f in seq:
        rows = byfolder[f]
        r0 = rows[0]
        t = min(x['start_hk'] for x in rows)
        if r0['type'] == 'stop':
            place = r0['place']
            kind = 'STOP'
        else:
            place = r0['from_node'] + ARROW + r0['to_node']
            kind = 'walk'
        name = f.split('/')[-1]
        lines.append(f"| {name} | {t} | {kind} | {place} | {phones_str(rows)} ({len(set(x['phone'] for x in rows))}) |")

lines.append('\n## Notes\n')
lines.append('- **Escalator & lift/stairs & Exit-5-door appear on both floors** — suffixed by floor folder '
             '(`floor5/…/esca_down` vs `floor4/…/esca_down`).')
lines.append('- **Floor-5 escalators form a triangle off the canteen:** canteen→esca_down, esca_up→canteen, '
             'esca_up→esca_down (3 edges among canteen / esca_up / esca_down).')
lines.append('- **Canteen (revisit)** = the *same* canteen spot recorded twice (a true revisit). '
             '**Y5302 point 2** = the *other door* of room Y5302, a different physical spot (not a revisit).')
lines.append('- **Gate** = the real building entrance/exit door (pintu keluar-masuk) on floor 4, not an emergency exit.')
lines.append('- One a56 walk recording (`floor4/walks/w06_esca_down__y4502`) is **accelerometer-only** '
             '(gyro/mag failed) — kept for accel/step data.')

open(os.path.join(OUT, 'ROUTE.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

# ---- friendly HTML version ----
def esc(s): return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
h = ['<!doctype html><meta charset="utf-8"><title>WalkSense route — 24 Nov Sesi 1</title>',
     '<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:720px;margin:24px auto;'
     'padding:0 16px;color:#1b2430;line-height:1.5}h1{font-size:22px}h2{margin-top:28px;border-bottom:2px solid #e4e8ee;'
     'padding-bottom:6px}.stop{background:#eef4ff;border-left:4px solid #2f6feb;padding:8px 12px;margin:8px 0;border-radius:6px}'
     '.walk{color:#5a6472;padding:2px 0 2px 20px;font-size:14px}.walk:before{content:"↓ walk ";color:#9aa4b2}'
     '.t{color:#9aa4b2;font-size:12px;font-variant-numeric:tabular-nums;margin-right:8px}'
     '.ph{float:right;font-size:12px;color:#2f6feb;background:#fff;border:1px solid #cdd9f0;border-radius:10px;padding:0 8px}'
     '.n{color:#5a6472;font-size:13px}.fc{background:#fff6e5;border-left:4px solid #e8a33d;padding:8px 12px;'
     'margin:8px 0;border-radius:6px;font-size:14px}</style>']
h.append('<h1>WalkSense route — 24 Nov 2026, Session 1</h1>')
h.append('<p class=n>Four phones (iphone, s24, a55, a56) walked together. '
         '<b style="color:#2f6feb">Blue = stop</b> (~60 s, phone faces the door). Grey = walk between stops.</p>')
prev_fl = None
for fl in ('5', '4'):
    h.append(f'<h2>Floor {fl}</h2>')
    for f in [x for x in order if x.startswith(f'floor{fl}/')]:
        rows = byfolder[f]; r0 = rows[0]; t = min(x['start_hk'] for x in rows)
        nph = len(set(x['phone'] for x in rows))
        if r0['type'] == 'stop':
            h.append(f'<div class=stop><span class=t>{t}</span><b>{esc(r0["place"])}</b>'
                     f'<span class=ph>{nph} phones</span></div>')
        else:
            h.append(f'<div class=walk><span class=t>{t}</span>{esc(r0["from_node"])} '
                     f'&rarr; {esc(r0["to_node"])}</div>')
    if fl == '5':
        h.append('<div class=fc>&#8595; took the lift / stairs <b>down to floor 4</b> '
                 '(floor change — no walk recorded)</div>')
open(os.path.join(OUT, 'ROUTE.html'), 'w', encoding='utf-8').write('\n'.join(h) + '\n')

# README
readme = f'''# Cleaned acquisition — 24 November 2026, Session 1 (floor 5 + floor 4)

Organized from `Data 24-11/Sesi 1`. **{summ['recordings_written']} recordings** from **4 phones**
({', '.join(summ['phones'])}), de-duplicated from {summ['recordings_raw']} raw archives
(the two `attachments.zip` were nested bundles; overlaps removed).

## Layout
```
floor5/  floor4/
  stops/   s01_<place>/<phone>/<Sensor>.csv   (~60s dwell, phone faces the door)
  walks/   w01_<from>__<to>/<phone>/<Sensor>.csv   (phone faces walking direction)
wifi/    observations.csv (all cleaned WiGLE rows), stop_associations.csv,
         stop_coverage.csv (wifi per stop), log_summary.csv
ROUTE.md       <- human-readable ordered route (read this first)
manifest.csv   <- one row per recording: floor, type, place, phone, duration, sensor row counts, source zip
locations.csv  <- one row per stop node (x_m/y_m blank until sketch coords added)
edges.csv      <- one row per walk
summary.json
```
Stops/walks are numbered in the order they were walked (`s01`, `s02`, … per floor).

## Counts
- Floor 5: {summ['stops_floor5']} stops, {summ['walks_floor5']} walks.
- Floor 4: {summ['stops_floor4']} stops, {summ['walks_floor4']} walks.
- Total: {summ['stops']} stops, {summ['walks']} walks.

## Sensors per phone
| phone | model | accel | gyro | mag | pressure |
|-------|-------|-------|------|-----|----------|
| iphone | iPhone 16 Pro | yes | yes | yes | **Barometer.csv** |
| s24 | SM-S9280 | yes | yes | yes | **Pressure.csv** |
| a55 | SM-A556E | yes | yes | yes | none |
| a56 | SM-A566B | yes | yes | yes | none |

Pressure has two different filenames (`Barometer.csv` on iphone, `Pressure.csv` on s24) — both are
hPa; every stop has ≥ 2 phones with pressure, so floor detection is covered everywhere.

## WiFi (WiGLE)
{summ['wifi']['wifi_clean']:,} cleaned observations, {summ['wifi']['unique_bssids']:,} unique BSSIDs from
{summ['wifi']['logs']} logs ({len(summ['wifi']['empty_logs'])} empty, skipped). Each observation is matched to its
**nearest stop**: `in_window` ({summ['wifi']['in_window']:,}) if its FirstSeen is inside the 60s dwell, else
`approach` ({summ['wifi']['approach']:,}) if within 120s of the stop (WiGLE scans in bursts between stops, so the
burst just before/after a stop is that stop's wifi). Result: **{summ['wifi']['stops_with_wifi']}/{summ['wifi']['stops_total']} stops covered**
(`stop_coverage.csv` has both counts; `stop_associations.csv` tags every row `in_window`/`approach` with its time gap).
Y4502 has 0 in-window but ~191 approach (a56 scanned ~60s before the stop). Wifi stays a **weak secondary signal**
(prior days: ~10% same-day revisit accuracy) — magnetometer + barometer are the workhorses.

## How it was built
Timestamps (not the noisy multi-language labels) were used to group each physical stop/walk across
the 4 phones. Sensor CSVs are copied verbatim — values are unaltered; cleaning here = de-duplication,
canonical labelling, floor assignment, and organization. Rebuild: `python build_clean.py`.

## Data notes
- Floor split: floors 5→4 by route — everything up to and including the floor-5 Lift/stairs-5
  corridor (Male-disabled-toilet, Lift/stairs-5, Y5401, Y5302) is **floor 5**; floor 4 begins at the
  "lift stair 5 lantai 4" landing. (Barometer alone can't separate the floors: pressure drifted over
  the 2-hour gap between the floor-5 and floor-4 hours.)
- Provisional: stop (x, y) metric coordinates not yet placed — waiting on the floor sketch.
'''
open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8').write(readme)
print('ROUTE.md and README.md written.')
print('floor5 stops:', summ['stops_floor5'], 'walks:', summ['walks_floor5'])
print('floor4 stops:', summ['stops_floor4'], 'walks:', summ['walks_floor4'])
