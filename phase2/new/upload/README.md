# Upload pipeline (record on the phone, send, get a result)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Record a stop or walk with **phyphox** on the iPhone, export it, and upload the ZIP from the phone's browser. The laptop answers with the floor, steps (and turns for a walk) and, for a stop, the top-3 places. Every upload is kept in `uploads/` (gitignored) with `uploads/log.jsonl`.

## Run it
Needs `numpy pandas scikit-learn matplotlib` (same as `crossday.py`).
```sh
cd phase2/new/upload
python walksense.py evaluate      # once: session 1 <-> session 2 test, writes out/eval.json (~20 s)
python server.py                  # prints http://<laptop-ip>:8000 -> open it on the phone
python -m unittest test_walksense.py   # end-to-end check with real 24-Nov ZIPs (~30 s)
```
- **Network:** the laptop joins the phone's **hotspot** (turn off any VPN). CityU Wi-Fi usually blocks phone-to-laptop traffic. Allow Python through the Windows firewall when it asks.
- Anyone on the same network can upload, so only run it on your own hotspot.

## On the phone, for each place
1. phyphox: an experiment with accelerometer, gyroscope, magnetometer and pressure. Stand **60 s, phone flat, facing the door** (same as 24 Nov: the place model uses raw x/y/z, which depends on the phone's heading).
2. Export as CSV (ZIP), save to Files.
3. On the page: pick the ZIP, optionally pick the true place (for the score), press **Send**.
4. Walks can be uploaded too (steps, turns, and they carry a floor change on the stairs).
At the start, press "I'm on 5F" or "I'm on 4F" once.

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
- No map/route on this page and no replay export for `circle-ui` (the 24-Nov places have no x/y yet).
- No graph prior (neighbouring places) on the place guess.
