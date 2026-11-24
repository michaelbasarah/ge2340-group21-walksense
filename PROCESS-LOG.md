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

---

## Lessons learned

- **Same-recording splits give fake accuracy.** 94% (pilot) became 78% on later revisits and 18 to 24% on another day, for the same kind of features. Always report the honest split and label the leaky one as leaky.
- **Check how a label was made before trusting it.** A rule that looked fine ("stop = origin of next walk") silently mislabelled stops with no walk after them. The collector's route list fixed 6 of 42 labels.
- **A fixed pressure threshold fails because of weather; compare consecutive stops instead.** Step tracking got 42/42 and 26/26.
- **A log that "covers" a stop is not a fingerprint.** WiGLE rows are not repeated scans. Count repeated scans, not rows.
- **Log everything at stops that you log on walks.** Not having the accelerometer at stops blocked the tilt correction.
- **Use one phone for the whole protocol.** Two phones disagreed (r = 0.20).
- **Small n.** 9 revisit visits and 17 cross-day visits: one visit is 6 to 11%. Present them as first estimates.
- **Write failures down while they are fresh.** They are the reason the day-3 checklist has the rules it has.

## Open questions / next steps

- **Day 3 collection by Thu 26 Nov (deadline 30 Nov):** follow `phase2/new/DAY3-CHECKLIST.md`. A new independent session would give a real "train on days 1 and 2, test on day 3" number.
- **Open question: does the new protocol really lift the cross-day number?** We expect it to land closer to 78% than to 18 to 24%, but that is an expectation to test, not a result.
- **Open question: does a scan-every-time Wi-Fi logger make Wi-Fi usable?** Untested; check WiGLE's database export first.
- **Open question: how much does tilt correction help at stops?** The 39% is on walk endpoints only.
- **17-Nov labels:** 8 of 23 place matches rest on route order. Anyone who remembers that walk can help (see section f of the team summary).
- **Floor-4 Google Maps pins** are still missing, so the map and routing stop at floor 5.
- **Unmerged branches** `prep/training`, `prep/map`, `prep/ready` are still local and unmerged; decide later whether any of it is wanted.
- **Report:** the team writes the report wording (course rule). Numbers can be taken from `phase2/new/cross-day/out/` and this log.
