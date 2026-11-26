# Demo runbook (live WalkSense on Dicta's iPhone 18)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing). Written 27 Nov 2026 from the repo state at `38082d0` (PROCESS-LOG entry 92). Every command below was run or `--help`-checked on 27 Nov unless it says "not tested".*

Demo set-up: **Dicta's iPhone 18 (`iPhone19,2`) only**, model trained on iPhone 18 data only (PROCESS-LOG 89; `walksense.pick_model` does this by itself when the device is `iPhone19,2`). The app is `phase2/new/upload/` (`server.py`, `live.py`, `index.html`; set-up background in its `README.md`).

**Two changes land after entries 90 and 91 (other workers).** Entry 90: floor rule (d) wired into the app, the a56 night excluded from the app's a56 model, Standard mode prefers ordinary toilets. Entry 91: the final day-3 headline excludes the a56 night. Nothing below depends on them, but after they land: `git pull`, rerun the self-test (section c), and the toilet answers in section c may change (Standard prefers an ordinary toilet over the disabled one). Re-check the numbers in section e against the new `day3/out/`.

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
   Want: `"enabled": true`, `"device": "iPhone19,2"`, `"connected": true`, `"measuring": true`, `"error": ""`, `model_note` = `trained on this phone model (iPhone19,2), all sessions`, and `buffers` listing acc, gyr, mag, baro. The page's status line says "Waiting for data" / "Standing" / "Stopped", never "Not connected to the phone". (15 s)
3. **One stop**: stand still, phone flat facing the door, for 10 s at any place. At 3 s the page says `Stopped ...`, the top-3 appears, the floor note appears once. Lit circle if sure (at least 80%), dashed "maybe" ring if not. Then walk 10 steps: the blue dot moves. (35 s)
4. **Search** "where can I study": expect the Study rooms (5F), method `keyword` offline or `gemini` with a key. (10 s)
5. **One route**: To = LT1a, From = Canteen entrance. Standard: 36.6 m, 48.2 s, escalator down 20 s (checked offline 27 Nov with `search.plan_route`). (10 s)
6. **Toilet chip**: chip Female, "Nearest toilet" from the Canteen: Female toilet (5F), about 16 m (checked offline). (10 s)
7. **Step-free route**: chip Step-free, same Canteen -> LT1a: lift, 65.0 m, 92 s, the card names the lift (checked offline). Step-free + Female toilet from the Canteen goes to the Mixed disabled toilet (4F) via the lift, about 30 m / 66 s (offline check). **After entry 90 lands** the Standard toilet answers may change; the Step-free ones should not. (15 s)
8. Back to Standard. Pause phyphox (saves a recording) and press play again before the real run.

If any step fails, go to the table.

## d) Failure and fix table

| What you see | Likely cause | Fix |
|---|---|---|
| `probe` / page says `cannot reach ... Connection refused` | Wrong port: phyphox on this iPhone serves on **port 80**, not 8080 (entry 86) | Use `http://192.168.137.xx` with no port. |
| Same error, address has no port | Remote access is off, phone slept, different network, or VPN on | Turn on Allow remote access, wake the phone, rejoin the laptop's hotspot, VPN off on both. |
| Page does not load on the phone | Server in WSL (printed IP is unreachable), hotspot off, firewall | Open `http://127.0.0.1:8000` on the laptop instead (section b). Allow Python in the Windows firewall. Same hotspot for both. |
| Page loads, status "Not connected to the phone" | `--live` address wrong, phyphox closed | Read the error text on the page; re-run `live.py probe` with the exact address; restart `server.py`. |
| Search says "answers offline" / no Gemini | No `.env`, no internet on the hotspot, timeout, quota (entry 71, 84) | **Expected and fine**: keyword then fuzzy still answers, the page says which method. Run `check_gemini.py` to see why. After no internet/timeout Gemini is skipped for 60 s; after a rejected key until restart. Raise `GEMINI_TIMEOUT_S` in `.env` if it is slow. |
| `KeyError: 'mag'` at start-up | Gitignored clean data not built (entry 81) | The two `build_night.py` / `build_tian26.py` commands in section a, then restart. |
| Floor wrong after a stop | Barometer missing or off in the phyphox experiment (floor note says `no barometer data: floor kept`), or you changed floor without a stop | Check the experiment has pressure; tap "I'm on 5F" / "I'm on 4F" once; stand still 10 s again. |
| Floor right, lit place wrong | Weak place (section e), phone not flat or not facing the door, 3 s window too short | Stand still **60 s** (the model was trained on 60 s stops), phone flat facing the door; the lit place can change as the stop gets longer. Only trust a lit circle that stays. |
| Nothing lights, only a "maybe" ring | Top guess under 80% | Wait longer; if still maybe, say it is unsure: that is the designed behaviour. |
| Blue dot jumps or sits still | Dot starts from the last named stop; it is wrong if that stop was wrong | Stand still at a strong place first so the dot restarts there. |
| Port 8000 already in use | An old server is running | Stop it (Ctrl+C) or use `--port 8001`. |
| Page shows the picture, not the plan | The map button was set to the picture | Press the map button (it says **Floor plan** then); the vector plan is the default. |
| Phone screen locks, data stops | Auto-lock | Settings > Display > Auto-Lock > Never; keep phyphox in front. |

