# 25 November 2026: floor-5 round + spot recordings (partial export)

*Internal team notes, not report text.* Every count below is from `clean/summary.json`, `clean/labels_used.csv`,
`raw/source_files.csv` or `raw/missing_from_export.csv`.

## What is here

```
2026-11-25/
├── raw/attachments/        phyphox ZIPs + one WiGLE log, byte-identical from the WhatsApp export (52 files)
├── raw/source_files.csv    file, sha256, size, sender (first name), chat time
├── raw/missing_from_export.csv   media messages of 25 Nov after 17:30 that the export did not contain (73)
├── labels_override.csv     hand decisions that beat the name rules (the 11 'DOC-...' files)
├── scripts/index_sources.py   hashes + sender per file (+ missing list when given the chat .txt, which stays private)
├── scripts/build_clean.py     raw -> clean/ (same layout as 2026-11-24: floor*/stops|walks/<folder>/<phone>/<Sensor>.csv)
└── clean/   manifest.csv, labels_used.csv, locations.csv, edges.csv, floor_check.csv, duplicates.csv, wifi/, summary.json
             (floor4/, floor5/ and wifi/observations.csv are gitignored: rebuild with build_clean.py, a few seconds)
```

Rebuild: `python -I phase2/clean-data/2026-11-25/scripts/build_clean.py` (the day-3 `run_all.sh` does it first).

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
