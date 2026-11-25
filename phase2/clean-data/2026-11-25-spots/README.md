# 25 November 2026: floor-5 round + spot recordings (partial export), now `2026-11-25-spots/`

> **Moved here on 25 Nov** (PROCESS-LOG, the entry "partial 25-Nov folder moved to 2026-11-25-spots"; `git mv`, nothing deleted). This
> folder was `phase2/clean-data/2026-11-25/`, built from a partial WhatsApp export. Dicta's complete 25-Nov dataset (one
> continuous 3-phone pass, floor 5 + floor 4) now lives in `../2026-11-25/` and is the authoritative 25-Nov data. What this
> folder adds on top of hers is the spot recordings (ip16 = Tian's iPhone17,4 and s24 = Michael's SM-S9280); its round
> recordings (ip18 + a56) were the same recordings as hers and were deleted from `raw/attachments/` on 26 Nov (verified byte-identical).

*Internal team notes, not report text.* Every count below is from `clean/summary.json`, `clean/labels_used.csv`,
`raw/source_files.csv` or `raw/missing_from_export.csv`.

## What is here

```
2026-11-25-spots/
├── raw/attachments/        phyphox ZIPs + one WiGLE log, byte-identical from the WhatsApp export (16 files; the 36 round ZIPs
│                           that are byte-identical to Dicta's were deleted on 26 Nov, see below)
├── raw/source_files.csv    file, sha256, size, sender (first name), chat time (52 rows: still lists the 36 deleted files, as a record)
├── raw/missing_from_export.csv   media messages of 25 Nov after 17:30 that the export did not contain (73)
├── labels_override.csv     hand decisions that beat the name rules (the 11 'DOC-...' files)
├── duplicates_vs_2026-11-25.csv   which of our files were already in Dicta's ../2026-11-25 (scripts/find_duplicates.py) + column deleted_2026-11-26
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
`exclude_sources`) leaves the 36 out, so every recording is in the training set once; what `25spots` adds is the 15 labelled spot stops (ip16 4, s24 11, all high confidence after the 26-Nov relabel) and the S24 WiGLE log.

**Deleted on 26 Nov (user-approved, PROCESS-LOG entry 68):** the 36 `byte_identical` ZIPs were removed from `raw/attachments/`
(`git rm`, so they stay in history). Before deleting, SHA-256 was recomputed for all 52 files here and for all 116 top-level
files of `../2026-11-25/raw/` plus every member of her container ZIPs (872 distinct hashes): exactly these 36 match one of hers
byte for byte, every one is a top-level file of hers (none only inside a container), and each reaches her clean tree
(`dicta_clean_folder` in the CSV). The other 16 files (the 11 `DOC-...` S24 ZIPs, the WiGLE log, and Tian's 4 spot ZIPs) match
nothing of hers and no same-device recording of hers starts within 30 s of them, so all 16 stay. The CSV is kept; its last column
`deleted_2026-11-26` gives, per row, the verified sha256 match and where her copy lives (or why the file was kept). Do not rerun
`scripts/find_duplicates.py` now: it reads `raw/attachments/`, which no longer holds the 36, and would overwrite the CSV (and
`../../new/day3` needs its `exclude_sources` rows). `clean/` was rebuilt by `build_clean.py` from the 16 files left (see Labels).

## Who recorded what (device read from each ZIP's `meta/device.csv`)

| track | who | phone (model) | slot | recordings in the export |
|---|---|---|---|---|
| round | Benedicta | ip18 (iPhone19,2) | iphone | 19 (stops + walks, floor 5, 17:35-18:10), deleted 26 Nov (in Dicta's set) |
| round | Chris | a56 (SM-A566B) | a56 | 17, deleted 26 Nov (in Dicta's set) |
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
- 15 of 15 recordings labelled, all high confidence: 4 by the name rules (Tian's ip16 files) and 11 by the user's own file
  names (`label_source` `user_filename`; `user correction 2026-11-26` for WA0052). 0 duplicates. Floor check (iPhone
  barometer, consecutive stops of one handset, 0.3 hPa): 3 of 3 pairs agree with the labels (`floor_check.csv`). (Before
  the 26-Nov deletion `clean/` held 51 recordings; the 36 round recordings are now only in Dicta's tree.)
- **Michael's 11 S24 stops (user-confirmed 2026-11-26).** WhatsApp renamed his files `DOC-...`, but each file's send time
  (`raw/source_files.csv`) equals the chat time of his named message, so the names are known. They are in
  `labels_override.csv` (column `label_source`, which `build_clean.py` now copies into `labels_used.csv`): WA0051 esca turun lv5
  (escalator_down), WA0052 esca naik lv4 (escalator_up: the user corrected 2026-11-26 that it was on the 5th floor although the
  name says lv4), WA0053 female toilet, WA0054 sr9, WA0055 male disb tlt (disabled_toilet, 5F), WA0056 liftstair5 (lift_stairs),
  WA0057 esca turun lv4 (escalator_down_4F), WA0058 esca naik lv4 (escalator_up_4F), WA0059 exit 10 door lvl 4 (exit_10_4F),
  WA0060 ex 5 door lvl 4 (exit_5_4F; 68 s, 4 time events = paused and resumed, loaded as one stop), WA0061 liftstair5 lt4
  (lift_stairs_4F). They replace the 3 earlier timing guesses (WA0052, WA0055, WA0056), which were wrong (PROCESS-LOG entry 69).
  The S24 barometer does not follow the floors (see entry 69); the user's labels are kept.

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
