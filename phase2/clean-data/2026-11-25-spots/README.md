# 25 November 2026: floor-5 round + spot recordings (partial export), now `2026-11-25-spots/`

> **Moved here on 25 Nov** (PROCESS-LOG, the entry "partial 25-Nov folder moved to 2026-11-25-spots"; `git mv`, nothing deleted). This
> folder was `phase2/clean-data/2026-11-25/`, built from a partial WhatsApp export. Dicta's complete 25-Nov dataset (one
> continuous 3-phone pass, floor 5 + floor 4) now lives in `../2026-11-25/` and is the authoritative 25-Nov data. What this
> folder adds on top of hers is the spot recordings (ip16 = Tian's iPhone17,4 and s24 = Michael's SM-S9280); its round
> recordings (ip18 + a56) are the same recordings as hers.

*Internal team notes, not report text.* Every count below is from `clean/summary.json`, `clean/labels_used.csv`,
`raw/source_files.csv` or `raw/missing_from_export.csv`.

## What is here

```
2026-11-25-spots/
├── raw/attachments/        phyphox ZIPs + one WiGLE log, byte-identical from the WhatsApp export (52 files)
├── raw/source_files.csv    file, sha256, size, sender (first name), chat time
├── raw/missing_from_export.csv   media messages of 25 Nov after 17:30 that the export did not contain (73)
├── labels_override.csv     hand decisions that beat the name rules (the 11 'DOC-...' files)
├── duplicates_vs_2026-11-25.csv   which of our files are already in Dicta's ../2026-11-25 (scripts/find_duplicates.py)
├── scripts/index_sources.py   hashes + sender per file (+ missing list when given the chat .txt, which stays private)
├── scripts/find_duplicates.py   our raw files vs Dicta's ../2026-11-25/raw -> duplicates_vs_2026-11-25.csv
├── scripts/build_clean.py     raw -> clean/ (same layout as 2026-11-24: floor*/stops|walks/<folder>/<phone>/<Sensor>.csv)
└── clean/   manifest.csv, labels_used.csv, locations.csv, edges.csv, floor_check.csv, duplicates.csv, wifi/, summary.json
             (floor4/, floor5/ and wifi/observations.csv are gitignored: rebuild with build_clean.py, a few seconds)
```

Rebuild: `python -I phase2/clean-data/2026-11-25-spots/scripts/build_clean.py` (the day-3 `run_all.sh` does it first).

## Overlap with Dicta's complete set (`duplicates_vs_2026-11-25.csv`)

`scripts/find_duplicates.py` compares every file in `raw/attachments/` with every recording in `../2026-11-25/raw/`
(her nested `attachments.zip` included): SHA-256 of the ZIP bytes, then same device model + phyphox START within 2 s.
Result: **36 byte-identical** (all the round recordings: ip18 19, a56 17; none more found by device + START),
**16 unique** (ip16 4, s24 11, and the WiGLE log `DOC-20261125-WA0062.gz`). The CSV sits at the folder root because
`build_clean.py` rebuilds `clean/` from scratch. The day-3 session `25spots` (`phase2/new/day3/config.json`,
`exclude_sources`) leaves the 36 out, so every recording is in the training set once; what `25spots` adds is the 7
labelled spot stops (ip16: escalator_down, sr9, escalator_down_4F, escalator_up_4F; s24: escalator_down,
escalator_down_4F, escalator_up_4F, medium confidence) and the S24 WiGLE log. The 8 unlabelled S24 files stay out.

**For the user to decide (not done):** the 36 duplicate raw ZIPs below are stored byte-identically in
`../2026-11-25/raw/` too. They could be deleted from this folder without losing data; they are kept until the user
says so.

