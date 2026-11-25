#!/usr/bin/env python3
"""Data gaps sheet: which place x phone data is missing, lacking or weak, and what to record next (internal team tool,
numbers only, no report text).

    python phase2/new/day3/gaps_sheet.py [--perf-tab "2026-11-25 gaps full25Nov"]
        writes out/data_gaps.xlsx (rewritten each run: it shows the latest outputs) and out/perf_csv/data_gaps_*.csv;
        with --perf-tab also APPENDS the coverage x performance table and the priority list as one new tab to
        out/phone_place_performance.xlsx (never overwrites: stops if the tab exists)

Inputs (written by the day-3 pipeline): out/fused_sample_predictions.csv and out-split20/fused_sample_predictions.csv
(learned-weight fused kNN, scheme leave_one_session_out), config.json (sessions, days, phones) and ../graph-v2/nodes.csv
(the 26 places and their floors).

FIXED RULES (written down on 25 Nov before the sheet was first generated; not tuned to what it shows):
  Coverage cell = place x phone, counted on the default variant's leave-one-session-out rows: every stop take of every
  session is a test sample there exactly once, so those rows are the takes.
    MISSING  0 takes
    LACKING  fewer than 2 sessions or fewer than 3 takes
    OK       otherwise
  Performance cell = place x phone, held-out accuracy (= recall: correct / n) and precision (of the samples of that
  phone predicted as the place, the share that really were it), leave one session out, per variant.
    WEAK     accuracy < 30 % or fewer than 3 test samples   (red)
    FAIR     30 % <= accuracy < 60 % and at least 3 samples  (amber)
    GOOD     accuracy >= 60 % and at least 3 samples         (green)
    no data  no test sample                                  (grey)
  Priority (to-collect list):
    place x phone rows: listed when coverage is MISSING or LACKING, or the default performance is WEAK.
      severity MISSING 3; WEAK with >= 3 takes 2; LACKING (incl. WEAK only because n < 3) 1.
    place rows: listed when the place (all phones, default) has accuracy < 30 %, or any phone cell is MISSING/LACKING.
      severity 3 if the place accuracy (all phones, default) < 30 %, else 2 if any phone is MISSING, else 1.
    order: severity (high first), then the place accuracy (all phones, default) ascending, then fewer takes.
    what to record: MISSING / LACKING -> max(3 - takes, 1) more takes with that phone at the place, at least one of them
    in a new session if the cell has < 2 sessions; WEAK -> 2 more takes at the place and 2 at the place it is most often
    confused with (top confusion pair of that cell, default variant), same phone.
    Protocol for every take: 60 s stop, phone flat in the hand facing the landmark, the same way every time
    (phase2/new/DAY3-CHECKLIST.md).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out' / 'data_gaps.xlsx'
CSV_DIR = HERE / 'out' / 'perf_csv'
SCHEME = 'leave_one_session_out'
MIN_SESSIONS, MIN_TAKES = 2, 3
WEAK_ACC, GOOD_ACC, MIN_N = 0.30, 0.60, 3
RED, AMBER, GREEN, GREY = 'F4C7C3', 'FCE8B2', 'B7E1CD', 'E0E0E0'
BOLD = Font(bold=True)
HEAD = PatternFill('solid', fgColor='DDE6F0')
fill = lambda c: PatternFill('solid', fgColor=c)
PROTOCOL = '60 s stop, phone flat in the hand facing the landmark, the same way every time'


def load(variant_dir):
    S = pd.read_csv(HERE / variant_dir / 'fused_sample_predictions.csv')
    S = S[S['scheme'] == SCHEME].copy()
    S['ok'] = S['true'] == S['pred']
    return S


def coverage_status(takes, sessions):
    if takes == 0:
        return 'MISSING'
    return 'LACKING' if sessions < MIN_SESSIONS or takes < MIN_TAKES else 'OK'


def perf_status(n, acc):
    if n == 0:
        return 'no data'
    if n < MIN_N or acc < WEAK_ACC:
        return 'WEAK'
    return 'GOOD' if acc >= GOOD_ACC else 'FAIR'


def cell_perf(S, place, phone=None):
    t = S[(S['true'] == place) & ((S['phone'] == phone) if phone else True)]
    pr = S[(S['pred'] == place) & ((S['phone'] == phone) if phone else True)]
    n, c = len(t), int(t['ok'].sum())
    acc = c / n if n else np.nan
    prec = float((pr['true'] == place).mean()) if len(pr) else np.nan
    wrong = t.loc[~t['ok'], 'pred'].value_counts()
    top = (wrong.index[0], int(wrong.iloc[0])) if len(wrong) else ('', 0)
    return {'n': n, 'correct': c, 'acc': acc, 'prec': prec, 'confused_with': top[0], 'confused_n': top[1]}


def append_perf_tab(tab, C, P, R):
    from openpyxl import load_workbook
    xl = HERE / 'out' / 'phone_place_performance.xlsx'
    if len(tab) > 31:
        raise SystemExit('tab name longer than 31 characters')
    wb = load_workbook(xl)
    if tab in wb.sheetnames:
        raise SystemExit(f'tab {tab!r} already exists in {xl}: earlier tabs are never overwritten')
    ws = wb.create_sheet(tab)
    ws.append(['Data gaps run (gaps_sheet.py); rules in data_gaps.xlsx README']); ws['A1'].font = BOLD
    ws.append([])
    pv = P[P['variant'] == 'default'].set_index(['place', 'phone'])
    hdr = ['place', 'floor', 'phone', 'takes', 'sessions', 'days', 'coverage', 'n (default)', 'accuracy (default)', 'precision (default)', 'performance (default)']
    ws.append(hdr)
    for c in ws[ws.max_row]:
        c.font = BOLD; c.fill = HEAD
    for _, x in C.iterrows():
        p = pv.loc[(x['place'], x['phone'])]
        ws.append([x['place'], int(x['floor']), x['phone'], int(x['takes']), int(x['sessions']), int(x['days']), x['status'], int(p['n']),
                   None if not np.isfinite(p['acc']) else float(p['acc']), None if not np.isfinite(p['prec']) else float(p['prec']), p['status']])
    ws.append([]); ws.append(['Priority (top 30)']); ws.cell(ws.max_row, 1).font = BOLD
    cols = ['rank', 'severity', 'level', 'place', 'phone', 'why', 'what to record']
    ws.append(cols)
    for c in ws[ws.max_row]:
        c.font = BOLD; c.fill = HEAD
    for _, x in R.head(30).iterrows():
        ws.append([int(x[c]) if isinstance(x[c], (np.integer,)) else x[c] for c in cols])
    autowidth(ws, 80)
    wb.save(xl)
    print('appended tab', tab, 'to', xl)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--perf-tab', default='')
    args = ap.parse_args()
    cfg = json.loads((HERE / 'config.json').read_text())
    day_of = {s['id']: s['day'] for s in cfg['sessions']}
    sessions = [s['id'] for s in cfg['sessions']]
    phones = [v['id'] for k, v in cfg['phones'].items() if not k.startswith('_')]
    nodes = pd.read_csv((HERE / cfg['places_graph']).resolve())
    nodes = nodes[nodes['virtual'] == 0].sort_values(['floor', 'node_id'], ascending=[False, True])
    places = list(nodes['node_id'])
    floor = dict(zip(nodes['node_id'], nodes['floor']))
    runs = {'default': load('out'), 'split20': load('out-split20')}
    D = runs['default']

    # ---------------- coverage
    cov_rows = []
    for pl in places:
        for ph in phones:
            t = D[(D['true'] == pl) & (D['phone'] == ph)]
            per_s = {s: int((t['session'] == s).sum()) for s in sessions}
            ns = sum(1 for v in per_s.values() if v)
            nd = len({day_of[s] for s, v in per_s.items() if v})
            cov_rows.append({'place': pl, 'floor': floor[pl], 'phone': ph, **{f'takes {s}': per_s[s] for s in sessions},
                             'takes': len(t), 'sessions': ns, 'days': nd, 'status': coverage_status(len(t), ns)})
    C = pd.DataFrame(cov_rows)

    # ---------------- performance
    perf_rows = []
    for var, S in runs.items():
        for pl in places:
            for ph in phones + ['all phones']:
                p = cell_perf(S, pl, None if ph == 'all phones' else ph)
                perf_rows.append({'variant': var, 'place': pl, 'floor': floor[pl], 'phone': ph, **p,
                                  'status': perf_status(p['n'], p['acc'])})
    P = pd.DataFrame(perf_rows)
    pd_ = P[P['variant'] == 'default'].set_index(['place', 'phone'])
    place_acc = {pl: pd_.loc[(pl, 'all phones'), 'acc'] for pl in places}

    # ---------------- priority
    pri = []
    Ci = C.set_index(['place', 'phone'])
    for pl in places:
        for ph in phones:
            c = Ci.loc[(pl, ph)]
            pf = pd_.loc[(pl, ph)]
            weak_data = pf['status'] == 'WEAK' and c['takes'] >= MIN_TAKES
            if c['status'] == 'OK' and not weak_data:
                continue
            sev = 3 if c['status'] == 'MISSING' else 2 if weak_data else 1
            why, todo = [], []
            if c['status'] in ('MISSING', 'LACKING'):
                why.append(f"{c['status'].lower()}: {int(c['takes'])} takes in {int(c['sessions'])} session(s)")
                more = max(MIN_TAKES - int(c['takes']), 1)
                todo.append(f"{more} more {ph} take{'s' if more > 1 else ''} at {pl}" + (', at least one in a new session' if c['sessions'] < MIN_SESSIONS else ''))
            if pf['status'] == 'WEAK' and pf['n'] > 0:
                why.append(f"weak: {int(pf['correct'])}/{int(pf['n'])} held out" + (f", confused with {pf['confused_with']} ({int(pf['confused_n'])}x)" if pf['confused_with'] else ''))
                if weak_data:
                    todo.append(f"2 more {ph} takes at {pl}" + (f" and 2 at {pf['confused_with']}" if pf['confused_with'] else ''))
            pri.append({'severity': sev, 'level': 'place x phone', 'place': pl, 'floor': floor[pl], 'phone': ph,
                        'takes': int(c['takes']), 'sessions': int(c['sessions']), 'coverage': c['status'],
                        'accuracy (default)': pf['acc'], 'n (default)': int(pf['n']), 'performance': pf['status'],
                        'place accuracy (all phones)': place_acc[pl], 'why': '; '.join(why), 'what to record': '; '.join(todo) + f' ({PROTOCOL})'})
    for pl in places:
        a = pd_.loc[(pl, 'all phones')]
        cells = C[C['place'] == pl]
        miss = list(cells.loc[cells['status'] == 'MISSING', 'phone'])
        lack = list(cells.loc[cells['status'] == 'LACKING', 'phone'])
        weak = a['n'] > 0 and a['acc'] < WEAK_ACC
        if not (weak or miss or lack):
            continue
        sev = 3 if weak else 2 if miss else 1
        why, todo = [], []
        if weak:
            why.append(f"weak: {int(a['correct'])}/{int(a['n'])} held out (all phones)" + (f", most often called {a['confused_with']} ({int(a['confused_n'])}x)" if a['confused_with'] else ''))
            todo.append(f"2 more takes at {pl} with each phone that has it" + (f", and 2 at {a['confused_with']} with the same phones" if a['confused_with'] else ''))
        if miss:
            why.append('missing for ' + ', '.join(miss))
            todo.append(f"3 takes at {pl} with " + ', '.join(miss))
        if lack:
            why.append('lacking for ' + ', '.join(lack))
        pri.append({'severity': sev, 'level': 'place', 'place': pl, 'floor': floor[pl], 'phone': 'all phones',
                    'takes': int(cells['takes'].sum()), 'sessions': int(D.loc[D['true'] == pl, 'session'].nunique()), 'coverage': '',
                    'accuracy (default)': a['acc'], 'n (default)': int(a['n']), 'performance': a['status'],
                    'place accuracy (all phones)': place_acc[pl], 'why': '; '.join(why), 'what to record': '; '.join(todo) + f' ({PROTOCOL})'})
    R = pd.DataFrame(pri)
    R['_acc'] = R['place accuracy (all phones)'].fillna(-1)
    R = R.sort_values(['severity', '_acc', 'takes', 'level', 'place', 'phone'], ascending=[False, True, True, False, True, True]).drop(columns='_acc')
    R.insert(0, 'rank', range(1, len(R) + 1))

    # ---------------- summary
    summ_ph, summ_pl = [], []
    for var, S in runs.items():
        for ph in phones:
            t = S[S['phone'] == ph]
            pls = sorted(set(t['true']))
            precs = [cell_perf(t, pl)['prec'] for pl in pls]
            summ_ph.append({'variant': var, 'phone': ph, 'test samples': len(t), 'correct': int(t['ok'].sum()),
                            'accuracy': t['ok'].mean() if len(t) else np.nan,
                            'macro precision': float(np.mean([0 if not np.isfinite(x) else x for x in precs])) if pls else np.nan,
                            'places with data': len(pls), 'sessions': int(t['session'].nunique()),
                            'takes (default)': int((D['phone'] == ph).sum())})
        for pl in places:
            p = cell_perf(S, pl)
            summ_pl.append({'variant': var, 'place': pl, 'floor': floor[pl], 'test samples': p['n'], 'correct': p['correct'],
                            'accuracy': p['acc'], 'precision': p['prec'], 'most often called': p['confused_with'],
                            'phones with data': int(S.loc[S['true'] == pl, 'phone'].nunique()),
                            'takes (default)': int((D['true'] == pl).sum())})
    SP, SL = pd.DataFrame(summ_ph), pd.DataFrame(summ_pl)

    # ---------------- workbook
    wb = Workbook()
    ws = wb.active; ws.title = 'README'
    readme = [
        ['WalkSense data gaps (internal team sheet, numbers only)'], [],
        ['Generated by', 'phase2/new/day3/gaps_sheet.py from out/ and out-split20/ fused_sample_predictions.csv (latest run, all sessions in config.json: ' + ', '.join(sessions) + ')'],
        ['Evaluation', 'Learned-weight fused kNN (fused_knn.py), leave one session out: each session is held out in turn, the model is trained on all the other sessions (all phones). '
                       'Sample = one stop take (default) or one 20 s piece of a take (split20).'],
        ['Coverage tab', f'stop takes per place x phone per session (default variant rows = every take once). MISSING = 0 takes; LACKING = fewer than {MIN_SESSIONS} sessions or fewer than {MIN_TAKES} takes; OK otherwise.'],
        ['Performance tab', f'held-out accuracy (correct / n) and precision per place x phone. WEAK (red) = accuracy < {WEAK_ACC:.0%} or fewer than {MIN_N} test samples; '
                            f'FAIR (amber) = {WEAK_ACC:.0%} to < {GOOD_ACC:.0%}; GOOD (green) = >= {GOOD_ACC:.0%}; grey = no test sample.'],
        ['Priority tab', 'ranked to-collect list. Severity: place x phone MISSING 3, WEAK with >= 3 takes 2, LACKING 1; place rows: accuracy < 30 % (all phones) 3, '
                         'a phone MISSING 2, else 1. Then lower place accuracy first, then fewer takes. "Confused with" = the top wrong prediction for that cell (default variant).'],
        ['Protocol', PROTOCOL + ' (phase2/new/DAY3-CHECKLIST.md).'],
        ['Rules fixed', 'The thresholds above were written into gaps_sheet.py on 25 Nov before the first sheet was generated; they are not tuned to the result.'],
        ['Caveat', 'Phones differ in how many sessions they have; a phone with one session (a55) has its takes tested only by models trained on other phones.'],
    ]
    for r in readme:
        ws.append(r)
    ws['A1'].font = Font(bold=True, size=13)
    ws.column_dimensions['A'].width = 18; ws.column_dimensions['B'].width = 150
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top')

    def legend(ws, r, items):
        ws.cell(r, 1, 'Legend').font = BOLD
        for j, (txt, col) in enumerate(items):
            c = ws.cell(r + 1 + j, 1, txt); c.fill = fill(col)
        return r + 2 + len(items)

    # Coverage grid
    wc = wb.create_sheet('Coverage')
    r = legend(wc, 1, [('MISSING: no take', RED), (f'LACKING: < {MIN_SESSIONS} sessions or < {MIN_TAKES} takes', AMBER), ('OK', GREEN)])
    wc.cell(r, 1, 'Takes per place x phone (cell = total takes, sessions / days; status colour)').font = Font(bold=True, size=12)
    r += 1
    hdr = ['floor', 'place'] + phones + ['all phones']
    for j, h in enumerate(hdr, 1):
        c = wc.cell(r, j, h); c.font = BOLD; c.fill = HEAD
    col = {'MISSING': RED, 'LACKING': AMBER, 'OK': GREEN}
    for fl in (5, 4):
        for pl in [p for p in places if floor[p] == fl]:
            r += 1
            wc.cell(r, 1, fl); wc.cell(r, 2, pl)
            for j, ph in enumerate(phones, 3):
                x = Ci.loc[(pl, ph)]
                c = wc.cell(r, j, f"{int(x['takes'])} takes, {int(x['sessions'])} s / {int(x['days'])} d ({x['status']})")
                c.fill = fill(col[x['status']])
            tot = C[C['place'] == pl]
            wc.cell(r, len(hdr), f"{int(tot['takes'].sum())} takes")
    r += 3
    wc.cell(r - 1, 1, 'Takes per session (long table)').font = Font(bold=True, size=12)
    lh = list(C.columns)
    for j, h in enumerate(lh, 1):
        c = wc.cell(r, j, h); c.font = BOLD; c.fill = HEAD
    for _, x in C.iterrows():
        r += 1
        for j, h in enumerate(lh, 1):
            c = wc.cell(r, j, x[h] if not isinstance(x[h], np.integer) else int(x[h]))
            if h == 'status':
                c.fill = fill(col[x[h]])
    autowidth(wc)

    # Performance grid
    wp = wb.create_sheet('Performance')
    pcol = {'WEAK': RED, 'FAIR': AMBER, 'GOOD': GREEN, 'no data': GREY}
    r = legend(wp, 1, [(f'WEAK: accuracy < {WEAK_ACC:.0%} or n < {MIN_N}', RED), (f'FAIR: {WEAK_ACC:.0%} to < {GOOD_ACC:.0%}', AMBER),
                       (f'GOOD: >= {GOOD_ACC:.0%}', GREEN), ('no test sample', GREY)])
    for var in runs:
        wp.cell(r, 1, f'{var}: leave one session out, cell = accuracy (correct/n), precision').font = Font(bold=True, size=12)
        r += 1
        for j, h in enumerate(hdr, 1):
            c = wp.cell(r, j, h); c.font = BOLD; c.fill = HEAD
        pv = P[P['variant'] == var].set_index(['place', 'phone'])
        for fl in (5, 4):
            for pl in [p for p in places if floor[p] == fl]:
                r += 1
                wp.cell(r, 1, fl); wp.cell(r, 2, pl)
                for j, ph in enumerate(phones + ['all phones'], 3):
                    x = pv.loc[(pl, ph)]
                    txt = '' if x['n'] == 0 else (f"{x['acc']:.0%} ({int(x['correct'])}/{int(x['n'])}), P " +
                                                 ('-' if not np.isfinite(x['prec']) else f"{x['prec']:.0%}"))
                    c = wp.cell(r, j, txt); c.fill = fill(pcol[x['status']])
        r += 3
    autowidth(wp)

    # Priority
    wr = wb.create_sheet('Priority')
    ph_ = list(R.columns)
    for j, h in enumerate(ph_, 1):
        c = wr.cell(1, j, h); c.font = BOLD; c.fill = HEAD
    scol = {3: RED, 2: AMBER, 1: 'FFF4CC'}
    for i, (_, x) in enumerate(R.iterrows(), 2):
        for j, h in enumerate(ph_, 1):
            v = x[h]
            v = None if isinstance(v, float) and not np.isfinite(v) else (int(v) if isinstance(v, np.integer) else v)
            c = wr.cell(i, j, v)
            if h in ('accuracy (default)', 'place accuracy (all phones)') and isinstance(v, float):
                c.number_format = '0%'
        wr.cell(i, 2).fill = fill(scol[int(x['severity'])])
    autowidth(wr, 90)

    # Summary
    wsum = wb.create_sheet('Summary')
    r = 1
    for title, T, pct in [('Per phone', SP, ('accuracy', 'macro precision')), ('Per place', SL, ('accuracy', 'precision'))]:
        wsum.cell(r, 1, title).font = Font(bold=True, size=12); r += 1
        for j, h in enumerate(T.columns, 1):
            c = wsum.cell(r, j, h); c.font = BOLD; c.fill = HEAD
        for _, x in T.iterrows():
            r += 1
            for j, h in enumerate(T.columns, 1):
                v = x[h]
                v = None if isinstance(v, float) and not np.isfinite(v) else (int(v) if isinstance(v, np.integer) else v)
                c = wsum.cell(r, j, v)
                if h in pct and isinstance(v, float):
                    c.number_format = '0.0%'
        r += 3
    autowidth(wsum)
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    CSV_DIR.mkdir(exist_ok=True)
    C.to_csv(CSV_DIR / 'data_gaps_coverage.csv', index=False)
    P.round(4).to_csv(CSV_DIR / 'data_gaps_performance.csv', index=False)
    R.round(4).to_csv(CSV_DIR / 'data_gaps_priority.csv', index=False)
    SP.round(4).to_csv(CSV_DIR / 'data_gaps_summary_phone.csv', index=False)
    SL.round(4).to_csv(CSV_DIR / 'data_gaps_summary_place.csv', index=False)
    print('wrote', OUT)
    if args.perf_tab:
        append_perf_tab(args.perf_tab, C, P, R)
    print('coverage', C['status'].value_counts().to_dict())
    print('performance default', P[(P['variant'] == 'default') & (P['phone'] != 'all phones')]['status'].value_counts().to_dict())
    print(R.head(10)[['rank', 'severity', 'level', 'place', 'phone', 'why', 'what to record']].to_string())


def autowidth(ws, maxw=48):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(maxw, max(8, w + 2))


if __name__ == '__main__':
    main()
