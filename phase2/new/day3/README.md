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
| handset per recording (raw ZIP metadata) | `phone_map.py` | `phone_map.csv`, `out/phone_map_summary.json` |
| data tables | `data.py` | `cache/` only |
| Wi-Fi diagnosis | `wifi_check.py` | `out/wifi_diagnosis.json` |
| cross-session, cross-day, walk endpoints, floor | `evaluate.py` | `out/results.json`, `out/summary_table.csv` |
| weighted fused kNN, nested CV | `fused_knn.py` | `out/fused_knn.json`, `out/fused_model.json`, `out/fused_window_predictions.csv` |
| tracker on 24 Nov + UI replay | `track24.py` | `out/track24_results.json`, `out/track24_visits.csv`, `out/replay_24nov_s2.json` |
| figures + data explorer | `visualise.py` | `out/*.png`, `out/explore.html` |
| split20 variant (`--split20`): pieces, exclusions, outliers; before/after table | `data.py` (`apply_variant`), `upload_eval_split20.py`, `compare_split20.py`, `exclude_23nov.csv` | `out-split20/` (same files as `out/` plus `pieces.csv`, `outliers.csv`, `variant_summary.json`, `upload_eval_split20.json`, `compare_before_after.csv`, `compare_same_pieces.json`); control `out-split20_only/` |
| kNN playground (sliders -> neighbours -> place; phone x session panel; compare-phones panel; place filter; variance panel; internal) | `playground.py` (template `playground_template.html`; python references `phone_matrix.py`, `compare_phones.py`, `variance.py`; check `playground_check.py`) | `out/knn_playground.html`, `out/phone_session_matrix.csv/.json`, `out/phone_compare_default.csv/.json`, `out/variance_by_place.csv/.json`, `out/variance_cells_by_place.csv` |
| per-sample predictions with top-3 (learned-weight fused kNN, every scheme) | `fused_knn.py` | `out/fused_sample_predictions.csv` |
| per-phone x per-place sheet (append one run; not run by `run_all.sh`) | `perf_sheet.py` | `out/phone_place_performance.xlsx` (README, Ranking, Progress, one tab per run), `out/perf_csv/` |
| places never / rarely correct (before vs after new data) | `hard_places.py` | `out/perf_csv/hard_places_<label>.csv` |
| 25-Nov spots clean tree (our partial export; rebuilt first by `run_all.sh`) | `../../clean-data/2026-11-25-spots/scripts/build_clean.py` | `clean-data/2026-11-25-spots/clean/` |
| 25-Nov spots vs Dicta's complete 25 Nov: which recordings are duplicates | `../../clean-data/2026-11-25-spots/scripts/find_duplicates.py` | `clean-data/2026-11-25-spots/duplicates_vs_2026-11-25.csv` (session `25spots` leaves the duplicates out via `exclude_sources`) |
| 25-Nov complete dataset (Dicta, committed built) | `../../clean-data/2026-11-25/scripts/build25.py` | `clean-data/2026-11-25/clean/` |
| data gaps per place x phone (coverage, held-out accuracy / precision, to-collect list; not run by `run_all.sh`) | `gaps_sheet.py` | `out/data_gaps.xlsx`, `out/perf_csv/data_gaps_*.csv` |

## Adding a session collected later

