# What the feature tables mean

A feature is a small summary of measurements. The original readings remain available. The current workflow is:

**Raw recordings → valid cleaned readings → summary statistics (features) → confirm location labels and map → baseline model and independent testing.**

We can summarize pressure, magnetism and acceleration now. Distances, map coordinates and compass calibration are not required for these descriptive calculations. No model has been trained and no accuracy result has been calculated.

## A real example: BM01

BM01 is the actual ZIP `point 2026-11-14 21-10-09.zip`, recorded from 21:09:41.933 Hong Kong time. Its candidate label is Exit 5; recording-to-location alignment remains provisional.

- The barometer originally has 9 readings. One has a negative experiment time and remains in quarantine. The **8 accepted readings** have mean **1010.397129125 hPa**, median **1010.39711 hPa**, and sample standard deviation **0.00029866 hPa**. Their sample span is approximately 0.49–6.98 seconds.
- The magnetometer has **1000 accepted vector readings** across roughly 10 seconds. For each vector we calculate magnitude `sqrt(x*x + y*y + z*z)`. The mean of these magnitudes is **43.93107 µT**, median **43.97287 µT**, and sample standard deviation **0.18780 µT**.
- These 1,008 accepted sensor readings become **one row** in `stop_features.csv`. They have not become 1,008 independent location visits. There are no exported Wi-Fi observations in this exact stop window; the Wi-Fi count is zero, and no RSSI values were invented.

## What the columns summarize

| Feature | Formula or rule | Unit | Meaning |
| --- | --- | --- | --- |
| Sample count | Number of accepted readings | readings | How much measured data supports the summary |
| Mean | `sum(values) / n` | Sensor's unit | Average observed value |
| Median | Middle sorted value, averaging the middle two for even n | Sensor's unit | Central value less sensitive to one extreme reading |
| Sample SD | `sqrt(sum((value - mean)^2) / (n - 1))` | Sensor's unit | Variation within this particular recording; not location accuracy |
| Range | `maximum - minimum` | Sensor's unit | Spread between the extremes |
| Vector magnitude | `sqrt(x*x + y*y + z*z)` per reading, then summarized | µT or m/s² | Overall vector strength; magnitude mean differs from magnitude of XYZ means |
| Sample time span | Last accepted relative time minus first | seconds | Span actually covered by readings; not a guarantee of uninterrupted sampling |
| Wi-Fi per-BSSID median | Median of actually exported candidate RSSI rows for one BM window and MAC | dBm | Descriptive signal strength from selectively persisted observations |
| Acceleration magnitude deviation RMS | `sqrt(mean((magnitude - segment_median_magnitude)^2))` | m/s² | A descriptive variation measure; not gravity-removed linear acceleration, a step count or distance |

## A movement example

ACC01 is the internal stable ID for original file label **P1**. It has **787 accepted readings**, recording duration **7.920 seconds**, mean magnitude **9.80450 m/s²** and magnitude SD **0.78200 m/s²**. Raw XYZ means alone can hide movement because positive and negative fluctuations cancel around the average. The variation columns describe that fluctuation while retaining gravity and phone-orientation effects.

`movement_features.csv` has 23 real recordings plus the one explicitly requested copy. The copied 5F connector uses ACC15, whose original filename says **P16–18**, not P15. Its feature numbers are exactly the parent's; its target acquisition times remain blank. Parent and copy share acquisition group ACC15 and are not independent recordings.

## What remains uncertain

- Twenty-six actual barometer/magnetometer ZIPs are present, with distinct names, SHA-256 hashes and recording start times: these are not byte-duplicate exports. The source list has twenty-five ordered description entries (including two Y5 302 visits), not necessarily twenty-five unique physical places. Original numbers are 1, 2, 3, 5…26; the user's typo correction makes a complete list 1…25. The repeat/test/extra recording is not identified yet; corrected list number is not raw BM ordinal. All location links remain candidate links.
- Open `../recording_review.csv` in Excel or LibreOffice. Each row is one actual ZIP with time, current candidate label and review fields. Confirm a location or flag a repeat/test there; rerunning feature extraction preserves existing `review_*` entries and does not automatically apply them to labels. The blank BM04 candidate is a placeholder from the previous ordinal mapping, not proof BM04 is the extra visit.
- Wi-Fi FirstSeen is verified UTC, but the export contains selective stored location observations, not complete scan snapshots. Exact installed WiGLE 2.111 source/binary was not matched to the audited current upstream source. No unobserved BSSID is filled with a weak RSSI value. Three phones' clocks and co-location remain unverified.
- The 664 Wi-Fi candidate observations form 663 stop/BSSID groups: **662 groups contain just one row**, and one contains two. Nearly every per-BSSID median therefore equals one exported reading, not an average of repeated scans throughout ten seconds.
- No two-second windows, interpolation, step detection, double integration, distance estimates, calibration or model training have been added.
