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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_matrix
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
    'xyz+baro only, k=1, own stop held out, ip16 only': ({'B': 0, 'xyz': 1, 'tilt': 0, 'baro': .3}, 1, lambda i: (visit != visit[i]) & (phone == P['phones'].index('ip16'))),
    'xyz+baro only, k=1, own stop held out, ip18 only': ({'B': 0, 'xyz': 1, 'tilt': 0, 'baro': .3}, 1, lambda i: (visit != visit[i]) & (phone == P['phones'].index('ip18'))),
    'default weights, k=50, floor 5 only': (DEF, 50, lambda i: floor == 5),
}

NPH = len(P['phones'])
def filt(i, only_phone=None, same_phone=False, holdout='session', only_sess=None):
    """Filter spec for the page's buildMask (JS) and the independent numpy mask for the same rule."""
    on = [only_phone is None or j == only_phone for j in range(NPH)]
    so = [True] * len(P['sessions']) if only_sess is None else [j in (only_sess if isinstance(only_sess, list) else [only_sess]) for j in range(len(P['sessions']))]
    f = {'sessOn': so, 'phoneOn': on, 'ffloor': 'all', 'loaded': int(i), 'holdout': holdout, 'samePhone': same_phone}
    m = np.array(on)[phone] & np.array(so)[sess]
    if same_phone: m = m & (phone == phone[i])
    if holdout == 'session': m = m & (sess != sess[i])
    elif holdout == 'visit': m = m & (visit != visit[i])
    return f, m


# (name, weights, k, mask function, filter-spec function or None).  Phone-filter cases go through the page's buildMask in JS.
FILT = {
    'single-phone filter s24 (checkbox/dropdown), own session held out': (lambda i: filt(i, only_phone=P['phones'].index('s24')), lambda i: phone[i] == P['phones'].index('s24')),
    'single-phone filter ip16, whole stop held out': (lambda i: filt(i, only_phone=P['phones'].index('ip16'), holdout='visit'), lambda i: phone[i] == P['phones'].index('ip16')),
    'single-phone filter ip18, whole stop held out': (lambda i: filt(i, only_phone=P['phones'].index('ip18'), holdout='visit'), lambda i: phone[i] == P['phones'].index('ip18')),
    'single-session filter (top Session dropdown) 24s2, no hold-out': (lambda i: filt(i, only_sess=P['sessions'].index('24s2'), holdout='none'), lambda i: True),
    'two-session filter 23nov+24s1, own session held out': (lambda i: filt(i, only_sess=[P['sessions'].index('23nov'), P['sessions'].index('24s1')]), lambda i: sess[i] != P['sessions'].index('24s2')),
    'single-phone filter a55 only, no hold-out': (lambda i: filt(i, only_phone=P['phones'].index('a55'), holdout='none'), lambda i: phone[i] == P['phones'].index('a55')),
    'train on same phone only (query phone), own session held out': (lambda i: filt(i, same_phone=True), lambda i: True),
    'train on same phone only, query = ip16 (23nov or 24s2)': (lambda i: filt(i, same_phone=True), lambda i: phone[i] == P['phones'].index('ip16')),
}
cases, meta = [], []
for name, (w, k, mk) in settings.items():
    for i in rng.choice(n, 60, replace=False):
        for tilt in (True, False):
            m = mk(i)
            if m.sum() < k: continue
            cases.append({'i': int(i), 'w': w, 'k': k, 'tilt': tilt, 'use': m.astype(int).tolist()}); meta.append((name, int(i), w, k, tilt, m))
for name, (spec, qok) in FILT.items():
    done = 0
    for i in rng.permutation(n):
        if done >= 30: break
        if not qok(i): continue
        f, m = spec(int(i))
        if m.sum() < 25: continue
        for tilt in (True, False):
            cases.append({'i': int(i), 'w': DEF, 'k': 25, 'tilt': tilt, 'filter': f}); meta.append((name, int(i), DEF, 25, tilt, m))
        done += 1
tmp = Path(tempfile.mkdtemp())
(tmp / 'cases.json').write_text(json.dumps(cases))
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), str(tmp / 'cases.json'), str(tmp / 'out.json')], check=True)
out = json.loads((tmp / 'out.json').read_text())
stats = {}
pcdiff = 0
mask_bad = 0
for (name, i, w, k, tilt, m), o in zip(meta, out):
    mask_bad += int(not np.array_equal(np.array(o['use'], bool), m))   # the page's mask == the independent numpy mask
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
print(f'training masks built by the page differ from the numpy masks in {mask_bad} of {tot} cases')

# ---- the live "phone x session" panel: JS numbers == python reference (phone_matrix.py == out/phone_session_matrix.json) at the default weights and k
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), '-', str(tmp / 'mx.json'), 'matrix'], check=True)
js = json.loads((tmp / 'mx.json').read_text())
py = phone_matrix.compute(P)
exp = json.loads((HERE / 'out' / 'phone_session_matrix.json').read_text())['cells']
bad, nna, ncell = 0, 0, 0
assert len(js) == len(py) == len(exp), (len(js), len(py), len(exp))
for j, p_, e in zip(js, py, exp):
    assert (j['mode'], j['phone'], j['col']) == (p_['mode'], p_['phone'], p_['col']) == (e['mode'], e['phone'], e['col'])
    ncell += 1
    if j['cell'] is None:
        nna += 1
        ok = p_['win_n'] == 0 and e['win_n'] == 0
    else:
        c_ = j['cell']
        per = {k: v for k, v in c_['per'].items()}
        ok = (c_['win'] == [p_['win_hit'], p_['win_n']] and c_['rec'] == [p_['rec_hit'], p_['rec_n']] and abs(c_['chance'] - p_['chance']) < 1e-12
              and c_['ntr'] == p_['n_train_windows'] and c_['nte'] == p_['n_test_windows'] and c_['cross'] == p_['cross_handset']
              and sorted(c_['trainPhones']) == p_['train_handsets'] and per == p_['per_place'])
    ok = ok and (p_['win_hit'], p_['win_n'], p_['rec_hit'], p_['rec_n'], p_['per_place']) == (e['win_hit'], e['win_n'], e['rec_hit'], e['rec_n'], e['per_place'])
    bad += int(not ok)
    if not ok: print('MATRIX MISMATCH', j['mode'], j['phone'], j['col'])
print(f'phone x session matrix: JS panel == python reference == out/phone_session_matrix.json in {ncell - bad}/{ncell} cells ({nna} greyed-out cells with no data)')
sys.exit(0 if ag == tot and mask_bad == 0 and bad == 0 else 1)
