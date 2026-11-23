# What the feature tables mean (17 November 2026)

A feature is a small summary of measurements. The original readings remain available. The current workflow is:

**Raw recordings → valid cleaned readings → summary statistics (features) → confirm location labels and map → baseline model and independent testing.**

We can summarize pressure, magnetism and acceleration now. Distances, map coordinates and compass calibration are not required for these descriptive calculations. No model has been trained and no accuracy result has been calculated.

## A real example: BM01

BM01 is the actual ZIP `poin 2026-11-17 21-15-19.zip`, recorded from 2026-11-17T21:14:39.464891+08:00. Its provisional, route-inferred label is **Exit 5** (route_inferred_single_sided_start).

- The barometer has **27 accepted readings** with mean **1014.385447 hPa**, median **1014.38614 hPa**, and sample standard deviation **0.002244 hPa**.
- The magnetometer has **2997 accepted vector readings**. For each vector we compute magnitude `sqrt(x*x + y*y + z*z)`. The mean magnitude is **48.21380 µT**, median **46.89925 µT**, sample SD **2.45077 µT**.
- These accepted readings become **one row** in `stop_features.csv`. They have not become many independent location visits. The Wi-Fi count for this window is **113**; no RSSI values were invented.

## What the columns summarize

| Feature | Formula or rule | Unit | Meaning |
| --- | --- | --- | --- |
| Sample count | Number of accepted readings | readings | How much measured data supports the summary |
| Mean | `sum(values) / n` | Sensor's unit | Average observed value |
| Median | Middle sorted value (mean of middle two for even n) | Sensor's unit | Central value, robust to one outlier |
| Sample SD | `sqrt(sum((value - mean)^2) / (n - 1))` | Sensor's unit | Variation within this recording; not location accuracy |
| Range | `maximum - minimum` | Sensor's unit | Spread between the extremes |
| Vector magnitude | `sqrt(x*x + y*y + z*z)` per reading, then summarized | µT or m/s² | Overall vector strength |
| Sample time span | Last accepted relative time minus first | seconds | Span actually covered by readings |
| Wi-Fi per-BSSID median | Median of actually exported candidate RSSI rows for one stop window and MAC | dBm | Descriptive signal strength from selectively persisted observations |
| Acceleration magnitude deviation RMS | `sqrt(mean((magnitude - segment_median)^2))` | m/s² | A descriptive variation measure; not gravity-removed linear acceleration, a step count or a distance |

## A movement example

ACC01 is the internal ID for the recording labelled **Exit toilet** (Exit 5 → Toilet). It has **762 accepted readings**, recording duration **7.664 s**, mean magnitude **9.85245 m/s²** and magnitude SD **0.97338 m/s²**. Raw XYZ means alone can hide movement because positive and negative fluctuations cancel; the variation columns describe that fluctuation while retaining gravity and phone-orientation effects.

`movement_features.csv` has all **23 measured** recordings and no synthetic rows. The two escalator double-landings (BM12→BM13 and BM23→BM24) have no walk recording between them and are listed in `../missing_movements.csv`; no transition was fabricated.

## What remains uncertain

- Stop labels are provisional, inferred only from adjacent movement filenames. Open `../recording_review.csv` to confirm names, floors and any repeat/test flags. Reruns preserve existing `review_*` entries and do not auto-apply them.
- One physical stop was exported twice (`poin 21-36-20` is a prefix of the resumed `poin 21-37-27`); the duplicated interval is quarantined in `../excluded_sensor_rows.csv` and recorded in `../duplicate_recordings.csv`, so it is summarized once.
- Wi-Fi FirstSeen is verified UTC but reflects selectively persisted stored observations, not complete scans. No unobserved BSSID is filled with a weak RSSI value. Three phones' clocks and co-location remain unverified.
- No two-second windows, interpolation, step detection, double integration, distance estimates, calibration or model training have been added.
