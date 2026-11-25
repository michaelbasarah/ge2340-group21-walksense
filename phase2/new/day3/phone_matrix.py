"""Phone x session matrix of the playground recipe (python reference for the live panel in knn_playground.html).

For every phone (handset) and every train -> test session pair, plus one leave-one-session-out column:
  mode 'same'  train on that phone's windows of the training session(s), test on that phone's windows of the test session
  mode 'all'   train on ALL phones' windows of the training session(s), test on that phone's windows of the test session
Prediction per 5 s window = the playground's kNN (gknn recipe: one standardised distance per feature group, divided by the
group's median pair distance, combined with the group weights, groups missing in either row drop out, k nearest, votes
weighted 1/(D+1e-6)). Scaling constants, medians, weights and k are those embedded in the page (all windows, true floor of the
test window as the barometer group), so this is the page's recipe in float64 with stable tie-breaking (lowest index first), not
the per-fold re-standardisation of evaluate.py / fused_knn.py. Recording result = majority vote of its window predictions
(ties -> lowest place index). Chance = 1 / number of distinct places in the training windows (mean over folds for leave-one-session-out).

compute() takes the page payload (dict), so playground.py (export) and playground_check.py (JS == python check) use the same data.
"""
from __future__ import annotations

import numpy as np


def columns(sessions):
    n = len(sessions)
    cols = [{'label': f'{sessions[a]}->{sessions[b]}', 'train': [a], 'test': b} for a in range(n) for b in range(n) if a != b]
    cols.append({'label': 'leave one session out', 'loso': True})
    return cols


def _distances(P, te, tr, w):
    c, sc, med = P['cols'], P['scale'], P['med']
    F = {f: np.array([np.nan if v is None else v for v in c[f]], float) for f in P['feats']}
    z = lambda f, idx: (F[f][idx] - sc[f][0]) / sc[f][1]
    floor = np.array(c['floor'])
    num = np.zeros((len(te), len(tr))); den = np.zeros((len(te), len(tr)))
    if w['B'] > 0:
        d = (z('B', te)[:, None] - z('B', tr)[None, :]) ** 2 / med['B']
        num += w['B'] * d; den += w['B']
    if w['xyz'] > 0:
        d = sum((z(f, te)[:, None] - z(f, tr)[None, :]) ** 2 for f in 'xyz') / 3 / med['xyz']
        num += w['xyz'] * d; den += w['xyz']
    if w['tilt'] > 0:
        a = (~np.isnan(F['Bv'][te]))[:, None] & (~np.isnan(F['Bv'][tr]))[None, :]
        d = (z('Bv', te)[:, None] - z('Bv', tr)[None, :]) ** 2 + (z('Bh', te)[:, None] - z('Bh', tr)[None, :]) ** 2
        d = np.where(a, d / 2 / med['tilt'], 0.0)
        num += w['tilt'] * d; den = den + w['tilt'] * a
    if w['baro'] > 0:
        num += w['baro'] * (floor[te][:, None] != floor[tr][None, :]); den += w['baro']
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(den > 0, num / den, np.inf)


def _predict(P, te, tr, w, k):
    D = _distances(P, te, tr, w)
    place = np.array(P['cols']['place'])
    ytr = place[tr]
    kk = min(k, len(tr))
    order = np.argsort(D, axis=1, kind='stable')[:, :kk]
    pred = np.full(len(te), -1)
    for r in range(len(te)):
        o = order[r][np.isfinite(D[r, order[r]])]
        if not len(o):
            continue
        wt = 1.0 / (D[r, o] + 1e-6)
        sh = np.zeros(len(P['places']))
        np.add.at(sh, ytr[o], wt)
        sh = sh / wt.sum()
        pred[r] = int(np.argmax(sh))
    return pred


def compute(P, w=None, k=None):
    w = w or P['model']['weights']
    k = k or P['model']['k']
    c = P['cols']
    sess, phone, place, rec = (np.array(c[x]) for x in ('sess', 'phone', 'place', 'rec'))
    nP = len(P['places'])
    cols = columns(P['sessions'])
    cells = []
    for mode in ('same', 'all'):
        for ph, pname in enumerate(P['phones']):
            for col in cols:
                folds = [(col['train'], col['test'])] if not col.get('loso') else \
                    [([s for s in range(len(P['sessions'])) if s != t], t) for t in range(len(P['sessions']))]
                wh = wn = rh = rn = 0
                chances, ntr, nte, trh = [], 0, 0, set()
                per = {}
                for trs, ts in folds:
                    te = np.where((sess == ts) & (phone == ph))[0]
                    trm = np.isin(sess, trs) & ((phone == ph) if mode == 'same' else True)
                    tr = np.where(trm)[0]
                    if not len(te) or not len(tr):
                        continue
                    pred = _predict(P, te, tr, w, k)
                    ok = pred >= 0
                    te, pred = te[ok], pred[ok]
                    if not len(te):
                        continue
                    ntr += len(tr); nte += len(te); trh |= {P['phones'][i] for i in set(phone[tr])}
                    chances.append(1 / len(set(place[tr])))
                    hit = pred == place[te]
                    wh += int(hit.sum()); wn += len(te)
                    for t, h in zip(place[te], hit):
                        s = per.setdefault(int(t), [0, 0, 0, 0]); s[0] += int(h); s[1] += 1
                    for r in sorted(set(rec[te])):
                        m = rec[te] == r
                        votes = np.bincount(pred[m], minlength=nP)
                        pr = int(np.argmax(votes)); t = int(place[te][m][0])
                        rh += int(pr == t); rn += 1
                        s = per.setdefault(t, [0, 0, 0, 0]); s[2] += int(pr == t); s[3] += 1
                cells.append({'mode': mode, 'phone': pname, 'col': col['label'], 'n_train_windows': ntr, 'n_test_windows': nte,
                              'win_hit': wh, 'win_n': wn, 'rec_hit': rh, 'rec_n': rn,
                              'chance': float(np.mean(chances)) if chances else None,
                              'train_handsets': sorted(trh), 'cross_handset': bool(trh and trh != {pname}),
                              'per_place': {P['places'][t]: s for t, s in sorted(per.items())}})
    return cells
