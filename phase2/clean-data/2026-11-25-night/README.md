# 25 November 2026, night run (second collection run, floor 5 + floor 4)

*Internal team notes, not report text.* Counts are from `round/clean/summary.json`, `tian/clean/summary.json`,
`build_summary.json` and `labels_night.csv` (rebuild them with the command below).

The second collection run of 25 Nov, about 21:40 to 00:40 (26 Nov). Three phones recorded one full pass of the
two-floor loop; Dicta and Chris then went back for extra takes at the weak places.

| track (day-3 session) | who | phone (model), folder | time | stops | walks |
|---|---|---|---|---|---|
| `round` (`25night`) | Dicta (Benedicta) | ip18 (iPhone19,2), `iphone` | 21:47 to 00:40 | 32 (24 loop + 8 extra) | 27 |
| `round` (`25night`) | Chris | a56 (SM-A566B), `a56` | 21:47 to 00:40 | 32 (24 loop + 8 extra) | 26 |
| `tian` (`25night_tian`) | Tian | ip16 (iPhone17,4), `iphone` | 21:40 to 23:00 | 23 | 23 |

Dicta and Chris walked in step (their STARTs are within seconds), Tian walked the loop on his own and faster, in his
own order, so he is a separate track (his own clean tree, his own day-3 session; the same split as 24 Nov session 1 /
session 2). Wi-Fi: Chris's WiGLE log `WigleWifi_20261126001048.csv.gz` (8011 Wi-Fi rows, all inside the run) belongs
to `round`. Tian has no Wi-Fi log.

## Layout
```
2026-11-25-night/
├── raw/                  phyphox ZIPs + 1 WiGLE log, byte-identical (WhatsApp '0000xxxx-' prefix removed, as in ../2026-11-25/raw)
├── labels_night.csv      one row per recording: phone, track, slot, START, type, floor, node(s), status, confidence, reason, sha256
├── wifi_logs.csv         WiGLE log -> track, scanner phone
├── tian_lt_check.csv     magnetometer check of Tian's two doubtful 4F stops (scripts/check_tian_lt.py)
├── build_summary.json    what was built and what was left out (labels_not_built)
├── scripts/
│   ├── nightlib.py       shared helpers (metadata, 24:mm:ss clock, file-name check)
│   ├── build_night.py    raw/ + labels_night.csv -> <track>/clean/
│   ├── ingest_export.py  add a teammate's export (ZIP or folder of loose files) -> raw/ + proposed label rows
│   └── check_tian_lt.py
├── round/clean/          Dicta + Chris
└── tian/clean/           Tian
```
Each `<track>/clean/` has the layout of Dicta's `../2026-11-25/clean/`: `floor5|floor4/stops/sNN_<node>/<phone>/<Sensor>.csv`,
`walks/wNN_<from>__<to>/<phone>/...`, `manifest.csv`, `locations.csv`, `edges.csv`, `summary.json`, `ROUTE.md`, `ROUTE.html`,
`wifi/observations.csv` (round). The sensor folders and `observations.csv` are gitignored; rebuild with
`python -I phase2/clean-data/2026-11-25-night/scripts/build_night.py` (seconds; the day-3 `run_all.sh` does it first).
Node names are Dicta's first-run names (`canteen`, `exit5_door`, `lift_stairs5`, `y5302_point2`, `gate`, ...);
`phase2/new/day3/names_25night.csv` maps them to graph-v2 places exactly as `names_25nov.csv`.

**Times after midnight** are written `24:mm:ss` in `start_hk` (00:16 on 26 Nov = `24:16:xx`), with the real date-time in
`start_iso`. Every reader of `start_hk` (day-3 `data.py`, the upload app's `hk_epoch`) adds h:m:s to the session day, so
order and gaps stay right across midnight without code changes.

## Labels
Every label comes from the collector's own file name (team rule: names are ground truth: lt/lv/lantai N = floor N,
atas = 5F, bawah = 4F, turun = down, naik = up, ke/to = walk from A to B, disb/disable = disabled, cewe = female,
cowo/cowok/men = male, ext/ezit = exit, kantin/kntin = canteen). Context-resolved names have their reason in the row:
- Dicta: "Disable tolet" 22:43 (after "Exit 5 door ke male disb toilet") = male disabled toilet 5F; "Disable tolet to stair" =
  to the lift/stairs 5F; "Disable toilet" 23:08 (after "Lift lt 4 to toilet disable") = mixed disabled toilet 4F;
  "Study room" 22:06 = sr9 (after "Y5302 to study room"; her first run had sr9 in this slot); "Y5302" 22:59 after
  "Y5401 to y5302" = y5302_point2 (the same pair as her first run at 18:29/18:30, which she mapped to point 2).
- **"Exit 4 lt4" (23:17, Dicta and Chris) = exit 5 door 4F** (typo: there is no exit 4; it comes after "Disable toilet to exit 5
  lt 4" and before "Exit 5 lantai 4 ke lt2a"). Confidence medium.
- Tian: a 8 s walk named only "y5202" (21:56, between his y5202 and toilet cewe stops) = y5202 -> female toilet (medium);
  "y4502 eska baik bawah" = y4502 -> escalator up 4F ("baik" read as "naik", medium); "lift stair corridor y" = lift/stairs ->
  y5401; "stair lift" without "bawah" = 5F (pressure 1017.65 hPa like his 5F stops; his "bawah" stops are 1018.2).
- Chris's takes: proposed by `ingest_export.py` (START within 150 s of Dicta's take of the same type) and his own name checked
  against that slot: 57 of 58 agreed; "exit 4 lt4" (same typo) was set by hand.
