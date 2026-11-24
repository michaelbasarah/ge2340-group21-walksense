# Circle navigator (UI prototype)

Code and UI only. A "circles on lines" navigator for the two floors (5F and 4F), subway-map style, instead of Google Maps. It replays a walk from a JSON file. No server, no build step.

## Open it
- Double-click `index.html` (works from disk), or from `phase2/new/` run `python -m http.server` and open `http://localhost:8000/circle-ui/index.html`.
- Press Play. Speed, scrub bar, next/previous frame and Restart are in the bar at the bottom.
- Phone (portrait, about 390 px): one floor at a time, switches automatically when the floor changes; tap 5F / 4F to look at the other one. Wide screens show both floors.
- `Theme` button: auto / light / dark.

## What you see
- Circles = checkpoints, lines = edges. The line from the current circle to the next one fills with the step count (dead reckoning). When the sensors confirm the next circle it lights up and the fill snaps to it. No compass: the arrow points along the planned route.
- States use fill, ring and icon as well as colour: hollow = not reached, dashed ring = next circle, filled with dot and pulsing ring = you (confirmed), dim with tick = visited, green with flag and double ring = destination, orange dashes = planned route, solid blue = filling as you walk.
- Shaded rounded region = the current area (the node `zone` field). Other areas are dotted outlines.
- Floor change (stairs, lift, escalator) is a dashed stub with a `4F` / `5F` badge; the fill runs along the stub on each floor.
- Panel (side on desktop, below the map on phone, no pop-ups): current place, floor, area, next circle with steps left, destination, steps, top-3 guesses with probabilities, and a replay check with two marks: exact point and area (area is right when the zone of the top guess equals the zone of `true_node`), plus a running count.
- Destination search: offline keyword rules ported from Dicta's matcher (`phase2/request-matching/match.py`, aliases from `destinations.csv`). Ties go to the nearest place. Route = shortest path by `distance_m` (else `median_steps`), computed in JS (Dijkstra) and recomputed from where you are. "Off the planned route" shows when the walk heads away from it.

## Data it loads (first match wins)
1. `?data=<same-site path>`, e.g. `index.html?data=../tracking/out/replay_23nov.json`. Other origins are refused. `?data=mock` forces the mock.
2. When served over http: `../tracking/out/replay_23nov.json` (tracker output). If it is missing the browser logs one harmless 404 and the page uses the mock.
3. The "Load JSON" button or dragging a file onto the page.
4. Otherwise the built-in mock, always labelled `MOCK DATA` on screen.

Other URL options: `t=<seconds>` start position, `speed=`, `play=1`, `floor=`, `theme=light|dark`.

## Format
```
{"graph": {"nodes": [{"id","floor","x","y","kind","zone","virtual","on_edge"}],
           "edges": [{"from","to","floor_change","distance_m","median_steps"}]},
 "destination": "<node id>",
 "frames": [{"t","floor","edge_from","edge_to","progress","node","confirmed","top3":[[id,prob],...],"true_node","steps_total"}]}
```
- `x`,`y`: any units, each floor is fitted to its panel. `zone` = area id such as `5F-study-corridor` or `a5_canteen_front` (shown as "5F · Study corridor"); null for virtual midpoints. Extra fields (`rec`, `meta`) are ignored.
- A frame with `confirmed: true` and `node` set snaps to that circle. A frame with `progress` (0 to 1) and `edge_from`/`edge_to` fills that edge. `true_node` is null when there is no ground truth (the exact/area marks then show "-").
- The page checks the file and refuses it with a message if ids/zones contain anything but letters, digits, `_` (and `-` in zones), if `floor` is not an integer, or numbers/booleans have the wrong type. Replay values are written to the page with `textContent`, never as HTML.

## Real data vs mock
- **Real (default over http):** `phase2/new/tracking/out/replay_23nov.json` from the tracker (v2): 40 nodes (31 real places plus 9 virtual midpoints), 39 edges, 5874 frames at 0.5 s, destination `escalator_up_4F`, real areas (`a5_...` / `a4_...` zones from `phase2/new/graph/nodes.csv`). `replay_17nov.json` also loads (`?data=../tracking/out/replay_17nov.json`; it has no destination, so the last real node is used). Checked with Playwright/headless Chromium: no console errors, full scrub through every frame.
- How the page treats the real file:
  - Virtual midpoints (`virtual: true`, `zone: null`, `on_edge: [a, b]`) are display-only: small grey dots on the line, no circle, label, area, search hit or route.
  - Area ids such as `a5_canteen_front` are shown as "5F · Canteen front".
  - Frames at a stop have null edge fields; walking frames have `true_node: null` (792 of 5874 frames in the 23-Nov file). The exact/area marks and the running tally skip frames with no `true_node`.
  - The tally is per 0.5 s frame (23-Nov: exact 1251/5082, area 1740/5082), so it is not the per-stop number in `phase2/new/tracking/README.md`.
  - Right after a floor change, while nothing on the new floor is confirmed yet, the tracker's guess on the new floor is shown as "you" (unconfirmed).
  - Playback skips recording breaks (a gap of more than 5 s between frames, e.g. the 32-minute break); the scrub bar still shows the real clock.
  - Edges with `median_steps: null` (some escalator lines) show no step count instead of "0 steps".
- If validation refuses a file, the reason now stays on screen above the mock that replaces it.
- **Mock** (`make_mock.py` -> `mock_replay.json`, `mock_replay.js`, `?data=mock` or opened from disk): REAL = the 31 place names, their floors and the visiting order of the 23-Nov route (`phase2/new/cross-day/labels_23nov_confirmed.csv`). FAKE = x,y layout, the 10 areas, distances, steps, progress, top-3 probabilities and the occasional wrong guess (seed 23). Destination `lt1a`.
- `places_data.js` is Dicta's `destinations.csv` as JS (real). Regenerate the mock with `python make_mock.py` (stdlib only).

## Files
`index.html` (page, CSS, JS) · `make_mock.py` · `mock_replay.json` / `mock_replay.js` · `places_data.js` · `screenshots/` (desktop 1280 px and phone 390 px, light and dark; `real-*.png` made with the real 23-Nov replay: start, mid-walk, stairs on 5F, first frame on 4F, arrival; the others with the mock).
