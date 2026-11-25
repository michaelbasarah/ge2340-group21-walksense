# -*- coding: utf-8 -*-
import json, os, csv
from datetime import datetime, timezone, timedelta
OUT=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"clean")
HK=timezone(timedelta(hours=8))
slots=json.load(open(os.path.join(OUT,"_slots.json")))
summary=json.load(open(os.path.join(OUT,"summary.json")))
def hhmm(a): return datetime.fromtimestamp(float(a),HK).strftime("%H:%M:%S")

f5=[s for s in slots if s["floor"]==5]; f4=[s for s in slots if s["floor"]==4]

# ---- per-phone recording counts ----
from collections import Counter
pc={ph:{"stop":0,"walk":0} for ph in ("iphone","a55","a56")}
for s in slots:
    for ph in s["members"]:
        pc[ph][s["kind"]]+=1
def phrow(ph):
    st=pc[ph]["stop"]; wk=pc[ph]["walk"]; return st,wk,st+wk
pertbl=["| phone | model | stops | walks | total |","|-------|-------|-------|-------|-------|"]
models={"iphone":"iPhone19,2","a55":"SM-A556E","a56":"SM-A566B"}
for ph in ("iphone","a55","a56"):
    st,wk,tot=phrow(ph); pertbl.append(f"| {ph} | {models[ph]} | {st} | {wk} | {tot} |")
nstop=sum(1 for s in slots if s['kind']=='stop'); nwalk=sum(1 for s in slots if s['kind']=='walk')
pertbl.append(f"| **all** |  | **{nstop}** | **{nwalk}** | **{sum(phrow(p)[2] for p in pc)}** |")
PERTABLE="\n".join(pertbl)

# ---------- ROUTE.md ----------
def md_table(ss):
    out=["| # | time | type | place | phones |","|---|------|------|-------|--------|"]
    for s in ss:
        phs=",".join(sorted(s["members"])); n=len(s["members"])
        if s["kind"]=="stop":
            name=f"{s['no']}_{s['node']}"; place=s["place"]; typ="STOP"
        else:
            a,b=s["node"]; name=f"{s['no']}_{a}__{b}"; place=f"{a} → {b}"; typ="walk"
        out.append(f"| {name} | {hhmm(s['anchor'])} | {typ} | {place} | {phs} ({n}) |")
    return "\n".join(out)

md=f"""# WalkSense route — 25 November 2026 (floor 5 + floor 4)

Three phones (**iphone, a55, a56**) walked the route together, each recording every stop (~60s) and every walk. Only `iphone` (iPhone19,2) logs pressure (floor) this session — `a55`/`a56` give extra accel/gyro/mag. The iphone barometer is clean (~0.005 hPa within-stop noise; a clean +0.9 hPa step down to floor 4).

- **Stops:** stand still ~60s, phone **facing the door/landmark**.
- **Walks:** phone **pointing in the walking direction**.
- **Floor change:** Y5302 (point 2) → down the lift/stairs → "Lift/stairs-5 (floor-4 landing)". No walk was recorded for the descent (taken on stairs/lift).


## Floor 5

{sum(1 for s in f5 if s['kind']=='stop')} stops, {sum(1 for s in f5 if s['kind']=='walk')} walks.

{md_table(f5)}

## Floor 4

{sum(1 for s in f4 if s['kind']=='stop')} stops, {sum(1 for s in f4 if s['kind']=='walk')} walks.

{md_table(f4)}

## Notes

- **Escalator, lift/stairs & Exit-5-door appear on both floors** — suffixed by floor folder (`floor5/…/esca_down` vs `floor4/…/esca_down`).
- **Floor-5 escalators form a triangle off the canteen:** esca_up→canteen, canteen→esca_down, esca_up→esca_down (3 edges among canteen / esca_up / esca_down). This session the escalators were visited **up then down** (esca_up stop before esca_down).
- **No canteen revisit this session** (unlike 24-Nov Sesi 1): the loop passes through the canteen as a walk, not a second stop.
- **Y5302 point 2** = the *other door* of room Y5302, a different physical spot (not a revisit).
- **Gate** = the real building entrance/exit door (pintu keluar-masuk) on floor 4, not an emergency exit.
- **Partial coverage (1 slot):** `floor4/walks/w06_esca_down__y4502` is missing **a56** (iphone + a55 present). Everything else has all 3 phones. (The a56 `s06_y5202` stop was uploaded later and added.)
- 2 byte-identical **a55** duplicates were dropped (sr9→y5202 walk, gate stop); 1 **a56** double-take of exit5_door→lt2a kept the in-lockstep take.
"""
open(os.path.join(OUT,"ROUTE.md"),"w",encoding="utf-8").write(md)

