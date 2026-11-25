#!/usr/bin/env python3
"""Interactive kNN playground (one self-contained HTML file).  INTERNAL TEAM TOOL, not report text.

Slide the features (|B|, magnetic x/y/z, tilt Bv/Bh, floor) to place a query point; the page finds its k nearest
stop windows live in the full standardised, group-weighted feature space (same recipe as gknn.py: standardise,
divide each group's mean squared difference by its median pair distance, combine with weights, votes weighted
1/D) and shows the predicted place. Wi-Fi is left out (a 100+-dim vector cannot be slid); |B| group = mean |B| only.

Writes out/knn_playground.html from playground_template.html (data embedded as JSON; Plotly from jsDelivr).
Run after data.py / fused_knn.py:  python phase2/new/day3/playground.py
"""
from __future__ import annotations

import colorsys
import json

import numpy as np

import csv

import data
import compare_phones
import phone_matrix
import variance

OUT = data.OUT
TEMPLATE = data.HERE / 'playground_template.html'
FEATS = ['B', 'x', 'y', 'z', 'Bv', 'Bh']
COLS = {'B': 'B_mean', 'x': 'x_mean', 'y': 'y_mean', 'z': 'z_mean', 'Bv': 'Bv', 'Bh': 'Bh'}
LABELS = {'B': '|B| mean (uT)', 'x': 'B_x mean (uT)', 'y': 'B_y mean (uT)', 'z': 'B_z mean (uT)',
          'Bv': 'B_vertical (uT)', 'Bh': 'B_horizontal (uT)'}
GROUP_OF = {'B': ['B'], 'xyz': ['x', 'y', 'z'], 'tilt': ['Bv', 'Bh']}
PCA_MIN_W = 0.05          # a group with default weight 0 still gets this weight in the (display-only) PCA


def round_col(a, nd):
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a]


