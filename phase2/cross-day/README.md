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
| `labels_23nov_confirmed.csv` | **The 23-Nov labels.** 23 Nov is the reference dataset. Columns: `stop_id, label, floor, confirmed, note`. Each place has one English ID per physical spot; a floor-4 spot with a floor-5 namesake gets `_4F`. The labels come from the collector's own route list (one walk per line, 37 lines = the 37 walk files in time order), lined up with the stop timestamps and walk-file names. Floor comes from the collector's rule (floor 5 until the stairs walk after BM26, floor 4 after it) and agrees with the barometer for all 42 stops. All 42 stops are `confirmed=yes` (the collector confirmed BM14). Edit, then rerun. |
| `crosswalk_17nov_to_23nov.csv` | Maps each 17-Nov stop onto a 23-Nov place name, with `confidence` (high/medium/low/none), the basis and a note. Only `high` and `medium` are used. |

**Label rule:** a 23-Nov stop is used if `confirmed=yes`, or if it has its own `From X` walk file after it. `clean.py` named each stop after the next walk's origin, so a stop with no walk after it got a copy of the following stop's label.

**Changes from Dicta's provisional labels** (`out/label_changes_vs_provisional.csv`):
- BM17: esca naik atas → `escalator_down` (end of the "kantin → esca turun" walk).
- BM19: exit lift 5 → `canteen` (end of the "esca naik → kantin" walk).
- BM40: esca turun bawah → `exit_5_4F` (end of the "entrance/exit → exit 5" walk).
- BM42: no label → `escalator_up_4F` (end of the last walk, "escalator down → up", file 'From esca turun bawah').
- BM25: y5302 → `y5302_back` (the back door; a different spot from BM04).
- BM14: exit lift 10 → `exit_5`, confirmed by the collector. Step 13 ends at exit 5 (BM14); they then walked to exit 10 without recording it, and step 14 starts there (BM15). The phone moved during BM14 (magnetometer spread 23 µT), so it is a noisy training visit.

**Walks that were not recorded** (the collector skipped them): exit 5 → exit 10 between BM14 and BM15; escalator down → escalator up between BM17 and BM18; canteen → exit 5 between BM19 and BM20 (after the 32-minute break; skipped because that walk was already recorded as step 1); exit 5 (4F) → escalator down (4F) between BM40 and BM41.

The other 36 stops keep Dicta's meaning under the new IDs. Dicta's floors are all correct.

## What was trained on what

All features are 2 s magnetometer windows (field strength |B|: mean, sd, 10th and 90th percentile; optionally also the mean x/y/z) or 10 s Wi-Fi chunks (strongest RSSI per BSSID, -100 if not heard). The models are kNN (k=5, distance-weighted) and a random forest (200 trees, balanced, seed 21). "Baro floor +" means the barometer picks the floor first, then a model trained only on that floor's places picks the place. A visit's answer is the majority vote over its windows.

1. **MAIN: 23 Nov, later revisits.** Nine places were recorded more than once (the collector re-recorded a spot every time they passed it). Training uses every other 23-Nov stop (33 visits, 31 places). Testing uses the latest visit of each of the 9 places. The classifier chooses among all 31 places, so chance is 3.2%.

   | place | train stop(s) | test stop | gap from the latest training visit |
   |---|---|---|---|
   | canteen | BM01, BM16 | BM19 | 4 min (31 min from BM01) |
   | exit_5_stairs | BM23 | BM26 | 4 min |
   | escalator_down | BM13 | BM17 | 9 min |
   | exit_10 | BM11 | BM15 | 10 min |
   | escalator_up_4F | BM35 | BM42 | 10 min |
   | escalator_down_4F | BM33 | BM41 | 12 min |
   | escalator_up | BM12 | BM18 | 13 min |
   | exit_5_4F | BM30 | BM40 | 16 min |
   | exit_5 | BM02, BM14 | BM20 | 44 min (62 min from BM02) |

   This is **leakage-reduced, not leakage-free**: it is the same day, the same phone and the same person. `revisit_23_reverse` (train on the later visits, test on the earliest) is also in the JSON.
2. **SECONDARY: true cross-day.** Train on 23 Nov and test on 17 Nov, using only the places both days share. "Core" means 15 places with high-confidence matches (17 test visits, chance 6.7%). "Extended" adds 8 route-inferred matches, giving 23 places. The reverse direction (train 17, test 23) is in the JSON only.
3. **BASELINE (leaky): same visit, time split.** Inside every stop, the first 60% of the windows train and the last 40% test, with a one-window gap.

