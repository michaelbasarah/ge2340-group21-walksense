#!/usr/bin/env python3
"""Results pack for the GE2340 Group 21 (WalkSense) report and slides.

INTERNAL TEAM TOOL, not report text. Reads the committed output files of the analysis
(day3, cross-day, tracking, upload, request-matching, clean-data), and writes figures,
tables and two internal notes sheets into results-pack/out/.

Rerun (from the repo root):
    python phase2/new/results-pack/build.py
    python phase2/new/results-pack/build.py --repo-root /path/to/other/checkout

No result number is typed in this file. Every number is read from a source file, goes
into a fact registry together with its source path, the source's last git commit and the
exact test definition, and the tables, figures, numbers.md and timeline.md are all drawn
from that registry. A source that is missing is reported and skipped, not invented.
"""
import argparse
import csv
import datetime as dt
import html
import json
import math
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# ----------------------------------------------------------------------------- config

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--repo-root", help="read the sources from this checkout instead of the one in config.json")
ap.add_argument("--config", default=str(HERE / "config.json"))
ARGS = ap.parse_args()
CFG = json.loads(Path(ARGS.config).read_text())
ROOT = Path(ARGS.repo_root).resolve() if ARGS.repo_root else (Path(ARGS.config).resolve().parent / CFG["repo_root"]).resolve()
MISSING = []  # (what, why)


def P(rel):
    return ROOT / rel


def note_missing(what, why=""):
    MISSING.append((what, why))
    print(f"  MISSING: {what} {why}", file=sys.stderr)


def loadj(rel):
    return json.loads(P(rel).read_text())


def git(*a):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


_commit_cache = {}


def commit_of(rel):
    """Short hash of the last commit that touched this file, plus a flag if it has local changes."""
    if rel in _commit_cache:
        return _commit_cache[rel]
    h = git("log", "-1", "--format=%h", "--", rel)
    dirty = git("status", "--porcelain", "--", rel)
    out = (h or "uncommitted") + (" +local changes" if dirty and h else "")
    _commit_cache[rel] = out
    return out


HEAD = git("rev-parse", "--short", "HEAD") or "unknown"
BRANCH = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"

# ----------------------------------------------------------------------------- style

OI = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
          blue="#0072B2", verm="#D55E00", purple="#CC79A7", grey="#8A8A8A", lgrey="#D9D9D9")
KIND_COLOUR = {"honest": OI["blue"], "partly_leaky": OI["orange"], "leaky": OI["verm"], "descriptive": OI["grey"]}
KIND_LABEL = {"honest": "honest held-out", "partly_leaky": "partly leaky", "leaky": "LEAKY", "descriptive": "descriptive"}
HEAT = LinearSegmentedColormap.from_list("heat", ["#FFFFFF", "#CFE5F3", "#56B4E9", "#0072B2", "#00334F"])

FONT = "DejaVu Sans"
for cand in ("Liberation Sans", "Arial", "Helvetica"):
    if any(f.name == cand for f in font_manager.fontManager.ttflist):
        FONT = cand
        break

SIZES = {
    "slide": dict(figsize=tuple(CFG["slide_size_in"]), base=16, small=13, title=19, lw=2.2, ms=9),
    "report": dict(figsize=(CFG["report_width_in"], 3.2), base=8, small=7, title=8.5, lw=1.0, ms=4),
}


def rc(fmt):
    s = SIZES[fmt]
    return {
        "font.family": FONT, "font.size": s["base"], "axes.titlesize": s["title"], "axes.labelsize": s["base"],
        "xtick.labelsize": s["small"], "ytick.labelsize": s["small"], "legend.fontsize": s["small"],
        "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": s["lw"] * 0.5,
        "svg.fonttype": "path", "figure.dpi": 100, "savefig.dpi": CFG["dpi"], "axes.titleweight": "bold",
        "hatch.linewidth": s["lw"] * 0.8,
    }


# ----------------------------------------------------------------------------- fact registry

class Fact:
    def __init__(self, id, label, k=None, n=None, chance=None, kind="honest", src=(), test="", unit="recordings",
                 value=None, note="", chance_note=""):
        self.id, self.label, self.k, self.n, self.chance = id, label, k, n, chance
        self.kind, self.src, self.test, self.unit = kind, list(src), test, unit
        self.value, self.note, self.chance_note = value, note, chance_note

    @property
    def p(self):
        return None if self.k is None or not self.n else self.k / self.n

    @property
    def ci(self):
        if self.k is None or not self.n:
            return None
        n, k, z = self.n, self.k, 1.96
        ph = k / n
        d = 1 + z * z / n
        c = (ph + z * z / (2 * n)) / d
        h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
        return max(0.0, c - h), min(1.0, c + h)

    def fmt(self):
        if self.value is not None:
            return str(self.value)
        if self.k is None:
            return "n/a"
        return f"{self.k}/{self.n} = {100 * self.p:.1f}%"

    def commit(self):
        return ", ".join(sorted({commit_of(s) for s in self.src})) if self.src else ""


FACTS = OrderedDict()


def add(f):
    FACTS[f.id] = f
    return f


def F(id):
    return FACTS.get(id)


def parse_frac(s):
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(s))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def guard(name, fn, *a, **kw):
    """Run one source reader; a missing file or key is reported and skipped."""
    try:
        return fn(*a, **kw)
    except (FileNotFoundError, KeyError, IndexError, TypeError, ValueError) as e:
        note_missing(name, f"({type(e).__name__}: {e})")
        return None


# ----------------------------------------------------------------------------- readers

SCHEME_TEST = {
    "random_LEAKY": ("LEAKY", "random 5-fold over {win} windows; windows of one recording are in both train and test; illustration only"),
    "by_recording_partly_leaky": ("partly_leaky", "GroupKFold(5) by {unit1}; the other phones of the same physical stop (and its Wi-Fi/floor) may be in training"),
    "grouped_by_stop": ("honest", "GroupKFold(5) by physical stop (no phone of a held-out stop in training)"),
    "leave_one_session_out": ("honest", "leave one session out (train on the other sessions, test the held-out session)"),
}
GROUP_LABEL = {"fused (learned weights)": "fused kNN, learned weights", "equal weights": "fused kNN, equal weights",
               "B only": "|B| only", "xyz only": "|B| x/y/z only", "tilt only": "tilt only (B_vertical, B_horizontal)",
               "wifi only": "Wi-Fi only (S24 scanner)", "baro only": "barometer floor only"}
GROUP_ID = {"fused (learned weights)": "fused", "equal weights": "equal", "B only": "B", "xyz only": "xyz",
            "tilt only": "tilt", "wifi only": "wifi", "baro only": "baro"}


def read_fused(variant, rel_dir):
    rel = f"{rel_dir}/fused_knn.json"
    d = loadj(rel)
    unit = CFG["variant_units"].get(variant, "recordings")
    sm = d["samples"]
    for scheme, sc in d["schemes"].items():
        kind, tdef = SCHEME_TEST[scheme]
        kind = {"LEAKY": "leaky"}.get(kind, kind)
        for g, r in sc["overall"].items():
            n = r["n_recordings_scored"]
            u = "windows" if scheme == "random_LEAKY" else unit
            add(Fact(f"fused.{variant}.{scheme}.{GROUP_ID[g]}", f"{GROUP_LABEL[g]}, {scheme}", r["exact"], n,
                     sc.get("chance_mean"), kind, [rel],
                     tdef.format(win=sm["windows"], unit1=unit.rstrip("s")) + f"; {sm['places']} places, 5 s windows; scored per {u[:-1] if u.endswith('s') else u}; variant '{variant}'", u))
            if "area" in r:
                add(Fact(f"fused.{variant}.{scheme}.{GROUP_ID[g]}.area", f"{GROUP_LABEL[g]} (area), {scheme}", r["area"], n,
                         None, "descriptive", [rel], "area = pre-registered graph-v2 area is correct (looser than exact place)", u))
        if scheme == "leave_one_session_out":
            for fo in sc["folds"]:
                r = fo["fused (learned weights)"]
                add(Fact(f"fused.{variant}.loso.fold.{fo['fold']}", f"fused kNN LOSO, {fo['fold']}", r["exact"], r["n_recordings"],
                         fo.get("chance"), "honest", [rel],
                         f"leave one session out, held-out = {fo['fold']}, weights {r['weights']}, k={r['k']}", unit))
    dm = loadj(f"{rel_dir}/fused_model.json")
    add(Fact(f"fused.{variant}.deployable", "deployable fused weights", value=json.dumps(dm["weights"]) + f", k={dm['k']}",
             kind="descriptive", src=[f"{rel_dir}/fused_model.json"],
             test=f"tuned by leave-one-session-out on all sessions {dm['sessions']}; inner accuracy {dm['loso_inner_acc']}"))


D3_FEATS = ["|B|", "|B| + baro floor", "|B|+xyz", "|B|+xyz + baro floor", "tilt", "tilt + baro floor", "|B|+xyz+tilt + baro floor",
            "Wi-Fi", "Wi-Fi + baro floor", "|B|+xyz+Wi-Fi + baro floor", "Wi-Fi (in-window rows only)"]


def d3id(exp, feat, pre="d3"):
    return f"{pre}.{exp}.{feat}"


def read_day3_results(variant, rel_dir):
    pre = "d3" if variant == PRIMARY else f"d3_{variant}"
    rel = f"{rel_dir}/results.json"
    d = loadj(rel)
    for exp, tests in d["stop_results"].items():
        sp = tests.get("_split", {})
        leaky = exp.startswith("LEAKY")
        for feat, r in tests.items():
            if feat == "_split" or "exact" not in r:
                continue
            tdef = (f"{exp}: " + (f"train {sp['train_recordings']}, test {sp['test_recordings']} recordings, {sp['train_places']} places; " if "train_recordings" in sp else "") + sp.get("note", ""))
            add(Fact(d3id(exp, feat, pre), f"{exp} / {feat}", r["exact"], r["n_recordings"], sp.get("chance"),
                     "leaky" if leaky else "honest", [rel], tdef + "; kNN k=5, 5 s windows, majority per recording"))
            if "area" in r:
                add(Fact(d3id(exp, feat, pre) + ".area", f"{exp} / {feat} (area)", r["area"], r["n_recordings"], None, "descriptive", [rel], "area correct (graph-v2 area)"))
    for name, r in d["walk_endpoint_results"].items():
        for feat in ("|B|", "raw x/y/z", "tilt (Bv,Bh)", "|B|+tilt"):
            if feat in r:
                add(Fact(f"{pre}.walkend.{name}.{feat}", f"walk endpoints {name} / {feat}", r[feat]["exact"], r["n_test_endpoints"], r["chance"], "honest", [rel],
                         f"{name}: 1-NN on first/last 2 s of walks, {r['n_train_endpoints']} train endpoints, {r['n_test_endpoints']} test endpoints, {r['train_places']} places", "endpoints"))
    for key, r in d["floor"].items():
        k, n = parse_frac(r["step_tracking"])
        add(Fact(f"{pre}.floor.{key}.step", f"floor, step tracking, {key}", k, n, 0.5, "honest", [rel],
                 f"barometer step tracking, jump threshold {r['jump_threshold_hpa']} hPa learned on {r['trained_on']}; chance 0.5 is derived (2 floors), not stored in the file", "stops",
                 chance_note="derived: 2 floors"))
        k2, n2 = parse_frac(r["absolute_threshold"])
        add(Fact(f"{pre}.floor.{key}.abs", f"floor, fixed threshold, {key}", k2, n2, 0.5, "honest", [rel],
                 f"fixed absolute threshold {r['absolute_threshold_hpa']} hPa from the other sessions; chance 0.5 derived", "stops", chance_note="derived: 2 floors"))
    for key, r in d["floor_stats"].items():
        add(Fact(f"{pre}.floorstats.{key}.jump", f"largest same-floor consecutive pressure change, {key}", value=f"{r['largest_same_floor_consecutive_change_hpa']} hPa",
                 kind="descriptive", src=[rel], test=f"floor_stats {key}: one floor step {r['floor_step_hpa']} hPa, f5 range {r['f5_range_hpa']} hPa, within-stop sd median {r['within_stop_sd_hpa_median']} hPa, {r['n_stops']} stops"))
    return d


