"""Where does the variance come from?  Nested sums of squares per feature (python reference for the panel in knn_playground.html).
INTERNAL TEAM TOOL, not report text.

Windows (5 s) sit in recordings, recordings in a cell (place, session, phone), cells in a place.  For one feature and a set of
windows the total sum of squares around the grand mean is split EXACTLY into five nested pieces (ANOVA-style sequential sums of
squares, window-weighted: every 5 s window counts once, so a long stop weighs more than a short one):

  between places       sum over windows (mean of its place        - grand mean)^2          the signal we want
  between sessions     sum over windows (mean of its place+session - mean of its place)^2     [order 'session_first']
  between phones       sum over windows (mean of place+session+phone - mean of place+session)^2   = same session, other handset
  between recordings   sum over windows (mean of its recording - mean of its place+session+phone)^2   = repeat visits of one cell
  within recording     sum over windows (value - mean of its recording)^2                      = window-to-window noise

Order 'phone_first' swaps the two middle levels (phones around the place mean, then sessions within a phone = same handset on
another day).  The two orders give the same total and the same places / recordings / within-recording pieces; they differ only in how the
phone-by-session part is shared between "phones" and "sessions" (the design is crossed and unbalanced: ip16 has 2 sessions, s24
2, ip18/a55/a56 1, 23 Nov has only ip16 stops).  A share = SS / total SS; sd of a piece = sqrt(SS / n) is its contribution to the variance
in the feature's own unit (the five sd^2 add up to the total sd^2).  These are plain sums of squares, not unbiased random-effects
variance components: a between-level SS also contains a little of the noise below it (noise / windows per group).

Pressure is a per-stop mean of that handset's barometer (iPhone slot or S24; A55/A56 have none), so it has no window-to-window
noise by construction (within-recording = 0) and 'xyz' pools the three magnetic axes (their SS add).  The page computes the same in JS
for its current filters; playground_check.py checks JS == this module.

Exports out/variance_by_place.csv/.json and out/variance_cells_by_place.csv.  Called by playground.py (needs the page payload).
"""
from __future__ import annotations

import csv
import json

import numpy as np
import pandas as pd

VFEATS = [('B', '|B| (uT)'), ('x', 'B_x (uT)'), ('y', 'B_y (uT)'), ('z', 'B_z (uT)'), ('xyz', 'x/y/z pooled (uT)'),
          ('Bv', 'B_vertical (uT)'), ('Bh', 'B_horizontal (uT)'), ('hpa', 'pressure (hPa)')]
PIECES = ['place', 'session', 'phone', 'rec', 'within']
ORDERS = ['session_first', 'phone_first']
CELL_FEATS = [('B', '|B|'), ('Bv', 'B_vertical')]


def frame(P):
    c = P['cols']
    df = pd.DataFrame({k: c[k] for k in ['place', 'sess', 'phone', 'rec', 'floor']})
    for f in ['B', 'x', 'y', 'z', 'Bv', 'Bh', 'hpa']:
        df[f] = np.array([np.nan if v is None else v for v in c[f]], float)
    return df


def decompose(df, feat, order='session_first'):
    """df: windows (place, sess, phone, rec + feature columns). Returns dict with n, mean, total, ss{5}, or None if no windows."""
    if feat == 'xyz':
        parts = [decompose(df, f, order) for f in 'xyz']
        if any(p is None for p in parts):
            return None
        return {'n': parts[0]['n'], 'mean': float('nan'), 'total': sum(p['total'] for p in parts),
                'ss': {k: sum(p['ss'][k] for p in parts) for k in PIECES}, 'n_places': parts[0]['n_places'], 'n_rec': parts[0]['n_rec']}
    d = df[np.isfinite(df[feat])]
    if not len(d):
        return None
    v = d[feat].to_numpy(float)
    g = v.mean()
    mean = lambda keys: d.groupby(keys)[feat].transform('mean').to_numpy()
    mP = mean(['place'])
    if order == 'session_first':
        m1 = mean(['place', 'sess']); m2 = mean(['place', 'sess', 'phone'])
        ss_sess, ss_ph = ((m1 - mP) ** 2).sum(), ((m2 - m1) ** 2).sum()
    else:
        m1 = mean(['place', 'phone']); m2 = mean(['place', 'phone', 'sess'])
        ss_ph, ss_sess = ((m1 - mP) ** 2).sum(), ((m2 - m1) ** 2).sum()
    assert d.groupby('rec')[['place', 'sess', 'phone']].nunique().max().max() == 1, 'a recording must sit in one cell'
    mR = mean(['rec'])
    ss = {'place': ((mP - g) ** 2).sum(), 'session': ss_sess, 'phone': ss_ph, 'rec': ((mR - m2) ** 2).sum(), 'within': ((v - mR) ** 2).sum()}
    return {'n': len(v), 'mean': float(g), 'total': float(((v - g) ** 2).sum()), 'ss': {k: float(x) for k, x in ss.items()},
            'n_places': int(d['place'].nunique()), 'n_rec': int(d['rec'].nunique())}


