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

- Since 26 Nov the default view is the vector floor plan (next section); this picture is the fallback behind the **Picture** button.
- `map/make_map.py` builds `map/floor5.png`, `map/floor4.png` and `map/places.json` from the PDF (needs `pymupdf pillow`, only to rebuild). It finds the red dots by colour and checks each place matches exactly one dot.
- Which dot is which place: route order and the sketch's metre marks, checked against the floor-5 pins in `phase2/map/coordinates_meters.csv`; escalator up vs down on 5F from the compass direction of the three escalator walks (6 of 6 recordings agree). **Please confirm**, especially the 4F lecture theatres (LT1A/LT1B top right, LT2A/LT2B bottom left) and the gate.
- The 4F **disabled toilet has no dot** on the sketch. It is drawn as a faint dot next to Exit 5 (same offset as the 5F male disabled toilet) and marked `inferred` in `places.json`.
- 80% is a cut-off chosen on the held-out test itself (lit 33/44 right, not lit 1/9 right), so it is a first guess, not a tested setting.

## The map v2 (vector floor plan)
The page now draws a real floor plan in metres instead of the picture: corridors, rooms, the 26 places, every corridor with its length, escalators and the lift with the floor they lead to, a 5 m scale bar and a north arrow. It is the default; the **Picture** button switches back to the old sketch PNG (remembered per browser). Light and dark mode follow the phone; **+ / − / ⤢** zoom, drag pans when zoomed, and the blue badges (`▼ to 4F`, `▲ from 4F`, `⇅ 4F`) switch floor. Screenshots: `screenshots/v2-*.png` (both floors, lit circle after a real 25-Nov upload, "maybe" ring, walking dot, zoom, dark, 390 px phone, picture fallback).

Files: `map/floorplan.json` (the data, read by the page), `map/floorplan.js` (the drawing, no libraries), `map/make_floorplan.py` (builds the JSON), `map/sketch_trace.json` (what was read from the sketch PDF). `route.py`, `places.json` and the PNGs are unchanged: the walking dot still comes from `route.py` in `places.json` pixels; the page recovers how far along the corridor it is (projection onto the pixel segment) and puts it at that fraction of the corridor drawn in metres. If a corridor is missing, an affine pixel -> metre fit (`px_to_m` in the JSON) is the fallback.

**How the coordinates were made** (`python map/make_floorplan.py`; numbers from `floorplan.json` > `fit`):
1. The sketch PDF is the collector's drawing on a Google indoor-map screenshot. From the PDF we take the red dots and the black corridor lines as exact vector coordinates (bends included), the typed 4F metre marks, and the screenshot itself (`python map/make_floorplan.py trace`, needs `pymupdf`). The screenshot is split by Google's flat colours into rooms, corridors, toilets and escalator/stair blocks and traced to polygons.
2. Metres: x east, y north, the frame of `phase2/map/coordinates_meters.csv` (Google lat/long of 8 floor-5 places). A scale + rotation + shift from screenshot pixels to that frame is fitted on those 8 places: 0.0887 m per pixel, rotation 1.1 deg (the screenshot is north-up, so the north arrow is real), sketch dots vs Google pins 0.75 m RMS (worst Exit 5, 1.15 m).
3. 4F: the 4F screenshot shows the same two Google markers (City Express, Y5ZONE). Lining them up gives scale 0.997, rotation -0.08 deg, shift 8.8 / 3.2 px, so 4F uses the same metres as 5F. Exit 5 and the lift landing then sit within about 0.5 m of the 5F ones.
4. Place points: least squares over every place and corridor bend. Terms: the 8 Google pins (sigma 0.25 m), the corridor lengths of `phase2/new/routing/graph.json` (sigma 0.3 m measured, max(0.5 m, 15%) steps, 4 m guess) and the sketch position (sigma 1.5 m, keeps the shape). Edge residual RMS: 5F 1.04 m, 4F 0.33 m. Per edge below (drawn = corridor length on the plan; mark = what the collector wrote on the sketch, handwriting read by eye).

