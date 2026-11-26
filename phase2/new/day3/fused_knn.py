#!/usr/bin/env python3
"""Weighted fused kNN on ALL stop data (every session in config.json, every phone).

One kNN over window samples; each sensor group has its own distance and weight (gknn.py):
  w_B (|B|), w_xyz (magnetic x/y/z), w_tilt (B_vertical/B_horizontal), w_wifi (Wi-Fi RSSI vector), w_baro (barometer floor).
Weights (on the simplex, step 0.1, coarse-to-fine) and k are chosen by INNER cross-validation on the
training part only, then scored once on the held-out part (nested CV).

Three ways of splitting, reported side by side on purpose:
  random     LEAKY, for illustration only: windows split at random (KFold, shuffled). Windows of one
             60 s recording are near-duplicates, so the test windows have twins in training.
  by_recording  partly leaky: whole recordings held out, but the other phones of the SAME stop can be in
             training (4 phones recorded each 24-Nov session-1 stop at the same time).
  grouped    honest: GroupKFold over physical stops (all phones of one stop held out together).
  loso       most honest: leave one session out (23 Nov / 24 s1 / 24 s2); inner CV is leave-one-session-out
             over the remaining sessions.
Then the deployable model: weights and k tuned by leave-one-session-out on all sessions.

With DAY3_VARIANT=split20 (data.py) a "recording" is a 20 s piece of a take; by_recording then groups by the parent
take (column `take`), so the pieces of one take are never on both sides; grouped and loso already group by stop/session.

Run:  python phase2/new/day3/fused_knn.py      (about 5-10 min) writes out/fused_knn.json, out/fused_model.json,
      out/fused_window_predictions.csv, out/fused_sample_predictions.csv (per sample: prediction and top-3)
"""
from __future__ import annotations

import itertools
import json
import time

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold

import data
import gknn

GROUPS = ['B', 'xyz', 'tilt', 'wifi', 'baro']
KS = [1, 3, 5, 9, 15, 25]
SEED = 21


def simplex(step):
    n = int(round(1 / step))
    return [tuple(round(c * step, 4) for c in comb) for comb in itertools.product(range(n + 1), repeat=len(GROUPS))
            if sum(comb) == n]


COARSE = simplex(0.25)
FINE = simplex(0.1)
CORNERS = [tuple(1.0 if i == j else 0.0 for i in range(len(GROUPS))) for j in range(len(GROUPS))]
EQUAL = tuple([0.2] * len(GROUPS))


def eval_grid(bank, folds, grid, area=None):
    """folds: list of (train_idx, val_idx, train_sessions, train_visits). Returns {(w, k): [rec_correct, rec_n, win_correct, win_n]}."""
    tot = {}
    for tr, va, tsess, tvis in folds:
        thr = bank.floor_threshold(tsess, tvis)
        dd = bank.dists(tr, va, GROUPS, thr)
        ytr = bank.y[tr]
        classes = sorted(set(ytr))
        yva = bank.y[va]
        keys = bank.rec[va]
        truth = dict(zip(keys, yva))
        for w in grid:
            D = bank.combine(dd, dict(zip(GROUPS, w)))
            if D is None:
                continue
            S, _ = gknn.knn_scores(D, ytr, classes, KS)
            for k, Sk in S.items():
                pred = gknn.aggregate(Sk, keys, classes)
                rc = sum(pred[r] == truth[r] for r in pred)
                wc = int((np.array(classes, dtype=object)[Sk.argmax(1)] == yva).sum())
                t = tot.setdefault((w, k), [0, 0, 0, 0])
                t[0] += rc; t[1] += len(pred); t[2] += wc; t[3] += len(va)
    return tot


def best(tot, among=None):
    """Highest sample accuracy, then window accuracy, then k nearest 5. Explicit final tie-break (PROCESS-LOG 91), so the
    choice never depends on dict order: the smaller k, then the lexicographically smallest weight vector."""
    items = [(wk, v) for wk, v in tot.items() if among is None or wk[0] in among]
    return max(items, key=lambda it: (it[1][0] / it[1][1], it[1][2] / it[1][3], -abs(it[0][1] - 5), -it[0][1],
                                      tuple(-x for x in it[0][0])))[0]


def tune(bank, folds):
    """Coarse grid (step 0.25) then the 0.1 grid around the best coarse point; plus corners and equal weights."""
    tot = eval_grid(bank, folds, sorted(set(COARSE) | set(CORNERS) | {EQUAL}))
    w0, _ = best(tot)
    near = [w for w in FINE if max(abs(a - b) for a, b in zip(w, w0)) <= 0.25 + 1e-9 and w not in {x for x, _ in tot}]
    tot.update(eval_grid(bank, folds, near))
    chosen = best(tot)
    return {'chosen': chosen, 'corners': {g: best(tot, [c]) for g, c in zip(GROUPS, CORNERS)}, 'equal': best(tot, [EQUAL]),
            'n_weight_vectors_tried': len({w for w, _ in tot}), 'inner_acc_chosen': round(tot[chosen][0] / tot[chosen][1], 3)}


