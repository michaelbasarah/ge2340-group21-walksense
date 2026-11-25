#!/usr/bin/env python3
"""Check: the kNN that runs inside out/knn_playground.html (CORE block, run in Node) == sklearn KNeighborsClassifier
with the same standardisation, weights, k and 1/(D+1e-6) vote weights. INTERNAL check, prints the agreement.

Python side builds the distance matrix independently (scipy cdist per group, availability masks as gknn.combine) from
the embedded data and feeds it to KNeighborsClassifier(metric='precomputed', weights=callable).
Also checks the PCA projection of a window equals the embedded pc1/pc2 of that window.
Run:  python phase2/new/day3/playground_check.py   (needs node; DAY3_VARIANT=split20 checks out-split20/ instead of out/)
"""
import json, os, re, subprocess, tempfile, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_matrix
import variance
import compare_phones
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.neighbors import KNeighborsClassifier

HERE = Path(__file__).resolve().parent
OUTDIR = HERE / (f"out-{os.environ['DAY3_VARIANT']}" if os.environ.get('DAY3_VARIANT', '').strip() else 'out')
HTML = OUTDIR / 'knn_playground.html'
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
exp = json.loads((OUTDIR / 'phone_session_matrix.json').read_text())['cells']
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

# ---- place filter: the page's training mask / drawn mask == independent numpy masks (place subsets, with and without "filter training too")
NPL = len(P['places']); place = y
mrng = np.random.default_rng(11)
mcases, mexp = [], []
for t in range(40):
    pon = mrng.random(NPL) < (0.2 if t % 2 else 0.6)
    if not pon.any(): pon[mrng.integers(NPL)] = True
    pht = bool(t % 3)
    son = [bool(v) for v in (mrng.random(len(P['sessions'])) < .8)] if t % 4 == 0 else [True] * len(P['sessions'])
    if not any(son): son[0] = True
    ffl = ['all', '5', '4'][t % 3]
    L = int(mrng.integers(n)) if t % 5 else -1
    hold = ['session', 'visit', 'rec', 'none'][t % 4]
    spec = {'sessOn': son, 'phoneOn': [True] * NPH, 'placeOn': [bool(v) for v in pon], 'placeTrain': pht, 'ffloor': ffl, 'loaded': L, 'holdout': hold, 'samePhone': False}
    base = np.array(son)[sess] & (np.ones(n, bool) if ffl == 'all' else floor == int(ffl))
    if L >= 0:
        base &= {'session': sess != sess[L], 'visit': visit != visit[L], 'rec': np.array(c['rec']) != c['rec'][L], 'none': np.ones(n, bool)}[hold]
    mcases.append(spec); mexp.append((base & (pon[place] if pht else True), base & pon[place]))
(tmp / 'mc.json').write_text(json.dumps(mcases))
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), str(tmp / 'mc.json'), str(tmp / 'mo.json'), 'masks'], check=True)
mo = json.loads((tmp / 'mo.json').read_text())
mbad = sum(int(not (np.array_equal(np.array(o['train'], bool), e[0]) and np.array_equal(np.array(o['draw'], bool), e[1]))) for o, e in zip(mo, mexp))
print(f'place filter: the page\'s training mask and drawn mask equal the numpy masks in {len(mo) - mbad}/{len(mo)} random cases (place subsets x filter-training on/off x floor x session x hold-out)')

# ---- variance decomposition: the page's JS == variance.py (pandas) == out/variance_by_place.json, at the default 'all' settings, 3 single places, a floor, and combined filters
exp_v = json.loads((OUTDIR / 'variance_by_place.json').read_text())
df = variance.frame(P)
cells_per_place = df.groupby('place').apply(lambda d: d.groupby(['phone', 'sess']).ngroups)
fl_of = np.array(P['place_floor'])
nrec = df.groupby('place')['rec'].nunique(); nwin = df.groupby('place').size()
sel = [int(nrec.idxmax()), int(nrec[fl_of == 4].idxmax()), int(nwin.idxmin())]      # most recordings, most recordings on floor 4, fewest windows
assert len(set(sel)) == 3, sel
SN, PN = len(P['sessions']), NPH
def spec(placeOn=None, phoneOn=None, sessOn=None, ffloor='all'):
    return {'sessOn': sessOn or [True] * SN, 'phoneOn': phoneOn or [True] * PN, 'placeOn': placeOn or [True] * NPL, 'placeTrain': True, 'ffloor': ffloor, 'loaded': -1, 'holdout': 'none', 'samePhone': False}
