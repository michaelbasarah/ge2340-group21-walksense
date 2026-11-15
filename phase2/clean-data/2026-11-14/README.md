# GE2340 cleaned acquisition, 14 November 2026 — v4

**Relabeling update:** the user says Chris's location list is unreliable and will supply fresh labels. All existing candidate names/numbers are historical, untrusted and awaiting replacement. Use the blank [RELABEL_TEMPLATE.csv](RELABEL_TEMPLATE.csv) and [RELABEL_README.md](RELABEL_README.md) to name all 49 actual source recordings. Cleaned measurements and feature values are unchanged; no recording has been deleted or confidently identified as the extra physical visit.

The exported files are readable and internally coherent enough for analysis. This is a cleaned acquisition with provisional location associations, not a fully labeled or independently tested training set.

## Evidence and scope

- Starts at WhatsApp messages at 21:10 HK, retaining the first attached recording's actual start at 21:09:41.933. Chat send times and filenames never replace recording metadata.
- 26 actual barometer/magnetometer stop recordings, 23 actual accelerometer movement recordings, and one WiGLE export. All 49 sensor ZIPs pass integrity checks. All 52 attachments referenced after the cutoff are present; unrelated homework is excluded from processing.
- The user corrected a numbering typo: source Dat1–3 remain 1–3, source Dat5 becomes corrected Dat4, and source Dat26 becomes corrected Dat25. `corrected_location_list.csv` contains the complete corrected sequence **1–25**; corrected Dat4 is **study room 11**.
- There are still **26 real stop recordings versus 25 named locations**. The extra/repeat/test recording has not been identified. All recording-to-name links are explicitly provisional. Raw BM IDs, original chat and P filenames are unchanged; corrected location numbers are separate display fields, not raw recording ordinals. In the retained candidate mapping BM04 is currently unmatched, pending alignment. This does not identify BM04 as the actual extra visit.
- Measured values, units and sample tables remain unchanged; metadata tables receive separate corrected display-number fields. Derived timestamps and magnitudes are separate fields; the requested copied 5F connector is in `augmentation/`. No smoothing, resampling, numeric distance estimation or model training was performed.
- Three distinct phones: barometer/magnetometer and accelerometer use different iPhones, Wi-Fi uses Samsung. Their wall clocks were not independently synchronized.

## What the escalator readings show

Under the retained candidate alignment, pressure medians are BM15 vending 2 **1010.4649 hPa**; BM16 4F down landing **1011.0469**; BM17 5F up landing **1010.4795**; BM18 4F up landing **1011.0655**. The rise, fall, rise supports the user's descent / return upstairs / descent route. Floor labels come from route context and user clarification; pressure supports consistency rather than independently proving exact floor identities. The numbering correction does not force shifted location names onto raw chronological recording ordinals while the extra-recording alignment remains unresolved.

`P16-18 (esca bawah)` retains its original filename and recording time 21:27:39, after BM18 at 21:24:33. Its candidate raw endpoints remain BM16→BM18 (corrected display Dat15→Dat17). At the user's explicit request, its **664 accepted ACC15 samples are copied exactly** into `SYN_ACC_5F_CONNECTOR`, representing the assumed physical map connector BM13→BM17 (corrected display Dat12→Dat16, 5F down→up). All display-number associations remain provisional pending recording alignment. The copy is labeled `is_synthetic=true`, `derivation_type=user_requested_copy`, `historical_visit=false`, and `intended_use=assumed_map_connector_or_simulation`. This physical connector is not the actual chronological walk, which included vending machines and floor changes.

Same distance and same walker are recorded as user assumptions; numeric distance remains blank. Target acquisition times remain blank, with original times retained in explicit `source_*` columns. The copy shares `acquisition_group_id=ACC15` with its parent, so both remain together in any partition. Measured tables still have 23 accelerometer segments and 46,124 total sensor readings; the augmented manifest has 24 edges, including one proxy. No separate P15 recording is present for vending 2 → 4F down landing. `accelerometer_edges.csv` contains only measured segments and timing checks.