def outer_score(bank, tr, te, tsess, tvis, w, k, area):
    thr = bank.floor_threshold(tsess, tvis)
    dd = bank.dists(tr, te, GROUPS, thr)
    ytr = bank.y[tr]
    classes = sorted(set(ytr))
    D = bank.combine(dd, dict(zip(GROUPS, w)))
    S, nn = gknn.knn_scores(D, ytr, classes, [k])
    keys = bank.rec[te]
    pred = gknn.aggregate(S[k], keys, classes)
    wpred = np.array(classes, dtype=object)[S[k].argmax(1)]
    # top-3 per sample (window scores summed per recording/piece, as gknn.aggregate; first = the prediction)
    agg = pd.DataFrame(S[k], columns=classes).assign(key=keys).groupby('key').sum()
    order = np.argsort(-agg.to_numpy(), axis=1, kind='stable')[:, :3]
    top3 = {kk: [classes[j] for j in o] for kk, o in zip(agg.index, order)}
    for kk in top3:
        assert top3[kk][0] == pred[kk] or agg.loc[kk, top3[kk][0]] == agg.loc[kk, pred[kk]]
        if top3[kk][0] != pred[kk]:            # tie: keep the prediction first
            top3[kk] = [pred[kk]] + [c for c in top3[kk] if c != pred[kk]][:2]
    return pred, wpred, ytr[nn], len(classes), top3


def run_scheme(bank, name, outer, inner_fn, area):
    """outer: list of (train_idx, test_idx, train_sessions, train_visits, label)."""
    res = {'folds': []}
    agg = {}
    win_rows, sample_rows = [], []
    for tr, te, tsess, tvis, lab in outer:
        t0 = time.time()
        T = tune(bank, inner_fn(tr))
        fold = {'fold': lab, 'n_train_windows': len(tr), 'n_test_windows': len(te),
                'n_train_places': int(len(set(bank.y[tr]))), 'chance': round(1 / len(set(bank.y[tr])), 3),
                'chosen_weights': dict(zip(GROUPS, T['chosen'][0])), 'chosen_k': T['chosen'][1],
                'inner_acc_chosen': T['inner_acc_chosen'], 'n_weight_vectors_tried': T['n_weight_vectors_tried']}
        variants = {'fused (learned weights)': T['chosen'], 'equal weights': T['equal'],
                    **{f'{g} only': T['corners'][g] for g in GROUPS}}
        for vname, (w, k) in variants.items():
            pred, wpred, nnlab, ncls, top3 = outer_score(bank, tr, te, tsess, tvis, w, k, area)
            truth = dict(zip(bank.rec[te], bank.y[te]))
            a = agg.setdefault(vname, [0, 0, 0, 0, 0])
            a[0] += sum(pred[r] == truth[r] for r in pred); a[1] += len(pred)
            a[2] += sum(area.get(pred[r]) == area.get(truth[r]) for r in pred)
            a[3] += int((wpred == bank.y[te]).sum()); a[4] += len(te)
            fold[vname] = {'k': k, 'weights': dict(zip(GROUPS, w)), **gknn.score_records(pred, truth, area),
                           'window_acc': round(float(np.mean(wpred == bank.y[te])), 3)}
            if vname == 'fused (learned weights)':
                win_rows += [{'scheme': name, 'fold': lab, 'key': kk, 'session': s, 'phone': p, 'true': t, 'pred_window': pw,
                              'nearest_neighbour_place': nl}
                             for kk, s, p, t, pw, nl in zip(bank.rec[te], bank.sess[te], bank.W.loc[te, 'phone'], bank.y[te], wpred, nnlab)]
                first = pd.Series(te).groupby(bank.rec[te]).first()
                nwin = pd.Series(bank.rec[te]).value_counts()
                sample_rows += [{'scheme': name, 'fold': lab, 'key': kk, 'session': bank.sess[first[kk]], 'phone': bank.W.loc[first[kk], 'phone'],
                                 'place_floor': int(bank.W.loc[first[kk], 'floor']), 'true': truth[kk], 'pred': pred[kk],
                                 'top3': '|'.join(top3[kk]), 'in_top3': truth[kk] in top3[kk], 'n_windows': int(nwin[kk]),
                                 'n_train_places': ncls} for kk in sorted(pred)]
        fold['seconds'] = round(time.time() - t0, 1)
        print(name, lab, fold['chosen_weights'], 'k', fold['chosen_k'], 'exact', fold['fused (learned weights)']['exact'],
              '/', fold['fused (learned weights)']['n_recordings'], f"({fold['seconds']} s)", flush=True)
        res['folds'].append(fold)
    res['overall'] = {v: {'exact': a[0], 'n_recordings_scored': a[1], 'exact_acc': round(a[0] / a[1], 3),
                          'exact_ci95': gknn.wilson(a[0], a[1]), 'area': a[2], 'area_acc': round(a[2] / a[1], 3),
                          'window_acc': round(a[3] / a[4], 3), 'n_test_windows': a[4]} for v, a in agg.items()}
    res['chance_mean'] = round(float(np.mean([f['chance'] for f in res['folds']])), 3)
    return res, (win_rows, sample_rows)