| floor | corridor | source | graph.json m | drawn m | residual | sketch mark |
|---|---|---|---|---|---|---|
| 5F | Canteen - Exit 5 | measured | 11.1 | 11.1 | -0.00 | 11.9 |
| 5F | Exit 5 - Male WC | measured | 3.6 | 3.62 | +0.02 | 6 |
| 5F | Male WC - Y5-302 | measured | 11.6 | 11.58 | -0.02 | 10 |
| 5F | Y5-302 - Study rooms | measured | 13.9 | 13.84 | -0.06 | 11 |
| 5F | Study rooms - Y5-202 | measured | 10.6 | 10.6 | +0.00 | 11 |
| 5F | Y5-202 - Female WC | measured | 10.7 | 10.69 | -0.01 | 10 |
| 5F | Female WC - Exit 10 | measured | 4.4 | 4.4 | +0.00 | 6 |
| 5F | Exit 10 - Canteen | measured | 11.6 | 11.62 | +0.02 | 11.9 |
| 5F | Exit 10 - Esc. up | **guess** | 4.9 | 8.47 | +3.57 | (not drawn) |
| 5F | Esc. up - Esc. down | steps | 10.3 | 9.2 | -1.10 | 3.9 |
| 5F | Esc. down - Exit 5 | steps | 7.6 | 8.12 | +0.52 | (not drawn) |
| 5F | Canteen - Esc. down | steps | 8.1 | 7.23 | -0.87 | 4.9 |
| 5F | Esc. up - Canteen | steps | 8.1 | 7.37 | -0.73 | 4.9 |
| 5F | Exit 5 - Disabled WC | steps | 3.2 | 3.16 | -0.04 | 1 (unclear) |
| 5F | Disabled WC - Lift / stairs | steps | 8.1 | 7.97 | -0.13 | 7 + 3 |
| 5F | Lift / stairs - Y5-401 | steps | 10.3 | 8.76 | -1.54 | 4 |
| 5F | Y5-401 - Y5-302 back | steps | 5.9 | 6.25 | +0.35 | 9 |
| 5F | Y5-302 back - Lift / stairs (via Y5-401) | steps | 16.2 | 15.01 | -1.19 | - |
| 4F | Lift / stairs - Disabled WC | steps | 8.1 | 8.11 | +0.01 | 9.1 + 1.? (whole Exit 5 - lift line) |
| 4F | Disabled WC - Exit 5 | steps | 3.2 | 3.14 | -0.06 | - |
| 4F | Exit 5 - LT2A | steps | 4.3 | 4.37 | +0.07 | 4.7 |
| 4F | LT2A - LT2B | steps | 15.7 | 15.63 | -0.07 | 15 |
| 4F | LT2B - Esc. down | steps | 5.4 | 5.5 | +0.10 | - |
| 4F | Esc. down - Y4-502 | steps | 9.7 | 9.59 | -0.11 | 9.38 |
| 4F | Y4-502 - Esc. up | steps | 9.7 | 9.41 | -0.29 | 9.38 |
| 4F | Esc. up - LT1B | steps | 5.9 | 5.93 | +0.03 | 6.76 |
| 4F | LT1B - LT1A | steps | 14.0 | 14.26 | +0.26 | 15 |
| 4F | LT1A - Exit 10 | steps | 5.9 | 5.75 | -0.15 | 4.77 |
| 4F | Exit 10 - Gate | steps | 10.8 | 10.9 | +0.10 | 11.43 |
| 4F | Gate - Exit 5 | steps | 14.6 | 13.61 | -0.99 | 11.43 |
| 4F | Esc. down - Esc. up | steps | 8.6 | 8.18 | -0.42 | 6.34 |

On the map the label shows the `graph.json` length: plain = measured (Google pin to pin), `~` and dashed = 23-Nov step count x 0.54 m, `?` and dotted = guess. Between floors (badges): escalator rides 20 s each way (**guess**, never timed, one way: 5F down -> 4F down, 4F up -> 5F up), lift/stairs 30 s (timed once 5F -> 4F).

