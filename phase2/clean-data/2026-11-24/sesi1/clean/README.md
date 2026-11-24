# Cleaned acquisition — 24 November 2026, Session 1 (floor 5 + floor 4)

Organized from `Data 24-11/Sesi 1`. **220 recordings** from **4 phones**
(a55, a56, iphone, s24), de-duplicated from 221 raw archives
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
- Floor 5: 15 stops, 15 walks.
- Floor 4: 12 stops, 13 walks.
- Total: 27 stops, 28 walks.

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
18,668 cleaned observations, 4,839 unique BSSIDs from
8 logs (2 empty, skipped). Each observation is matched to its
**nearest stop**: `in_window` (1,789) if its FirstSeen is inside the 60s dwell, else
`approach` (11,808) if within 120s of the stop (WiGLE scans in bursts between stops, so the
burst just before/after a stop is that stop's wifi). Result: **27/27 stops covered**
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