# ---------- README.md ----------
w=summary["wifi"]
readme=f"""# Cleaned acquisition — 25 November 2026 (floor 5 + floor 4)

Organized from `Data 25-11`. **{summary['recordings_written']} recordings** written from **3 phones**
(a55, a56, iphone), de-duplicated from 163 raw archives
(`attachments.zip` was a nested bundle of 51 more recordings; 2 byte-identical a55 overlaps removed).

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
- Floor 5: {summary['stops_floor5']} stops, {summary['walks_floor5']} walks.
- Floor 4: {summary['stops_floor4']} stops, {summary['walks_floor4']} walks.
- Total: {summary['stops']} stops, {summary['walks']} walks.

## Recordings per phone
{PERTABLE}

a56 has one fewer walk than iphone/a55 — it missed `floor4/walks/w06_esca_down__y4502`.

## Sensors per phone
| phone | model | accel | gyro | mag | pressure |
|-------|-------|-------|------|-----|----------|
| iphone | iPhone19,2 | yes | yes | yes | **Barometer.csv** |
| a55 | SM-A556E | yes | yes | yes | none |
| a56 | SM-A566B | yes | yes | yes | none |

**Only one floor sensor this session** (iphone barometer; no s24). It is high quality — within-stop
std ~0.005 hPa and a clean +0.9 hPa step from floor 5 to floor 4 — so floor detection is covered,
but there is **no cross-phone redundancy** for floor (if the iphone recording for a stop were missing,
that stop would have no pressure; here the iphone is present at every stop).

## WiFi (WiGLE)
{w['wifi_clean']:,} cleaned WIFI observations, {w['unique_bssids']:,} unique BSSIDs from
{w['logs']} logs (1 empty, skipped; the real one scanned on a56). Each observation is matched to its
**nearest stop**: `in_window` ({w['in_window']:,}) if its FirstSeen is inside the 60s dwell, else
`approach` ({w['approach']:,}) if within 120s of the stop (WiGLE scans in bursts between stops). Result:
**{w['stops_with_wifi']}/{w['stops_total']} stops covered** ({w['infra_obs']:,} CityU-infra obs).
`stop_coverage.csv` has both counts; `stop_associations.csv` tags every row `in_window`/`approach` with its time gap.
Wifi stays a **weak secondary signal** (prior days: ~10% same-day revisit accuracy) — magnetometer + barometer are the workhorses.

## How it was built
Timestamps (from each recording's `meta/time.csv` START, not the noisy multi-language labels) anchored
every physical stop/walk to the complete iphone sequence, then a55/a56 recordings were matched by nearest
start time. Sensor CSVs are copied verbatim — values unaltered; cleaning = de-duplication, canonical
labelling, floor assignment, organization, and wifi association.

## Data notes
- Floor split: floors 5→4 by route — everything up to and including the floor-5 corridor
  (Male-disabled-toilet, Lift/stairs-5, Y5401, Y5302 point 2) is **floor 5**; floor 4 begins at the
  "lift stair 5 lantai 4" landing.
- Provisional: stop (x, y) metric coordinates not yet placed — waiting on the floor sketch.
"""
open(os.path.join(OUT,"README.md"),"w",encoding="utf-8").write(readme)

# ---------- ROUTE.html ----------
def esc(s): return s.replace("&","&amp;").replace("<","&lt;")
H=['<!doctype html><meta charset="utf-8"><title>WalkSense route — 25 Nov 2026</title>']
H.append('<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#1b2430;line-height:1.5}h1{font-size:22px}h2{margin-top:28px;border-bottom:2px solid #e4e8ee;padding-bottom:6px}.stop{background:#eef4ff;border-left:4px solid #2f6feb;padding:8px 12px;margin:8px 0;border-radius:6px}.walk{color:#5a6472;padding:2px 0 2px 20px;font-size:14px}.walk:before{content:"\\2193 walk ";color:#9aa4b2}.t{color:#9aa4b2;font-size:12px;font-variant-numeric:tabular-nums;margin-right:8px}.ph{float:right;font-size:12px;color:#2f6feb;background:#fff;border:1px solid #cdd9f0;border-radius:10px;padding:0 8px}.n{color:#5a6472;font-size:13px}.fc{background:#fff6e5;border-left:4px solid #e8a33d;padding:8px 12px;margin:8px 0;border-radius:6px;font-size:14px}</style>')
H.append('<h1>WalkSense route — 25 Nov 2026 (floor 5 + floor 4)</h1>')
H.append('<p class=n>Three phones (iphone, a55, a56) walked together. <b style="color:#2f6feb">Blue = stop</b> (~60 s, phone faces the door). Grey = walk between stops. Only the iphone logs floor pressure this session.</p>')
def html_floor(title,ss,fc_after=None):
    H.append(f'<h2>{title}</h2>')
    for s in ss:
        n=len(s["members"]); phtxt=f"{n} phone"+("s" if n!=1 else "")
        if s["kind"]=="stop":
            H.append(f'<div class=stop><span class=t>{hhmm(s["anchor"])}</span><b>{esc(s["place"])}</b><span class=ph>{phtxt}</span></div>')
        else:
            a,b=s["node"]; H.append(f'<div class=walk><span class=t>{hhmm(s["anchor"])}</span>{esc(a)} &rarr; {esc(b)}</div>')
    if fc_after: H.append(fc_after)
html_floor("Floor 5",f5,'<div class=fc>&#8595; took the lift / stairs <b>down to floor 4</b> (floor change — no walk recorded)</div>')
html_floor("Floor 4",f4)
open(os.path.join(OUT,"ROUTE.html"),"w",encoding="utf-8").write("\n".join(H))

# cleanup internal file
os.remove(os.path.join(OUT,"_slots.json"))
print("docs written: ROUTE.md, README.md, ROUTE.html")
print("\n=== Recordings per phone ===")
print(PERTABLE)
