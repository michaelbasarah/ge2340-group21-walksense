# Routing: A* on one graph vs an LLM given a text floor plan

*Internal team notes, not report text (course rule: an LLM may only polish our own writing). Every number is in `out/results.json`, `out/astar_check.json`, `out/results_table.csv` or `graph.json`.*

Proposal objective: the building is a graph (nodes = checkpoints, lifts/stairs, escalators, exits; edges carry walking time); A* finds the fastest route; compare it with an LLM that gets a text description of the floor plan ("may invent corridors").

## Files

| file | what |
|---|---|
| `build_graph.py` -> `graph.json` | the one routing graph: 26 places from `graph-v2`, 34 edges, each edge with metres, seconds and where the number came from |
| `route.py` | A*, Dijkstra, turn-by-turn instructions, `route(start, goal) -> (path, metres, seconds, instructions)` on graph.json as it is (used by the checks below); route planner for the app: `plan(start, goal, mode)` and `nearest_toilet(start, mode, gender)` (section "Route planner"); standard library only |
| `check_astar.py` -> `out/astar_check.json` | A* vs Dijkstra on every ordered pair, heuristic checks, walking-speed sensitivity |
| `test_route.py` | 13 unit tests (`python -m unittest test_route` inside this folder): the 4 original + 9 for the planner |
| `python route.py samples` -> `out/planner_samples.json` | planner examples in both modes, connector costs, which connector the cross-floor pairs use, nearest toilet for every mode x gender from 8 starts |
| `llm_baseline.py` -> `out/llm_cache/*.json` | text floor plan from the graph, 50 pairs x 3 conditions = 150 calls of `claude -p --model haiku`; every raw answer cached with prompt, model, date, CLI version, latency |
| `evaluate.py` -> `out/results.json`, `results_table.csv`, `llm_answers.csv`, `routing_results.png` | scoring |

Rerun: `python build_graph.py; python check_astar.py; python llm_baseline.py run` (only calls missing cache files, 4 in parallel); `python evaluate.py`. Run from this folder.

## Graph and edge lengths

Cost = seconds. Same-floor edge: metres / 1.3 m/s (speed given for this task). Lengths, in priority order: **measured** (pin-to-pin metres in `phase2/map/edges_floor5.csv`), **steps** (23-Nov median step count x 0.54 m, the median 23-Nov stride from `tracking/out/pdr_summary.json`; not surveyed), **guess**. Escalators are one-way (5F down escalator -> 4F down escalator, 4F up escalator -> 5F up escalator), as in `map-ui/ROUTING.md`. Lift/stairs both ways.

Edge counts (`graph.json`): 8 measured, 23 steps, 3 guess. Notes:

- graph-v2 merged `sr8..sr11` into `sr9` and kept the boundary distances (8.0 m, 7.1 m). Here `y5302-sr9` = 13.9 m (8.0 + 2.9 + 3.0, measured legs through the study rooms) and `sr9-y5202` = 10.6 m (3.5 + 7.1). `viz/floor5_map.html` uses straight lines instead (13.6, 10.4).
- Where both a map distance and a step count exist, m/step is stored as `m_per_step_check` on the edge: 1.59 (canteen-exit_5, 7 steps for 11.1 m, a likely undercount), 0.45, 0.61, 0.56, 0.55, 0.72. The "steps" edges inherit that spread.

**Guesses and unverified values the team must confirm**