## Cleaning rules and row accounting

- Recorded START/PAUSE intervals map experiment-relative seconds to device wall-clock epoch, UTC and HK. Every event is retained in `recording_intervals.csv`.
- Negative experiment times, outside-interval samples, nonfinite/unparseable values, and exact duplicate time-and-value rows are quarantined in `excluded_sensor_rows.csv` with the original values and source row. Repeated values at different timestamps are retained.
- Input sensor readings: **46,171**; accepted: **46,124**; quarantined: **47**. Readings are never silently discarded. `sensor_quality.csv` includes raw and cleaned medians and per-sensor time coverage.
- Barometer files contain nine original readings each, including one negative-time reading. Accepted pressure readings therefore cover approximately 0.5–7 seconds, shorter than the roughly ten-second magnetometer interval. Rates are not forced to match.
- Accelerometer magnitude includes gravity; it is not linear acceleration, distance, or a step count. Magnetic vector axes depend on phone orientation. Magnitudes are derived for inspection, not a calibration claim.

## Wi-Fi limitations

The WiGLE CSV has 6,211 original data rows; 6,196 accepted Wi-Fi observations and 15 non-Wi-Fi rows separated. Original metadata and column values are retained. See `wifi_timestamp_audit.json` for source-code audit results and clock limitations.

`FirstSeen` is retained under its original name. **UTC is verified by the official WiGLE v1.6 format**; converting it to Hong Kong time adds eight hours and is not a phone-clock adjustment. The audit identifies upstream export time as `persisted_observation_location_time`, rather than radio acquisition time. The exact installed 2.111 source/binary was not matched to the inspected upstream source. Observation persistence is selective: 98.22% of consecutive repeated-BSSID records improve by at least 5 dB. These are incomplete, change-selected observations, not complete fresh fingerprints; do not fill missing access points with -100 dBm or any other assumed absence value.

Visible quality flags are `radio_acquisition_time_unavailable`, `cross_device_clock_alignment_unverified`, `selectively_persisted_not_complete_scan`, and `gps_not_indoor_ground_truth`. GPS coordinates and accuracy are original WiGLE metadata only, **not indoor ground truth or map coordinates**. The original `lt1`/`lt2` labels were retained; English lecture-theatre expansions are explicitly marked as inferred and do not determine floor numbers.

The provisional association file uses exact containment in each recorded stop interval with no nearest-time assignment or interpolation. 664 rows are provisionally associated across 22 stops, 5,532 remain unassigned. Stops with no exported FirstSeen row in their exact window: **BM01, BM12, BM14, BM22**. An empty window is not proof the phone saw no access points. Presence of a row is not proof of a complete scan. No static stop label is embedded in the Wi-Fi observation table. Timestamp seconds also have up-to-one-second boundary precision; `wifi/audit_per_stop_coverage.csv` keeps any boundary-overlap candidates separate from the exact stored-second matches.

## Files

- `sessions.csv`: source, device, actual recorded times and provisional labels for each ZIP.
- `sensor_samples.csv`, `sensors/*.csv`: accepted samples with units, original relative times, UTC/HK timestamps, source values and vector magnitudes.
- `sensor_quality.csv`, `excluded_sensor_rows.csv`: per-sensor checks and full quarantine records.
- `locations_provisional.csv`: source descriptions, translated labels, floor candidates and uncertainty; coordinates remain blank.
- `corrected_location_list.csv`: corrected 1–25 list, original source numbers and explicit unresolved candidate-recording links.
- `accelerometer_edges.csv`, `missing_movements.csv`: actual movement recordings, candidate endpoints, timing checks and gaps.
- `augmentation/derived_accelerometer_samples.csv`: 664 exact copied proxy samples, provenance and blank target times.
- `augmentation/augmented_accelerometer_edges.csv`, `augmentation/user_requested_override.json`: 23 measured edges plus the copied proxy and its authorization/assumptions.
- `wifi/observations.csv`: accepted exported Wi-Fi rows; `non_wifi_rows.csv` and `excluded_rows.csv` keep other input rows accountable.
- `wifi/stop_associations_provisional.csv`, `stop_coverage_provisional.csv`, `unassigned_observations.csv`: provisional exact-window matches and gaps.
- `diagnostic_timeline.svg`: self-contained plot of measured pressure, magnetic magnitude and recording intervals.
- `summary.json`, `validation.json`, `source_files.csv`: machine-readable counts and integrity evidence.
- `raw/`: byte-identical selected sensor attachments, original decompressed Wi-Fi CSV and source checksum. The full original export and chat transcript are deliberately omitted from this team copy and remain privately preserved by the data owner.