def read_crossday(rel_dir):
    rel = f"{rel_dir}/results.json"
    d = loadj(rel)
    exps = {"revisit_23": "same day 23 Nov, revisit (train on earlier visit, test on later visit)",
            "cross_core": "train 23 Nov, test 17 Nov, core places (high-confidence 17-Nov label matches)",
            "cross_core_reverse_train17_test23": "train 17 Nov, test 23 Nov, core places",
            "cross_extended": "train 23 Nov, test 17 Nov, extended places",
            "block_23": "LEAKY: 23 Nov same visit, first 60% of each stop train, rest test",
            "block_17": "LEAKY: 17 Nov same visit, first 60% of each stop train, rest test"}
    methods = {"magnitude_knn": "|B| kNN", "magnitude_knn_baro_floor": "|B| kNN + baro floor", "magnitude_xyz_knn": "|B|+xyz kNN",
               "magnitude_xyz_knn_baro_floor": "|B|+xyz kNN + baro floor", "rssi_knn": "Wi-Fi RSSI kNN", "rssi_knn_baro_floor": "Wi-Fi RSSI kNN + baro floor"}
    nplaces = d["labels"]["n_places_23nov"]
    for ex, edef in exps.items():
        for mod in ("mag", "wifi"):
            for m, mlabel in methods.items():
                r = d["results"].get(ex, {}).get(mod, {}).get(m)
                if not r:
                    continue
                vp = r.get("visit_predictions", {})
                n = r["n_test_visits"]
                k = sum(1 for v in vp.values() if v["true"] == v["pred"]) if vp else round(r["visit_place_accuracy"] * n)
                chance = (1 / nplaces) if ex.startswith(("revisit", "block_23")) else None
                add(Fact(f"cd.{ex}.{m}", f"cross-day {ex} / {mlabel}", k, n, chance, "leaky" if ex.startswith("block") else "honest", [rel],
                         f"crossday.py v1 places: {edef}; 2 s magnetometer windows (Wi-Fi: 10 s chunks), kNN k=5, one answer per stop visit (majority vote); {nplaces} places on 23 Nov",
                         "stop visits"))
    # chance for the 17<->23 core test is stored in summary_table.csv
    st = pd.read_csv(P(f"{rel_dir}/summary_table.csv"))
    for _, r in st.iterrows():
        f = F(f"cd.{r.experiment}.{r.method}")
        if f is not None and f.chance is None:
            f.chance = float(r.chance)
        if f is not None and f.src and not any("summary_table" in s for s in f.src):
            f.src.append(f"{rel_dir}/summary_table.csv")
    return d


def read_tilt(rel_dir):
    rel = f"{rel_dir}/tilt_results.json"
    d = loadj(rel)
    for name, r in d["revisit_tests"]["leave_one_pass_out"].items():
        add(Fact(f"tilt.lopo.{name}", f"23-Nov walk endpoints, leave one pass out, {name}", round(r["endpoint_accuracy"] * r["n_test_endpoints"]), r["n_test_endpoints"], r["chance"],
                 "honest", [rel], f"{d['n_endpoints']} endpoints over {d['n_places']} places, 1-NN, leave one pass out; same day, same walking phone; features '{name}'", "endpoints"))
    add(Fact("tilt.device_corr", "walk phone vs stop phone, mean |B| per place, correlation", value=f"r = {d['device_check_walk_vs_stop_mean_B']['correlation']}",
             kind="descriptive", src=[rel], test=f"{d['device_check_walk_vs_stop_mean_B']['n_places']} places, median abs difference {d['device_check_walk_vs_stop_mean_B']['median_abs_difference_uT']} uT"))


def read_tracker():
    rel = f"{CFG['tracking_dir']}/tracker_results.json"
    d = loadj(rel)
    v2 = d["variants"]["v2_relocalise_and_firm_floor"]
    sets = {"lovo23": ("all 23-Nov stops, leave one visit out (22 of 42 stops are the only visit of their place and have no fingerprint)", v2["day_23nov_lovo"]["all_42_stops"], 31),
            "x2317": ("train 23 Nov, replay 17 Nov, core 17 visits", v2["cross_day_train23_test17"]["core_high_confidence_17_visits"], 31)}
    for key, (tdef, blk, npl) in sets.items():
        for meth in ("tracker", "snapshot_knn_crossday_recipe", "emission_only_no_graph", "tracker_arrival_before_stop_data"):
            if meth not in blk:
                continue
            for metric in ("exact", "area", "top3", "floor"):
                r = blk[meth][metric]
                add(Fact(f"trk.{key}.{meth}.{metric}", f"tracker v2 {key} / {meth} / {metric}", r["k"], r["n"], (1 / npl) if metric == "exact" else None, "honest", [rel],
                         f"tracking/tracker.py v2 vs snapshot classifier, {tdef}; chance 1/{npl} places is derived", "stop visits"))
    return d


def read_track24():
    rel = f"{CFG['day3_variants'][PRIMARY]}/track24_results.json"
    d = loadj(rel)
    npl = d["n_places"]
    blocks = {"x": ("train 24 s1 (ip18), replay 24 s2 (ip16): DIFFERENT handsets", d["results"]["all_26_stops"]),
              "same": ("fingerprints from 23-Nov ip16 stops, replay 24 s2 (ip16): same handset, different day, line lengths from s1 walks",
                       d["same_handset_variant"]["results"]["all_26_stops"])}
    for key, (tdef, blk) in blocks.items():
        for meth in ("tracker", "snapshot_knn_crossday_recipe", "emission_only_no_graph", "tracker_arrival_before_stop_data"):
            for metric in ("exact", "area", "within_one_neighbour", "top3", "floor"):
                r = blk[meth][metric]
                add(Fact(f"trk24.{key}.{meth}.{metric}", f"tracker 24 Nov {key} / {meth} / {metric}", r["k"], r["n"], (1 / npl) if metric == "exact" else None, "honest", [rel],
                         f"day3/track24.py (tracker v2 unchanged) on graph-v2, {npl} places, {tdef}; chance 1/{npl} derived. Optimistic: every test walk is one recorded line, start/graph from the same route", "stop visits"))


def read_upload():
    rel = f"{CFG['upload_dir']}/eval.json"
    d = loadj(rel)
    for name, r in d["place"].items():
        k, n = parse_frac(r["top1"])
        add(Fact(f"up.{name}.top1", f"upload eval {name} top-1", k, n, r["chance_top1"], "honest", [rel],
                 f"upload/walksense.py PlaceModel: train on one 24-Nov session's stops, test every stop of the other ({r['devices']}); true floor GIVEN so chance is 1/13 per floor, "
                 f"2 s windows, first/last 5 s skipped", "stop visits", chance_note="per-floor model, floor given"))
        k3, n3 = parse_frac(r["top3"])
        add(Fact(f"up.{name}.top3", f"upload eval {name} top-3", k3, n3, None, "descriptive", [rel], "true place is among the 3 best guesses"))
    for key, r in d["floor_tracking"].items():
        k, n = parse_frac(r["stops_correct"])
        add(Fact(f"up.floor.{key}", f"upload floor tracking {key}", k, n, 0.5, "honest", [rel],
                 "median-of-last-6 pressure rule, 0.40 hPa; chance 0.5 derived", "stops", chance_note="derived: 2 floors"))
    rl = f"{CFG['upload_dir']}/live_checks.json"
    lc = loadj(rl)
    for key, r in lc["walking_dot"].items():
        add(Fact(f"up.dot.{key}.first", f"walking dot {key}: right first corridor", r["first_corridor_right"], r["walks"], None, "honest", [rl],
                 "corridors learned from one 24-Nov session, the other session's walks, each started at its TRUE start place (optimistic)", "walks"))
        add(Fact(f"up.dot.{key}.end3m", f"walking dot {key}: end within 3 m", r["end_within_3m"], r["walks"], None, "honest", [rl],
                 "same test; end position on the sketch map within 3 m of the true end", "walks"))
        add(Fact(f"up.dot.{key}.err", f"walking dot {key}: end error median / p90", value=f"{r['end_error_m_median']} m / {r['end_error_m_p90']} m", kind="descriptive", src=[rl],
                 test=f"same test, {r['walks']} walks, map scale {r['m_per_px']} m per pixel"))
    for key, r in lc["live_replay"].items():
        add(Fact(f"up.live.{key}.found", f"live replay {key}: stops found", r["found"], r["n_stops"], None, "honest", [rl],
                 f"a whole session streamed through LiveTracker on its real clock, model from the other iPhone; extra stops {r['extra_stops']}", "stops"))
        add(Fact(f"up.live.{key}.top1", f"live replay {key}: top-1", r["top1"], r["n_stops"], None, "honest", [rl], "same replay, place named after the stop", "stops"))
        add(Fact(f"up.live.{key}.lit", f"live replay {key}: circle lit and right", r["lit_right"], r["lit"], None, "honest", [rl], "circle lit only when top-1 probability >= 0.8; counts right among lit", "lit circles"))
    for k, v in lc["top1_by_standing_time"].items():
        kk, nn = parse_frac(v)
        add(Fact(f"up.standing.{k}", f"top-1 from first N s only, {k}", kk, nn, None, "honest", [rl], "first N seconds of each held-out stop only", "stop visits"))


def read_compare(variant, rel_dir):
    rel = f"{rel_dir}/compare_before_after.csv"
    d = pd.read_csv(P(rel))
    for i, r in d.iterrows():
        add(Fact(f"cmp.{variant}.{i:02d}", r["test"], int(r["after_correct"]), int(r["after_n"]), float(r["after_chance"]), "leaky" if "LEAKY" in r["test"] else ("partly_leaky" if "partly leaky" in r["test"] else "honest"),
                 [rel], f"variant '{variant}' (20 s pieces, exclusions, outliers removed); BEFORE (take level, out/) = {int(r['before_correct'])}/{int(r['before_n'])}", "recordings or pieces"))


