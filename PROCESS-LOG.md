# Process log: GE2340 Group 21 (WalkSense)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

One entry per step, oldest first, newest at the bottom. Failures are logged on purpose: they are part of the story and part of what we learned. Every number below comes from a file in this repo (named in the entry) or from a git commit message. If a number is not in a file, it is not here. New work must add an entry in this same format (see `CLAUDE.md`).

Entry format: **What we tried / Why / How / Result / Outcome / What changed because of it / Links.**

Repo facts used throughout: remote `github.com/michaelbasarah/ge2340-group21-walksense`; branches `main` (pushed), `analysis/cross-day` (local, fully merged into `main`), and three unmerged local review branches `prep/training`, `prep/map`, `prep/ready` (not pushed, described in the 16 Nov entry). Commit dates are from `git log`.

Contents:
1. 14 Nov: first acquisition and cleaning (v1 to v4)
2. 15 Nov: workspace set-up and recording/labelling workflow
3. 16 Nov: label-gated training pipeline and map-replay preparation (unmerged branches)
4. 17 Nov: second session (trial session, 26 stops at 30 s) and its cleaning
5. 17 to 23 Nov: Dicta's positioning pilot gave 94%, which turned out to be leakage
6. 22 to 23 Nov: floor-5 map, prototype and request matching
7. 23 Nov: two-floor session (42 stops, gyroscope, about 60 s) and Dicta's clean.py with provisional labels
8. 24 Nov: first cross-day run
9. 24 Nov: relabel from the collector's route
10. 24 Nov: revisit 4/6 became 7/9, cross-day 24% became 18 to 24%
11. 24 Nov: FAILURE, a fixed barometer threshold does not work (weather drift)
12. 24 Nov: FAILURE, WiGLE CSV Wi-Fi is near useless
13. 24 Nov: FAILURE, stops cannot be tilt-corrected (no accelerometer logged)
14. 24 Nov: FAILURE, the two iPhones' magnetometers disagree (r = 0.20)
15. 24 Nov: tilt correction on walk endpoints, 39% vs 0%
16. 24 Nov: team summary written and pushed to main
17. 24 Nov: old/new reorganisation, day-3 checklist, this log
18. 24 Nov: area definitions pre-registered (circles-on-lines graph nodes)
19. 24 Nov: graph edges and step counting (PDR) on the walks
20. 24 Nov: route-aware tracker (HMM on the graph): helps across days, not on 23-Nov LOVO; v1 FAILED to recover
21. 24 Nov: circle navigator UI prototype (circles on lines)
22. 24 Nov: graph-v2, merged study rooms and lift/stairs (non-destructive)
23. 24 Nov: two-session clean dataset published (sesi1 4-phone + Wi-Fi, sesi2 2-phone)
24. 25 Nov: cross-day rerun on graph-v2 merged places (v1 kept)
25. 25 Nov: 24-Nov evaluation without leakage: cross-session, cross-day, walk endpoints, barometer floor
26. 25 Nov: FAILURE, Wi-Fi is still not a fingerprint on 24 Nov (WiGLE still logs new-or-stronger only)
27. 25 Nov: weighted fused kNN on all stop data, leaky vs grouped vs leave-one-session-out
28. 25 Nov: route-aware tracker on 24 Nov (train session 1, replay session 2) and a replay for the circle UI
29. 25 Nov: figures, an interactive data explorer, the day3 README and one-command rerun
30. 25 Nov: interactive kNN playground (slide features, see the neighbours and the predicted place)
31. 25 Nov: per-phone filtering and colouring in the playground and the explorer
32. 25 Nov: the phone is the real handset (ip16 / ip18), all-sessions option, phone x session panel
- Lessons learned
- Open questions / next steps

---

## 1. 14 Nov: first acquisition and cleaning (v1 to v4)

- **What we tried:** the very first recording session: 26 stationary recordings (barometer + magnetometer), 23 walking recordings (accelerometer) and one Wi-Fi log, taken from the team WhatsApp export. Cleaned into readable CSVs with provenance.
- **Why:** to check what the sensors give before collecting more.
- **How:** `phase2/clean-data/2026-11-14/clean.py` (cleaning), `feature_extraction.py` (first-pass descriptive statistics), `make_relabel_template.py`, `package.py`. Rules: keep readings inside the recorded interval, quarantine bad rows with their full values, no smoothing. Steps are listed in `phase2/clean-data/2026-11-14/PROCESSING_LOG.md`.
- **Result:** 46,171 original readings = 46,124 accepted + 47 quarantined (negative experiment time). Accepted: 208 pressure, 25,981 magnetic, 19,935 acceleration. Wi-Fi: 6,196 WIFI rows + 15 LTE rows; 664 candidate stop associations across 22 stops. 26 stop files vs only 25 numbered descriptions in the collector's list.
- **Outcome:** partly succeeded. The data are clean and traceable, but the location labels were unreliable: the README says the user judged the old location list unreliable and would supply fresh labels, so every old name is "untrusted". The reason for 26 vs 25 was never found; no recording was deleted. A 664-sample copy of one walk (`SYN_ACC_5F_CONNECTOR`) was added at the user's request, marked synthetic, and is not an independent observation.
- **What changed because of it:** a blank relabel template with all 49 rows (`RELABEL_TEMPLATE.csv`) so labels could be confirmed one file at a time, instead of trusting old names.
- **Links:** `phase2/clean-data/2026-11-14/README.md`, `.../PROCESSING_LOG.md`, `.../RELABEL_README.md`. First committed in `a6dbd12` (15 Nov).

## 2. 15 Nov: workspace set-up and recording/labelling workflow

- **What we tried:** turn the pile of files into one shared team repository where teammates can label the 49 recordings without overwriting each other.
- **Why:** the 14-Nov labels were unreliable (entry 1) and several people had to fix them.
- **How:** commit `a6dbd12` ("Prepare private GE2340 team workspace and recording labeling workflow"): `labeling/README.md` (8-step workflow: claim IDs in `labeling/assignments.csv`, copy the template to `labeling/submissions/<alias>.csv`, fill names and floors, run `python3 scripts/validate_labels.py`, return by branch or pull request), `labeling/assignments.csv` (50 lines), `scripts/validate_team.py` and `scripts/validate_labels.py`, `docs/GITHUB_HANDOFF.md`, `SOURCE_MANIFEST.json` (file hashes), the course templates and the Phase 1 sources. Commit `c00dc0d` documented the portable upload and recorded file hashes. Commit `499247d` recorded that the owner chose a public repository.
- **Result:** the repo and workflow exist. `labeling/submissions/` contains only `.gitkeep`: no label submissions have been returned through this workflow.
- **Outcome:** set-up succeeded, but the labelling route was not used for the later sessions. From 17 Nov the labels came from route-named files and from the collector's own route list (entries 4, 7, 9).
- **What changed because of it:** later sessions used file names that carry the route (e.g. `From canteen ...zip`), which is what made the 24-Nov relabel possible.
- **Links:** `README.md`, `labeling/README.md`, `docs/GITHUB_HANDOFF.md`, commits `a6dbd12`, `c00dc0d`, `499247d`.

## 3. 16 Nov: label-gated training pipeline and map-replay preparation (unmerged branches)

- **What we tried:** prepare the training and map code before any confirmed labels existed, so work could start the moment labels arrived.
- **Why:** labels were pending (entries 1 and 2).
- **How:** three local review branches, never merged into `main` and not pushed:
  - `prep/training` (`3c7942e`, `8a51469`): `phase2/training/pipeline.py` (a "label-gated" pipeline: it refuses to train until labels, stop-to-map bindings and a map catalogue are present), `tests/test_pipeline.py`, templates, `README.md`. Default extraction on the 14-Nov data gives 244 two-second windows (133 stationary, 111 movement). `examples/current-readiness.json` records: 49 source recordings, 0 confirmed stops, `training_ready: false`, `model_trained: false`.
  - `prep/map` (`c56cf4c`, `acf6936`): extra map-editor and replay code in `phase2/map-ui/` (`map-tools.mjs`, `preparation-ui.mjs`, an editable map, recorded-position replay). `phase2/map-ui/BUILD_LOG.md` on that branch records 188 DOM checks passing and that a real-browser (Chromium) test failed to start in the sandbox, so real rendering was not verified.
  - `prep/ready` (`db836ec` on top of `cc2bc2d`, `40301a1`, `a0cf1b7`): `docs/PRE_LABEL_HANDOFF.md`, `scripts/check_ready.py`, `scripts/check_contract.py`, adding a combined readiness check (`check_ready.py` runs the source/feature checks, preparation tests and map routing checks) and a handoff document. Its handoff notes that scikit-learn-backed fitting was not executed there (PyPI DNS was unavailable).
- **Result:** nothing was trained on these branches. The pipeline stays blocked by design until labels arrive.
- **Outcome:** partly useful, mostly not used. The pipeline targets the 14-Nov data format and the label-gated flow; the later sessions have a different layout, so it was not run on them.
- **What was reused later:** only the model set-up. `crossday.py` reuses the same classifier recipe (median impute + standard scaling, distance-weighted kNN, 200-tree balanced random forest with seed 21) and the per-recording majority vote, adapted from `phase2/training/pipeline.py` (`prep/training` 8a51469); see "Reused code" in `phase2/new/cross-day/README.md`. The map branch's work was not needed for the positioning results; `main` has the earlier map app in `phase2/map-ui/`.
- **Links:** `git show prep/training:phase2/training/README.md`, `git show prep/ready:docs/PRE_LABEL_HANDOFF.md`, `git show prep/map:phase2/map-ui/BUILD_LOG.md`. The branches were deliberately left unmerged and unpushed.

## 4. 17 Nov: second session (trial session, 26 stops at 30 s) and its cleaning

- **What we tried:** a second data collection, this time with walk files already named by route (e.g. `Sr11 10`), to get a labelled loop on floors 5 and 4.
- **Why:** the first session's labels were unreliable (entry 1); we also wanted barometer/Wi-Fi/magnetometer data to test the positioning idea.
- **How:** `phase2/clean-data/2026-11-17/clean.py`; stops of about 30 s (the pilot README and `crossday` README state 30 s). Stops on one iPhone (iPhone17,4), walks on another (iPhone19,2), Wi-Fi on a Samsung (SM-A556E) with WiGLE.
- **Result** (`summary.json`, `README.md`): 26 stops (BM01 to BM26) and 23 walks. 104,504 readings = 101,436 accepted + 3,068 quarantined. One stop (`poin 21-37-27`) was a double export of another: 3,025 rows quarantined as a duplicate. Wi-Fi: 3,085 observations, 961 associated to stops, covering only 15 of 26 stops. 12 stops (BM08, BM14 to BM19, BM21, BM22, BM24 to BM26) had no Wi-Fi rows.
- **Outcome:** data succeeded, Wi-Fi mostly failed. The session README says an empty window is not proof the phone saw nothing. The pilot README names the cause: Android Wi-Fi scan throttling (fix: Developer options, Wi-Fi scan throttling OFF). Labels were only route-inferred: 20 of 26 confirmed on both sides, the rest less certain.
- **What changed because of it:** the next session used longer stops (about 60 s) and added the gyroscope (entry 7).
- **Links:** `phase2/clean-data/2026-11-17/README.md`, `.../PROCESSING_LOG.md`, `.../summary.json`.

## 5. 17 to 23 Nov: Dicta's positioning pilot gave 94%, which turned out to be leakage

