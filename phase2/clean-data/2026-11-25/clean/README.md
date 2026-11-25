# Cleaned acquisition — 25 November 2026 (floor 5 + floor 4)

Organized from `Data 25-11`. **161 recordings** written from **3 phones**
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
- Floor 5: 14 stops, 15 walks.
- Floor 4: 12 stops, 13 walks.
- Total: 26 stops, 28 walks.

## Recordings per phone
| phone | model | stops | walks | total |
|-------|-------|-------|-------|-------|
| iphone | iPhone19,2 | 26 | 28 | 54 |
| a55 | SM-A556E | 26 | 28 | 54 |
| a56 | SM-A566B | 26 | 27 | 53 |
| **all** |  | **26** | **28** | **161** |

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
7,178 cleaned WIFI observations, 2,760 unique BSSIDs from
2 logs (1 empty, skipped; the real one scanned on a56). Each observation is matched to its
**nearest stop**: `in_window` (1,032) if its FirstSeen is inside the 60s dwell, else
`approach` (5,884) if within 120s of the stop (WiGLE scans in bursts between stops). Result:
**26/26 stops covered** (5,428 CityU-infra obs).
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
