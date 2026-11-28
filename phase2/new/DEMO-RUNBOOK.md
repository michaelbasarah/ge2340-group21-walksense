# Demo runbook (live WalkSense on Dicta's iPhone 18)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing). Written 27 Nov 2026 from the repo state at `38082d0` (PROCESS-LOG entry 92); the per-place numbers in sections e and f were refreshed on 27 Nov to the entry-91 official run (entry 94). Every command below was run or `--help`-checked on 27 Nov unless it says "not tested".*

Demo set-up: **Dicta's iPhone 18 (`iPhone19,2`) only**, model trained on iPhone 18 data only (PROCESS-LOG 89; `walksense.pick_model` does this by itself when the device is `iPhone19,2`). The app is `phase2/new/upload/` (`server.py`, `live.py`, `index.html`; set-up background in its `README.md`).

**Entries 90 and 91 have landed (main `a9326d3`).** Entry 90: floor rule (d) wired into the app, the a56 night excluded from the app's a56 model, Standard mode prefers ordinary toilets. Entry 91: the final day-3 headline excludes the a56 night. Do `git pull` and rerun the self-test (section c) as before; the toilet answers in section c were rechecked for entry 93, and the per-place numbers in section e were recomputed from the new `day3/out/` in entry 94.

## a) Night before checklist

- [ ] **Charge** the iPhone 18 (keep it plugged in during the demo if the cable allows), the laptop, and a power bank.
- [ ] **phyphox experiment** on the iPhone: one experiment with **magnetometer + accelerometer + gyroscope + BAROMETER** all ticked. Dicta's phone logged no pressure in 27 of 59 night takes (PROCESS-LOG 72), so open the experiment and look at the pressure graph before you leave: it must show a number (about 1000 hPa), not a flat empty line.
- [ ] **Allow remote access** in that experiment (phyphox menu). Test it again at the venue, the address changes with the network.
- [ ] iPhone settings: auto-lock set to Never (Settings > Display > Auto-Lock), VPN off, low-power mode off. Keep phyphox in the foreground with the screen on: whether iOS keeps serving with the phone in a pocket is **not confirmed** (upload README).
- [ ] **Laptop environment**: Python with `numpy pandas scikit-learn matplotlib`. Main laptop has `/home/basarah/personal/ge2340-team/.venv`. Fresh machine:
  ```sh
  python3 -m venv .venv && .venv/bin/pip install numpy pandas scikit-learn matplotlib
  ```
- [ ] **Update the code**: `cd <repo root>; git pull; git log --oneline -3` (note the commit hash on your phone: the demo must run on the commit you tested).
- [ ] **Fresh clone only: rebuild the gitignored clean data.** The app trains on 6 sessions at start-up and 3 of them are not in git, so a fresh clone stops with `KeyError: 'mag'` (entry 81, reproduced on 27 Nov in a new worktree). Two commands, a few seconds each, from the repo root:
  ```sh
  .venv/bin/python -I phase2/clean-data/2026-11-25-night/scripts/build_night.py     # sessions 25night + 25night_tian
  .venv/bin/python -I phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py     # session 26tian
  ```
  They print some "not built: review ..." lines about Tian's LT takes: expected (those takes are deliberately left out of training). Check that it worked: `ls phase2/clean-data/2026-11-25-night/round/clean/floor4 >/dev/null 2>&1 && echo built || echo REBUILD` must print `built`. Sessions 24-Nov and 25-Nov are in git and need no rebuild.
- [ ] **Gemini key**: it lives in the repo-root `.env` (gitignored; copy it from the laptop that has it, never through chat or git; a new worktree has no `.env`). Then
  ```sh
  .venv/bin/python phase2/new/upload/check_gemini.py
  ```
  Good = `OK: Gemini answered in ... Model: gemini-3.5-flash-lite` (it never prints the key, only its length). If it fails, the demo still works: search answers offline (keyword, then fuzzy) and the page says which method answered.