def export_matrix(P, cells):
    flds = ['mode', 'phone', 'phone_model', 'train_session', 'test_session', 'n_train_windows', 'n_test_windows', 'win_hit', 'win_n', 'win_acc',
            'rec_hit', 'rec_n', 'rec_acc', 'chance', 'cross_handset', 'train_handsets']
    rows = []
    for c in cells:
        tr, _, te = c['col'].partition('->')
        if c['col'].startswith('leave'):
            tr, te = 'other two sessions', 'each session in turn'
        rows.append({'mode': c['mode'], 'phone': c['phone'], 'phone_model': P['phone_info'][c['phone']]['model'], 'train_session': tr,
                     'test_session': te, 'n_train_windows': c['n_train_windows'], 'n_test_windows': c['n_test_windows'],
                     'win_hit': c['win_hit'], 'win_n': c['win_n'], 'win_acc': round(c['win_hit'] / c['win_n'], 3) if c['win_n'] else '',
                     'rec_hit': c['rec_hit'], 'rec_n': c['rec_n'], 'rec_acc': round(c['rec_hit'] / c['rec_n'], 3) if c['rec_n'] else '',
                     'chance': round(c['chance'], 3) if c['chance'] else '', 'cross_handset': c['cross_handset'],
                     'train_handsets': ' '.join(c['train_handsets'])})
    with (OUT / 'phone_session_matrix.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=flds); w.writeheader(); w.writerows(rows)
    (OUT / 'phone_session_matrix.json').write_text(json.dumps({
        'what': 'Live-demo recipe of knn_playground.html (not evaluation results): phone x train->test session, window and recording accuracy. '
                'Computed by phone_matrix.py at the default weights and k.',
        'weights': P['model']['weights'], 'k': P['model']['k'], 'phones': P['phone_info'], 'cells': cells}, indent=1))
    print(f'wrote phone_session_matrix.csv/.json ({len(rows)} cells)')


def export_compare(P):
    """Python reference of the page's 'Compare phones' panel at the default settings (all phones, sessions and places, k and weights of fused_model.json)."""
    rows, js = [], {}
    for mode in ('all', 'same'):
        res = compare_phones.compute(P, mode=mode, holdout='session')
        js[mode] = res
        for r in compare_phones.export_rows(P, res):
            rows.append({'mode': {'all': 'train on all phones, test on this phone', 'same': 'train and test on the same phone only'}[mode], 'holdout': 'leave one session out', **r})
    flds = list(rows[0])
    with (OUT / 'phone_compare_default.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=flds); w.writeheader(); w.writerows({k: (round(v, 4) if isinstance(v, float) else ('' if v is None else v)) for k, v in r.items()} for r in rows)
    (OUT / 'phone_compare_default.json').write_text(json.dumps({
        'what': 'Live-demo recipe of the Compare phones panel in knn_playground.html (not evaluation results): per phone, all sessions and places, leave one session out, '
                'recording majority vote; macro metrics over the places the phone has test recordings of (sklearn, zero_division=0). Computed by compare_phones.py at the default weights and k.',
        'weights': P['model']['weights'], 'k': P['model']['k'], 'results': js}, indent=1, default=float))
    print(f'wrote phone_compare_default.csv/.json ({len(rows)} rows)')


def main():
    D = data.load()
    W = D['W'].reset_index(drop=True)
    V = D['V'].set_index('visit')
    model = json.loads((OUT / 'fused_model.json').read_text())
    # the playground uses the same 5 s windows as fused_knn.py
    places = (W.groupby('place')['floor'].agg(lambda s: int(s.mode().iloc[0])).reset_index()
              .sort_values(['floor', 'place'], ascending=[False, True]))
    plist = places['place'].tolist()
    pidx = {p: i for i, p in enumerate(plist)}
    sessions = sorted(W['session'].unique())
    cfg_phones = [v for k, v in data.config()['phones'].items() if not k.startswith('_')]
    present = set(W['phone'])
    phones = [v['id'] for v in cfg_phones if v['id'] in present]            # config order: ip16, ip18, s24, a55, a56
    models = W.groupby('phone')['device'].first().to_dict()
    phone_info = {v['id']: {'display': v['display'], 'model': models[v['id']]} for v in cfg_phones if v['id'] in present}
    recs = sorted(W['key'].unique())
    visits = sorted(W['visit'].unique())
    cols = {
        'place': [pidx[p] for p in W['place']],
        'sess': [sessions.index(s) for s in W['session']],
        'phone': [phones.index(s) for s in W['phone']],
        'rec': [recs.index(s) for s in W['key']],
        'visit': [visits.index(s) for s in W['visit']],
        'floor': [int(f) for f in W['floor']],
        # pressure of the window's OWN handset (per-stop mean: iPhone slot -> hpa_iphone, S24 -> hpa_s24, A55/A56 have none)
        'hpa': round_col(np.where(W['slot'] == 'iphone', W['visit'].map(V['hpa_iphone']), np.where(W['slot'] == 's24', W['visit'].map(V['hpa_s24']), np.nan)).astype(float), 2),
    }
    for f in FEATS:
        cols[f] = round_col(W[COLS[f]].to_numpy(float), 3)
    X = {f: np.array([np.nan if v is None else v for v in cols[f]], float) for f in FEATS}
    n = len(W)

    # ---- scaling constants (computed on the embedded, rounded values; all windows)
    scale = {}
    for f in FEATS:
        ok = np.isfinite(X[f])
        scale[f] = [float(X[f][ok].mean()), float(X[f][ok].std() + 1e-9)]
    Z = {f: (X[f] - scale[f][0]) / scale[f][1] for f in FEATS}

    def median_pair(feats):
        """Median over all window pairs (i<j, both with the group) of the mean squared standardised difference."""
        ok = ~np.isnan(np.stack([Z[f] for f in feats], 1)).any(1)
        A = np.stack([Z[f][ok] for f in feats], 1)
        vals = []
        for i in range(len(A) - 1):
            vals.append(((A[i + 1:] - A[i]) ** 2).mean(1).astype(np.float32))
        return float(np.median(np.concatenate(vals)))
    med = {g: median_pair(fs) for g, fs in GROUP_OF.items()}

    # ---- PCA (display only): standardised, weighted features; fixed at the default weights
    wdef = {g: model['weights'][g] for g in ['B', 'xyz', 'tilt', 'baro']}
    wp = {g: max(w, PCA_MIN_W) for g, w in wdef.items()}
    fs = {}
    for g, fl in GROUP_OF.items():
        for f in fl:
            fs[f] = float(np.sqrt(wp[g] / (len(fl) * med[g])))
    fs['floor'] = float(np.sqrt(wp['baro']))
    names = FEATS + ['floor']
    M = np.stack([np.nan_to_num(Z[f]) * fs[f] for f in FEATS] + [(np.array(cols['floor']) == 5).astype(float) * fs['floor']], 1)
    center = M.mean(0)
    U, S, Vt = np.linalg.svd(M - center, full_matrices=False)
    comps = Vt[:2]
    for i in range(2):                 # sign convention: largest-|loading| positive
        if comps[i][np.abs(comps[i]).argmax()] < 0:
            comps[i] = -comps[i]
    proj = (M - center) @ comps.T
    expl = (S ** 2 / (S ** 2).sum())[:2]
    cols['pc1'] = round_col(proj[:, 0], 3)
    cols['pc2'] = round_col(proj[:, 1], 3)

    colours = []
    for i in range(len(plist)):
        h = (i * 0.381966) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, 0.5 if i % 2 == 0 else 0.62, 0.72)
        colours.append('#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255)))

    payload = {
        'n': n, 'places': plist, 'place_labels': {k: v for k, v in data.config().get('place_display', {}).items() if not k.startswith('_')}, 'place_floor': places['floor'].astype(int).tolist(), 'colours': colours,
        'sessions': sessions, 'phones': phones, 'phone_info': phone_info, 'recs': recs, 'visits': visits, 'cols': cols,
        'feats': FEATS, 'labels': LABELS, 'vfeats': variance.VFEATS, 'scale': scale, 'med': med,
        'model': {'weights': wdef, 'wifi_weight_dropped': model['weights']['wifi'], 'k': model['k'],
                  'loso_inner_acc': model['loso_inner_acc']},
        'pca': {'names': names, 'scale': [fs[f] for f in names], 'center': center.tolist(),
                'comps': comps.tolist(), 'explained': expl.tolist(), 'min_weight': PCA_MIN_W},
    }
    # python reference of the live "phone x session" panel (same recipe, default weights and k)
    cells = phone_matrix.compute(payload)
    export_matrix(payload, cells)
    export_compare(payload)
    variance.export(payload, OUT)          # nested variance decomposition (python reference of the page's variance panel)
    html = TEMPLATE.read_text().replace('__DATA__', json.dumps(payload, separators=(',', ':')))
    (OUT / 'knn_playground.html').write_text(html)
    print(f'wrote knn_playground.html: {n} windows, {len(plist)} places, {len(recs)} recordings, '
          f'{len(html) / 1e6:.2f} MB, PCA explained {expl.round(3).tolist()}, medians {med}')


if __name__ == '__main__':
    main()
