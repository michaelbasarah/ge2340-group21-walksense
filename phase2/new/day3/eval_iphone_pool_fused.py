#!/usr/bin/env python3
"""Day-3 fused kNN: does pooling iPhone 16 (ip16) training windows with iPhone 18 (ip18) beat ip18 only, TESTING ON ip18?

Same machinery as fused_knn.py (imported read-only: tune, outer_score; weights and k tuned by inner leave-one-session-out CV
on the training part only, scored once on the held-out ip18 windows). Held-out = each ip18 session (24s1, 25nov, 25night).
Training pools (windows of the other sessions): A ip18 only | B ip18 + all ip16 (23nov, 24s2, 25night_tian, 25spots, 26tian) |
C ip16 only | D all phones (control: must equal out/fused_sample_predictions.csv, scheme leave_one_session_out, phone ip18).
Writes out-iphone-pool/ only (out/ is not touched).   Run: python phase2/new/day3/eval_iphone_pool_fused.py
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data                    # noqa: E402
import gknn                    # noqa: E402
import fused_knn as fk         # noqa: E402

OUT = HERE / 'out-iphone-pool'
TEST_SESSIONS = ['24s1', '25nov', '25night']


def macro(rows):
    tp, nt, npred = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in rows:
        nt[r['true']] += 1; npred[r['pred']] += 1; tp[r['true']] += r['pred'] == r['true']
    cl = list(nt)
    return {'macro_recall': round(float(np.mean([tp[c] / nt[c] for c in cl])), 3),
            'macro_precision': round(float(np.mean([tp[c] / npred[c] if npred[c] else 0.0 for c in cl])), 3), 'n_classes': len(cl)}


def main():
    D = data.load()
    area = data.places()['area'].to_dict()
    bank = gknn.Bank(D, wifi_rows='near', wifi_scanner='s24')
    idx = np.arange(len(bank.W))
    ph = bank.W['phone'].to_numpy()
    sess = bank.sess
    print({p: int((ph == p).sum()) for p in sorted(set(ph))}, flush=True)
    rows = []
    for s in TEST_SESSIONS:
        te = idx[(sess == s) & (ph == 'ip18')]
        pools = {'A_ip18_only': (sess != s) & (ph == 'ip18'), 'B_ip18_plus_ip16': (sess != s) & np.isin(ph, ['ip18', 'ip16']),
                 'C_ip16_only': (sess != s) & (ph == 'ip16'), 'D_all_phones': (sess != s)}
        for pname, mask in pools.items():
            tr = idx[mask]
            tsess = sorted(set(sess[tr]))

            def inner(trn):
                ss = sorted(set(sess[trn]))
                return [(trn[sess[trn] != q], trn[sess[trn] == q], [x for x in ss if x != q], None) for q in ss]

            t0 = time.time()
            T = fk.tune(bank, inner(tr))
            truth = dict(zip(bank.rec[te], bank.y[te]))
            for vname, (w, k) in (('fused (learned weights)', T['chosen']), ('xyz only', T['corners']['xyz'])):
                pred, wpred, nnlab, ncls, top3 = fk.outer_score(bank, tr, te, tsess, None, w, k, area)
                for kk in sorted(pred):
                    first = te[bank.rec[te] == kk][0]
                    rows.append({'test_session': s, 'train_pool': pname, 'variant': vname, 'key': kk, 'floor': int(bank.W.loc[first, 'floor']),
                                 'true': truth[kk], 'pred': pred[kk], 'in_top3': truth[kk] in top3[kk], 'k': k,
                                 'weights': json.dumps(dict(zip(fk.GROUPS, w))), 'n_train_windows': len(tr), 'n_train_sessions': len(tsess)})
            print(s, pname, 'train windows', len(tr), 'weights', dict(zip(fk.GROUPS, T['chosen'][0])), 'k', T['chosen'][1],
                  f'{time.time() - t0:.0f}s', flush=True)
    df = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / 'iphone_pool_fused_predictions.csv', index=False)
    res = {'what': __doc__.strip().split('\n\n')[0], 'test': 'ip18 stops of 24s1, 25nov, 25night (85 recordings)', 'variants': {}}
    ref = pd.read_csv(HERE / 'out' / 'fused_sample_predictions.csv')
    ref = ref[(ref.scheme == 'leave_one_session_out') & (ref.phone == 'ip18')]
    res['control_out_fused_sample_predictions_ip18'] = {'top1': f'{int((ref.true == ref.pred).sum())}/{len(ref)}', 'top3': f'{int(ref.in_top3.sum())}/{len(ref)}'}
    for vname in df.variant.unique():
        res['variants'][vname] = {}
        for pname in df.train_pool.unique():
            d = df[(df.variant == vname) & (df.train_pool == pname)]
            n = len(d)
            res['variants'][vname][pname] = {
                'top1': f'{int((d.true == d.pred).sum())}/{n}', 'top1_acc': round(float((d.true == d.pred).mean()), 3),
                'top3': f'{int(d.in_top3.sum())}/{n}', **macro(d.to_dict('records')),
                'per_session_top1': {s: f"{int(((g.true == g.pred)).sum())}/{len(g)}" for s, g in d.groupby('test_session')},
                'weights_k': {s: [g.weights.iloc[0], int(g.k.iloc[0])] for s, g in d.groupby('test_session')}}
        a = df[(df.variant == vname) & (df.train_pool == 'A_ip18_only')].set_index(['test_session', 'key'])
        b = df[(df.variant == vname) & (df.train_pool == 'B_ip18_plus_ip16')].set_index(['test_session', 'key'])
        okb, oka = (b.true == b.pred), (a.true == a.pred).reindex(b.index)
        wl = defaultdict(lambda: [0, 0])
        for key in b.index:
            p = f"{b.loc[key, 'floor']}F {b.loc[key, 'true']}"
            wl[p][0] += bool(okb[key] and not oka[key]); wl[p][1] += bool(oka[key] and not okb[key])
        res['variants'][vname]['B_vs_A'] = {'wins_total': sum(v[0] for v in wl.values()), 'losses_total': sum(v[1] for v in wl.values()),
                                            'by_place': {k: {'wins': v[0], 'losses': v[1]} for k, v in sorted(wl.items()) if v[0] or v[1]}}
    (OUT / 'iphone_pool_fused.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({v: {p: (o['top1'], o['top3'], o['macro_precision'], o['macro_recall']) for p, o in d.items() if p != 'B_vs_A'}
                      for v, d in res['variants'].items()}, indent=1))
    print('control', res['control_out_fused_sample_predictions_ip18'])


if __name__ == '__main__':
    main()
