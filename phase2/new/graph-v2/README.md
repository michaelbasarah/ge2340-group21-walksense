# graph-v2: merged-node graph (floors 5 and 4)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

This is a **non-destructive** second version of `../graph`. Nothing in `../graph` or
`../cross-day/labels_23nov_confirmed.csv` is edited; this folder holds rebuilt copies with two
places merged, decided on 24 Nov from the collector's hand-drawn maps.

## What changed vs v1

| merge | v1 nodes | v2 node | why |
|---|---|---|---|
| study rooms | `sr8`, `sr9`, `sr10`, `sr11` | **`sr9`** | one place: the four rooms are within ~5 m of each other, so a fingerprint classifier only confuses them. `sr9` (the middle one) is the label. |
| lift + stairs (5F) | `lift_5`, `exit_5_stairs` | **`lift_stairs`** | collected as two stops but used as one place. |
| lift + stairs (4F) | `lift_5_4F`, `exit_5_stairs_4F` | **`lift_stairs_4F`** | same, on floor 4. |

Real places: **31 → 26**. `Y5-202` and `Y5-302` stay separate (they are not part of the study-room cluster).

## Files

- `nodes.csv`, `edges.csv` — same columns as v1. 26 real nodes + 9 virtual midpoints, 34 edges; the graph is connected (every real node reachable from `canteen`).
- `labels_23nov_merged.csv` — `../cross-day/labels_23nov_confirmed.csv` with the `label` column remapped (the `note` records each `old->new`). To score the classifier on merged classes, point `crossday.py` at this file instead of the confirmed one; `crossday.py` itself is left unchanged.
- `area_check_v2.csv` — area membership after the merge (checkpoint lists only; the radius/step metrics are **not** recomputed here — rerun the area tool if those are needed).
- `merge_v2.py` — the script that builds all of the above from v1. Rerun with `python phase2/new/graph-v2/merge_v2.py`.

## Distance semantics (node contraction)

An edge that becomes internal to a merged node (e.g. `sr11–sr10`) is dropped. The distance to a
merged cluster is the **boundary** edge distance, not the summed interior length — so `y5302–sr9`
keeps 8.0 m (the old `y5302–sr11`) and `sr9–y5202` keeps 7.1 m (the old `sr8–y5202`). Google-scaled
distances will replace the placeholders on the escalator/lift edges later.

## Not done here

- `crossday.py` is **not** switched to the merged labels (that would change the team's accuracy numbers); it is offered as a drop-in file for the team to adopt.
- Floor-4 metric coordinates are still schematic (no Google pins yet).
