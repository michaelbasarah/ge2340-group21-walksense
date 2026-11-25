"""Compare phones side by side (python reference for the "Compare phones" panel of knn_playground.html).  INTERNAL, live demo, not evaluation results.

For each phone: test = its windows in the checked sessions and places; training = windows of the checked sessions and places
(mode 'same': that phone only, 'all': every phone) minus the held-out part of the test window: holdout 'session' = its whole session
(leave one session out), 'visit' = its whole stop (all phones). Same kNN recipe as phone_matrix.py (page scaling, weights, k, 1/(D+1e-6) votes).
A recording's prediction = majority vote of its window predictions (ties -> lowest place index). Metrics are the sklearn ones:
accuracy_score, precision_recall_fscore_support(labels = the places the phone has test recordings of, average='macro', zero_division=0);
top-3 = the true place is among the 3 places with the largest summed vote share over the recording's windows (share > 0).
chance = 1 / number of checked places.  compute() takes the page payload, so playground.py (export) and playground_check.py (JS == python) share it.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

import phone_matrix


def _shares(P, te, tr, w, k):
    """Normalised 1/(D+1e-6) vote shares over places for each test window (rows of zeros = no distance)."""
    D = phone_matrix._distances(P, te, tr, w)
    ytr = np.array(P['cols']['place'])[tr]
    order = np.argsort(D, axis=1, kind='stable')[:, :min(k, len(tr))]
    sh = np.zeros((len(te), len(P['places'])))
    for r in range(len(te)):
        o = order[r][np.isfinite(D[r, order[r]])]
        if not len(o):
            continue
        wt = 1.0 / (D[r, o] + 1e-6)
        tot = 0.0
        for x in wt:                         # sequential sum, like the page (np.sum is pairwise)
            tot += x
        for p, x in zip(ytr[o], wt):
            sh[r, p] += x
        sh[r] /= tot
    return sh


def compute(P, w=None, k=None, phones=None, sess_on=None, place_on=None, mode='all', holdout='session'):
    w = w or P['model']['weights']
    k = k or P['model']['k']
    c = P['cols']
    sess, phone, place, rec, visit = (np.array(c[x]) for x in ('sess', 'phone', 'place', 'rec', 'visit'))
    nP = len(P['places'])
    sess_on = np.array(sess_on if sess_on is not None else [True] * len(P['sessions']), bool)
    place_on = np.array(place_on if place_on is not None else [True] * nP, bool)
    phones = list(range(len(P['phones']))) if phones is None else phones
    out = []
    for ph in phones:
        ok = sess_on[sess] & place_on[place]
        pool = ok & ((phone == ph) if mode == 'same' else True)
        test = np.where(ok & (phone == ph))[0]
        key = visit if holdout == 'visit' else sess
        r_true, r_pred, r_acc = {}, {}, {}
        wh = wn = 0
        per = {}
        for kv in sorted(set(key[test])):
            te = test[key[test] == kv]
            tr = np.where(pool & (key != kv))[0]
            if not len(tr):
                continue
            sh = _shares(P, te, tr, w, k)
            has = sh.sum(1) > 0
            te, sh = te[has], sh[has]
            pred = sh.argmax(1)               # first max = lowest place index
            hit = pred == place[te]
            wh += int(hit.sum()); wn += len(te)
            for t, h in zip(place[te], hit):
                s = per.setdefault(int(t), [0, 0, 0, 0]); s[2] += int(h); s[3] += 1
            for i, p, s_ in zip(te, pred, sh):
                r = int(rec[i])
                r_true[r] = int(place[i])
                v = r_pred.setdefault(r, np.zeros(nP, int)); v[p] += 1
                r_acc[r] = r_acc.get(r, np.zeros(nP)) + s_
        recs = sorted(r_true)
        yt = np.array([r_true[r] for r in recs]); yp = np.array([int(np.argmax(r_pred[r])) for r in recs])
        t3 = 0
        for r in recs:
            a = r_acc[r]; top = np.lexsort((np.arange(nP), -a))[:3]
            t3 += int(r_true[r] in top and a[r_true[r]] > 0)
        for t, p_ in zip(yt, yp):
            s = per.setdefault(int(t), [0, 0, 0, 0]); s[0] += int(t == p_); s[1] += 1
        res = {'phone': P['phones'][ph], 'nRec': len(recs), 'nWin': wn, 'recHit': int((yt == yp).sum()) if recs else 0, 'winHit': wh, 'top3Hit': t3, 'per': per}
        if recs:
            labels = sorted(set(yt.tolist()))
            pr, rc, f1, _ = precision_recall_fscore_support(yt, yp, labels=labels, average='macro', zero_division=0)
            res.update(acc=float(accuracy_score(yt, yp)), winAcc=wh / wn, prec=float(pr), recall=float(rc), f1=float(f1), top3=t3 / len(recs))
        else:
            res.update(acc=None, winAcc=None, prec=None, recall=None, f1=None, top3=None)
        out.append(res)
    return out


def export_rows(P, res, place_on=None):
    n_checked = int(sum(place_on)) if place_on is not None else len(P['places'])
    return [{'phone': r['phone'], 'n_test_recordings': r['nRec'], 'n_test_windows': r['nWin'], 'rec_correct': r['recHit'],
             'rec_accuracy': r['acc'], 'win_correct': r['winHit'], 'win_accuracy': r['winAcc'], 'macro_precision': r['prec'],
             'macro_recall': r['recall'], 'macro_f1': r['f1'], 'top3_rate': r['top3'], 'chance': 1 / n_checked} for r in res]
