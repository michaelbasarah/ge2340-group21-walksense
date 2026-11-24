# 24 November 2026 — two collection sessions (floor 5 + floor 4)

Today's WalkSense data, **raw and cleaned**, for two separate walks of the same two-floor
loop. Kept together in this one folder, isolated from the other `clean-data/` sessions.

## Layout
```
2026-11-24/
├── README.md              (this file)
├── floor-sketch-v1.pdf    hand-marked floor plan (red dots = stops, metre distances)
├── scripts/               the exact scripts that built clean/ from raw/
├── sesi1/
│   ├── raw/    original phyphox ZIPs + WiGLE .csv.gz (byte-identical)
│   └── clean/  organized tree + ROUTE.html (read first), manifest.csv, wifi/, summary.json
└── sesi2/
    ├── raw/
    └── clean/
```
Inside each `clean/`: `floor5/` and `floor4/`, each with `stops/<node>/<phone>/<Sensor>.csv` and
`walks/<from>__<to>/<phone>/<Sensor>.csv`; plus `ROUTE.html`/`ROUTE.md`, `manifest.csv`,
`locations.csv`, `edges.csv`, `wifi/`, `README.md`, `summary.json`. Open `ROUTE.html` first.

## Sessions at a glance
| | Session 1 | Session 2 |
|---|---|---|
| time | ~16:00–19:11 | ~21:55–23:21 |
| phones | iphone, s24, a55, a56 | iphone, s24 |
| recordings | 220 | 108 |
| stops / walks | 27 / 28 | 26 / 28 |
| Wi-Fi obs (stops covered) | 18,668 (27/27) | 17,376 (26/26) |

Session 2 is a **second independent pass** of the same route → use it as a cross-session
train/test split (train on sesi1, test on sesi2) to avoid same-day leakage.

## Notes for training
- **Floor detection: use the iPhone `Barometer.csv`.** The s24 `Pressure.csv` is noisy/unreliable
  (drifts several hPa while standing still and doesn't resolve the ~0.5 hPa floor step); down-weight it.
- Sensor CSVs are copied **verbatim** from the phones — values unaltered. Cleaning = de-duplication,
  canonical labelling, floor assignment, organization, and Wi-Fi→stop association.
- Stop (x, y) coordinates are **not yet placed** — the red dots on `floor-sketch-v1.pdf` still need
  labelling, so `locations.csv` `x_m`/`y_m` are blank. Edge distances come from the sketch's metre marks.
- Full per-session detail in each `clean/README.md`.
