#!/usr/bin/env python3
"""Does live phyphox data from the demo phone look like the iPhone 18 training data? (PROCESS-LOG entry 95)

  python live_phone_check.py <capture folder or phyphox ZIP> [--truth 5:esca_down] [--name NAME]
      -> out/live_phone_check[_NAME].json

A capture folder is what live-walk/evidence/*/ holds: get_responses.bin(.gz) (the phone's /get answers, bytes as
received), config.json, meta.json. A ZIP is a live recording (recordings/*.zip) or a phyphox export.
Compared with the ip18 (iPhone19,2) training stops, first/last 5 s trimmed, in 2 s windows (the app's windows):
  - sample rates, pressure, and how far the newest pressure sample runs behind the newest acc sample
  - still 2 s windows (|acc| std < live.STILL_STD): mean B in phone axes, |B|, gravity direction, B noise
  - per place on the truth floor: nearest training window (scaled like the app's model) from each live window,
    and the app model's answer for those windows (the same model the port-8000 server builds: all ip18 sessions)
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

import live
import walksense as ws

DEVICE = 'iPhone19,2'
PCT = (5, 50, 95)


def read_capture(folder: Path):
    """get_responses.bin -> {sensor: array(t, ...)}: the first answer is 'full', later ones only newer samples."""
    cfg = json.loads((folder / 'config.json').read_text())
    sets = {}
    for s in cfg['export']:
        bufs = [x['buffer'] for x in s['sources']]
        for sensor, keys in live.KEYWORDS.items():
            if any(k in s['set'].lower() for k in keys):
                sets[sensor] = bufs
    gz = folder / 'get_responses.bin.gz'               # stored gzipped in live-walk/evidence (same bytes inside)
    raw = gzip.decompress(gz.read_bytes()) if gz.exists() else (folder / 'get_responses.bin').read_bytes()
    parts, last, polls = {k: [] for k in sets}, {}, []
    i = 0
    while i < len(raw):
        j = raw.index(b'\n', i)
        wall, _, n = raw[i:j].decode().split('\t')
        body = json.loads(raw[j + 1:j + 1 + int(n)])
        i = j + 1 + int(n) + 1
        for sensor, names in sets.items():
            cols = [body['buffer'].get(b, {}).get('buffer', []) for b in names]
            m = min(len(c) for c in cols)
            if not m:
                continue
            a = np.array([[np.nan if v is None else float(v) for v in c[-m:]] for c in cols]).T
            a = a[np.isfinite(a).all(1)]
            if sensor in last:
                a = a[a[:, 0] > last[sensor]]
            if len(a):
                parts[sensor].append(a); last[sensor] = float(a[-1, 0])
        if 'acc' in last and 'baro' in last:
            polls.append((float(wall), last['acc'] - last['baro']))
    rec = {s: np.vstack(v) for s, v in parts.items() if v}
    rec['device'] = json.loads((folder / 'meta.json').read_text()).get('deviceModel', '')
    return rec, polls


def windows(rec, lo, hi, still_only=False):
    """2 s windows in [lo, hi): bx, by, bz, |mean B|, gx, gy, gz (unit gravity), B noise (mean per-axis std), t."""
    mag, acc, rows = rec['mag'], rec['acc'], []
    for a in np.arange(lo, hi - ws.WINDOW_S + 1e-9, ws.WINDOW_S):
        m = mag[(mag[:, 0] >= a) & (mag[:, 0] < a + ws.WINDOW_S), 1:4]
        g = acc[(acc[:, 0] >= a) & (acc[:, 0] < a + ws.WINDOW_S), 1:4]
        if len(m) < 10 or len(g) < 10:
            continue
        if still_only and np.linalg.norm(g, axis=1).std() >= live.STILL_STD:
            continue
        b, up = m.mean(0), g.mean(0) / np.linalg.norm(g.mean(0))
        rows.append([*b, float(np.linalg.norm(b)), *up, float(m.std(0).mean()), a])
    return np.array(rows).reshape(-1, 9)


COLS = ('Bx', 'By', 'Bz', '|B|', 'gx', 'gy', 'gz', 'B_noise')


def pct(x):
    return [round(float(v), 2) for v in np.percentile(x, PCT)] if len(x) else None


def main(argv):
    src = Path(argv[0])
    truth = next((argv[i + 1] for i, a in enumerate(argv) if a == '--truth'), '')
    name = next((argv[i + 1] for i, a in enumerate(argv) if a == '--name'), '')
    if src.is_dir():
        rec, polls = read_capture(src)
    else:
        rec, polls = ws.read_zip(src.read_bytes()), []
    out = {'source': str(src), 'device': rec.get('device', ''), 'truth': truth or None}
    rate = lambda a: round(float(1 / np.median(np.diff(a[:, 0]))), 1)
    out['live'] = {'seconds': round(float(rec['acc'][-1, 0] - rec['acc'][0, 0]), 1),
                   'rate_hz': {s: rate(rec[s]) for s in live.SENSORS if s in rec and len(rec[s]) > 2},
                   'mag_time_equals_gyro_time': bool(len(rec['mag']) == len(rec['gyr']) and np.allclose(rec['mag'][:, 0], rec['gyr'][:, 0])),
                   'pressure_hpa': pct(rec['baro'][:, 1]) if 'baro' in rec else None,
                   'acc_end_minus_baro_end_s': round(float(rec['acc'][-1, 0] - rec['baro'][-1, 0]), 2) if 'baro' in rec else None,
                   'baro_lag_at_each_poll_s': pct([p for _, p in polls[1:]]) if polls else None}
    lw = windows(rec, rec['acc'][0, 0], rec['acc'][-1, 0], still_only=True)
    out['live']['still_2s_windows'] = len(lw)
    out['live']['features_p5_p50_p95'] = {c: pct(lw[:, i]) for i, c in enumerate(COLS)}

    stops = ws.training_stops(device=DEVICE, exclude=ws.TRAIN_EXCLUDE)
    tw, tl, ends, rates = [], [], [], []
    for s in stops:
        r = s['rec']
        t0, t1 = r['mag'][0, 0] + ws.TRIM_S, r['mag'][-1, 0] - ws.TRIM_S
        w = windows(r, t0, t1)
        tw.append(w); tl += [(s['floor'], s['place'], s['session'])] * len(w)
        rates.append(rate(r['mag']))
        if 'baro' in r and len(r['baro']) > 1:
            ends.append(r['acc'][-1, 0] - r['baro'][-1, 0])
    tw = np.vstack(tw)
    out['training'] = {'stops': len(stops), 'windows': len(tw), 'sessions': sorted({x[2] for x in tl}),
                       'mag_rate_hz_median': float(np.median(rates)), 'acc_end_minus_baro_end_s': pct(ends),
                       'features_p5_p50_p95': {c: pct(tw[:, i]) for i, c in enumerate(COLS)},
                       'pressure_hpa_by_floor': {f: pct(np.concatenate([s['rec']['baro'][:, 1] for s in stops
                                                                         if s['floor'] == f and 'baro' in s['rec']]))
                                                 for f in (5, 4)}}
    # live still windows inside the training range? share of live windows within the training p5..p95 per feature
    lo, hi = np.percentile(tw[:, :8], 5, axis=0), np.percentile(tw[:, :8], 95, axis=0)
    out['live_share_inside_training_p5_p95'] = {c: round(float(((lw[:, i] >= lo[i]) & (lw[:, i] <= hi[i])).mean()), 3)
                                                if len(lw) else None for i, c in enumerate(COLS)}
    floor = int(truth.split(':')[0]) if truth else 5
    model = ws.PlaceModel(stops)                       # = the server's iPhone19,2 model
    pipe = model.models[floor]
    scale = lambda x: pipe.named_steps['scale'].transform(pipe.named_steps['impute'].transform(x))
    on = np.array([f == floor for f, _, _ in tl])
    Ttr, places = scale(tw[on, :3]), np.array([p for f, p, _ in tl if f == floor])
    sess = np.array([x for f, _, x in tl if f == floor])
    res = {'floor': floor, 'training_windows_per_place': dict(Counter(places.tolist())),
           'training_visits_per_place': {p: sorted({x for q, x in zip(places, sess) if q == p}) for p in sorted(set(places))}}
    if len(lw):
        L = scale(lw[:, :3])
        d = np.linalg.norm(L[:, None, :] - Ttr[None, :, :], axis=2)
        res['live_nearest_scaled_distance_per_place_p5_p50_p95'] = {p: pct(d[:, places == p].min(1)) for p in sorted(set(places))}
        proba = pipe.predict_proba(lw[:, :3])
        mean = proba.mean(0)
        res['model_answer_mean_over_live_windows'] = [(str(pipe.classes_[i]), round(float(mean[i]), 3)) for i in np.argsort(-mean)[:5]]
        res['model_top1_per_window'] = dict(Counter(str(pipe.classes_[i]) for i in proba.argmax(1)))
    # reference: a training window's nearest window of the SAME place in another session vs of any OTHER place
    same, other = [], []
    for i in range(len(Ttr)):
        dd = np.linalg.norm(Ttr - Ttr[i], axis=1)
        m_same = (places == places[i]) & (sess != sess[i])
        if m_same.any():
            same.append(dd[m_same].min()); other.append(dd[places != places[i]].min())
    res['reference_training_nearest_same_place_other_session'] = pct(same)
    res['reference_training_nearest_other_place'] = pct(other)
    if truth:
        p = truth.split(':')[1]
        own = Ttr[places == p]
        per_visit = {x: own[sess[places == p] == x].mean(0).round(2).tolist() for x in sorted(set(sess[places == p]))}
        res['truth_place'] = {'place': p, 'visit_mean_scaled_xyz': per_visit,
                              'live_mean_scaled_xyz': scale(lw[:, :3]).mean(0).round(2).tolist() if len(lw) else None,
                              'visit_mean_raw_uT': {x: tw[on][(places == p) & (sess == x), :3].mean(0).round(1).tolist()
                                                    for x in sorted(set(sess[places == p]))},
                              'live_mean_raw_uT': lw[:, :3].mean(0).round(1).tolist() if len(lw) else None}
    out['places'] = res
    f = ws.OUT / (f'live_phone_check_{name}.json' if name else 'live_phone_check.json')
    f.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1:])
