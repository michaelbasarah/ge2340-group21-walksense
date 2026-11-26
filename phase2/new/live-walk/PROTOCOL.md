# Live-walk protocol: one scored walk of WalkSense on Dicta's iPhone 18

*Internal team notes, not report text (course rule: an LLM may only polish our own writing). Written 27 Nov 2026 (PROCESS-LOG entry 92), **before any live walk was scored** (entry 86: the connection works, no scored walk exists). The scoring rule below is fixed now. If you change a rule after the first scored walk, write the change and the reason in PROCESS-LOG and say which walks used which rule.*

## What this measures

Whether the app, run live on the demo phone, lights the **right place**, on the **right floor**, **soon enough**, on a route written down in advance. It is a small honest test of the demo, not a replacement for the leave-one-session-out numbers (`upload/out/eval.json`). Only the demo phone (iPhone 18, `iPhone19,2`), the model trained on iPhone 18 data only (entry 89).

## Fixed before the walk

**Route (7 stops, the same for every scored walk; start on 4F):**

| Stop | `true_place_id` | Name on the page | Floor |
|---|---|---|---|
| 1 | `entrance_exit` | Entrance gate (4F) | 4 |
| 2 | `lt2a` | LT2a | 4 |
| 3 | `escalator_up_4F` | Up escalator (4F) | 4 |
| 4 | `escalator_up` | Up escalator (5F) | 5 (after riding up) |
| 5 | `canteen` | Canteen entrance | 5 |
| 6 | `exit_5` | Exit 5 (emergency exit) | 5 |
| 7 | `male_toilet` | Male toilet | 5 |

Why these places: they were the places with all stops right for iPhone 18 in the day-3 leave-one-session-out table (`DEMO-RUNBOOK.md` section e). So this walk tests the **best case** of the demo, not the average: if the walk fails here it will fail elsewhere; if it passes, say that it passed on the strong places only. A second, separate walk through the weak places can be scored with the same rules (write its route into this file first).

Between stops walk the corridors of `routing/graph.json` (gate -> Exit 5 4F -> LT2a; LT2a -> LT2b -> down escalator 4F -> up escalator 4F; ride up; up escalator 5F -> Canteen -> Exit 5 -> Male toilet). **Never stand still for 3 s or more anywhere except at the 7 stops**: the app reads that as a stop.

**People:** the **walker** (Dicta, holds the phone, does not look at the app page and does not see any score during the walk); the **scorer** (a second teammate at the laptop with the page open; does not tell the walker anything about lit places during the walk). The scorer marks arrivals; nobody edits anything during the walk.

**Number of scored walks: 3** (planned now). One extra **practice walk** first, not scored, to catch set-up problems (follow `DEMO-RUNBOOK.md` sections a to c). If only 1 or 2 scored walks are possible, report that number and say why. **Every scored walk is reported**, good or bad. A walk is **void** only if data stopped for a technical reason (phone locked, hotspot dropped, app crashed): write why in `notes`, keep the files, run a new walk. A walk is never void because the result was poor.

**App and model fixed:** note the commit (`git log --oneline -1`) and the exact start command in `server_start.txt`; do not change code, thresholds, training data or the model between walks. Do **not** add the walk's recording to the training data before all scored walks are scored (the recording folder is `upload/recordings/`, gitignored).

**Pass bar (write it here BEFORE walk 1, then do not change it):** ______ lit-correct out of 21 (3 walks x 7 stops). For reference only, not a bar: leave-one-session-out on iPhone 18 recordings is 65/85 top-1 (76%) in `upload/out/eval.json` / entry 89, with floor 100% in the 24-Nov and 25-Nov sessions (upload README).

## Running one walk

Set up (laptop, repo root; server on `--floor 4` as in `DEMO-RUNBOOK.md` section b). Replace `<run>` by `phase2/new/live-walk/runs/<YYYY-MM-DD>_walk<k>` (k = 1, 2, 3).

```sh
mkdir -p <run> && cd <run>
git log --oneline -1 > server_start.txt           # app commit; also paste the exact server.py command below it
# terminal 1: the server, output kept
cd <repo>/phase2/new/upload && ../../../.venv/bin/python server.py --port 8000 --live http://192.168.137.xx --device iPhone19,2 --floor 4 2>&1 | tee <run>/server.log
# terminal 2: one line of the live state per second
while true; do echo "{\"wall\":$(date +%s.%N),\"live\":$(curl -s -m 2 http://127.0.0.1:8000/api/live || echo null)}" >> <run>/live_log.jsonl; sleep 1; done
# terminal 3: the scorer's arrival marker. Type the stop number and Enter at the instant the walker stops moving.
while read -r s; do echo "$(date +%s.%N),$s" >> <run>/marks.csv; done
```
(The marker loop and the log loop were run on 27 Nov against a closed port: they write `epoch,stop` lines and `{"wall":...,"live":null}` lines. `/api/live` returns the whole live state: `state.mode`, `state.lit`, `state.top3`, `state.floor`, `state.stops`.) Both loops read the same laptop clock, so no clock sync with the phone is needed.