def read_upload_split20(rel_dir):
    rel = f"{rel_dir}/upload_eval_split20.json"
    d = loadj(rel)
    for name, r in d["place"].items():
        k, n = parse_frac(r["top1"])
        add(Fact(f"up20.{name}.top1", f"upload eval on 20 s pieces {name} top-1", k, n, r["chance_top1"], "honest", [rel],
                 f"walksense PlaceModel trained on whole takes, tested on kept 20 s pieces ({r['devices']}); floor given", "20 s pieces"))


def read_wifi():
    rel = f"{CFG['day3_variants'][PRIMARY]}/wifi_diagnosis.json"
    d = loadj(rel)
    for s, r in d["inside_one_stop"].items():
        add(Fact(f"wifi.rows_per_bssid.{s}", f"Wi-Fi rows per BSSID inside one stop, median, {s}", value=str(r["rows_per_bssid_inside_one_stop_median"]), kind="descriptive", src=[rel],
                 test=f"WiGLE log, rows assigned in the stop dwell; scanner logged a median of {r['distinct_scan_timestamps_per_60s_stop_median']} distinct scan times per 60 s stop; {r['stop_visits']} stop visits"))
    for lg in d["per_log"]:
        add(Fact(f"wifi.stronger.{lg['session']}.{lg['scanner']}", f"share of repeat rows stronger than all earlier rows, {lg['session']} {lg['scanner']}",
                 value=f"{lg['share_repeats_stronger_than_all_earlier_rows']}", kind="descriptive", src=[rel], test=f"log {lg['log']}: {lg['repeat_rows']} repeat rows of {lg['rows']} rows"))
    return d


def read_variance():
    rel = f"{CFG['day3_variants'][PRIMARY]}/variance_by_place.csv"
    v = pd.read_csv(P(rel))
    v = v[(v.scope == "all places") & (v.order == "session_first")]
    for _, r in v.iterrows():
        for piece in ("within", "rec", "phone", "session", "place"):
            add(Fact(f"var.{r.order}.{r.feature}.{piece}", f"variance share {piece}, {r.feature}, {r.order}", value=f"{100 * r['share_' + piece]:.1f}%", kind="descriptive", src=[rel],
                     test=f"sum of squares of {r.unit_label} over {int(r.n_windows)} windows, {int(r.n_places)} places, {int(r.n_recordings)} recordings, {r.order} nesting; plain SS of a crossed unbalanced design, not a random-effects estimate"))
    return v


def read_pdr():
    rel = f"{CFG['tracking_dir']}/pdr_summary.json"
    d = loadj(rel)
    for day in ("23Nov", "17Nov"):
        r = d[day]
        add(Fact(f"pdr.{day}.steps", f"steps counted, {day}", value=f"{r['steps_total']} steps in {r['walks']} walks ({r['walks_reliable']} reliable), median cadence {r['median_cadence_reliable']} steps/s",
                 kind="descriptive", src=[rel], test="count_steps from phase2/old/positioning-pilot/step_detection.py, unchanged"))
        e = r["floor5_map_edges"]
        add(Fact(f"pdr.{day}.stride", f"stride vs floor-5 map, {day}", value=f"median {e['median_m_per_step']} m/step (range {e['min_m_per_step']} to {e['max_m_per_step']}, {e['n_walks']} walks)",
                 kind="descriptive", src=[rel], test="map distance = straight line between pins, so real strides are a bit longer"))
    tc = d["23Nov"]["turn_checks"]
    add(Fact("pdr.turns", "turn detection checks", value=f"{tc['walks_with_a_turn']} of {d['23Nov']['walks']} walks have a turn of 45 deg or more", kind="descriptive", src=[rel],
             test="only 2 checks have a known expected answer (straight corridor: no turn; stairs: U-turn on landing, not verified on site)"))


def read_pilot():
    rel = CFG["pilot_results"]
    d = loadj(rel)
    add(Fact("pilot.knn", "old pilot, kNN on magnetometer slices (same recording)", round(d["knn_magnetic"]["stop_accuracy"] * d["slices_test"]), d["slices_test"], 1 / d["stops"], "leaky", [rel],
             f"phase2/old/positioning-pilot: {d['slices_total']} 2 s slices of {d['stops']} 17-Nov stops, {d['slices_train']} train / {d['slices_test']} test slices from the SAME recordings. SUPERSEDED, leaky; k is accuracy x n (file stores only the rate {d['knn_magnetic']['stop_accuracy']})",
             "slices", chance_note="derived 1/26"))
    add(Fact("pilot.floor", "old pilot, barometer floor split accuracy", value=f"{d['knn_magnetic']['floor_accuracy']}", kind="leaky", src=[rel], test="same leaky slice split; floor from kNN on magnetometer slices"))


def read_reqmatch():
    rel = CFG["request_matching_results"]
    d = pd.read_csv(P(rel))
    labels = {"keyword": "keyword rules", "embed": "sentence embeddings (MiniLM)", "llm": "LLM (cached Claude answers)",
              "fuzzy_keyword": "keyword then fuzzy alias match", "hybrid": "keyword, fuzzy, then LLM only if neither answers",
              "tokens": "starter token overlap"}
    for m, lab in labels.items():
        if f"{m}_ok" not in d.columns:
            note_missing(f"request matching column {m}_ok in {rel}")
            continue
        ok = d[f"{m}_ok"].astype(str) == "True"
        for sl, mask, what in (("test", d["split"] == "test", "test split (62 queries: easy + agent-drafted hard, fixed before any method ran)"),
                               ("all", d["split"].notna(), "all 128 queries (dev rows were used to tune thresholds)")):
            add(Fact(f"rm.{m}.{sl}", f"request matching, {lab}, {sl}", int(ok[mask].sum()), int(mask.sum()), None, "honest" if sl == "test" else "partly_leaky", [rel],
                     f"{what}; top-1 place ID (or NONE) must match expected; hard queries are agent drafts not yet reviewed by the team; chance not defined", "queries"))


def read_sample_predictions(variant, rel_dir):
    """Per-recording predictions of the learned-weight fused kNN (honest LOSO) for heat maps."""
    for cand in CFG["sample_predictions_candidates"]:
        rel = f"{rel_dir}/{cand}"
        if P(rel).exists():
            df = pd.read_csv(P(rel))
            df = df[df.scheme == "leave_one_session_out"].copy()
            df["hit"] = (df["true"] == df["pred"]).astype(int)
            return df, rel
    note_missing(f"fused_sample_predictions in {rel_dir}")
    return None, None


# ----------------------------------------------------------------------------- run readers

PRIMARY = CFG["primary_variant"]
print(f"results pack: reading sources from {ROOT} (HEAD {HEAD}, branch {BRANCH})")
D3_RESULTS = {}
for var, rel_dir in CFG["day3_variants"].items():
    guard(f"fused_knn.json ({var})", read_fused, var, rel_dir)
for var, rel_dir in CFG["day3_variants"].items():
    D3_RESULTS[var] = guard(f"day3 results.json ({var})", read_day3_results, var, rel_dir)
PRIMARY = CFG["primary_variant"]
CD = guard("cross-day results", read_crossday, CFG["crossday_dir"])
guard("tilt results", read_tilt, CFG["crossday_dir"])
guard("tracker results", read_tracker)
guard("track24 results", read_track24)
guard("upload eval/live checks", read_upload)
for var, rel_dir in CFG["day3_variants"].items():
    if var != PRIMARY:
        guard(f"upload eval on pieces ({var})", read_upload_split20, rel_dir)
        guard(f"compare_before_after ({var})", read_compare, var, rel_dir)
WIFI = guard("wifi diagnosis", read_wifi)
VAR = guard("variance_by_place.csv", read_variance)
guard("pdr summary", read_pdr)
guard("pilot results", read_pilot)
guard("request-matching results", read_reqmatch)
SAMPLES = {}
for var, rel_dir in CFG["day3_variants"].items():
    SAMPLES[var] = read_sample_predictions(var, rel_dir)

# ----------------------------------------------------------------------------- derived facts from per-sample predictions


def derived_from_samples():
    df, rel = SAMPLES[PRIMARY]
    if df is None:
        return
    g = df.groupby("true").hit.agg(["sum", "count"])
    zero = sorted(g.index[g["sum"] == 0])
    add(Fact("derived.never_correct", "places with 0 correct recordings in leave-one-session-out", value=", ".join(zero) if zero else "none", kind="descriptive", src=[rel],
             test=f"fused kNN learned weights, leave one session out, {len(df)} recordings, {len(g)} places; derived by build.py from the per-sample file"))
    tot = df.hit.sum()
    f = F(f"fused.{PRIMARY}.leave_one_session_out.fused")
    ok = f is not None and (f.k == tot and f.n == len(df))
    print(f"  check: per-sample LOSO {tot}/{len(df)} equals fused_knn.json {f.k if f else '?'}/{f.n if f else '?'}: {ok}")
    if not ok:
        note_missing("consistency", "per-sample LOSO count differs from fused_knn.json")


derived_from_samples()

# ----------------------------------------------------------------------------- output helpers


def save(fig, name, fmt):
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"{name}_{fmt}"
    fig.savefig(OUT / f"{stem}.png", dpi=CFG["dpi"], facecolor="white")
    fig.savefig(OUT / f"{stem}.svg", facecolor="white")
    plt.close(fig)
    return stem


FIGURES = []  # (name, title, sources, test text)


def pct_label(f, with_frac=True):
    return f"{100 * f.p:.0f}%" + (f"\n{f.k}/{f.n}" if with_frac else "")


def wrap(s, w):
    import textwrap
    return "\n".join(textwrap.wrap(s, w))


# ----------------------------------------------------------------------------- figures

def fig_honest_vs_leaky(fmt):
    ids = [(f"fused.{PRIMARY}.random_LEAKY.fused", "Random windows\n(LEAKY)"),
           (f"fused.{PRIMARY}.by_recording_partly_leaky.fused", "By recording\n(partly leaky)"),
           (f"fused.{PRIMARY}.grouped_by_stop.fused", "By physical stop\n(honest)"),
           (f"fused.{PRIMARY}.leave_one_session_out.fused", "Leave one\nsession out\n(honest)")]
    items = [(F(i), l) for i, l in ids if F(i)]
    if not items:
        return None
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 3.0)
    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(len(items))
    for xi, (f, lab) in zip(x, items):
        lo, hi = f.ci
        ax.bar(xi, f.p * 100, 0.62, color=KIND_COLOUR[f.kind], hatch="//" if f.kind != "honest" else None, edgecolor="white" if f.kind == "honest" else "#7a2f00", linewidth=0.8)
        ax.errorbar(xi, f.p * 100, yerr=[[f.p * 100 - lo * 100], [hi * 100 - f.p * 100]], color="black", capsize=4, lw=s["lw"] * 0.7)
        ax.text(xi, min(hi * 100 + 2, 103), f"{100 * f.p:.1f}%\n{f.k}/{f.n}", ha="center", va="bottom", fontsize=s["base"], fontweight="bold")
    ch = items[0][0].chance
    if ch:
        ax.axhline(ch * 100, color=OI["black"], ls="--", lw=s["lw"] * 0.7)
        ax.text(len(items) - 0.45, ch * 100 + 1.5, f"chance {ch * 100:.1f}%", ha="right", va="bottom", fontsize=s["small"])
    ax.set_xticks(x, [l for _, l in items])
    ax.set_ylim(0, 118)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("place accuracy (%)")
    ax.set_title("Same fused kNN, four ways to split the data", loc="left")
    fig.tight_layout()
    return fig