| edge | value | status |
|---|---|---|
| `escalator_down` -> `escalator_down_4F` (one way) | 20 s ride | GUESS: no escalator ride was ever timed |
| `escalator_up_4F` -> `escalator_up` (one way) | 20 s ride | GUESS: same |
| `exit_10` - `escalator_up` | 4.9 m | GUESS: straight line between the two schematic positions (walk ACC11 has no usable step count, no map distance) |
| `lift_stairs` <-> `lift_stairs_4F` | 30.0 s | timed once on the stairs, 5F -> 4F only (ACC23); 4F -> 5F assumed the same; the lift is not timed; 28.6 m = 53 steps x 0.54 |
| all 23 "steps" edges (every 4F edge, plus the 5F edges around the escalators, disabled toilet, lift/stairs, Y5-401, Y5-302 back door) | see `graph.json` | steps x 0.54 m, not surveyed; floor-4 coordinates are schematic, there are no floor-4 Google pins yet |
| walking speed | 1.3 m/s | given for this task; the team's own sensor walks are slower (0.54 m x 1.55 steps/s from `pdr_summary.json` = about 0.84 m/s) |

Walking-speed sensitivity (`out/astar_check.json`): with 0.84 or 1.0 m/s, 12 of 650 ordered pairs get a different fastest path than at 1.3 m/s (the trade-off between walking and the 20 s escalator / 30 s stairs times moves); at 1.5 m/s, 2 pairs.

## A*

Heuristic: straight-line distance on the same floor / speed, with the coordinates shrunk per floor so that no edge is shorter than its straight line (factor 0.8506 on floor 5, 0.6543 on floor 4: the schematic coordinates are not to scale); for a goal on the other floor, the cheapest transfer edge is added (distance to its start + ride time + distance from its end to the goal). Checks (`out/astar_check.json`): all 650 ordered pairs give the same cost as Dijkstra (max difference 0.0 s); admissible for every pair and consistent on every edge; mean nodes expanded 7.54 (A*) vs 14.0 (Dijkstra).

Instructions look like: `Walk to Down escalator (5F) (about 8 m, 6 s).`, `Take the escalator down to floor 4 (about 20 s).`, `Turn left at <place>, then walk to ...`. Left/right comes from node coordinates (x east, y north as drawn in `viz/floor5_map.html`); only 5F nodes with `xy_source = floor5_metres` are surveyed, the rest are schematic, so treat turns as unconfirmed.

## LLM baseline

`claude -p --model haiku` (answering model `claude-haiku-5-5`, Claude Code 2.1.332, 25 Nov 2026), run from an empty temporary folder with `--tools ""`, `--setting-sources ""`, a one-line system prompt, no session saved. One answer per prompt (the CLI has no temperature switch); no repeats. 50 ordered pairs, fixed by seed 2340 and a minimum of 2 hops: 20 within 5F, 8 within 4F, 11 5F -> 4F, 11 4F -> 5F. Answer = JSON list of place IDs.

Three conditions on the same pairs: **dist** = floor plan in words (every place with ID/name/floor, then for each place what you can reach in one step, with metres and escalator/stairs seconds, plus the speed); **adj** = the same plan with no numbers; **names** = only the list of places, "no list of corridors is available" (shows what it makes up). Prompts are in the cache files (`prompt` field).

Scoring (`evaluate.py`): a hop is bad if an ID does not exist, if there is no directed edge (an escalator against its direction counts), "success" = no bad hop, starts at the start, ends at the goal. Cost ratio = travel time of the answer / A* time, on successful answers only. Invented-edge rate = bad hops / all hops.

| method | n | success (valid, reaches goal) | fastest route | cost ratio, successful (mean / median / max) | bad hops / hops | answers with a bad hop | latency median / mean |
|---|---|---|---|---|---|---|---|
| A* | 50 | 50 | 50 (100%) | 1.0 | 0 | 0 | 0.0155 ms per query |
| LLM + distances | 50 | 50 (100%) | 49 (98%) | 1.0018 / 1.0 / 1.0914 | 0 / 203 | 0 | 7.04 s / 7.79 s |
| LLM + adjacency only | 50 | 50 (100%) | 41 (82%) | 1.0198 / 1.0 / 1.5756 | 0 / 204 | 0 | 6.56 s / 6.39 s |
| LLM + places only | 50 | 2 (4%) | 2 (4%) | 1.0 / 1.0 / 1.0 (n = 2) | 59 / 93 (63.4%) | 47 | 6.83 s / 6.94 s |

