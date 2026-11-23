# Cross-day analysis: team summary (24 Nov 2026)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Every number below comes from `out/results.json`, `out/tilt_results.json` or `README.md` in this folder. Visit-level accuracy means: each stop gets one answer (the majority vote of its 2-second windows), and we count how many stops are right.

## a. What we did today

- We relabelled the 23-Nov stops from the collector's own route list (one walk per line, matched to the stop times and walk-file names). All 42 stops are now confirmed, and 23 Nov is our main dataset.
- 4 of the provisional labels were wrong: BM17, BM19, BM40 and BM42. BM14 was also changed (it is exit 5, not exit 10) and the collector confirmed it.
- BM25 is the Y5302 back door (`y5302_back`), a different spot from BM04.
- 4 walks were never recorded (the collector skipped them). That is fine: a stop with no walk after it just can't be named automatically.
- The floor of every stop agrees with the barometer (42/42).
- Full list of changes: `out/label_changes_vs_provisional.csv`.

## b. Results compared with before

**Before:** the pilot's ~94% came from training and testing on the same recording (leakage: neighbouring readings from one visit are almost identical).

**Now**, from the least to the most honest test:

| Test | Result |
|---|---|
| Same visit (first 60% of a stop trains, last 40% tests). Still leaky, kept only for comparison | 98-100% with magnetic x/y/z (42 stops) |
| **23-Nov revisits**: train on the earlier pass, test on the later pass of the same place (9 places, chance 3%) | **7/9 = 78%**, 89% within one neighbour, floor 100% |
| **Cross-day**: train 23 Nov, test 17 Nov (15 shared places, 17 test visits, chance 6.7%) | **18-24%** |

- **Floor from the barometer:** floor tracking by jumps between consecutive stops gets 42/42 (train 17, test 23) and 26/26 (train 23, test 17). A fixed pressure threshold fails (23/42 and 15/26), because the weather pushed the floor-5 pressure up by 0.46 hPa during the 23-Nov session, almost a whole floor step (0.68 hPa).
- **Wi-Fi is nearly useless in this data.** The WiGLE CSV only logs an access point when it is new or its signal gets stronger, so most access points show up at just one stop. Wi-Fi scored 0-11% on the revisit test (9 stops). This is a logging limit, not proof that Wi-Fi can't locate.
- **Tilt correction (23-Nov walk endpoints only):** splitting the magnetic field into a part along gravity and a part across it gives 39% (11/28) on a different pass of the same place, against 0% for |B| alone and for raw x/y/z. These are rough 2-second samples at the start and end of walks, so this number is **not comparable** to the stop numbers above.
- **The two iPhones disagree.** Stops used an iPhone17,4 and walks an iPhone19,2. Their magnetic readings at the same 31 places correlate only r = 0.20 (median difference about 4 µT). So stop data and walk data can't be mixed.

**Why cross-day is so much lower than same-day revisits:**
- The phone was held differently. Magnetic x/y/z depends on how the phone is turned, and that is exactly what changes between days.
- The 17-Nov stops were only 30 s long (23 Nov: 60 s), so there is less data per stop.
- The 17-Nov labels are still uncertain. 8 of the 23 place matches rest on route order, not on labels, and we only use the 15 firmest places for the main cross-day number.
- Only 15 places are shared between the two days, so each test visit counts for about 6%.
- Conditions change between days (time of day, people, the weather drift).

Small numbers: 9 test visits (revisit) and 17 (cross-day). Treat everything as a first estimate.

## c. Checklist for day 3, and why

Ideally collect by **Thu 26 Nov** (deadline 30 Nov).

- [ ] **One phone for both stops and walks, the same phone on every day.** Why: the two iPhones disagree (r = 0.20), and we can't check whether the same phone was used on both days.
- [ ] **Accelerometer and gyroscope ON during stops, not only during walks.** Why: stops only logged the barometer and magnetometer, so the phone's tilt at a stop is unknown. With the accelerometer we can do the tilt correction on every stop.
- [ ] **A Wi-Fi logger that saves every scan.** Test WiGLE's database export first, or use a scan-logging app. Check that an access point heard at one stop also appears at the stops next to it. Why: the WiGLE CSV drops repeats.
- [ ] **60-s stops, with the same place IDs as `labels_23nov_confirmed.csv`, always a stop and then a walk.** Why: 30-s stops hurt 17 Nov, and a stop with no walk after it can't be named automatically.
- [ ] **Phone flat, facing the landmark, the same way at every stop.** Why: magnetic x/y/z only works if the phone is held the same way.
- [ ] **A separate test walk on another day, with "I'm here" taps** at each checkpoint (the plan in `WHATS-LEFT-TO-COLLECT.md`). Why: the taps give ground truth for scoring.
- [ ] **Floor-4 map pins** (Google Maps pins, like floor 5). Why: there is no floor-4 map yet, so "within one neighbour" can't use real floor-4 distances.

## d. What we expect after day 3 (expectations to test, NOT results)

- A real different-day number, collected under one consistent protocol. We *expect* it to land much closer to the 78% revisit result than to the 18-24% cross-day result, because the main causes of the low number (different phone handling, 30-s stops, uncertain labels) are things the protocol removes. This may turn out wrong.
- Wi-Fi fingerprints that are usable (if the new logger really saves every scan). Untested.
- Stop fingerprints that are tilt-corrected (if accelerometer data is logged at stops). The 39% tilt result is on walk endpoints only, so we don't yet know how much it helps at stops.

## e. How to rerun

From the repo root (needs `numpy pandas scikit-learn matplotlib`):

```sh
python phase2/cross-day/crossday.py   # about 30 s; writes out/results.json and the figures
python phase2/cross-day/tilt.py       # run after crossday.py; writes the tilt outputs
```

On the first run `crossday.py` rebuilds the gitignored 23-Nov sensor CSVs into `cache/` (the cleaning code is not changed). Outputs are all in `phase2/cross-day/out/`:

- `results.json`, `summary_table.csv`: every experiment and method
- `revisit_check_23nov.csv`, `places.csv`, `label_changes_vs_provisional.csv`
- `tilt_results.json`, `tilt_endpoints.csv`
- figures: `fig_accuracy_overview.png`, `fig_confusion_revisit_23nov.png`, `fig_confusion_cross_day.png`, `fig_pressure_by_stop.png`, `fig_magnetic_17_vs_23.png`, `fig_tilt.png`

To change a label, edit `labels_23nov_confirmed.csv` and rerun. More detail: `README.md` in this folder.

## f. Open questions about 17 Nov (optional)

See `crosswalk_17nov_to_23nov.csv`. The 17-Nov names are generic, so 8 matches rest on route order (`confidence = medium`). If anyone remembers the 17-Nov walk, these would help:

- BM17 and BM19 were labelled "Exit 5 (revisit)" on 17 Nov but were actually on floor 4 (we mapped them to exit_10_4F and exit_5_4F).
- BM01, BM02, BM03, BM08, BM09, BM10: route-order matches (exit_5, male_toilet, y5302, y5202, female_toilet, exit_10). The 17-Nov labels for BM08 to BM10 called them revisits of earlier places, but the 23-Nov route says they are different spots.
- BM26 ("Kantin exit", exit 5 or exit 10 are both next to the canteen) can't be matched, so it is not used.