def fig_accuracy_vs_chance(fmt):
    spec = [
        ("LEAKY (same recording or same visit in train and test)", None),
        ("pilot.knn", "Pilot kNN, 17 Nov slices"),
        ("cd.block_23.magnitude_xyz_knn_baro_floor", "23 Nov same visit, |B|+xyz+floor"),
        ("d3.LEAKY_same_recording_time_split_24s2_iphone.|B|+xyz", "24 Nov s2 same recording, |B|+xyz"),
        (f"fused.{PRIMARY}.random_LEAKY.fused", "Fused kNN, random windows"),
        ("HONEST (train and test are different visits, sessions or days)", None),
        ("cd.revisit_23.magnitude_xyz_knn_baro_floor", "23 Nov revisit, |B|+xyz+floor"),
        ("cd.cross_core.magnitude_xyz_knn_baro_floor", "23 to 17 Nov, |B|+xyz+floor"),
        (d3id("xsession_24s1_to_24s2_iphone", "|B|+xyz + baro floor"), "24 Nov iPhone s1 to s2 (ip18 to ip16)"),
        (d3id("xsession_24s2_to_24s1_iphone", "|B|+xyz + baro floor"), "24 Nov iPhone s2 to s1 (ip16 to ip18)"),
        (d3id("xsession_24s1_to_24s2_s24", "|B|+xyz + baro floor"), "24 Nov S24 s1 to s2 (same phone)"),
        (d3id("xsession_24s2_to_24s1_s24", "|B|+xyz + baro floor"), "24 Nov S24 s2 to s1 (same phone)"),
        (d3id("xday_23nov_to_24s2_iphone", "|B|+xyz + baro floor"), "23 to 24 Nov s2, same ip16"),
        (d3id("xday_24s2_to_23nov_iphone", "|B|+xyz + baro floor"), "24 Nov s2 to 23 Nov, same ip16"),
        (f"fused.{PRIMARY}.grouped_by_stop.fused", "Fused kNN, by physical stop"),
        (f"fused.{PRIMARY}.leave_one_session_out.fused", "Fused kNN, leave one session out"),
        ("trk24.x.tracker.exact", "HMM tracker 24 Nov s1 to s2"),
    ]
    rows = []
    for sid, lab in spec:
        if lab is None:
            rows.append(("hdr", sid))
        elif F(sid):
            rows.append(("bar", F(sid), lab))
    rows = [r for i, r in enumerate(rows) if r[0] == "bar" or (i + 1 < len(rows) and rows[i + 1][0] == "bar")]
    if not any(r[0] == "bar" for r in rows):
        return None
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 5.6)
    fig, ax = plt.subplots(figsize=figsize)
    y = 0
    ys, labs = [], []
    for r in rows:
        if r[0] == "hdr":
            ax.text(-0.02, -y, r[1], transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=s["small"], fontweight="bold", color="#444444")
            y += 1
            continue
        f, lab = r[1], r[2]
        lo, hi = f.ci
        ax.barh(-y, f.p * 100, 0.7, color=KIND_COLOUR[f.kind], hatch="//" if f.kind == "leaky" else None, edgecolor="#7a2f00" if f.kind == "leaky" else "white", lw=0.6)
        ax.plot([lo * 100, hi * 100], [-y, -y], color="black", lw=s["lw"] * 0.6)
        if f.chance:
            ax.plot([f.chance * 100] * 2, [-y - 0.38, -y + 0.38], color="black", lw=s["lw"] * 1.2)
        ax.text(102, -y, f"{100 * f.p:.0f}%  {f.k}/{f.n}", va="center", ha="left", fontsize=s["small"])
        ys.append(-y)
        labs.append(lab)
        y += 1
    ax.set_yticks(ys, labs)
    ax.set_xlim(0, 125 if fmt == "slide" else 150)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("place accuracy (%); black tick = chance")
    ax.set_ylim(-y + 0.4, 0.8)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.legend(handles=[Patch(facecolor=KIND_COLOUR["leaky"], hatch="//", edgecolor="#7a2f00", label="LEAKY"),
                        Patch(facecolor=KIND_COLOUR["honest"], label="honest held-out")], loc="lower right", frameon=False, ncol=2)
    ax.set_title("Accuracy against chance, every test", loc="left")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def _heat(ax, M, N, rows, cols, s, title=None, show_cols=True):
    """Draw an accuracy heat map; M hits and N totals (rows x cols); grey where N == 0."""
    nr, nc = len(rows), len(cols)
    acc = np.where(N > 0, M / np.maximum(N, 1), np.nan)
    ax.imshow(np.ma.masked_invalid(acc), cmap=HEAT, vmin=0, vmax=1, aspect="auto")
    ax.set_facecolor("#EDEDED")
    for i in range(nr):
        for j in range(nc):
            if N[i, j] == 0:
                ax.text(j, i, "-", ha="center", va="center", color="#9a9a9a", fontsize=s["small"])
            else:
                a = M[i, j] / N[i, j]
                ax.text(j, i, f"{int(M[i, j])}/{int(N[i, j])}", ha="center", va="center", fontsize=s["small"] - (1 if s["base"] > 10 else 0.5),
                        color="white" if a > 0.55 else "black")
    ax.set_xticks(range(nc), cols if show_cols else [])
    ax.set_yticks(range(nr), rows)
    ax.set_xticks(np.arange(-0.5, nc, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, nr, 1), minor=True)
    ax.grid(which="minor", color="#BBBBBB", lw=0.6)
    ax.tick_params(which="both", length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    if title:
        ax.set_title(title, fontsize=s["base"], loc="left")


def _split_floors(df):
    f5 = sorted(df[df.place_floor == 5].true.unique())
    f4 = sorted(df[df.place_floor == 4].true.unique())
    return f5, f4


def _heat_pair(fmt, colkey, collabels, title, name_extra=""):
    df, rel = SAMPLES[PRIMARY]
    if df is None:
        return None
    cols = [c for c in collabels if c in set(df[colkey])]
    if not cols:
        return None
    f5, f4 = _split_floors(df)
    # order places inside each floor by overall accuracy (best first)
    acc = df.groupby("true").hit.mean()
    f5 = sorted(f5, key=lambda p: (-acc[p], p))
    f4 = sorted(f4, key=lambda p: (-acc[p], p))
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 4.9)
    fig, axs = plt.subplots(1, 2, figsize=figsize, gridspec_kw=dict(width_ratios=[len(f5) or 1, len(f4) or 1]) if False else None)
    for ax, places, ttl in ((axs[0], f5, "Floor 5"), (axs[1], f4, "Floor 4")):
        M = np.zeros((len(places), len(cols)))
        N = np.zeros_like(M)
        for i, p in enumerate(places):
            for j, c in enumerate(cols):
                sub = df[(df.true == p) & (df[colkey] == c)]
                M[i, j], N[i, j] = sub.hit.sum(), len(sub)
        _heat(ax, M, N, places, cols, s, ttl)
    fig.suptitle(title, x=0.01, ha="left", fontsize=s["title"], fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94 if fmt == "slide" else 0.95))
    return fig


def fig_per_place_accuracy(fmt):
    df, _ = SAMPLES[PRIMARY]
    if df is None:
        return None
    order = list(dict.fromkeys(CFG_SESSIONS))
    # columns: test session; "all" is added as a pseudo column
    df2 = pd.concat([df, df.assign(session="all")])
    cols = [c for c in order if c in set(df["session"])] + ["all"]
    df_backup = SAMPLES[PRIMARY]
    SAMPLES[PRIMARY] = (df2, df_backup[1])
    try:
        return _heat_pair(fmt, "session", cols, "Place accuracy by held-out session (fused kNN, leave one session out; correct/recordings)")
    finally:
        SAMPLES[PRIMARY] = df_backup


def fig_phone_place(fmt):
    df, _ = SAMPLES[PRIMARY]
    if df is None:
        return None
    df2 = pd.concat([df, df.assign(phone="all")])
    cols = [c for c in CFG["phone_order"] if c in set(df["phone"])] + ["all"]
    df_backup = SAMPLES[PRIMARY]
    SAMPLES[PRIMARY] = (df2, df_backup[1])
    try:
        return _heat_pair(fmt, "phone", cols, "Phone x place (fused kNN, leave one session out; correct/recordings)")
    finally:
        SAMPLES[PRIMARY] = df_backup


def fig_phone_session(fmt):
    df, _ = SAMPLES[PRIMARY]
    if df is None:
        return None
    phones = [p for p in CFG["phone_order"] if p in set(df["phone"])]
    sess = [c for c in dict.fromkeys(CFG_SESSIONS) if c in set(df["session"])]
    M = np.zeros((len(phones), len(sess)))
    N = np.zeros_like(M)
    for i, p in enumerate(phones):
        for j, c in enumerate(sess):
            sub = df[(df.phone == p) & (df.session == c)]
            M[i, j], N[i, j] = sub.hit.sum(), len(sub)
    s = SIZES[fmt]
    figsize = (9.5, 4.8) if fmt == "slide" else (CFG["report_width_in"], 2.4)
    fig, ax = plt.subplots(figsize=figsize)
    _heat(ax, M, N, phones, sess, s, None)
    ax.set_xlabel("held-out session")
    ax.set_ylabel("phone")
    ax.set_title("Phone x session (fused kNN, leave one session out; correct/recordings)", loc="left", fontsize=s["base"])
    fig.tight_layout()
    return fig


