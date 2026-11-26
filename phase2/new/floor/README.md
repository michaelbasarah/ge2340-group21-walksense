# Floor rules when the barometer is missing (offline study, PROCESS-LOG entry 74)

Internal team notes, not report text. Nothing here is wired into the upload app.

**Question.** The upload app's floor tracker is right at every stop where the iPhone logged pressure, but on the
25-Nov night run it showed 5F at 12 of Dicta's 4F stops (20/32): her iPhone logged no pressure from 22:43 to 23:17,
which is when the group went down, and Chris's a56 never logs pressure. Which fallback rule would have helped,
scored honestly?

**Method.** The candidate rules, their parameter grids, the split and the decision rule were written in
[`PREREGISTRATION.md`](PREREGISTRATION.md) and committed (a884c97) before any candidate was run. Parameters were
chosen on the tuning sessions (23 Nov, 24 s1, 24 s2, 25 Nov) only and frozen (`out/params.json`); the held-out
sessions (25 night, 25 night Tian, 26 Tian, 25 spots) were scored once.

Run (a few seconds; uses the day-3 feature cache, built by `day3/data.py` on first use):

```sh
python phase2/new/floor/baseline.py      # reproduces the two current rules -> out/baseline.json
python phase2/new/floor/candidates.py    # tune, freeze, score, figures -> out/*.json, out/table.csv, out/fig_*.png
```

## 1. The current rules, reproduced from their own code

- **R0, upload app** (`upload/walksense.py` `Session.track_floor`): every recording (stop or walk) gives two
  readings, the median pressure of its first and last 3 s. Each reading is compared with the median of the last 6
  readings on the current floor; more than 0.40 hPa higher = moved down to 4F, more than 0.40 hPa lower = up to 5F
  (then the reference starts again). If more than 15 min passed since the end of the last recording **with
  pressure**, the reference is emptied and the floor is kept. A recording without pressure keeps the floor.
- **R1, day-3 step tracking** (`day3/data.py` `track_floor`, threshold from `day3/evaluate.py` `floor_eval`): stop
  medians only; the floor changes when two consecutive stops with pressure differ by more than half the median floor
  step of the other sessions (0.292 to 0.307 hPa for the iPhone); a stop without pressure keeps the floor.
- `out/baseline.json` `all_match` = true: R0 gives 27/27, 26/26, 26/26, 20/32, 23/23, 25/25 exactly as
  `upload/out/eval.json`, R1 gives every `day3/out/results.json` `floor` number (e.g. 24s1 23/27, 25night 29/32).

Why R0 fails on 25 night (`out/scores.json`, `fig_25night_timeline.png`): the last reading before the dropout is
the 22:41 walk on 5F; the next one is the 23:36 walk on 4F, so the rule sees a gap of about 55 min (not the 19 min
between recordings), keeps 5F and re-anchors on 4F pressure. Even without the reset it would not move: c1 with the
gap rule switched off ("never") also gives 20/32, because the pressure had fallen with the weather and the 4F
reading was less than 0.40 hPa above the 5F reference. R1 compares stop medians with a lower threshold (0.292 hPa)
and catches the step at 23:37, so it misses only the 3 stops without pressure.

## 2. Candidates (as pre-registered)

| id | rule | frozen parameters (`out/params.json`) |
|---|---|---|
| a | magnetic floor vote only: kNN (x/y/z of the 5 s stop windows) trained on the other sessions' stops of the same phone model, floor = argmax of the mean probability | k = 5 |
| b | transition detection from motion | **not testable**, see below |
| c1 | R0 with the gap T tuned | T = never (tuning: 202 stops right with "never", 196 with 60 min, 190 with 5 to 30 min; `out/tuning.json`) |
| c2 | R0 with a drift-extrapolated reference (30-min slope, clamped to 1 hPa/h), never reset | fixed, nothing tuned |
| d | R0 when pressure is present; the magnetic vote is consulted at stops without pressure and at the first M stops after a gap > 15 min; H confident votes in a row for the other floor switch it | k = 15, P = 0.7, H = 2, M = 3 (359 of 401 tuning stops) |

**(b) is not testable with this data** (`out/motion_check.json`, `fig_motion_check.png`): in all 301 iPhone
recordings with pressure, the largest change between the start and the end of one recording is 0.19 hPa, below one
floor step. The escalator, lift and stair rides were never inside a recording (collectors stopped recording between
places), so there is no labelled transition to train or score an accelerometer/gyroscope detector on. (The S24
shows changes up to 6.2 hPa inside recordings, which is its noise, not a floor change.)

