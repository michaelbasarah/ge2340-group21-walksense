# Processing log — GE2340 acquisition of 14 November 2026

This is the record of meaningful processing decisions. Add new decisions/results below as work continues; do not rewrite the original acquisition evidence. Versions v1–v4 are completed local artifacts. No training, upload or publication has been performed.

| Step | Completed work and reason | Evidence / result |
| --- | --- | --- |
| 1. Find the export | Read `WhatsApp Chat with GE2340.zip` from Windows Downloads. Start at messages sent 21:10 on 14 November; use internal recording times rather than sending times. | Source SHA-256 `7f7e42c00513de2abf974d98b58bd2a56fe24d18c29542ae56b6da6fdc356a34`. First included recording actually starts 21:09:41.933 HK. |
| 2. Inventory the actual files | Check each referenced attachment and each nested sensor ZIP. Preserve original source and selected sensor attachments byte-for-byte. | 49 sensor ZIPs = 26 barometer/magnetometer recordings + 23 accelerometer recordings. One Wi-Fi GZIP. All 52 attachment references after the cutoff exist; unrelated homework is not processed. |
| 3. Read recording metadata | Use each phyphox `meta/time.csv` START/PAUSE event to map relative seconds to device epoch time, UTC and HK. Preserve actual device identity. | Two iPhones record the sensor streams; Samsung records Wi-Fi. No independent inter-phone clock calibration or offset is claimed. |
| 4. Clean sensor readings (v1) | Keep finite parseable readings inside their actual acquisition interval. Quarantine negative-time/outside-window rows with their full source values; no smoothing or resampling. | 46,171 original readings = 46,124 accepted + 47 quarantined negative-time readings. Accepted: 208 pressure, 25,981 magnetic and 19,935 acceleration readings. |
| 5. Explain different sampling rates | Keep separate pressure and magnetic readings rather than forcing rows to align by index. | Each barometer file has 9 original readings including one negative time; 8 accepted readings span approximately 0.5–7 seconds. Magnetic recordings last about 10 seconds at approximately 100 Hz. |
| 6. Inspect route and accelerators | Treat accelerometer files as movements between candidate stops. Use original P filenames and actual intervals. | 22 movements fall between candidate endpoint stop windows. Original `P16–18` is stable ID ACC15 and is recorded after both candidate endpoint visits; retain it as a later connector visit. No separate P15 file is present. |
| 7. Incorporate escalator explanation | User clarified: 5F down landing → vending 1 → vending 2 → 4F down landing. Barometer/magnetometer include upstairs/downstairs side trip; accelerometer covers lower-floor down-to-up connector. | Retained candidate BM15/16/17/18 clean pressure medians: 1010.4649 / 1011.0469 / 1010.4795 / 1011.0655 hPa. Rise/fall/rise supports the floor-change sequence. This does not independently establish all location labels. |
| 8. Audit Wi-Fi export | Separate 6,196 WIFI from 15 LTE rows; keep provenance. Confirm UTC format and inspect observation persistence in official format/upstream code. | Zero exact duplicate Wi-Fi rows. FirstSeen is stored location-observation time; selective persistence is consistent with 98.22% of repeated-BSSID changes being RSSI improvements ≥5 dB. Exact installed 2.111 source/binary was not matched to current upstream. See `wifi/AUDIT.md`. |
| 9. Candidate Wi-Fi-to-stop association | Normalize UTC/HK display, then retain rows whose exported second falls inside an actual stop interval. Do not interpolate or infer absent access points. | 664 candidate observations across 22 stops. BM01/BM12/BM14/BM22 have no exported row in the exact window. 2,244 inter-stop rows and 3,288 outside the full sensor span remain unassigned. No fresh-scan or complete-fingerprint claim. |
| 10. Preserve and package v1 | Generate readable CSVs, manifests, QC, timeline and reproducible cleaner. | Source-level row accounting/hashes validated. Private full-chat source stays local; shareable archive omits the whole chat and transcript. |
| 11. Apply user's requested copy (v2) | User explicitly allowed duplicating the lower-floor accelerometer connector for the assumed 5F connector, stating same distance and same person. | Copy all 664 accepted ACC15 samples into separate `SYN_ACC_5F_CONNECTOR`; retain parent/provenance and acquisition group ACC15. Mark synthetic, user-requested, nonhistorical, intended for assumed map connector/simulation. Target acquisition times and numeric distance remain blank. Measured tables unchanged. |
| 12. Correct numbering typo (v3) | User explained the skipped 4 in the source list was a typo. Keep source 1–3 and shift original 5–26 to corrected 4–25. Preserve original numbers and filenames. | `corrected_location_list.csv` is complete 1–25. Corrected Dat4 is study room 11. There are still 26 real stop ZIPs versus 25 descriptions. All location-to-recording links remain candidates. BM04 was the unmatched slot in the earlier ordinal mapping, not proof of which recording is extra. |
| 13. Prepare review table (v4) | Make `recording_review.csv` with one row per actual stop ZIP, internal start/end, source name, candidate association and blank review fields. | Twenty-six rows let the group identify the repeat/test/extra recording. No file is deleted or relabeled as confirmed while that alignment is unknown. |
| 14. Extract first-pass features (v4) | Summarize each complete cleaned recording using counts, means, medians, sample SDs, ranges and time coverage. Summarize actual Wi-Fi candidate groups without missing-AP values. | `features/stop_features.csv`: 26 rows. `wifi_by_stop_bssid.csv`: 663 actual groups, counts sum to 664; 662 contain a single row and one contains two. These medians usually equal one exported reading, not repeated ten-second scan averages. `movement_features.csv`: 23 measured rows + one proxy with features copied from its parent. Original readings unchanged. |
| 15. Validate and explain v4 | Check feature source counts/statistics, grouping totals, copied-feature identity and blank proxy times. Document an actual BM01/ACC01 worked example. | `features/feature_validation.json`, `feature_manifest.json`, `FEATURES_EXPLAINED.md`. No NaN, invented distance/steps or false calibration claims. |