95% Wilson intervals (50 answers): success with distances 0.929 to 1.0; fastest with distances 0.895 to 0.996; fastest adjacency-only 0.692 to 0.902. Latency includes about 3 to 4 s of CLI start-up and runs 4 at a time; A* is 0.0155 ms per query (`astar_check.json`). Cost of the 150 calls: about 0.10 USD (CLI-reported).

What this does and does not say: given a correct text plan of this small graph (26 places, one screen of text), Haiku does not invent corridors and is almost always optimal when it has distances; it loses time when it has only adjacency (9 of 50 not fastest, one 1.58x); without any corridor list it invents them (59 of 93 hops, 47 of 50 answers). So "may invent corridors" holds only when the plan is missing or incomplete. The LLM is about 5 orders of magnitude slower per answer (seconds vs microseconds), is not guaranteed optimal, and its optimality here depends on the distances in the prompt, which come from the same graph (including the guessed edges).

### LLM failure examples (`out/results.json`, `out/llm_answers.csv`, raw text in `out/llm_cache/`)

- places only, `lt1a` -> `y4502`: `lt1a > lt1b > lift_stairs_4F > y4502`; `lt1b>lift_stairs_4F` and `lift_stairs_4F>y4502` are not corridors.
- places only, `escalator_down_4F` -> `exit_10_4F`: `escalator_down_4F > exit_10_4F` (a direct hop that does not exist).
- places only, `escalator_up_4F` -> `lt1a`: an empty list `[]`.
- adjacency only, `lift_stairs` -> `escalator_up_4F`: valid but takes the stairs and walks the 4F loop (64.85 s), 1.5756 x the fastest (41.16 s: walk on 5F to the down escalator and ride it).
- distances, `y5302_back` -> `lt1a`: valid but goes `lift_stairs > lift_stairs_4F > ... > entrance_exit` instead of the fastest route, 1.0914 x; the same answer in adjacency only.
- No condition with a plan produced a wrong-direction escalator or an unknown ID.

## Route planner (used by the upload app, entry 78)

`plan(start, goal, mode)` and `nearest_toilet(start, mode, gender)` in `route.py`. `route()`, `check_astar.py`, `evaluate.py` and `llm_baseline.py` still use graph.json exactly as before (`Graph(profile=None)`), so the A* checks and the LLM comparison above are unchanged.

**Cost.** Seconds, as above: a walked corridor costs metres / 1.3 m/s, so on one floor the fastest route is also the shortest. Every graph edge already has a length (8 measured, 23 steps x 0.54 m, 3 guesses); nothing had to be derived from `floorplan.json`. "On foot" metres in the app = walked corridors + the stairs flight (28.6 m); lift and escalator rides count 0 m.

**Connectors.** graph.json has one `lift_stairs` edge between the two lift landings (lift and stairs side by side). The planner splits it into two parallel edges between the same landings, both directions, and keeps the escalators one way:

| connector | where | cost | status |
|---|---|---|---|
| stairs | `lift_stairs` <-> `lift_stairs_4F` | 30.0 s, 28.6 m | timed once 5F -> 4F (ACC23); 4F -> 5F assumed the same |
| lift | same landings | 42.0 s = 30 s wait + 12 s ride (one floor) | GUESS (`LIFT_WAIT_S`, `LIFT_RIDE_S` in `route.py`); nobody timed the lift |
| escalator down | `escalator_down` -> `escalator_down_4F` only | 20 s | GUESS (graph.json) |
| escalator up | `escalator_up_4F` -> `escalator_up` only | 20 s | GUESS (graph.json) |

Between two nodes only the cheapest edge the mode allows is searched (Dijkstra on a multigraph = Dijkstra on its cheapest parallel edges); the instructions still know the other one ("Take the stairs down to 4F (about 30 s); the lift is next to them."). With these numbers Standard never picks the lift (stairs 30 s < lift 42 s at the same landing); the lift would win in Standard only if the wait were under 18 s. Over all 336 ordered cross-floor pairs (`out/planner_samples.json`): Standard uses the escalator for 251 and the stairs for 85; Step-free uses the lift for all 336. Standard costs equal the old `route()` costs for every pair (test).

