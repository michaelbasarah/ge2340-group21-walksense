# WalkSense-Work

All the data cleaning + AI done for the GE2340 project, kept **separate** from the teammates'
zip (`../ge2340-group21-walksense-main/`). Nothing here touches their folder.

Needs: Python 3 with `numpy pandas scikit-learn matplotlib model2vec` (all installed on this laptop).

Full history of what we tried and what happened (failures included): [`../PROCESS-LOG.md`](../PROCESS-LOG.md).

## old/ and new/
`old/` holds work that is superseded and is kept only so history stays readable: the positioning pilot trained and tested on the same recording (leakage), and the old collect list predates the 24-Nov findings. `new/` holds today's analysis and what to do next. Start with `new/TEAM-SUMMARY-2026-11-24.md`, then follow `new/DAY3-CHECKLIST.md` when collecting. `clean-data/`, `map/`, `prototype/`, `request-matching/` and `field-sheet.html` stay where they are.

## Folders
| Folder | What it is | Run |
|---|---|---|
| `clean-data/2026-11-17/` | The cleaned 17 Nov session (26 stops, 23 walks, Wi-Fi), labelled + validated. | `python clean.py` then `python feature_extraction.py` |
| `old/` | **Superseded 2026-11-24.** Dicta's positioning pilot (`old/positioning-pilot/`, its ~94% was leaky) and the old collect list. Kept for history. | `cd old/positioning-pilot && python pilot_train.py` |
| `new/` | **Current.** `new/cross-day/` = leakage-reduced and cross-day analysis; `new/TEAM-SUMMARY-2026-11-24.md`; `new/DAY3-CHECKLIST.md` = the collection rules for day 3. | `python new/cross-day/crossday.py`, then `tilt.py` |
| `request-matching/` | Objective #9 — type a request, get a place (keyword + embedding). | `python match.py` or `python match.py "where can i eat"` |
| `map/` | Floor-5 coordinates → metres, corridor graph, map previews. | `python build_map.py` |
| `prototype/` | The demo web app (search + positioning replay + floor-5 map + routing). | `python server.py` → http://127.0.0.1:5173 |
| `GMaps/` | Google indoor-map screenshots + the raw checkpoint coordinates (floor 5). | — |

## The prototype (start here to see it)
```
cd prototype
python server.py        # then open http://127.0.0.1:5173
```
Three parts: **(1)** "Where do you want to go?" — keyword vs embedding matching;
**(2)** "Replay a walk" — the positioning engine on the real 17 Nov walk; **(3)** "Find your way" —
floor-5 map with room blocks, corridors and A* routing.

## Done
- **Cleaning** (`clean-data/2026-11-17/`): 101,436 accepted sensor readings, full accountability,
  validation checks. Detected and quarantined a **double-exported stop** (one `poin` recording was a
  re-export of another). Review everything in `review_all_recordings.csv`.
- **Positioning (#1–#3):** magnetic k-NN separates the 26 stops (silhouette 0.44), barometer splits the
  two floors cleanly, step detector reads realistic cadence (~1.6 steps/s). *Single-session numbers are
  optimistic — a real score needs a second day.*
- **Text matching (#9):** keyword + offline embedding (model2vec) with a confidence threshold.
  Fixed semantics: "emergency" → emergency exit, "leave the building" → exit gate, study rooms need
  booking so "revise" is not auto-assigned.
- **Map + routing (#4 partial, #10 partial):** floor-5 coordinates converted to metres (distances match
  tape measurements), A* on an **editable corridor graph** (`map/edges_floor5.csv`).

## In progress
- **#4 metres / #10 routing:** floor 5 only. Needs **floor-4 coordinates** and the escalator link to span
  both floors. The map shows only the 12 checkpoints as blocks — true room footprints need a traced plan.
- **#11 UI:** this is a **prototype** to prove the pieces work. The polished final UI is the teammate's job.

## Blocked / not started (need the next data collection)
- **#5 Wi-Fi** — re-collect with **scan throttling OFF** (12/26 stops had no Wi-Fi this time).
- **#6 heading** — record **gyroscope + magnetometer during the walks** (only recorded at stops this time).
- **#7 fusion, #8 wrong-turn, #12 user tests** — built on top of the above.
- **LLM matching method** — needs an API key (keyword + embedding already work offline).

## Editable data files (safe to correct by hand)
- `map/coordinates.csv` — checkpoint lat/long (+ floor). Delete a row to drop a checkpoint.
- `map/edges_floor5.csv` — which checkpoints connect by a corridor. Remove wall-crossers, add missing links;
  the map and routes update from this.
- `request-matching/destinations.csv` — places + synonyms. `test_queries.csv` — matching test set.
- `clean-data/2026-11-17/review_all_recordings.csv` — confirm labels / floors here.
