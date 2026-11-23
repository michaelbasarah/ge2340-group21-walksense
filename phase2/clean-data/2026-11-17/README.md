# GE2340 cleaned acquisition, 17 November 2026 — v1

The exported files are readable and internally coherent enough for analysis. This is a cleaned acquisition with **provisional, route-inferred** location labels, not an independently map-verified or model-tested training set.

This is the second GE2340 acquisition. Unlike the 14 November set, the 23 movement recordings were already labelled by their filenames (e.g. `Sr11 10` = study room 11 → study room 10), the stops form one continuous walk, there is no numbering typo, and no synthetic/duplicated connector was added. Every measurement here is real.

## Evidence and scope

- 26 actual barometer/magnetometer stop recordings (`poin ...zip`), 23 actual accelerometer movement recordings (named by route), and one WiGLE export. All 49 sensor ZIPs pass integrity checks.
- Stops are numbered **BM01–BM26** in recording order. Each stop also carries a provisional location label inferred only from the names of the movement recordings immediately before and after it. 20 stop labels are confirmed on both sides (the preceding movement's destination equals the following movement's origin); the rest are escalator landings or the two single-sided route endpoints.
- The walk is a loop that revisits Y5, the toilet, Exit 5, the canteen and Y4. `corrected_location_list.csv` lists all 26 ordered checkpoints; `locations_provisional.csv` carries the per-stop confidence and notes.
- Three distinct phones: the barometer/magnetometer stops use one iPhone, the accelerometer movements use a different iPhone, and Wi-Fi uses a Samsung. Their wall clocks were not independently synchronized.
- No smoothing, resampling, numeric distance estimation, step counting, calibration or model training was performed. Raw archives are preserved byte-identically in `raw/attachments/`.

## What the escalator readings show

Pressure medians across the descent are BM11 canteen **1014.449768 hPa**, BM12 upper landing **1014.466095**, BM13 lower landing **1015.035019**, BM14 Y4 **1015.036697**. On the way back up, BM22 Y4 **1015.065002**, BM23 lower landing **1015.06218**, BM24 upper landing **1014.476929**, BM25 canteen **1014.493179**. The pressure change across the escalator supports a real floor change; it does not independently prove exact floor identities. Floor numbers are left blank pending a marked indoor map.

## Cleaning rules and row accounting

- Recorded START/PAUSE intervals map experiment-relative seconds to device wall-clock epoch, UTC and HK. Every event is retained in `recording_intervals.csv`.
- Negative experiment times, outside-interval samples, nonfinite/unparseable values, and exact duplicate time-and-value rows are quarantined in `excluded_sensor_rows.csv` with the original values and source row. Repeated values at different timestamps are retained.
- Input sensor readings: **104,504**; accepted: **101,436**; quarantined: **3,068**. Readings are never silently discarded. `sensor_quality.csv` includes raw and cleaned medians and per-sensor time coverage.
- Accepted counts by sensor: {'magnetometer': 77930, 'barometer': 700, 'accelerometer': 22806}.
- Each barometer file begins with one negative-experiment-time reading (quarantined); the remaining pressure readings span the recording. Magnetometer runs at roughly 100 Hz. Accelerometer magnitude includes gravity; it is not linear acceleration, distance, or a step count. Magnetic vector axes depend on phone orientation.

## Wi-Fi limitations

The WiGLE CSV has 3,087 original data rows; 3,085 accepted Wi-Fi observations and 2 non-Wi-Fi (LTE) rows separated. Original metadata and column values are retained. See `wifi/AUDIT.md` and `wifi_timestamp_audit.json`.

`FirstSeen` is retained under its original name and interpreted as **UTC** (official WiGLE v1.6 format); Hong Kong time adds eight hours. It is a persisted observation time, not radio acquisition time. These are selectively persisted observations, not complete fresh scans; do not fill missing access points with -100 dBm or any assumed absence value. GPS coordinates are original metadata only, **not indoor ground truth**.