one = lambda i: [j == i for j in range(NPL)]
vcases = [('all places, all phones and sessions (default)', spec(), None)]
for i in sel:
    vcases.append((f"single place {P['places'][i]} (F{P['place_floor'][i]}, {int(nrec[i])} recordings, {int(nwin[i])} windows)", spec(placeOn=one(i)), P['places'][i]))
vcases.append(('all floor 5 (place dropdown)', spec(placeOn=[int(f) == 5 for f in P['place_floor']]), 'all floor 5'))
vcases.append(('three places x phones ip16+s24 x sessions 24s1+24s2', spec(placeOn=[j in sel for j in range(NPL)], phoneOn=[p in ('ip16', 's24') for p in P['phones']], sessOn=[s != '23nov' for s in P['sessions']]), None))
(tmp / 'vc.json').write_text(json.dumps([{'filter': f} for _, f, _ in vcases]))
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), str(tmp / 'vc.json'), str(tmp / 'vo.json'), 'variance'], check=True)
vo = json.loads((tmp / 'vo.json').read_text())
vbad = 0
def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))
for (name, f, scope), o in zip(vcases, vo):
    m = np.array(f['sessOn'])[sess] & np.array(f['phoneOn'])[phone] & np.array(f['placeOn'])[place]
    d = df[m]
    nfeat = bad_f = 0
    for order in variance.ORDERS:
        for feat, _ in variance.VFEATS:
            r = variance.decompose(d, feat, order); j = o['var'][order][feat]
            nfeat += 1
            if r is None:
                ok = j is None
            else:
                ok = (j is not None and j['n'] == r['n'] and close(j['total'], r['total']) and all(close(j['ss'][k], r['ss'][k]) for k in variance.PIECES)
                      and j['nPlaces'] == r['n_places'] and j['nRec'] == r['n_rec'] and close(sum(r['ss'].values()), r['total']) and close(sum(j['ss'].values()), j['total']))
                if ok and scope in exp_v['variance']:                       # also equal to what was written to out/variance_by_place.json (rounded to 4 decimals)
                    e = exp_v['variance'][scope][order][feat]
                    ok = e['n_windows'] == r['n'] and all(abs(e[f'ss_{k}'] - r['ss'][k]) < 1e-3 for k in variance.PIECES)
            bad_f += int(not ok)
            if not ok: print('VARIANCE MISMATCH', name, order, feat)
    # per-place cell table (mean, sd, deviation, furthest flag)
    ref = variance.cell_table(d, P['places'])
    cb = 0
    for rc in ref:
        jc = next((c for c in o['cells'][str(rc['place_idx'])]['cells'] if c['ph'] == rc['phone_idx'] and c['s'] == rc['sess_idx']), None)
        okc = jc is not None and jc['n'] == rc['n'] and jc['nRec'] == rc['n_rec']
        for ft, _ in variance.CELL_FEATS:
            jj = jc[ft] if jc else {}
            for key_py, key_js in (('mean', 'mean'), ('sd', 'sd'), ('dev', 'dev')):
                a, b = rc[f'{ft}_{key_py}'], jj.get(key_js)
                okc = okc and ((a is None) == (b is None)) and (a is None or close(a, b))
            okc = okc and rc[f'{ft}_furthest'] == jj.get('furthest')
        cb += int(not okc)
    ncells = len(ref)
    print(f"variance: {name}: {o['n']} windows, JS == python in {nfeat - bad_f}/{nfeat} feature x nesting results, per-place cell table in {ncells - cb}/{ncells} cells")
    vbad += bad_f + cb