## Numbers (place accuracy per visit; window-level and within-one-neighbour figures are in the JSON)

| Method | Same visit, 23 Nov (n=42) | **Revisit, 23 Nov (n=9)** | Same visit, 17 Nov core (n=17) | **Cross-day 23→17 core (n=17)** |
|---|---|---|---|---|
| Magnetic \|B\| kNN | 38% | 0% | 59% | 18% |
| Baro floor + magnetic \|B\| kNN | 57% | 11% | 77% | 18% (within one neighbour 35%) |
| Magnetic \|B\|+xyz kNN | 98% | 78% | 100% | 24% (4/17) |
| Baro floor + magnetic \|B\|+xyz kNN | 100% | **78%** (7/9, window 69%, within one neighbour 89%) | 100% | 18% (within one neighbour 53%) |
| Wi-Fi RSSI RF | 10% | 0% | 11% | 11% (n=9, chance 11%) |
| Baro floor + Wi-Fi RSSI RF | 10% | 0% | 22% | 22% |
| chance | 3.2% | 3.2% | 6.7% | 6.7% |

The two misses on revisits are BM40 (exit_5_4F, predicted lt2a, its neighbour) and BM41 (escalator_down_4F, predicted lt1b).

**Floor (barometer):**

| Method | Train 17 → test 23 | Train 23 → test 17 |
|---|---|---|
| Absolute pressure threshold | 23/42 | 15/26 |
| Threshold re-zeroed at the first stop | 29/42 | 26/26 |
| Step tracking (floor changes when consecutive stops jump by more than half a floor step) | **42/42** | **26/26** |

One floor step is 0.58 hPa (17 Nov) and 0.68 hPa (23 Nov). On 23 Nov the weather pushed floor-5 pressure up by 0.46 hPa over the session. That is almost a whole floor, which is why a fixed threshold fails. In every fused method the predicted place is on the right floor 100% of the time.

**What the numbers say:**
- The gap between "same visit" (~100% with xyz) and "later revisit" (78%) or "other day" (18–24%) is the leakage.
- Cross-day place accuracy is about 3 times chance; it is worse than same-day revisits, so day-to-day change (and how the phone is held) matters more than time within a day.
- The floor is solved by step tracking.

## Orientation correction (tilt), 23-Nov walks only

Run `python phase2/cross-day/tilt.py` after `crossday.py`. It writes `out/tilt_results.json`, `out/tilt_endpoints.csv` and `out/fig_tilt.png`. The baseline results above are unchanged.

**Why only walks.** Stop recordings (BM*) logged only the barometer and magnetometer on both days, so the phone's tilt at a stop is unknown and stops can't be corrected. The 23-Nov walk recordings (ACC*) logged accelerometer, gyroscope and magnetometer in one file on one clock (starts agree within 0.11 s, all ~100 Hz). The 17-Nov walks logged only the accelerometer, so they can't be used.

**What it does.**
- For each walk it estimates gravity in the phone frame. It does this two ways: the mean accelerometer over the window ("low-pass"), and a gyro-aided complementary filter.
- It splits the magnetic field into a vertical part along gravity (B_vertical) and a horizontal part (B_horizontal). Both stay the same however the phone is tilted or turned.
- The first and last 2 s of each walk become fingerprints of its start and end place, using the labels of the stop before and after. That gives 66 endpoints over 31 places. Walks shorter than 5 s are skipped because their two ends would overlap; this drops BM20's walk, among others.
- The phone was 8–21° from flat at the endpoints (median 13°).

**Results** (same samples for every feature set; 1-nearest-neighbour; 31 places, chance 3%):

| Features | Silhouette (25 places with 2+ endpoints) | Other-pass accuracy, leave one pass out (28 test endpoints) | Latest pass only (10 endpoints) |
|---|---|---|---|
| \|B\| only | -0.49 | 0% | 0% |
| raw x/y/z | -0.43 | 0% | 0% |
| B_vertical + B_horizontal, low-pass gravity | **-0.16** | **39%** (11/28) | 40% |
| B_vertical + B_horizontal, gyro-aided gravity | -0.19 | 29% | 30% |

A "pass" is one stop and the walk ends next to it. The test pass's endpoints are never in training.

**What worked.**
- Splitting the field along gravity clearly helps on walk endpoints: 0% → 39%.
- Raw x/y/z fails here because the phone points in the walking direction, which differs between passes.
- |B| alone is one number and isn't enough to tell 31 places apart.
- Gyro-aided gravity did not beat the plain average. The endpoints are near-standing, so averaging the accelerometer is enough. The filter's sign convention was checked: its gravity tracks the smoothed accelerometer within about 2°.

