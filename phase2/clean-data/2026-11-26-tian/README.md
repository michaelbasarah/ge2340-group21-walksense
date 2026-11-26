# 26 November 2026, morning: Tian's pass (ip16, floor 5 + floor 4)

*Internal team notes, not report text.* Counts are from `clean/summary.json` and `labels_tian26.csv` (rebuild with the
command below). Day-3 session id `26tian`; PROCESS-LOG entry 73.

Tian walked the two-floor loop alone with his iPhone 16 (iPhone17,4 = ip16, the same handset as 24 Nov session 2,
`25night_tian` and his 25-Nov spot takes), 09:30 to 10:39. 52 recordings: 25 stops (60 s) and 27 walks (4 to 14 s).

| floor | stops | walks |
|---|---|---|
| 5 | 13 | 14 |
| 4 | 12 | 13 |

## Layout
```
2026-11-26-tian/
├── raw/                    52 phyphox ZIPs, byte-identical to the downloads (names unchanged)
├── labels_tian26.csv       one row per recording: file, sha256, chat time + gap, Tian's caption, kind, floor, slot, node(s),
│                           graph-v2 place(s), status, confidence, reason, pressure
├── lt_night_check.csv      field check of his five doubtful 25-Nov night takes against this morning's LT stops
├── medium_label_check.csv  field check of the "lift turun bawah" stop (labelled escalator down 4F)
├── scripts/
│   ├── tianlib.py          day, window, labels path; reuses ../2026-11-25-night/scripts/nightlib.py (metadata, place names)
│   ├── ingest_tian26.py    downloads folder + chat.txt -> raw/ + labels_tian26.csv (one-off; the chat is not kept)
│   ├── build_tian26.py     raw/ + labels_tian26.csv -> clean/ (run by day3/run_all.sh)
│   └── check_lt_night.py   -> lt_night_check.csv, medium_label_check.csv
└── clean/                  Dicta's 25-Nov layout: floor5|floor4/stops|walks/<slot>/iphone/<Sensor>.csv (gitignored),
                            manifest.csv, locations.csv, edges.csv, summary.json, ROUTE.md
```
Rebuild the sensor folders: `python -I phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py` (seconds).
Node names are the 25-Nov / night-run names (`exit5_door`, `lift_stairs5`, `y5302_point2`, `gate`, ...), so
`phase2/new/day3/names_25night.csv` maps them to graph-v2 places and the IDs match Tian's night track.

## Labels (from Tian's chat captions)
His phone saved every file as `point <date time>.zip` (only the first is named, `exit 5`). He sent each file to the
group right after recording it, with the place as the caption. `ingest_tian26.py` matched each file (in save-time order,
the time in its name) to Tian's first `<document omitted>` chat line at or after that time: 52 files, 52 lines, strict
one-to-one and in order, each caption before the next file was saved, gaps 7 to 45 s (`chat_gap_s`). Only the time and
the caption of those lines are kept (`chat_time`, `tian_caption`); the chat text is not in the repo.

Captions are ground truth (atas = 5F, bawah = 4F, esc/eska turun = escalator down, naik = up, cewe = female, men = male,
esit = exit, two places = walk A -> B, one place = stop); every row's reason says how it was read, and each caption's
kind (stop/walk) was checked against the duration (>= 40 s = stop). Two captions contradict their neighbours and were
resolved from the sequence and the duration (confidence medium):
- **"lift turun bawah" (10:22 START, chat 10:23:27), a 60 s stop = escalator down 4F.** It comes right after the walk
  "lt2b esc turun bawah" and before the walks "esc turun bawah esc naik bawah" and "esc turun bawah y4502", which both
  start at the 4F down escalator; the 4F lift/stairs stop is "stair lift bawah" (10:09). Its field is far from both of
  his 4F lift/stairs stops (40.8 and 49.2 uT x/y/z) and nearest his 4F escalator-up stops (14.9 and 17.4 uT;
  `medium_label_check.csv`).
- **"lt1b exit 10" (10:33 START, chat 10:34:09), a 5 s walk = LT1A -> exit 10 door 4F.** It starts right after the
  "lt1a" stop and ends before the "exit 10 bawah" stop.

Nothing was left out: all 52 rows are `ok`, and all 27 walks are corridors of the app's floor plan.
"stair lift" (no "bawah") is the 5F lift/stairs (1017.15 hPa, as his 5F stops; his 4F stops are about 1017.8).

Not recorded: a canteen stop (the run starts at the exit 5 door) and the 5F walk from the escalators to the exit 5 door
before "esit 5 toilet disabled men". Two walks start at the 4F down escalator ("esc turun bawah esc naik bawah" and
"esc turun bawah y4502"), as in his night run.

## His 25-Nov night takes named "lt2b"/"lt2a" a second time (`lt_night_check.csv`)
Five night takes 22:49 to 22:55 were left out of the night run (status `review`, ../2026-11-25-night/README.md) because
they sit where the route has LT1B and LT1A. This morning he recorded LT2A, LT2B, LT1B and LT1A on the same phone, so
`check_lt_night.py` compares them (mean x/y/z, first and last 5 s trimmed, uT):
- the 22:50 stop "lt2b" is 3.0 uT from this morning's LT1B (next LT1A 36.2, LT2B 61.4, LT2A 63.3);
- the 22:53 stop "lt2a" is 14.2 uT from this morning's LT1A (next LT1B 27.1, LT2A 61.0, LT2B 69.7);
- control: his night LT2A stop (22:34, ok) is 22.1 uT from this morning's LT2A (next LT1A 53.4); his night LT2B stop
  (22:37, ok) is 39.3 uT from LT2B and 42.2 from LT2A, so LT2B's field moved between the two runs.
- The three walks (start / end 1.5 s) are not conclusive: the same comparison on this morning's own LT1B -> LT1A walk puts
  its start nearest LT2B and its end nearest LT2A (the phone turns while walking).
This is evidence, not a relabel: the five rows stay `review` until the team decides.