def fig_cross_bars(fmt):
    d3 = [("xsession_24s1_to_24s2_iphone", "24 Nov\niPhone\ns1 to s2\n(ip18 to ip16)"), ("xsession_24s2_to_24s1_iphone", "iPhone\ns2 to s1\n(ip16 to ip18)"),
          ("xsession_24s1_to_24s2_s24", "S24\ns1 to s2"), ("xsession_24s2_to_24s1_s24", "S24\ns2 to s1"),
          ("xday_23nov_to_24s2_iphone", "23 Nov to\n24 s2\n(same ip16)"), ("xday_24s2_to_23nov_iphone", "24 s2 to\n23 Nov\n(same ip16)"),
          ("xday_23nov_to_24s1_iphone", "23 Nov to\n24 s1\n(ip16 to ip18)")]
    feats = [("|B| + baro floor", "|B| + floor", OI["sky"]), ("|B|+xyz + baro floor", "|B|+xyz + floor", OI["blue"]),
             ("tilt + baro floor", "tilt + floor", OI["green"]), ("Wi-Fi + baro floor", "Wi-Fi + floor", OI["orange"])]
    cd = [("cross_core", "23 to 17 Nov"), ("cross_core_reverse_train17_test23", "17 to 23 Nov")]
    cdf = [("magnitude_knn_baro_floor", "|B| + floor", OI["sky"]), ("magnitude_xyz_knn_baro_floor", "|B|+xyz + floor", OI["blue"]), ("rssi_knn_baro_floor", "Wi-Fi + floor", OI["orange"])]
    if not any(F(d3id(e, f)) for e, _ in d3 for f, *_ in feats):
        return None
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 5.4)
    if fmt == "slide":
        fig, (a1, a2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw=dict(width_ratios=[3.6, 1.5]))
    else:
        fig, (a1, a2) = plt.subplots(2, 1, figsize=figsize, gridspec_kw=dict(height_ratios=[2.2, 1.5]))

    def grouped(ax, groups, series, getter, chance_of):
        w = 0.8 / len(series)
        for gi, (gk, glab) in enumerate(groups):
            for si, (sk, slab, col) in enumerate(series):
                f = getter(gk, sk)
                if f is None:
                    continue
                x = gi + (si - (len(series) - 1) / 2) * w
                lo, hi = f.ci
                ax.bar(x, f.p * 100, w * 0.92, color=col, label=slab if gi == 0 else None)
                ax.plot([x, x], [lo * 100, hi * 100], color="black", lw=s["lw"] * 0.5)
                ax.text(x, hi * 100 + 1, f"{f.k}/{f.n}", ha="center", va="bottom", fontsize=s["small"] - (2.5 if fmt == "slide" else 1.2), rotation=90)
        ch = chance_of()
        if ch:
            ax.axhline(ch * 100, color="black", ls="--", lw=s["lw"] * 0.6)
        ax.set_xticks(range(len(groups)), [g[1] for g in groups])
        ax.set_ylim(0, 100)
        ax.set_ylabel("place accuracy (%)")

    grouped(a1, d3, feats, lambda g, sk: F(d3id(g, sk)), lambda: 1 / 26)
    a1.text(-0.45, 1 / 26 * 100 + 1.5, f"chance {100 / 26:.1f}%", ha="left", fontsize=s["small"])
    a1.set_title("Cross-session and cross-day, 24 Nov data (kNN k=5)", loc="left", fontsize=s["base"])
    a1.legend(loc="upper right", frameon=False, ncol=2)
    grouped(a2, cd, cdf, lambda g, sk: F(f"cd.{g}.{sk}"), lambda: (F("cd.cross_core.magnitude_knn").chance if F("cd.cross_core.magnitude_knn") else None))
    a2.set_title("17 Nov vs 23 Nov", loc="left", fontsize=s["base"])
    if fmt == "slide":
        a2.set_ylabel("")
    _c = F("cd.cross_core.magnitude_knn")
    if _c and _c.chance:
        a2.text(-0.45, _c.chance * 100 + 1.5, f"chance {100 * _c.chance:.1f}%", ha="left", fontsize=s["small"])
    fig.tight_layout()
    return fig


def fig_tracker_vs_snapshot(fmt):
    panels = [("trk24.x", "24 Nov s1 to s2\n(ip18 to ip16), n=26"), ("trk24.same", "24 Nov s2, fingerprints\nfrom 23 Nov (same ip16), n=26"),
              ("trk.lovo23", "23 Nov, leave one\nvisit out, n=42"), ("trk.x2317", "23 to 17 Nov\ncross-day core, n=17")]
    meths = [("tracker", "HMM tracker (graph + steps + fingerprint)", OI["green"]), ("snapshot_knn_crossday_recipe", "snapshot kNN (no graph)", OI["sky"]),
             ("emission_only_no_graph", "emission only (tracker without graph)", OI["lgrey"])]
    metrics = [("exact", "exact place"), ("area", "right area")]
    panels = [p for p in panels if F(f"{p[0]}.tracker.exact")]
    if not panels:
        return None
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 3.4)
    fig, axs = plt.subplots(1, len(panels), figsize=figsize, sharey=True)
    axs = np.atleast_1d(axs)
    w = 0.26
    for ax, (pk, ptitle) in zip(axs, panels):
        for mi, (mk, mlab, col) in enumerate(meths):
            for xi, (ek, elab) in enumerate(metrics):
                f = F(f"{pk}.{mk}.{ek}")
                if f is None:
                    continue
                x = xi + (mi - 1) * w
                lo, hi = f.ci
                ax.bar(x, f.p * 100, w * 0.92, color=col, label=mlab if (ax is axs[0] and xi == 0) else None)
                ax.plot([x, x], [lo * 100, hi * 100], color="black", lw=s["lw"] * 0.5)
                ax.text(x, hi * 100 + 1, f"{f.k}", ha="center", va="bottom", fontsize=s["small"])
        ch = F(f"{pk}.tracker.exact").chance
        if ch:
            ax.axhline(ch * 100, color="black", ls="--", lw=s["lw"] * 0.6)
        ax.set_xticks(range(len(metrics)), [m[1] for m in metrics])
        ax.set_title(ptitle, fontsize=s["small"] + 1, loc="left")
        ax.set_ylim(0, 105)
    axs[0].set_ylabel("stop visits correct (%)")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, fontsize=s["small"])
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    return fig


def fig_variance(fmt):
    if VAR is None:
        return None
    v = VAR[VAR.order == "session_first"].set_index("feature")
    feats = [("B", "|B|"), ("xyz", "x/y/z pooled"), ("Bv", "B vertical"), ("Bh", "B horizontal"), ("hpa", "pressure")]
    feats = [(k, l) for k, l in feats if k in v.index]
    pieces = [("share_place", "places (signal)", OI["green"]), ("share_session", "sessions (days)", OI["orange"]), ("share_phone", "phones", OI["verm"]),
              ("share_rec", "recordings", OI["sky"]), ("share_within", "within recording", OI["lgrey"])]
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 3.0)
    fig, ax = plt.subplots(figsize=figsize)
    for yi, (fk, fl) in enumerate(feats):
        left = 0
        for pk, pl, col in pieces:
            val = float(v.loc[fk, pk]) * 100
            ax.barh(-yi, val, 0.62, left=left, color=col, label=pl if yi == 0 else None, edgecolor="white", lw=0.6)
            if val >= 5:
                ax.text(left + val / 2, -yi, f"{val:.0f}%", ha="center", va="center", fontsize=s["small"], color="black" if col not in (OI["verm"],) else "white")
            left += val
    ax.set_yticks([-i for i in range(len(feats))], [l for _, l in feats])
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of total variance (%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2 if fmt == "slide" else -0.3), ncol=5, frameon=False)
    n = int(v["n_windows"].iloc[0])
    ax.set_title(f"Where the spread comes from ({n} windows, session-first nesting)", loc="left")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    return fig


def _clock(x):
    return f"{int(x // 60):02d}:{int(x % 60):02d}"


def floor_frames():
    """Per session: DataFrame(minute, hpa, floor, device, wrong)."""
    cfg3 = loadj(CFG["day3_config"])
    base = Path(CFG["day3_config"]).parent
    res = (D3_RESULTS.get(PRIMARY) or {})
    out = OrderedDict()
    for sess in cfg3["sessions"]:
        sid = sess["id"]
        try:
            if sess["loader"] == "crossday_23nov":
                cd_rel = f"{CFG['clean_data_dir']}/2026-11-23"
                sx = pd.read_csv(P(f"{cd_rel}/sessions.csv"))
                q = pd.read_csv(P(f"{cd_rel}/sensor_quality.csv"))
                q = q[q.sensor == "barometer"].set_index("stop_id").clean_x_median
                sx = sx[sx.kind == "stop"].drop_duplicates("session_id")
                df = pd.DataFrame({"time": sx.start_hk.str[11:16], "hpa": sx.session_id.map(q), "floor": sx.floor, "device": sx.device_model, "place": sx.location_label})
                src = [f"{cd_rel}/sessions.csv", f"{cd_rel}/sensor_quality.csv"]
            else:
                rel = str((base / sess["path"] / "manifest.csv").as_posix())
                rel = str(Path(rel).resolve().relative_to(ROOT)) if Path(rel).is_absolute() else rel
                # day3 config paths are relative to the day3 folder
                rel = (Path(CFG["day3_config"]).parent / sess["path"] / "manifest.csv")
                rel = Path(*[p for p in rel.parts if p != ".."]) if ".." not in rel.parts else rel
                m = pd.read_csv(P(str(Path(CFG["day3_config"]).parent / sess["path"] / "manifest.csv")).resolve())
                m = m[(m.type == "stop") & m.pressure_hpa.notna()]
                df = pd.DataFrame({"time": m.start_hk.str[:5], "hpa": m.pressure_hpa, "floor": m.floor, "device": m.device, "place": m.node})
                src = [str((Path(CFG["day3_config"]).parent / sess["path"] / "manifest.csv").resolve().relative_to(ROOT.resolve()))]
        except Exception as e:  # noqa: BLE001
            note_missing(f"floor timeline data for session {sid}", f"({type(e).__name__}: {e})")
            continue
        df["minute"] = df.time.str[:2].astype(int) * 60 + df.time.str[3:5].astype(int)
        df["wrong"] = False
        fl = res.get("floor", {}).get(f"iphone_test_{sid}")
        if fl:
            for w in fl.get("step_tracking_wrong_stops", []):
                mm = int(w["start_hk"][:2]) * 60 + int(w["start_hk"][3:5])
                df.loc[(df.minute == mm) & df.device.astype(str).str.startswith("iPhone"), "wrong"] = True
        out[sid] = (df.dropna(subset=["hpa"]), src, (fl or {}).get("step_tracking"))
    return out


def fig_floor_timeline(fmt):
    fr = floor_frames()
    if not fr:
        return None
    s = SIZES[fmt]
    n = len(fr)
    cols = 2 if n > 1 else 1
    rows_ = math.ceil(n / cols)
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 1.9 * rows_ + 0.6)
    fig, axs = plt.subplots(rows_, cols, figsize=figsize)
    axs = np.atleast_1d(axs).ravel()
    fcol = {5: OI["blue"], 4: OI["orange"]}
    mk = ["o", "s", "^", "D"]
    for ax, (sid, (df, src, st)) in zip(axs, fr.items()):
        devs = sorted(d for d in df.device.unique() if str(d).startswith("iPhone"))
        for di, dev in enumerate(devs):
            sub = df[df.device == dev]
            for fl_, c in fcol.items():
                ss = sub[sub.floor == fl_]
                ax.scatter(ss.minute, ss.hpa, s=s["ms"] ** 2 * 0.9, color=c, marker=mk[di % 4], zorder=3, label=f"{dev}, floor {fl_}" if sid == list(fr)[0] else None)
            w = sub[sub.wrong]
            ax.scatter(w.minute, w.hpa, s=s["ms"] ** 2 * 4, facecolors="none", edgecolors=OI["verm"], linewidths=s["lw"] * 1.3, zorder=4)
        sm = df[df.device.astype(str).str.startswith("SM-S9280")]
        ax.scatter(sm.minute, sm.hpa, s=s["ms"] ** 2 * 0.6, facecolors="none", edgecolors=OI["grey"], marker="o", zorder=2, label="S24 (barometer unreliable)" if sid == list(fr)[0] else None)
        ax.set_title(f"{sid}" + (f": step tracking {st}" if st else ""), loc="left", fontsize=s["base"])
        ax.set_ylabel("pressure (hPa)")
        ticks = ax.get_xticks()
        ax.set_xticks(ticks)
        ax.set_xticklabels([_clock(t) for t in ticks])
        ax.set_xlim(df.minute.min() - 3, df.minute.max() + 3)
    for ax in axs[n:]:
        ax.axis("off")
    h, l = axs[0].get_legend_handles_labels()
    handles = h + [plt.Line2D([], [], marker="o", ls="", markerfacecolor="none", markeredgecolor=OI["verm"], markersize=s["ms"] * 1.6, label="floor wrong (step tracking)")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=s["small"])
    fig.tight_layout(rect=(0, 0.1 if fmt == "slide" else 0.12, 1, 1))
    return fig


