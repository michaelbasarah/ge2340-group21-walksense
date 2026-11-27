# Live evidence, 27 Nov 2026: Dicta's iPhone 18 in live mode, 5F/4F rides (PROCESS-LOG entry 95)

*Internal team notes, not report text.* Not a scored walk (see `../../PROTOCOL.md`); **not training data** (not added to any model).

## What this is
Raw answers of phyphox remote access on Dicta's iPhone 18 (`deviceModel` iPhone19,2, phyphox 1.2.1 build 17929, iOS 27.2.1: `meta.json`), experiment "Test App" (`config.json`: Accelerometer, Barometer, Gyroscope, Magnetometer; buffers `acc_time/accX..Z`, `baro_time/baroX`, `gyro_time/gyroX..Z`, `mag_time/magX..Z`). One phyphox measurement (session id 5480320), times = phyphox experiment time in s. Read on the laptop (WSL) with read-only `GET /config`, `/meta`, `/get`; nothing was changed on the phone.

| Folder | Read at (HKT, laptop clock) | Contents |
|---|---|---|
| `polls_1822/` | 18:22:28 to about 18:25:00 | first `/get` = the full buffers since the start (t 0 to ~689 s), then 225 incremental polls every 0.5 s (to t ~836 s); `api_live_8000.jsonl` = the port-8000 demo server's `/api/live` answer at each poll (what the user saw) |
| `full_1830/` | 18:30:31 | one full `/get` (t 0 to 1168.9 s); `api_live_8000.jsonl` = one `/api/live` answer |

`get_responses.bin.gz` = gzip of the response bodies exactly as received (bytes identical after `gunzip`); each record is a line `wall_time<TAB>path<TAB>byte_count` followed by that many body bytes and a newline. SHA-256 of the uncompressed files: `full_1830` 8b19354db88a8955d89a7170c9c3a3c72650491eea52724f29df28b030ba6e9f, `polls_1822` 491663f161d0962836138596bad3d20f722e0fc44682282006d84fef591d79d3. Read with `phase2/new/upload/live_phone_check.py` (`read_capture`).

## Labels (from the user's messages, relayed by the advisor; exact times of the messages are not known)
- During the session, before the first ride: the user was **standing at the 5F down escalator** (`esca_down`, 5F) and the app answered sr9 / lift_stairs5.
- Then **5F -> 4F by escalator or lift** (the user did not say which), then at **LT1B (`lt1b`, 4F)**; the user reports the app kept them on 5F ("Y5") and switched late.
- Later: the user rode 5F -> 4F several times; "every 5F -> 4F transition fails live" or switches very slowly.

Which stop was at which place is **not** labelled per stop. The rides themselves are found in the pressure (`live.rides`, threshold 0.4 hPa): 5F->4F at t 703.9-717.8 s (+0.55 hPa), 4F->5F at 818.2-831.0 (-0.50), 5F->4F at 985.8-998.6 (+0.51), 4F->5F at 1094.7-1109.7 (-0.56); 60-86% of each ride reads as "still" (standing on the escalator or in the lift). Before t 700 the pressure stays at 1014.88-1015.00 hPa, so the user was on 5F the whole time before the first ride.