- `Canteen 2026-11-25 17-37-05.zip` = `../2026-11-25/raw/Canteen 2026-11-25 17-37-05.zip`
- `Canteen ke esca down 2026-11-25 18-10-56.zip` = `../2026-11-25/raw/Canteen ke esca down 2026-11-25 18-10-56.zip`
- `Canteen ke exit 5 door 2026-11-25 17-38-21.zip` = `../2026-11-25/raw/Canteen ke exit 5 door 2026-11-25 17-38-21.zip`
- `Esca up 2026-11-25 18-08-14.zip` = `../2026-11-25/raw/Esca up 2026-11-25 18-08-14.zip`
- `Esca up ke kantin 2026-11-25 18-09-41.zip` = `../2026-11-25/raw/Esca up ke kantin 2026-11-25 18-09-41.zip`
- `Exit 10 door 2026-11-25 18-02-18.zip` = `../2026-11-25/raw/Exit 10 door 2026-11-25 18-02-18.zip`
- `Exit 10 door ke kantin 2026-11-25 18-03-42.zip` = `../2026-11-25/raw/Exit 10 door ke kantin 2026-11-25 18-03-42.zip`
- `Exit 5 door 2026-11-25 17-40-32.zip` = `../2026-11-25/raw/Exit 5 door 2026-11-25 17-40-32.zip`
- `Exit 5 door ke toilet cowo 2026-11-25 17-41-24.zip` = `../2026-11-25/raw/Exit 5 door ke toilet cowo 2026-11-25 17-41-24.zip`
- `Sr9 2026-11-25 17-51-54.zip` = `../2026-11-25/raw/Sr9 2026-11-25 17-51-54.zip`
- `Sr9 ke y5202 2026-11-25 17-52-59.zip` = `../2026-11-25/raw/Sr9 ke y5202 2026-11-25 17-52-59.zip`
- `Toilet cewe 2026-11-25 17-58-59.zip` = `../2026-11-25/raw/Toilet cewe 2026-11-25 17-58-59.zip`
- `Toilet cewe ke exit 10 door 2026-11-25 18-00-32.zip` = `../2026-11-25/raw/Toilet cewe ke exit 10 door 2026-11-25 18-00-32.zip`
- `Toilet cowo 2026-11-25 17-44-43.zip` = `../2026-11-25/raw/Toilet cowo 2026-11-25 17-44-43.zip`
- `Toilet cowo ke y5302 2026-11-25 17-46-09.zip` = `../2026-11-25/raw/Toilet cowo ke y5302 2026-11-25 17-46-09.zip`
- `Y5202 2026-11-25 17-55-10.zip` = `../2026-11-25/raw/Y5202 2026-11-25 17-55-10.zip`
- `Y5202 ke toilet cewe 2026-11-25 17-56-17.zip` = `../2026-11-25/raw/Y5202 ke toilet cewe 2026-11-25 17-56-17.zip`
- `Y5302 2026-11-25 17-48-05.zip` = `../2026-11-25/raw/Y5302 2026-11-25 17-48-05.zip`
- `Y5302 ke sr9 2026-11-25 17-49-32.zip` = `../2026-11-25/raw/Y5302 ke sr9 2026-11-25 17-49-32.zip`
- `esca naik 2026-11-25 18-07-50.zip` = `../2026-11-25/raw/esca naik 2026-11-25 18-07-50.zip`
- `esca naik to kantin 2026-11-25 18-09-54.zip` = `../2026-11-25/raw/esca naik to kantin 2026-11-25 18-09-54.zip`
- `exit 10 door ke kantin 2026-11-25 18-03-36.zip` = `../2026-11-25/raw/exit 10 door ke kantin 2026-11-25 18-03-36.zip`
- `exit 5 2026-11-25 17-40-19.zip` = `../2026-11-25/raw/exit 5 2026-11-25 17-40-19.zip`
- `ext 10 2026-11-25 18-02-16.zip` = `../2026-11-25/raw/ext 10 2026-11-25 18-02-16.zip`
- `ext 5 to toilet cwk 2026-11-25 17-41-14.zip` = `../2026-11-25/raw/ext 5 to toilet cwk 2026-11-25 17-41-14.zip`
- `kantin 2026-11-25 17-36-50.zip` = `../2026-11-25/raw/kantin 2026-11-25 17-36-50.zip`
- `kantin exit 5 2026-11-25 17-38-36.zip` = `../2026-11-25/raw/kantin exit 5 2026-11-25 17-38-36.zip`
- `kantin to esca turun 2026-11-25 18-10-48.zip` = `../2026-11-25/raw/kantin to esca turun 2026-11-25 18-10-48.zip`
- `study room 2026-11-25 17-51-27.zip` = `../2026-11-25/raw/study room 2026-11-25 17-51-27.zip`
- `studyroom to y5 202 2026-11-25 17-52-58.zip` = `../2026-11-25/raw/studyroom to y5 202 2026-11-25 17-52-58.zip`
- `toilet cewe 2026-11-25 17-59-01.zip` = `../2026-11-25/raw/toilet cewe 2026-11-25 17-59-01.zip`
- `toilet cewe to ext 10 2026-11-25 18-00-08.zip` = `../2026-11-25/raw/toilet cewe to ext 10 2026-11-25 18-00-08.zip`
- `tolet cowo to y5302 2026-11-25 17-46-02.zip` = `../2026-11-25/raw/tolet cowo to y5302 2026-11-25 17-46-02.zip`
- `y5202 to toilet cewe 2026-11-25 17-56-08.zip` = `../2026-11-25/raw/y5202 to toilet cewe 2026-11-25 17-56-08.zip`
- `y5302 2026-11-25 17-47-42.zip` = `../2026-11-25/raw/y5302 2026-11-25 17-47-42.zip`
- `y5302 to study room 2026-11-25 17-49-14.zip` = `../2026-11-25/raw/y5302 to study room 2026-11-25 17-49-14.zip`