- **What we tried:** a quick check on the 17-Nov data of whether the magnetometer can identify a stop, whether the barometer separates floors, and whether steps can be detected. The pilot was written by teammate Dicta ("vibe-coded", allowed by the course). It is committed in `f975725` on 23 Nov; the exact date it was run is not recorded.
- **Why:** to see if the positioning idea is worth pursuing before more collection.
- **How:** `phase2/old/positioning-pilot/pilot_train.py`: 26 stops cut into 2 s slices (390 slices, 234 train, 156 test), kNN and random forest on magnetometer statistics; `step_detection.py` for steps. (The folder was `phase2/positioning-pilot/` until entry 17.)
- **Result** (`old/positioning-pilot/out/results.json`): stop accuracy kNN 94.2%, random forest 92.3%, nearest centroid 89.1%; barometer floor accuracy 97.4%; silhouette over 26 stops 0.439 (two floors 0.131). Step detector: 353 steps total, median cadence 1.57 steps/s (reproduced on 24 Nov).
- **Outcome:** misleading. Train and test slices came from the same recording: neighbouring 2 s slices of one visit are almost identical, so ~94% is an optimistic upper bound, not a result. The pilot README says exactly this ("IMPORTANT, read before quoting any number") and that a different day is needed as test set. The silhouette and the clean two-floor barometer split were the only leakage-free signals.
- **What changed because of it:** we needed a leakage-reduced evaluation (entries 8 to 10). The pilot was marked superseded on 24 Nov and moved to `phase2/old/`.
- **Links:** `phase2/old/positioning-pilot/README.md`, `.../out/results.json`.

## 6. 22 to 23 Nov: floor-5 map, prototype and request matching

- **What we tried:** the non-positioning parts of the app: floor-5 map coordinates, a demo web app, and text-to-place matching.
- **Why:** project objectives #4, #9, #10, #11 in `phase2/README.md`.
- **How:** Google Maps pins for floor 5 (`phase2/GMaps/`, screenshots dated 22 Nov) converted to metres by `phase2/map/build_map.py`; an editable corridor graph `phase2/map/edges_floor5.csv` with A* routing; `phase2/prototype/` (demo web app); `phase2/request-matching/match.py` (keyword + embedding). Committed in `f975725` (23 Nov), refreshed in `86cbb44`.
- **Result** (`phase2/README.md`): distances match tape measurements; the map shows only the 12 checkpoints as blocks, not true room footprints; request matching fixed "emergency" and "leave the building" meanings.
- **Outcome:** partly done. Floor 5 only; there are no floor-4 coordinates, so routing cannot span both floors yet. The prototype is a proof of the pieces, not the final UI.
- **What changed because of it:** floor-4 Google Maps pins went onto the day-3 checklist.
- **Links:** `phase2/README.md`, `phase2/map/`, `phase2/prototype/`, `phase2/request-matching/`.

## 7. 23 Nov: two-floor session (42 stops, gyroscope, about 60 s) and Dicta's clean.py with provisional labels

- **What we tried:** a bigger session covering both floors, with the fixes from entry 4: longer stops (about 60 s), the gyroscope on walks, Wi-Fi from two WiGLE logs.
- **Why:** more stops, both floors, and heading data.
- **How:** collection, then `phase2/clean-data/2026-11-23/clean.py` (written by Dicta). It names each stop after the origin of the next walk file ("From X" means stop X); floors are split from barometer medians. The cleaned CSVs are large, so the big ones are gitignored and regenerated with `clean.py`. Commit `86cbb44` (23 Nov) adds the data, `field-sheet.html` and the first collect list `WHATS-LEFT-TO-COLLECT.md`.
- **Result** (`summary.json`, `README.md`): 42 unique stops (26 on floor 5, 16 on floor 4), 37 walks. 382,278 readings = 364,067 accepted (288,441 magnetometer, 2,312 barometer, 36,662 accelerometer, 36,652 gyroscope) + 18,211 quarantined. Pause/resume produced duplicate recordings: 3 duplicate intervals quarantined (12,101 + 6,050 duplicate rows plus 60 negative-time rows). Wi-Fi: 2 logs, 6,522 accepted observations, 3,112 unique BSSIDs, 41 of 42 stops with Wi-Fi rows.
- **Outcome:** data succeeded. Two problems appeared only later: (a) the labelling rule "stop = origin of next walk" gives a stop with no walk after it a copy of the next stop's label (entry 9); (b) "41/42 stops with Wi-Fi" only counted rows, not repeated scans (entry 12). `missing_movements.csv` lists 5 consecutive-stop pairs with no walk recorded.
- **What changed because of it:** the "Stop, then start a NEW recording at each stop (no pause/resume)" rule, and the need to confirm labels against the collector's route.
- **Links:** `phase2/clean-data/2026-11-23/README.md`, `.../summary.json`, `.../duplicate_recordings.csv`, `.../missing_movements.csv`, commit `86cbb44`.

## 8. 24 Nov: first cross-day run

- **What we tried:** an honest accuracy number: train on one set of visits, test on different visits, instead of one recording split in two. Three tests: (1) main: 23-Nov revisits (a place visited twice, train on the earlier visit, test on the later); (2) secondary: true cross-day (train 23 Nov, test 17 Nov) for places both days share; (3) baseline (leaky): same-visit time split, kept only for comparison.
- **Why:** the pilot's 94% was leakage (entry 5).
- **How:** `crossday.py` (commit `d7cc053`, 24 Nov 02:13 HK). The 23-Nov labels came from Dicta's provisional list in `labels_23nov_confirmed.csv` (all `confirmed=no`); the 17-Nov stops were mapped to 23-Nov place names with `crosswalk_17nov_to_23nov.csv`. Features: 2 s magnetometer windows (field strength |B|, optionally x/y/z) and 10 s Wi-Fi chunks; kNN (k=5) and random forest (200 trees, seed 21); barometer picks the floor first in the "baro floor +" variants. Stops with no walk after them (BM14, BM17, BM19, BM40) and BM42 (no label) were left out until confirmed.
- **Result** (first README at `d7cc053`): 37 usable 23-Nov stops; revisit test 6 places, best 67% (4/6; |B|+xyz with barometer floor), chance 3.2%; cross-day core (15 places, 17 test visits, chance 6.7%) 24%; Wi-Fi cross-day 33% (n = 9).
- **Outcome:** worked as a tool, but the inputs were weak: 5 stops excluded, labels unconfirmed, and tiny n (6 test visits).
- **What changed because of it:** ask the collector for the real route to firm up the labels (entry 9).
- **Links:** commit `d7cc053`; current script `phase2/new/cross-day/crossday.py`.

## 9. 24 Nov: relabel from the collector's route

- **What we tried:** replace the provisional 23-Nov labels with labels built from the collector's own route list.
- **Why:** the label rule in entry 7 breaks for stops with no walk after them.
- **How:** the route (one walk per line, 37 lines) was lined up with the 37 walk files and the stop timestamps. One English ID per physical spot, `_4F` for floor-4 namesakes. Commits `b4243c1` (24 Nov 02:31 HK; 41/42 confirmed) and `7ece689` (02:37; BM14 confirmed by the collector, 42/42). New output `out/label_changes_vs_provisional.csv`.
- **Result** (`label_changes_vs_provisional.csv`): 6 of 42 labels changed, none of the floors:
  - BM14: exit lift 10 to `exit_5` (collector confirmed; step 13 ends at exit 5, they walked on to exit 10 without recording it)
  - BM17: esca naik atas to `escalator_down`
  - BM19: exit lift 5 to `canteen`
  - BM25: y5302 to `y5302_back` (the back door, a different spot from BM04)
  - BM40: esca turun bawah to `exit_5_4F`
  - BM42: no label to `escalator_up_4F`
  - Floors: all 42 agree with the barometer. 4 walks were never recorded by the collector: exit 5 to exit 10 (BM14 to BM15), escalator down to up (BM17 to BM18), canteen to exit 5 (BM19 to BM20, after a 32-minute break) and exit 5 (4F) to escalator down (4F) (BM40 to BM41).
- **Outcome:** succeeded. 31 places, 42 stops, all confirmed. 5 of the provisional labels were wrong or missing (BM14, BM17, BM19, BM40, BM42) and BM25 was merged into the wrong place. The 17-Nov crosswalk was also updated (17-Nov BM17 is now `exit_10_4F`, BM19 `exit_5_4F`).
- **What changed because of it:** exit 5 now has 3 visits and the revisit test has 9 places instead of 6 (entry 10).
- **Links:** `phase2/new/cross-day/labels_23nov_confirmed.csv`, `.../out/label_changes_vs_provisional.csv`, commits `b4243c1`, `7ece689`.

## 10. 24 Nov: revisit 4/6 became 7/9, cross-day 24% became 18 to 24%

- **What we tried:** rerun `crossday.py` on the confirmed labels.
- **Result** (`out/results.json`, `cross-day/README.md`, `1df6965` summary):
  - Same visit, 23 Nov (leaky, n = 42): 98 to 100% with magnetic x/y/z.
  - **Revisit, 23 Nov (9 places, chance 3.2%):** 7/9 = 78% (|B|+xyz with barometer floor; window level 69%, within one neighbour 89%, floor 100%). Before the relabel: 4/6 = 67%.
  - **Cross-day, train 23 Nov, test 17 Nov (15 core places, 17 test visits, chance 6.7%):** 18 to 24% (|B| only 18%, |B|+xyz 24% = 4/17, with barometer floor 18%). Before: 24%.
  - |B| only on revisits: 0%. Wi-Fi: 0 to 11% (entry 12).
  - The two revisit misses are BM40 (predicted the neighbour `lt2a`) and BM41 (predicted `lt1b`).
- **Outcome:** succeeded as a measurement, with two caveats. The jump from ~100% (same visit) to 78% (revisit) to 18 to 24% (other day) is exactly the leakage. And cross-day is only about 3 times chance. n is 9 and 17: one visit is 11% or 6%. The cross-day 17-Nov side still has 8 of 23 place matches inferred from route order (core uses only the 15 high-confidence ones).
- **What changed because of it:** the day-3 plan targets the likely causes: phone handling differs between days, 17-Nov stops were 30 s (23 Nov: 60 s), and the two days used different phones.
- **Links:** `phase2/new/cross-day/out/results.json`, `.../out/summary_table.csv`, `.../out/fig_accuracy_overview.png`.

## 11. 24 Nov: FAILURE, a fixed barometer threshold does not work (weather drift)

- **What we tried:** decide the floor of a stop from one fixed pressure threshold learned on the other day.
- **Why:** the simplest possible floor detector.
- **How:** `crossday.py`, "floor" section of `results.json`. Compared: absolute threshold, threshold re-zeroed at the first stop, and step tracking (a floor change when consecutive stops jump by more than half a floor step).
- **Result:** absolute threshold: train 17 to test 23 = 23/42 (55%), train 23 to test 17 = 15/26 (58%). Re-zeroed at the first stop: 29/42 and 26/26. **Step tracking: 42/42 and 26/26.** One floor step is 0.58 hPa (17 Nov) and 0.68 hPa (23 Nov); the floor-5 pressure drifted by 0.46 hPa over the 23-Nov session (range), almost a whole floor.
- **Outcome:** the fixed threshold failed because the weather moves the pressure by almost a floor step. Step tracking works on both days.
- **What changed because of it:** all fused methods use step tracking; the predicted place is on the correct floor 100% of the time. The floor is considered solved.
- **Links:** `phase2/new/cross-day/out/fig_pressure_by_stop.png`, `results.json` (`floor`).

