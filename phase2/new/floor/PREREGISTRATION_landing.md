# Connector-gated floor rules: pre-registration (PROCESS-LOG entry 78, provisional number)

Written and committed **before any gated rule below was run or scored**. Internal team notes, not report text.

Idea (user, 26 Nov): "for escalator or lift changes, we have the entry and exit points, so detect from there." A floor
change can only happen through a connector (the lift/stairs core or an escalator), so the floor may switch only
right after the walker was at a connector landing, in a direction that connector allows; the next floor evidence
(pressure step or magnetic vote) confirms it. Everywhere else floor evidence is ignored.

## What had been looked at before writing this

- Everything entry 74 looked at, plus its outputs (`out/scores.json`, `out/decision.json`, the frozen parameters
  `out/params.json`). `baseline.py` and `candidates.py` were rerun in this worktree: `out/` unchanged (R0, R1, (a),
  c1, c2, (d) numbers as in entry 74).
- The per-unit place sequences (true place, floor, edge pressures) of every iPhone and a56 unit, printed around each
  labelled floor change. Seen: at every 5F -> 4F change of the 24-Nov-style route the last lift/stairs stop on 5F is
  two stops (6 to 13 min) before the change and the first 4F stop is the lift/stairs landing; the 25-night 4F -> 5F
  change follows the 4F walk `esca_down->esca_up` and lands at `sr9`; on 24 s1 the walk `esca_up->esca_down` (5F,
  16:51) is followed by the 79-min break with the +0.83 hPa weather rise.
- The day-3 leave-one-session-out fused kNN predictions (`day3/out/fused_sample_predictions.csv`,
  `leave_one_session_out`) **at the connector stops only** (true place = lift or escalator). Seen: many connector
  stops are not predicted as a connector at top-1; in particular Dicta's 25-night 5F lift stop (22:50) is predicted
  `disabled_toilet` (top-3 has the two 5F escalators) and her 4F lift landing (23:03) `sr9` (no connector in the
  top-3). So the predicted top-1 gate is expected to miss her first change; this was known when the variants below
  were chosen.
- The 23-Nov walk list (`clean-data/2026-11-23/accelerometer_edges.csv`): walk ACC23 "exit 5 stairs -> exit 5 stairs
  bawah" (18:34:17 to 18:34:47) is the only recording that spans a labelled floor change; 23-Nov walks have no
  barometer file.
- Not computed before this file was committed: any gated rule, any gate open/close statistic, the upload app's
  place guesses used by the `pred_app` gate below.

## Data, units, scoring

Exactly as `PREREGISTRATION.md`: the same recordings table (`floorlib.recordings()`), the same units (session x
phone slot), tuning sessions `23nov`, `24s1`, `24s2`, `25nov`; held-out `25night`, `25night_tian`, `26tian`,
`25spots`; the same masked tuning copies (pressure deleted for every recording starting within +-20 min of the first
floor change); score = stops on the right floor (walks reported in brackets); every rule starts on the unit's true
first floor; S24 pressure treated as absent by the (d)-based rules only (as in (d)).

## Connectors

- Kind from a place name, floor-agnostic: `lift` if the name starts with `lift` (lift_stairs, lift_stairs5,
  lift_stairs_4F); `down` if it starts with `esca` and contains `down`; `up` if it starts with `esca` and contains
  `up`. Every other place is not a connector. (23 Nov `exit_5`/`exit_10` are exits, not lifts.)
- Directions a kind allows from the floor the tracker currently shows: `lift` 5 -> 4 and 4 -> 5; `down` 5 -> 4 only;
  `up` 4 -> 5 only (graph.json: the escalators are one-way). A down escalator seen while the tracker shows 4F, or an
  up escalator while it shows 5F, opens nothing (wrong direction).
- Kind is taken without the floor on purpose: the true place names of the 24-Nov sessions (`lift_stairs5` on 4F)
  and the floor suffix of the graph ids would otherwise leak the true floor into the gate.

## Gate sources (where the "previous place" comes from)

- `true` (upper bound): the true place of every stop, and both endpoints of every walk (`from->to`).
- `pred_d3` (realistic, offline model): stops only; the stop's top-1 in the day-3 leave-one-session-out fused kNN
  (`day3/out/fused_sample_predictions.csv`, scheme `leave_one_session_out`, matched on the window key). Fused uses the
  barometer group too; in the masked copies the prediction is left as computed (with pressure), stated as a limit.
