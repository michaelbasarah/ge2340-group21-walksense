# GE2340 Wi-Fi export audit

The export is readable and contains usable, selectively recorded observations. It is **not a complete sequence of Wi-Fi scan snapshots**. Time-window associations can be retained as provisional candidates, with no fabricated scans or signal-absence values.

## Verified source facts

- The official [WiGLE CSV v1.6 specification](https://api.wigle.net/csvFormat-1_6.html) defines `FirstSeen` as a UTC timestamp with second precision. Converting to Hong Kong time adds eight hours; this is a timezone conversion, not an estimated phone-clock correction.
- In the inspected [upstream ObservationUploader](https://github.com/wiglenet/wigle-wifi-wardriving/blob/main/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/background/ObservationUploader.java#L404), the formatter explicitly uses UTC. The `FirstSeen` column comes from cursor column 7. The [database iterator](https://github.com/wiglenet/wigle-wifi-wardriving/blob/main/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/db/DatabaseHelper.java#L1793) selects that column as `location.time`. Thus the column is a persisted observation timestamp, rather than one immutable first-ever timestamp per access point.
- [DatabaseHelper observation persistence](https://github.com/wiglenet/wigle-wifi-wardriving/blob/main/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/db/DatabaseHelper.java#L1301) conditionally saves observations based on new-network status, position changes, stronger RSSI, and related conditions. It writes `Location.getTime()` into the observation. The threshold constant is 5 dB. This timestamp does not expose radio acquisition time or location-fix age.
- The [Wi-Fi receiver](https://github.com/wiglenet/wigle-wifi-wardriving/blob/main/wiglewifiwardriving/src/main/java/net/wigle/wigleandroid/listener/WifiReceiver.java#L171) obtains a location independently of the scan results; acquisition time and scan identity are not exported in this CSV.

**Version caveat:** the supplied header says appRelease 2.111. The sources above are current upstream `main`, inspected during this audit; the exact installed 2.111 source/binary was not matched. The stable official UTC format and the local data support the interpretation, but do not prove every internal implementation detail of that binary. Links identify files and inspected line anchors, not immutable commit hashes.

## Local evidence

The source archive SHA-256 is `7f7e42c00513de2abf974d98b58bd2a56fe24d18c29542ae56b6da6fdc356a34`.

- `DOC-20261114-WA0049.gz`: 6,211 rows, comprising **6,196 WIFI** and **15 LTE** rows.
- **2,760 distinct Wi-Fi BSSIDs**, 357 distinct stored timestamp seconds, and **zero exact duplicate Wi-Fi rows**.
- Wi-Fi timestamps cover **2026-11-14 12:24:56–13:34:40 UTC**, equivalent to **20:24:56–21:34:40 Hong Kong**.
- Of 3,436 consecutive observations of the same BSSID in file order, **3,375 (98.22%) increase RSSI by at least 5 dB**. This strong selection pattern supports the persistence-filter interpretation. It would be inappropriate to regard missing rows as proof that an access point disappeared.
- Recording metadata identifies **three devices**: barometer/magnetometer `iPhone17,4`, accelerometer `iPhone19,2`, Wi-Fi Samsung `SM-S9280`. Their clocks and physical co-location were not independently synchronized or verified by this audit.
- Exported position accuracy ranges from **3.79 to 400 m**, median **12.71 m**. These coordinates cannot supply precise indoor landmark positions or route distances.

## Provisional stop association

Using the exported second as an instant, interpreted as UTC, and each barometer/magnetometer session's internal START–PAUSE interval:

- **664 Wi-Fi rows** fall within the 26 stop intervals.
- **22 stops** have at least one candidate Wi-Fi row; **BM01, BM12, BM14, BM22** have zero.
- **2,908 rows** fall within the full sensor-session span (21:09:41.933–21:34:16.955 Hong Kong); **2,244** of those are between stops. Another **3,288** rows fall outside that span.
- Timestamp-second buckets introduce boundary uncertainty of up to one second. `per_stop_coverage.csv` separately reports rows whose second bucket could overlap the interval; these are boundary candidates, not extra confirmed measurements.

These counts describe recorded observations with candidate temporal associations. They do not prove Wi-Fi scan count, fingerprint completeness, precise acquisition time, clock synchronization, or the phone's exact landmark during a stop. A zero-row stop is **missing exported observation coverage**, not “no Wi-Fi.”

## Cleaning rules

1. Preserve all original fields and row provenance; normalize timestamps to UTC and Hong Kong time while retaining `FirstSeen` verbatim.
2. Keep WIFI and LTE rows distinct. Do not discard a repeated BSSID merely because it appears earlier.
3. Use `persisted_observation_location_time` as the time-semantics flag, with `radio_acquisition_time_unavailable`, `cross_device_clock_alignment_unverified`, and `selectively_persisted_not_complete_scan` flags.
4. Associate only rows actually inside a stop interval; expose associations as provisional. Keep inter-stop/out-of-span rows in separate tables. If boundary-overlap candidates are included, label them separately.
5. Do not interpolate Wi-Fi observations, forward-fill old RSSI, infer complete scan groups from one second, or fill unheard BSSIDs with a very weak RSSI value.
6. Retain missing stop coverage. Do not train or report evaluation performance as though this single walk offered independent repeat visits or complete synchronized multimodal samples.

## Reproduction and checks

Run `python3 /tmp/ge2340_wifi_audit/audit.py`. The stdlib-only script reads the original archive, audits all 26 stop intervals, writes `audit.json` and `per_stop_coverage.csv`, and verifies the source checksum before/after. It asserts the expected 26 sessions and 6,196 Wi-Fi rows. No original file was modified. No training, upload, account action, or commit was performed.
