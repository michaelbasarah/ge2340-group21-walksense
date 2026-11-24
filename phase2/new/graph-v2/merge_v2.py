# -*- coding: utf-8 -*-
"""Build the v2 (merged-node) graph from the v1 graph, non-destructively.

v1 lives in ../graph (originals are NEVER modified). This writes a fresh set of
files into this folder (graph-v2/):

  nodes.csv, edges.csv            -- the routing graph with merged nodes
  labels_23nov_merged.csv         -- cross-day classifier labels, study rooms + lift/stairs collapsed
  area_check_v2.csv               -- area membership after the merge (checkpoint lists only)

Merges (decided 24-Nov):
  * study-room cluster  sr8, sr10, sr11 -> sr9   (one place; sr9 is the middle)
  * lift + stairs       lift_5 + exit_5_stairs       -> lift_stairs      (floor 5)
                        lift_5_4F + exit_5_stairs_4F -> lift_stairs_4F   (floor 4)

Node contraction semantics: an edge that becomes a self-loop (both ends inside a
merged node) is dropped; the distance to a merged cluster is the BOUNDARY edge
distance (standard graph node-contraction), not the summed interior length.
"""
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
V1   = os.path.join(HERE, "..", "graph")
XDAY = os.path.join(HERE, "..", "cross-day")

MERGE = {
    "sr8": "sr9", "sr10": "sr9", "sr11": "sr9",
    "lift_5": "lift_stairs", "exit_5_stairs": "lift_stairs",
    "lift_5_4F": "lift_stairs_4F", "exit_5_stairs_4F": "lift_stairs_4F",
}
# new nodes created by a merge (not a surviving original): position = mean of members
NEW_NODES = {
    "lift_stairs":    {"members": ["lift_5", "exit_5_stairs"],       "floor": 5, "area": "a5_exit5_corner"},
    "lift_stairs_4F": {"members": ["lift_5_4F", "exit_5_stairs_4F"], "floor": 4, "area": "a4_exit5_corner"},
}
def canon(nid): return MERGE.get(nid, nid)

def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), csv.DictReader(open(path, encoding="utf-8")).fieldnames

def write(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

# ---- nodes ----
nrows, nfields = read(os.path.join(V1, "nodes.csv"))
pos = {r["node_id"]: (float(r["x"]), float(r["y"])) for r in nrows}
dropped = set(MERGE)                       # ids that disappear into a canonical node
out_nodes = []
for r in nrows:
    nid = r["node_id"]
    if nid in dropped:
        continue
    if r["virtual"] == "1" and r["on_edge"]:
        a, b = r["on_edge"].split("|")
        a2, b2 = canon(a), canon(b)
        if a2 == b2:                        # midpoint of a now-internal edge: drop it
            continue
        r = dict(r)
        r["on_edge"] = a2 + "|" + b2
        r["node_id"] = "v_" + a2 + "__" + b2
    out_nodes.append(r)
# append the two new merged lift/stairs nodes
for nid, spec in NEW_NODES.items():
    xs = [pos[m][0] for m in spec["members"]]; ys = [pos[m][1] for m in spec["members"]]
    out_nodes.append({"node_id": nid, "floor": str(spec["floor"]),
                      "x": f"{sum(xs)/len(xs):.2f}", "y": f"{sum(ys)/len(ys):.2f}",
                      "kind": "lift_stairs", "area": spec["area"], "virtual": "0",
                      "xy_source": "schematic", "on_edge": ""})
write(os.path.join(HERE, "nodes.csv"), nfields, out_nodes)

# ---- edges ----
erows, efields = read(os.path.join(V1, "edges.csv"))
seen = {}
for r in erows:
    a, b = canon(r["from"]), canon(r["to"])
    if a == b:                              # internal to a merged node
        continue
    key = frozenset((a, b))
    r = dict(r); r["from"], r["to"] = a, b
    if key in seen:                         # duplicate after contraction: keep shorter boundary edge
        def dist(x):
            try: return float(x["distance_m"])
            except (ValueError, TypeError): return 1e9
        if dist(r) < dist(seen[key]): seen[key] = r
    else:
        seen[key] = r
write(os.path.join(HERE, "edges.csv"), efields, list(seen.values()))

# ---- classifier labels ----
lrows, lfields = read(os.path.join(XDAY, "labels_23nov_confirmed.csv"))
for r in lrows:
    old = r["label"]; new = canon(old)
    if new != old:
        r["note"] = (r.get("note", "") + f" [v2: merged {old}->{new}]").strip()
        r["label"] = new
write(os.path.join(HERE, "labels_23nov_merged.csv"), lfields, lrows)

# ---- area membership after merge (checkpoint lists only; metrics not recomputed) ----
arows, afields = read(os.path.join(V1, "area_check.csv"))
for r in arows:
    members = [canon(c) for c in r["checkpoints"].split()]
    seenm = []; [seenm.append(m) for m in members if m not in seenm]
    r["checkpoints"] = " ".join(seenm); r["n_checkpoints"] = str(len(seenm))
write(os.path.join(HERE, "area_check_v2.csv"),
      ["area", "floor", "n_checkpoints", "checkpoints"],
      [{k: r[k] for k in ["area", "floor", "n_checkpoints", "checkpoints"]} for r in arows])

print("v2 nodes:", len(out_nodes), "edges:", len(seen), "labels:", len(lrows))
print("study-room labels now:", sorted({r["label"] for r in lrows if r["label"] in ("sr9",) or r["label"].startswith("sr")}))
