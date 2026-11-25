#!/usr/bin/env python3
"""Per-phone x per-place performance sheet (internal team tool; numbers only, no report text).

Appends ONE evaluation run to out/phone_place_performance.xlsx as a new dated tab, appends one row to the `Progress`
tab, and rebuilds the `Ranking` tab from that run. Earlier run tabs and Progress rows are never changed or deleted;
a tab name that already exists stops the script (pick a new name).

    python phase2/new/day3/perf_sheet.py --run-dir out-split20 --tab "2026-11-25 split20 +25Nov" --data "23nov 24s1 24s2 25nov"

Source: <run-dir>/fused_sample_predictions.csv (written by fused_knn.py: one row per test sample of the learned-weight
fused kNN, with its top-3) and <run-dir>/fused_knn.json. Default scheme = leave_one_session_out (the most honest
split: a whole session is held out, train on the others; every phone and every take of a stop stays on one side).
The same tables are written as CSV to out/perf_csv/.

Definitions (per phone p and place X, over p's test samples):
  n          test samples of p whose true place is X (sample = one take; one 20 s piece in split20)
  correct    of those, predicted X
  recall     correct / n  (= per-place accuracy)
  precision  samples of p predicted X that really are X / samples of p predicted X (blank if p never predicted X)
  F1         2 PR / (P + R) (0 when either is 0, blank when precision is blank and recall is 0)
  top-3      true place among the 3 best-scoring places
Per-phone summary: accuracy = correct / n over all its samples; macro precision / recall / F1 = mean over the places in
that phone's test set (a place never predicted counts precision 0, as sklearn zero_division=0).
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
XLSX = HERE / 'out' / 'phone_place_performance.xlsx'
CSV_DIR = HERE / 'out' / 'perf_csv'
BOLD = Font(bold=True)
HEAD = PatternFill('solid', fgColor='DDE6F0')

README = [
    ['WalkSense: per-phone x per-place performance (internal team sheet, numbers only)'],
    [],
    ['What', 'One tab per evaluation run (date + variant + data). Tabs are appended by phase2/new/day3/perf_sheet.py and never rewritten.'],
    ['Model', 'Weighted fused kNN (fused_knn.py): |B|, magnetic x/y/z, tilt, Wi-Fi, barometer floor; weights and k chosen by inner CV on the training part only.'],
    ['Evaluation', 'Leave one session out: each session (23 Nov, 24 Nov s1, 24 Nov s2, 25 Nov, ...) is held out in turn and the model is trained on all the others '
                   '(all phones). Grouped by take: all windows / 20 s pieces of one take, and all phones of one stop, are on the same side. '
                   'Nothing of the test session is used for training or tuning.'],
    ['Sample', 'default variant: one whole take (60 s stop recording, its 5 s windows vote); split20: one 20 s piece of a take (3 per take).'],
    ['n', 'test samples of that phone whose true place is that place'],
    ['correct / recall', 'predicted that place; recall = correct / n (per-place accuracy)'],
    ['precision', 'of the samples of that phone the model called this place, the share that really were this place (blank = never predicted)'],
    ['F1', '2PR/(P+R)'],
    ['top-3', 'true place among the 3 best-scoring places'],
    ['Phone summary', 'accuracy over all samples; macro precision / recall / F1 = mean over the places in that phone\'s test set (never-predicted place = precision 0)'],
    ['Chance', '1 / number of places in training (26 graph-v2 places = 3.8%)'],
    ['Ranking tab', 'rebuilt from the latest run tab each time: phones by accuracy, places by recall (all phones)'],
    ['Progress tab', 'one row appended per run; earlier rows are never changed'],
    ['CSV', 'the same tables in phase2/new/day3/out/perf_csv/'],
    ['Tian\'s sheet', '"WalkSense ranking by phone.xlsx" (sent 25 Nov 17:45) was not in the WhatsApp export; columns to be matched when it arrives.'],
]


def metrics(df: pd.DataFrame) -> pd.DataFrame:
    """df: rows of one phone (or all). Per true place: n, correct, recall, precision, F1, top-3."""
    rows = []
    for place in sorted(set(df['true'])):
        t = df[df['true'] == place]
        pr = df[df['pred'] == place]
        n, c = len(t), int((t['pred'] == place).sum())
        rec = c / n
        prec = (int((pr['true'] == place).sum()) / len(pr)) if len(pr) else np.nan
        f1 = (2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0) if np.isfinite(prec) else (0.0 if rec == 0 else np.nan)
        rows.append({'place': place, 'floor': int(t['place_floor'].iloc[0]), 'n': n, 'correct': c, 'recall': rec,
                     'precision': prec, 'f1': f1, 'n_predicted_as': len(pr), 'top3': int(t['in_top3'].sum()), 'top3_rate': t['in_top3'].mean()})
    return pd.DataFrame(rows)


def summary(df: pd.DataFrame, m: pd.DataFrame) -> dict:
    return {'n': len(df), 'correct': int((df['true'] == df['pred']).sum()), 'accuracy': float((df['true'] == df['pred']).mean()),
            'macro_precision': float(m['precision'].fillna(0).mean()), 'macro_recall': float(m['recall'].mean()),
            'macro_f1': float(m['f1'].fillna(0).mean()), 'top3_acc': float(df['in_top3'].mean()), 'places': len(m)}


def write_rows(ws, r0, header, rows, pct=()):
    for j, h in enumerate(header, 1):
        c = ws.cell(r0, j, h); c.font = BOLD; c.fill = HEAD
    for i, row in enumerate(rows, r0 + 1):
        for j, v in enumerate(row, 1):
            if isinstance(v, float) and not np.isfinite(v):
                v = None
            c = ws.cell(i, j, v)
            if header[j - 1] in pct and isinstance(v, float):
                c.number_format = '0.0%'
    return r0 + len(rows) + 2


def autowidth(ws, maxw=48):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(maxw, max(8, w + 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True, help='out or out-split20 (relative to day3/)')
    ap.add_argument('--tab', required=True, help='tab name, at most 31 characters, e.g. "2026-11-25 split20 +25Nov"')
    ap.add_argument('--data', required=True, help='sessions included, e.g. "23nov 24s1 24s2 25nov"')
    ap.add_argument('--scheme', default='leave_one_session_out')
    ap.add_argument('--note', default='')
    ap.add_argument('--date', default=str(date.today()))
    a = ap.parse_args()
    if len(a.tab) > 31 or re.search(r'[\[\]:*?/\\]', a.tab):
        raise SystemExit(f'tab name {a.tab!r}: Excel allows at most 31 characters and none of []:*?/\\')
    run = HERE / a.run_dir
    S = pd.read_csv(run / 'fused_sample_predictions.csv')
    S = S[S['scheme'] == a.scheme].copy()
    S['in_top3'] = S['in_top3'].astype(str).str.lower().eq('true')
    F = json.loads((run / 'fused_knn.json').read_text())
    ov = F['schemes'][a.scheme]['overall']['fused (learned weights)']
    assert int((S['true'] == S['pred']).sum()) == ov['exact'] and len(S) == ov['n_recordings_scored'], 'sample CSV does not match fused_knn.json'
    variant = F.get('variant', 'default')
    phones = [p for p in ['ip16', 'ip18', 's24', 'a55', 'a56'] if p in set(S['phone'])] + sorted(set(S['phone']) - {'ip16', 'ip18', 's24', 'a55', 'a56'})

    per_phone = {p: metrics(S[S['phone'] == p]) for p in phones}
    allm = metrics(S)
    summ = {p: summary(S[S['phone'] == p], per_phone[p]) for p in phones}
    summ['all phones'] = summary(S, allm)
    folds = sorted(set(S['fold']))

    wb = load_workbook(XLSX) if XLSX.exists() else Workbook()
    if not XLSX.exists():
        wb.active.title = 'README'
    if a.tab in wb.sheetnames:
        raise SystemExit(f'tab {a.tab!r} already exists in {XLSX}: earlier runs are never overwritten, choose a new tab name')
    # README (definitions; rewritten so it stays current)
    if 'README' in wb.sheetnames:
        del wb['README']
    ws = wb.create_sheet('README', 0)
    for r in README:
        ws.append(r)
    ws['A1'].font = Font(bold=True, size=13)
    ws.column_dimensions['A'].width = 18; ws.column_dimensions['B'].width = 140
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top')

    # ---- run tab
    ws = wb.create_sheet(a.tab)
    info = [('run', a.tab), ('date', a.date), ('variant', variant), ('data (sessions)', a.data), ('scheme', a.scheme),
            ('model', 'fused kNN, learned weights per fold (fused_knn.py)'), ('source', f'phase2/new/day3/{a.run_dir}/fused_sample_predictions.csv'),
            ('samples', f"{len(S)} ({'20 s pieces' if variant != 'default' else 'takes'})"),
            ('overall', f"{ov['exact']}/{ov['n_recordings_scored']} = {ov['exact_acc']:.1%}, chance mean {F['schemes'][a.scheme]['chance_mean']:.1%}"),
            ('note', a.note)]
    for k, v in info:
        ws.append([k, v]); ws.cell(ws.max_row, 1).font = BOLD
    r = ws.max_row + 2
    ws.cell(r - 1, 1, 'Per phone (summary)').font = Font(bold=True, size=12)
    hdr = ['phone', 'n', 'correct', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc', 'places']
    r = write_rows(ws, r, hdr, [[p] + [summ[p][h] for h in hdr[1:]] for p in phones + ['all phones']],
                   pct={'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc'})
    ws.cell(r - 1, 1, 'Per held-out session x phone (correct / n)').font = Font(bold=True, size=12)
    fr = []
    for f in folds:
        t = S[S['fold'] == f]
        row = [f]
        for p in phones:
            q = t[t['phone'] == p]
            row.append(f"{int((q['true'] == q['pred']).sum())}/{len(q)}" if len(q) else '')
        row.append(f"{int((t['true'] == t['pred']).sum())}/{len(t)} = {(t['true'] == t['pred']).mean():.1%}")
        fr.append(row)
    r = write_rows(ws, r, ['held-out'] + phones + ['all'], fr)
    ws.cell(r - 1, 1, 'Recall per place x phone (correct / n); last column all phones').font = Font(bold=True, size=12)
    places = allm.sort_values(['floor', 'place'], ascending=[False, True])
    wide = []
    for _, pl in places.iterrows():
        row = [pl['place'], int(pl['floor'])]
        for p in phones:
            m = per_phone[p].set_index('place')
            row.append(f"{int(m.loc[pl['place'], 'correct'])}/{int(m.loc[pl['place'], 'n'])}" if pl['place'] in m.index else '')
        row.append(f"{int(pl['correct'])}/{int(pl['n'])} = {pl['recall']:.0%}")
        wide.append(row)
    r = write_rows(ws, r, ['place', 'floor'] + phones + ['all phones'], wide)
    ws.cell(r - 1, 1, 'Per phone x place (long table)').font = Font(bold=True, size=12)
    long_hdr = ['phone', 'place', 'floor', 'n', 'correct', 'recall', 'precision', 'f1', 'n_predicted_as', 'top3', 'top3_rate']
    long_rows = []
    for p in phones + ['all phones']:
        m = allm if p == 'all phones' else per_phone[p]
        for _, x in m.sort_values(['floor', 'place'], ascending=[False, True]).iterrows():
            long_rows.append([p] + [x[h] for h in long_hdr[1:]])
    write_rows(ws, r, long_hdr, long_rows, pct={'recall', 'precision', 'f1', 'top3_rate'})
    autowidth(ws)

    # ---- Ranking (latest run)
    if 'Ranking' in wb.sheetnames:
        del wb['Ranking']
    wr = wb.create_sheet('Ranking', 1)
    wr.append(['Ranking from run', a.tab]); wr['A1'].font = BOLD
    wr.append(['scheme', a.scheme]); wr.append([])
    ph_rank = sorted(phones, key=lambda p: (-summ[p]['accuracy'], -summ[p]['macro_precision']))
    rr = write_rows(wr, 4, ['rank', 'phone', 'n', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc'],
                    [[i + 1, p] + [summ[p][h] for h in ['n', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc']] for i, p in enumerate(ph_rank)],
                    pct={'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc'})
    pl_rank = allm.sort_values(['recall', 'f1', 'place'], ascending=[False, False, True]).reset_index(drop=True)
    write_rows(wr, rr, ['rank', 'place (all phones)', 'floor', 'n', 'correct', 'recall', 'precision', 'f1', 'top3_rate'],
               [[i + 1, x['place'], x['floor'], x['n'], x['correct'], x['recall'], x['precision'], x['f1'], x['top3_rate']] for i, x in pl_rank.iterrows()],
               pct={'recall', 'precision', 'f1', 'top3_rate'})
    autowidth(wr)

    # ---- Progress (append only)
    base_hdr = ['date', 'tab', 'variant', 'data included', 'scheme', 'samples', 'overall accuracy', 'macro precision', 'macro recall',
                'macro F1', 'top-3', 'chance (mean)']
    if 'Progress' in wb.sheetnames:
        wp = wb['Progress']
        hdr = [c.value for c in wp[1]]
    else:
        wp = wb.create_sheet('Progress', 2)
        hdr = list(base_hdr)
    for p in phones:
        if f'acc {p}' not in hdr:
            hdr.append(f'acc {p}')
    for j, h in enumerate(hdr, 1):
        c = wp.cell(1, j, h); c.font = BOLD; c.fill = HEAD
    al = summ['all phones']
    vals = {'date': a.date, 'tab': a.tab, 'variant': variant, 'data included': a.data, 'scheme': a.scheme, 'samples': al['n'],
            'overall accuracy': al['accuracy'], 'macro precision': al['macro_precision'], 'macro recall': al['macro_recall'],
            'macro F1': al['macro_f1'], 'top-3': al['top3_acc'], 'chance (mean)': F['schemes'][a.scheme]['chance_mean'],
            **{f'acc {p}': summ[p]['accuracy'] for p in phones}}
    nr = wp.max_row + 1
    for j, h in enumerate(hdr, 1):
        c = wp.cell(nr, j, vals.get(h))
        if isinstance(vals.get(h), float):
            c.number_format = '0.0%'
    autowidth(wp)
    order = ['README', 'Ranking', 'Progress'] + [s for s in wb.sheetnames if s not in ('README', 'Ranking', 'Progress')]
    wb._sheets = [wb[s] for s in order]
    XLSX.parent.mkdir(exist_ok=True)
    wb.save(XLSX)

    # ---- CSV copies
    CSV_DIR.mkdir(exist_ok=True)
    slug = re.sub(r'[^A-Za-z0-9]+', '_', a.tab).strip('_')
    pd.DataFrame(long_rows, columns=long_hdr).to_csv(CSV_DIR / f'{slug}_phone_place.csv', index=False)
    pd.DataFrame([[p] + [summ[p][h] for h in hdr_s] for p, hdr_s in [(p, ['n', 'correct', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc', 'places'])
                                                                       for p in phones + ['all phones']]],
                 columns=['phone', 'n', 'correct', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc', 'places']).to_csv(CSV_DIR / f'{slug}_phone_summary.csv', index=False)
    pd.DataFrame(fr, columns=['held-out'] + phones + ['all']).to_csv(CSV_DIR / f'{slug}_session_phone.csv', index=False)
    pd.DataFrame([[c.value for c in row] for row in wp.iter_rows(min_row=2)], columns=hdr).to_csv(CSV_DIR / 'progress.csv', index=False)
    pl_rank.to_csv(CSV_DIR / 'ranking_places_latest.csv', index=False)
    pd.DataFrame([[i + 1, p] + [summ[p][h] for h in ['n', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc']] for i, p in enumerate(ph_rank)],
                 columns=['rank', 'phone', 'n', 'accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'top3_acc']).to_csv(CSV_DIR / 'ranking_phones_latest.csv', index=False)
    print(f'appended tab {a.tab!r} to {XLSX}; samples {len(S)}; overall {al["accuracy"]:.3f}; phones', {p: round(summ[p]['accuracy'], 3) for p in phones})


if __name__ == '__main__':
    main()