1. **Screen recording** of the laptop page for the whole walk (and, if possible, a second person filming the walker's feet). Keep the video **out of git** (large); put it in the team Drive and write the link in `notes.md`.
2. Phone: phyphox on **play**, barometer graph moving, screen on, **phone flat in the hand, facing the way of the door/landmark** at stops.
3. Walker walks to stop 1. The moment she stops, the scorer types `1` + Enter. She stands still **20 s**, flat, facing the door/landmark. The scorer counts 20 s on the laptop clock and says nothing. Then she walks to stop 2, and so on to stop 7.
4. **No retakes inside a walk.** If she stops at the wrong place or moves early, the scorer writes it in `deviation` (what, how long) and the stop is scored as normal against the planned place: it is a miss if the app lit something else. If she did not reach a planned stop at all, the stop is a miss with `deviation` filled.
5. After stop 7: pause phyphox (this saves `upload/recordings/<date-time>.zip`), stop the loops (Ctrl+C), copy that ZIP to `<run>/recording.zip`.

## Scoring rule (fixed)

For each planned stop `i` with arrival time `t_a` (the `marks.csv` row for stop `i`; if two rows for the same stop, the first):

- **Snapshot** = the last `live_log.jsonl` line with `wall <= t_a + 10.0` (10 s after arrival: the app names a place after 3 s of stillness and the stop is still going). Fields are read from `live.state`: `mode`, `lit`, `top3`, `floor`.
- **lit_correct**: snapshot `mode == "stop"` and `lit == true_place_id`. **Primary metric.** A stop that is not lit at 10 s (`lit` null, `mode` not `stop`) counts as **not correct** (not dropped from the denominator). A lit wrong place also counts as not correct; report "lit wrong" and "not lit" separately.
- **top1_correct**: `top3[0][0] == true_place_id` in the snapshot. **top3_correct**: `true_place_id` among the three ids in `top3`.
- **floor_correct**: snapshot `floor == true_floor`.
- **first_lit_place / first_lit_after_s**: the first log line with `wall >= t_a` and `mode == "stop"` and `lit` not null, within `t_a + 20 s`; the place, and `wall - t_a` in seconds (empty if none). The lit place can change as the stop goes on; the **10 s snapshot** is what is scored, the first-lit place is only reported. Time resolution is 1 s (the log period).
- **false stops** (per walk): the number of separate runs of log lines with `mode == "stop"` that start outside every `[t_a, t_a + 25 s]` window. They show the app naming a place while walking.
- **Time to light** (per walk): median and maximum of `first_lit_after_s` over stops that lit.

**Report, for each walk and pooled over the walks:** lit_correct / stops, lit wrong, not lit, top1_correct, top3_correct, floor_correct, median and max time to light, false stops. Always give the denominators (7 per walk; chance is about 1 in 12 to 14 places on a floor). Do not report the best walk alone, and do not report lit-correct among lit stops only unless the plain count is next to it. With 3 walks of 7 stops, one stop is 4.8 points: say it is a small test.

Do not mix this test with the training or tuning of the model, and do not retune the 80% light-up cut-off (`walksense.LIGHT_P`) on these walks (it was chosen on held-out recorded data, README).

## Filing the results (so a later script can score them)

One folder per walk, `phase2/new/live-walk/runs/<YYYY-MM-DD>_walk<k>/`:

| File | Content | In git? |
|---|---|---|
| `live_log.jsonl` | one JSON line per second: `{"wall": epoch seconds, "live": the /api/live reply or null}` | yes |
| `marks.csv` | no header; `epoch seconds,stop_no` (1 to 7), one line per arrival | yes |
| `score_sheet.csv` | a copy of `live-walk/score_sheet.csv` with 7 filled rows (columns below) | yes |
| `server_start.txt` | commit hash and the exact `server.py` command | yes |
| `server.log` | server output | yes |
| `recording.zip` | the saved phyphox recording (`upload/recordings/<date-time>.zip`), lets us replay the walk through the live code | yes if under a few MB |
| `notes.md` | who walked/scored, hotspot, deviations, void reason, links to the video | yes |
| screen recording `.mp4` | the page during the walk | **no** (Drive; link in `notes.md`) |

`score_sheet.csv` columns: `walk_id` (`<date>_walk<k>`), `date`, `walker_phone` (`iPhone19,2`), `app_commit`, `stop_no`, `true_place_id`, `true_floor`, `arrival_epoch_s` (from `marks.csv`), `stood_s` (how long she really stood, from the video), `state_mode_at_10s`, `lit_place_at_10s`, `top1_at_10s`, `top3_at_10s` (ids joined with `|`), `floor_at_10s`, `first_lit_place`, `first_lit_after_s`, `lit_correct`, `top1_correct`, `top3_correct`, `floor_correct` (1 or 0), `deviation`, `notes`. The columns from `state_mode_at_10s` to `floor_correct` must be **reproducible from `live_log.jsonl` + `marks.csv` by the rules above**: a scoring script reads those two files and fills the columns; if a hand-filled value differs from the script, the script's value is used and the difference goes into `notes`. (That script does not exist yet: write it before the first walk is scored, or fill the sheet by hand with the same rules and check by script later.)

Log the walks in PROCESS-LOG (what was run, the numbers from the filled sheets, voided walks, failures) in the same commit as the files.
