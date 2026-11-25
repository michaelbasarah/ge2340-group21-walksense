# Upload pipeline (record on the phone, send, get a result)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Record a stop or walk with **phyphox** on the iPhone, export it, and upload the ZIP from the phone's browser. The laptop answers with the floor, steps (and turns for a walk) and, for a stop, the top-3 places. Every upload is kept in `uploads/` (gitignored) with `uploads/log.jsonl`.

## Run it
Needs `numpy pandas scikit-learn matplotlib` (same as `crossday.py`).
```sh
cd phase2/new/upload
python walksense.py evaluate      # once: leave one session out over the 3 sessions, writes out/eval.json (~45 s)
python server.py                  # prints http://<laptop-ip>:8000 -> open it on the phone
python -m unittest test_walksense.py test_live.py   # end-to-end checks with real 24-Nov data (~90 s)
WALKSENSE_SESSIONS=24nov python walksense.py evaluate   # the old 24-Nov-only behaviour (writes out/eval_24nov.json; same numbers as out/eval_2026-11-24.json)
```
- **Network:** the laptop joins the phone's **hotspot** (turn off any VPN). CityU Wi-Fi usually blocks phone-to-laptop traffic. Allow Python through the Windows firewall when it asks.
- Anyone on the same network can upload, so only run it on your own hotspot.

## On the phone, for each place
1. phyphox: an experiment with accelerometer, gyroscope, magnetometer and pressure. Stand **60 s, phone flat, facing the door** (same as 24 Nov: the place model uses raw x/y/z, which depends on the phone's heading).
2. Export as CSV (ZIP), save to Files.
3. On the page: pick the ZIP, optionally pick the true place (for the score), press **Send**.
4. Walks can be uploaded too (steps, turns, and they carry a floor change on the stairs).
At the start, press "I'm on 5F" or "I'm on 4F" once.

## Live mode (phyphox remote access, no export/upload)
The laptop reads the iPhone's sensors **while you walk** and the map updates every second. While walking, a **blue dot** moves along the corridors from the last named stop (steps + compass heading, `route.py`). After **3 s standing still** (phone flat, facing the door) the place circle lights up and the dot restarts from there. The floor is updated once at each stop.

**Recordings:** every phyphox ▶ (play) to ⏸ (pause) is saved as `recordings/<date-time>.zip`, laid out like a phyphox export (Accelerometer.csv, Gyroscope.csv, Magnetometer.csv, Barometer.csv, meta/device.csv), so it can be uploaded on the page or added to the dataset. The page shows the last saved file. `recordings/` is gitignored; copy files into `phase2/clean-data/` only on purpose.

1. **Network:** turn on the laptop's **Windows Mobile Hotspot** (Settings > Network > Mobile hotspot) and join it from the iPhone. Turn off the VPN. (The phone's own hotspot may also work.)
2. **iPhone:** open the phyphox experiment that records accelerometer, gyroscope, magnetometer and pressure (the one used on 24 Nov), tap the menu > **Allow remote access**. phyphox shows an address like `http://192.168.137.23:8080`. Keep phyphox open and the screen on.
3. **Laptop, check first:** `python live.py probe http://192.168.137.23:8080` must list buffers for acc, gyr, mag and baro and show samples. If something says NOT FOUND, open `http://<phone>:8080/config` in the laptop browser and send its text so the names can be added.
4. **Start:** `python server.py --live http://192.168.137.23:8080 --floor 5` (start floor; `--device` defaults to `iPhone17,4` = iPhone 16 Plus). Open the printed address on the laptop (or on the phone in a second tab). Press play in phyphox.
5. Walk; stop 3 s at each place. If the floor is wrong, tap "I'm on 5F/4F". Pause phyphox to save the recording.

