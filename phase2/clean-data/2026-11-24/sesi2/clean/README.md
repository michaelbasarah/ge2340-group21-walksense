# Cleaned acquisition — 24 November 2026, Session 2 (floor 5 + floor 4)

Organized from `Data 24-11/Sesi 2`. **108 recordings** from **2 phones**
(iphone, s24). This is a **second independent pass of the same loop as Session 1** —
the two phones each recorded their own stops and walks in lockstep, so every stop
has 2 phones and both carry a floor (pressure) sensor.

**Use:** this session is the **separate fingerprint day** needed to train/test
across sessions without same-day leakage (Session 1 = train, Session 2 = test, or
cross-validate).

## Layout
```
floor5/  floor4/
  stops/   s01_<place>/<phone>/<Sensor>.csv   (~60s dwell, phone faces the door)
  walks/   w01_<from>__<to>/<phone>/<Sensor>.csv   (phone faces walking direction)
wifi/    observations.csv (all cleaned WiGLE WIFI rows), stop_associations.csv,
         stop_coverage.csv (wifi per stop), log_summary.csv
ROUTE.md       <- human-readable ordered route (read this first)
manifest.csv   <- one row per recording: floor, type, place, phone, duration, sensor row counts, source zip
locations.csv  <- one row per stop node (x_m/y_m blank until sketch coords added)
edges.csv      <- one row per walk
summary.json
```
Stops/walks are numbered in the order they were walked (`s01`, `s02`, … per floor).

## Counts
- Floor 5: 14 stops, 15 walks.
- Floor 4: 12 stops, 13 walks.
- Total: 26 stops, 28 walks (× 2 phones = 108 recordings).

Difference vs Session 1 (27 stops): Session 2 has **no separate `canteen_revisit`
stop** between Exit 10 and the escalators (the phones walked straight through), and
the floor-5 escalators were visited **up-then-down** (Session 1 was down-then-up).
Every other node matches Session 1 one-for-one.

## Sensors per phone
| phone | model | accel | gyro | mag | pressure |
|-------|-------|-------|------|-----|----------|
| iphone | iPhone 16 Pro (iPhone17,4) | yes | yes | yes | **Barometer.csv** |
| s24 | SM-S9280 | yes | yes | yes | **Pressure.csv** |

Pressure has two different filenames (`Barometer.csv` on iphone, `Pressure.csv` on
s24) — both are hPa. s24 samples accel/gyro at ~465 Hz, iphone at ~100 Hz (expected —
different OS caps); both are fine for step/heading features.

> ⚠️ **Use the iPhone barometer for floor features — NOT the s24.** The s24 (SM-S9280)
> pressure sensor is unreliable: it drifts multiple hPa *even standing still* (up to
> **1.35 hPa std / 4.6 hPa range inside a single 60s stop**) and cannot resolve the
> ~0.5 hPa floor step. The iPhone barometer is clean (~0.02 hPa std) and shows the
> correct **+0.5 hPa step** from floor 5 down to floor 4, held across every floor-4
> stop. Ignore or heavily down-weight the s24 `Pressure.csv` for floor detection.
> (Floor *labels* in this dataset are route-assigned and correct regardless of sensor.)

## WiFi (WiGLE)
One log this session, scanned on **s24** (`WigleWifi_20261124235955.csv.gz`):
17,376 cleaned WIFI observations, 7,852 unique BSSIDs (55 cell/LTE rows dropped).
Each BSSID's FirstSeen (UTC → +8 HK) is matched to the stop whose 60s dwell window it
falls in → **26/26 stops have wifi** (Session 1 missed Y4502; this session covers
everything). 3,881 first-sightings land inside a stop window; 10,280 observations are
CityU infra SSIDs (IFL, eduroam, CityU WLAN, HK Tech 300, CityU Alumni/Collaboration,
Wi-Fi.HK via CityU, CSL). Per-stop counts in `wifi/stop_coverage.csv`.
Caveats (same as before): only **one scanner phone** (no cross-phone redundancy), and
WiGLE logs each BSSID's *first* sighting only — so later stops in the second corridor
(e.g. F5 male_disabled_toilet = 4 obs) look sparse because nearby APs were already
first-seen earlier. Wifi stays a **weak secondary signal** (~10% same-day revisit
accuracy on prior days) — magnetometer + barometer remain the workhorses.

## How it was built
The two phones recorded in lockstep, so each physical stop/walk was matched across
phones by **chronological order within floor** (not by the noisy multi-language
labels). Sensor CSVs are copied verbatim — values are unaltered; cleaning here =
canonical labelling, floor assignment, and organization. Rebuild: `python build_s2.py`.

## Data notes
- Floor split: floor 5 → floor 4 at the "lift stair 5 lantai 4" landing — everything
  up to and including the floor-5 Lift/stairs-5 corridor (Male-disabled-toilet,
  Lift/stairs-5, Y5401, Y5302 point 2) is **floor 5**; floor 4 begins at the landing.
  (Barometer alone can't separate the floors: pressure drifts over the session.)
- One label typo in the raw data: the iphone's second floor-4 escalator stop was
  labelled "esc turun bawah" but is the **Escalator-up** node (s24 labelled it
  "esc naik", and the route order confirms it) — cleaned to `esca_up`.
- Provisional: stop (x, y) metric coordinates not yet placed — waiting on the floor sketch.