**What is a guess or inferred** (marked in `floorplan.json` by `source`, `status`, `inferred`, `note`):
- 8 of 31 corridor lengths are measured (all on 5F), 22 are steps x 0.54 m, 1 is a guess (Exit 10 - up escalator; not drawn on the sketch, drawn as a straight line). Esc. down - Exit 5 and Y5-302 back - lift are not drawn on the sketch either (straight line / same corridor through Y5-401).
- 4F has no Google pins: its positions are the sketch dots fitted to the step lengths, nothing on 4F is surveyed.
- The 4F mixed disabled toilet has no sketch dot: placed at the 5F offset from Exit 5, which lands at the door of Google's "Wheelchair Accessible Bathroom" (marked `*`).
- Room footprints are traced from Google, and which block belongs to which place is our reading: Google calls the 5F male-toilet block "Female Bathroom"; LT1A/LT1B/LT2A/LT2B are the nearest Google lecture theatres (Tin Ka Ping, CY Sun, Sze Chi Ching, David Chow), Y4-502 is next to Google's Photo Copying Centre, Y5-202 has no Google room; the lift is not on Google (the purple block is the stair block by the stop).
- Sketch marks and step lengths disagree in places: the 5F escalator triangle (sketch 3.9 / 4.9 m vs steps 10.3 / 8.1 m) and Lift - Y5-401 - Y5-302 back (sketch 4 + 9 m vs steps 10.3 + 5.9 m). The fit splits the difference (the escalator points moved 2.2 and 2.6 m from the sketch dots, Y5-401 2.4 m).

**Editing `floorplan.json`:** small fixes can be made by hand; the page reads only this file (reload the page). A place is `floors.<5|4>.places.<id>` with `x`, `y` in metres (east, north) and `name` / `short` (label on the map); `label_dx` / `label_dy` move its label. A corridor is an entry of `edges` with `points` (polyline in metres, first and last point = the two places), `metres` and `source` (`measured` / `steps` / `guess`). Rooms are `rooms[].polys` (polygons in metres); `walkable` is the white corridor area; `links` are the escalators and the lift. Place ids must stay the model's ids (the page and `route.py` use them). A real rebuild (`python map/make_floorplan.py`) overwrites hand edits: put lasting changes in `make_floorplan.py` (`NAMES`, `PATHS`, `FOOTPRINTS`, `LABEL_DIR`, weights) or in `graph.json` / `coordinates_meters.csv`, then rebuild. `test_walksense.py` checks that every place the model can guess and every corridor the walking dot can take is in `floorplan.json`.

## Search with Gemini: setup
The search bar at the top of the page finds one of our 26 places from a room name or a free question ("where can I study", "toilet on 4th floor", "where is the chemistry lab") and draws the route on the map. Without a key it still works offline (keyword, then fuzzy match); with a Gemini key it also answers free questions in one sentence.

1. Copy `.env.example` to `.env` at the **repo root** (the folder with `PROCESS-LOG.md`). `.env` is gitignored (check: `git check-ignore -v .env`).
2. Paste the key after `GEMINI_API_KEY=` (no quotes, no spaces). Get a key at **aistudio.google.com/apikey**.
3. Check it: `python phase2/new/upload/check_gemini.py` prints `OK: ... Model: ...` or what is wrong (no key / key rejected / no internet / quota / unknown model). It makes one tiny call.
4. Start `server.py` as usual (restart it if it was running). The start-up lines say `Search: Gemini <model>` or that it answers offline.