def fig_wifi(fmt):
    if WIFI is None:
        return None
    s = SIZES[fmt]
    figsize = s["figsize"] if fmt == "slide" else (CFG["report_width_in"], 2.8)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw=dict(width_ratios=[1, 1.4]))
    ins = WIFI["inside_one_stop"]
    keys = list(ins)
    vals = [ins[k]["rows_per_bssid_inside_one_stop_median"] for k in keys]
    scans = [ins[k]["distinct_scan_timestamps_per_60s_stop_median"] for k in keys]
    a1.bar(range(len(keys)), vals, 0.6, color=OI["verm"])
    for i, (v_, sc) in enumerate(zip(vals, scans)):
        a1.text(i, v_ + 0.03, f"{v_:.2f}\n({sc:g} scans)", ha="center", va="bottom", fontsize=s["small"])
    a1.set_xticks(range(len(keys)), keys)
    a1.set_ylim(0, max(vals) * 1.6)
    a1.axhline(1, color="black", lw=s["lw"] * 0.5, ls=":")
    a1.set_ylabel("rows per BSSID inside one stop")
    a1.set_title("Median rows per BSSID\n(scans per stop in brackets)", loc="left", fontsize=s["base"])
    logs = WIFI["per_log"]
    lab = [f"{lg['session']}\n{lg['scanner']}" for lg in logs]
    vv = [lg["share_repeats_stronger_than_all_earlier_rows"] * 100 for lg in logs]
    a2.bar(range(len(logs)), vv, 0.6, color=OI["orange"])
    a2.set_xticks(range(len(logs)), lab, fontsize=s["small"] - 2)
    a2.set_ylim(0, 112)
    a2.set_ylabel("%")
    a2.set_title("Repeat rows stronger than all earlier\nrows of that BSSID (per log)", loc="left", fontsize=s["base"])
    fig.tight_layout()
    return fig


def _bar_text(*a):
    pass


CFG_SESSIONS = []
try:
    CFG_SESSIONS = [x["id"] for x in loadj(CFG["day3_config"])["sessions"]]
except Exception as e:  # noqa: BLE001
    note_missing("day3 config sessions", str(e))

FIG_SPECS = [
    ("fig_honest_vs_leaky", fig_honest_vs_leaky, "Honest vs leaky: one classifier, four splits", [f"phase2/new/day3/out/fused_knn.json"],
     "Fused kNN (learned weights), per-recording or per-window accuracy under four outer splits."),
    ("fig_accuracy_vs_chance", fig_accuracy_vs_chance, "Accuracy against chance, every test",
     ["phase2/new/day3/out/results.json", "phase2/new/day3/out/fused_knn.json", "phase2/new/cross-day/out/results.json", "phase2/new/day3/out/track24_results.json", "phase2/old/positioning-pilot/out/results.json"],
     "Each bar is one test from numbers.md; black tick = chance for that test; leaky tests hatched."),
    ("fig_per_place_accuracy", fig_per_place_accuracy, "Per-place accuracy by held-out session", ["phase2/new/day3/out/fused_sample_predictions.csv"],
     "Fused kNN learned weights, leave one session out, per recording."),
    ("fig_phone_place", fig_phone_place, "Phone x place accuracy", ["phase2/new/day3/out/fused_sample_predictions.csv"],
     "Same predictions as the per-place heat map, split by the phone that recorded the take."),
    ("fig_phone_session", fig_phone_session, "Phone x session accuracy", ["phase2/new/day3/out/fused_sample_predictions.csv"],
     "Same predictions, split by phone and held-out session."),
    ("fig_cross_bars", fig_cross_bars, "Cross-session and cross-day bars", ["phase2/new/day3/out/results.json", "phase2/new/cross-day/out/results.json"],
     "kNN k=5 with barometer floor, per feature set; 24-Nov data (chance 1/26) and 17 vs 23 Nov (chance from summary_table.csv)."),
    ("fig_floor_timeline", fig_floor_timeline, "Barometer floor timeline", ["phase2/clean-data/*/manifest.csv", "phase2/new/day3/out/results.json"],
     "Median pressure per stop in time order, colour = true floor, red ring = step tracking got the floor wrong."),
    ("fig_variance", fig_variance, "Variance decomposition", ["phase2/new/day3/out/variance_by_place.csv"],
     "Share of total variance per feature: places, sessions, phones, recordings, within recording (session-first nesting)."),
    ("fig_tracker_vs_snapshot", fig_tracker_vs_snapshot, "Tracker vs snapshot", ["phase2/new/day3/out/track24_results.json", "phase2/new/tracking/out/tracker_results.json"],
     "HMM tracker vs snapshot kNN on the same stop visits; exact place and right area; bar label = stop visits correct."),
    ("fig_wifi_diagnosis", fig_wifi, "Wi-Fi logger diagnosis", ["phase2/new/day3/out/wifi_diagnosis.json"],
     "Why the WiGLE CSV is not a fingerprint: each BSSID is logged about once per stop and repeats are mostly stronger rows."),
]


def build_figures():
    done = []
    for name, fn, title, srcs, desc in FIG_SPECS:
        made = []
        for fmt in ("slide", "report"):
            with plt.rc_context(rc(fmt)):
                try:
                    fig = fn(fmt)
                except Exception as e:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    note_missing(f"figure {name} ({fmt})", f"({type(e).__name__}: {e})")
                    fig = None
                if fig is not None:
                    made.append(save(fig, name, fmt))
        if made:
            done.append((name, title, srcs, desc, made))
            print(f"  figure {name}: {', '.join(made)}")
    return done


# ----------------------------------------------------------------------------- positioning table

def _cell(f):
    if f is None:
        return "", "", "", ""
    ci = f.ci
    return f.k, f.n, f"{100 * f.p:.1f}% [{100 * ci[0]:.0f} to {100 * ci[1]:.0f}]", ("" if f.chance is None else f"{100 * f.chance:.1f}%")


def positioning_rows(variant=PRIMARY, only_fused=False):
    """Rows of the method comparison table. Each row = (method, feature set, honest fact, leaky fact, partly leaky fact, note)."""
    v = variant
    R = []

    def fz(g, scheme):
        return F(f"fused.{v}.{scheme}.{g}")

    def row(meth, feat, honest, leaky=None, partly=None, note="", extra=None, tdef=None):
        R.append(dict(method=meth, feature=feat, honest=honest, leaky=leaky, partly=partly, note=note, extra=extra or [], tdef=tdef))

    # fused-framework rows (same test for every feature group): leave one session out, n = all stops of all phones
    if not only_fused:
        row("A  Dead reckoning", "steps (count along a known line), belief on arrival", F("trk24.x.tracker_arrival_before_stop_data.exact"),
            note="graph + step counts only, before the stop's sensor data; start/route known (optimistic)",
            tdef="train 24 s1 (ip18), replay 24 s2 (ip16), graph-v2, per stop visit")
        row("A  Dead reckoning", "walking dot: right first corridor, other session", F("up.dot.sesi1->sesi2.first"),
            note="start place given; chance not defined in file; second direction and end error in numbers.md",
            tdef="corridors from one 24-Nov session, other session's 28 walks, true start place given",
            extra=[F("up.dot.sesi2->sesi1.first")])
    row("B  Wi-Fi kNN", "Wi-Fi only (S24 scanner, rows within 120 s)", fz("wifi", "leave_one_session_out"), fz("wifi", "random_LEAKY"), fz("wifi", "by_recording_partly_leaky"),
        note="WiGLE logs a BSSID only when new or stronger: not a fingerprint (entries 12, 30)")
    if not only_fused:
        row("B  Wi-Fi kNN", "Wi-Fi + floor, iPhone-floor gate, 24 Nov s1 to s2", F(d3id("xsession_24s1_to_24s2_iphone", "Wi-Fi + baro floor")),
            note="same test as the |B|+xyz rows below", extra=[F(d3id("xsession_24s2_to_24s1_iphone", "Wi-Fi + baro floor"))],
            tdef="train 24 s1 (ip18), test 24 s2 (ip16), 5 s windows, k=5, floor gate")
        row("B  Wi-Fi kNN", "Wi-Fi in-window rows only, 24 Nov s1 to s2", F(d3id("xsession_24s1_to_24s2_iphone", "Wi-Fi (in-window rows only)")),
            note="rows inside the 60 s stop only", extra=[F(d3id("xsession_24s2_to_24s1_iphone", "Wi-Fi (in-window rows only)"))],
            tdef="train 24 s1, test 24 s2, no floor gate")
        row("B  Wi-Fi kNN", "Wi-Fi RSSI kNN, 23 to 17 Nov (n small)", F("cd.cross_core.rssi_knn"), note="9 core visits only; with floor gate see numbers.md",
            tdef="train 23 Nov, test 17 Nov, 10 s chunks, 9 core visits",
            extra=[F("cd.cross_core.rssi_knn_baro_floor")])
    row("C  Magnetic kNN", "|B| only (field strength)", fz("B", "leave_one_session_out"), fz("B", "random_LEAKY"), fz("B", "by_recording_partly_leaky"))
    row("C  Magnetic kNN", "|B| x/y/z (field vector)", fz("xyz", "leave_one_session_out"), fz("xyz", "random_LEAKY"), fz("xyz", "by_recording_partly_leaky"),
        note="works only if the phone is held the same way (facing the door)")
    row("C  Magnetic kNN", "tilt (B_vertical, B_horizontal)", fz("tilt", "leave_one_session_out"), fz("tilt", "random_LEAKY"), fz("tilt", "by_recording_partly_leaky"),
        note="needs accelerometer at stops (24 Nov only)")
    if not only_fused:
        row("C  Magnetic kNN", "|B|+xyz + floor, same phone ip16, 23 Nov to 24 s2", F(d3id("xday_23nov_to_24s2_iphone", "|B|+xyz + baro floor")),
            F(d3id("LEAKY_same_recording_time_split_24s2_iphone", "|B|+xyz")), note="true cross-day, same handset; leaky = same recording time split (24 s2, n=26)",
            tdef="train 23 Nov stops (ip16), test 24 s2 stops (ip16), 5 s windows, k=5",
            extra=[F(d3id("xday_24s2_to_23nov_iphone", "|B|+xyz + baro floor"))])
        row("C  Magnetic kNN", "|B|+xyz + floor, iPhone 24 Nov s1 to s2 (different handset)", F(d3id("xsession_24s1_to_24s2_iphone", "|B|+xyz + baro floor")),
            F(d3id("LEAKY_same_recording_time_split_24s2_iphone", "|B|+xyz")), extra=[F(d3id("xsession_24s2_to_24s1_iphone", "|B|+xyz + baro floor"))],
            tdef="train 24 s1 (ip18), test 24 s2 (ip16), different handsets, k=5")
        row("C  Magnetic kNN", "|B|+xyz + floor, 23 Nov revisit (same day)", F("cd.revisit_23.magnitude_xyz_knn_baro_floor"), F("cd.block_23.magnitude_xyz_knn_baro_floor"),
            note="n = 9 revisits; leaky = same visit time split (n = 42)",
            tdef="23 Nov: train on earlier visit, test on later visit of the same place; 31 places (v1)")
        row("C  Magnetic kNN", "|B|+xyz + floor, 23 to 17 Nov", F("cd.cross_core.magnitude_xyz_knn_baro_floor"), F("cd.block_17.magnitude_xyz_knn_baro_floor"),
            note="n = 17 visits; leaky = 17-Nov same visit time split",
            tdef="train 23 Nov, test 17 Nov, 15 core places (v1)")
        row("D  HMM fusion + barometer", "barometer floor, step tracking, iPhone, 24 s2", F("d3.floor.iphone_test_24s2.step"),
            note="floor only; 24 s1 is 23/27 (failure after a long break), see numbers.md",
            tdef="step tracking, threshold from the other sessions, per stop", extra=[F("d3.floor.iphone_test_24s1.step")])
        row("D  HMM fusion + barometer", "HMM tracker, exact place, 24 Nov s1 to s2 (ip18 to ip16)", F("trk24.x.tracker.exact"), note="optimistic: graph and route from the same walks; snapshot kNN same stops in numbers.md",
            tdef="train 24 s1 (ip18), replay 24 s2 (ip16), per stop visit, 26 places",
            extra=[F("trk24.x.snapshot_knn_crossday_recipe.exact")])
        row("D  HMM fusion + barometer", "HMM tracker, same handset ip16 (fingerprints from 23 Nov)", F("trk24.same.tracker.exact"), tdef="fingerprints from 23-Nov ip16 stops, replay 24 s2 (ip16), per stop visit", extra=[F("trk24.same.snapshot_knn_crossday_recipe.exact")])
        row("D  HMM fusion + barometer", "HMM tracker, 23 Nov leave one visit out", F("trk.lovo23.tracker.exact"), note="22 of 42 stops have no fingerprint in training",
            tdef="23 Nov replay, leave one visit out, per stop visit",
            extra=[F("trk.lovo23.snapshot_knn_crossday_recipe.exact")])
    row("D  Fusion (weighted kNN, no HMM)", "fused kNN, learned weights (|B|, xyz, tilt, Wi-Fi, floor)", fz("fused", "leave_one_session_out"), fz("fused", "random_LEAKY"), fz("fused", "by_recording_partly_leaky"),
        note="honest alternative: grouped by stop in numbers.md")
    return R