1. Clean it into the `clean/` layout (`manifest.csv`, `floor*/stops|walks/<folder>/<phone>/<Sensor>.csv`, `wifi/observations.csv`): 24 Nov used `phase2/clean-data/2026-11-24/scripts/build_clean.py` (fixed route order); 25 Nov: Dicta's `phase2/clean-data/2026-11-25/scripts/build25.py` (route order by timestamp, the complete set, session `25nov`) and our `phase2/clean-data/2026-11-25-spots/scripts/build_clean.py` (labels from each file name, with confidence; session `25spots`, see its README). A manifest may carry a `track` column (the stops one group walked in order): barometer floor tracking and Wi-Fi assignment then run per track; without it the session is one track.
2. Add one entry to `config.json` under `sessions` (`"loader": "clean_tree"`, `path`, `day`, `names`, and `raw` so `phone_map.py` checks the handset of every recording against the raw ZIP). If the new session uses node names that `names_24nov.csv` does not know, add rows there (or point `names` at a new CSV with the same columns, first column `floor`, a `node_<day>` column and `place_v2`: `names_25nov.csv` maps Dicta's node names, `names_25spots.csv` is the identity map of the spots tree). Optional session keys: `exclude_sources` (a CSV with `source_zip` and `status`; every row whose status is not `unique` is left out, e.g. recordings already in another session), `wifi_scanner` / `wifi_log` (for an `observations.csv` without `scanner_phone` / `epoch` columns: epoch from `firstseen_hk`). Unknown names are listed in `data.py`'s output and are never silently dropped from the log.
3. `sh phase2/new/day3/run_all.sh` (and `--split20`). The fused kNN automatically adds the new session as one more leave-one-session-out fold. `evaluate.py` has named splits for 23/24 Nov and the leave-25-Nov-out splits; `track24.py` is 24 Nov only.
4. Append the run to the sheet: `python phase2/new/day3/perf_sheet.py --run-dir out-split20 --tab "<date> split20 <what>" --data "<sessions>"` (a new tab and a Progress row; nothing earlier is changed), and `python phase2/new/day3/hard_places.py --label <name> out out-split20`. Keep the old playground as a dated copy (`knn_playground_<date><letter>.html`) before the rerun overwrites it.

## Names (24 Nov -> graph-v2)

`names_24nov.csv` maps every 24-Nov node to a graph-v2 place (26 places; every 24-Nov stop and walk end is mapped, nothing unmapped). Places are scored on the graph-v2 names (study rooms = `sr9`, lift+stairs = `lift_stairs` / `lift_stairs_4F`).

Mapped by route position, **confirmed by the user on 2026-11-26** (`confidence = high`, basis `user confirmed 2026-11-26` in `names_24nov.csv` and `names_25nov.csv`; they were `medium`):
- `male_disabled_toilet` (5F) = 23-Nov `disabled_toilet` (exit 5 -> it -> lift/stairs on both days).
- `y5302_point2` (5F, "other door") = 23-Nov `y5302_back` (after Y5401 on both days).
- `gate` (4F) = 23-Nov `entrance_exit` (exit 10 -> it -> exit 5 on both days).

No v1 name exists for `sr9` (the 24-Nov study-room stop: which of the four rooms it was is not recorded) and `lift_stairs5` (one stop on 24 Nov, two v1 places), so v1 (31-place) scoring is not possible on 24 Nov.

## Phones: the phone is the real handset (ip16, ip18, s24, a55, a56)

Two different iPhones were used (the user confirmed it on 25 Nov: an iPhone 16 and an iPhone 18). The phone of every recording is read from the phyphox metadata inside the raw ZIP (`meta/device.csv`, `deviceModel`) by `phone_map.py`, which writes `phone_map.csv` (one row per recording: session, recording, type, sensor slot, source ZIP, model id, phone label, status) and `out/phone_map_summary.json`, and stops the pipeline if a model id is not in `config.json` `phones` or the raw ZIP disagrees with the cleaned manifest. `config.json` `phones` maps model id -> `id` (stable label in files and results) and `display` (the name shown in the HTML pages and figures; rename it, e.g. to "Michael's iPhone", and rerun, no code change).

| phone (`id`) | model id | recordings (stop + walk) | windows (5 s stops) |
|---|---|---|---|
| ip16 | iPhone17,4 | 23 Nov stops 42; 24 s2 stops 26 + walks 28 | 504 (23 Nov) + 312 (24 s2) = **816** |
| ip18 | iPhone19,2 | 23 Nov walks 37; 24 s1 stops 27 + walks 28 | **324** (24 s1) |
| s24 | SM-S9280 | 24 s1 (55 recordings) and 24 s2 (54) | 324 + 312 = **636** |
| a55 | SM-A556E | 24 s1 only | **324** |
| a56 | SM-A566B | 24 s1 only | **325** |

Per recording the mapping is consistent per session: 24 s1 has only ip18 on the iPhone slot, 24 s2 only ip16, 23 Nov mixes both but by recording type (all 42 stops ip16, all 37 walks ip18). No recording is undetermined (407 of 407 recordings matched to a raw ZIP, raw model = manifest model). The 14 and 17 Nov raw ZIPs (not used by day 3) also contain both iPhones (23 ip18-model and 26 ip16-model recordings each). Both session READMEs call the iPhone "iPhone 16 Pro"; the device IDs differ, and the user says ip16 + ip18.

Consequences: "iPhone, session 1 -> session 2" (ip18 -> ip16) is a different-handset test; the S24 is the only same-handset cross-session pair on 24 Nov; the true same-handset cross-day pair is 23-Nov stops -> 24-Nov session 2 (ip16 both). ip18 has data in one session only, so no same-handset cross-session test exists for it. Result keys keep the sensor-slot name (`..._iphone`, `..._s24`) and every split states its handsets in `_split.note`.

## Results

Chance is 1/26 = 3.8% for every stop task below (26 graph-v2 places in training). Cells are exact place, correct / test recordings, with the area count (graph-v2 pre-registered areas) in brackets. "+ floor" = the iPhone barometer floor (step tracking, threshold from the training session) restricts the candidates. kNN k = 5, 5 s windows, equal weight per feature group. Source: `out/results.json` (`stop_results`), also flat in `out/summary_table.csv`.

### a. Cross-session on 24 Nov (train one session, test the other, same phone role)

| features | iPhone s1->s2 (ip18 -> ip16) | iPhone s2->s1 (ip16 -> ip18) | S24 s1->s2 | S24 s2->s1 |
|---|---|---|---|---|
| \|B\| + floor | 4/26 (8) | 5/27 (6) | 4/26 (9) | 5/27 (12) |
| \|B\|+xyz + floor | 12/26 (14) | 14/27 (16) | 8/26 (12) | 10/27 (16) |
| tilt (B_vertical, B_horizontal) + floor | 7/26 (9) | 9/27 (9) | 6/26 (9) | 3/27 (11) |
| \|B\|+xyz+tilt + floor | 12/26 (14) | 15/27 (15) | 7/26 (10) | 8/27 (13) |
| Wi-Fi + floor | 8/26 (10) | 6/27 (7) | 8/26 (10) | 6/27 (7) |
| \|B\|+xyz+Wi-Fi + floor | 12/26 (12) | 14/27 (16) | 7/26 (12) | 9/27 (15) |
| Wi-Fi, in-window rows only (no floor) | 2/26 (3) | 2/27 (3) | 2/26 (3) | 2/27 (3) |

The iPhone columns are two different handsets (ip18 = iPhone19,2 vs ip16 = iPhone17,4); the S24 is one handset. Without the floor the numbers are in the JSON (e.g. iPhone \|B\|+xyz+tilt 13/26 and 15/27).

**Leaky reference** (same recording split in time, first 60% trains): \|B\|+xyz 26/26 on both phones (24 s2). That is the gap between "same recording" and "another session".

Tilt: B_vertical/B_horizontal alone beat \|B\| alone (iPhone 8/26 and 8/27 vs 1/26 and 2/27 without floor), but adding tilt to \|B\|+xyz changes the iPhone result by at most one recording and makes the S24 worse. At stops the phone is held the same way (flat, facing the door), so raw x/y/z already carries the orientation-dependent part that tilt correction was meant to fix.

### b. True cross-day (iPhone stops)

| split | \|B\| + floor | \|B\|+xyz + floor | Wi-Fi + floor | \|B\|+xyz+Wi-Fi + floor |
|---|---|---|---|---|
| 23 Nov -> 24 s2, same handset ip16 (iPhone17,4) | 5/26 (12) | **13/26** (14) | 4/26 (8) | 14/26 (16) |
| 24 s2 -> 23 Nov, same handset ip16 | 6/42 (9) | **18/42** (19) | 5/42 (9) | 14/42 (20) |
| 23 Nov -> 24 s1, different handsets (ip16 -> ip18) | 6/27 (10) | 11/27 (14) | 5/27 (8) | 11/27 (14) |
| 23 Nov + 24 s1 -> 24 s2 (two training sessions, ip16 + ip18 -> ip16) | 5/26 (9) | 15/26 (15) | 8/26 (11) | 12/26 (13) |

23-Nov stops have no accelerometer, so no tilt features in the first three rows; in the last row \|B\|+xyz+tilt + floor gives 16/26 (tilt from the 24 s1 part only). Compare: the 17-Nov cross-day test (23 -> 17, 15 places, chance 6.7%) gave 18 to 24% (`cross-day/README.md`); here the same handset and the same stop protocol on both days gives 13/26 and 18/42 with 26 places.

**Walk endpoints** (first/last 2 s of each walk, 1-NN as in `cross-day/tilt.py`, per endpoint; `walk_endpoint_results`):

| split | \|B\| | raw x/y/z | tilt | chance |
|---|---|---|---|---|
| 23 Nov -> 24 s1, ip18 (iPhone19,2) both days | 6/54 | 15/54 | 13/54 | 3.8% |
| 24 s1 -> 23 Nov, ip18 (iPhone19,2) both days | 5/66 | 21/66 | 19/66 | 3.8% |
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

One kNN over every stop window of every phone and session (2425 windows = ip16 816 + ip18 324 + s24 636 + a55 324 + a56 325; 202 recordings, 95 stops, 26 places). Five feature groups with their own distance and weight: \|B\|, magnetic x/y/z, tilt, Wi-Fi (S24, 120 s rows), barometer floor. Weights on the simplex (step 0.25, then step 0.1 near the best) and k in {1, 3, 5, 9, 15, 25} are chosen by inner cross-validation on the training part only, then scored once on the held-out part.

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

`tracking/tracker.py` v2, unchanged, on graph-v2. Train session 1 (fingerprints ip18 = iPhone19,2, line lengths from session-1 walks, floor threshold 0.243 hPa), replay session 2 (ip16 = iPhone17,4). So this run is **cross-handset** (`out/track24_results.json` `handsets`). 26 stops:

| method | exact | area | within one neighbour | top-3 | floor |
|---|---|---|---|---|---|
| tracker | 20/26 [58-89%] | 20/26 | 22/26 | 21/26 | 24/26 |
| snapshot kNN (crossday.py recipe, 2 s windows) | 15/26 | 18/26 | 19/26 | 21/26 | 26/26 |
| emission only (no graph) | 15/26 | 15/26 | 18/26 | 19/26 | 24/26 |
| tracker on arrival (before the stop's data) | 13/26 | 18/26 | 18/26 | 19/26 | 23/26 |

**Same-handset variant** (`same_handset_variant` in the JSON): the fingerprints and the floor threshold (0.342 hPa) come from the 23-Nov stops (ip16, the test handset; one visit per place, a different day), the line lengths still from session-1 walks. Same 26 test stops: tracker 19/26 exact, 21/26 area, 22/26 within one neighbour, 24/26 top-3, floor 25/26; snapshot kNN 13/26, emission only 13/26 (cross-handset run: 20, 15, 15). So the same handset trained a day earlier is not better than a different handset trained the same evening: the day (drift) matters at least as much as the handset here, and the two runs differ in training size and day, so this is not a clean handset comparison.

Optimistic in the same ways as entry 20: the graph and the walk order are the route both sessions walked, and every walk is one recorded line. "Confirmed" frames: 2095 of 3122 stop frames, 1830 of them correct. Replay: `out/replay_24nov_s2.json` (3560 frames, same format as `tracking/out/replay_23nov.json`, graph-v2 nodes). Open it with `phase2/new/circle-ui/index.html?data=../day3/out/replay_24nov_s2.json` over http (e.g. `python -m http.server` in `phase2/new`). The 23-Nov replay and the UI are unchanged.

## Figures (`out/`)

- `out/variance_by_place.csv` / `.json`, `out/variance_cells_by_place.csv`: the variance split per place and feature, and mean +- sd per place x phone x session (section h; python reference of the playground's variance panel, not evaluation results).
- `out/phone_session_matrix.csv` / `.json`: the playground's live "how each phone performs across sessions" panel computed in Python at the default weights and k (not evaluation results; see section g).
- `fig_accuracy_vs_chance.png`: accuracy per feature set vs chance (cross-session iPhone and S24, cross-day same iPhone).
- `fig_leaky_vs_honest.png`: the same fused kNN under the four splits.
- `fig_confusion.png`: confusion matrices, fused kNN leave-one-session-out (windows) and 23 Nov -> 24 s2 (recordings).
- `fig_floor_detection.png`: pressure per stop over time, iPhone vs S24, three sessions.
- `fig_per_place_B_pressure.png`: \|B\| and pressure per place and session (strip plot).
- `fig_knn_neighbour_graph.png`: nearest-neighbour "confusion as a graph" on the graph-v2 layout.
- `fig_embed_*.png`: PCA and t-SNE of the magnetic features, \|B\|+tilt (24 Nov), the fused space (t-SNE on the learned-weight distance) and Wi-Fi (MDS, one dot per stop).
- **`explore.html`**: interactive explorer (plotly from a CDN, pinned with an integrity hash). Views: every embedding above, raw \|B\| vs B_vertical, barometer per stop. Hover shows place, session, handset (display name + model id) and recording; click legend entries to show or hide places. **Phone**, **Session** and **Place** dropdowns (place: all, all floor 5, all floor 4, or one place, plus a tick list for several) and **Colour by place / phone / session** show per-phone, per-session and per-place clusters; with one place selected the colour switches to phone, and colour by session uses the shape for the phone (the playground has the same, plus a "train on same phone only" test and the variance panel of section h).

### g. kNN playground panel: how each phone performs across sessions (live demo, not evaluation results)

`out/knn_playground.html` has a panel with phones as rows and train -> test session pairs plus one leave-one-session-out column; each cell shows recordings (majority vote of the recording's 5 s windows) and windows as correct/total, and chance (1 / places in training). It uses the page's current k and weights live (default = `fused_model.json`: B 0.1, xyz 0.7, tilt 0, baro 0.1, k 25) and the page's recipe (global scaling, true floor), not the per-fold recipe of `evaluate.py` / `fused_knn.py`, so its numbers differ from the tables above. Two modes: same phone only, or all phones of the training session(s) (cells where the training includes other handsets are marked cross-handset). Grey = that phone has no data in the test or training session. `phone_matrix.py` computes the same matrix in Python (`out/phone_session_matrix.csv/.json`); `playground_check.py` checks that the panel equals it in all 70 cells. The page also has an "any session" option in the Try-it session dropdown and a top-level Session dropdown synced with the session checkboxes.

Default settings, same phone only (recordings, windows; chance 3.8%): ip16 23 Nov -> 24 s2 14/26, 158/312; ip16 24 s2 -> 23 Nov 18/42, 220/504; ip16 leave-one-session-out 32/68, 378/816; s24 24 s1 -> 24 s2 8/26, 96/312; s24 24 s2 -> 24 s1 10/27, 125/324; s24 leave-one-session-out 18/53, 221/636; ip18, a55 and a56 have data in 24 s1 only, so there is no same-phone cross-session cell. All other cells and the all-phones mode are in the CSV.

### h. Place filter and "where does the variance come from" (playground; live demo, not evaluation results)

**Place filter** (playground and explorer): a top-level **Place** dropdown next to Phone and Session (all places, all floor 5, all floor 4, or one place) and, in the playground's filters card, a place checklist with all/none buttons; the dropdown and the checklist are two views of one state, like the phone and session controls. In the playground the filter applies to what is drawn and, by default, to the kNN training bank; untick **filter training too** to only hide points and keep the full model (the note under the filters says how many windows train and how many are drawn). With one place selected the colour switches from place to phone (the user can pick session, which uses the shape for the phone), and the axes zoom to the drawn windows.

**Variance panel** (playground): for the windows that pass the filters (session, phone, floor, place; the hold-out of "Try it" is ignored) and for each of |B|, B_x, B_y, B_z, x/y/z pooled, B_vertical, B_horizontal and pressure, the sum of squares around the grand mean is split exactly into five nested pieces (window-weighted, so a long stop weighs more): within recording (window to window), between recordings of the same place+session+phone (repeat visits), between phones, between sessions, between places. Two nestings (selector in the panel): **session first** (place > session > phone within the session, so "between phones" = same session) and **phone first** (place > phone > session within the phone, so "between sessions" = same handset on another day). They share the total and the recording and within-recording pieces and differ only in how the phone-by-session part is split (the design is crossed and unbalanced: ip16 has two sessions, s24 two, ip18/a55/a56 one, 23 Nov has only ip16 stops). Shown as one stacked bar per feature (plus a thin context bar with all places when fewer places are selected) and a table of shares and sd contributions (sqrt(SS/n); the five squares add to the total variance). A per-place table gives mean +- sd of |B| and B_vertical for each phone x session cell and shades the cell furthest from the place's overall mean (per feature). Method and caveats are in the `variance.py` docstring and the panel's "Method" fold-out: plain sums of squares, not unbiased random-effects components; pressure is the handset's per-stop mean (a55/a56 have none), so it has no window noise and it contains weather drift; B_vertical/B_horizontal do not exist on 23 Nov.

Python reference: `variance.py` (called by `playground.py`) writes `out/variance_by_place.csv/.json` (scope = all places, each floor, each place; both nestings; SS, shares, sd per piece) and `out/variance_cells_by_place.csv`. `playground_check.py` checks the page's JS equals the python in 16/16 feature x nesting results (8 features x 2 nestings) at the default settings, at 3 single places (canteen, escalator_down_4F, disabled_toilet), at floor 5 and at a combined phone/session/place filter, plus the per-place cell tables (182/182 cells at the default), and that the page's training and drawn masks equal numpy masks in 40 random place-filter cases.

Headline at the default settings (all 2425 windows, 26 places; `out/variance_by_place.csv`, share of the total variance, session-first nesting; phone-first in brackets where it differs):

| feature | within recording | between recordings | between phones | between sessions | between places |
|---|---|---|---|---|---|
| \|B\| | 0.9% | 2.3% | 51.5% (44.4%) | 31.4% (38.5%) | 13.8% |
| x/y/z pooled | 0.7% | 2.3% | 31.2% (23.9%) | 10.4% (17.8%) | 55.2% |
| B_vertical | 0.5% | 0.8% | 64.5% | 11.5% | 22.7% |
| B_horizontal | 0.8% | 2.0% | 78.0% | 8.3% | 10.9% |
| pressure | 0.0% | 0.0% | 81.7% | 14.9% | 3.4% |

Reading it: window noise is negligible (<= 1%); for |B| the handset and the day explain about 83% of the spread and the place only 14%, which is why |B| alone cannot name a place; the three axes keep 55% in the place (they carry direction), but a third of their spread is still the phone. Places with the largest drift (|B|, sd of the between-session + between-phone pieces in uT, session-first): escalator_down_4F 42.1 (almost all between sessions: the ip16 cell in 24 s2 has a |B| mean of 147.8 uT, see Data issues), escalator_up_4F 39.5 (phones 32.9, sessions 22.0), disabled_toilet 29.9 (phones 28.4), escalator_down 21.1 (phones 18.1) and y5401 20.6 (phones 19.7). For x/y/z pooled: escalator_down_4F 71.0, escalator_up_4F 65.1, disabled_toilet 41.0, escalator_down 37.0, lt1a 31.0.

### i. split20 variant: 20 s pieces, 23-Nov stairs and study rooms excluded, obvious outliers removed (`out-split20/`)

User request (25 Nov): every take becomes three 20 s samples; on 23 Nov the stairs stops are dropped (stairs = lift) and only sr9 is kept of the study rooms ("do s8 10 11"); obvious outliers removed. Run: `sh phase2/new/day3/run_all.sh --split20` (writes `out-split20/`; `out/` is not touched). Control without exclusions and outlier removal: `sh phase2/new/day3/run_all.sh --variant split20_only` (`out-split20_only/`). Settings: `config.json` `variants`; code: `data.py` `apply_variant`.

- **Pieces:** piece j of a take = its 5 s windows 4j..4j+3 = [20j, 20j+20) s from the take's first magnetometer sample. Each piece is one sample (key `<take>#p<j>`, parent in column `take`). The physical stop (`visit`) is unchanged, so grouped CV and leave-one-session-out keep the three pieces of a take (and all phones of a stop) on one side; `fused_knn.py` groups its "by recording" split by take; every split asserts this. Take lengths (`variant_summary.json` `take_span_s`): 23 Nov 59.98-60.0 s, 24 s1 59.98-63.74 s, 24 s2 59.96-61.01 s, so every take gives 3 pieces (one A56 take of 63.74 s has a partial 4th piece, dropped as incomplete). Wi-Fi and the barometer floor stay per stop (a piece uses its stop's Wi-Fi vector and tracked floor).
- **Exclusions** (`exclude_23nov.csv`): 23-Nov BM23 and BM26 ("exit 5 stairs"), BM27 ("exit 5 stairs bawah"), BM05 sr11, BM06 sr10, BM08 sr8 = 18 pieces; lift_stairs keeps BM22 (lift), lift_stairs_4F keeps BM28 (lift), sr9 keeps BM07. 8 walk endpoints at those stops are dropped from the walk-endpoint test. The barometer floor sequence still uses every stop (the stairs stops are where the floor changes).
- **Outliers** (rules and thresholds fixed in `config.json` before any split20 accuracy was computed, from the within-take spread of the pieces, `variant_summary.json` `within_take_spread`: |B| deviation MAD 0.308 uT, 99th percentile 10.58 uT; direction change 99th percentile 16.0 deg): a piece is removed if its |B| median is more than 5 uT from the median of its take's pieces, or its mean field direction is more than 20 deg from the take's median vector. Also checked: missing windows (dropout) 0, flat magnetometer 0. Removed 11 pieces (`out-split20/outliers.csv`): 23 Nov 5 (all 3 pieces of BM14 exit_5, |B| 46.9 / 21.5 / 35.7 uT with a 124 deg turn, so the whole take is gone; 2 pieces of BM11 exit_10, direction 26 and 30 deg), 24 s1 6 (A55: lt2a 2, y5202 2, male_toilet 1; A56: escalator_up 1), 24 s2 0. The >100 uT 4F-escalator readings of 24 s2 are not removed: all pieces of those takes agree and both phones see them, so they are not glitches by this rule.
- **Counts** (`variant_summary.json`): 607 pieces from 202 takes; kept 577 (23 Nov 103, 24 s1 318, 24 s2 156), excluded 18, outlier 11, incomplete 1; 195 takes keep at least one piece, 88 of 95 stops; 2308 windows, 26 places.

Before / after (`out-split20/compare_before_after.csv`, `out-split20_only/compare_before_after.csv`, written by `compare_split20.py`). Correct / samples; a sample is a whole take before and a 20 s piece after (tracker: per stop visit). Chance 3.8% everywhere (1/26; 4.0% mean over the split20 GroupKFold folds).

| test | before (out/) | split20 only (control) | split20 (+ exclusions, outliers) |
|---|---|---|---|
| fused weighted kNN, leave one session out | 74/202 = 36.6% | 193/606 = 31.8% | 222/577 = 38.5% |
| fused weighted kNN, GroupKFold(5) by stop | 58/202 = 28.7% | 182/606 = 30.0% | 187/577 = 32.4% |
| fused, by take (partly leaky: other phones of the stop train) | 112/202 = 55.4% | 361/606 = 59.6% | 330/577 = 57.2% |
| fused, random windows (LEAKY) | 932/935 = 99.7% | 1779/1785 = 99.7% | 1689/1698 = 99.5% |
| same iPhone ip16, 23 Nov -> 24 s2, \|B\|+xyz + floor | 13/26 = 50.0% | 40/78 = 51.3% | 40/78 = 51.3% |
| same iPhone ip16, 24 s2 -> 23 Nov, \|B\|+xyz + floor | 18/42 = 42.9% | 47/126 = 37.3% | 45/103 = 43.7% |
| cross-session iPhone s1 -> s2 (ip18 -> ip16) | 12/26 = 46.2% | 34/78 = 43.6% | 34/78 = 43.6% |
| cross-session iPhone s2 -> s1 (ip16 -> ip18) | 14/27 = 51.9% | 41/81 = 50.6% | 41/81 = 50.6% |
| cross-session S24 s1 -> s2 | 8/26 = 30.8% | 22/78 = 28.2% | 22/78 = 28.2% |
| cross-session S24 s2 -> s1 | 10/27 = 37.0% | 30/81 = 37.0% | 30/81 = 37.0% |
| tracker s1 -> s2 (per stop) | 20/26 | 20/26 | 20/26 |
| tracker, same-handset variant (23 Nov fingerprints) | 19/26 | 19/26 | 20/26 |
| playground recipe, same phone only, ip16 leave one session out | 32/68 = 47.1% | 96/204 = 47.1% | 94/181 = 51.9% |
| playground recipe, same phone only, s24 leave one session out | 18/53 = 34.0% | 55/159 = 34.6% | 56/159 = 35.2% |

Leave-one-session-out per fold (`fused_knn.json`): before 9/42, 42/108, 23/52; split20 only 24/126, 105/324, 64/156; split20 28/103, 128/318, 66/156 (test 23 Nov, 24 s1, 24 s2). Deployable weights (`fused_model.json`): before and split20 only B 0.1, xyz 0.7, tilt 0, Wi-Fi 0.1, baro 0.1, k 25; split20 B 0.1, xyz 0.5, Wi-Fi 0.2, baro 0.2, k 25 (inner accuracy 0.478); the playground default uses these, so its matrix changes with the weights as well as the data.

Reading it:
- Splitting alone changes little per sample: the named splits stay within 3 points of the take-level number except 24 s2 -> 23 Nov (42.9% -> 37.3%), and leave-one-session-out drops from 36.6% to 31.8% while GroupKFold rises from 28.7% to 30.0%. Three pieces of a take are not three independent samples (they share the stop, the phone and the day), so the larger n narrows the interval only on paper; the intervals in the JSON assume independence.
- The gain of the full split20 over the control comes from removing data, and partly from removing hard test pieces. Same test pieces check (`out-split20/compare_same_pieces.json`): 24 s2 -> 23 Nov, the control scores 45/103 on exactly the pieces split20 keeps, the same as split20 (45/103); its 47/126 includes the 23 excluded or removed 23-Nov pieces, of which it got 2 right. Where no test piece was removed (23 Nov -> 24 s2 and all 24-Nov cross-session splits) split20 and the control are identical.
- Leaky stays leaky: random windows 99.5%, and a same-take time split (`LEAKY_same_recording_time_split_24s2_iphone`, \|B\|+xyz) 72/78.
- Upload pipeline (`../upload/walksense.py` unchanged, scored on 20 s pieces by `upload_eval_split20.py`, `out-split20/upload_eval_split20.json`): raw x/y/z top-1 iPhone s1 -> s2 51/78 (65%; take level in `../upload/out/eval.json`: 17/26 = 65%), s2 -> s1 51/81 (63%; 17/27 = 63%); S24 34/78 and 28/81 (11/26 and 10/27); chance 7.7% (true floor given). No 24-Nov iPhone or S24 piece was removed, so the control gives the same numbers.

### j. 25 Nov added as a fourth session (`config.json` session `25nov`; PROCESS-LOG entries 41 to 45)

25 Nov is a partial WhatsApp export (`../../clean-data/2026-11-25-spots/README.md`): the floor-5 round by ip18 and a56 (9 stops) and spot recordings by ip16 and s24 (2 stops on floor 5, 2 on floor 4); 23 stop takes, 66 kept 20 s pieces (3 removed as outliers, all ip16 at the 4F escalators: `out-split20/outliers.csv`). Before = the entry-40 state, rerun with the track-aware code (identical numbers, entry 43); after = the same code with `25nov` in `config.json`. Chance 3.8% (26 places).

| test (learned-weight fused kNN) | default before | default after | split20 before | split20 after |
|---|---|---|---|---|
| leave one session out | 74/202 = 36.6% | 91/225 = 40.4% | 222/577 = 38.5% | 248/643 = 38.6% |
| GroupKFold(5) by stop | 58/202 = 28.7% | 81/225 = 36.0% | 187/577 = 32.4% | 239/643 = 37.2% |
| by take (partly leaky) | 112/202 = 55.4% | 123/225 = 54.7% | 330/577 = 57.2% | 373/643 = 58.0% |
| random windows (LEAKY) | 932/935 | 1040/1047 | 1689/1698 | 1852/1868 |

Leave one session out per held-out session (`fused_knn.json`): default 23 Nov 9/42 -> 16/42, 24 s1 42/108 -> 45/108, 24 s2 23/52 -> 20/52, 25 Nov 10/23 (new); split20 28/103 -> 42/103, 128/318 -> 119/318, 66/156 -> 55/156, 32/66 (new). Deployable model (`fused_model.json`) after: default B 0, xyz 0.25, tilt 0.5, Wi-Fi 0, baro 0.25, k 25 (inner 0.436); split20 B 0.1, xyz 0.4, tilt 0.1, Wi-Fi 0, baro 0.4, k 9 (inner 0.47).

Per phone, leave one session out (`out/phone_place_performance.xlsx`, `out/perf_csv/*_phone_summary.csv`; accuracy, macro precision): split20 after ip18 0.583 / 0.466, ip16 0.416 / 0.308, a56 0.386 / 0.345, s24 0.298 / 0.312, a55 0.224 / 0.154 (before: ip18 0.506, ip16 0.381, a56 0.450, s24 0.358, a55 0.250 accuracy). Default after: ip18 0.667, ip16 0.444, a56 0.412, s24 0.286, a55 0.185.

Leave 25 Nov out (`results.json` `leave25nov_out_*`, kNN k=5, \|B\|+xyz + baro floor; train on 23/24 Nov, all phones or the same handset only), per take (default) and per piece (split20): ip18 8/9 and 7/9 (24/27 and 21/27); a56 1/7 and 2/7 (3/21 and 6/21); ip16 1/4 and 1/4 (2/9 and 0/9); s24 0/3 and 0/3 (0/9 and 0/9). Barometer floor on 25 Nov per track (step tracking): iPhone round 9/9, iPhone spots 4/4, S24 spots 3/4.

Update 26 Nov (PROCESS-LOG entry 69, the 11 S24 spot takes now labelled from the user's file names): leave 25 Nov out, |B|+xyz + baro floor, s24 (11 takes, 33 pieces): all phones 3/11 and 6/33, same handset only 2/11 and 6/33 (the 0/3 and 0/9 above were for 3 takes). Leave one session out, fused kNN: default 122/295 = 41.4% (was 123/287), split20 375/842 = 44.5% (was 385/818); s24 25-Nov takes 1/11 (default) and 8/33 (split20).

Places never correct before (entry 41), leave one session out, correct / samples (`out/perf_csv/hard_places_before_25nov_rerun.csv` -> `hard_places_after_25nov.csv`):

| place | 25-Nov takes | default before -> after | split20 before -> after |
|---|---|---|---|
| escalator_down_4F | 2 (ip16, s24) | 0/8 -> 1/10 | 3/24 -> 3/28 |
| escalator_up_4F | 2 (ip16, s24) | 0/8 -> 3/10 | 5/24 -> 8/29 |
| female_toilet | 2 (ip18, a56) | 0/7 -> 5/9 | 0/21 -> 14/27 |
| lift_stairs | 0 | 0/9 -> 0/9 | 0/21 -> 0/21 |
| y5302_back | 0 | 0/7 -> 0/7 | 0/21 -> 0/21 |

Places with zero correct after (leave one session out, per sample): default lift_stairs, y5302_back, y5401; split20 disabled_toilet, escalator_down, lift_stairs, y5302_back, y5401 (before: y5401 4/7 and 5/21, disabled_toilet 3/7 and 6/21, escalator_down 2/8 and 6/24). The playgrounds before the rerun are kept as `out*/knn_playground_2026-11-25a.html` and the per-sample predictions as `out*/fused_sample_predictions_2026-11-25a.csv`.

### l. The complete 25 Nov (Dicta's set as session `25nov`, our spot stops as `25spots`; PROCESS-LOG entries 49, 50)

`25nov` is now Dicta's complete pass (`../../clean-data/2026-11-25/`, 26 stops x ip18 + a55 + a56); `25spots` is our partial
export minus the 36 recordings that are byte-identical to hers (`../../clean-data/2026-11-25-spots/duplicates_vs_2026-11-25.csv`),
i.e. 7 spot takes of ip16 and s24. The old session set is `config_2026-11-25_partial25nov.json`
(`DAY3_CONFIG=config_2026-11-25_partial25nov.json sh run_all.sh` reproduces entries 44 to 47).

| leave one session out, learned-weight fused kNN | before (entries 44/45) | after |
|---|---|---|
| default (takes) | 91/225 = 40.4% | 123/287 = 42.9% |
| split20 (20 s pieces) | 248/643 = 38.6% | 385/818 = 47.1% |

Leave 25 Nov out (train 23/24 Nov, kNN k=5, |B|+xyz + baro floor, all phones; default / split20): ip18 17/26 / 57/78, a56 10/26 / 31/75,
a55 8/26 / 22/70, ip16 1/4 / 2/9, s24 0/3 / 0/9. No place has zero correct any more (leave one session out); weakest: lift_stairs
(precision 0.143), y5302_back, y5401, disabled_toilet. Phone ranking (default accuracy, macro precision): ip18 0.698, 0.667;
ip16 0.500, 0.474; a56 0.453, 0.409; s24 0.250, 0.250; a55 0.226, 0.173. All numbers: PROCESS-LOG entry 50.

### m. The 25-Nov night run (sessions `25night` and `25night_tian`; PROCESS-LOG entry 72)

`25night` = Dicta's ip18 + Chris's a56, who walked in step (`../../clean-data/2026-11-25-night/round/clean`, 32 stops each,
8 of them extra takes at weak places 00:15 to 00:40); `25night_tian` = Tian's ip16, who walked on his own
(`.../tian/clean`, 23 stops). Both use `names_25night.csv` (Dicta's 25-Nov name map). Six spot takes at 20:22 to 20:27 went
to `25spots`. `run_all.sh` rebuilds the night trees first (`build_night.py`).

| leave one session out, learned-weight fused kNN | before (entry 69) | after |
|---|---|---|
| default (takes) | 122/295 = 41.4% | 169/386 = 43.8% |
| split20 (20 s pieces) | 375/842 = 44.5% | 501/1108 = 45.2% |

Per phone (default): ip18 60.4% -> 70.6%, ip16 48.6% -> 49.5%, a56 49.1% -> 34.1%, s24 23.4% -> 27.3%, a55 26.4% -> 26.4%.
**Chris's a56 magnetometer was offset on the night run** (median |B| 110.9 uT against 40 to 45 uT on the other days,
`../../clean-data/2026-11-25-night/field_check.csv`), so its 32 night takes score 2/32 and pull a56 down everywhere they are
in the training set. They are kept; excluding them is a team decision (for example an `exclude_sources` CSV that lists them).
All numbers: PROCESS-LOG entry 72.

### n. Tian's 26-Nov morning pass (session `26tian`; PROCESS-LOG entry 73)

`26tian` = Tian's ip16 (iPhone17,4) alone, 09:30 to 10:39, 25 stops + 27 walks (`../../clean-data/2026-11-26-tian/clean`,
labels from his chat captions in `labels_tian26.csv`; names `names_25night.csv`). `run_all.sh` builds it first
(`build_tian26.py`). ip16 now has three sessions with stops of its own handset besides 23 Nov (24s2, 25night_tian, 26tian).

| leave one session out, learned-weight fused kNN | before (entry 72) | after |
|---|---|---|
| default (takes) | 169/386 = 43.8% | 178/411 = 43.3% |
| split20 (20 s pieces) | 501/1108 = 45.2% | 553/1183 = 46.7% |

ip16 (default): 48/97 (49.5%) -> 61/122 (50.0%); the `26tian` fold is 12/25 (default) and 37/75 (split20). The other phones
have no new data; their small changes come from the per-fold weights, which are relearned with `26tian` in every training set.
All numbers: PROCESS-LOG entry 73.

### o. a56 night offset: keep, exclude or recalibrate (offline comparison; PROCESS-LOG entry 76)

Offline analysis only: `config.json`, `out/` and `out-split20/` are unchanged. `sh phase2/new/day3/a56_offset.sh` (about 2 h with
12 runs in parallel, one core each) writes `out-a56/`: one folder per option and variant (the same `evaluate.py` + `fused_knn.py`),
`comparison.csv/.json`, `a56_night_per_place*.csv`, the offset fits and the night time series.

- **A** keep; **B** exclude the a56 night takes (`exclude_sources` in a derived config, `out-a56/config_B.json`);
- **C** hard-iron correction for every phone and session: offset = centre of a robust circle fitted to the take-mean x/y of all
  stop takes of that phone in that session (no labels; guards fixed before any accuracy: >= 10 takes, radius 20 to 60 uT, no
  angular gap over 180 deg, else no correction; z not corrected because every take was recorded flat, `flat_check.csv`);
  **C1** = C on the a56 night takes only; **C2** / **C21** = the same with a circle fitted to the takes within 30 min of each take.
- The correction is subtracted from the raw samples before the 5 s windows, so it changes x/y/z, |B| and tilt; Wi-Fi and the
  barometer are untouched.

Learned-weight fused kNN, leave one session out (`out-a56/comparison.csv`; "without a56 night" = the same test samples in every option):

| option | default | without a56 night | a56 | a56 night | split20 | without a56 night | a56 | a56 night |
|---|---|---|---|---|---|---|---|---|
| A | 179/411 (43.6%) | 177/379 | 30/85 | 2/32 | 553/1183 (46.7%) | 541/1092 | 94/246 | 12/91 |
| B | 190/379 (50.1%) | 190/379 | 30/53 | excluded | 526/1092 (48.2%) | 526/1092 | 85/155 | excluded |
| C | 197/411 (47.9%) | 183/379 | 43/85 | 14/32 | 573/1180 (48.6%) | 531/1089 | 125/246 | 42/91 |
| C1 | 194/411 (47.2%) | 183/379 | 42/85 | 11/32 | 614/1183 (51.9%) | 583/1092 | 114/246 | 31/91 |
| C2 | 178/411 (43.3%) | 166/379 | 44/85 | 12/32 | 524/1181 (44.4%) | 486/1090 | 128/246 | 38/91 |
| C21 | 201/411 (48.9%) | 185/379 | 46/85 | 16/32 | 599/1183 (50.6%) | 556/1092 | 137/246 | 43/91 |

A with one BLAS thread per run gives 179/411 where the official run has 178/411 (split20 553/1183 = official); __AMT__
The a56 night offset is not constant (`night_drift.json`, `fig_a56_night_offset.png`): against the first 25-Nov run the median
take offset is -29.8 / -107.4 / 1.6 uT (x/y/z) before 22:59 and -41.6 / -68.8 / -4.4 uT from 23:00. At 22:59 (y5302_back) both
phones saw a strong field (ip18 take |B| 284.3 uT) and within that walk + stop the a56 y field went from about -115 to +78 uT (`night_trace_1s.csv`); after it the offset sits in a second regime. So it is not one constant magnet stuck to the phone.

## Data issues found

- Very strong fields (place median \|B\| above 100 uT, `results.json` `magnetic_check`): 24 s2 iPhone at escalator_down_4F 147.9 and escalator_up_4F 142.5 uT, 24 s2 S24 at escalator_down_4F 127.7, 24 s1 S24 at disabled_toilet 121.6 and escalator_down 101.3. The iPhone on 23 Nov ranges 32.9 to 58.9 uT. Both phones see the 4F down-escalator in session 2, so it is more likely something physical there that night (running escalator machinery?) than one sensor. Worth asking the collector; see `fig_per_place_B_pressure.png`.
- `sesi2/clean/ROUTE.md` says "Sensors-only (no Wi-Fi logged)", but the same session has a WiGLE log (`sesi2/clean/README.md`, `summary.json`).
- Session 2 has walks out of route order (floor 5: exit10 -> canteen, then the escalator-up stop, then three walks esca_up -> canteen, canteen -> esca_down, esca_up -> esca_down; floor 4: the walk gate -> exit 5 was recorded before the gate stop). The tracker attaches each walk to the last stop before it.
- Session 1 has S24 Wi-Fi rows at only 14 of 27 stops; two S24 logs are empty (`sesi1/clean/summary.json`).
- 25 Nov (`../../clean-data/2026-11-25-spots/`): 73 media messages are missing from the WhatsApp export (the rest of the 5F round from 18:13, the whole 4F round, Tian's ranking xlsx); all 11 of Michael's S24 spot files are labelled from his own file names (user-confirmed 2026-11-26, high confidence; PROCESS-LOG entry 69). The 4F escalator pieces of ip16 on 25 Nov disagree within the take (\|B\| 6.6 to 32.3 uT from the take median), so the outlier rule removed 3 of its 6 pieces there.

### k. Playground: top-bar checkboxes and the "Compare phones side by side" panel (live demo, not evaluation results; PROCESS-LOG entry 46)

The Phone, Session and Place dropdowns of the top bar are now multi-select checkbox groups with an all / none toggle each; places are grouped by floor (5F, 4F) inside a pop-up with a toggle per floor. They are views of the same state as the checklists in the filters card (one source of truth: `st.phoneOn`, `st.sessOn`, `st.placeOn`). The Try-it selectors (Session / Place / Phone) only pick one recording to load and stay selects.

The panel at the bottom has one column per ticked phone, all with the current k and weights, the ticked sessions and places, and a hold-out rule (leave one session out = default, or leave one stop out) and a training mode (train on all phones and test on this phone = default, or train and test on the same phone only). Rows: test recordings (windows), accuracy (recording majority vote), window accuracy, macro precision / recall / F1 (on recording votes, mean over the places the phone has test recordings of, a never-predicted place counts precision 0 like `perf_sheet.py`), top-3 rate (true place among the 3 largest summed vote shares of the recording), chance (1 / ticked places), then recordings correct / n per place with the best phone per row shaded; a bar chart of accuracy and macro precision per phone. The computation is `comparePhones()` in the checked core block; `compare_phones.py` is the numpy + sklearn reference and `playground_check.py` compares them (default settings, random subsets, leave one stop out). Defaults at the current k and weights are in `out/phone_compare_default.csv/.json` and `out-split20/...`. Not applied here: the floor filter and the Try-it hold-out.


## Display names of the two disabled toilets (2026-11-26)

User: the 5F `disabled_toilet` is the **male disabled toilet**, the 4F `disabled_toilet_4F` is a **mixed (unisex) disabled toilet**. The place ids are unchanged; `config.json` `place_display` gives the shown names ("Male disabled toilet (5F)", "Mixed disabled toilet (4F)"), used by the interactive pages, the figures, `perf_sheet.py` and `gaps_sheet.py` (`data.relabel_sheet`), and the routing graph / `request-matching/destinations.csv` names.
