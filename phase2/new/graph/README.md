# Circles-on-lines graph (floors 5 and 4)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Each checkpoint is a circle (node); each walkable connection is a line (edge). `nodes.csv` is a hand-edited input. `edges.csv` is built from the 23-Nov walks by `build_graph.py` (run `python phase2/new/tracking/pdr.py` first; or use `phase2/new/tracking/run_all.sh`).

## nodes.csv

| column | meaning |
|---|---|
| `node_id` | the place ID used in `../cross-day/labels_23nov_confirmed.csv` (31 real places), or `v_<a>__<b>` for a display-only midpoint |
| `floor` | 5 or 4 |
| `x`, `y` | display position in metres-like units, two panels side by side (floor 4 is shifted +45 in x). `xy_source = floor5_metres` means the real floor-5 metre coordinates from `phase2/map/coordinates_meters.csv`; `schematic` means placed by route order and step counts (subway-map style, not surveyed); `midpoint` = the middle of its edge |
| `kind` | room / toilet / exit / lift / escalator / stairs (`virtual` for midpoints) |
| `area` | the AREA id (see below). Empty for virtual midpoints |
| `virtual` | 1 = display-only midpoint on a long edge: no fingerprint data, never a tracker answer |
| `on_edge` | for virtual midpoints, the edge it sits on (`a|b`) |

Map-name mapping for the 11 floor-5 coordinates (same as `crossday.py` `MAP_NAMES`): "Exit 5 (emergency exit)" = `exit_5`, "Exit by bathroom (emergency)" = `exit_10`, "Canteen (entrance)" = `canteen`, Y5-302 = `y5302` (front door), Y5-202 = `y5202`, Study Room 8 to 11 = `sr8` to `sr11`, plus the two toilets.

## Areas: pre-registered on 24 Nov, before any tracker accuracy was computed

Accuracy is scored two ways: the exact checkpoint, and the right AREA (a group of neighbouring checkpoints; people only need the area because they can see the rooms around them). The area column was fixed and committed on its own, before the tracker or any accuracy number existed. The only data looked at to make it were the floor-5 metre coordinates and the step counts per walk (from `../tracking/pdr.py`, committed straight after this file; steps are not an accuracy result).

**Grouping rule**
1. An area is on one floor and connected through graph edges inside it.
2. Where floor-5 metre coordinates exist: every member with coordinates is within 6 m of the centroid of those members ("about 5 to 6 m from the area's middle").
3. A member without coordinates is at most 20 detected steps (about 10 m) from another member over a direct walk (23-Nov count; walks with big sampling gaps, ACC06 and ACC11, not used).
4. The longest shortest walked path between two members of an area is at most 36 steps (about 18 m end to end, i.e. about 9 m either side of the middle).
5. If a checkpoint could join more than one area, it goes where the area stays tighter (smaller radius or shorter step span).
6. Target about 8 to 10 areas. The rule gave 11, including 3 single-checkpoint areas (`y5302`, `y5202`, `lt1b`) that rule 2 or 4 would not let merge. In a single-checkpoint area, "area correct" = "exact correct".

**The 11 areas**

| area | floor | checkpoints | why |
|---|---|---|---|
| `a5_exit5_corner` | 5 | exit_5, male_toilet, disabled_toilet, lift_5, exit_5_stairs | exit_5 and male_toilet 3.6 m apart; disabled toilet 6 steps from exit 5; lift 15 steps from the disabled toilet; stairs 2 steps from the lift. Longest path 31 steps |
| `a5_canteen_front` | 5 | canteen, escalator_up, escalator_down | both escalator tops 15 steps from the canteen. escalator_down is 14 steps from exit 5 but joining the exit-5 corner would make that corner 37 steps long (rule 4) |
| `a5_exit10_toilet` | 5 | female_toilet, exit_10 | 4.4 m apart (radius 2.2 m). exit_10 could also pair with the canteen (radius 5.8 m) but this is tighter (rule 5) |
| `a5_study_rooms` | 5 | sr11, sr10, sr9, sr8 | every room within 4.9 m of the middle |
| `a5_y5302_front` | 5 | y5302 | adding it to exit_5 + male_toilet puts it 8.9 m from the new middle; adding it to the study rooms puts it 9.8 m away (rule 2) |
| `a5_y5202` | 5 | y5202 | would be 9.4 m from the middle with the study rooms, 8.6 m with the toilet/exit 10 pair (rule 2) |
| `a5_y5401_y5302back` | 5 | y5401, y5302_back | 11 steps apart. y5401 is 19 steps from the stairs, but joining the exit-5 corner breaks rule 4 |
| `a4_exit5_corner` | 4 | exit_5_stairs_4F, lift_5_4F, disabled_toilet_4F, exit_5_4F, lt2a | same corner as floor 5 (4, 15, 6 steps); LT2A door 8 steps from exit 5. Longest path 33 steps |
| `a4_escalators` | 4 | lt2b, escalator_down_4F, y4502, escalator_up_4F | LT2B 10 steps from the down escalator; escalators 16 steps apart; Y4502 18 steps from each. Longest path 28 steps (LT2B to Y4502) |
| `a4_exit10_entrance` | 4 | lt1a, exit_10_4F, entrance_exit | LT1A 11 steps from exit 10; entrance 20 steps from exit 10. Longest path 31 steps |
| `a4_lt1b` | 4 | lt1b | 11 steps from escalator_up_4F, but adding it to `a4_escalators` makes that 37 steps (rule 4); 26 steps from LT1A (rule 3) |

