# Day 3 (24 Nov) evaluation: leakage-free positioning on the two-session dataset

*Internal team notes, not report text (course rule: an LLM may only polish our own writing). Code, numbers and figures only.*

Every number below is copied from a file in `out/` that the scripts write (`results.json`, `fused_knn.json`, `wifi_diagnosis.json`, `track24_results.json`). Accuracy is per stop recording unless a line says otherwise. Chance = 1 / number of places in training.

## Run (one command, from the repo root)

```sh
sh phase2/new/day3/run_all.sh        # PYTHON=.venv/bin/python sh ... to pick the interpreter; about 10 min
```

Needs `numpy pandas scikit-learn scipy matplotlib` (the repo's `.venv/` has them; it is gitignored). The first run parses the 24-Nov CSVs (~670 MB) into `day3/cache/` (gitignored) and, if missing, rebuilds the 23-Nov cache through `cross-day/crossday.py`.

| step | script | writes |
|---|---|---|
| data tables | `data.py` | `cache/` only |
| Wi-Fi diagnosis | `wifi_check.py` | `out/wifi_diagnosis.json` |
| cross-session, cross-day, walk endpoints, floor | `evaluate.py` | `out/results.json`, `out/summary_table.csv` |
| weighted fused kNN, nested CV | `fused_knn.py` | `out/fused_knn.json`, `out/fused_model.json`, `out/fused_window_predictions.csv` |
| tracker on 24 Nov + UI replay | `track24.py` | `out/track24_results.json`, `out/track24_visits.csv`, `out/replay_24nov_s2.json` |
| figures + data explorer | `visualise.py` | `out/*.png`, `out/explore.html` |
| kNN playground (sliders -> neighbours -> place; internal) | `playground.py` (template `playground_template.html`; check `playground_check.py`) | `out/knn_playground.html` |

## Adding a session collected later

1. Clean it with `phase2/clean-data/2026-11-24/scripts/build_clean.py` (same `clean/` layout: `manifest.csv`, `floor*/stops|walks/<folder>/<phone>/<Sensor>.csv`, `wifi/observations.csv`).
2. Add one entry to `config.json` under `sessions` (`"loader": "clean_tree"`, `path`, `day`, `names`). If the new session uses node names that `names_24nov.csv` does not know, add rows there (or point `names` at a new CSV with the same columns). Unknown names are listed in `data.py`'s output and are never silently dropped from the log.
3. `sh phase2/new/day3/run_all.sh`. The fused kNN automatically adds the new session as one more leave-one-session-out fold. `evaluate.py` and `track24.py` have named splits for the current three sessions; add a line there for a new named split.

## Names (24 Nov -> graph-v2)

`names_24nov.csv` maps every 24-Nov node to a graph-v2 place (26 places; every 24-Nov stop and walk end is mapped, nothing unmapped). Places are scored on the graph-v2 names (study rooms = `sr9`, lift+stairs = `lift_stairs` / `lift_stairs_4F`).

Needs confirmation from the collector (mapped by route position, `confidence = medium`):
- `male_disabled_toilet` (5F) = 23-Nov `disabled_toilet` (exit 5 -> it -> lift/stairs on both days).
- `y5302_point2` (5F, "other door") = 23-Nov `y5302_back` (after Y5401 on both days).
- `gate` (4F) = 23-Nov `entrance_exit` (exit 10 -> it -> exit 5 on both days).

No v1 name exists for `sr9` (the 24-Nov study-room stop: which of the four rooms it was is not recorded) and `lift_stairs5` (one stop on 24 Nov, two v1 places), so v1 (31-place) scoring is not possible on 24 Nov.

## Phones: the "iphone" is two different handsets

From `manifest.csv` (`device` column), summarised in `out/results.json` `devices`:

| session | iphone | s24 |
|---|---|---|
| 23 Nov stops | iPhone17,4 | (Wi-Fi scanner SM-S9280) |
| 23 Nov walks | iPhone19,2 | |
| 24 Nov session 1 | **iPhone19,2** | SM-S9280 |
| 24 Nov session 2 | **iPhone17,4** | SM-S9280 |

So "iPhone, session 1 -> session 2" is a different-handset test; the S24 is the only same-handset cross-session pair on 24 Nov. The true same-handset cross-day pair is 23-Nov stops -> 24-Nov session 2 (iPhone17,4 both). Both session READMEs call the iPhone "iPhone 16 Pro"; the device IDs differ.

## Results

Chance is 1/26 = 3.8% for every stop task below (26 graph-v2 places in training). Cells are exact place, correct / test recordings, with the area count (graph-v2 pre-registered areas) in brackets. "+ floor" = the iPhone barometer floor (step tracking, threshold from the training session) restricts the candidates. kNN k = 5, 5 s windows, equal weight per feature group. Source: `out/results.json` (`stop_results`), also flat in `out/summary_table.csv`.

### a. Cross-session on 24 Nov (train one session, test the other, same phone role)

| features | iPhone s1->s2 | iPhone s2->s1 | S24 s1->s2 | S24 s2->s1 |
|---|---|---|---|---|
| \|B\| + floor | 4/26 (8) | 5/27 (6) | 4/26 (9) | 5/27 (12) |
| \|B\|+xyz + floor | 12/26 (14) | 14/27 (16) | 8/26 (12) | 10/27 (16) |
| tilt (B_vertical, B_horizontal) + floor | 7/26 (9) | 9/27 (9) | 6/26 (9) | 3/27 (11) |
| \|B\|+xyz+tilt + floor | 12/26 (14) | 15/27 (15) | 7/26 (10) | 8/27 (13) |
| Wi-Fi + floor | 8/26 (10) | 6/27 (7) | 8/26 (10) | 6/27 (7) |
| \|B\|+xyz+Wi-Fi + floor | 12/26 (12) | 14/27 (16) | 7/26 (12) | 9/27 (15) |
| Wi-Fi, in-window rows only (no floor) | 2/26 (3) | 2/27 (3) | 2/26 (3) | 2/27 (3) |

The iPhone columns are two different handsets (iPhone19,2 vs iPhone17,4); the S24 is one handset. Without the floor the numbers are in the JSON (e.g. iPhone \|B\|+xyz+tilt 13/26 and 15/27).

**Leaky reference** (same recording split in time, first 60% trains): \|B\|+xyz 26/26 on both phones (24 s2). That is the gap between "same recording" and "another session".

Tilt: B_vertical/B_horizontal alone beat \|B\| alone (iPhone 8/26 and 8/27 vs 1/26 and 2/27 without floor), but adding tilt to \|B\|+xyz changes the iPhone result by at most one recording and makes the S24 worse. At stops the phone is held the same way (flat, facing the door), so raw x/y/z already carries the orientation-dependent part that tilt correction was meant to fix.

### b. True cross-day (iPhone stops)

| split | \|B\| + floor | \|B\|+xyz + floor | Wi-Fi + floor | \|B\|+xyz+Wi-Fi + floor |
|---|---|---|---|---|
| 23 Nov -> 24 s2, same handset iPhone17,4 | 5/26 (12) | **13/26** (14) | 4/26 (8) | 14/26 (16) |
| 24 s2 -> 23 Nov, same handset | 6/42 (9) | **18/42** (19) | 5/42 (9) | 14/42 (20) |
| 23 Nov -> 24 s1, different handsets | 6/27 (10) | 11/27 (14) | 5/27 (8) | 11/27 (14) |
| 23 Nov + 24 s1 -> 24 s2 (two training sessions) | 5/26 (9) | 15/26 (15) | 8/26 (11) | 12/26 (13) |

23-Nov stops have no accelerometer, so no tilt features in the first three rows; in the last row \|B\|+xyz+tilt + floor gives 16/26 (tilt from the 24 s1 part only). Compare: the 17-Nov cross-day test (23 -> 17, 15 places, chance 6.7%) gave 18 to 24% (`cross-day/README.md`); here the same handset and the same stop protocol on both days gives 13/26 and 18/42 with 26 places.

**Walk endpoints** (first/last 2 s of each walk, 1-NN as in `cross-day/tilt.py`, per endpoint; `walk_endpoint_results`):

| split | \|B\| | raw x/y/z | tilt | chance |
|---|---|---|---|---|
| 23 Nov -> 24 s1, iPhone19,2 both days | 6/54 | 15/54 | 13/54 | 3.8% |
| 24 s1 -> 23 Nov, iPhone19,2 both days | 5/66 | 21/66 | 19/66 | 3.8% |
| 24 s1 -> 24 s2, S24 same handset | 4/50 | 7/50 | 6/50 | 4.0% |
| 24 s2 -> 24 s1, S24 same handset | 2/50 | 8/50 | 8/50 | 4.0% |

The 23-Nov same-day result (tilt 39% vs 0% for raw x/y/z, entry 15) does not carry over: across days raw x/y/z is as good as or better than tilt on walk endpoints, because both days walk the route in the same direction, so the phone points the same way.

### c. Wi-Fi: verdict

**Not usable as a fingerprint on this data.** WiGLE still writes an access point only when it is new or stronger (`out/wifi_diagnosis.json`):
- Inside one 60 s stop, each BSSID appears a median of 1.02 to 1.08 times (`rows_per_bssid_inside_one_stop_median`), although the scanner logged a median of 6 to 12.5 distinct scan times per stop.
- Of all repeat rows of a BSSID, 90% to 100% are stronger than every earlier row of that BSSID in the same log (`share_repeats_stronger_than_all_earlier_rows`, 9 logs).
- Rows assigned inside the stop dwell: 1841 in session 1 vs 13597 within 120 s (`rows_assigned`); this is the 1789 vs 11808 of `sesi1/clean/summary.json`, recounted. Most Wi-Fi rows are the first sighting on the walk towards a stop, not a reading at the stop.
- Inside one session, 85% (session 1) and 63% (session 2) of in-window BSSIDs are heard at one stop only.
- Across sessions (S24 scanner, rows within 120 s): the most similar stop by BSSID overlap is the same place for 7/13 session-2 test stops vs session 1, and 6/26 for 23 Nov vs session 2 (`nearest_by_jaccard_is_same_place`). Only 14 of the 27 session-1 stops have S24 Wi-Fi rows at all.
- Classification: in-window rows only 2/26 and 2/27 (near chance, 3.8%); with the 120 s approach rows 6 to 8 of 26/27 within 24 Nov, and 4/26, 5/42 across days with the floor. Adding Wi-Fi to \|B\|+xyz does not help consistently.

The approach rows carry some route-order information (the same new access points appear on the same walk in both sessions), which is not a property of the place. A logger that records every scan is still needed before Wi-Fi can be judged.

### d. Barometer floor (`floor`, `floor_stats`)

| session | iPhone step tracking | iPhone fixed threshold | S24 step tracking |
|---|---|---|---|
| 23 Nov | 42/42 | 26/42 | (no S24 pressure) |
| 24 s1 | **23/27** | 27/27 | 13/27 |
| 24 s2 | 26/26 | 12/26 | 17/26 |

FAILURE in 24 s1: the 4 floor-5 stops after the break (disabled_toilet 18:12, lift_stairs, y5401, y5302_back; the stop before was escalator_up at 16:49) are called floor 4 (`step_tracking_wrong_stops`). Pressure rose 0.833 hPa across the break (weather), more than the 0.315 hPa jump threshold, so it looked like going down a floor; the real step down at 18:26 then could not register (already "floor 4"). The S24 floor step is -0.014 hPa in session 1 and the median within-stop SD is 0.234 to 0.438 hPa (iPhone 0.005 to 0.034): the S24 pressure sensor cannot be used for floors.

### e. Weighted fused kNN (`fused_knn.py`, `out/fused_knn.json`)

One kNN over every stop window of every phone and session (2425 windows, 202 recordings, 95 stops, 26 places). Five feature groups with their own distance and weight: \|B\|, magnetic x/y/z, tilt, Wi-Fi (S24, 120 s rows), barometer floor. Weights on the simplex (step 0.25, then step 0.1 near the best) and k in {1, 3, 5, 9, 15, 25} are chosen by inner cross-validation on the training part only, then scored once on the held-out part.

| split (outer) | fused, learned weights | equal weights | best single group | chance |
|---|---|---|---|---|
| random windows (**LEAKY, illustration only**) | 932/935 = 99.7% | 932/935 | x/y/z 916/935 | 3.8% |
| whole recordings, other phones of the same stop may train (partly leaky) | 112/202 = 55.4% | 94/202 | Wi-Fi 112/202 | 3.8% |
| whole stops, GroupKFold(5) (honest) | **58/202 = 28.7%** [22.9-35.3] | 54/202 | x/y/z 52/202 | 3.8% |
| whole sessions, leave one session out (most honest) | **74/202 = 36.6%** [30.3-43.5] | 71/202 | x/y/z 64/202 | 3.8% |

- The leaky random split is the same kind of leak as the old 94% pilot: the 5 s windows of one recording are near-copies, so a random split always has a twin in training.
- The "whole recordings" split is a second, subtler leak: on 24 s1 four phones recorded each stop at the same time, and Wi-Fi and the floor are per stop, so a held-out phone's stop still has its Wi-Fi vector in training. The inner CV duly gives Wi-Fi 0.7 of the weight there, and "Wi-Fi only" scores 112/202 under that split but 22/202 under grouped CV.
- Chosen weights (B, xyz, tilt, wifi, baro) per leave-one-session-out fold: test 23 Nov (0.1, 0.5, 0, 0.3, 0.1), k 3, 9/42; test 24 s1 (0.1, 0.6, 0, 0.2, 0.1), k 3, 42/108; test 24 s2 (0, 0.2, 0, 0.3, 0.5), k 25, 23/52. Grouped-CV folds mostly chose baro 0.5 to 0.7 with tilt 0.1 to 0.4 and k 25.
- **Deployable setting** (tuned by leave-one-session-out on all three sessions, `out/fused_model.json`): w_B 0.1, w_xyz 0.7, w_tilt 0, w_wifi 0.1, w_baro 0.1, k 25 (inner accuracy 0.46).
- Learned weights beat equal weights by 3 to 4 recordings in both honest splits; that is inside the interval.
- Pooling all phones costs accuracy: the per-phone, same-handset split 24 s2 -> 23 Nov gets 18/42 with \|B\|+xyz + floor, while the pooled model gets 9/42 on 23 Nov. The phones' magnetometers disagree (offsets, frames), so one pooled kNN mixes them.

### f. Tracker on 24 Nov (`track24.py`, `out/track24_results.json`)

`tracking/tracker.py` v2, unchanged, on graph-v2. Train session 1 (fingerprints iPhone19,2, line lengths from session-1 walks, floor threshold 0.243 hPa), replay session 2 (iPhone17,4). 26 stops:

| method | exact | area | within one neighbour | top-3 | floor |
|---|---|---|---|---|---|
| tracker | 20/26 [58-89%] | 20/26 | 22/26 | 21/26 | 24/26 |
| snapshot kNN (crossday.py recipe, 2 s windows) | 15/26 | 18/26 | 19/26 | 21/26 | 26/26 |
| emission only (no graph) | 15/26 | 15/26 | 18/26 | 19/26 | 24/26 |
| tracker on arrival (before the stop's data) | 13/26 | 18/26 | 18/26 | 19/26 | 23/26 |

Optimistic in the same ways as entry 20: the graph and the walk order are the route both sessions walked, and every walk is one recorded line. "Confirmed" frames: 2095 of 3122 stop frames, 1830 of them correct. Replay: `out/replay_24nov_s2.json` (3560 frames, same format as `tracking/out/replay_23nov.json`, graph-v2 nodes). Open it with `phase2/new/circle-ui/index.html?data=../day3/out/replay_24nov_s2.json` over http (e.g. `python -m http.server` in `phase2/new`). The 23-Nov replay and the UI are unchanged.

## Figures (`out/`)

- `fig_accuracy_vs_chance.png`: accuracy per feature set vs chance (cross-session iPhone and S24, cross-day same iPhone).
- `fig_leaky_vs_honest.png`: the same fused kNN under the four splits.
- `fig_confusion.png`: confusion matrices, fused kNN leave-one-session-out (windows) and 23 Nov -> 24 s2 (recordings).
- `fig_floor_detection.png`: pressure per stop over time, iPhone vs S24, three sessions.
- `fig_per_place_B_pressure.png`: \|B\| and pressure per place and session (strip plot).
- `fig_knn_neighbour_graph.png`: nearest-neighbour "confusion as a graph" on the graph-v2 layout.
- `fig_embed_*.png`: PCA and t-SNE of the magnetic features, \|B\|+tilt (24 Nov), the fused space (t-SNE on the learned-weight distance) and Wi-Fi (MDS, one dot per stop).
- **`explore.html`**: interactive explorer (plotly from a CDN, pinned with an integrity hash). Views: every embedding above, raw \|B\| vs B_vertical, barometer per stop. Hover shows place, session, phone and recording; click legend entries to show or hide places.

## Data issues found

- Very strong fields (place median \|B\| above 100 uT, `results.json` `magnetic_check`): 24 s2 iPhone at escalator_down_4F 147.9 and escalator_up_4F 142.5 uT, 24 s2 S24 at escalator_down_4F 127.7, 24 s1 S24 at disabled_toilet 121.6 and escalator_down 101.3. The iPhone on 23 Nov ranges 32.9 to 58.9 uT. Both phones see the 4F down-escalator in session 2, so it is more likely something physical there that night (running escalator machinery?) than one sensor. Worth asking the collector; see `fig_per_place_B_pressure.png`.
- `sesi2/clean/ROUTE.md` says "Sensors-only (no Wi-Fi logged)", but the same session has a WiGLE log (`sesi2/clean/README.md`, `summary.json`).
- Session 2 has walks out of route order (floor 5: exit10 -> canteen, then the escalator-up stop, then three walks esca_up -> canteen, canteen -> esca_down, esca_up -> esca_down; floor 4: the walk gate -> exit 5 was recorded before the gate stop). The tracker attaches each walk to the last stop before it.
- Session 1 has S24 Wi-Fi rows at only 14 of 27 stops; two S24 logs are empty (`sesi1/clean/summary.json`).