- [ ] **Tests (optional, about 90 s)**: `cd phase2/new/upload; ../../../.venv/bin/python -m unittest test_walksense.py test_live.py test_search.py` (not run on 27 Nov; README says about 90 s for the first two).
- [ ] **Start the server and look at the page** (commands in section b), then run the 2-minute self-test (section c) once the night before, in the room you will demo in if you can.
- [ ] Printed or phone-saved copy of this runbook and the route in section e. A second phone or the laptop to screen-record.

## b) Start commands, and finding the phone's IP

**Network (every time).** Laptop: Settings > Network > **Mobile hotspot** on. iPhone: join that hotspot, **VPN off** on both (the laptop has a `ProTUN` adapter: turn it off). CityU Wi-Fi usually blocks phone-to-laptop traffic, so do not use it. Allow Python through the Windows firewall if it asks. Anyone on the hotspot can reach the server, so keep the hotspot password private.

**Find the phone's address.**
1. In phyphox, switch on **Allow remote access**: phyphox shows `http://192.168.137.xx` (the hotspot gives out 192.168.137.x addresses). That is the address to use.
2. Or Windows Settings > Mobile hotspot > Connected devices lists the phone's IP.
3. Or from WSL: `powershell.exe -NoProfile -Command "arp -a"` and look in the 192.168.137.x block (command works; with no hotspot on it lists only the normal Wi-Fi block).

**Use the address without `:8080` (port 80).** On 25 Nov the probe was refused on `:8080` and worked without a port (entry 86). The upload README still says `:8080` in several places: ignore that (see "README outdated" in the entry-92 log).

**Probe first** (the phone must be on, phyphox open, remote access on):
```sh
cd phase2/new/upload
../../../.venv/bin/python live.py probe http://192.168.137.xx
```
Good output: four lines `acc`, `gyr`, `mag`, `baro`, each with a buffer name (not `NOT FOUND`), then a `status:` line and a sample count for each sensor. Check the `baro` line has samples: no samples = barometer not in the experiment. With nothing reachable the probe fails with `cannot reach ... same network? VPN off? phyphox remote access on?` (checked on 27 Nov against a closed port).

**Start the app** (about 45 s of training first; measured 43 s on 27 Nov):
```sh
cd phase2/new/upload
../../../.venv/bin/python server.py --port 8000 --live http://192.168.137.xx --device iPhone19,2 --floor 4
# v2 (1 s stand, entry 97): run the same command from phase2/v2/upload instead
```
- `--device iPhone19,2` is needed: the default is `iPhone17,4`, which would load the iPhone 16 model. The start-up line must say `trained on this phone model (iPhone19,2)`.
- `--floor` is the floor where you start (4 or 5). The suggested route in section e starts at the 4F gate, so `--floor 4`.
- Start-up lines to look for: `Live: reading http://... as iPhone19,2` and `Search: Gemini gemini-3.5-flash-lite (key from .env)` (or the "answers offline" line).
- Then press **play** in phyphox. Each play..pause is saved as `phase2/new/upload/recordings/<date-time>.zip` (gitignored): keep them, a later script can replay or score them.

**Opening the page.** The server prints the laptop's addresses. If the server runs **inside WSL** (our main laptop), the printed address is WSL's own (`192.168.x.x` on `eth0`, 27 Nov: `192.168.104.227`) and the phone cannot open it (entry 86). So:
- Demo from the **laptop's browser**: `http://127.0.0.1:8000` (WSL2 normally forwards localhost; the app was run in WSL on 25 Nov, entry 86; not re-tested on 27 Nov), and show/record the laptop screen. The phone only has to run phyphox.
- Showing the page on the phone itself needs a Windows port forward or WSL mirrored networking: **not tested**, do not try it for the first time on demo day.
- If the server runs on native Windows Python, the printed hotspot address (`192.168.137.1:8000`) should open on the phone: also not tested.

## c) Two-minute self-test (before recording)

The page and the commands below are on the laptop. `curl` and `python3 -m json.tool` are there in WSL.