Floor-4 areas are bigger than the floor-5 ones because floor 4 has no metre coordinates, only steps. Floor-4 Google Maps pins (day-3 checklist) would let rule 2 apply there too.

**Within 5 m** is reported only where floor-5 metre coordinates exist (the 11 `floor5_metres` checkpoints).

## Virtual midpoints

Edges of at least 10 m (floor-5 map) or at least 20 steps get one display-only midpoint (`virtual = 1`) so the UI can light the line in two halves. They have no fingerprint data and the tracker never answers them. The stairs walk (53 steps) is a floor change and has none.

## edges.csv (built by build_graph.py)

| column | meaning |
|---|---|
| `from`, `to` | node IDs (undirected; `from` is the walk's direction on 23 Nov) |
| `floor_change` | 1 if the edge joins floor 5 and floor 4 |
| `distance_m` | floor-5 map distance (`phase2/map/edges_floor5.csv`), empty elsewhere |
| `median_steps` | detected steps on the 23-Nov walk(s) of this edge (`../tracking/out/pdr_walks_23nov.csv`); empty if the only walk had sampling gaps (ACC06 sr10-sr9, ACC11 exit_10-escalator_up) or there is no walk |
| `n_walks` | number of 23-Nov walks on this edge |
| `source` | `walk_23nov`, `map_floor5`, `escalator_17nov` |
| `walks_23nov`, `median_steps_17nov`, `walks_17nov` | the walk IDs, and the 17-Nov steps where that day walked the same edge |
| `long_edge` | at least 10 m or 20 steps (gets a virtual midpoint in `nodes.csv`) |

How the edges were made:
- **Every 23-Nov walk is an edge** (37 walks, each matched by time to the stop before and after it). Every walk turned out to be a different edge, so `n_walks` is 1 everywhere.
- **All 11 floor-5 map edges** were also walked on 23 Nov, so they only add `distance_m`.
- **Floor changes:** the stairs walk `exit_5_stairs` to `exit_5_stairs_4F` (ACC23, 53 steps), and the two escalators (`escalator_down` to `escalator_down_4F`, `escalator_up_4F` to `escalator_up`). Nobody rode an escalator on 23 Nov; the 17-Nov session has back-to-back stops at the top and bottom landings (BM12 to BM13 and BM23 to BM24, no walk file, one-floor pressure jump), which is the data support. **No lift ride was recorded on either day, so `lift_5` and `lift_5_4F` are not joined.**
- **Not edges:** the 4 moves the collector made without recording a walk (exit_5 to exit_10, escalator_down to escalator_up, canteen to exit_5, exit_5_4F to escalator_down_4F). The second and third are already edges from other walks; the tracker treats each unrecorded move as "stay or move up to 3 lines" with no step information.

Size: floor 5 has 18 nodes and 22 same-floor edges, floor 4 has 13 nodes and 14 same-floor edges, plus 3 floor-change edges (39 edges in all) and 9 virtual midpoints.

`area_check.csv` recomputes the area rule for each area (radius of the members with coordinates, longest step path, worst join). All 11 areas pass. Where a walk's steps are unreliable but the map distance exists (sr10-sr9), metres are converted to steps at the median 23-Nov stride (0.54 m per step, `../tracking/out/pdr_summary.json`).
