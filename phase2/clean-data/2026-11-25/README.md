# 25 November 2026 — day-3 collection (floor 5 + floor 4)

WalkSense data, **raw and cleaned**, for one continuous walk (~17:35–19:15) of the two-floor
loop. Isolated in this one dated folder, like the other `clean-data/` sessions.

## Layout
```
2026-11-25/
├── README.md              (this file)
├── floor-sketch-v1.pdf    hand-marked floor plan (red dots = stops) — same sketch as 24-Nov
├── scripts/               the exact scripts that build clean/ from raw/
├── raw/                   original phyphox ZIPs + WiGLE .csv.gz (byte-identical)
└── clean/                 organized tree + ROUTE.html (read first), manifest.csv, wifi/, summary.json
```
Inside `clean/`: `floor5/` and `floor4/`, each with `stops/<node>/<phone>/<Sensor>.csv` and
`walks/<from>__<to>/<phone>/<Sensor>.csv`; plus `ROUTE.html`/`ROUTE.md`, `manifest.csv`,
`locations.csv`, `edges.csv`, `wifi/`, `README.md`, `summary.json`. Open `ROUTE.html` first.

## At a glance
| | this session |
|---|---|
| time | ~17:35–19:15 (one continuous pass) |
| phones | iphone, a55, a56 |
| recordings | 161 written (164 raw → 162 unique) |
| stops / walks | 26 / 28 (floor 5: 14/15, floor 4: 12/13) |
| Wi-Fi obs (stops covered) | 7,178 (26/26) |

### Recordings per phone
| phone | model | stops | walks | total |
|-------|-------|-------|-------|-------|
| iphone | iPhone19,2 | 26 | 28 | 54 |
| a55 | SM-A556E | 26 | 28 | 54 |
| a56 | SM-A566B | 26 | 27 | 53 |

a56 is one walk short — it missed `floor4/walks/w06_esca_down__y4502` (iphone + a55 cover it).

## Notes for training
- **Only one floor sensor this session: the iPhone `Barometer.csv`** (no s24 this time). It is clean —
  ~0.005 hPa within-stop noise and a clean +0.9 hPa step from floor 5 down to floor 4 — but there is
  **no cross-phone pressure redundancy**. The iPhone is present at every stop, so every stop still has a
  floor reading.
- This is a **second independent, full pass** of the same loop as 24-Nov → usable as a cross-session
  train/test split (e.g. train 24-Nov, test 25-Nov) without same-day leakage.
- Sensor CSVs are copied **verbatim** from the phones — values unaltered. Cleaning = de-duplication
  (2 byte-identical a55 copies dropped), canonical labelling, floor assignment, organization, and
  Wi-Fi→stop association.
- Route differences vs 24-Nov Sesi 1: **no canteen-revisit stop** (canteen is a walk-through); the
  floor-5 escalators were visited **up then down**; `y5302` was again recorded at two different doors
  (`y5302` + `y5302_point2`, not a revisit). Floor split is by route — floor 4 begins at the
  "lift stair 5 lantai 4" landing.
- Stop (x, y) coordinates are **not yet placed** — the red dots on `floor-sketch-v1.pdf` still need
  pixel/metre positions before `locations.csv` can be filled (`x_m`/`y_m` blank).

## Rebuild
From this folder: `python scripts/build25.py && python scripts/wifi_docs25.py && python scripts/gendocs25.py`
(reads `raw/`, writes `clean/`; stdlib only).
