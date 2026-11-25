# Results pack (figures, tables, internal number sheets)

*Internal team notes and tooling, not report text (course rule: an LLM may only polish our own writing). It builds figures, tables and fact sheets from the committed outputs; it writes no report or slide prose.*

## Rerun

From the repo root (needs `numpy pandas matplotlib`; the repo `.venv` has them):

```sh
.venv/bin/python phase2/new/results-pack/build.py                       # about 1 min, rewrites out/
.venv/bin/python phase2/new/results-pack/build.py --repo-root <checkout> # read the sources from another checkout (e.g. main after the 25-Nov data lands)
```

`build.py` clears and rewrites `out/` each run. After new data lands: rerun the day-3 pipeline (`sh phase2/new/day3/run_all.sh`, and `--split20`) first, then rerun this. Paths are in `config.json`; no result number is typed in `build.py`. A missing or changed source is reported at the end (`numbers.md`, section "Not found / skipped") and the matching figure or row is skipped.

## What is in `out/`

| file | content |
|---|---|
| `index.html` | one-page gallery of all figures (slide and report size) plus the positioning table |
| `numbers.md` | every headline number: value, 95% CI (Wilson), n, chance, kind (honest / partly leaky / LEAKY), exact test definition, source file, last commit of the source. Ends with known inconsistencies between source files (flagged, not fixed) |
| `timeline.md` | dated sessions (14, 17, 23, 24, 25 Nov): what each added, failures, lessons, then analysis milestones. Numbers come from the sources; the wording is in `timeline_facts.json` (copied from PROCESS-LOG, entry numbers in brackets) |
| `positioning_table.md/.csv` | proposal methods A (dead reckoning), B (Wi-Fi kNN), C (magnetic kNN), D (HMM fusion + barometer) with the honest held-out number, n, chance, and the LEAKY and partly-leaky numbers in their own columns. `positioning_table_split20.*` = the fused-framework rows on 20 s pieces |
| `table_*.csv` | all day-3 tests, per place, phone x place, tracker vs snapshot, request matching |
| `fig_*_slide.png/.svg` | 16:9 (13.33 x 7.5 in), 300 dpi PNG plus SVG, large fonts |
| `fig_*_report.png/.svg` | 5.5 in wide (the template text width), 300 dpi PNG plus SVG |

Figures: `honest_vs_leaky` (99.7% to 36.6%), `accuracy_vs_chance` (every test, chance tick), `per_place_accuracy` (place x held-out session), `phone_place`, `phone_session`, `cross_bars` (cross-session and 17 vs 23 Nov), `floor_timeline` (pressure per stop, wrong floors ringed), `variance` (places / sessions / phones / recordings), `tracker_vs_snapshot`, `wifi_diagnosis`. Palette: Okabe-Ito (colour-blind safe); leaky bars are hatched as well as coloured.

## Conventions

- Primary variant = take level (`phase2/new/day3/out/`); the 20 s-piece variant (`out-split20/`) is shown in `numbers.md` section 3 and the `_split20` table. Change `primary_variant` in `config.json` to switch the figures.
- Heat maps use `fused_sample_predictions.csv` (learned-weight fused kNN, leave one session out, per recording; written by the day-3 pipeline since entry 43); the dated `..._2026-11-25a.csv` copy is only a fallback (`config.json`).
- Request matching (`table_request_matching.csv`, facts `rm.<method>.test` / `.all`): keyword, embeddings, LLM (cached answers), fuzzy keyword, hybrid and the starter token overlap from `phase2/request-matching/results.csv`; the test split is the honest number, "all" includes the dev rows used for tuning.
- Wilson intervals, the 1/2 chance of the floor tests and the pilot's hit count (stored only as a rate) are computed by `build.py`; they are marked "derived" in `numbers.md`.
- Tian's upload app (PROCESS-LOG 66): `up.<training sessions> -> <held-out session> <feature>.top1` (`sesi1`, `sesi2`, `25nov`; `same_model` or `cross_handset` in `numbers.md`). `up24.*` = the same eval before the 3-session retrain (`eval_2026-11-24.json`). `up20.*` (20 s pieces) is still the old 24-Nov-only model, not rerun.
- The failure and lesson bullets in `timeline_facts.json` are hand-kept text copied from PROCESS-LOG; update them when the log changes.