**What didn't.**
- Silhouettes are still negative. Walk endpoints are noisy (people are starting or stopping), so these are weak fingerprints.
- Walk endpoints can't simply be added to the stop fingerprints: walks used a different phone (iPhone19,2) from stops (iPhone17,4), and the two phones' |B| at the same places correlate only r = 0.20 (median difference 4 µT).

**For day 3:** log the accelerometer (and gyroscope) at stops too, with the same phone as the walks. Then every stop gets B_vertical/B_horizontal, which on this evidence are the orientation-proof features worth having. Cross-day is exactly where phone orientation changes.

## Figures (`out/`)

- `fig_accuracy_overview.png`: same visit vs revisit vs other day for each method, with chance marked.
- `fig_confusion_revisit_23nov.png`: the main split, magnetic fusion and Wi-Fi.
- `fig_confusion_cross_day.png`: train 23, test 17, core places.
- `fig_pressure_by_stop.png`: pressure per stop on both days, showing the floor jumps and the 23-Nov drift.
- `fig_magnetic_17_vs_23.png`: mean |B| per shared place on each day (r = 0.70).

## Other outputs

- `out/summary_table.csv`: every experiment × method.
- `out/revisit_check_23nov.csv`: each repeated 23-Nov label with its time, pressure, the walk files before and after it, and a verdict.
- `out/places.csv`: the 31 usable 23-Nov places, their tier, and the stops on each day.
- `out/label_changes_vs_provisional.csv`: each stop's current label vs Dicta's provisional one, and floor vs barometer.

## Phones

- **Stops:** iPhone17,4 on both days.
- **Walks:** iPhone19,2 on both days.
- **Wi-Fi:** different Samsung phones. 17 Nov used an SM-A556E (Android 15) and 23 Nov an SM-S9280 (Android 16), both on WiGLE 2.111.

There is no per-device calibration. |B|-only features don't depend on how the phone was turned. x/y/z features do, and they only work when the phone is held the same way (they score well on same-day revisits but not across days). Wi-Fi "presence" features, which ignore RSSI offsets between the two Samsungs, are also in the JSON. We can't check whether the same physical iPhone was used both days, or whether its magnetometer output is calibrated.

## Caveats

- **Small n.** The main result has 9 test visits and the cross-day result has 17. One visit is 11% or 6% of the score. Treat them as first estimates.
- **Labels.** The 23-Nov labels come from the collector's route list lined up by time, so they are much firmer than before. The 17-Nov side is still inferred: 8 of the 23 cross-day place matches rest on route order rather than labels. See `note` in both CSVs.
- **Only 2 days,** at different times (17 Nov around 21:15, 23 Nov 17:17–19:01), with stops of different lengths (30 s vs 60 s).
- **Wi-Fi is not a fingerprint in this data.** WiGLE writes a network to its CSV only when it is new or its signal improves, so 80% of 23-Nov BSSIDs appear at just one stop. The nine revisit pairs share 0–3 access points (out of 4–192 per stop). Wi-Fi therefore scores near zero even inside one stop. This is a logging limitation, not proof that Wi-Fi can't locate. It also means "dense Wi-Fi" in `WHATS-LEFT-TO-COLLECT.md` means many rows, not repeated scans. 17 Nov has Wi-Fi at only 9 of the 15 core places.
- **"Within one neighbour"** uses consecutive stops on either route plus `map/edges_floor5.csv`. There is no floor-4 map yet.

## What day 3 would add

- A third independent session gives the planned "train on days 1–2, test on day 3" setup. That means more visits per place, both test directions with one phone protocol, and enough test visits for a stable number.
- For Wi-Fi to be usable, log **every scan**, not the WiGLE CSV, then check that an access point heard at one stop appears at every nearby stop. One way might be WiGLE's database export or a scan-logging app, but this is untested.
- Hold the phone the same way at every stop (flat, top edge facing the landmark). The x/y/z magnetic features need that.
- Record a stop, then a walk, every time. A stop with no walk after it can't be named automatically.

## Reused code

The model set-up (median impute + standard scaling, distance-weighted kNN, 200-tree balanced random forest with seed 21) and the per-recording majority vote were adapted from `phase2/training/pipeline.py` on the unmerged `prep/training` branch (8a51469). That branch's label-gated workflow targets the 14-Nov data format, so it wasn't run here. The windowing follows `positioning-pilot/pilot_train.py` (2 s windows, time split inside a stop).
