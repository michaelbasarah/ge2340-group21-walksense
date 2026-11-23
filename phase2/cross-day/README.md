# Leakage-reduced and cross-day positioning results

Code and numbers only. This folder doesn't contain report text. The course allows an LLM to polish the team's writing but not to write it, so the team writes any wording that goes into the report.

## Run

```sh
python phase2/cross-day/crossday.py
```

Needs `numpy pandas scikit-learn matplotlib` (the same as the rest of `phase2/`). A run takes about 30 s. Every number below comes from `out/results.json`, which this command writes.

On the first run the script rebuilds the gitignored 23-Nov sensor CSVs. It copies `clean-data/2026-11-23/clean.py` **unchanged** into `cache/2026-11-23/` and runs it there with `--source <repo>/phase2/clean-data/2026-11-23/raw/attachments`. **No code was changed.** The Windows `DEFAULT_SOURCE` is simply overridden by the existing `--source` flag. The rebuilt `sessions.csv`, `locations_provisional.csv`, `recording_intervals.csv` and Wi-Fi association files match the committed ones byte for byte (once Windows CRLF line endings are ignored), and the script checks this every time it rebuilds. Nothing in `clean-data/` is written.

## Inputs you can edit

| File | What it is |
|---|---|
| `labels_23nov_confirmed.csv` | **The 23-Nov labels.** 23 Nov is the reference dataset. Columns: `stop_id, label, floor, confirmed, note`. It is pre-filled with the provisional labels from `clean-data/2026-11-23/locations_provisional.csv` and `confirmed=no`. Fix a label, set `confirmed=yes` and rerun. |
| `crosswalk_17nov_to_23nov.csv` | Maps each 17-Nov stop onto a 23-Nov place name, with `confidence` (high/medium/low/none), the basis and a note. Only `high` and `medium` are used. |

**Label rule:** a 23-Nov stop is used if `confirmed=yes`, or if it has its own `From X` walk file after it. `clean.py` names a stop after the next walk's origin, so a stop with no walk after it got a copy of the following stop's label. Those stops (BM14, BM17, BM19, BM40) and BM42, which has no label, are left out until the team confirms them.

## What was trained on what

All features are 2 s magnetometer windows (field strength |B|: mean, sd, 10th and 90th percentile; optionally also the mean x/y/z) or 10 s Wi-Fi chunks (strongest RSSI per BSSID, -100 if not heard). The models are kNN (k=5, distance-weighted) and a random forest (200 trees, balanced, seed 21). "Baro floor +" means the barometer picks the floor first, then a model trained only on that floor's places picks the place. A visit's answer is the majority vote over its windows.

1. **MAIN: 23 Nov, later revisits.** Six places have two real visits (each visit has its own walk file). Training uses every other usable 23-Nov stop (31 visits, 31 places). Testing uses the latest visit of each of those 6 places. The classifier chooses among all 31 places, so chance is 3.2%.

   | place | train stop | test stop | gap |
   |---|---|---|---|
   | exit 5 stairs | BM23 | BM26 | 4 min |
   | exit lift 10 | BM11 | BM15 | 10 min |
   | esca turun bawah | BM33 | BM41 | 12 min |
   | canteen | BM01 | BM16 | 25 min |
   | exit lift 5 | BM02 | BM20 | 62 min |
   | y5302 | BM04 | BM25 | 68 min |

   This is **leakage-reduced, not leakage-free**: it is the same day, the same phone and the same person. `revisit_23_reverse` (train on the later visits, test on the earliest) is also in the JSON.
2. **SECONDARY: true cross-day.** Train on 23 Nov and test on 17 Nov, using only the places both days share. "Core" means 15 places with high-confidence matches (17 test visits, chance 6.7%). "Extended" adds 6 route-inferred matches, giving 21 places. The reverse direction (train 17, test 23) is in the JSON only.
3. **BASELINE (leaky): same visit, time split.** Inside every stop, the first 60% of the windows train and the last 40% test, with a one-window gap.

## Numbers (place accuracy per visit; window-level and within-one-neighbour figures are in the JSON)

| Method | Same visit, 23 Nov (n=37) | **Revisit, 23 Nov (n=6)** | Same visit, 17 Nov core (n=17) | **Cross-day 23→17 core (n=17)** |
|---|---|---|---|---|
| Magnetic \|B\| kNN | 49% | 0% | 59% | 24% |
| Baro floor + magnetic \|B\| kNN | 65% | 0% | 77% | 24% (within one neighbour 41%) |
| Magnetic \|B\|+xyz kNN | 100% | 50% | 100% | 24% |
| Baro floor + magnetic \|B\|+xyz kNN | 100% | **67%** (4/6, window 58%) | 100% | 24% (within one neighbour 47%) |
| Wi-Fi RSSI RF | 11% | 0% | 11% | 33% (n=9, chance 11%) |
| chance | 3.2% | 3.2% | 6.7% | 6.7% |