- **Left out (status `review`, 5 of Tian's): "eska naik bawah lt2 b" 22:49, "lt2b" 22:50, "lt2b lt2a" 22:51, "lt2a" 22:53,
  "lt2a exit10" 22:55.** His names say LT2B/LT2A a second time, but they come after the 4F up escalator and before exit 10,
  where the route has LT1B and LT1A, and their field is far from his own LT2A/LT2B takes of 22:34/22:37 and near his 24-Nov
  LT1B (12.6 uT) and LT1A (1.2 uT) takes (`tian_lt_check.csv`). Tian should say which rooms they were; then set the rows to
  `ok` (floor 4, a slot number, node `lt1b`/`lt1a` or `lt2b`/`lt2a`) and rebuild.
- **Also left out: Tian's walk "toilet disabled bawah lt2a" (22:33)**, 4F disabled toilet -> LT2A. The label is fine, but the place
  graph and the upload app's floor plan have no direct corridor between those two (the walk passes the 4F exit 5 door), and the
  app builds its corridors from the walks (`test_walksense.py` checks that every corridor is drawn). Set it `ok` if the team
  adds that corridor to the map.

## Sensor problems found (`field_check.csv`, `scripts/check_field.py`)
- **Chris's a56 magnetometer was off all night**: median |B| over his 32 stops 110.9 uT (49.0 to 186.8), against 45.2 uT for the
  same phone on the first 25-Nov run and 40.6 uT on 24 Nov; mean x/y/z offset against his first-run take at the same 24
  places -35.4 / -77.6 / -3.3 uT (sd 24.4 / 25.4 / 7.5). Dicta's iPhone on the same walk: 36.9 uT, offset 5.5 / -2.3 / 2.4 uT.
  This looks like a hard-iron offset (uncalibrated sensor or a magnet / magnetic case near the phone), not a label problem.
  The takes are kept and used like every other take; see PROCESS-LOG entry 72 for what it does to the a56 numbers.
- One of Dicta's stops, "Y5302" 22:59 (y5302_point2), is the B_max of her night stops in `field_check.csv` (332.6 uT; her median is 36.9 uT): something magnetic was close to the phone at that take.

## Coverage of the run (stops per place, from labels_night.csv rows with status ok)
| place (graph-v2) | ip18 Dicta | a56 Chris | ip16 Tian |
|---|---|---|---|
| canteen, exit_5, male_toilet, y5302, female_toilet, y4502, lt2a, lt2b, escalator_down_4F, escalator_up_4F, exit_10_4F, entrance_exit, disabled_toilet_4F | 1 | 1 | 1 |
| sr9, y5202, exit_10, disabled_toilet (5F male), lift_stairs, y5302_back, y5401, lift_stairs_4F | 2 | 2 | 1 |
| escalator_down, escalator_up (5F) | 0 | 0 | 1 |
| exit_5_4F | 1 | 1 | 0 |
| lt1b, lt1a | 1 | 1 | 0 (2 doubtful takes left out) |

Skipped or missing (no recording in any download): the 5F escalator **stops** for Dicta and Chris (their three 5F
escalator walks are there; the gaps 22:23-22:31 and 22:33-22:38 would fit them), the 5F walk male_toilet -> y5302 for Dicta
and Chris, Chris's walk sr9 -> y5202 (22:09; Dicta has it), Tian's 4F exit 5 door stop (he walked disabled toilet 4F -> LT2A).
13 of Dicta's 32 stops have no `Barometer.csv` (phyphox did not log pressure), so the floor tracker skips them.
Tian's walk "center gate exit 5 bawah" (22:58) was recorded before his "center gate" stop (22:59).

## Adding the other phones' files later
```sh
python -I phase2/clean-data/2026-11-25-night/scripts/ingest_export.py "<WhatsApp Chat - GE2340 ...>.zip" --dry-run
python -I phase2/clean-data/2026-11-25-night/scripts/ingest_export.py /mnt/c/Users/Hp/Downloads --since "2026-11-26 02:40" --dry-run
```
Drop `--dry-run` to copy. It hashes everything against the repo (already-present files are skipped, byte-identical
copies inside the source kept once), copies new night-run recordings to `raw/`, and appends one row per recording to
`labels_night.csv`: `ok` when its START is within 150 s of an anchor take of the same type and its own name names the same
place, otherwise `review` (fix the row from the file name). A phone that walked on its own is labelled as its own track
(rows `anchor = yes`, `track = <name>`, as for Tian). New WiGLE logs get a `review` row in `wifi_logs.csv`. Then
`build_night.py`, then `sh phase2/new/day3/run_all.sh` (and `--split20`). Nothing from the export except the recordings
and WiGLE logs is read or kept (no chat text).

Not in this session: Michael's S24 and Tian's ip16 spot takes at 20:22-20:27 (before the run) went to `../2026-11-25-spots`.