## Reproduce and verify

From this directory:

```bash
python3 clean.py --source 'raw/WhatsApp Chat with GE2340.zip'
python3 clean.py --validate-only
```

These commands work in the original local folder, where the full source export is preserved. **Recipients of the shareable ZIP must separately obtain the original export** and run `python3 clean.py --source '/path/to/WhatsApp Chat with GE2340.zip'` before source-level validation can run; the selected sensor-only attachments in the shareable ZIP do not replace that private source archive. The existing validation record describes the local full-source validation.

To incorporate a completed external timestamp audit, add `--wifi-audit /path/to/audit.json`; the audit is copied into this dataset. Rerunning without that option preserves an existing audit automatically.

Validation checks source/attachment hashes, row accounting, finite values and intervals, Wi-Fi associations, complete corrected numbering 1–25, preserved original source numbers/raw BM IDs, explicit unresolved alignment, unchanged measured counts, exact authorized proxy copy, shared parent/group IDs and blank target acquisition times. It does not certify location ground truth, device clock synchronization, or Wi-Fi scan completeness. Original v1, v2 and v3 archives remain intact; `package.py` creates `ge2340-cleaned-2026-11-14-v4.zip`.

Remaining work is identifying the extra/repeat/test recording to reconcile 26 stop recordings with 25 corrected named locations, independent device-clock alignment, more complete Wi-Fi acquisition if needed, and map coordinates/distances. Preserve one visit as one acquisition unit: adjacent samples from one stop do not constitute independent train/test visits. The shareable ZIP deliberately excludes the full-chat archive and relevant chat transcript; the original remains preserved privately in the local raw folder.

<!-- V4_FEATURES -->
## Processing history and first-pass feature tables

Start with [PROCESSING_LOG.md](PROCESSING_LOG.md) for every completed stage and pending decision. [features/FEATURES_EXPLAINED.md](features/FEATURES_EXPLAINED.md) explains an actual stop and movement example in plain language.

- `recording_review.csv`: 26 actual stop ZIPs, time, source filename/hash, provisional candidate label and confirmation fields. Open in Excel/LibreOffice to identify the extra/repeat/test recording. Existing `review_*` entries survive reruns and are not automatically applied to labels. The corrected location list has 25 description entries (including revisits); this difference is unrelated to the copied connector.
- `features/stop_features.csv`: one summary row per actual stop (26), including pressure and magnetic statistics, time spans, uncertainty and Wi-Fi candidate counts.
- `features/wifi_by_stop_bssid.csv`: 663 observed stop/BSSID groups summarize 664 candidate observations; 662 groups have only one row, so their medians are single exported readings. No absent-AP filling.
- `features/movement_features.csv`: 23 measured movement summaries and one explicitly copied proxy, with shared parent/group provenance and blank target times for the proxy.
- `features/feature_manifest.json`, `feature_validation.json`: source table hashes, counts and checks. The original cleaned readings and acquisition tables are unchanged by feature extraction.

Reproduce features after cleaning with `python3 feature_extraction.py`, verify with `python3 feature_extraction.py --validate-only`, then rebuild v4 with `python3 package.py`. The feature script adds descriptive statistics only: no two-second slicing, interpolation, double integration, distances, step counts, calibration or training. Processing can proceed to these summaries before compass/map-distance work.