**Floor (barometer):**

| Method | Train 17 → test 23 | Train 23 → test 17 |
|---|---|---|
| Absolute pressure threshold | 23/42 | 15/26 |
| Threshold re-zeroed at the first stop | 29/42 | 26/26 |
| Step tracking (floor changes when consecutive stops jump by more than half a floor step) | **42/42** | **26/26** |

One floor step is 0.58 hPa (17 Nov) and 0.68 hPa (23 Nov). On 23 Nov the weather pushed floor-5 pressure up by 0.46 hPa over the session. That is almost a whole floor, which is why a fixed threshold fails. In every fused method the predicted place is on the right floor 100% of the time.

**What the numbers say:**
- The gap between "same visit" (~100% with xyz) and "later revisit" (67%) or "other day" (24%) is the leakage.
- Cross-day place accuracy is about 3.5 times chance.
- The floor is solved by step tracking.

## Figures (`out/`)

- `fig_accuracy_overview.png`: same visit vs revisit vs other day for each method, with chance marked.
- `fig_confusion_revisit_23nov.png`: the main split, magnetic fusion and Wi-Fi.
- `fig_confusion_cross_day.png`: train 23, test 17, core places.
- `fig_pressure_by_stop.png`: pressure per stop on both days, showing the floor jumps and the 23-Nov drift.
- `fig_magnetic_17_vs_23.png`: mean |B| per shared place on each day (r = 0.71).

## Other outputs

- `out/summary_table.csv`: every experiment × method.
- `out/revisit_check_23nov.csv`: each repeated 23-Nov label with its time, pressure, the walk files before and after it, and a verdict.
- `out/places.csv`: the 31 usable 23-Nov places, their tier, and the stops on each day.

## Phones

- **Stops:** iPhone17,4 on both days.
- **Walks:** iPhone19,2 on both days.
- **Wi-Fi:** different Samsung phones. 17 Nov used an SM-A556E (Android 15) and 23 Nov an SM-S9280 (Android 16), both on WiGLE 2.111.

There is no per-device calibration. |B|-only features don't depend on how the phone was turned. x/y/z features do, and they only work when the phone is held the same way (they score well on same-day revisits but not across days). Wi-Fi "presence" features, which ignore RSSI offsets between the two Samsungs, are also in the JSON. We can't check whether the same physical iPhone was used both days, or whether its magnetometer output is calibrated.

## Caveats

- **Small n.** The main result has 6 test visits and the cross-day result has 17. One visit is 17% or 6% of the score. Treat them as first estimates.
- **Labels are provisional.** The 23-Nov labels are unconfirmed, and 6 of the 21 cross-day place matches rest on route order rather than labels. See `note` in both CSVs.
- **Only 2 days,** at different times (17 Nov around 21:15, 23 Nov 17:17–19:01), with stops of different lengths (30 s vs 60 s).
- **Wi-Fi is not a fingerprint in this data.** WiGLE writes a network to its CSV only when it is new or its signal improves, so 80% of 23-Nov BSSIDs appear at just one stop. The six revisit pairs share 0–3 access points out of 17–107 each. Wi-Fi therefore scores near zero even inside one stop. This is a logging limitation, not proof that Wi-Fi can't locate. It also means "dense Wi-Fi" in `WHATS-LEFT-TO-COLLECT.md` means many rows, not repeated scans. 17 Nov has Wi-Fi at only 9 of the 15 core places.
- **"Within one neighbour"** uses consecutive stops on either route plus `map/edges_floor5.csv`. There is no floor-4 map yet.

## What day 3 would add

- A third independent session gives the planned "train on days 1–2, test on day 3" setup. That means more visits per place, both test directions with one phone protocol, and enough test visits for a stable number.
- For Wi-Fi to be usable, log **every scan**, not the WiGLE CSV, then check that an access point heard at one stop appears at every nearby stop. One way might be WiGLE's database export or a scan-logging app, but this is untested.
- Hold the phone the same way at every stop (flat, top edge facing the landmark). The x/y/z magnetic features need that.
- Record a stop, then a walk, every time. A stop with no walk after it can't be named automatically.

## Reused code

The model set-up (median impute + standard scaling, distance-weighted kNN, 200-tree balanced random forest with seed 21) and the per-recording majority vote were adapted from `phase2/training/pipeline.py` on the unmerged `prep/training` branch (8a51469). That branch's label-gated workflow targets the 14-Nov data format, so it wasn't run here. The windowing follows `positioning-pilot/pilot_train.py` (2 s windows, time split inside a stop).
