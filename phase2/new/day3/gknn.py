"""Group-weighted kNN: one distance per sensor group, combined with weights.

Groups (feature blocks):
  B     magnetic field strength |B|: mean, sd, p10, p90 per window   (orientation-free)
  xyz   mean magnetic x, y, z per window                             (depends on how the phone is held)
  tilt  B_vertical, B_horizontal (field split along gravity)         (needs the accelerometer; NaN on 23-Nov stops)
  wifi  the stop's Wi-Fi vector (strongest RSSI per BSSID, 0 = not heard), one per physical stop
  baro  the stop's floor from iPhone-barometer step tracking (threshold learned from the TRAINING sessions only)

Per group g: d_g = mean squared difference of standardised features (stats from the training rows only),
divided by the median d_g over training pairs, so the groups are on one scale. Wi-Fi: squared RSSI difference
summed over the BSSIDs heard at either stop / number of those BSSIDs. Baro: 0 if same floor, else 1.
Combined:  D = sum_g w_g * a_g * d_g / sum_g w_g * a_g,  a_g = 1 if both rows have group g (missing groups drop out).
Prediction: k nearest training windows, votes weighted 1/D, summed over the windows of a recording, argmax.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

import data

NUMERIC = {'B': data.MAG_B, 'xyz': data.MAG_XYZ, 'tilt': data.TILT}
ALL_GROUPS = ['B', 'xyz', 'tilt', 'wifi', 'baro']
MEDIAN_SEED = 21
# Determinism (PROCESS-LOG 91): the group scale (median distance over 3000 random training pairs) used to draw from ONE
# module-level generator, so its value depended on how many dists() calls the process had made before (evaluate.py
# before fused_knn.py in one process gave 179/411 instead of 178/411). Every dists() call now starts its own generator
# from MEDIAN_SEED, so the scale depends only on the training rows of that call.


class Bank:
    def __init__(self, D: dict, wifi_rows: str = 'near', wifi_scanner: str | None = None):
        self.W = D['W'].reset_index(drop=True)
        self.V = D['V'].set_index('visit')
        self.y = self.W['place'].to_numpy()
        self.rec = self.W['key'].to_numpy()
        self.vis = self.W['visit'].to_numpy()
        self.sess = self.W['session'].to_numpy()
        # Wi-Fi: one vector per physical stop
        O = D['O'] if wifi_rows == 'near' else D['O'][D['O']['in_window']]
        if wifi_scanner:
            O = O[O['scanner'] == wifi_scanner]
        visits = list(self.V.index)
        vi = {v: i for i, v in enumerate(visits)}
        bs = {b: j for j, b in enumerate(sorted(O['bssid'].unique()))}
        X = np.zeros((len(visits), max(1, len(bs))), np.float32)
        best = O.groupby(['visit', 'bssid'])['rssi'].max().reset_index()
        X[best['visit'].map(vi).to_numpy(), best['bssid'].map(bs).to_numpy()] = np.clip((best['rssi'].to_numpy() + 100) / 100, 0.01, 1)
        P = (X > 0).astype(np.float32)
        sq = (X * X).sum(1)
        d2 = sq[:, None] + sq[None, :] - 2 * X @ X.T
        n = P.sum(1)
        union = n[:, None] + n[None, :] - P @ P.T
        with np.errstate(invalid='ignore', divide='ignore'):
            self.wifi_vd = np.where(union > 0, d2 / union, np.nan).astype(np.float32)
        self.wifi_has = n > 0
        self.vidx = np.array([vi[v] for v in self.vis])
        self.n_bssids = len(bs)

    # ------------------------------------------------------------------ floor from the barometer
    def floor_threshold(self, train_sessions, train_visits=None) -> float:
        """Half the median pressure jump between consecutive stops on different floors, from training data only.
        Consecutive = next stop of the same track (a track = the stops one group walked in order; = the session unless
        the session's manifest has a `track` column, e.g. 25 Nov: route round vs spot recordings).
        train_visits: if given, only pairs of consecutive stops that are both training visits are used."""
        steps = []
        for s in train_sessions:
            for _, v in self.V[self.V['session'] == s].groupby('track', sort=True):
                v = v.sort_values('start')
                p, f = v['hpa_iphone'].to_numpy(), v['floor'].to_numpy()
                ok = np.isfinite(p)
                if train_visits is not None:
                    ok &= v.index.isin(list(train_visits))
                idx = np.where(ok)[0]
                for i, j in zip(idx, idx[1:]):
                    if j == i + 1 and f[i] != f[j]:
                        steps.append(abs(p[j] - p[i]))
        return float(np.median(steps)) / 2 if steps else 0.3

    def tracked_floors(self, threshold: float) -> dict:
        """Barometer step tracking per track. A stop with no iPhone pressure of its own gets NaN (floor unknown, the
        baro group is then unavailable for it) instead of inheriting the previous stop's floor."""
        out = {}
        for _, v in self.V.groupby('track', sort=True):
            v = v.sort_values('start')
            p = v['hpa_iphone'].to_numpy()
            fl = data.track_floor(p, threshold).astype(float)
            fl[~np.isfinite(p)] = np.nan
            out.update(dict(zip(v.index, fl)))
        return out

    # ------------------------------------------------------------------ distances
    def dists(self, tr, te, groups, floor_threshold=None):
        """Per group: (d [nte, ntr] float32, avail_te [nte], avail_tr [ntr])."""
        out = {}
        for g in groups:
            if g in NUMERIC:
                cols = NUMERIC[g]
                A, B = self.W.loc[tr, cols].to_numpy(float), self.W.loc[te, cols].to_numpy(float)
                at, ae = ~np.isnan(A).any(1), ~np.isnan(B).any(1)
                if at.sum() < 2:
                    continue
                mu, sd = A[at].mean(0), A[at].std(0) + 1e-9
                Za, Zb = np.nan_to_num((A - mu) / sd), np.nan_to_num((B - mu) / sd)
                d = cdist(Zb, Za, 'sqeuclidean').astype(np.float32) / len(cols)
                ia = np.where(at)[0]
                rng = np.random.default_rng(MEDIAN_SEED)       # fresh per call: same rows -> same pairs
                p, q = rng.choice(ia, 3000), rng.choice(ia, 3000)
                med = np.median(((Za[p] - Za[q]) ** 2).mean(1)[p != q])
                out[g] = (d / max(med, 1e-9), ae, at)
            elif g == 'wifi':
                vt, ve = self.vidx[tr], self.vidx[te]
                d = self.wifi_vd[np.ix_(ve, vt)]
                at, ae = self.wifi_has[vt], self.wifi_has[ve]
                uv = np.unique(vt[at])
                sub = self.wifi_vd[np.ix_(uv, uv)]
                med = np.nanmedian(sub[~np.eye(len(uv), dtype=bool)]) if len(uv) > 1 else 1.0
                out[g] = (np.nan_to_num(d / max(med, 1e-9), nan=0.0).astype(np.float32), ae, at)
            elif g == 'baro':
                fl = self.tracked_floors(floor_threshold)
                ft = np.array([fl[v] for v in self.vis[tr]]); fe = np.array([fl[v] for v in self.vis[te]])
                at, ae = np.isfinite(ft), np.isfinite(fe)
                d = ((fe[:, None] != ft[None, :]) & ae[:, None] & at[None, :]).astype(np.float32)   # unknown floor -> 0, and marked unavailable
                out[g] = (d, ae, at)
        return out

    @staticmethod
    def combine(dd, w):
        num, den = 0.0, 0.0
        for g, wg in w.items():
            if wg <= 0 or g not in dd:
                continue
            d, ae, at = dd[g]
            a = (ae[:, None] & at[None, :]).astype(np.float32) * wg
            num = num + a * d
            den = den + a
        if isinstance(den, float):
            return None
        with np.errstate(invalid='ignore', divide='ignore'):
            D = np.where(den > 0, num / den, np.inf)
        return D


def knn_scores(D, ytr, classes, ks, gate=None):
    """Per k: class score matrix [nte, ncls] (votes weighted 1/D). gate: bool [nte, ntr], False = not allowed."""
    if gate is not None:
        D = np.where(gate, D, np.inf)
    kmax = min(max(ks), D.shape[1])
    idx = np.argpartition(D, kmax - 1, axis=1)[:, :kmax]
    dsel = np.take_along_axis(D, idx, 1)
    # Explicit tie-break (PROCESS-LOG 91): equal distances are ordered by training-row index. Rows where the kmax-th
    # distance is shared with an unselected training row are re-selected with a stable full sort (lowest index wins),
    # so the neighbour set never depends on the selection algorithm's internal order.
    kth = dsel.max(1)
    tied = (D <= kth[:, None]).sum(1) > kmax
    if tied.any():
        r = np.where(tied)[0]
        idx[r] = np.argsort(D[r], axis=1, kind='stable')[:, :kmax]
        dsel[r] = np.take_along_axis(D[r], idx[r], 1)
    order = np.lexsort((idx, dsel), axis=1)
    idx, dsel = np.take_along_axis(idx, order, 1), np.take_along_axis(dsel, order, 1)
    ci = {c: i for i, c in enumerate(classes)}
    lab = np.vectorize(ci.get)(ytr[idx])
    wts = np.where(np.isfinite(dsel), 1.0 / (dsel + 1e-6), 0.0)
    out = {}
    for k in ks:
        k = min(k, kmax)
        S = np.zeros((D.shape[0], len(classes)))
        rows = np.repeat(np.arange(D.shape[0]), k)
        np.add.at(S, (rows, lab[:, :k].ravel()), wts[:, :k].ravel())
        S = S / np.maximum(S.sum(1, keepdims=True), 1e-12)
        out[k] = S
    return out, idx[:, 0]


def aggregate(S, keys, classes):
    """Sum window score vectors per recording -> predicted class per recording."""
    df = pd.DataFrame(S, columns=classes)
    df['key'] = keys
    agg = df.groupby('key').sum()
    return dict(zip(agg.index, np.array(classes, dtype=object)[agg.to_numpy().argmax(1)]))


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(float(c - h), 3), round(float(c + h), 3)]


def score_records(pred: dict, truth: dict, area: dict | None = None):
    keys = sorted(pred)
    n = len(keys)
    ex = sum(pred[k] == truth[k] for k in keys)
    out = {'n_recordings': n, 'exact': int(ex), 'exact_acc': round(ex / n, 3) if n else None, 'exact_ci95': wilson(ex, n)}
    if area:
        ar = sum(area.get(pred[k]) == area.get(truth[k]) for k in keys)
        out.update({'area': int(ar), 'area_acc': round(ar / n, 3) if n else None, 'area_ci95': wilson(ar, n)})
    return out