1. **Probe** (section b): four buffers, baro has samples. (15 s)
2. **Live status**: with the server running and phyphox on play,
   ```sh
   curl -s http://127.0.0.1:8000/api/live | python3 -m json.tool | head -40
   ```
   Want: `"enabled": true`, `"device": "iPhone19,2"`, `"connected": true`, `"measuring": true`, `"error": ""`, `model_note` = `trained on this phone model (iPhone19,2), all sessions`, and `buffers` listing acc, gyr, mag, baro. On the page, open **Live sensor data ▸** (closed by default since entry 93): it says "Waiting for data" / "Standing" / "Stopped", never "Not connected to the phone". (15 s)
3. **One stop**: stand still, phone flat facing the door, for 10 s at any place. From 1 s Live sensor data says `Stopped ...` and the dashed "maybe" ring shows the best guess; from 3 s the circle lights if sure (at least 80%). The chip at the bottom right of the map shows the place and % (entry 96). The From list now reads "Current location (<that place>)". Then walk 10 steps: the blue dot moves. (35 s)
4. **Search** "where can I study": To = Study rooms (5F) and the route from Current location is drawn; no answer sentence (entry 93). Steps ▸ says `Search: offline keyword match` or `Search: Gemini`. Before any place has lit, the card says **Waiting for location** and draws nothing: that is expected. (10 s)
5. **One route**: To = LT1a, From = Canteen entrance. Standard: 37 m · 48 s, "Floor change: Escalator 5F → 4F" (36.6 m, 48.2 s, escalator down 20 s; checked offline 27 Nov with `search.plan_route`, rechecked for entry 93). (10 s)
6. **Toilet**: WC **Female**, From = Canteen, To = **Nearest toilet** (or search "toilet"): Female toilet (5F), 16 m · 12 s (checked offline). The old "Nearest toilet" button and "Any WC" chip are gone (entry 93); tap Female again for "any". (10 s)
7. **Disabled route**: chip **Disabled** (called Step-free before entry 93), same Canteen -> LT1a: 65 m · 1 min 32 s, "Floor change: Lift 5F → 4F" and a "Disabled: lifts only" tag (checked offline). Disabled + WC Female + To = Nearest toilet from the Canteen: Mixed disabled toilet (4F) via the lift, 30.5 m / 65.5 s (offline check, entry 93). (15 s)
8. **Start in the query** (entry 93): search "im in y5202, find me the nearest exit": From becomes Room Y5-202, To = Exit 10 (by the toilets), 15 m · 12 s (offline and with Gemini on 27 Nov). Since entry 94 every exit counts as an emergency exit, so "nearest emergency exit" gives the same answer (it was Exit 5, 38 m, before). Set From back to **Current location** afterwards. (10 s)
9. Back to Standard. Pause phyphox (saves a recording) and press play again before the real run.

If any step fails, go to the table.

## d) Failure and fix table