## 3. Scores: stops on the right floor (walks in brackets)

From `out/scores.json` / `out/table.csv`. "masked" = a tuning iPhone unit with pressure deleted for every recording
within 20 min of its floor change (simulates Dicta's dropout). a55 and a56 have no barometer: R0, R1, c1 and c2
just keep the start floor there. (d) treats the S24 barometer as absent (pre-registered, it is too noisy).

| unit | handset | pressure recs | R0 | R1 | c1 | c2 | a | d |
|---|---|---|---|---|---|---|---|---|
| 23nov iphone (tuning) | ip16 | 42/42 | 42/42 (0/0) | 42/42 (0/0) | 42/42 (0/0) | 42/42 (0/0) | 36/42 (0/0) | 42/42 (0/0) |
| 23nov iphone masked (tuning) | ip16 | 23/42 | 26/42 (0/0) | 30/42 (0/0) | 30/42 (0/0) | 30/42 (0/0) | 36/42 (0/0) | 41/42 (0/0) |
| 24s1 a55 (tuning) | a55 | 0/55 | 15/27 (15/28) | 15/27 (15/28) | 15/27 (15/28) | 15/27 (15/28) | 21/27 (23/28) | 26/27 (28/28) |
| 24s1 a56 (tuning) | a56 | 0/55 | 15/27 (15/28) | 15/27 (15/28) | 15/27 (15/28) | 15/27 (15/28) | 23/27 (24/28) | 26/27 (27/28) |
| 24s1 iphone (tuning) | ip18 | 55/55 | 27/27 (28/28) | 23/27 (25/28) | 23/27 (24/28) | 23/27 (24/28) | 19/27 (19/28) | 27/27 (28/28) |
| 24s1 iphone masked (tuning) | ip18 | 35/55 | 15/27 (15/28) | 21/27 (22/28) | 21/27 (22/28) | 21/27 (22/28) | 19/27 (19/28) | 22/27 (23/28) |
| 24s1 s24 (tuning) | s24 | 55/55 | 10/27 (13/28) | 13/27 (14/28) | 10/27 (12/28) | 10/27 (12/28) | 16/27 (17/28) | 24/27 (24/28) |
| 24s2 iphone (tuning) | ip16 | 54/54 | 26/26 (28/28) | 26/26 (28/28) | 26/26 (28/28) | 26/26 (28/28) | 17/26 (19/28) | 26/26 (28/28) |
| 24s2 iphone masked (tuning) | ip16 | 31/54 | 14/26 (15/28) | 14/26 (15/28) | 14/26 (15/28) | 14/26 (15/28) | 17/26 (19/28) | 14/26 (15/28) |
| 24s2 s24 (tuning) | s24 | 54/54 | 15/26 (14/28) | 17/26 (18/28) | 15/26 (14/28) | 15/26 (14/28) | 16/26 (15/28) | 20/26 (22/28) |
| 25nov a55 (tuning) | a55 | 0/54 | 14/26 (15/28) | 14/26 (15/28) | 14/26 (15/28) | 14/26 (15/28) | 23/26 (24/28) | 25/26 (27/28) |
| 25nov a56 (tuning) | a56 | 0/53 | 14/26 (15/27) | 14/26 (15/27) | 14/26 (15/27) | 14/26 (15/27) | 16/26 (16/27) | 16/26 (15/27) |
| 25nov iphone (tuning) | ip18 | 54/54 | 26/26 (28/28) | 26/26 (28/28) | 26/26 (28/28) | 26/26 (28/28) | 24/26 (25/28) | 26/26 (28/28) |
| 25nov iphone masked (tuning) | ip18 | 33/54 | 14/26 (15/28) | 20/26 (22/28) | 20/26 (22/28) | 20/26 (22/28) | 24/26 (25/28) | 24/26 (26/28) |
| **25night a56** | a56 | 0/58 | 19/32 (13/26) | 19/32 (13/26) | 19/32 (13/26) | 19/32 (13/26) | 17/32 (12/26) | 19/32 (13/26) |
| **25night iphone** | ip18 | 32/59 | 20/32 (14/27) | 29/32 (24/27) | 20/32 (14/27) | 28/32 (22/27) | 25/32 (22/27) | **30/32 (25/27)** |
| 25night_tian iphone | ip16 | 46/46 | 23/23 (23/23) | 23/23 (23/23) | 23/23 (23/23) | 23/23 (23/23) | 21/23 (20/23) | 23/23 (23/23) |
| 25spots iphone | ip16 | 8/8 | 4/6 (0/2) | 4/6 (0/2) | 4/6 (0/2) | 4/6 (0/2) | 5/6 (2/2) | 5/6 (2/2) |
| 25spots s24 | s24 | 13/13 | 7/13 (0/0) | 8/13 (0/0) | 7/13 (0/0) | 7/13 (0/0) | 9/13 (0/0) | 10/13 (0/0) |
| 26tian iphone | ip16 | 52/52 | 25/25 (27/27) | 25/25 (27/27) | 25/25 (27/27) | 25/25 (27/27) | 24/25 (26/27) | 25/25 (27/27) |

Tuning rows for (a) and (d) are leave-one-session-out inside the tuning sessions (the vote never sees its own
session), but their parameters were chosen on these rows, so they are optimistic. Held-out rows are the honest ones.

## 4. Where each rule fails (wrong stops in `out/scores.json`)

- **R0**: any floor change without pressure, and a long gap at a floor change (25 night 12 stops, 23:03 to 24:05);
  25 spots iPhone: the two 5F spots at 20:22-20:23 after a 2.5 h gap with the floor still at 4F.
- **R1**: weather across a break: 24 s1 18:12 to 18:22 (4 stops, +0.833 hPa during the break, entry 30); stops
  without pressure (25 night 23:03, 23:08, 23:17). Its 25-night success after the 55-min gap is the same bet that
  failed on 24 s1: a pressure step after a long gap is read as a floor change.
- **c1**: tuning picked "never reset", because in the masked runs the floor change is still visible after the
  dropout. It then loses the 4 weather stops of 24 s1 (like R1) and gains nothing on 25 night (the step was below
  0.40 hPa).
- **c2**: the 30-min slope does not follow the 24 s1 weather (same 4 stops wrong); on 25 night it moves to 4F too
  early (22:43 to 22:59, 4 stops), extrapolating the falling evening pressure. Its 28/32 is partly luck.
- **(a)**: the magnetic vote alone is wrong at 1 to 9 stops per iPhone unit even with pressure available (e.g. 24 s2
  ip16 17/26, 26 Tian 24/25); it loses 4 stops that R0 gets right on the complete-pressure held-out units
  (`out/decision.json`).
- **(d)**: 25 night ip18 misses 23:03 and 23:08: the vote (`out/scores.json` `votes_k_d`) said 4F at 22:59 (wrong, still on 5F), 5F at 23:03
  (wrong) and 4F at 23:08 and 23:17, so H = 2 switches at 23:17. With H = 1 the 22:59 vote would have switched too
  early. 24 s2 masked: the ip16 votes at the 4F stops were not confident twice in a row, so no switch (14/26).
- **a56 on 25 night, every rule**: 19/32 at best (= never leaving 5F). The magnetic vote (`votes_k_d`) says 5F at 11 of its 13
  4F stops (the night magnetometer reads about 85 uT off, entry 72), so (d) never switches and (a) is worse (17/32).

## 5. Recommendation (decision rule from the pre-registration, `out/decision.json`)

- **iPhone: (d) passes** (and so do R1 and c2): it loses no stop that R0 gets right on 25 night Tian, 26 Tian and
  25 spots, and gains 10 stops on 25 night ip18 (20 -> 30/32). R1 (+9) and c2 (+8) also pass, but both lose the 4
  weather stops of 24 s1 that R0 and (d) keep. **(d) with k = 15, P = 0.7, H = 2, M = 3** is the candidate to
  propose for the app: it is R0 unchanged whenever pressure is present and continuous, and only asks the magnetometer
  when pressure is missing or right after a long gap.
- **Phones without a barometer (a55, a56; S24 treated as absent): no rule passes.** (d) is far above "keep the start
  floor" on the tuning sessions (137 vs 83 of 159 stops) and on 25 spots S24 (10 vs 7 of 13), but the only held-out
  no-barometer unit, Chris's a56 on 25 night, is unchanged (19 vs 19 of 32) because its magnetometer is off.
  So the gain for no-barometer phones is not shown on held-out data; it needs a held-out session with a healthy
  Android magnetometer.
- (b) cannot be decided: record one take across a floor change (start before stepping on the escalator, stop after)
  if the team wants it tested.

## 6. Limits

- Small n: one held-out unit has a real dropout (25 night ip18); the masked runs are simulations on tuning data.
- The vote uses the day-3 5 s windows with no trimming, not the app's 2 s trimmed windows.
- Every rule starts on the true first floor, as `walksense.py evaluate` does.
- 23 Nov has stops only (no walk pressure), so R0 sees one reading per stop there.