How it answers (`search.py`, endpoint `GET /api/search?q=...&from=<place id>`):
- Gemini first (when a key is set). It gets the same place list as the request-matching LLM method and must answer one listed place ID or `NONE` plus one short sentence (JSON); a place we do not cover gets a polite "not in the area WalkSense covers". The key stays on the laptop: the browser only talks to `server.py`.
- No key, no internet, a timeout (8 s, `GEMINI_TIMEOUT_S` in `.env`), an HTTP error or an unusable reply: keyword, then fuzzy (`phase2/request-matching/match.py`). The page shows which method answered. After no internet / a timeout / a quota error Gemini is skipped for 60 s; a rejected key or unknown model is skipped until the server restarts.
- Route: A* from `phase2/new/routing/route.py` on `routing/graph.json` (imported, not copied; since entry 78 `plan()` with the Standard / Step-free mode, see "Route planner" below). Start = the place picked in the **From** list, else the place that is lit right now (live mode, else the last uploaded stop), else the 4F entrance gate. The orange line follows the floor-plan corridors on each floor; the steps list names every place, the escalator / lift rides and the metres. Graph ids and map keys differ (the map keys repeat across floors), so `search.GRAPH_TO_MAP` is an explicit 26-row table; `test_search.py` checks it against `floorplan.json`, `destinations.csv` and `places.json`.
- Model: `gemini-3.5-flash-lite` (stable; Google's docs, checked 26 Nov 2026, call it the fastest and most cost-effective 3.5 model and list a free tier). Change it with `GEMINI_MODEL=` in `.env`.
- Tests: `python -m unittest test_search.py` (Gemini mocked: good reply, NONE, garbage, timeout, HTTP 400/403/429; `/api/search` through a real server on a free port) and `cd ../../request-matching && python -m unittest test_gemini`.
- Accuracy on the 128 test queries with Gemini: `cd phase2/request-matching && python evaluate.py --method hybrid_gemini` (keyword -> fuzzy -> Gemini; `--method gemini` = Gemini on every query). At most `--max-calls` real calls (default 150); answers are cached in `llm_cache_gemini_v1.json`; writes `out/gemini_results.json` and `out/gemini_failures_<method>.csv`. Without a key it prints how to add one and stops.

## Route planner (From / To, step-free mode, toilet filter)
Asked for by the user on 26 Nov: "from B to E, light up the suggested path by the lowest distance; if the floor changes, suggest the closest lift or escalator; a disabled mode with lifts only and disabled toilets only; filter toilets by gender". Code: `phase2/new/routing/route.py` (`plan()`, `nearest_toilet()`, see that README, section "Route planner") and `search.py` / `server.py` here. Examples and costs are in `routing/out/planner_samples.json` (`python route.py samples` in `routing/`).

On the page (everything sits in the top bar, never a popup in the middle):
- **From / To** lists under the search box. From empty = where I am (the lit place in live mode, else the last uploaded stop, else the 4F entrance gate). Choosing a To place draws the route at once. **Tap a place on the floor plan** to set it as To (or as From, with the "Tap a place to set To / From" switch under the map). Search results also fill To.
- The route is the cheapest one over `graph.json` edge lengths (every corridor has a length; none had to be derived from `floorplan.json`). The orange line follows the corridors; each walked leg gets its length in metres in orange (the grey label of that corridor is hidden under it); where the floor changes there is an orange tag (`Lift ▼ 4F` / `Escalator ▼ 4F` / `Stairs ▼ 4F` where you leave, `Lift from 5F` where you arrive). The card shows the metres on foot, the time (walking at 1.3 m/s + the ride), the floor change with its cost and the step list ("Take the lift down to 4F (about 42 s: 30 s waiting + 12 s ride, both guesses)").
- **Standard / Step-free** chips. Step-free = wheelchair: no stairs and no escalators, lifts only; any toilet request goes to a disabled toilet. **Any WC / Male / Female** chips = the toilet filter. **Nearest toilet** routes to the nearest toilet that fits both. Mode and filter are remembered per browser (`localStorage`, wrapped in try/catch; the page works without it). Changing the mode re-runs the last route.
- Typed toilet requests ("toilet", "restroom", "washroom", "where can I pee", or anything Gemini / keyword resolves to a toilet) also use the mode and filter. Words in the question win over the filter ("ladies" with the Male filter -> female toilet, and the card says so); "disabled" / "accessible" / "wheelchair" -> disabled toilets even in Standard; "4F" / "5F" -> that floor only. When Gemini picked a different toilet, its sentence is replaced by "Nearest ... toilet: ..." and the reply keeps `matched_place` (Gemini's pick).
- If the filter leaves no toilet the card says so in red and lists every toilet with the reason it was left out (e.g. "disabled toilet 5F" in Step-free + Female: the only 5F disabled toilet is male only).

Toilets we have (graph.json, names from `day3/config.json` `place_display`): 5F `male_toilet`, `female_toilet`, `disabled_toilet` = **Male** disabled toilet; 4F only `disabled_toilet_4F` = **Mixed** disabled toilet. There is no ordinary male or female toilet on 4F in our data. Filter rule: Male -> male toilets + mixed; Female -> female toilets + mixed; Step-free -> disabled toilets only (still with the gender rule). Ranking = route cost (seconds; on one floor this is the shortest walk); across floors the lift wait counts.

API (all GET, JSON, `400 {"error": ...}` for a bad value):
- `/api/route?from=<id>&to=<id>&mode=standard|accessible` -> `from`, `to`, `path` (graph ids), `route` (one step per place, with `map_key`, `floor`, `mode` = walk/stairs/lift/escalator, metres, seconds), `legs` (one per hop: kind, metres, seconds, length_status), `connectors`, `distance_m`, `seconds`, `instructions`.
- `/api/nearest?type=toilet&from=<id>&mode=&gender=any|male|female` -> the same route fields + `place_id` (null if none fits), `answer`, `options` (every fitting toilet with metres and seconds), `excluded` (with the reason).
- `/api/search?q=&from=&mode=&gender=` as before, plus `mode`, `gender`, `legs`, `connectors`, and `toilet` (options, excluded, note) for toilet requests.

Tests: `python -m unittest test_search.py` (16 tests: the earlier 10 + toilet requests under the filter, no-option message, Gemini answer post-processed, step-free route, `/api/route` and `/api/nearest` through a real server on a free port). Screenshots `screenshots/v4-*.png` (headless Chromium 1234, served by `server.Handler` without trained place models): Y5-302 -> Female toilet on 5F, Canteen -> LT1a Standard (escalator) vs Step-free (lift, 5F and 4F views), nearest toilet with the Female filter from Y5-401, Step-free + Female "toilet" from the canteen (lift to the 4F mixed toilet), the no-option card, a route set by tapping Y5-202 on the plan, and phone width 390 px in dark and light (page width = 390, no horizontal scroll; no console errors on any of them).

## ip16 and ip18: pooled training? (26 Nov, PROCESS-LOG entry 89)
`python eval_iphone_pool.py` (about 20 s, reads `walksense.py` read-only) writes `out/iphone_pool.json`: for each held-out ip18 session (`sesi1`, `25nov`, `25night`, 85 stops) the model is trained on (a) the other ip18 sessions, (b) those plus all ip16 sessions (`sesi2`, `25night_tian`, `26tian`), (c) ip16 only. (a) and (c) reproduce `out/eval.json` exactly. xyz top-1 / top-3: (a) 65/85, 73/85; (b) 67/85, 71/85; (c) 57/85, 70/85; macro precision 0.739 / 0.790 / 0.637. The day-3 fused kNN (`../day3/eval_iphone_pool_fused.py` > `../day3/out-iphone-pool/`) gives 59/85, 58/85 and 44/85 top-1. So ip16 alone is clearly worse on ip18, and pooling is a tie on top-1: **demo model = ip18 only** (what the app does already for an iPhone19,2 upload). To pool, `build_models()` would have to build the iPhone19,2 model from `training_stops(sessions=...)` of both iPhone models instead of `training_stops(device=d)`; not done. 23-Nov is not loadable by the app (no entry in `ALL_SESSIONS`).

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
- No replay export for `circle-ui`. (Route drawing: see "Route planner" above.)
- No graph prior (neighbouring places) on the place guess.