| What you see | Likely cause | Fix |
|---|---|---|
| `probe` / page says `cannot reach ... Connection refused` | Wrong port: phyphox on this iPhone serves on **port 80**, not 8080 (entry 86) | Use `http://192.168.137.xx` with no port. |
| Same error, address has no port | Remote access is off, phone slept, different network, or VPN on | Turn on Allow remote access, wake the phone, rejoin the laptop's hotspot, VPN off on both. |
| Page does not load on the phone | Server in WSL (printed IP is unreachable), hotspot off, firewall | Open `http://127.0.0.1:8000` on the laptop instead (section b). Allow Python in the Windows firewall. Same hotspot for both. |
| Page loads, status "Not connected to the phone" | `--live` address wrong, phyphox closed | Read the error text on the page; re-run `live.py probe` with the exact address; restart `server.py`. |
| Search says "answers offline" / no Gemini | No `.env`, no internet on the hotspot, timeout, quota (entry 71, 84) | **Expected and fine**: keyword then fuzzy still answers; the card's Steps ▸ says which method. Run `check_gemini.py` to see why. After no internet/timeout Gemini is skipped for 60 s; after a rejected key until restart. Raise `GEMINI_TIMEOUT_S` in `.env` if it is slow. |
| `KeyError: 'mag'` at start-up | Gitignored clean data not built (entry 81) | The two `build_night.py` / `build_tian26.py` commands in section a, then restart. |
| Floor wrong after a stop | Barometer missing or off in the phyphox experiment (floor note says `no barometer data: floor kept`), or you changed floor without a stop | Check the experiment has pressure; tap "I'm on 5F" / "I'm on 4F" once; stand still 10 s again. |
| Floor right, lit place wrong | Weak place (section e), phone not flat or not facing the door, 3 s window too short | Stand still **60 s** (the model was trained on 60 s stops), phone flat facing the door; the lit place can change as the stop gets longer. Only trust a lit circle that stays. |
| Nothing lights, only a "maybe" ring | Top guess under 80% | Wait longer; if still maybe, say it is unsure: that is the designed behaviour. |
| Blue dot jumps or sits still | Dot starts from the last named stop; it is wrong if that stop was wrong | Stand still at a strong place first so the dot restarts there. |
| Port 8000 already in use | An old server is running | Stop it (Ctrl+C) or use `--port 8001`. |
| Page shows the picture, not the plan | The map button was set to the picture | Press the map button (it says **Floor plan** then); the vector plan is the default. |
| Phone screen locks, data stops | Auto-lock | Settings > Display > Auto-Lock > Never; keep phyphox in front. |

## e) Suggested demo route and what to avoid

**Evidence, with its limits.** The per-place numbers are from the day-3 fused kNN, leave-one-session-out, iPhone 18 stops only (`phase2/new/day3/out/fused_sample_predictions.csv`, final entry-91 run, scheme `leave_one_session_out`, phone `ip18`; 85 stops over 24s1, 25nov, 25night; chance about 1 in 26). **ip18 headline in this file: 60/85 = 70.6% top-1, 73/85 top-3** (entry 91). The app's own model is a different kNN (entry 89, its own pooling test: 65/85 top-1, 73/85 top-3 for the app's model against 59/85 top-1 for the fused one), so these per-place counts only show **which places tend to be weak**, they do not predict this demo. Counts of 3 or 4 stops per place are tiny. Compared with the 26-Nov file that entry 92 used, three places moved (entry 91: the a56-night exclusion changes the tuned weights and k, the ip18 takes themselves are the same): y5202 2/4 to 3/4, escalator_down_4F 0/3 to 1/3, lt1a 1/3 to 2/3; all other ip18 places are unchanged. The 20 s-piece split (`out-split20`, ip18 175/253 = 69.2%) agrees on the weakest: escalator_down 0/6 and escalator_down_4F 0/9.

**Weak ip18 places (top-1 correct / stops):** escalator_down 0/2 (the only place still at 0), escalator_down_4F 1/3, then 2/4: sr9, disabled_toilet, lift_stairs, y5401. Next weakest, 2 of 3 (also avoid for a "must work" moment): disabled_toilet_4F, exit_5_4F, lt2b, y4502, lt1b, exit_10_4F, y5302, female_toilet, lt1a (lt1a moved up from 1/3).

**Stronger places (all stops right):** canteen 4/4, exit_5 3/3, male_toilet 3/3, escalator_up 2/2, lt2a 3/3, escalator_up_4F 3/3, entrance_exit 3/3. Next: exit_10 3/4, y5302_back 3/4, lift_stairs_4F 3/4, y5202 3/4 (moved up from 2/4).

**Suggested route: 7 stops, 4F then 5F** (same route as the scored walk in `live-walk/PROTOCOL.md`; start `--floor 4`):