def table_markdown_csv(R, tag):
    cols = ["Method", "Feature set / variant", "Honest held-out test", "Correct", "n", "Accuracy [95% CI]", "Chance", "LEAKY (random split)", "Partly leaky (by recording)", "Note", "Source"]
    recs = []
    for r in R:
        h = r["honest"]
        if h is None and r["leaky"] is None and r["partly"] is None:
            continue
        ks, ns, acc, ch = _cell(h)
        tdef = (h.test.split(";")[0] if h else "")
        if h and h.kind == "honest" and h.id.startswith("fused."):
            tdef = "leave one session out, all phones (n = " + str(h.n) + ")"
        elif r.get("tdef"):
            tdef = r["tdef"]
        elif h:
            tdef = h.test[:150]
        extra = "; ".join(f"{e.label}: {e.k}/{e.n}" for e in r["extra"] if e is not None and e.k is not None)
        lk = f"{r['leaky'].k}/{r['leaky'].n} = {100 * r['leaky'].p:.1f}%" if r["leaky"] and r["leaky"].k is not None else ""
        pl = f"{r['partly'].k}/{r['partly'].n} = {100 * r['partly'].p:.1f}%" if r["partly"] and r["partly"].k is not None else ""
        note = r["note"] + (f" [other direction / comparator: {extra}]" if extra else "")
        src = ", ".join(sorted({s for f in (h, r["leaky"], r["partly"]) if f for s in f.src})) + " @ " + ", ".join(sorted({f.commit() for f in (h, r["leaky"], r["partly"]) if f}))
        recs.append([r["method"], r["feature"], tdef, ks, ns, acc, ch, lk, pl, note, src])
    df = pd.DataFrame(recs, columns=cols)
    df.to_csv(OUT / f"positioning_table{tag}.csv", index=False)
    lines = ["<!-- INTERNAL TEAM NOTES, not report text. Generated by results-pack/build.py. -->", "",
             "| " + " | ".join(cols[:-1]) + " |", "|" + "---|" * (len(cols) - 1)]
    for rec in recs:
        lines.append("| " + " | ".join(str(x).replace("|", "\\|") for x in rec[:-1]) + " |")
    lines += ["", "Chance is 1/(places in training) unless the row says otherwise (floor rows: 1/2 derived; walking dot: not defined in the file). "
              "n is recordings for stop tests, stop visits for tracker tests. The LEAKY column is the random-window split of the same classifier; do not quote it as a result.", ""]
    (OUT / f"positioning_table{tag}.md").write_text("\n".join(lines))
    return df


# ----------------------------------------------------------------------------- other tables


def other_tables():
    # 1. cross-session / cross-day table, every feature set (day3)
    d = D3_RESULTS.get(PRIMARY)
    if d:
        recs = []
        for exp, tests in d["stop_results"].items():
            if exp.startswith("LEAKY"):
                continue
            for feat in tests:
                if feat == "_split":
                    continue
                f = F(d3id(exp, feat))
                a = F(d3id(exp, feat) + ".area")
                if f:
                    recs.append([exp, feat, f.k, f.n, f"{100 * f.p:.1f}%", a.k if a else "", "" if f.chance is None else f"{100 * f.chance:.1f}%", f.test.split(";")[0][:120]])
        pd.DataFrame(recs, columns=["test", "features", "correct", "n", "accuracy", "area correct", "chance", "definition"]).to_csv(OUT / "table_day3_all_tests.csv", index=False)
    # 2. per place
    df, rel = SAMPLES[PRIMARY]
    if df is not None:
        t = df.groupby("true").agg(correct=("hit", "sum"), n=("hit", "size"), floor=("place_floor", "first"))
        t["accuracy"] = (t.correct / t.n).round(3)
        t.sort_values(["floor", "accuracy"], ascending=[False, False]).to_csv(OUT / "table_per_place.csv")
        pp = df.pivot_table(index="true", columns="phone", values="hit", aggfunc=["sum", "count"])
        pp.to_csv(OUT / "table_phone_place.csv")
    # 3. tracker vs snapshot
    recs = []
    for pk in ("trk24.x", "trk24.same", "trk.lovo23", "trk.x2317"):
        for meth in ("tracker", "snapshot_knn_crossday_recipe", "emission_only_no_graph", "tracker_arrival_before_stop_data"):
            for metric in ("exact", "area", "top3", "floor"):
                f = F(f"{pk}.{meth}.{metric}")
                if f:
                    recs.append([pk, meth, metric, f.k, f.n, f"{100 * f.p:.1f}%", f.test[:140]])
    if recs:
        pd.DataFrame(recs, columns=["test", "method", "metric", "correct", "n", "accuracy", "definition"]).to_csv(OUT / "table_tracker_vs_snapshot.csv", index=False)
    # 4. request matching
    ids = [f"rm.{m}.{sl}" for sl in ("test", "all") for m in ("keyword", "embed", "llm", "fuzzy_keyword", "hybrid", "tokens")]
    if any(F(i) for i in ids):
        recs = [[F(i).label, F(i).k, F(i).n, F(i).test] for i in ids if F(i)]
        pd.DataFrame(recs, columns=["method", "correct", "n", "definition"]).to_csv(OUT / "table_request_matching.csv", index=False)


# ----------------------------------------------------------------------------- numbers.md

KNOWN_ISSUES = [
    ("Chance is not one number.", "Stop tests in day3 use chance 1/26 (26 graph-v2 places); upload/out/eval.json uses 1/13 because the true floor is given; cross-day/ uses 1/31 (23-Nov places), 1/15 and 1/12 for core sets; the tracker tests use 1/31 or 1/26. Always quote chance together with n."),
    ("iPhone 'xyz' cross-session 17/26 vs 12/26.", "upload/out/eval.json gives iPhone s1 to s2 17/26 (floor given, 2 s windows per floor model); day3/out/results.json gives 12/26 for |B|+xyz + floor (floor from step tracking, 5 s windows). Same data, different recipe and chance (1/13 vs 1/26). They are not the same test."),
    ("Snapshot kNN differs between files.", "track24 snapshot kNN exact 15/26 (2 s windows, sklearn per floor) vs day3 results.json 12/26 for the same s1 to s2 split (5 s windows, gknn.py); the log (entry 32) states this. In the tracking/ cross-day test the snapshot is 2/17 exact while crossday.py gives 3/17 or 4/17 for the same 23 to 17 test (tracker_results.json reference block)."),
    ("Floor tracking 24 s1: 23/27 vs 27/27.", "day3/out/results.json (jump threshold rule) 23/27 and a fixed threshold 27/27; upload/out/eval.json (median of last 6 readings, long-gap rule) 27/27 for the same session. Different rules."),
    ("Wi-Fi coverage claims.", "PROCESS-LOG entry 12 says the 23-Nov Wi-Fi covers 41/42 stops (counted rows), day3/out/wifi_diagnosis.json says 42/42 (stops_with_any_wifi, all scanners, within 120 s); neither says the data is usable (rows per BSSID per stop is about 1)."),
    ("Cross-day Wi-Fi range.", "Entry 12 says cross-day core Wi-Fi 11 to 22%; cross-day/out/summary_table.csv has 11% to 44% across the eight Wi-Fi variants of cross_core (n = 9, the 44% is presence_knn + floor)."),
    ("Entry numbers.", "Commit messages made before the first merge use old entry numbers 24 to 33 (see entry 39); the log uses 29 to 38 (renumbered twice: +4 at entry 39, +1 when Dicta's entry 28 landed, entry 48)."),
    ("Handset names.", "Session READMEs call both iPhones 'iPhone 16 Pro'; the device IDs are iPhone19,2 (ip18) and iPhone17,4 (ip16). The 'iPhone 18' label is the user's statement, not in the data (day3/config.json)."),
    ("Different places, different sets.", "23-Nov v1 has 31 places, graph-v2 26; 24-Nov can only be scored on graph-v2 names. cross-day numbers (v1) and day3 numbers (v2) are not on the same place list."),
]