## 12. 24 Nov: FAILURE, WiGLE CSV Wi-Fi is near useless

- **What we tried:** Wi-Fi fingerprints (strongest RSSI per access point in 10 s chunks, random forest and kNN).
- **Why:** Wi-Fi is the usual indoor-positioning signal; the old collect list claimed "dense Wi-Fi, 41/42 stops covered (~39 scans each)".
- **How:** `crossday.py`, Wi-Fi features from `clean-data/*/wifi/`.
- **Result:** revisit test 0 to 11% (n = 9, chance 3.3%); cross-day core 11 to 22% (n = 9, chance 11%); Wi-Fi exists at only 9 of the 15 core places on both days. 80% of the 23-Nov BSSIDs appear at only one stop; the 9 revisit pairs share 0 to 3 access points (out of 4 to 192 per stop). Wi-Fi scores near zero even inside one stop (same-visit 10%).
- **Outcome:** failed, and the cause is the logger, not Wi-Fi itself. WiGLE writes an access point to its CSV only when it is new or its signal improves, so repeat scans are never saved. The "41/42 covered" claim counted rows, not repeated scans, so it was misleading.
- **What changed because of it:** day-3 rule: use a logger that saves every scan, and test WiGLE's database export first (untested). Android Wi-Fi scan throttling also stays OFF.
- **Links:** `phase2/new/cross-day/README.md` (Caveats), `phase2/clean-data/2026-11-17/README.md` (Wi-Fi limitations).

## 13. 24 Nov: FAILURE, stops cannot be tilt-corrected (no accelerometer logged)

- **What we tried:** orientation-proof magnetic features (split the field along gravity) at the stops.
- **Why:** x/y/z magnetic features reach 78% on same-day revisits but only 18 to 24% across days, and the phone is held differently each time.
- **How:** checked what the stop recordings logged.
- **Result:** stop recordings (BM*) logged only the barometer and magnetometer on both days, so the phone's tilt at a stop is unknown. The 23-Nov walks logged accelerometer, gyroscope and magnetometer on one clock (starts agree within 0.11 s, all ~100 Hz); the 17-Nov walks logged only the accelerometer.
- **Outcome:** failed for stops. Only 23-Nov walks can be corrected (entry 15).
- **What changed because of it:** day-3 rule: accelerometer + gyroscope ON during stops too.
- **Links:** `phase2/new/cross-day/README.md` (Orientation correction).

## 14. 24 Nov: FAILURE, the two iPhones' magnetometers disagree (r = 0.20)

- **What we tried:** add the walk endpoints to the stop fingerprints to get more training data.
- **Why:** more samples per place.
- **How:** `tilt.py`, `device_check_walk_vs_stop_mean_B` in `out/tilt_results.json`.
- **Result:** stops used an iPhone17,4 and walks an iPhone19,2 (the same two models on both days). Mean |B| at the same 31 places correlates only r = 0.197 (median absolute difference 3.96 µT).
- **Outcome:** failed: stop data and walk data can't be mixed. We also can't verify that the same physical iPhone was used on both days, or whether its magnetometer output is calibrated. For comparison, the 17-Nov vs 23-Nov field strength per shared place does correlate (r = 0.687), so |B| carries some place signal across days on the same stop phone.
- **What changed because of it:** day-3 rule: one phone for stops and walks, the same phone every day.
- **Links:** `phase2/new/cross-day/out/tilt_results.json`, `.../out/fig_magnetic_17_vs_23.png`.

## 15. 24 Nov: tilt correction on walk endpoints, 39% vs 0%

- **What we tried:** since stops can't be corrected (entry 13), test the idea on 23-Nov walk endpoints (first and last 2 s of each walk, labelled with the stop before and after).
- **Why:** to see whether orientation-proof features are worth the day-3 effort.
- **How:** `tilt.py` (commit `f35e9ca`, 24 Nov 02:46 HK). Gravity from the mean accelerometer ("low-pass") or a gyro-aided complementary filter; field split into B_vertical and B_horizontal; 1-nearest-neighbour; leave one pass out.
- **Result** (`out/tilt_results.json`): 66 endpoints over 31 places (walks shorter than 5 s skipped); phone 8 to 21 degrees from flat (median 13). Other-pass accuracy, 28 test endpoints, chance 3%: |B| only 0%; raw x/y/z 0%; **tilt-corrected (low-pass gravity) 39% (11/28)**; gyro-aided gravity 29%. Latest pass only (10 endpoints): 40% for low-pass. Silhouettes are all still negative (low-pass -0.16 vs -0.49 for |B| only).
- **Outcome:** partly succeeded. It is the only feature set that recognised places on walk data (39% vs 0%), but the samples are noisy (people start or stop walking at the endpoints), n is small, and the number is not comparable to the stop numbers. The gyro-aided filter did not beat the plain average because the endpoints are almost still.
- **What changed because of it:** it justified asking for accelerometer + gyroscope at stops on day 3.
- **Links:** `phase2/new/cross-day/tilt.py`, `.../out/tilt_results.json`, `.../out/tilt_endpoints.csv`, `.../out/fig_tilt.png`, commit `f35e9ca`.

## 16. 24 Nov: team summary written and pushed to main

- **What we tried:** one plain-English page for teammates: what we did, results compared with before, the day-3 checklist and why, expectations to test (not results), and how to rerun.
- **How:** `TEAM-SUMMARY-2026-11-24.md`, commit `1df6965` (24 Nov 02:50 HK), pushed to `origin/main`. Earlier commits `d7cc053`, `b4243c1`, `7ece689` and `f35e9ca` were made on branch `analysis/cross-day`, which is fully merged into `main`.
- **Result:** `origin/main` at `1df6965`.
- **Outcome:** succeeded. The summary lists open questions about the 17-Nov labels (8 route-order matches; 17-Nov BM17 and BM19 were labelled "Exit 5 (revisit)" but were on floor 4).
- **Links:** `phase2/new/TEAM-SUMMARY-2026-11-24.md` (moved there in entry 17).

## 17. 24 Nov: old/new reorganisation, day-3 checklist, this log

- **What we tried:** make the repo readable: separate superseded work from current work, and write the collection rules down.
- **Why:** the pilot's 94% and the old collect list contradict the new findings; teammates could quote or follow them by mistake.
- **How:** `git mv` (history kept, no content changed apart from paths and notes):
  - `phase2/positioning-pilot/` to `phase2/old/positioning-pilot/`; `phase2/WHATS-LEFT-TO-COLLECT.md` to `phase2/old/`; each got a "Superseded on 2026-11-24. See phase2/new/" note.
  - `phase2/cross-day/` to `phase2/new/cross-day/`; `TEAM-SUMMARY-2026-11-24.md` to `phase2/new/`.
  - New `phase2/new/DAY3-CHECKLIST.md`.
  - Paths fixed: `crossday.py` now uses `PHASE2 = HERE.parent.parent`; `pilot_train.py` and `step_detection.py` read `../../clean-data/2026-11-17`; run commands in READMEs and the summary now say `phase2/new/cross-day/`.
  - Added this log plus `CLAUDE.md` and `AGENTS.md` (standing rule: every piece of work appends an entry here).
- **Result:** verification after the move: `crossday.py` (about 37 s) and `tilt.py` (about 3 s) rerun; every file in `new/cross-day/out/` is byte-identical to before, including `results.json` and `tilt_results.json`. `pilot_train.py` and `step_detection.py` rerun; CSV and JSON outputs are identical, the 3 PNGs differed only in bytes (plotting library output), so the originals were restored and `old/` stays as it was. The `cache/` and `__pycache__/` folders are ignored by `phase2/new/cross-day/.gitignore`.
- **Outcome:** succeeded.
- **Links:** `phase2/README.md`, `phase2/new/DAY3-CHECKLIST.md`, `CLAUDE.md`, `AGENTS.md`.

## 18. 24 Nov: area definitions pre-registered (circles-on-lines graph nodes)

- **What we tried:** fix the "areas" used for the second accuracy measure (right area, not only the right checkpoint) before any tracker result exists, so the grouping can't be tuned to the results.
- **Why:** the user's design decision: a "circles on lines" map instead of Google Maps, and accuracy measured as exact checkpoint AND area, since people only need to know the area and can see the rooms around them.
- **How:** `phase2/new/graph/nodes.csv` (hand-edited input) and the grouping rule in `phase2/new/graph/README.md`, committed on their own, on branch `feat/circle-tracking`. The only data used: floor-5 metre coordinates (`phase2/map/coordinates_meters.csv`) and 23-Nov step counts per walk (`phase2/new/tracking/pdr.py`, next commit). Rule: same floor and connected; members with coordinates within 6 m of their centroid; a checkpoint without coordinates at most 20 steps from another member; longest path inside an area at most 36 steps; ties go to the tighter area.
- **Result** (`nodes.csv`): 31 real checkpoints (18 on floor 5, 13 on floor 4) in 11 areas (7 on floor 5, 4 on floor 4), plus 9 display-only virtual midpoints on long edges. 3 areas hold a single checkpoint (`y5302`, `y5202`, `lt1b`).
- **Outcome:** done, but slightly above the 8 to 10 areas we aimed for: the 6 m rule would not let the two classrooms merge with the study rooms or toilets. Floor-4 areas are larger than floor-5 ones because floor 4 has only step counts, no coordinates.
- **What changed because of it:** the tracker evaluation (next entry) scores "area correct" with exactly these groups.
- **Links:** `phase2/new/graph/nodes.csv`, `phase2/new/graph/README.md`.

## 19. 24 Nov: graph edges and step counting (PDR) on the walks

- **What we tried:** build the lines of the circles-on-lines map from the collector's real 23-Nov route, and count steps and gyro turns on every walk.
- **Why:** step counting fills the line between two circles; the step counts also tell the tracker how long each line is.
- **How:** `phase2/new/tracking/pdr.py` (step detector reused unchanged from `phase2/old/positioning-pilot/step_detection.py`; turns = gyroscope around gravity, 23 Nov only because 17-Nov walks have no gyroscope). `phase2/new/graph/build_graph.py` writes `edges.csv` and `area_check.csv`. Every walk is matched by time to the stop before and after it.
- **Result** (`tracking/out/pdr_summary.json`, `graph/edges.csv`, `graph/area_check.csv`):
  - Graph: floor 5 has 18 nodes and 22 edges, floor 4 has 13 nodes and 14 edges, plus 3 floor-change edges (stairs, and the two escalators supported by the 17-Nov back-to-back landing stops). 39 edges, 9 long edges with virtual midpoints. Each of the 37 walks is a different edge. No lift ride on either day, so no lift edge.
  - Steps, 23 Nov: 37 walks, 558 steps, median cadence 1.55 steps/s. 2 walks (ACC06, ACC11) have big sampling gaps, so their steps are marked unreliable. 17 Nov: 23 walks, 353 steps, median cadence 1.57; ACC16 unreliable.
  - Stride against the floor-5 map (straight-line pin distances): median 0.54 m per step on 23 Nov (10 walks, range 0.32 to 1.59) and 0.46 on 17 Nov (10 walks, range 0.29 to 0.77). The 1.59 is ACC01 (canteen to exit 5, 7 steps for 11.1 m), which looks like an undercount.
  - Turns: the two reliable straight study-room corridor walks (ACC05, ACC07) show no turn (net -8 and +6 degrees). The stairs walk (ACC23) shows one -136 degree turn and -190 degrees in total, consistent with turning on a landing. 3 of 37 walks have a turn of 45 degrees or more.
  - Area rule check: all 11 pre-registered areas pass (`area_check.csv`).
