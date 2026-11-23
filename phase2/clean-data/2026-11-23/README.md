# GE2340 cleaned acquisition, 23 November 2026 — two-floor (floor 5 + floor 4)

Second cleaned session, now covering **both floors**. 42 unique stops
(26 on floor 5, 16 on floor 4) and 37 movement recordings. Movements now
include the **gyroscope** (for heading). Every value is real; nothing invented.

## What was handled
- **Pause/resume duplicates:** some stop recordings were paused between stops and re-exported
  several times. Identical intervals were de-duplicated, so one physical stop = one interval.
  3 duplicate intervals were quarantined (see `duplicate_recordings.csv`).
- **Labels** come from the origin of the next movement file (`From X` -> stop X); confirm against the route.
- **Floors** split from barometer medians.
- **Two WiGLE logs** merged (6,522 accepted observations, 41/42 stops covered).

## Counts
- Accepted sensor readings: **364,067** ({'magnetometer': 288441, 'barometer': 2312, 'accelerometer': 36662, 'gyroscope': 36652}); quarantined **18,211**.
- Exclusion reasons: {'negative_experiment_time': 60, 'duplicate_reexport_interval_superseded_by_BM03': 12101, 'duplicate_reexport_interval_superseded_by_BM04': 6050}.

## Files
`sensor_samples.csv`, `sensors/*.csv` (incl. gyroscope), `sensor_quality.csv`, `excluded_sensor_rows.csv`,
`sessions.csv`, `recording_intervals.csv`, `locations_provisional.csv`, `accelerometer_edges.csv`,
`missing_movements.csv`, `duplicate_recordings.csv`, `wifi/*`, `summary.json`, `validation.json`.

Reproduce: `python clean.py --source "../../../Data 23-11"`.
