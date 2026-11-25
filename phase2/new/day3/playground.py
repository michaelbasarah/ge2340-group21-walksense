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

import data

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
    phones = sorted(W['phone'].unique())
    recs = sorted(W['key'].unique())
    visits = sorted(W['visit'].unique())
    cols = {
        'place': [pidx[p] for p in W['place']],
        'sess': [sessions.index(s) for s in W['session']],
        'phone': [phones.index(s) for s in W['phone']],
        'rec': [recs.index(s) for s in W['key']],
        'visit': [visits.index(s) for s in W['visit']],
        'floor': [int(f) for f in W['floor']],
        'hpa': round_col(W['visit'].map(V['hpa_iphone']).to_numpy(float), 1),
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
        'n': n, 'places': plist, 'place_floor': places['floor'].astype(int).tolist(), 'colours': colours,
        'sessions': sessions, 'phones': phones, 'recs': recs, 'visits': visits, 'cols': cols,
        'feats': FEATS, 'labels': LABELS, 'scale': scale, 'med': med,
        'model': {'weights': wdef, 'wifi_weight_dropped': model['weights']['wifi'], 'k': model['k'],
                  'loso_inner_acc': model['loso_inner_acc']},
        'pca': {'names': names, 'scale': [fs[f] for f in names], 'center': center.tolist(),
                'comps': comps.tolist(), 'explained': expl.tolist(), 'min_weight': PCA_MIN_W},
    }
    html = TEMPLATE.read_text().replace('__DATA__', json.dumps(payload, separators=(',', ':')))
    (OUT / 'knn_playground.html').write_text(html)
    print(f'wrote knn_playground.html: {n} windows, {len(plist)} places, {len(recs)} recordings, '
          f'{len(html) / 1e6:.2f} MB, PCA explained {expl.round(3).tolist()}, medians {med}')


if __name__ == '__main__':
    main()
