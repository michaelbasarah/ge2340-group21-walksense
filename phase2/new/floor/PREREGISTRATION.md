# Floor rules: pre-registration (PROCESS-LOG entry 76, provisional number)

Written and committed **before any candidate rule below was scored**. Only the two current rules (R0, R1) had
been run when this file was committed (`baseline.py`, `out/baseline.json`: both reproduce their committed numbers).
What had been looked at before writing this: PROCESS-LOG 72/73, the night README, `upload/out/eval.json`,
`day3/out/results.json` `floor`, and the manifest pressure column (`pressure_hpa`) of the iPhone slot in 24 s1,
25 Nov, 25-Nov night (`round`) and 26 Nov (Tian). No magnetic floor vote, no candidate tracker and no masked run
had been computed.

## Data and units

- Sessions (day-3 ids): tuning = `23nov`, `24s1`, `24s2`, `25nov`; held-out = `25night` (Dicta ip18 + Chris a56),
  `25night_tian` (ip16), `26tian` (ip16), `25spots` (ip16 + s24). Parameters are chosen on the tuning sessions only;
  held-out numbers are computed once with the frozen parameters (`out/params.json`).
- Unit = one session x phone slot (iphone, s24, a55, a56), its recordings (stops and walks) in time order, exactly
  as one phone would upload them. 23 Nov has stops only (ip16 pressure median per stop from the day-3 visit table).
- Score per unit: stops with the right floor / stops, and walks with the right floor / walks (the manifest gives every
  walk one floor). Every rule starts on the unit's first true floor (as `walksense.py evaluate` does).
- Pressure exists for iphone (all sessions except 13 of Dicta's 25-night stops and 14 of her walks) and s24
  (24 s1, 24 s2, spots). a55 and a56 have no pressure file in any session.
- Wrong stops are listed per unit (time, place, true floor, shown floor) in `out/scores.json`.

## Current rules (reproduced, not changed)

- **R0 (upload app)**: `walksense.Session.track_floor` on every recording: the edge pressures (median of first/last 3 s)
  are compared with the median of the last 6 readings on this floor; a change of more than 0.40 hPa moves the floor
  (rise = down to 4F, fall = up to 5F); after more than 15 min since the end of the last recording with pressure,
  the reference is emptied and the floor is kept; a recording without pressure keeps the floor and is skipped.
- **R1 (day-3 step tracking)**: `data.track_floor` on the stop medians, threshold = half the median |pressure step|
  at floor changes in the other sessions (`evaluate.floor_eval`); a stop without pressure keeps the floor. Walks show
  the floor of the last stop.

## Candidates

### (a) MAG: magnetic floor vote only
- Features: the day-3 5 s windows of the stop recording (`x_mean, y_mean, z_mean`, `day3/data.py`).
- Model: median imputer + standard scaler + `KNeighborsClassifier(k, weights='distance')`, label = floor.
- Training pool: stop windows of the other sessions (leave the test session out), same device model; if the pool has
  no window of that model, all models. While tuning, the pool is the other **tuning** sessions only; for the held-out
  scores the pool is all other sessions.
- Vote = mean predicted probability over the recording's windows; shown floor = argmax. Walks show the floor of the
  last stop (start floor before the first stop). No pressure is used.
- Grid: k in {5, 15, 25}. Choose the k with the most correct stops summed over every tuning unit; tie -> larger k.

### (b) Transition detection from motion (escalator/lift/stairs signature)
- Data-support test first: a recording can only show a transition if its pressure moves by a floor step inside it.
  For every recording with pressure, |p1 - p0| (edge medians). If **no** recording has |p1 - p0| > 0.40 hPa, no
  labelled floor change happens inside any recording (the rides are between recordings), so there is nothing to
  train or score a motion detector on: (b) is reported as **not testable with this data** and not scored.
- If some recordings pass, they are listed and plotted only; no detector is built in this entry (too few examples).

### (c) Gap handling
- **c1 (re-anchor after a gap, gap length tuned)**: this is what R0 already does (keep the floor, empty the reference,
  re-anchor on the next reading). Scored as R0 with the gap T in {5, 10, 15, 30, 60 min, never}. Choose T by the
  most correct stops summed over the tuning iPhone units, unmasked + masked (below); tie -> 15 min, else larger T.
- **c2 (drift-extrapolated reference, no reset)**: as R0 (0.40 hPa, median of the last 6 readings, readings = edge
  pressures at the recording start and end time), but the reference is never emptied on a gap; instead it is moved
  by the recent drift: slope = least-squares fit of the readings on this floor in the last 30 min before the newest
  one, used only if those readings span at least 10 min, clamped to +-1.0 hPa/h (else 0);
  reference(t) = median(last 6) + slope x (t - median time of the last 6). Fixed parameters, nothing tuned.

### (d) COMB: pressure when present, magnetic vote otherwise, with hysteresis
- Pressure part = R0 unchanged (0.40 hPa, last 6, T = 15 min).
- The magnetic vote of (a) (same model and pool rules) is **consulted** at a stop when (i) the stop has no pressure,
  or (ii) it is one of the first M stops with pressure after a gap of more than T since the last pressure reading
  (the reference may have re-anchored on the wrong floor). A floor change seen by pressure ends (ii).
- A consulted vote counts if its probability >= P and it names the other floor. After H counting votes in a row for
  the same floor, the floor switches and the pressure reference restarts from this recording's readings. A consulted
  confident vote for the current floor resets the count; walks and unconfident votes leave it unchanged.
- Phones without pressure (a55, a56) and **s24** run (d) on the vote alone: the S24 barometer is treated as absent,
  because on 24 s1 (a tuning session) its floor step is -0.014 hPa against a within-stop SD of 0.234 to 0.438 hPa
  (day3 README). R0, R1, c1 and c2 still use the S24 pressure, as the app would.
- Grid: k in {5, 15, 25}, P in {0.5, 0.6, 0.7, 0.8, 0.9}, H in {1, 2}, M in {0, 3}. Choose by the most correct stops
  summed over all tuning units (iphone unmasked, iphone masked, s24, a55, a56); ties -> larger H, then larger P,
  then smaller M, then larger k.

## Masked tuning runs (simulated pressure dropout)
The tuning iPhone units never lose pressure, so a fallback would never fire there. In a masked copy of each tuning
iPhone unit, pressure is set to missing for every recording that starts within +-20 min of t_c = the start of the
first recording on the other floor (25 night: Dicta's dropout was 22:43 to 23:17 around the 23:03 change). Every
rule is reported on both copies; only (c1) and (d) use the masked copies for choosing parameters.

## Decision rule (fixed now)
- iPhone: recommend a candidate over R0 only if, on the held-out iPhone units, it loses **no** stop that R0 gets
  right where pressure is complete (`25night_tian`, `26tian`, `25spots` iphone) and gains stops on `25night` ip18.
- Phones without pressure (a55, a56, s24 as absent): recommend (a) or (d) only if it beats "start floor kept"
  (= R0 on those phones) on the held-out a56 unit **and** on the tuning a55 + a56 + s24 units summed.
- Nothing is wired into the app in this entry.