- **Outcome:** partly succeeded. Steps look realistic (about 1.5 steps/s) and are good enough to say "moving along a line" and roughly how far. The stride varies a lot between walks, so steps alone cannot place someone to within a few metres. Turns can only be checked in two places (straight corridor and stairs), because there is no corridor map for the other walks and none for floor 4.
- **What changed because of it:** the tracker (next entry) uses steps only to judge "which line, and how far along it", and the barometer and magnetometer to confirm the circle.
- **Links:** `phase2/new/tracking/pdr.py`, `.../out/pdr_walks_23nov.csv`, `.../out/pdr_walks_17nov.csv`, `.../out/pdr_summary.json`, `phase2/new/graph/build_graph.py`, `.../edges.csv`, `.../area_check.csv`, `.../README.md`.

## 20. 24 Nov: route-aware tracker (HMM on the graph): helps across days, not on 23-Nov LOVO; v1 FAILED to recover

- **What we tried:** proposal method D, a tracker that follows you along the circles-on-lines graph. Steps move the belief along a line, and the barometer floor plus the magnetometer confirm the circle at a stop. We compared it on the same stops with the independent snapshot classifier from `crossday.py`, and exported a replay file for the UI.
- **Why:** the user's design: light up circles as you walk, with no Google Maps and no compass.
- **How:** `phase2/new/tracking/tracker.py` (run everything with `sh phase2/new/tracking/run_all.sh`). 23 Nov is replayed in time order with leave-one-visit-out (the magnetic model for a stop never contains that stop) and leave-one-walk-out step lengths. Cross-day: train on 23 Nov, replay 17 Nov. Metrics per stop visit with 95% Wilson intervals: exact, area (pre-registered, entry 18), within one neighbour, top-3, floor, within 5 m. v1 used parameters fixed before the first run. After v1's failure analysis, v2 changed exactly two things: 5% re-localisation after each move and a floor weight of 0.99.
- **Result** (`tracking/out/tracker_results.json`):
  - **23 Nov, all 42 stops:** tracker v2 exact 12/42 = 29% [17 to 44], area 16/42 = 38%, floor 40/42; tracker v1 exact 11/42, area 17/42; snapshot exact 15/42 = 36% [23 to 51], area 19/42 = 45%, floor 42/42. 22 of the 42 stops are the only visit to their place, so they have no fingerprint when tested: 0/22 exact for every method. On the 9 latest revisits both get 7/9 (the same as `crossday.py`'s 78%).
  - **Cross-day 23 to 17, core (17 visits):** tracker v2 exact 5/17 = 29% [13 to 53], area 12/17 = 71% [47 to 87], top-3 12/17, floor 17/17; tracker v1 exact 6/17, area 12/17; snapshot exact 2/17 = 12% [3 to 34], area 7/17 = 41% [22 to 64]. Extended (25 visits): tracker v2 exact 10/25, area 17/25; snapshot 4/25 and 9/25.
  - Steps alone (belief on arrival, before the stop's data): 2/42 exact on 23 Nov.
  - Optimistic variant (line lengths from the same walks): 23 Nov exact 14/42, area 19/42, floor 42/42.
  - Sensitivity (v2, temperature x window weight, 9 settings): 23-Nov exact 26% to 33%.
  - "Confirmed" (top circle at least 0.6): 2000 of 5082 stop frames, of which only 660 are correct.
  - Replay: `out/replay_23nov.json` 5874 frames, `out/replay_17nov.json` 2078 frames.
- **Outcome:** mixed.
  - FAILURE (v1): with no re-localisation a wrong belief could never come back, and the 0.95 floor weight lost to the transition prior. v2 fixes the first problem but barely changes the numbers.
  - 23 Nov: no better than the snapshot, because half the stops have no fingerprint, and the graph carries the resulting errors forward. BM27 and BM28 (right after the stairs) are on the wrong floor in both versions: under leave-one-walk-out the stairs line has no known length, so 53 steps look implausible.
  - Cross-day: the graph clearly helps (area 12/17 vs 7/17). This is optimistic: the graph was built from the same route, the transition prior assumes one recorded line per walk, the escalator lines come from the 17-Nov data, and the intervals overlap.
  - "Confirmed" is not reliable yet.
- **What changed because of it:** the UI builds against `replay_23nov.json` (keys documented in `phase2/new/tracking/README.md`). For day 3, every place needs at least two visits, so that a leave-one-visit-out test has a fingerprint for every place, and a test walk off the recorded route would check the optimistic part.
- **Links:** `phase2/new/tracking/tracker.py`, `.../run_all.sh`, `.../README.md`, `.../out/tracker_results.json`, `.../out/tracker_visits_23nov.csv`, `.../out/tracker_visits_17nov.csv` (`_v1` files for v1), `.../out/replay_23nov.json`, `.../out/replay_17nov.json`; area pre-registration commit `dc76ab2`; graph/PDR commit `b62d9e0`.

---

## 21. 24 Nov: circle navigator UI prototype (circles on lines)

- **What we tried:** a phone-first navigator UI replacing Google Maps. Checkpoints are circles joined by lines on two floor panels (5F, 4F). The line to the next circle fills with the step count and snaps when the sensors confirm the circle. The destination is green with the planned route highlighted. The current area is shaded, and the panel shows exact-point and area ✓/✗ against `true_node`.
- **Why:** a UI that matches what the tracker produces (graph, edge progress, confirmed node, top-3, area). It was built against the agreed JSON format on a mock while the tracker was built in parallel.
- **How:** `phase2/new/circle-ui/index.html` (vanilla JS + SVG, no build step). Route = Dijkstra in JS over `distance_m` (else `median_steps`). Search = a JS port of Dicta's keyword matcher (`phase2/request-matching/match.py`, `destinations.csv`). `make_mock.py` builds the mock from `phase2/new/cross-day/labels_23nov_confirmed.csv` (31 nodes, 39 edges, 680 frames, 10 areas, destination `lt1a`, seed 23). Checked in headless Chromium at 1280 px and 390 px, light and dark.
- **Result:** no console errors. Opened from disk the mock loads; over http it loads `../tracking/out/replay_23nov.json`, falling back to the mock, labelled "MOCK DATA".
- **Outcome:** success as a UI prototype. The mock's positions, steps and guesses are invented. Security review fix before commit: replay values are written with `textContent` only, the file is validated (id/zone character sets, integer floors, numeric/boolean fields), and `?data=` accepts same-origin paths only. Tested with injection ids/zones and a cross-origin URL: all refused.
- **Integration with the real tracker output (done when landing on `main`):** the UI was opened with the real `replay_23nov.json` (40 nodes incl. 9 virtual midpoints, 39 edges, 5874 frames, destination `escalator_up_4F`) in headless Chromium; no console errors, every frame scrubbed. The tracker's code and outputs were not changed. Minimal fixes in `circle-ui/index.html` only: (1) virtual midpoints (`virtual: true`, `zone: null`, `on_edge`) are accepted and drawn as small display-only dots, with no label, area, search hit or route (before the fix they were full circles labelled "V canteen exit 5" and added a shaded "?" area); (2) the validator also checks `virtual` (boolean) and `on_edge` (node ids), still refusing bad characters in non-null ids and zones; (3) real area ids (`a5_canteen_front`) are shown as "5F · Canteen front"; (4) playback skips recording breaks (gap above 5 s between frames, e.g. the 32-minute break); (5) edges with `median_steps: null` show no step count instead of "0 steps"; (6) after a floor change the tracker's unconfirmed guess on the new floor is shown as "you" (the last confirmed circle was on the other floor); (7) a file refused by validation keeps its error message on screen, and a missing destination falls back to the last real node, not a virtual one. Exact/area counts skip frames with no `true_node` (792 of 5874); per 0.5 s frame on 23 Nov they are exact 1251/5082 and area 1740/5082, the same as recomputed from the file in Python. These frame counts are not the per-stop numbers of entry 20. Re-tested after the fixes: the mock still loads (from disk and `?data=mock`); an injection id, an injection zone, a bad `on_edge` and a non-boolean `virtual` are refused with a message and nothing runs; `?data=` with another origin, another port, `//host/...` and `javascript:` is refused; `replay_17nov.json` loads.
- **What changed because of it:** the JSON format is exercised by a consumer. `zone` carries the area id; "area correct" = the zone of the top guess equals the zone of `true_node`. The real replay shows the tracker's weak points visibly, for example the stairs walk ends on 5F and the first 4F frame is an unconfirmed guess.
- **Links:** `phase2/new/circle-ui/` (README: real data vs mock), screenshots with real data `phase2/new/circle-ui/screenshots/real-desktop-*.png` and `real-phone-*.png` (start, mid-walk, stairs on 5F, floor switch to 4F, arrival), commit 66a437c on `feat/circle-ui` (merged into `main`).

---

## 22. 24 Nov: graph-v2, merged study rooms and lift/stairs (non-destructive)

- **What we tried:** a second version of the graph with two places merged, from the collector's 24-Nov hand-drawn maps: the four study rooms `sr8`/`sr9`/`sr10`/`sr11` into one node `sr9`, and lift+stairs `lift_5`+`exit_5_stairs` into `lift_stairs` (5F) and `lift_5_4F`+`exit_5_stairs_4F` into `lift_stairs_4F` (4F). `Y5-202` and `Y5-302` were kept separate (not part of the study-room cluster).
- **Why:** the four study rooms are within ~5 m of each other (`a5_study_rooms` radius in `area_check.csv`), so a fingerprint classifier only confuses them; the collector treats the cluster, and the lift/stairs pair, as one place each. Wanted both the routing graph and the cross-day classifier labels to reflect that, without touching v1.
- **How:** `phase2/new/graph-v2/merge_v2.py` reads `../graph/nodes.csv`, `../graph/edges.csv`, `../cross-day/labels_23nov_confirmed.csv` and `../graph/area_check.csv` and writes a fresh `graph-v2/`. Node contraction: internal edges (both ends in one merged node) are dropped; the distance to a merged cluster is the boundary edge distance (e.g. `y5302–sr9` keeps 8.0 m from the old `y5302–sr11`, `sr9–y5202` keeps 7.1 m from the old `sr8–y5202`); duplicate edges after contraction keep the shorter `distance_m`. Merged lift/stairs nodes are placed at the mean of their members' coordinates. v1 files are not modified; `crossday.py` is not switched over.
- **Result:** real places 31 → 26; `nodes.csv` 35 rows (26 real + 9 virtual midpoints), `edges.csv` 34 edges, graph connected (26/26 real nodes reachable from `canteen`, checked in Python). `labels_23nov_merged.csv` has all 42 rows with the study-room and lift/stairs rows remapped (BM05/06/08 → `sr9`, BM22/23/26 → `lift_stairs`, BM27/28 → `lift_stairs_4F`), each `note` recording the `old->new`. `area_check_v2.csv` has the remapped membership lists (metrics not recomputed).
- **Outcome:** success as a data artifact; non-destructive. Not yet an accuracy result — nobody has rerun the classifier on the merged labels.
- **What changed because of it:** the team can point `crossday.py` at `labels_23nov_merged.csv` to score merged classes, and the map/UI can read `graph-v2/` to show one study-room circle and one lift/stairs circle per floor. v1 stays as the record of the un-merged graph.
- **Links:** `phase2/new/graph-v2/` (`merge_v2.py`, `nodes.csv`, `edges.csv`, `labels_23nov_merged.csv`, `area_check_v2.csv`, `README.md`).

---

## 23. 24 Nov: two-session clean dataset published (sesi1 4-phone + Wi-Fi, sesi2 2-phone)

- **What we tried:** cleaned and published both 24-Nov collection sessions (floor 5 + floor 4), raw and organized, under one isolated folder `phase2/clean-data/2026-11-24/` (`README.md`, `sesi1/`, `sesi2/`, `floor-sketch-v1.pdf`, `scripts/`). Each session has `raw/` (byte-identical phone ZIPs + WiGLE `.csv.gz`) and `clean/` (browsable tree + tables).
- **Why:** day-3 training data; a second independent pass (sesi2) gives a real cross-session train/test split (train sesi1, test sesi2) without the same-day leakage that inflated earlier numbers.
- **How:** `scripts/build_clean.py` groups each physical stop/walk across phones by **timestamp** (raw labels are noisy — three languages + typos), assigns a canonical node + floor, de-duplicates (including the nested `attachments.zip` bundles), copies each sensor CSV verbatim, and associates WiGLE first-sightings to the **nearest** stop (`in_window` inside the 60 s dwell, else `approach` within 120 s, since WiGLE scans in bursts between stops). `gen_docs.py` and `make_route_html.py` write the ROUTE/README. Floor split is by route: floor 4 begins at the "lift stair 5 lantai 4" landing (collector-confirmed); barometer alone can't split the floors because pressure drifted over the day.
- **Result:** Sesi 1 — 220 unique recordings (4 phones iphone/s24/a55/a56, 55 each), 27 stops + 28 walks (15+15 floor 5, 12+13 floor 4), Wi-Fi 18,668 obs / 4,839 BSSIDs, 27/27 stops covered (`sesi1/clean/summary.json`). Sesi 2 — 108 recordings (2 phones, 54 each), 26 stops + 28 walks, Wi-Fi 17,376 obs / 7,852 BSSIDs, 26/26 stops covered (`sesi2/clean/summary.json`). Both verified: no empty sensor files, every stop has ≥ 1 iPhone barometer.
- **Outcome:** success — both sessions complete and organized; a friend can train directly from `clean/` or rebuild it from `raw/` with `scripts/build_clean.py`.
- **What changed because of it:** floor 4 is now covered with repeated visits, and the cross-session split (sesi1→sesi2) replaces same-day leakage. Confirmed from `sesi2/clean/summary.json` that the **s24 (SM-S9280) barometer is unreliable** (drifts several hPa standing still) — use the iPhone `Barometer.csv` for floor features. Note: Y5302 was recorded at two different doors (`y5302` + `y5302_point2`, not a revisit); the floor-5 escalators form a canteen triangle (canteen→esca_down, esca_up→canteen, esca_up→esca_down).
- **Links:** `phase2/clean-data/2026-11-24/` (`README.md`, `sesi1/`, `sesi2/`, `scripts/`, `floor-sketch-v1.pdf`); summaries `sesi1/clean/summary.json`, `sesi2/clean/summary.json`.

---

## 24. 25 Nov: cross-day rerun on graph-v2 merged places (v1 kept)

- **What we tried:** the open item from entry 22: score `crossday.py` on the graph-v2 merged places (study rooms -> `sr9`, lift+stairs -> `lift_stairs` / `lift_stairs_4F`) and compare exact and area accuracy with v1.
- **Why:** to see whether merging places that a fingerprint can't separate changes the numbers before anyone uses v2 for the map/UI or quotes it.
- **How:** `crossday.py` got a `--v2` flag: labels from `phase2/new/graph-v2/labels_23nov_merged.csv`, the same merge applied to the 17-Nov crosswalk and the floor-5 map names, output to `phase2/new/cross-day/out-v2/`. Without the flag nothing changes: after the edit `out/` was regenerated and is byte-identical (checked with `git status`; the new venv with numpy 2.5.5, pandas 3.1.1, scikit-learn 1.9.1, matplotlib 3.11.2 also reproduces it byte for byte). New `compare_v1_v2.py` scores exact and area (pre-registered areas from `graph/nodes.csv` and `graph-v2/nodes.csv`) per stop visit from both `results.json` files, with 95% Wilson intervals.
- **Result** (`phase2/new/cross-day/out-v2/v1_vs_v2.json`, `out-v2/results.json`):
  - Places: 31 -> 26; cross-day core places 15 -> 12, extended 23 -> 20 (`out-v2/results.json`: `labels.n_places_23nov`, `crosswalk.core`, `crosswalk.extended`).
  - 23-Nov revisit, baro floor + |B|+xyz kNN: v1 exact 7/9, area 8/9 (chance 3.2%); v2 exact 7/11, area 8/11 (chance 3.8%). The two extra v2 test visits (BM08 study room, BM28 4F lift/stairs) only became "revisits" because different spots were merged; both are wrong. On the 9 shared visits v1 and v2 are identical (7/9).
  - Cross-day 23 -> 17 core (17 visits): |B|+xyz kNN v1 exact 4/17, area 8/17 -> v2 exact 5/17, area 8/17; baro floor + |B|+xyz kNN v1 3/17, area 10/17 -> v2 4/17, area 10/17. Chance 6.7% (v1) and 8.3% (v2).
  - Cross-day extended (25 visits), baro floor + |B|+xyz kNN: v1 4/25, area 10/25 -> v2 5/25, area 10/25.
  - Wi-Fi (9 core visits only), baro floor + RSSI RF: v1 2/9 -> v2 6/9 (chance 11% -> 17%). Four of the 9 Wi-Fi test visits are study rooms, so merging them decides most of this jump.
  - Floor results are unchanged (42/42 and 26/26 step tracking).
- **Outcome:** success as a check; the merge is cosmetic for the magnetometer. It gains exactly one exact visit (17-Nov BM04, sr11 predicted sr9) and cannot change area accuracy, because the merged spots were already in one area. The Wi-Fi jump rests on 9 visits and mostly on the study rooms becoming one class, so it is not evidence that Wi-Fi works.
- **What changed because of it:** v2 is fine for the map/UI (one study-room circle, one lift/stairs circle per floor) and costs nothing in accuracy. When quoting accuracy, say which place list was used; area accuracy is the same either way. The day-3 (24-Nov) evaluation (entry 25) uses the graph-v2 names.
- **Links:** `phase2/new/cross-day/crossday.py` (`--v2`), `phase2/new/cross-day/compare_v1_v2.py`, `phase2/new/cross-day/out-v2/` (`results.json`, `v1_vs_v2.json`, `v1_vs_v2.csv`, `summary_table.csv`, figures), `phase2/new/cross-day/README.md` (graph-v2 section), `.gitignore` (`.venv/`).

---

## 25. 25 Nov: 24-Nov evaluation without leakage: cross-session, cross-day, walk endpoints, barometer floor

- **What we tried:** honest place accuracy on the new 24-Nov two-session data (entry 23): train one session, test the other, per phone; train 23 Nov, test 24 Nov with the same handset; tilt-corrected features (now possible at stops, the accelerometer was logged); barometer floor per session.
- **Why:** 23-Nov same-visit numbers were inflated by leakage and the 17-Nov cross-day test was weak (18 to 24%). Session 2 is an independent second pass, so it gives a real train/test split.
- **How:** new folder `phase2/new/day3/`. `config.json` lists the sessions (23 Nov through `crossday.py`'s cache, 24 s1 and 24 s2 from `clean-data/2026-11-24/*/clean/`); `names_24nov.csv` maps every 24-Nov node to a graph-v2 place; `data.py` builds 5 s window features (|B| mean/sd/p10/p90, mean x/y/z, B_vertical/B_horizontal from the mean accelerometer in the window) and per-stop barometer and Wi-Fi tables, cached in `day3/cache/` (gitignored); `gknn.py` is a kNN where each feature group (|B|, xyz, tilt, Wi-Fi, baro floor) has its own distance and weight; `evaluate.py` runs the named splits (k = 5, equal weights, iPhone-barometer floor as an optional gate) and asserts that no recording or stop is in both train and test. Accuracy per stop recording, chance = 1/26 = 3.8% (26 graph-v2 places). Full tables: `phase2/new/day3/README.md`.
- **Result** (`phase2/new/day3/out/results.json`, `summary_table.csv`):
  - Phones (`devices`): the "iphone" is iPhone19,2 in 24 s1 and iPhone17,4 in 24 s2 (and the 23-Nov stops); the S24 (SM-S9280) is the same handset in both 24-Nov sessions. So iPhone s1 <-> s2 is a different-handset test.
  - Cross-session, |B|+xyz + floor: iPhone 12/26 (s1 -> s2) and 14/27 (s2 -> s1); S24 8/26 and 10/27. |B| + floor alone 4/26 to 5/27. Leaky reference (same recording, time split): |B|+xyz 26/26 on both phones.
  - Tilt at stops: B_vertical/B_horizontal alone 8/26 and 8/27 on the iPhone vs |B| alone 1/26 and 2/27 (no floor); added to |B|+xyz it changes the iPhone result by at most one recording (12/26 and 15/27 with floor) and lowers the S24 (7/26, 8/27).
  - True cross-day, same handset iPhone17,4, |B|+xyz + floor: 23 Nov -> 24 s2 13/26 (area 14/26); 24 s2 -> 23 Nov 18/42 (area 19/42). Different handsets (23 Nov -> 24 s1): 11/27. Training on 23 Nov + 24 s1, testing 24 s2: 15/26 (|B|+xyz+tilt + floor 16/26).
  - Walk endpoints, 1-NN as `tilt.py`, 23 Nov <-> 24 s1 with iPhone19,2 both days: raw x/y/z 15/54 and 21/66, tilt 13/54 and 19/66, |B| 6/54 and 5/66.
  - Floor, iPhone step tracking (threshold from the other sessions): 23 Nov 42/42, 24 s2 26/26, **24 s1 23/27**. Fixed threshold: 26/42, 27/27, 12/26. S24 step tracking 13/27 and 17/26.
  - Names (`unmapped_names`): nothing unmapped at graph-v2 level. Mapped by route position, needing confirmation: `male_disabled_toilet` = `disabled_toilet`, `y5302_point2` = `y5302_back`, `gate` = `entrance_exit`. No v1 name exists for the 24-Nov `sr9` and `lift_stairs5`, so 24 Nov can only be scored on graph-v2 places.
- **Outcome:** success, with two failures logged.
  - Same handset across days now gives 13/26 and 18/42 with 26 places, against 18 to 24% with 15 places on 17 Nov; the same protocol on both days is what changed. The 78% "revisit" number from 23 Nov is still not reached.
  - FAILURE (floor): in 24 s1 the 4 floor-5 stops after the long break (escalator_up 16:49, then disabled_toilet 18:12) are called floor 4. Pressure rose 0.833 hPa across the break (`floor_stats`, `step_tracking_wrong_stops`), more than the 0.315 hPa jump threshold. Step tracking assumes no weather change between consecutive stops; a long pause breaks that.
  - FAILURE (tilt): the 39% vs 0% walk-endpoint result on 23 Nov (entry 15) does not carry over across days; at stops (phone held the same way) and on walks (same walking direction both days) raw x/y/z already works, and tilt adds nothing on top.
  - The S24 pressure sensor is confirmed unusable for floors (floor step -0.014 hPa in session 1, median within-stop SD 0.234 to 0.438 hPa vs iPhone 0.005 to 0.034).
- **What changed because of it:** per-phone, same-handset models are the honest headline; the barometer rule needs a "long gap" guard (re-zero after a pause, or only accept a floor change when a walk or stair/escalator move happened in between). Not implemented here, because it would be tuned after seeing this failure.
- **Links:** `phase2/new/day3/` (`config.json`, `names_24nov.csv`, `data.py`, `gknn.py`, `evaluate.py`, `.gitignore`), `phase2/new/day3/out/results.json`, `phase2/new/day3/out/summary_table.csv`.

---

## 26. 25 Nov: FAILURE, Wi-Fi is still not a fingerprint on 24 Nov (WiGLE still logs new-or-stronger only)

- **What we tried:** check whether the 24-Nov WiGLE logs fixed the problem of entry 12 (each access point logged about once), and whether Wi-Fi can locate across sessions.
- **Why:** session 1's `summary.json` shows 1789 rows inside the stop dwell vs 11808 "approach" rows, which looked like the same logging limit.
- **How:** `phase2/new/day3/wifi_check.py` on all 9 WiGLE logs (23 Nov, 24 s1, 24 s2): rows per BSSID per log; whether a repeat row is stronger than every earlier row of that BSSID; rows per BSSID inside one 60 s stop; how many stops a BSSID is heard at; overlap (Jaccard) of BSSID sets between sessions for the same place vs other places. Each row is assigned to the nearest stop in time (in the dwell = in-window, else within 120 s). Classification with Wi-Fi is in `evaluate.py` (entry 25), using the S24 scanner only (the same scanner phone in every session).
- **Result** (`phase2/new/day3/out/wifi_diagnosis.json`, `results.json`):
  - Inside one stop, each BSSID appears a median of 1.04 (23 Nov), 1.02 (24 s1) and 1.08 (24 s2) times, while the scanner logged a median of 8, 6 and 12.5 distinct scan times per stop.
  - Repeat rows that are stronger than all earlier rows of that BSSID: 0.898 to 1.000 across the 9 logs.
  - Rows inside the dwell vs within 120 s: 24 s1 1841 vs 13597; 24 s2 4261 vs 11475; 23 Nov 1891 vs 4175.
  - In-window BSSIDs heard at one stop only: 0.807 (23 Nov), 0.85 (24 s1), 0.632 (24 s2).
  - Cross-session, S24 rows within 120 s: the stop with the largest BSSID overlap is the same place for 7/13 (24 s1 vs 24 s2) and 6/26 (23 Nov vs 24 s2). Only 14 of 27 session-1 stops have any S24 rows.
  - Classification (`results.json`): in-window Wi-Fi 2/26 and 2/27 (chance 3.8%); with the 120 s rows and the floor 6 to 8 of 26/27 within 24 Nov, 4/26 and 5/42 across days.
- **Outcome:** FAILURE, as expected. The WiGLE CSV is still a "new or stronger" log, not a scan log: an access point heard at one stop is almost never written again at the next stop, so there is no fingerprint to compare. The approach rows give a little signal within one day, but that partly reflects the walking order (the same access points are new on the same walk in both sessions), not the place. Adding Wi-Fi to |B|+xyz does not help consistently.
- **What changed because of it:** Wi-Fi stays out of the headline. Collecting usable Wi-Fi needs a logger that writes every scan (the open question from entry 12 is unchanged).
- **Links:** `phase2/new/day3/wifi_check.py`, `phase2/new/day3/out/wifi_diagnosis.json`; entry 12.

---

## 27. 25 Nov: weighted fused kNN on all stop data, leaky vs grouped vs leave-one-session-out

- **What we tried:** the user's design: one kNN over every stop recording of every session and phone (23 Nov, 24 s1, 24 s2), where each sensor group has its own learned weight in the distance (w_B for |B|, w_xyz, w_tilt, w_wifi, w_baro), with the weights and k tuned by cross-validation. Scored four ways on purpose, to show the leakage gap next to the honest numbers.
- **Why:** to see how far fusing everything gets, and to make the leakage visible: random row/window splits are exactly what produced the old 94%.
- **How:** `phase2/new/day3/fused_knn.py` (uses `gknn.py`). Samples = 5 s windows (2425 windows, 202 recordings, 95 stops, 26 places). Per group: standardised squared distance scaled by its median over training pairs; Wi-Fi = S24 rows within 120 s of the stop; baro = iPhone step-tracking floor (threshold from training stops only); a missing group drops out of the weighted mean. Weights on the simplex (step 0.25, then step 0.1 within 0.25 of the best, plus each group alone and equal weights), k in {1, 3, 5, 9, 15, 25}, chosen by inner CV on the training part only (nested CV), then scored once on the held-out part. Outer splits: random windows KFold(5) (LEAKY, illustration only); GroupKFold(5) by recording (partly leaky); GroupKFold(5) by physical stop (honest); leave one session out with leave-one-session-out inner CV (most honest). Asserts check that the honest splits share no recording or stop. Deployable setting: tuned by leave-one-session-out on all sessions. About 5 minutes.
- **Result** (`phase2/new/day3/out/fused_knn.json`, `fused_model.json`; per recording, chance 3.8%):
  - Random windows (LEAKY): 932/935 = 99.7% (window accuracy 99.1%).
  - Whole recordings (other phones of the same stop may be in training): 112/202 = 55.4%; "Wi-Fi only" also 112/202.
  - Whole stops, grouped CV: **58/202 = 28.7%** [22.9 to 35.3]; equal weights 54/202; x/y/z only 52/202.
  - Leave one session out: **74/202 = 36.6%** [30.3 to 43.5]; equal weights 71/202; x/y/z only 64/202; Wi-Fi only 29/202; baro only 16/202. Per fold: test 23 Nov 9/42 (weights B 0.1, xyz 0.5, tilt 0, wifi 0.3, baro 0.1, k 3), test 24 s1 42/108 (0.1, 0.6, 0, 0.2, 0.1, k 3), test 24 s2 23/52 (0, 0.2, 0, 0.3, 0.5, k 25).
  - Deployable weights: **w_B 0.1, w_xyz 0.7, w_tilt 0, w_wifi 0.1, w_baro 0.1, k 25** (inner leave-one-session-out accuracy 0.46).
- **Outcome:** the leakage demonstration worked: 99.7% (random) -> 55.4% (by recording) -> 28.7% / 36.6% (honest). The second step is a leak we had not named before: Wi-Fi and the floor belong to the stop, not the phone, so holding out one phone of a 4-phone stop still leaves its Wi-Fi vector in training, and the tuner puts 0.7 of the weight on Wi-Fi. Under honest splits Wi-Fi gets 0 to 0.3 and x/y/z carries the result. Learned weights beat equal weights by 3 to 4 recordings, inside the interval. FAILURE: pooling all phones is worse than a per-phone model: the pooled model gets 9/42 on 23 Nov, the same-handset per-phone kNN gets 18/42 on the same stops (entry 25), because the phones' magnetometers disagree.
- **What changed because of it:** report the honest splits only, with the leaky ones labelled as illustrations. For a deployable model, train per phone (or calibrate each phone's magnetometer) instead of pooling. New sessions are one line in `config.json` and add one leave-one-session-out fold automatically.
- **Links:** `phase2/new/day3/fused_knn.py`, `phase2/new/day3/gknn.py`, `phase2/new/day3/out/fused_knn.json`, `.../fused_model.json`, `.../fused_window_predictions.csv`; previous commit `1a28a48`.

---

## 28. 25 Nov: route-aware tracker on 24 Nov (train session 1, replay session 2) and a replay for the circle UI

- **What we tried:** the tracker of entry 20 (v2 parameters, `tracking/tracker.py` reused unchanged) on 24 Nov with graph-v2, and a replay file the circle UI can load.
- **Why:** the 23-Nov tracker test had no fingerprint for half its stops; on 24 Nov every place has a fingerprint from an independent session.
- **How:** `phase2/new/day3/track24.py`: graph = `graph-v2/` (26 places); magnetic fingerprints = session-1 iPhone stops (iPhone19,2), |B|+xyz on 2 s windows as `crossday.py`; expected steps per line = median over session-1 iPhone walks on that line (step detector reused unchanged from `phase2/old/positioning-pilot/step_detection.py`, as `pdr.py`); floor = iPhone step tracking with the session-1 floor step. Replay of session 2 (iPhone17,4, a different handset) in time order; each walk is attached to the last stop that started before it. Same comparison as entry 20 (snapshot kNN, emission only, belief on arrival).
- **Result** (`phase2/new/day3/out/track24_results.json`, `track24_visits.csv`; 26 stops, 26 places):
  - Tracker: exact **20/26** [58 to 89%], area 20/26, within one neighbour 22/26, top-3 21/26, floor 24/26.
  - Snapshot kNN (crossday.py recipe): exact 15/26, area 18/26, floor 26/26. Emission only: 15/26. Tracker on arrival (graph + steps only): 13/26.
  - Floor tracking on session 2: 26/26 (threshold 0.243 hPa). 28 test walks, 401 steps, none flagged unreliable; every walked line exists in graph-v2.
  - The tracker's two floor errors are the two 4F escalator stops, both put on the 5F `escalator_up` with probability 1.0: the very strong field there in session 2 (entry 29, `magnetic_check`) looks most like the strongest floor-5 fingerprint, and the magnetic evidence over 60 s outweighs the 0.99 floor weight.
  - "Confirmed" frames: 2095 of 3122 stop frames, 1830 of them on the right circle. Replay: `out/replay_24nov_s2.json`, 3560 frames, same keys as `tracking/out/replay_23nov.json` (checked in Python against the UI's id/zone rules; no browser was available in this session to open it).
- **Outcome:** success with the entry-20 caveats: the graph and the walk order come from the route both sessions walked, and every walk is one recorded line, so 20/26 is optimistic. The snapshot here (15/26, 2 s windows, sklearn per-floor kNN) differs from entry 25's 12/26 for the same split (5 s windows, `gknn.py`), so window length matters by a few stops.
- **What changed because of it:** the circle UI can show a 24-Nov replay without code changes: `phase2/new/circle-ui/index.html?data=../day3/out/replay_24nov_s2.json` over http. The 23-Nov replay and the UI are untouched. A test walk that leaves the recorded route is still needed to measure the tracker without the optimistic parts.
- **Links:** `phase2/new/day3/track24.py`, `phase2/new/day3/out/track24_results.json`, `.../track24_visits.csv`, `.../replay_24nov_s2.json`; `phase2/new/tracking/tracker.py` (unchanged); previous commits `1a28a48`, `3b9292c`.

---

## 29. 25 Nov: figures, an interactive data explorer, the day3 README and one-command rerun

- **What we tried:** figures for the report/video and a way for the team to "see the data": feature-space embeddings per sensor group and for the fused space, per-place |B| and pressure, a nearest-neighbour "confusion as a graph" on the graph-v2 layout, and an interactive HTML explorer. Replaces the leaky pilot's `phase2/old/positioning-pilot/out/magnetic_pca.png` (left untouched in `old/`).
- **Why:** the user asked to see clusters and drift between sessions, not only accuracy numbers.
- **How:** `phase2/new/day3/visualise.py` (matplotlib PNGs; at most three categorical colours per static chart with places as text labels; `explore.html` uses plotly.js 2.35.2 from a CDN, pinned with an integrity hash, data embedded). Embeddings: PCA and t-SNE of |B|+xyz (all windows) and |B|+tilt (24 Nov), t-SNE on the fused distance with the deployable weights, MDS of the Wi-Fi distance (one dot per stop). `run_all.sh` reruns everything in order. `evaluate.py` now also writes `magnetic_check` and the stops that floor tracking got wrong (`step_tracking_wrong_stops`) so the README's data notes come from a file. The explorer was checked by running its script in Node with a stub plot library (8 views, 26 place traces, 2425 points); no browser was available in this session.
- **Result:** `phase2/new/day3/out/`: `fig_accuracy_vs_chance.png`, `fig_leaky_vs_honest.png`, `fig_confusion.png`, `fig_floor_detection.png`, `fig_per_place_B_pressure.png`, `fig_knn_neighbour_graph.png`, `fig_embed_*.png` (6), `explore.html`. Data issues found while plotting (`results.json` `magnetic_check`): place medians above 100 uT at the 4F down-escalator in session 2 on both phones (iPhone 147.9, S24 127.7 uT) and at the 4F up-escalator (iPhone 142.5), while the 23-Nov iPhone ranges 32.9 to 58.9 uT. The Wi-Fi MDS shows no grouping of the same place across sessions, matching entry 26. `run_all.sh` reran the whole pipeline from the repo root (5 min 32 s): every file in `out/`, figures included, came out identical except the per-fold run times (`seconds`) in `fused_knn.json`, which were left at the committed values.
- **Outcome:** success.
- **What changed because of it:** `phase2/new/day3/README.md` documents the run, how to add a session (one `config.json` entry), the name map, the phone/handset table, all results and the data issues. Internal notes only, no report text.
- **Links:** `phase2/new/day3/visualise.py`, `run_all.sh`, `README.md`, `out/*.png`, `out/explore.html`; commits `643737d` (entry 24), `1a28a48` (entries 25, 26), `3b9292c` (entry 27), `113d90c` (entry 28).

---

## 30. 25 Nov: interactive kNN playground (slide features, see the neighbours and the predicted place)

- **What we tried:** a single HTML page where sliders position a query point on the stop-window scatter and the page shows the k nearest windows and the predicted place, as a demo for the video and for the team to build intuition. Internal team tool, not report text.
- **Why:** the user wanted "a k-nearest-neighbour graph where you slide certain variables to position a point and see which cluster (place) it belongs to".
- **How:** `phase2/new/day3/playground.py` embeds the 2425 five-second windows of `fused_knn.py` (26 places, sessions 23nov/24s1/24s2, all phones) into `playground_template.html` and writes `out/knn_playground.html` (0.23 MB; plotly.js 2.35.2 from jsDelivr with the same integrity hash as `explore.html`). Sliders: |B| mean, B_x/B_y/B_z mean, B_vertical, B_horizontal (range = data min..max, default median) plus a floor selector. The kNN runs live in JS in the full standardised space with the gknn.py recipe (standardise, mean squared difference per group divided by the group's median pair distance, weights, availability masks, votes weighted 1/(D+1e-6)); weights default to `out/fused_model.json` (B 0.1, xyz 0.7, tilt 0, baro 0.1, k 25). Wi-Fi is left out (cannot be slid). Differences from `fused_knn.py`, stated in the page: the |B| group is the window mean only (fused_knn.py also uses sd, p10, p90), scaling constants use all windows (not the training part only), floor is the true floor (not the step-tracked one), one query is one window (no per-recording aggregation). The 2-D view is a linear PCA computed in Python on the standardised weighted features (default weights; weight-0 groups get 0.05 so every slider moves the star), explained variance 34% and 25%; an "axes" option plots any two raw features. A "load a real window" control sets the sliders from a window of a chosen session/place and shows its true place; by default it holds that window's whole session out of training. Filters: floor, session, phone. `playground_check.py` + `playground_check.js` compare the JS with sklearn.
- **Result:** check (720 cases: 6 settings x 60 random windows x tilt on/off, including held-out session, held-out stop, one phone only, floor-5 only): the JS prediction equals sklearn `KNeighborsClassifier(metric='precomputed', weights=1/(d+1e-6))` on an independently built (scipy) distance matrix in 720/720 cases, same neighbour set in all 720, largest vote-share difference 1.3e-15; the JS PCA projection of a window equals the embedded pc1/pc2 to 0.0005 (3-decimal rounding). A first run showed 712/720 only because the Python reference treated a missing tilt of the query as zero (23-Nov windows have none); the page drops the tilt group in that case and the reference was fixed to match, so that was a bug in the check, not in the page. Rendered in headless Chromium (playwright-core, because the `mcp__browser__*` tools could not connect to Chrome): desktop, phone width (390 px, no horizontal scroll) and dark mode, no console errors except a favicon 404 from the test server.
- **Outcome:** success. Limits: single-window predictions are far noisier than the per-recording numbers in the README (do not quote the page's hits as accuracy); the 2-D projection cannot show why a neighbour is near in the full space; pressure is not a slider.
- **What changed because of it:** `run_all.sh` builds the page after `visualise.py`; README table row added.
- **Links:** `phase2/new/day3/playground.py`, `playground_template.html`, `playground_check.py`, `playground_check.js`, `out/knn_playground.html`; the commit that adds this entry.

---

## 31. 25 Nov: per-phone filtering and colouring in the playground and the explorer

- **What we tried:** make the data viewable per phone (iphone, s24, a55, a56) in both interactive pages. The playground already had phone checkboxes, but unlabelled in the last card, and the user did not find them. Internal team tool, not report text.
- **Why:** the phones' magnetometers disagree (entries 14, 27) and the README recommends a same-phone test, so the team wants to see each phone's windows on their own and test "train on the same phone only".
- **How:** edited the generators, not only the HTML: `phase2/new/day3/playground_template.html` (+ `playground.py`, unchanged) and `visualise.py`, then reran `visualise.py` and `playground.py`. Playground: a labelled **Phone** dropdown at the top next to Colour/View (all phones plus each phone, with window counts); the filter card now has labelled "Sessions:" and "Phones:" rows; dropdown and checkboxes are two views of the same state (several ticked phones show "custom (several)"); **Colour by place / phone** toggle (shape stays session, place goes first in the hover); "Try it" has a Phone dropdown for the random window and a "train on same phone only" checkbox (with the note that "iphone" is two handsets). The training-mask rule moved into the CORE block as `buildMask()` so the Node check runs the page's own filtering. Explorer: Phone dropdown (counts per phone for the current view), Colour by place/phone toggle, every point now carries a phone key (the Wi-Fi view counts as s24, the barometer view as iphone). `playground_check.py`/`.js`: new cases that go through `buildMask` (single-phone s24 with own session held out, single-phone iphone with whole stop held out, a55 only, "same phone only"), plus a check that the page's mask equals an independent numpy mask.
- **Result:** windows per phone (from `data.load()`, shown in the page labels): iphone 1140, s24 636, a56 325, a55 324 (total 2425); per phone and session: iphone 504 (23 Nov) / 324 (24 s1) / 312 (24 s2), s24 324 (24 s1) / 312 (24 s2), a55 324 and a56 325 (24 s1 only). `playground_check.py`: JS prediction equals sklearn in 960/960 cases (the earlier 720 plus 240 new single-phone and same-phone cases, 60 per setting), same neighbour set in all, largest vote-share difference 1.3e-15, and the page's training mask equals the numpy mask in 960/960. Rendered headless in Chromium (playwright-core), desktop 1280 and 390 px, no horizontal scroll, no console errors; selecting s24 in the dropdown ticks only s24 in the filter card (636 of 2425 windows used), "random window + s24 + same phone only" trained on 324 windows, all nearest neighbours s24. Screenshots: `phone_*.png` in the session scratchpad (not committed).
- **Outcome:** success. A first run of the new check gave 932/960 only because my numpy mask did not implement the "whole stop" hold-out (the page was right); fixed in the check, so that is a bug in the check, not in the page.
- **What changed because of it:** `out/explore.html` and `out/knn_playground.html` regenerated (PNGs identical on rerun); README unchanged except the explorer line.
- **Links:** `phase2/new/day3/playground_template.html`, `visualise.py`, `playground_check.py`, `playground_check.js`, `out/explore.html`, `out/knn_playground.html`; the commit that adds this entry.

---

## 32. 25 Nov: the phone is the real handset (ip16 / ip18), all-sessions option, phone x session panel

- **What we tried:** make the phone identity in the whole day-3 pipeline the real handset, read per recording from the source data, instead of one lumped "iphone". Internal team tool, not report text.
- **Why:** two different iPhones were used (entries 14, 25), and the user confirmed it and named them: an iPhone 16 and an iPhone 18, labels `ip16` (iPhone17,4) and `ip18` (iPhone19,2). The per-phone filters/colours in `out/knn_playground.html` and `out/explore.html`, the "same phone only" playground test and the per-phone counts all still treated both as one phone (entry 31: "iphone 1140 windows").
- **The assumption that was wrong:** until now the code keyed everything on the sensor slot ("iphone", "s24", "a55", "a56"), and the handset behind the iPhone slot was only noted by hand in READMEs and result notes. That was never wrong inside one session (each session has one iPhone for stops), but (a) the playground's "same phone only" for the iPhone mixed ip16 (23 Nov, 24 s2) with ip18 (24 s1), (b) the 23-Nov walk endpoints were hard-coded as iPhone19,2, (c) `track24.py` hard-coded its device text, (d) the explorer's Phone filter and counts merged both handsets.
- **How:** (1) new `phone_map.py`: reads `meta/device.csv` (`deviceModel`) of every raw ZIP (outer and nested) for 23 Nov, 24 s1, 24 s2, joins it to the cleaned manifests / `sessions.csv` by source ZIP name, writes `phase2/new/day3/phone_map.csv` (one row per recording: session, recording, type, sensor slot, source ZIP, device model, phone label, manifest model, status) and `out/phone_map_summary.json`, and exits non-zero on an unknown model, a raw/manifest mismatch or an unfound ZIP; it is the first step of `run_all.sh`. (2) `config.json` gets a `phones` map: model id -> `id` (stable key) and `display` (shown in the HTML pages and figures; rename it there, e.g. to "Michael's iPhone", rerun, no code change). The model-to-"iPhone 16/18" step is the user's statement (25 Nov), not something in the data. (3) `data.py`: the `phone` column is now the handset id, a new `slot` column keeps the sensor slot; visits get `handsets` and `iphone_handset`; the 23-Nov walk endpoints take their handset per walk from `sessions.csv`. `evaluate.py`, `track24.py`, `visualise.py`, `playground.py` use the handset; result keys keep the slot name and every split states its handsets. (4) `track24.py` also runs a same-handset variant. (5) Playground and explorer pages show the handset display name + model id in labels and hovers. (6) The two additions the user asked for: an "any session" option in the Try-it Session dropdown (the hold-out still applies to the loaded window's own session/stop/recording) and a top-level Session dropdown next to Phone, synced with the session checkboxes; and a "How each phone performs across sessions" panel (heatmap of correct/total per recording and per window, same-phone or all-phones training, live in the page's k and weights, grey cells where a phone has no data, cross-handset marker, hover lists places with hits and misses), exported from Python by `phone_matrix.py` to `out/phone_session_matrix.csv/.json`.
- **Result (mapping):** 407 recordings (79 on 23 Nov, 220 on 24 s1, 108 on 24 s2), all matched to a raw ZIP, 0 undetermined, raw model equals manifest model everywhere (`out/phone_map_summary.json`). 23 Nov iPhone slot: 42 stops ip16, 37 walks ip18 (so that session mixes both, by recording type); 24 s1: ip18 on all 55 iPhone recordings (plus s24 55, a55 55, a56 55); 24 s2: ip16 on all 54 (plus s24 54). The raw 14 and 17 Nov ZIPs (not used by day 3) also hold both iPhones (23 iPhone19,2 and 26 iPhone17,4 each). No model id other than the five in `config.json`. Windows per phone: ip16 816 (504 on 23 Nov + 312 on 24 s2), ip18 324 (24 s1), s24 636, a55 324, a56 325 (total 2425; before: iphone 1140).
- **Result (before vs after, full rerun `PYTHON=.venv/bin/python sh phase2/new/day3/run_all.sh`, exit 0):** no accuracy number changed. `results.json` `stop_results` (every experiment and feature set), `floor`, `floor_stats` and the walk-endpoint results equal the previous run apart from labels (keys, notes, `devices`, the phone names in the magnetic check); `fused_knn.json` and `fused_model.json` equal except the per-phone sample keys (ip16 504 on 23 Nov and 312 on 24 s2, ip18 324, instead of iphone) and fold timings; `track24_results.json` main results are unchanged (tracker 20/26 exact, area 20, within one 22, top-3 21, floor 24; floor tracking test 26/26). That is expected: every earlier split already selected the iPhone slot of a whole session, and each session has one iPhone for stops. What the lumped label did change was the interactive pages and the labels. The earlier README labels were right: 23 Nov -> 24 s2 is a true same-handset test (ip16 both, 13/26 and the reverse 18/42 with |B|+xyz + floor), 23 Nov -> 24 s1 is cross-handset (ip16 -> ip18, 11/27), 24 s1 <-> 24 s2 iPhone is cross-handset (ip18 <-> ip16), and the 23-Nov / 24-s1 walk-endpoint pair is same-handset (ip18 both days).
- **Result (new, same-handset tracker variant, `track24_results.json` `same_handset_variant`):** fingerprints and floor threshold (0.342 hPa) from the 23-Nov ip16 stops, line lengths from session 1: tracker 19/26 exact, 21/26 area, 24/26 top-3, floor 25/26; snapshot kNN 13/26; emission only 13/26. The cross-handset run (ip18 session 1 -> ip16 session 2) is 20/26, 15/26, 15/26. So the same handset a day earlier did not beat a different handset the same evening; day and handset are confounded (and 23 Nov has one visit per place), so no conclusion about handsets.
- **Result (playground checks):** `playground_check.py` now covers ip16 and ip18 separately (single-phone filter with own stop held out, "xyz+baro, own stop held out"), same phone only for ip16, the new session filters and the matrix: 1320/1320 predicted places agree with sklearn, 0 of 1320 mask differences, and the live panel's 70 cells (35 per mode) equal `phone_matrix.py` and `out/phone_session_matrix.json` (45 cells are greyed out because the phone has no data there; window and recording counts, chance, per-place tallies and handsets all equal). Headless Chromium smoke test: Session dropdown 24s2 ticks only 24s2 in the filter card (624 windows), ticking two boxes shows "custom", "any session" random windows came from all three sessions, the matrix computed in 362 to 453 ms live, no exceptions; the explorer lists ip16/ip18/s24/a55/a56 with the model ids. Panel numbers at the default weights, same phone only (recordings, windows; chance 3.8%): ip16 23 Nov -> 24 s2 14/26, 158/312; ip16 24 s2 -> 23 Nov 18/42, 220/504; ip16 leave-one-session-out 32/68, 378/816; s24 24 s1 -> 24 s2 8/26, 96/312; s24 24 s2 -> 24 s1 10/27, 125/324; s24 leave-one-session-out 18/53, 221/636. ip18, a55 and a56 have data in 24 s1 only, so they have no same-phone cross-session cell.
- **Outcome:** success. The panel is a live demo with the page's recipe (global scaling, true floor), not an evaluation; its numbers differ from the README tables by design.
- **What changed because of it:** README Phones section and tables relabelled (ip16 / ip18), per-phone window counts, section f (same-handset variant) and new section g; `phone_map.csv` is the audit trail; `run_all.sh` runs `phone_map.py` first. Unchanged: `prep/*`, the raw ZIPs, the cleaned data.
- **Links:** `phase2/new/day3/phone_map.py`, `phone_map.csv`, `phone_matrix.py`, `config.json`, `data.py`, `evaluate.py`, `track24.py`, `visualise.py`, `playground.py`, `playground_template.html`, `playground_check.py`, `out/phone_map_summary.json`, `out/phone_session_matrix.csv`, `out/knn_playground.html`, `out/explore.html`; the commit that adds this entry.

---

## Lessons learned

- **Same-recording splits give fake accuracy.** 94% (pilot) became 78% on later revisits and 18 to 24% on another day, for the same kind of features. Always report the honest split and label the leaky one as leaky.
- **Check how a label was made before trusting it.** A rule that looked fine ("stop = origin of next walk") silently mislabelled stops with no walk after them. The collector's route list fixed 6 of 42 labels.
- **A fixed pressure threshold fails because of weather; compare consecutive stops instead.** Step tracking got 42/42 and 26/26.
- **A log that "covers" a stop is not a fingerprint.** WiGLE rows are not repeated scans. Count repeated scans, not rows.
- **Log everything at stops that you log on walks.** Not having the accelerometer at stops blocked the tilt correction.
- **Use one phone for the whole protocol.** Two phones disagreed (r = 0.20).
- **Small n.** 9 revisit visits and 17 cross-day visits: one visit is 6 to 11%. Present them as first estimates.
- **A tracker needs a way back.** Limiting moves to neighbouring circles without a small "could be anywhere" share meant one wrong stop was never corrected (entry 20, v1).
- **A map can't replace a fingerprint.** Where a place had no fingerprint in training, the graph did not find it (0/22 on 23 Nov); it helps most when every place has a fingerprint and the magnetometer is weak (cross-day, area 12/17 vs 7/17).
- **Merging places only renames errors inside an area.** graph-v2 gained one exact cross-day visit and no area visits (entry 24); a merge can't fix a weak fingerprint, and "revisits" created by merging different spots are not real revisits.
- **Group by the thing that is shared, not by the file.** Wi-Fi and the floor belong to a stop, not to a phone: holding out one phone of a 4-phone stop gave 55% instead of 29% (entry 27). Random window splits gave 99.7%.
- **Check the device ID, not the phone's nickname.** "iphone" was two handsets on 24 Nov; the same handset across days gave 13/26 and 18/42, a different one less (entry 25). Pooling all phones in one kNN was worse than one model per phone (entry 27).
- **Step tracking on the barometer breaks over long pauses.** Weather moved the pressure 0.833 hPa during a break and four stops went to the wrong floor (entry 25).
- **A same-day win can vanish across days.** Tilt correction helped on 23-Nov walk endpoints (39% vs 0%) but added nothing across days or at stops (entry 25).
- **Check the check.** The first sklearn comparison of the playground disagreed in 8 of 720 cases because the reference mishandled a missing feature (entry 30); compare the missing-data rules, not only the maths.
- **Put the filter rule in the code that is tested.** The playground's training-mask rule now lives in the checked block and the check compares it with an independent mask (entry 31); a mask bug would otherwise hide behind a correct kNN.
- **A device ID in the metadata beats a label in a README.** The phone is now read per recording from each ZIP's `device.csv` and checked against the manifests (entry 32); the numbers did not change because each session had one iPhone, but the interactive pages and the "same phone" tests had been mixing two handsets.
- **Write failures down while they are fresh.** They are the reason the day-3 checklist has the rules it has.

## Open questions / next steps

- **Day-3 data (24 Nov) is in and evaluated (entries 25 to 29).** Still worth collecting if time allows (deadline 30 Nov): (1) a test walk that leaves the recorded route, with "I'm here" taps, to measure the tracker without the optimistic parts; (2) one handset for every session (the 24-Nov "iphone" was two devices, now labelled ip16 and ip18; ip18 has stops in 24 s1 only, so it has no same-handset cross-session test); (3) a Wi-Fi logger that saves every scan. A further fingerprint session with the same handset would add a fourth leave-one-session-out fold (one line in `phase2/new/day3/config.json`).
- **Cross-day with the new protocol (entry 25):** same handset 23 Nov -> 24 Nov s2 13/26 and the reverse 18/42 (chance 3.8%, 26 places), up from 18 to 24% on 17 Nov, still below the 23-Nov 78% revisit number. Only one same-handset day pair exists, so this is one estimate.
- **Open question: does a scan-every-time Wi-Fi logger make Wi-Fi usable?** Still untested; the 24-Nov WiGLE logs are again new-or-stronger only (entry 26).
- **Tilt at stops (entry 25):** answered for this protocol: no clear gain over raw x/y/z when the phone is held the same way. It might still matter for a user who holds the phone differently; untested.
- **17-Nov labels:** 8 of 23 place matches rest on route order. Anyone who remembers that walk can help (see section f of the team summary).
- **Floor-4 Google Maps pins** are still missing, so the map and routing stop at floor 5.
- **Unmerged branches** `prep/training`, `prep/map`, `prep/ready` are still local and unmerged; decide later whether any of it is wanted.
- **Tracker (entry 20):** collect at least two visits per place on day 3, plus a test walk that leaves the recorded route, to measure the tracker without the optimistic parts. The collector should confirm the area groups, the floor-4 loop order and the escalator pairs in `phase2/new/graph/README.md`. "Confirmed" needs a better rule before the UI relies on it.
- **Circle UI and tracker (entries 18 to 21), confirmations needed from the team:** the area groups (`phase2/new/graph/README.md`), the floor-4 loop order, the escalator pairs, whether ACC01 really stood still, the stairs U-turn and the corners, and the unrecorded exit5 to exit10 walk (see `phase2/new/tracking/README.md`). The UI shows these as the tracker has them. After day 3, re-export the replay and reload it in `phase2/new/circle-ui/` (it needs no change if the format is the same).
- **graph-v2 (entries 22, 24):** done: the merge changes cross-day exact by one visit and area not at all (entry 24). Still open: decide whether v2 replaces v1 for the map/UI; the collector should confirm the two merges match the hand-drawn maps.
- **Collector to confirm (entry 25, `phase2/new/day3/names_24nov.csv`):** 24-Nov `male_disabled_toilet` = 23-Nov `disabled_toilet`; `y5302_point2` = `y5302_back`; `gate` = `entrance_exit`; which study room the 24-Nov `sr9` stop was at.
- **24-Nov data questions (entries 28, 29):** what made the field above 100 uT at the 4F escalators in session 2 (both phones); the out-of-order walks in session 2 (floor-5 escalators, and gate -> exit 5 recorded before the gate stop); `sesi2/clean/ROUTE.md` says no Wi-Fi but the session has a WiGLE log; the session READMEs call both iPhones "iPhone 16 Pro" but the device IDs differ (iPhone19,2 and iPhone17,4); the user says they are an iPhone 16 (ip16, iPhone17,4) and an iPhone 18 (ip18, iPhone19,2), so the READMEs are wrong for the second phone. The handsets can be renamed (e.g. to owners) in `phase2/new/day3/config.json` `phones.display`.
- **Barometer floor rule:** add a guard for long pauses (entry 25) and pre-register it before testing it on new data.
- **Report:** the team writes the report wording (course rule). Numbers can be taken from `phase2/new/cross-day/out/` and this log.
