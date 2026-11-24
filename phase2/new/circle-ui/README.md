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
{"graph": {"nodes": [{"id","floor","x","y","kind","zone","virtual"}],
           "edges": [{"from","to","floor_change","distance_m","median_steps"}]},
 "destination": "<node id>",
 "frames": [{"t","floor","edge_from","edge_to","progress","node","confirmed","top3":[[id,prob],...],"true_node","steps_total"}]}
```
- `x`,`y`: any units, each floor is fitted to its panel. `zone` = area id such as `5F-study-corridor` (shown as "5F · Study corridor").
- A frame with `confirmed: true` and `node` set snaps to that circle. A frame with `progress` (0 to 1) and `edge_from`/`edge_to` fills that edge. `true_node` is null when there is no ground truth (the exact/area marks then show "-").
- The page checks the file and refuses it with a message if ids/zones contain anything but letters, digits, `_` (and `-` in zones), if `floor` is not an integer, or numbers/booleans have the wrong type. Replay values are written to the page with `textContent`, never as HTML.

## Mock vs real
- Mock (`make_mock.py` -> `mock_replay.json`, `mock_replay.js`): REAL = the 31 place names, their floors and the visiting order of the 23-Nov route (`phase2/new/cross-day/labels_23nov_confirmed.csv`). FAKE = x,y layout, the 10 areas, distances, steps, progress, top-3 probabilities and the occasional wrong guess (seed 23). Destination in the mock is `lt1a`. The mock walk is the data-collection walk, so it often leaves the planned route.
- Real: nothing yet. Needs the tracker output `phase2/new/tracking/out/replay_23nov.json` and the graph with real x,y and areas.
- `places_data.js` is Dicta's `destinations.csv` as JS (real). Regenerate everything with `python make_mock.py` (stdlib only).

## Files
`index.html` (page, CSS, JS) · `make_mock.py` · `mock_replay.json` / `mock_replay.js` · `places_data.js` · `screenshots/` (desktop 1280 px and phone 390 px, light and dark; made with the mock).