**Modes.** `standard` = walk + stairs + lift + escalator; `accessible` ("Disabled" in the app since entry 93, "Step-free" before) = walk + lift. Wheelchair speed is not modelled (same 1.3 m/s); we do not know whether any corridor has a step.

**Examples** (`out/planner_samples.json`):

| from -> to | Standard | Disabled (`accessible`) |
|---|---|---|
| Y5-302 -> Female toilet (5F, "B -> C -> D -> E") | 35.2 m, 27.1 s: Y5-302 -> study rooms 13.9 m -> Y5-202 10.6 m -> Female toilet 10.7 m (all measured) | same |
| Canteen -> LT1a | 36.6 m, 48.2 s, down escalator | 65.0 m, 92.0 s, lift |
| Y5-302 -> LT2B | 28.2 m, 41.7 s, escalator | 57.8 m, 86.5 s, lift |
| LT1a -> Canteen | 28.0 m, 41.5 s, up escalator | 65.0 m, 92.0 s, lift |
| 5F lift landing -> 4F lift landing | 28.6 m, 30.0 s, stairs | 0.0 m, 42.0 s, lift |
| 5F up escalator -> 4F down escalator | 10.3 m, 27.9 s (walk to the down escalator first) | 65.9 m, 92.7 s, lift |

**Toilets.** `TOILETS` in `route.py`: `male_toilet` (5F, male), `female_toilet` (5F, female), `disabled_toilet` (5F, male, disabled: "Male disabled toilet (5F)"), `disabled_toilet_4F` (4F, mixed, disabled: "Mixed disabled toilet (4F)"); names from `day3/config.json` `place_display` (user, 26 Nov). 4F has no ordinary toilet in our data. Male -> male + mixed; Female -> female + mixed; Step-free -> disabled only. Nearest = lowest route cost; ties by metres. A filter with no toilet returns `choice = None` and a message that lists every toilet with its reason (e.g. Step-free + Female + 5F only: the 5F disabled toilet is male only). Standard + Any or Male can pick a disabled toilet when it is the nearest (from the canteen: male disabled toilet 14.3 m / 11.0 s, male toilet 14.7 m / 11.3 s); the app lists the other fitting toilets under the route.

**Exits (entry 93).** `EXITS` in `route.py`: the 5 exit nodes of graph.json; `emergency` = tagged emergency in `request-matching/destinations.csv`; since entry 94 (user decision 27 Nov) **all 5 exits are tagged emergency** (before: Exit 5 on 5F and 4F only). `nearest_exit(start, mode, emergency=False, floor=None)` ranks them by route cost like `nearest_toilet`. From Y5-202: Exit 10 (by the toilets) 15.1 m / 11.6 s, with or without the emergency filter (entry 93 had Exit 5 37.8 m / 29.1 s for emergency). `route.py samples` writes `exits` (9 starts x 2 modes x emergency yes/no).

**To confirm on site:** the lift position (one lift next to the stairs on each floor, as `lift_stairs` assumes), whether stairs exist at that core on both floors and whether there are other lifts; a timed lift wait and ride; a timed escalator ride; 4F -> 5F on the stairs; whether 4F really has no ordinary toilets; whether the 5F disabled toilet is male only and the 4F one mixed (from the user, 26 Nov); step-free access along every corridor (thresholds, doors).

## Not done / to check

- One sample per prompt, one model, one 25-Nov run; the pair sample is not a random draw of all 650 pairs (seeded, at least 2 hops, fixed strata). No temperature repeats.
- The plan fed to the LLM is machine-written from the graph. A looser human description (or a bigger building) was not tested.
- Edge lengths above must be confirmed; the guessed escalator/stairs times and the 4F step-based lengths can change which route is fastest.