def write_numbers_md(rows_fig):
    L = []
    L.append("# numbers.md: every headline number, with its source and test definition")
    L.append("")
    L.append("**INTERNAL TEAM NOTES, not report text.** Generated by `phase2/new/results-pack/build.py`; do not edit by hand, rerun the build. "
             "The course rule applies: an LLM may only polish our own writing, so these are numbers and test definitions, not sentences for the report.")
    L.append("")
    L.append(f"Build: repo HEAD `{HEAD}` on `{BRANCH}`, {dt.date.today().isoformat()}. Sources read from `{ROOT}`. "
             "Each row names the source file and the last commit that touched it (`uncommitted` or `+local changes` if the file is not committed as read).")
    L.append("")
    L.append("Kinds: **honest** = train and test are different visits, sessions or stops; **partly leaky** = the other phones of the same physical stop may be in training; **LEAKY** = same recording in train and test (illustration only, never quote as a result); **descriptive** = not an accuracy.")
    L.append("")
    sections = [
        ("1. The leakage story (one classifier, four splits)", lambda f: f.id.startswith(f"fused.{PRIMARY}.") and f.id.count(".") == 3),
        ("2. Fused kNN per feature group (leave one session out, grouped by stop; area counts)", lambda f: f.id.startswith(f"fused.{PRIMARY}.") and (f.id.endswith(".area") or "loso.fold" in f.id or "deployable" in f.id)),
        ("3. Same, 20 s pieces variant (out-split20; pieces of one take are not independent): fused groups", lambda f: f.id.startswith("fused.split20.") and f.id.count(".") == 3),
        ("3b. 20 s pieces vs take level (compare_before_after.csv; value = after, BEFORE in the definition)", lambda f: f.id.startswith("cmp.")),
        ("4. Cross-session and cross-day, 24 Nov data (day3/results.json, kNN k=5)", lambda f: f.id.startswith("d3.x") or f.id.startswith("d3.LEAKY")),
        ("5. Walk endpoints, barometer floor", lambda f: f.id.startswith("d3.walkend") or f.id.startswith("d3.floor")),
        ("6. 17 vs 23 Nov cross-day and the 23-Nov revisit/leaky blocks (cross-day/, v1 places)", lambda f: f.id.startswith("cd.")),
        ("7. Tilt (23-Nov walk endpoints) and phone disagreement", lambda f: f.id.startswith("tilt.")),
        ("8. Tracker (HMM) vs snapshot", lambda f: f.id.startswith("trk")),
        ("9. Dead reckoning: steps, stride, walking dot, live replay (upload/, tracking/)", lambda f: f.id.startswith(("pdr.", "up.dot", "up.live", "up.standing"))),
        ("10. Tian's upload app: held-out test (take level, floor given)", lambda f: f.id.startswith("up.") and (".top1" in f.id or ".top3" in f.id or f.id.startswith("up.floor")) and not f.id.startswith(("up.dot", "up.live", "up.standing", "up20"))),
        ("11. Tian's app on 20 s pieces", lambda f: f.id.startswith("up20")),
        ("12. Wi-Fi diagnosis", lambda f: f.id.startswith("wifi.")),
        ("13. Variance decomposition (all places, session-first)", lambda f: f.id.startswith("var.session_first")),
        ("14. Old pilot (superseded, leaky) and request matching", lambda f: f.id.startswith(("pilot", "rm."))),
        ("15. Derived by build.py", lambda f: f.id.startswith("derived")),
    ]
    used = set()
    for title, pred in sections:
        fs = [f for f in FACTS.values() if pred(f) and f.id not in used and not f.id.endswith(".area") and not f.id.startswith("d3_")]
        if not fs:
            continue
        L.append(f"## {title}")
        L.append("")
        L.append("| id | what | value | 95% CI | n (unit) | chance | kind | exact test definition | source file | commit |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for f in fs:
            used.add(f.id)
            ci = f.ci
            cis = f"{100 * ci[0]:.0f} to {100 * ci[1]:.0f}%" if ci else ""
            nn = f"{f.n} {f.unit}" if f.n else ""
            ch = "" if f.chance is None else f"{100 * f.chance:.1f}%" + (f" ({f.chance_note})" if f.chance_note else "")
            tdef = f.test.replace("|", "\\|").replace("\n", " ")
            L.append(f"| `{f.id}` | {f.label.replace('|', chr(92) + '|')} | {f.fmt().replace('|', chr(92) + '|')} | {cis} | {nn} | {ch} | {KIND_LABEL[f.kind]} | {tdef} | `{', '.join(f.src)}` | {f.commit()} |")
        L.append("")
    rest = [f for f in FACTS.values() if f.id not in used and not f.id.endswith(".area") and not f.id.startswith("d3_")]
    if rest:
        L.append("## Other facts")
        L.append("")
        for f in rest:
            L.append(f"- `{f.id}`: {f.label} = {f.fmt()} ({KIND_LABEL[f.kind]}); {f.test}; `{', '.join(f.src)}` @ {f.commit()}")
        L.append("")
    L.append("Not listed here (kept in the CSV/JSON sources): area-correct counts and the 20 s-piece versions of every day-3 test (see `out-split20/results.json`, `table_day3_all_tests.csv`).")
    L.append("")
    L.append("## Known inconsistencies between source files (flagged, not fixed)")
    L.append("")
    for a, b in KNOWN_ISSUES:
        L.append(f"- **{a}** {b}")
    L.append("")
    if MISSING:
        L.append("## Not found / skipped in this build")
        L.append("")
        for w, why in MISSING:
            L.append(f"- {w} {why}")
        L.append("")
    (OUT / "numbers.md").write_text("\n".join(L))


# ----------------------------------------------------------------------------- timeline.md


def resolve(text):
    def sub(m):
        tok = m.group(1).strip()
        try:
            if tok.startswith("json:"):
                rel, _, path = tok[5:].partition("#")
                obj = loadj(rel)
                mode = None
                if "|" in path:
                    path, mode = path.split("|")
                for part in path.split("."):
                    obj = obj[int(part)] if isinstance(obj, list) else obj[part]
                if mode == "len":
                    obj = len(obj)
                if isinstance(obj, list):
                    obj = ", ".join(map(str, obj))
                elif isinstance(obj, dict):
                    obj = "; ".join(f"{a}: {b}" for a, b in obj.items())
                return str(obj)
            if tok.startswith("csvcount:"):
                rel, col, val = tok[9:].split("|")
                d = pd.read_csv(P(rel))
                return str(int((d[col].astype(str) == val).sum()))
            if tok.startswith("csvrows:"):
                return str(len(pd.read_csv(P(tok[8:]))))
            if tok.startswith("f:"):
                parts = tok[2:].split(":")
                f = F(parts[0])
                if f is None:
                    return "[n/a]"
                if len(parts) == 2:
                    return {"k": str(f.k), "n": str(f.n), "pct": f"{100 * f.p:.1f}%"}.get(parts[1], f.fmt())
                return f.fmt()
        except Exception as e:  # noqa: BLE001
            note_missing(f"timeline placeholder {tok}", f"({type(e).__name__}: {e})")
        return "[n/a]"
    return re.sub(r"\{\{(.+?)\}\}", sub, text)


def write_timeline():
    rel = CFG["timeline_facts"]
    tf = json.loads((HERE / rel).read_text())
    L = ["# timeline.md: dated data-collection sessions, what each added, failures and lessons", "",
         "**INTERNAL TEAM NOTES, not report text.** Bullet facts only, taken from `PROCESS-LOG.md` (entry numbers in brackets) and from source files (numbers in `{{...}}` slots are read from the files at build time). "
         "Generated by `phase2/new/results-pack/build.py` from `timeline_facts.json`; edit that file for the wording of failures and lessons.", "",
         f"Build: repo HEAD `{HEAD}`, {dt.date.today().isoformat()}.", ""]
    for s in tf["sessions"]:
        L.append(f"## {s['date']}: {s['title']}")
        L.append("")
        for key, head in (("added", "Added"), ("failures", "Failures and problems"), ("lessons", "Lessons / what changed")):
            if s.get(key):
                L.append(f"**{head}**")
                for b in s[key]:
                    L.append(f"- {resolve(b)}")
                L.append("")
        if s.get("log"):
            L.append(f"Log entries: {s['log']}. Data: {resolve(s.get('data', ''))}")
            L.append("")
    L.append("## Analysis milestones, in order")
    L.append("")
    for b in tf["milestones"]:
        L.append(f"- {resolve(b)}")
    L.append("")
    (OUT / "timeline.md").write_text("\n".join(L))


# ----------------------------------------------------------------------------- html gallery


def write_gallery(figs, ptable):
    h = ["<!doctype html><meta charset='utf-8'><title>WalkSense results pack</title>",
         "<style>body{font-family:system-ui,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;color:#222}h1{font-size:1.4em}h2{font-size:1.1em;margin-top:2em}"
         "img{max-width:100%;border:1px solid #ddd}.row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}.row div{flex:1 1 360px}"
         "table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccc;padding:3px 6px;vertical-align:top}th{background:#f2f2f2}.src{color:#555;font-size:12px}"
         ".warn{background:#fff3cd;padding:8px 12px;border-left:4px solid #E69F00}</style>",
         "<h1>WalkSense results pack (internal)</h1>",
         "<p class='warn'>Internal team notes, not report text. Generated by <code>phase2/new/results-pack/build.py</code> "
         f"(repo HEAD {HEAD}, {dt.date.today().isoformat()}). Numbers: <a href='numbers.md'>numbers.md</a>, <a href='timeline.md'>timeline.md</a>.</p>"]
    for name, title, srcs, desc, made in figs:
        h.append(f"<h2>{html.escape(title)}</h2><p class='src'>{html.escape(desc)}<br>sources: {html.escape(', '.join(srcs))}</p><div class='row'>")
        for stem in made:
            fmt = stem.rsplit("_", 1)[1]
            h.append(f"<div><b>{fmt}</b> (<a href='{stem}.png'>png</a>, <a href='{stem}.svg'>svg</a>)<br><a href='{stem}.png'><img src='{stem}.png' loading='lazy'></a></div>")
        h.append("</div>")
    h.append("<h2>Positioning comparison table</h2>")
    h.append(ptable.to_html(index=False, escape=True, border=0))
    (OUT / "index.html").write_text("\n".join(h))


# ----------------------------------------------------------------------------- main

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        if old.is_file():
            old.unlink()
    figs = build_figures()
    R = positioning_rows(PRIMARY)
    ptable = table_markdown_csv(R, "")
    for var in CFG["day3_variants"]:
        if var != PRIMARY:
            table_markdown_csv(positioning_rows(var, only_fused=True), f"_{var}")
    other_tables()
    write_timeline()
    write_numbers_md(figs)
    write_gallery(figs, ptable)
    print(f"done: {len(FACTS)} facts, {len(figs)} figures, {len(MISSING)} missing items; outputs in {OUT}")