The provisional association uses exact containment of the stored FirstSeen second inside a recorded stop interval, with no nearest-time assignment or interpolation. 961 rows are provisionally associated across 15 stops; 2,124 remain unassigned. Stops with no exported FirstSeen row in their exact window: **BM08, BM14, BM15, BM16, BM17, BM18, BM19, BM21, BM22, BM24, BM25, BM26**. An empty window is not proof the phone saw no access points; a present row is not proof of a complete scan.

## Files

- `sessions.csv`: source, device, actual recorded times and provisional labels for each ZIP.
- `sensor_samples.csv`, `sensors/*.csv`: accepted samples with units, original relative times, UTC/HK timestamps, source values and vector magnitudes.
- `sensor_quality.csv`, `excluded_sensor_rows.csv`: per-sensor checks and full quarantine records.
- `locations_provisional.csv`, `corrected_location_list.csv`: the 26 ordered stops, route-inferred labels and confidence.
- `accelerometer_edges.csv`, `missing_movements.csv`: the 23 measured movements with their bounding stops and timing checks, and the 2 consecutive-stop gaps with no walk recording.
- `wifi/observations.csv`, `stop_associations_provisional.csv`, `stop_coverage_provisional.csv`, `unassigned_observations.csv`, `non_wifi_rows.csv`, `excluded_rows.csv`, `AUDIT.md`: Wi-Fi cleaning and provisional exact-window matches.
- `diagnostic_timeline.svg`: self-contained plot of measured pressure, magnetic magnitude and recording intervals.
- `summary.json`, `validation.json`, `source_files.csv`: machine-readable counts and integrity evidence.
- `features/`: first-pass descriptive statistics (see `features/FEATURES_EXPLAINED.md`).
- `raw/`: byte-identical source ZIPs/GZIP (`raw/attachments/`) and the decompressed Wi-Fi CSV.

## Reproduce and verify

From this directory:

```bash
python3 clean.py --source "../../../../Data (17-11)"
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
```

The first run copies the loose ZIPs and the WiGLE GZIP into `raw/attachments/` byte-for-byte; later runs can reproduce from those preserved copies without the external folder. Validation checks attachment hashes, row accounting, finite values and intervals, Wi-Fi associations, the 26/23 recording split, movement-to-stop adjacency and that no synthetic rows exist. It does not certify location ground truth, device clock synchronization, or Wi-Fi scan completeness.

## Remaining work

Confirm stop labels and floor numbers against a marked indoor plan; add map coordinates and distances; decide whether complete Wi-Fi logging and independently synchronized repeat visits are needed; then choose a baseline and independent evaluation visits. No training or train/test slicing has happened. Preserve one visit as one acquisition unit: adjacent samples from one stop are not independent train/test visits.

<!-- V1_FEATURES -->
## Processing history and first-pass feature tables

Start with [PROCESSING_LOG.md](PROCESSING_LOG.md) for every completed stage and pending decision. [features/FEATURES_EXPLAINED.md](features/FEATURES_EXPLAINED.md) explains an actual stop and movement example in plain language.

- `recording_review.csv`: 26 actual stop ZIPs, time, source filename/hash, provisional route-inferred label and confirmation fields. Open in Excel/LibreOffice to confirm names, floors and any repeat/test recording. Existing `review_*` entries survive reruns and are not automatically applied to labels.
- `features/stop_features.csv`: one summary row per actual stop (26), including pressure and magnetic statistics, time spans and Wi-Fi candidate counts.
- `features/movement_features.csv`: 23 measured movement summaries (no synthetic rows), each with its bounding stops and acceleration statistics.
- `features/wifi_by_stop_bssid.csv`: one row per observed stop/BSSID group, from the selectively persisted observations. No absent-AP filling.
- `features/feature_manifest.json`, `feature_validation.json`: source table hashes, counts and checks. The original cleaned readings and acquisition tables are unchanged by feature extraction.

Reproduce features after cleaning with `python3 feature_extraction.py`, verify with `python3 feature_extraction.py --validate-only`. The feature script adds descriptive statistics only: no two-second slicing, interpolation, double integration, distances, step counts, calibration or training.