Checked on recorded data (`python live.py check` > `out/live_checks.json`, ~15 min; the pre-25-Nov run is `out/live_checks_2026-11-24.json`): each session streamed through the live code in 0.5 s steps on its real clock with a held-out model. 24 s1 with the iPhone17,4 model: stops found 27/27 (extra stops 2), floor 27/27, top-1 17/27, top-3 21/27, lit 22 (16 right). 24 s2 with the iPhone19,2 model (now 24 s1 + 25 Nov): found 26/26, floor 26/26, top-1 18/26, top-3 25/26, lit 22 (16 right). 25 Nov with the iPhone17,4 model: found 26/26, floor 26/26, top-1 17/26, top-3 21/26, lit 23 (16 right). Same handset (iPhone19,2, the other session only): 24 s1 from 25 Nov 18/27 top-1 (top-3 23/27, lit 24, 16 right, extra stops 2); 25 Nov from 24 s1 19/26 (top-3 22/26, lit 25, 19 right, extra stops 0). Top-1 from only the first 3 s of a stop vs 60 s (iPhone, one training session): 24 s1 -> 25 Nov 19/26 vs 20/26, 25 Nov -> 24 s1 17/27 vs 18/27, 24 s1 -> 24 s2 16/26 vs 17/26, 24 s2 -> 24 s1 16/27 vs 17/27 (all 6 ordered pairs of sessions are in the file). Walking dot (corridors learned from one session, walks of another, starting at the true start place), right first corridor / end within 3 m of 28 walks, median error: 24 s1 -> 24 s2 28 / 23 (0.6 m); 24 s2 -> 24 s1 26 / 25 (0.8 m); 24 s1 -> 25 Nov 26 / 24 (1.2 m); 24 s2 -> 25 Nov 26 / 27 (1.4 m); 25 Nov -> 24 s1 26 / 26 (0.8 m); 25 Nov -> 24 s2 28 / 28 (1.2 m). `test_live.py` runs the real live code against a fake phyphox that replays session-2 recordings 20x faster through the same `/get` calls.

Not confirmed against a real phone yet: the phyphox `/config` format (buffer discovery; `probe` falls back to common names) and whether iOS keeps serving with the screen on but the phone in a pocket.

## The map
The page shows the collector's floor sketch (`floor-sketch-v1.pdf`, 5F and 4F) with its red stop dots. After a stop, the dot of the top guess **lights up** (red with a yellow ring and a pulse) when the model is at least 80% sure; below that it gets a dashed "maybe" ring and the page says to try again. The map switches to the floor you are on; the 5F/4F buttons show the other floor. Screenshots: `screenshots/`.

- `map/make_map.py` builds `map/floor5.png`, `map/floor4.png` and `map/places.json` from the PDF (needs `pymupdf pillow`, only to rebuild). It finds the red dots by colour and checks each place matches exactly one dot.
- Which dot is which place: route order and the sketch's metre marks, checked against the floor-5 pins in `phase2/map/coordinates_meters.csv`; escalator up vs down on 5F from the compass direction of the three escalator walks (6 of 6 recordings agree). **Please confirm**, especially the 4F lecture theatres (LT1A/LT1B top right, LT2A/LT2B bottom left) and the gate.
- The 4F **disabled toilet has no dot** on the sketch. It is drawn as a faint dot next to Exit 5 (same offset as the 5F male disabled toilet) and marked `inferred` in `places.json`.
- 80% is a cut-off chosen on the held-out test itself (lit 33/44 right, not lit 1/9 right), so it is a first guess, not a tested setting.

## What it does
| Part | How | Tested |
|---|---|---|
| Floor | pressure jump of more than 0.40 hPa from the **median of the last 6 readings on this floor** (never absolute pressure: weather drift, entry 11). After a gap of over 15 min the floor is kept. | iPhone, both 24-Nov sessions in time order: 27/27 and 26/26 stops; the same for any threshold 0.30 to 0.50 |
| Steps, turns | team code reused unchanged: `count_steps` (pilot) and `turns` (`tracking/pdr.py`); distance = steps x 0.54 m (23-Nov median stride, rough) | not re-tested here |
| Place | kNN (`crossday.make_model`) on 2 s windows of mean magnetic x/y/z, per floor, **trained only on the same phone model**; visit answer = mean probability over windows | see below |

