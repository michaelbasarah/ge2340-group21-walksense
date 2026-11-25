# Upload pipeline (record on the phone, send, get a result)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Record a stop or walk with **phyphox** on the iPhone, export it, and upload the ZIP from the phone's browser. The laptop answers with the floor, steps (and turns for a walk) and, for a stop, the top-3 places. Every upload is kept in `uploads/` (gitignored) with `uploads/log.jsonl`.

## Run it
Needs `numpy pandas scikit-learn matplotlib` (same as `crossday.py`).
```sh
cd phase2/new/upload
python walksense.py evaluate      # once: session 1 <-> session 2 test, writes out/eval.json (~20 s)
python server.py                  # prints http://<laptop-ip>:8000 -> open it on the phone
python -m unittest test_walksense.py test_live.py   # end-to-end checks with real 24-Nov data (~90 s)
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
The laptop reads the iPhone's sensors **while you walk** and the map updates every second: walking shows the step count, and after **10 s standing still** (phone flat, facing the door) the place circle lights up. The floor is updated once at each stop. The whole stream is also saved to `live_runs/<time>/` as phyphox-style CSVs (gitignored), so every live walk is new data.

1. **Network:** turn on the laptop's **Windows Mobile Hotspot** (Settings > Network > Mobile hotspot) and join it from the iPhone. Turn off the VPN. (The phone's own hotspot may also work.)
2. **iPhone:** open the phyphox experiment that records accelerometer, gyroscope, magnetometer and pressure (the one used on 24 Nov), tap the menu > **Allow remote access**. phyphox shows an address like `http://192.168.137.23:8080`. Keep phyphox open and the screen on.
3. **Laptop, check first:** `python live.py probe http://192.168.137.23:8080` must list buffers for acc, gyr, mag and baro and show samples. If something says NOT FOUND, open `http://<phone>:8080/config` in the laptop browser and send its text so the names can be added.
4. **Start:** `python server.py --live http://192.168.137.23:8080 --floor 5` (start floor; `--device` defaults to `iPhone17,4` = iPhone 16 Plus). Open the printed address on the laptop (or on the phone in a second tab). Press play in phyphox.
5. Walk; stop 10 s at each place. If the floor is wrong, tap "I'm on 5F/4F".

Checked on recorded data (`python live.py check` > `out/live_checks.json`): each 24-Nov session streamed through the live code in 0.5 s steps on its real clock, with the other iPhone's model (held out): stops found 27/27 and 26/26 with no extra stops, floor 27/27 and 26/26, top-1 17/27 and 17/26, top-3 21/27 and 24/26, lit 22 (16 right) both ways. Top-1 from only the first 10 s of a stop: 16/26 and 17/27 (60 s: 17/26 and 17/27). `test_live.py` runs the real live code against a fake phyphox that replays session-2 recordings 20x faster through the same `/get` calls.

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

Place, train on one 24-Nov session and test every stop of the other (true floor given, chance about 8%), from `out/eval.json`:

| phones | xyz top-1 | xyz top-3 | tilt top-1 | \|B\| top-1 |
|---|---|---|---|---|
| iPhone19,2 -> iPhone17,4 | 17/26 | 24/26 | 11/26 | 5/26 |
| iPhone17,4 -> iPhone19,2 | 17/27 | 22/27 | 13/27 | 6/27 |
| S24 -> S24 | 11/26 | 13/26 | 6/26 | 1/26 |
| S24 -> S24 (reverse) | 10/27 | 15/27 | 4/27 | 2/27 |

**Important:** the two sessions used **different iPhones** (session 1 iPhone19,2, session 2 iPhone17,4). The server picks the training data by the phone model in the ZIP (`meta/device.csv`), so it only has one session per iPhone. A phone model it has never seen falls back to all phones and says "expect low accuracy" on the page. Uploading a recording the model was trained on (any 24-Nov stop) scores near 100% and means nothing.

## Not done
- No Wi-Fi (iOS apps cannot scan). Android + WiGLE upload is the next step if Wi-Fi earns its place.
- No route drawing on the map and no replay export for `circle-ui`.
- No graph prior (neighbouring places) on the place guess.