## How 26 versus 25 was counted

The **26** comes directly from 26 distinct nested `point ...zip` files containing `Barometer.csv` and `Magnetometer.csv`: 26 unique filenames, 26 unique ZIP SHA-256 hashes and 26 unique recording start times. They are not byte-duplicate exports. The count excludes the 23 accelerometer ZIPs and the later synthetic copy. The **25** comes from the 25 ordered description lines in the source message: numbers 1,2,3,5…26. This is a count of description entries, not unique physical places: both Y5 302 visits are included. Renumbering fixes their displayed sequence but does not change the file count. The reason for the extra recording remains pending. The initial BM04 blank was a processing placeholder, not evidence that location 4 is missing.

## Reproduce the completed stages

```bash
python3 clean.py --source 'raw/WhatsApp Chat with GE2340.zip'
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
python3 package.py
```

The shareable ZIP excludes the private whole-chat export; recipients need that source separately for the source-level cleaner. Feature extraction reads the supplied cleaned CSVs and can be rerun without the chat. V1, v2 and v3 ZIPs remain preserved; the current package is v4.

## Pending work

1. Identify which of the 26 stop recordings is a repeat/test/extra and confirm recording-to-location links using `recording_review.csv`.
2. Confirm map coordinates and distances when the marked indoor plan is available; numeric fields remain blank until then.
3. Decide whether complete Wi-Fi logging and independently synchronized repeat visits are needed for model evaluation.
4. After confirmed labels, choose a simple baseline and independent evaluation visits. No training or train/test slicing has happened.

## Future entries

Append the next user correction, processing action, command and verified result here. Feature extraction preserves existing `review_*` entries keyed by raw ID and source ZIP/hash; it does not automatically apply them as confirmed labels.

### Relabeling reset — user will provide fresh names

- User says the list supplied by Chris is still wrong/messy and will relabel everything. Treat all existing candidate associations as untrusted, awaiting replacement. Keep the original list and earlier candidates as historical provenance rather than confirmed ground truth.
- Comparison found no confident physical duplicate to delete. All 26 stationary source ZIPs have different hashes/start times; nearby different places can have similar pressure or magnetic strength. A difference between 26 recordings and 25 old description entries does not prove a physical duplicate or mean one recording should be removed.
- Ran `python3 make_relabel_template.py` to create `RELABEL_TEMPLATE.csv`, sorted by actual recording START chronology. It contains 49 actual sensor files: 26 barometer/magnetometer stops and 23 accelerometer movements, with original ZIP/source ID, sender, WhatsApp sent time and actual start/end. Confirmation fields are blank; no old candidate place names, proxy recording or Wi-Fi log is included.
- `RELABEL_README.md` explains stop names/floors, walking from→to, optional repeat/test flags and deferred map distances. Template checks verify 49 unique source IDs, the 26/23 split and source-faithful filenames, hashes and timestamps. Cleaned readings and feature tables were not modified. No endpoint remapping, deletion or training was performed.


### Indoor map UI prototype — 15 November 2026

While corrected recording labels are pending, built a local map-first interface in [`../../map-ui/BUILD_LOG.md`](../../map-ui/BUILD_LOG.md). It supports room/landmark selection, typed start/end routing, directional cross-floor escalators, explicit demo detection, local landmark photos and floor-image backgrounds. The prototype uses illustrative coordinates and has no real sensor-model connection or verified metric distances. It does not alter sensor measurements, features or acquisition labels. A standalone offline HTML and source ZIP are provided. Routing and DOM checks pass; actual visual/native media and HTTP readiness are unverified because browser/server execution is restricted in this sandbox. Future software steps are recorded in the linked build log.