**Sessions:** `walksense.ALL_SESSIONS` is a list of `{name, path}`: `sesi1` and `sesi2` (24 Nov) and `25nov` (Dicta's complete 25-Nov pass, phones iPhone19,2, a55, a56). The server, `live.py` and `route.py` train on all of them. `WALKSENSE_SESSIONS=24nov` (or a comma list of names) limits it to the old behaviour; output files then get that tag (`out/eval_24nov.json`, `out/live_checks_24nov.json`). The pre-25-Nov results are kept as `out/eval_2026-11-24.json` and `out/live_checks_2026-11-24.json`.

Place, leave one session out (true floor given, chance about 8%, per-floor model of the same phone model; `cross-handset` = that handset was in no other session, so a different handset of the same phone is used), from `out/eval.json`:

| phones | train -> test | xyz top-1 | xyz top-3 | tilt top-1 | \|B\| top-1 |
|---|---|---|---|---|---|
| iPhone17,4 -> iPhone19,2 (cross-handset) | sesi2->sesi1 | 17/27 | 22/27 | 13/27 | 6/27 |
| iPhone19,2 -> iPhone17,4 (cross-handset) | sesi1+25nov->sesi2 | 18/26 | 25/26 | 13/26 | 9/26 |
| iPhone17,4 -> iPhone19,2 (cross-handset) | sesi2->25nov | 17/26 | 21/26 | 10/26 | 9/26 |
| iPhone19,2 -> iPhone19,2 (same handset) | 25nov->sesi1 | 18/27 | 23/27 | 13/27 | 7/27 |
| iPhone19,2 -> iPhone19,2 (same handset) | sesi1->25nov | 19/26 | 21/26 | 13/26 | 10/26 |
| S24 -> S24 | sesi1->sesi2 | 11/26 | 13/26 | 6/26 | 1/26 |
| S24 -> S24 (reverse) | sesi2->sesi1 | 10/27 | 15/27 | 4/27 | 2/27 |
| a55 -> a55 | sesi1->25nov | 5/26 | 11/26 | 2/26 | 2/26 |
| a55 -> a55 (reverse) | 25nov->sesi1 | 3/27 | 11/27 | 3/27 | 2/27 |
| a56 -> a56 | sesi1->25nov | 14/26 | 18/26 | 7/26 | 4/26 |
| a56 -> a56 (reverse) | 25nov->sesi1 | 13/27 | 18/27 | 10/27 | 3/27 |

Before 25 Nov (`out/eval_2026-11-24.json`): iPhone19,2 -> iPhone17,4 17/26 (top-3 24/26), iPhone17,4 -> iPhone19,2 17/27 (22/27), S24 11/26 and 10/27. The 25-Nov rows are the first same-handset cross-session test (iPhone19,2: 19/26 and 18/27). Floor tracking over the iPhone recordings of each session in time order: sesi1 27/27, sesi2 26/26, 25nov 26/26 (the 25-Nov iPhone is the only phone with a barometer that day).

**Important:** iPhone17,4 was recorded in one session only (24 s2), so it still has no same-handset test. The server picks the training data by the phone model in the ZIP (`meta/device.csv`): iPhone19,2 now trains on 24 s1 + 25 Nov, S24 on both 24-Nov sessions, iPhone17,4 on 24 s2. A phone model it has never seen falls back to all phones and says "expect low accuracy" on the page. Uploading a recording the model was trained on (any recorded stop) scores near 100% and means nothing.

## Not done
- No Wi-Fi (iOS apps cannot scan). Android + WiGLE upload is the next step if Wi-Fi earns its place.
- No route drawing on the map and no replay export for `circle-ui`.
- No graph prior (neighbouring places) on the place guess.
