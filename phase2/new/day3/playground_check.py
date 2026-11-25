#!/usr/bin/env python3
"""Check: the kNN that runs inside out/knn_playground.html (CORE block, run in Node) == sklearn KNeighborsClassifier
with the same standardisation, weights, k and 1/(D+1e-6) vote weights. INTERNAL check, prints the agreement.

Python side builds the distance matrix independently (scipy cdist per group, availability masks as gknn.combine) from
the embedded data and feeds it to KNeighborsClassifier(metric='precomputed', weights=callable).
Also checks the PCA projection of a window equals the embedded pc1/pc2 of that window.
Run:  python phase2/new/day3/playground_check.py   (needs node)
"""
import json, re, subprocess, tempfile, sys
from pathlib import Path
import numpy as np
from scipy.spatial.distance import cdist
from sklearn.neighbors import KNeighborsClassifier

HERE = Path(__file__).resolve().parent
HTML = HERE / 'out' / 'knn_playground.html'
P = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', HTML.read_text(), re.S).group(1))
c = P['cols']; n = P['n']; NP = len(P['places'])
F = {f: np.array([np.nan if v is None else v for v in c[f]], float) for f in P['feats']}
Z = {f: (F[f] - P['scale'][f][0]) / P['scale'][f][1] for f in F}
y = np.array(c['place']); floor = np.array(c['floor']); sess = np.array(c['sess']); phone = np.array(c['phone']); visit = np.array(c['visit'])
DEF = P['model']['weights']; rng = np.random.default_rng(7)


def ref_dist(qi, w, use_tilt, tr):
    """Distances from window qi to training windows tr (python reference)."""
    num = np.zeros(len(tr)); den = np.zeros(len(tr))
    def add(g, d, a):
        nonlocal num, den
        if w[g] > 0:
            num += w[g] * np.where(a, d, 0); den += w[g] * a
    ones = np.ones(len(tr), bool)
    add('B', cdist(Z['B'][[qi], None], Z['B'][tr, None], 'sqeuclidean')[0] / P['med']['B'], ones)
    xyz = np.stack([Z[f] for f in 'xyz'], 1)
    add('xyz', cdist(xyz[[qi]], xyz[tr], 'sqeuclidean')[0] / 3 / P['med']['xyz'], ones)
    tl = np.stack([Z['Bv'], Z['Bh']], 1)
    a = ~np.isnan(tl[tr]).any(1) & (use_tilt and not np.isnan(tl[qi]).any())   # query without tilt: group drops out
    add('tilt', np.nan_to_num(cdist(np.nan_to_num(tl[[qi]]), np.nan_to_num(tl[tr]), 'sqeuclidean')[0]) / 2 / P['med']['tilt'], a)
    add('baro', (floor[tr] != floor[qi]).astype(float), ones)
    return np.where(den > 0, num / np.maximum(den, 1e-300), np.inf)


def sk_predict(qi, w, k, use_tilt, mask):
    tr = np.where(mask)[0]
    D = ref_dist(qi, w, use_tilt, tr)
    clf = KNeighborsClassifier(n_neighbors=k, metric='precomputed', weights=lambda d: 1 / (d + 1e-6))
    clf.fit(np.zeros((len(tr), len(tr))), y[tr])          # train matrix unused at predict time
    proba = clf.predict_proba(D[None, :])[0]
    full = np.zeros(NP); full[clf.classes_] = proba
    nn = np.argsort(D, kind='stable')[:k]
    return int(clf.classes_[proba.argmax()]), full, tr[nn]


settings = {
    'default weights, k=25, all windows': (DEF, 25, lambda i: np.ones(n, bool)),
    'equal weights, k=5, all windows': ({'B': .25, 'xyz': .25, 'tilt': .25, 'baro': .25}, 5, lambda i: np.ones(n, bool)),
    'tilt weight 0.5, k=10, 24 Nov only (all have tilt)': ({'B': .1, 'xyz': .4, 'tilt': .5, 'baro': 0}, 10, lambda i: sess != 0),
    'default weights, k=25, own session held out': (DEF, 25, lambda i: sess != sess[i]),
    'xyz+baro only, k=1, own stop held out, iphone only': ({'B': 0, 'xyz': 1, 'tilt': 0, 'baro': .3}, 1, lambda i: (visit != visit[i]) & (phone == P['phones'].index('iphone'))),
    'default weights, k=50, floor 5 only': (DEF, 50, lambda i: floor == 5),
}
cases, meta = [], []
for name, (w, k, mk) in settings.items():
    for i in rng.choice(n, 60, replace=False):
        for tilt in (True, False):
            m = mk(i)
            if m.sum() < k: continue
            cases.append({'i': int(i), 'w': w, 'k': k, 'tilt': tilt, 'use': m.astype(int).tolist()}); meta.append((name, int(i), w, k, tilt, m))
tmp = Path(tempfile.mkdtemp())
(tmp / 'cases.json').write_text(json.dumps(cases))
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), str(tmp / 'cases.json'), str(tmp / 'out.json')], check=True)
out = json.loads((tmp / 'out.json').read_text())
stats = {}
pcdiff = 0
for (name, i, w, k, tilt, m), o in zip(meta, out):
    pred, share, nn = sk_predict(i, w, k, tilt, m)
    s = stats.setdefault(name, {'n': 0, 'pred_agree': 0, 'nn_set_agree': 0, 'max_share_diff': 0.0})
    s['n'] += 1; s['pred_agree'] += int(pred == o['pred'])
    s['nn_set_agree'] += int(set(nn) == set(o['order']))
    s['max_share_diff'] = max(s['max_share_diff'], float(np.abs(share - np.array(o['shares'])).max()))
    if tilt:
        pcdiff = max(pcdiff, abs(o['pc'][0] - c['pc1'][i]), abs(o['pc'][1] - c['pc2'][i]))
tot = sum(s['n'] for s in stats.values()); ag = sum(s['pred_agree'] for s in stats.values())
for name, s in stats.items():
    print(f"{name}: predicted place agrees {s['pred_agree']}/{s['n']}, same neighbour set {s['nn_set_agree']}/{s['n']}, max |share diff| {s['max_share_diff']:.2e}")
print(f'TOTAL predicted place agrees {ag}/{tot}; max |JS PCA projection - embedded pc| over checked windows = {pcdiff:.4f} (embedded values are rounded to 3 decimals)')
sys.exit(0 if ag == tot else 1)
