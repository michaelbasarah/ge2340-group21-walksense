# Continuous place estimate: offline study (PROCESS-LOG entries 60, 61)

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Question: in live mode, can the place kNN run every 1 s or faster and be combined over time
(s_t = a p_t + b p_(t-1) + c p_(t-2) + ...) so it keeps updating without jumping around?
Offline only: nothing in `../upload/` (Tian's app) is changed or used differently.

```sh
python phase2/new/smoothing/tune.py   # ~6 min on 20 cores; writes out/live_smoothing.json, out/live_smoothing.csv, out/fig_*.png
```
Needs the same packages as `upload/` plus scipy (already a scikit-learn dependency).

- `smooth.py`: estimators (none, FIR a,b,c..., EMA, jump guard, HMM forward filter on the recorded corridors), gating, pre-filter, abstain.
- `replay.py`: streams a 24-Nov session through Tian's `LiveTracker` (subclassed, his `update()` runs unchanged) and logs a continuous estimate every tick.
- `tune.py`: the grid (22,896 settings per session), the selection rule (in its docstring and in log entry 60, fixed before the first result), nested leave-one-session-out, abstain curve, per-phone offset check, figures.

Outputs: `out/live_smoothing.json` (`baseline_tian_3s`, `nested` = per family: chosen on one session and scored on the other, both directions, plus the pooled choice; `abstain`; `visit_level_calibration`; `end_to_end_check`; `gate_stats`), `out/live_smoothing.csv` (every setting, both sessions and pooled), `out/fig_heldout.png`, `out/fig_timeline.png`. Results and caveats: PROCESS-LOG entry 61.