- `pred_app` (realistic, what the app can do live): stops only; top-1 of the upload app's own place model
  (`walksense.PlaceModel`, `xyz`, trained on the other upload-app sessions' stops of the same phone model, as
  `walksense.evaluate` `same_model`), asked among the places of the floor the tracker shows **before** this recording
  (exactly what the app can compute at that moment). Available for the six upload-app sessions (24 s1, 24 s2, 25 Nov,
  25 night, 25 night Tian, 26 Tian) and for 25 spots (trained on all six, read with `walksense.read_folder`); not for
  23 Nov (not an app session): there the `pred_app` rules fall back to the ungated rule and 23 Nov is left out of the
  `pred_app` tuning sum. A unit whose phone model has no training stops gets no `pred_app` touches (rule = ungated).

## Gate

A **touch** = a recording j where the source names a connector. The gate is **open at recording i towards floor g**
(g = the other floor) if some touch j <= i (j = i allowed: the arrival landing itself opens it) has a kind that
allows current floor -> g and start(i) - start(j) <= T. Otherwise it is closed.

## Gated rules (e)

- **eR0**: R0 (`walksense.Session.track_floor`, 0.40 hPa vs median of the last 6 edge readings, 15-min reset)
  except that a jump switches the floor only if the gate is open at that recording; with the gate closed the reading
  is added to the reference and the floor is kept (no switch, no reset).
- **eR0n**: as eR0 but without the 15-min reset (the gate replaces it as the guard against weather), jump threshold
  theta.
- **eR1**: R1 (day-3 step tracking on stop medians, threshold from the other sessions) where a step switches only if
  the gate is open at that stop; walks show the floor of the last stop. (Not required, added because R1 is the rule
  that caught 25 night after the gap.)
- **ed**: (d) with its frozen parameters (k = 15, P = 0.7, H = 2, M = 3; `out/params.json`, same vote and pools), where
  both its pressure switch and its vote switch need the gate open at that recording; a confident vote for the other
  floor while the gate is closed is ignored (streak unchanged); a pressure jump while closed is absorbed as in eR0.

Each rule x each source (true, pred_d3, pred_app) is a separate candidate: eR0-true, eR0-pred_d3, eR0-pred_app, ...

## Grid and selection (tuning sessions only, then frozen)

- T in {5, 10, 20, 30, 45, 60} min for every rule; theta in {0.30, 0.40} hPa for eR0n.
- Chosen per rule x source by the most correct stops summed over all tuning units (iphone, iphone masked, s24, a55,
  a56; 23 Nov left out for `pred_app`). Ties: smaller T (stricter gate), then theta = 0.40.
- Frozen values written to `out/landing_params.json`; held-out units scored once.

## Also reported (descriptive, no decision)

- **Transitions table** (`out/transitions.json`): for every labelled floor change of every unit (and the 23-Nov ACC23
  stairs walk): the recordings before and after, the departure touch (last touch on the old floor of a kind that
  allows the change, and how many minutes before the change), whether the first recording on the new floor is a
  landing, the pressure step between the last reading before and the first after (if both exist), per source.
- **Gate statistics** per unit and source: number of touches, touches followed by a real change within T (frozen)
  and touches not followed by one, and the share of real changes that had an open gate.
- **Within-walk check**: walks that start or end at a connector landing whose name says the other floor (24-Nov-style
  `lift_stairs5` on 4F, `esca_down`/`esca_up` on 4F), whether pressure across the consecutive recordings brackets a
  floor step.

## Decision rule (fixed now)

1. Same as `PREREGISTRATION.md`, per candidate: recommend a candidate over R0 for the iPhone only if, on the held-out
   iPhone units with complete pressure (`25night_tian`, `26tian`, `25spots` iphone), it loses **no** stop that R0 gets
   right, and it gains stops on `25night` ip18. Phones without pressure: (ed) only if it beats "start floor kept" on
   held-out `25night` a56 **and** on the tuning a55 + a56 + s24 units summed.
2. **App change** (`upload/walksense.py`, `live.py`): only a `pred_app` candidate can be wired, because only it uses
   what the app has live. Wire it only if it passes 1 **and** loses no stop that R0 gets right on **any** held-out
   unit (all held-out units, all phones). If both eR0-pred_app and eR0n-pred_app pass, take the one with more correct
   held-out iPhone stops; tie -> eR0 (closer to the current rule). If only ed-pred_app passes, it is reported but not
   wired here (the app has no magnetic floor vote; porting the day-3 vote is a team decision). The old rule stays
   selectable behind a constant.
3. The true-gate rows are an upper bound only and never a reason to change the app.