## Who recorded what (device read from each ZIP's `meta/device.csv`)

| track | who | phone (model) | slot | recordings in the export |
|---|---|---|---|---|
| round | Benedicta | ip18 (iPhone19,2) | iphone | 19 (stops + walks, floor 5, 17:35-18:10) |
| round | Chris | a56 (SM-A566B) | a56 | 17 |
| spots | Tian | ip16 (iPhone17,4) | iphone | 4 stops (17:41-17:52) |
| spots | Michael | s24 (SM-S9280) | s24 | 11 stops (17:40-18:05) + WiGLE log `DOC-20261125-WA0062.gz` (17:40-18:17 HK, 4461 Wi-Fi rows) |

A track = the stops one group walked in order. The barometer floor tracking and the Wi-Fi assignment run per track
(Michael's S24 scanned Wi-Fi where Michael was, not where the round was).

## Labels (`clean/labels_used.csv`, one row per recording, with confidence and reason)

- Names are parsed per recording by explicit rules in `build_clean.py` (`label_text`): place words (kantin/canteen,
  toilet cowo/cwk -> male_toilet, toilet cewe -> female_toilet, study room/sr9 -> sr9, eska/esca naik/turun ->
  escalator_up/down, exit/ext 5/10 -> exit_5/exit_10, ...), floor words (bawah/lantai 4/lt4/lvl 4 -> floor 4,
  atas/lv5 -> floor 5). A place that exists on one floor fixes the floor; an escalator/exit/lift without a floor word
  takes the floor of the track's previous labelled recording. Stop = at least 30 s (as 24 Nov), walk = shorter.
- 43 of 51 recordings labelled: 34 high, 9 medium confidence. 0 duplicates. Floor check (iPhone barometer,
  consecutive stops of one handset, 0.3 hPa): 11 of 11 pairs agree with the labels (`floor_check.csv`).
- **Medium, to confirm:** the 3 Michael S24 recordings labelled by timing (WhatsApp renamed his files `DOC-...`, the
  names are lost): `DOC-...WA0052` = escalator_down (starts 9 s after Tian's "eska turun atas"),
  `WA0055` = escalator_down_4F (5 s after "eska turun bawah"), `WA0056` = escalator_up_4F (3 s after "eska naik bawah").
  The other 6 medium rows are the round's exit 5, exit 10 and escalator-up stops (both phones each): no floor word in
  the name, so the floor (5) comes from the track context; the iPhone barometer agrees (`floor_check.csv`).
- **Unlabelled, not used (8):** Michael's S24 `DOC-...WA0051, 53, 54, 57, 58, 59, 60, 61` (no name, no simultaneous
  labelled recording; WA0054 overlaps Tian's sr9 by about 30 s only; WA0060 was paused and resumed, 68 s).

## Missing from this export (`raw/missing_from_export.csv`)

The export has 40 named ZIPs of 25 Nov; WhatsApp wrote `<Media omitted>` for 73 later media messages:
- Benedicta 35 (all captioned): the rest of the floor-5 round from 18:13 (esca down, male disabled toilet, lift/stairs 5,
  y5401, y5302 back) and the whole floor-4 round 18:34-19:15.
- Chris 37 (no captions): his toilet cowo stop at 17:45 and the same round from 18:13.
- Tian 1: `WalkSense ranking by phone.xlsx` (17:45).
- Not in the chat at all: Chris's Y5202 stop (his walks into and out of Y5202 are there).
- Michael's S24 file names (the files are here as `DOC-...`).

To add them: drop the ZIPs (and any WiGLE `.csv.gz`) into `raw/attachments/`, run `scripts/index_sources.py` (with the
chat .txt path for the senders) and `scripts/build_clean.py`, then the day-3 pipeline. A named re-export of a file that
is already here as `DOC-...` is recognised as the same recording (same model + START time) and replaces it
(`clean/duplicates.csv`); delete its row in `labels_override.csv` if the name now says what it is.

## Notes

- `DOC-20261125-WA0000.gz` in the export is byte-identical to `2026-11-24/sesi2/raw/WigleWifi_20261124235955.csv.gz`
  (a 24-Nov log) and was not copied here.
- The round's 5F escalator-up stop: Chris started 18:06:12, Benedicta 18:06:57 (45 s apart, one stop).
