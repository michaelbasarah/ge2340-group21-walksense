# Route-aware tracking on the circles-on-lines graph

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Code and numbers only. Every number below comes from `out/tracker_results.json`, `out/pdr_summary.json` or `../graph/`, which the command below writes.

## Run (one command, from the repo root)

```sh
sh phase2/new/tracking/run_all.sh          # about 1 minute; PYTHON=/path/to/python to pick an interpreter
```

Needs `numpy pandas scikit-learn scipy matplotlib`. It runs `pdr.py` (steps and turns), `../graph/build_graph.py` (edges and area check) and `tracker.py` (tracker, snapshot comparison, replay export). If the gitignored 23-Nov sensor CSVs are missing, `pdr.py` rebuilds them through `crossday.py`'s cache, exactly as `crossday.py` does.

## What it does

The map is a graph: each checkpoint is a circle, each walkable connection is a line (`../graph/`). The tracker keeps a probability for every circle and updates it in time order, the way a live app would (it only uses past data):
- **Walking:** detected steps (`pdr.py`) move the probability along the lines. Each possible move (stay, 1 line, 2 lines) is weighted by how well the step count fits that line's expected number of steps.
- **Standing at a stop:** the barometer floor (step tracking from `crossday.py`) and the magnetometer (the |B| + x/y/z window features from `crossday.py`; distance to each place's nearest training windows becomes a probability) confirm the circle.
- **No walk recorded between two stops** (4 times on 23 Nov, the 2 escalator rides on 17 Nov): stay or move up to 3 lines, no step information.
- No compass. The direction arrow in the UI comes from the route (the next circle towards the destination).

Compared on exactly the same stops:
- **Snapshot:** the `crossday.py` classifier (barometer floor, then |B|+xyz kNN, majority vote over the stop), retrained here with the same training stops as the tracker.
- **Emission only:** the tracker's own barometer + magnetic evidence for that stop, without the graph.
- **Tracker on arrival:** the tracker's belief when the stop starts, before any of the stop's data (graph + steps only).

## How it was evaluated

- **23 Nov, leave-one-visit-out (LOVO):** the magnetic model for each stop is trained on the other 41 stops, never on that stop's own recording. The line that a walk is actually on gets no step count from that same walk (leave-one-walk-out: its length comes from the map distance divided by the other walks' stride, or the other walks' typical count).
  Because 22 of the 42 stops are the only visit to their place, **those 22 places have no fingerprint at all when they are tested.** So the 42 stops are also split into "place has another visit in training" (20) and "no fingerprint" (22).
- **Cross-day:** the magnetic model and line lengths come from 23 Nov only; the 17-Nov loop is replayed. Core = 15 high-confidence places (17 visits), extended = + medium-confidence route matches (25 visits). The classifier chooses among all 31 places, so these are not the same as the 15-place `crossday.py` numbers (18 to 24%).
- **Metrics** (per stop visit, at the end of the stop), each with n and a 95% Wilson interval: exact checkpoint; area (the 11 areas pre-registered in commit `dc76ab2`, see `../graph/README.md`); within one neighbour on the graph; true place in the top 3; floor; within 5 m (only stops whose true place has floor-5 metre coordinates, a prediction without coordinates counts as wrong).

## Two versions (v1 failed, v2 is the fix)

- **v1 (parameters fixed before the first run):** magnetic temperature 1.0, weight 0.1 per 2 s window, floor weight 0.95, no re-localisation. It failed in a specific way: once the belief was wrong it could never recover, because every move was limited to 2 or 3 lines and all other circles got (almost) zero.
- **v2:** exactly two changes, chosen from that failure, not by searching over results: 5% of the belief is spread over all circles after every move ("re-localise anywhere"), and the floor weight is 0.99. The replay files come from v2.
- The two emission parameters were also varied (temperature 0.5/1/2 × weight 0.05/0.1/0.2) to show how sensitive the result is. They were not used to pick anything. On 23 Nov all 42 stops, v2 exact accuracy stays between 26% and 33% across that grid (`v2_sensitivity_23nov_all_42_tracker`).

## Numbers

**23 Nov, LOVO, all 42 stops** (exact checkpoint chance about 3%)

| method | exact | area | within one neighbour | top-3 | floor | within 5 m |
|---|---|---|---|---|---|---|
| Tracker v2 | 12/42 = 29% [17–44] | 16/42 = 38% [25–53] | 16/42 = 38% [25–53] | 14/42 = 33% [21–48] | 40/42 = 95% [84–99] | 5/16 = 31% [14–56] |
| Tracker v1 | 11/42 = 26% [15–41] | 17/42 = 40% [27–56] | 14/42 = 33% [21–48] | 14/42 = 33% [21–48] | 40/42 = 95% [84–99] | 6/16 = 38% [18–61] |
| Snapshot (crossday.py kNN) | 15/42 = 36% [23–51] | 19/42 = 45% [31–60] | 22/42 = 52% [38–67] | 20/42 = 48% [33–62] | 42/42 = 100% [92–100] | 8/16 = 50% [28–72] |
| Emission only | 14/42 = 33% [21–48] | 18/42 = 43% [29–58] | 21/42 = 50% [36–64] | 18/42 = 43% [29–58] | 42/42 = 100% [92–100] | 8/16 = 50% [28–72] |
| Tracker on arrival | 2/42 = 5% [1–16] | 11/42 = 26% [15–41] | 13/42 = 31% [19–46] | 11/42 = 26% [15–41] | 39/42 = 93% [81–98] | 2/16 = 12% [4–36] |

Split (v2 tracker vs snapshot, exact): place has another visit in training 12/20 = 60% [39–78] vs 15/20 = 75% [53–89]; no fingerprint 0/22 vs 0/22 (area 2/22 vs 2/22). On the 9 latest revisits (the `crossday.py` main test set) both get 7/9 = 78%, matching `crossday.py`'s 78%.

**Cross-day, train 23 Nov, replay 17 Nov, core places (17 visits)**

| method | exact | area | within one neighbour | top-3 | floor | within 5 m |
|---|---|---|---|---|---|---|
| Tracker v2 | 5/17 = 29% [13–53] | 12/17 = 71% [47–87] | 11/17 = 65% [41–83] | 12/17 = 71% [47–87] | 17/17 = 100% [82–100] | 3/6 = 50% [19–81] |
| Tracker v1 | 6/17 = 35% [17–59] | 12/17 = 71% [47–87] | 12/17 = 71% [47–87] | 11/17 = 65% [41–83] | 17/17 = 100% [82–100] | 4/6 = 67% [30–90] |
| Snapshot (crossday.py kNN) | 2/17 = 12% [3–34] | 7/17 = 41% [22–64] | 8/17 = 47% [26–69] | 9/17 = 53% [31–74] | 17/17 = 100% [82–100] | 1/6 = 17% [3–56] |
| Emission only | 1/17 = 6% [1–27] | 5/17 = 29% [13–53] | 6/17 = 35% [17–59] | 6/17 = 35% [17–59] | 17/17 = 100% [82–100] | 1/6 = 17% [3–56] |
| Tracker on arrival | 4/17 = 24% [10–47] | 8/17 = 47% [26–69] | 11/17 = 65% [41–83] | 9/17 = 53% [31–74] | 14/17 = 82% [59–94] | 2/6 = 33% [10–70] |

Extended (25 visits): tracker v2 exact 10/25 = 40% [23–59], area 17/25 = 68% [48–83]; snapshot exact 4/25 = 16% [6–35], area 9/25 = 36% [20–56].

**Optimistic variant** (v2, line lengths taken from the same walks, i.e. no leave-one-walk-out): 23 Nov all 42 stops exact 14/42 = 33%, area 19/42 = 45%, floor 42/42.

**"Confirmed" frames, 23 Nov v2:** 2000 of the 5082 stop frames reach the 0.6 threshold, but only 660 of those are on the right circle. In this replay, "confirmed" is not yet trustworthy.

## What the numbers say

- **On another day, the graph helps a lot:** area 12/17 vs 7/17 and exact 5 to 6/17 vs 2/17 against the snapshot. The magnetic fingerprint alone is weak across days, and knowing which circles connect (plus the step count) removes most of the wrong answers.
- **On 23 Nov with LOVO, the tracker is not better than the snapshot** (12/42 vs 15/42). Half the stops have no fingerprint when tested, so the magnetometer pulls the tracker to a nearby place that does have one. Then the graph carries that error forward to the next stops. The graph cannot invent a fingerprint.
- **Floor:** the tracker puts 2 stops on the wrong floor on 23 Nov (BM27 and BM28, just after the stairs), in both versions. Under leave-one-walk-out the stairs line has no known length (the only stairs walk is the one being tested), so its 53 steps look far too long and the tracker doubts the floor change. With line lengths from the same walks, the floor is 42/42.
- Steps alone (tracker on arrival) are weak: 2/42 exact on 23 Nov. Steps tell "moving along a line", not which line.

## What is optimistic (read before quoting)

- **The graph comes from the same route.** Every line exists because the collector walked it on 23 Nov, and the 17-Nov loop mostly walks the same lines in the same order. A real user can take lines we never recorded.
- **The transition prior knows the walk order**: a walk is always exactly one recorded line in this data, and the tracker is told a walk happened (it starts from the walk recording). The escalator floor-change lines come from the 17-Nov test day itself (the back-to-back landing stops).
- The 23-Nov replay still uses the same day, phone and person for training and testing (leakage-reduced, not leakage-free). Small n: one visit is 2 to 6 percentage points; most intervals overlap.
- The tracker is started with a uniform belief, but the floor tracking assumes the first stop is on floor 5 (as `crossday.py` does).
- v2's two changes were made after seeing v1's results (both are reported).

## Step counting and turns (pdr.py)

From `out/pdr_summary.json`: 23 Nov, 37 walks, 558 steps, median 1.55 steps/s; 17 Nov, 23 walks, 353 steps, median 1.57 steps/s. Walks ACC06 and ACC11 (23 Nov) and ACC16 (17 Nov) have big sampling gaps, so their steps are marked unreliable and the tracker treats them as "no step information". Stride against the floor-5 map (straight pin-to-pin distances): median 0.54 m per step on 23 Nov (10 walks, 0.32 to 1.59) and 0.46 on 17 Nov (10 walks, 0.29 to 0.77). Turns: the 2 reliable straight study-room walks show no turn; the stairs walk shows a -136 degree turn (-190 in total); 3 of 37 walks have a turn of 45 degrees or more. Other turns can't be checked without a corridor map. Per-walk detail: `out/pdr_walks_23nov.csv`, `out/pdr_walks_17nov.csv`.

## Replay export: the fixed interface for the UI

`out/replay_23nov.json` (v2, 23-Nov LOVO replay, 5874 frames) and `out/replay_17nov.json` (cross-day, 2078 frames, same format, `destination` is null).

```
{"graph": {"nodes": [{"id", "floor", "x", "y", "kind", "zone", "virtual"}],
           "edges": [{"from", "to", "floor_change", "distance_m", "median_steps"}]},
 "destination": "<last node of the walk>",
 "frames": [{"t", "floor", "edge_from", "edge_to", "progress", "node", "confirmed",
             "top3": [[id, prob], ...], "true_node", "steps_total"}],
 "meta": {...}}
```

| key | meaning |
|---|---|
| `graph.nodes[].id` | checkpoint ID (31 real) or `v_<a>__<b>` (9 virtual midpoints) |
| `floor` | 5 or 4 |
| `x`, `y` | display position (floor 4 panel shifted +45 in x); real floor-5 metres where they exist, else schematic |
| `kind` | room / toilet / exit / lift / escalator / stairs / virtual |
| `zone` | the AREA id (pre-registered); null for virtual midpoints |
| `virtual` | true = display-only midpoint, never a tracker answer. Virtual nodes also carry `on_edge: [a, b]` |
| `edges[].floor_change` | true for stairs and escalator lines |
| `distance_m`, `median_steps` | floor-5 map metres, 23-Nov steps; null when unknown |
| `destination` | `escalator_up_4F` (last stop of 23 Nov) |
| `frames[].t` | seconds since the first recording started; 2 frames per second while a stop or walk was recording; t jumps over gaps with no recording (including the 32-minute break) |
| `floor` | barometer floor (step tracking); during a walk, the floor of the last stop |
| `edge_from`, `edge_to`, `progress` | during a walk: the most likely line and how far along it (0 to 1, from steps); null at stops |
| `node` | most likely circle now (during a walk, the nearer end of the line) |
| `confirmed` | true at a stop when the top circle has probability of at least 0.6 (barometer + magnetometer); always false while walking |
| `top3` | the three most likely circles with probabilities |
| `true_node` | the labelled place at stops; null while walking |
| `steps_total` | detected steps since the start |
| `rec` (extra) | the recording the frame comes from (BMxx stop or ACCxx walk) |

## Files

`pdr.py`, `tracker.py`, `run_all.sh`; outputs in `out/`: `tracker_results.json` (everything, both versions), `tracker_visits_23nov.csv` / `tracker_visits_17nov.csv` (per stop, v2; `_v1` files for v1), `replay_*.json`, `pdr_*`.

## Reused code

`crossday.py` (imported, unchanged): sensor loading, 2 s magnetic windows and features, barometer step tracking, the kNN recipe. `phase2/old/positioning-pilot/step_detection.py` (imported, unchanged): the step detector.