| # | Place id | Name on the page | Floor | Fused ip18 |
|---|---|---|---|---|
| 1 | `entrance_exit` | Entrance gate (4F) | 4 | 3/3 |
| 2 | `lt2a` | LT2a | 4 | 3/3 |
| 3 | `escalator_up_4F` | Up escalator (4F) | 4 | 3/3 |
| (ride the escalator up: floor changes to 5) | | | | |
| 4 | `escalator_up` | Up escalator (5F) | 5 | 2/2 |
| 5 | `canteen` | Canteen entrance | 5 | 4/4 |
| 6 | `exit_5` | Exit 5 (emergency exit) | 5 | 3/3 |
| 7 | `male_toilet` | Male toilet | 5 | 3/3 |

Walking between them: gate to LT2a passes Exit 5 (4F); LT2a to the up escalator passes LT2b and the down escalator (4F). **Walk past, do not stop** at those (since entry 96 a stand of 1 s or more is read as a place). Stop 3 to 4 includes the escalator ride: do not stand still on the escalator, and stand still only after stepping off.

**Demo the planner on the strong places too:** search/route between them (Canteen -> LT1a Standard vs Disabled is the best story: escalator 36.6 m vs lift 65.0 m, both checked offline), then the WC toggle with To = Nearest toilet. **Avoid** as a live-lit moment: the two escalator-down stops, the 5F lift/stairs, and LT1a (now 2/3, no longer a 0 or 1). The route planner does not use the place guess for a typed From/To, so weak places are safe there: only the lit circle and the From = "Current location" default depend on the guess.

If a weak place must be shown, say it is the weak one before the lit circle appears, and have the retake ready (section f).

## f) Retake list for Dicta's iPhone 18

Why: these are the 6 weakest places (2/4 or worse) in the iPhone 18 leave-one-session-out numbers above (entry-91 official run; lt1a 2/3 and y5202 3/4 dropped off the earlier list of 8, lt1a is still worth one more take if there is time); more iPhone 18 stops at them is the only data that can change the demo (entry 89: other phones do not help). Each retake must be a **new session** (a different day or visit), not extra takes next to old ones, or the numbers become leaky again (CLAUDE.md, "same-recording splits give fake accuracy").

| Place id | Page name | Floor | Now |
|---|---|---|---|
| `escalator_down` | Down escalator (5F) | 5 | 0/2 |
| `escalator_down_4F` | Down escalator (4F) | 4 | 1/3 |
| `sr9` | Study rooms (SR8 to SR11 merged) | 5 | 2/4 |
| `disabled_toilet` | Male disabled toilet (5F) | 5 | 2/4 |
| `lift_stairs` | Lift and stairs (5F) | 5 | 2/4 |
| `y5401` | Room Y5-401 | 5 | 2/4 |

How to record each take:
1. **Barometer on**, checked before the first take (pressure graph moving). A take without pressure cannot be floor-tracked.
2. **One new recording per stop, 60 s**, phone **flat, facing the door/landmark**, same hold every time (DAY3-CHECKLIST). No pause/resume. Start the next recording only after the stop; walk to the next place between recordings.
3. **Name = place id + take + date**, exactly the ids in the table: `<place_id>_take<k>_<YYYYMMDD>-<HHMM>`, e.g. `escalator_down_4F_take1_20261128-1015`. Set it in phyphox when saving. The collector's own name is the ground truth (entry 79, labels never from timing). Put the floor in the id only as the repo already does (`_4F`), never in prose.
4. Several visits per place, on **different days if possible** (at least two takes per place, 3 is better); for the escalators stand still at the **foot/landing** and write down which end.
5. Sending the files (entry 79): **export from the iPhone itself and push the raw ZIPs to GitHub** (as Dicta did on 25 Nov) or send them from **her own WhatsApp** (an export only contains the files that device downloaded and sent; the laptop's chat export silently left out teammates' files). Never collect them through the laptop's WhatsApp Desktop export. Say in the group chat how many files were sent; the receiver counts them against that number and hashes them (`ingest_export.py`).
6. After ingest: add the labels, rerun `walksense.py evaluate` and `eval_iphone_pool.py` and log the result (PROCESS-LOG rule).