def cell_table(df, places):
    """Per place x phone x session: mean +- sd (ddof 1) of |B| and B_vertical, deviation from the place's overall (window-weighted) mean,
    and a flag on the cell(s) furthest from it (per feature)."""
    rows = []
    for p, dp in df.groupby('place'):
        cells = []
        for (ph, s), dc in dp.groupby(['phone', 'sess']):
            cells.append({'place': places[p], 'place_idx': int(p), 'phone_idx': int(ph), 'sess_idx': int(s), 'n': len(dc), 'n_rec': int(dc['rec'].nunique())})
            for f, _ in CELL_FEATS:
                x = dc[f].dropna()
                cells[-1][f'{f}_n'] = len(x)
                cells[-1][f'{f}_mean'] = float(x.mean()) if len(x) else None
                cells[-1][f'{f}_sd'] = float(x.std(ddof=1)) if len(x) > 1 else None
        for f, _ in CELL_FEATS:
            allv = dp[f].dropna()
            ov = float(allv.mean()) if len(allv) else None
            dev = [abs(c[f'{f}_mean'] - ov) if c[f'{f}_mean'] is not None else -1 for c in cells]
            mx = max(dev) if dev else -1
            for c, dv in zip(cells, dev):
                c[f'{f}_place_mean'] = ov
                c[f'{f}_dev'] = (c[f'{f}_mean'] - ov) if c[f'{f}_mean'] is not None else None
                c[f'{f}_furthest'] = bool(mx > 0 and dv >= mx - 1e-12)
        rows += cells
    return rows


def scopes(P):
    """(scope name, type, window mask) for 'all', each floor and each single place."""
    d = frame(P)
    out = [('all places', 'all', np.ones(len(d), bool))]
    for fl in sorted(set(P['place_floor']), reverse=True):
        out.append((f'all floor {fl}', 'floor', np.array([P['place_floor'][p] == fl for p in d['place']])))
    for i, name in enumerate(P['places']):
        out.append((name, 'place', (d['place'] == i).to_numpy()))
    return d, out


def export(P, out_dir):
    d, sc = scopes(P)
    rows, js = [], {}
    for name, typ, m in sc:
        for order in ORDERS:
            for f, lab in VFEATS:
                r = decompose(d[m], f, order)
                if r is None:
                    continue
                row = {'scope': name, 'scope_type': typ, 'order': order, 'feature': f, 'unit_label': lab, 'n_windows': r['n'],
                       'n_places': r['n_places'], 'n_recordings': r['n_rec'], 'mean': round(r['mean'], 4) if np.isfinite(r['mean']) else '',
                       'total_sd': round(float(np.sqrt(r['total'] / r['n'])), 5)}
                for k in PIECES:
                    row[f'ss_{k}'] = round(r['ss'][k], 4)
                for k in PIECES:
                    row[f'share_{k}'] = round(r['ss'][k] / r['total'], 5) if r['total'] > 0 else ''
                for k in PIECES:
                    row[f'sd_{k}'] = round(float(np.sqrt(r['ss'][k] / r['n'])), 5)
                rows.append(row)
                js.setdefault(name, {}).setdefault(order, {})[f] = {k: row[k] for k in row if k not in ('scope', 'scope_type', 'order', 'feature')}
    fl = list(rows[0].keys())
    with (out_dir / 'variance_by_place.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fl); w.writeheader(); w.writerows(rows)
    cells = cell_table(d, P['places'])
    for c in cells:
        c['phone'] = P['phones'][c.pop('phone_idx')]; c['session'] = P['sessions'][c.pop('sess_idx')]; c.pop('place_idx')
    cf = ['place', 'phone', 'session', 'n', 'n_rec'] + [f'{f}_{s}' for f, _ in CELL_FEATS for s in ('n', 'mean', 'sd', 'place_mean', 'dev', 'furthest')]
    with (out_dir / 'variance_cells_by_place.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cf, extrasaction='ignore'); w.writeheader()
        w.writerows([{k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()} for c in cells])
    (out_dir / 'variance_by_place.json').write_text(json.dumps({
        'what': 'Nested sums of squares per feature (see variance.py docstring). Live-demo recipe of knn_playground.html, not evaluation results. '
                'scope = all places / each floor / one place; order session_first = place > session > phone > recording > window, '
                'phone_first = place > phone > session > recording > window. share_* = SS / total SS, sd_* = sqrt(SS / n).',
        'pieces': {'place': 'between places', 'session': 'between sessions', 'phone': 'between phones', 'rec': 'between recordings of one place/session/phone',
                   'within': 'within recording (window to window)'},
        'phones': P['phone_info'], 'sessions': P['sessions'], 'variance': js, 'cells': cells}, indent=1))
    print(f'wrote variance_by_place.csv/.json ({len(rows)} rows) and variance_cells_by_place.csv ({len(cells)} cells)')