print(f'variance decomposition: JS panel == variance.py (and out/variance_by_place.json) {"in all cases" if vbad == 0 else "FAILED in " + str(vbad)}; pieces add up to the total in every case')
# ---- compare-phones panel: the page's comparePhones() == compare_phones.py (numpy distances + sklearn metrics): default settings (all phones, sessions
# and places, leave one session out, both training modes) plus random place / session / phone subsets, weights, k and the leave-one-stop-out rule
NSE = len(P['sessions'])
crng = np.random.default_rng(23)
ccases = []
for mode in ('all', 'same'):
    ccases.append(('default', {'w': DEF, 'k': P['model']['k'], 'o': {'phones': list(range(NPH)), 'sessOn': [True] * NSE, 'placeOn': [True] * NPL, 'mode': mode, 'holdout': 'session'}}))
for t in range(10):
    pon = crng.random(NPL) < 0.5
    if pon.sum() < 3: pon[crng.choice(NPL, 3, replace=False)] = True
    son = crng.random(NSE) < 0.75
    if son.sum() < 2: son[:2] = True
    phs = [int(j) for j in range(NPH) if crng.random() < 0.7] or [0]
    w_ = DEF if t % 2 else {g: float(crng.choice([0, .1, .3, .7])) for g in DEF} | {'xyz': 0.5}
    ccases.append((f'random {t}', {'w': w_, 'k': int(crng.choice([1, 5, 25])), 'o': {'phones': phs, 'sessOn': [bool(v) for v in son], 'placeOn': [bool(v) for v in pon],
                                                                                'mode': ['all', 'same'][t % 2], 'holdout': ['session', 'visit'][(t // 2) % 2]}}))
ccases.append(('default, leave one stop out', {'w': DEF, 'k': P['model']['k'], 'o': {'phones': list(range(NPH)), 'sessOn': [True] * NSE, 'placeOn': [True] * NPL, 'mode': 'all', 'holdout': 'visit'}}))
(tmp / 'cp.json').write_text(json.dumps([c for _, c in ccases]))
subprocess.run(['node', str(HERE / 'playground_check.js'), str(HTML), str(tmp / 'cp.json'), str(tmp / 'cpo.json'), 'compare'], check=True)
cpo = json.loads((tmp / 'cpo.json').read_text())
cbad = ncmp = 0
KEYS = ['nRec', 'nWin', 'recHit', 'winHit', 'top3Hit']
for (name, c), jres in zip(ccases, cpo):
    o = c['o']
    pres = compare_phones.compute(P, w=c['w'], k=c['k'], phones=o['phones'], sess_on=o['sessOn'], place_on=o['placeOn'], mode=o['mode'], holdout=o['holdout'])
    assert len(pres) == len(jres)
    for pr, jr in zip(pres, jres):
        ncmp += 1
        ok = all(pr[k_] == jr[k_] for k_ in KEYS)
        for k_ in ('acc', 'winAcc', 'prec', 'recall', 'f1', 'top3'):
            a, b = pr[k_], jr[k_]
            ok = ok and ((a is None) == (b is None)) and (a is None or abs(a - b) < 1e-9)
        ok = ok and {int(t): v for t, v in pr['per'].items()} == {int(t): v for t, v in jr['per'].items()}
        cbad += int(not ok)
        if not ok: print('COMPARE MISMATCH', name, P['phones'][jr['phone']], {k_: (pr[k_], jr[k_]) for k_ in KEYS + ['acc', 'prec']})
dflt = compare_phones.compute(P, mode='all')
print(f'compare phones: the page\'s per-phone accuracy, window accuracy, macro precision / recall / F1, top-3 and per-place counts equal compare_phones.py (numpy + sklearn) in {ncmp - cbad}/{ncmp} phone results over {len(ccases)} settings (default, random subsets, leave one stop out)')
for r in dflt:
    print(f"  default (all phones train, leave one session out) {r['phone']}: rec {r['recHit']}/{r['nRec']} acc {r['acc']:.4f} prec {r['prec']:.4f}" if r['nRec'] else f"  {r['phone']}: no data")
sys.exit(0 if ag == tot and mask_bad == 0 and bad == 0 and mbad == 0 and vbad == 0 and cbad == 0 else 1)