## e) Suggested demo route and what to avoid

**Evidence, with its limits.** The per-place numbers are from the day-3 fused kNN, leave-one-session-out, iPhone 18 stops only (`phase2/new/day3/out/fused_sample_predictions.csv`, scheme `leave_one_session_out`, phone `ip18`; 85 stops over 24s1, 25nov, 25night; chance about 1 in 26). The app's own model is a different kNN (entry 89: 65/85 top-1, 73/85 top-3 against 59/85 for the fused one), so these per-place counts only show **which places tend to be weak**, they do not predict this demo. Counts of 3 or 4 stops per place are tiny. Rerun after entries 90/91: the a56 night is not iPhone data, so ip18 counts should not change, but check.

**Weak ip18 places (top-1 correct / stops):** escalator_down_4F 0/3, escalator_down 0/2, lt1a 1/3, sr9 2/4, y5202 2/4, disabled_toilet 2/4, lift_stairs 2/4, y5401 2/4. Next weakest, 2 of 3 (also avoid for a "must work" moment): disabled_toilet_4F, exit_5_4F, lt2b, y4502, lt1b, exit_10_4F, y5302, female_toilet.

**Stronger places (all stops right):** canteen 4/4, exit_5 3/3, male_toilet 3/3, escalator_up 2/2, lt2a 3/3, escalator_up_4F 3/3, entrance_exit 3/3. Next: exit_10 3/4, y5302_back 3/4, lift_stairs_4F 3/4.

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

Walking between them: gate to LT2a passes Exit 5 (4F); LT2a to the up escalator passes LT2b and the down escalator (4F). **Walk past, do not stop** at those (a stop of 3 s or more is read as a place). Stop 3 to 4 includes the escalator ride: do not stand still on the escalator, and stand still only after stepping off.

**Demo the planner on the strong places too:** search/route between them (Canteen -> LT1a Standard vs Step-free is the best story: escalator 36.6 m vs lift 65.0 m, both checked offline), then the toilet chips. **Avoid** as a live-lit moment: the two escalator-down stops, LT1a, and the 5F lift/stairs. The route planner does not use the place guess for a typed From/To, so weak places are safe there: only the lit circle and the From = "where I am" default depend on the guess.

If a weak place must be shown, say it is the weak one before the lit circle appears, and have the retake ready (section f).

## f) Retake list for Dicta's iPhone 18

Why: these are the 8 weakest places in the iPhone 18 leave-one-session-out numbers above; more iPhone 18 stops at them is the only data that can change the demo (entry 89: other phones do not help). Each retake must be a **new session** (a different day or visit), not extra takes next to old ones, or the numbers become leaky again (CLAUDE.md, "same-recording splits give fake accuracy").

| Place id | Page name | Floor | Now |
|---|---|---|---|
| `escalator_down_4F` | Down escalator (4F) | 4 | 0/3 |
| `escalator_down` | Down escalator (5F) | 5 | 0/2 |
| `lt1a` | LT1a | 4 | 1/3 |
| `sr9` | Study rooms (SR8 to SR11 merged) | 5 | 2/4 |
| `y5202` | Room Y5-202 | 5 | 2/4 |
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
