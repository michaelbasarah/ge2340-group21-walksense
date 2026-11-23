# Positioning pilot — GE2340

A dry run of the positioning pipeline on the **2026-11-17** session, to check whether the
sensors can actually locate a stop before collecting more data. **Vibe-coded** (allowed by
the course); all numbers come from our own real recordings.

## How to run
```bash
cd phase2/positioning-pilot
python pilot_train.py
```
Needs: `numpy pandas scikit-learn matplotlib` (`python -m pip install scikit-learn`).
Reads `../clean-data/2026-11-17/`. Writes everything to `out/`.

## What it does
1. Cuts each 30 s stop's magnetometer into **2 s slices** (15 per stop, 390 total) and
   summarises each slice (magnitude mean/sd/min/max + x/y/z mean).
2. Trains **kNN** and **Random Forest** to predict the stop from the magnetic slice.
3. Measures **separability** independent of any model (silhouette score) so the result
   is not just classifier optimism.
4. Clusters stops into two floors by **barometer** pressure.

## Outputs (`out/`)
- `results.json` — all metrics.
- `magnetic_slices.csv` — the training table (what a fingerprint dataset looks like).
- `pressure_per_stop.png` — per-stop pressure, coloured by floor.
- `magnetic_pca.png` — magnetic slices projected to 2D.
- `confusion_knn.png` — which stops get confused.

## IMPORTANT — read before quoting any number
This is **one session**, so train and test slices come from the **same walk**. The stop
accuracy (~0.94) is an **optimistic upper bound**, NOT a grade result, because nearby
slices are almost identical (leakage). A valid result needs a **different day** as the test
set (train days 1-2, test day 3). Wi-Fi is excluded here: scan throttling left 12 of 26
stops with no Wi-Fi this session (fix: Developer options -> Wi-Fi scan throttling OFF).

The honest, leakage-free signal is the **silhouette score** (~0.44 over 26 stops = real
structure) and the **clean two-floor barometer split** — those say the method is worth
pursuing.
