# v3 app — handoff (28 Nov 2026)

*Internal team notes (not report text). Written for the teammate who will try to fix/test the live walk.*

Dicta's session built a new UI + smarter search on top of the v2 app, and tried a live walk test that got blocked by a VPN (not a code problem). Everything is here so you can pick it up.

## What `phase2/v3/upload/` is
A **copy of `phase2/v2/upload/` (your moved app) with two things changed**: a reworked front-end (`index.html`) and extra search features (`search.py`). Everything else (`walksense.py`, `live.py`, `server.py`, `map/`, tests) is your v2 code unchanged. It's in a **separate `v3/` folder on purpose so it does not overlap your v2.** The teammate's `phase2/new/routing/` tweak (ROUTING path) and the live-mode display tweaks (place at 1 s, floor note) are folded in.

**Run it** (same as v2):
```sh
cd phase2/v3/upload
python server.py --port 8000                                   # upload mode
python server.py --port 8000 --live http://<phone-ip> --device iPhone19,2 --floor 5   # live
```
It imports the **shared** `phase2/new/routing/route.py` and `phase2/request-matching/destinations.csv`, so those have small **additive** changes (below) that v2 also sees but doesn't use.

## What's new vs v2
**UI (`index.html`) — purely cosmetic/UX, no model/logic change:**
- Liquid-glass styling (frosted floating controls), fonts (Space Grotesk headings + Inter body), vanilla-tilt on buttons (CDN), iOS-style sliding toggles for Standard/Disabled + WC, a vertical floor capsule (5F/4F slider, Pic separate), a drag-to-resize panel/map splitter, a left-panel walking-guide line (shown only while walking), cursor/scroll-wheel zoom, responsive control rows.
- External CDNs used: Google Fonts + `vanilla-tilt` (both degrade gracefully offline).

**Search (`search.py` + shared `route.py`/`destinations.csv`):**
- **LT1/LT2 = one room, two doors.** "LT1 / classroom 1 / lecture hall 1 / kelas 1" routes to the **nearest door** (A from the gate side, B from the escalators). New `route.py` `nearest_door()` + `LECTURES` table; `search.py` `lecture_query()`.
- **"classroom" / "class" synonyms** added to the Y-rooms in `destinations.csv` (y5302, y5202, y5401, y5302_back, y4502).
- **"a X near a landmark"** (e.g. "classroom near male toilet" → Y5-302). Done by giving Gemini each place's map neighbours (`search.py` `_near_map`, `_ask_prompt_map`, `ASK_SYSTEM_MAP`). Works ~4/5 of the time (free Gemini model is imperfect on the "kind" filter).

## The live-walk trial (28 Nov) — what happened
We tried a live walk on Dicta's iPhone 18 (iPhone19,2). **The app worked** — it connected and processed ~5 minutes of real sensor data and produced floor + place guesses. **The blocker was the laptop's VPN (ProtonVPN / "ProTUN"):**
- With the VPN **on**, the laptop cannot reach the phone's phyphox at `http://172.20.10.1` (`WinError 10013`). Confirmed ~6 times: VPN on = unreachable, VPN off = connects.
- ProtonVPN **auto-reconnects**, and its "Allow LAN connections" setting is **paid-only**, so the feed kept dying mid-walk (froze the map on the last reading). Fully *quitting* the VPN app (not just disconnecting) is the reliable fix; or use **upload mode** (no network at all).
- **Accuracy caveat (separate from the VPN):** even with a steady feed the place guesses wandered among nearby 5F rooms (y5302/sr9/y5401). That's the known magnetic-fingerprint limit (~70% top-1 on stops, worse walking), not a bug. The 1 s live guess (entry 96) + the new `27nov` data may have shifted it vs a few days ago — worth a held-out re-check.

## The recordings (for you to test without a phone)
`phase2/v3/live-trial-2026-11-28/recordings/` has the **4 phyphox recordings saved during today's walk** (each phyphox play→pause). You can replay/upload them through the app (`Upload a recording`) to test floor + place without needing the live network.

## What's left for you
1. **Live walk** — either fully quit the VPN on the test laptop, or run the walk on a laptop with no forced VPN.
2. **Judge accuracy honestly** — upload the recordings here as stops/walks and compare to the held-out numbers; check whether 1 s-guess / `27nov` helped or hurt.
3. **If you keep this UI** — decide whether it replaces v2 or stays v3; wire `test_search.py` for the new LT-door/classroom cases before merging.

Full change narrative: PROCESS-LOG.md entry 98.