def main():
    D = data.load()
    area = data.places()['area'].to_dict()
    bank = gknn.Bank(D, wifi_rows='near', wifi_scanner='s24')
    n = len(bank.W)
    idx = np.arange(n)
    sessions = sorted(set(bank.sess))
    allsess = sessions

    def visits_of(ix):
        return set(bank.vis[ix])

    # inner-fold builders (on the training part only)
    def inner_random(tr):
        kf = KFold(3, shuffle=True, random_state=SEED)
        return [(tr[a], tr[b], allsess, None) for a, b in kf.split(tr)]

    def inner_group(groups_arr):
        def f(tr):
            gk = GroupKFold(3)
            return [(tr[a], tr[b], allsess, visits_of(tr[a])) for a, b in gk.split(tr, groups=groups_arr[tr])]
        return f

    def inner_loso(tr):
        ss = sorted(set(bank.sess[tr]))
        return [(tr[bank.sess[tr] != s], tr[bank.sess[tr] == s], [x for x in ss if x != s], None) for s in ss]

    out = {'what': 'Weighted fused kNN on all stop windows, nested CV. Computed by fused_knn.py.',
           'groups': GROUPS, 'k_grid': KS, 'weight_grid': 'simplex step 0.25, then step 0.1 within 0.25 of the best; plus each group alone and equal weights',
           'samples': {'windows': n, 'recordings': int(len(set(bank.rec))), 'stop_visits': int(len(set(bank.vis))),
                       'places': int(len(set(bank.y))), 'window_s': D['config']['window_s'],
                       'per_session_phone': {f'{s}/{p}': int(c) for (s, p), c in bank.W.groupby(['session', 'phone']).size().items()}},
           'wifi': 'nearest stop within 120 s, s24 scanner only; Wi-Fi and baro are per physical stop (shared by all its windows)',
           'schemes': {}}
    if data.VARIANT:
        out['variant'] = data.VARIANT
        out['samples']['takes'] = int(bank.W['take'].nunique())
    wins, samples = [], []
    rec_groups = bank.W['take'].to_numpy() if 'take' in bank.W else bank.rec     # split20: group pieces by their take
    vis_groups = bank.vis
    kf = KFold(5, shuffle=True, random_state=SEED)
    outer_random = [(idx[a], idx[b], allsess, None, f'random fold {i + 1}') for i, (a, b) in enumerate(kf.split(idx))]
    gk = GroupKFold(5)
    outer_rec = [(idx[a], idx[b], allsess, visits_of(idx[a]), f'recording fold {i + 1}') for i, (a, b) in enumerate(gk.split(idx, groups=rec_groups))]
    outer_grp = [(idx[a], idx[b], allsess, visits_of(idx[a]), f'stop fold {i + 1}') for i, (a, b) in enumerate(gk.split(idx, groups=vis_groups))]
    outer_loso = [(idx[bank.sess != s], idx[bank.sess == s], [x for x in sessions if x != s], None, f'test {s}') for s in sessions]
    for name, outer, inner in [('random_LEAKY', outer_random, inner_random), ('by_recording_partly_leaky', outer_rec, inner_group(rec_groups)),
                               ('grouped_by_stop', outer_grp, inner_group(vis_groups)), ('leave_one_session_out', outer_loso, inner_loso)]:
        for tr, te, *_ in outer:
            if name != 'random_LEAKY':
                assert not set(bank.rec[tr]) & set(bank.rec[te])
                assert not set(rec_groups[tr]) & set(rec_groups[te]), 'pieces of one take on both sides'
            if name in ('grouped_by_stop', 'leave_one_session_out'):
                assert not set(bank.vis[tr]) & set(bank.vis[te])
        res, w = run_scheme(bank, name, outer, inner, area)
        out['schemes'][name] = res
        wins += w[0]
        samples += w[1]
    # deployable model: tune on everything with leave-one-session-out inner CV
    T = tune(bank, inner_loso(idx))
    model = {'what': 'Deployable fused kNN settings, tuned by leave-one-session-out CV on all sessions (fused_knn.py).',
             'weights': dict(zip(GROUPS, T['chosen'][0])), 'k': T['chosen'][1], 'loso_inner_acc': T['inner_acc_chosen'],
             'floor_jump_threshold_hpa': round(bank.floor_threshold(sessions), 3), 'sessions': sessions, 'window_s': D['config']['window_s']}
    out['deployable_model'] = model
    (data.OUT / 'fused_knn.json').write_text(json.dumps(out, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    (data.OUT / 'fused_model.json').write_text(json.dumps(model, indent=1))
    pd.DataFrame(wins).to_csv(data.OUT / 'fused_window_predictions.csv', index=False)
    # one row per test sample (take, or 20 s piece in split20) of the learned-weight model: prediction + top-3 (perf_sheet.py)
    pd.DataFrame(samples).to_csv(data.OUT / 'fused_sample_predictions.csv', index=False)
    for s, r in out['schemes'].items():
        print(s, json.dumps({v: (o['exact'], o['n_recordings_scored'], o['exact_acc'], o['window_acc']) for v, o in r['overall'].items()}))
    print('model', model)


if __name__ == '__main__':
    main()
