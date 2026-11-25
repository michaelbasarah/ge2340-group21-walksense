#!/usr/bin/env python3
"""Per-place hit counts from the existing outputs, to name the places that were never (or almost never) classified
correctly, and to follow them after new data is added. Numbers only, read from the output files.

    python phase2/new/day3/hard_places.py --label before_25nov out out-split20
    (a run dir can be given as name=folder, e.g. out=/tmp/copy-of-committed-out)

Per run dir and place: leave-one-session-out windows (fused_window_predictions.csv, learned-weight fused kNN),
grouped-by-stop windows (same file), leave-one-session-out samples (fused_sample_predictions.csv, if present) and the
honest named splits of results.json (every feature set, cross-session / cross-day / leave-25-Nov-out; LEAKY excluded).
Writes out/perf_csv/hard_places_<label>.csv and prints the places with zero correct.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def per_place(run: Path) -> pd.DataFrame:
    w = pd.read_csv(run / 'fused_window_predictions.csv')
    out = {}
    for sch, tag in [('leave_one_session_out', 'loso_win'), ('grouped_by_stop', 'grouped_win')]:
        l = w[w['scheme'] == sch]
        g = (l['true'] == l['pred_window']).groupby(l['true'])
        out[f'{tag}_correct'] = g.sum().astype(int); out[f'{tag}_n'] = g.size()
    sp = run / 'fused_sample_predictions.csv'
    if sp.exists():
        s = pd.read_csv(sp)
        s = s[s['scheme'] == 'leave_one_session_out']
        g = (s['true'] == s['pred']).groupby(s['true'])
        out['loso_sample_correct'] = g.sum().astype(int); out['loso_sample_n'] = g.size()
        out['loso_sample_top3'] = s['in_top3'].astype(str).str.lower().eq('true').groupby(s['true']).sum().astype(int)
    R = json.loads((run / 'results.json').read_text())
    c, n = {}, {}
    for e, blk in R['stop_results'].items():
        if e.startswith('LEAKY'):
            continue
        for fs, r in blk.items():
            if isinstance(r, dict) and 'predictions' in r:
                for t, p in r['predictions'].values():
                    c[t] = c.get(t, 0) + (t == p); n[t] = n.get(t, 0) + 1
    out['named_splits_correct'] = pd.Series(c, dtype=int); out['named_splits_n'] = pd.Series(n, dtype=int)
    D = pd.DataFrame(out).fillna(0).astype(int)
    D.index.name = 'place'
    return D


def main():
    args = sys.argv[1:]
    label = 'now'
    if args[:1] == ['--label']:
        label, args = args[1], args[2:]
    frames = []
    for d in args:
        d, _, path = d.partition('=')            # 'out' or 'out=<folder holding a copy of out/>'
        D = per_place(HERE / (path or d))
        D.columns = [f'{d}:{c}' for c in D.columns]
        frames.append(D)
    T = pd.concat(frames, axis=1).fillna(0).astype(int).sort_index()
    out = HERE / 'out' / 'perf_csv' / f'hard_places_{label}.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    T.to_csv(out)
    for col in T.columns:
        if col.endswith('_correct'):
            nc = col[:-len('_correct')] + '_n'
            zero = [p for p in T.index if T.loc[p, col] == 0 and T.loc[p, nc] > 0]
            print(f'{col}: zero correct at {zero}')
    print('wrote', out)


if __name__ == '__main__':
    main()
