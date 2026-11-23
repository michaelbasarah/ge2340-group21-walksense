# Processing log — GE2340 acquisition of 17 November 2026

This is the record of meaningful processing decisions for the second acquisition. Add new
decisions/results below as work continues; do not rewrite the original acquisition evidence.
No training, upload or publication has been performed.

| Step | Completed work and reason | Evidence / result |
| --- | --- | --- |
| 1. Inventory the export | Read the loose phyphox ZIPs and the WiGLE GZIP in `Data (17-11)`. Preserve every file byte-for-byte in `raw/attachments/`. | 49 sensor ZIPs = 26 barometer/magnetometer stop recordings (`poin ...zip`) + 23 accelerometer movement recordings (route-named). One WiGLE GZIP. All ZIPs pass integrity checks. |
| 2. Read recording metadata | Use each phyphox `meta/time.csv` START/PAUSE event to map relative seconds to device epoch, UTC and HK. Preserve device identity. | Stops recorded on iPhone17,4, movements on a different iPhone, Wi-Fi on a Samsung. Clocks not independently synchronized. |
| 3. Detect a double-exported stop | One recording (`poin 21-37-27`) has two intervals; its first interval is an exact re-export of the standalone `poin 21-36-20`. | The duplicated interval is quarantined (reason `duplicate_reexport_interval_superseded_by_BM19`), recorded in `duplicate_recordings.csv`. 26 distinct physical stops remain; the stop is counted once. |
| 4. Clean sensor readings | Keep finite parseable readings inside their actual acquisition interval. Quarantine negative-time, outside-interval, nonfinite and exact-duplicate rows with their full source values; no smoothing or resampling. | Input 104,504 readings = 101,436 accepted + 3,068 quarantined. Accepted by sensor: {'magnetometer': 77930, 'barometer': 700, 'accelerometer': 22806}. |
| 5. Number and label stops | Number stops BM01..BM26 in recording order. Derive a provisional location label for each from the names of the adjacent movement recordings. | 20 labels confirmed on both sides; 4 escalator landings and 2 single-sided endpoints are lower-confidence. Floors left blank pending a map. |
| 6. Build the route | Assign each movement to the stop immediately before and after it in recording order; record consecutive stop pairs with no walk recording. | 23 measured movements, all within their endpoint windows; 2 unrecorded escalator double-landings in `missing_movements.csv`. Pressure medians drop ~0.6 hPa across the descent and recover on the way up. |
| 7. Audit and associate Wi-Fi | Separate WIFI from non-WIFI rows; verify UTC format; associate rows whose stored FirstSeen second falls inside a stop interval. No interpolation or absent-AP filling. | 3,085 WIFI observations, 2 LTE rows separated. 961 provisional associations across 15 stops; 2,124 unassigned. |
| 8. Extract first-pass features | Summarize each cleaned recording with counts, means, medians, sample SDs, ranges and time coverage; summarize Wi-Fi candidate groups without missing-AP values. | `features/stop_features.csv` (26 rows), `features/movement_features.csv` (23 rows, no synthetic), `features/wifi_by_stop_bssid.csv`. Original readings unchanged. |

## Reproduce the completed stages

```bash
python3 clean.py --source "../../../../Data (17-11)"
python3 clean.py --validate-only
python3 feature_extraction.py
python3 feature_extraction.py --validate-only
```

## Pending work

1. Confirm stop labels, floor numbers and any repeat/test recording using `recording_review.csv` and the marked indoor plan.
2. Add map coordinates and distances when the plan is available; numeric fields remain blank until then.
3. Decide whether more complete Wi-Fi logging and independently synchronized repeat visits are needed for evaluation.
4. After confirmed labels, choose a baseline and independent evaluation visits. No training or train/test slicing has happened.

## Future entries

Append the next correction, processing action, command and verified result here. Feature extraction preserves existing `review_*` entries keyed by raw ID and source ZIP/hash; it does not automatically apply them as confirmed labels.
