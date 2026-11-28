#!/usr/bin/env python3
"""Held-out test on the iPhone 18 Pro's new 27-Nov stops, BEFORE the app trains on them (PROCESS-LOG entry 95).

    python eval_27nov.py      -> out/ip18_27nov_test.json   (about 20 s)

Train: the iPhone19,2 place model on the other ip18 sessions only (sesi1, 25nov, 25night; TRAIN_EXCLUDE kept).
Test: the 11 stops of 27nov (iPhone19,2, 17:13 to 17:42).
- whole stop: the app's visit answer (mean over 2 s windows, first/last 5 s trimmed), on the true floor
- 1 s: the live 1 s estimate (entry 61: mean magnetic x/y/z of 1 s fed to the same kNN), for the first still second
  after the 5 s trim and for every second of the stand (per-second top-1)
- floor: the app's floor tracker (ws.analyse, rule for iPhone19,2) over the 11 stops in time order, starting on 5F
"""
import json
import sys
from pathlib import Path

import numpy as np

import walksense as ws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'smoothing'))
import smooth  # noqa: E402   (window_feature, still_flat: the entry-61 1 s estimate)

DEVICE, TRAIN, TEST = 'iPhone19,2', ('sesi1', '25nov', '25night'), '27nov'


def one_second(model, st):
    """(first still second top-1 place, per-second hits, per-second count) for one stop."""
    rec, m = st['rec'], model.models.get(st['floor'])
    acc, mag = rec['acc'], rec['mag']
    t0, t1 = mag[0, 0] + ws.TRIM_S, mag[-1, 0] - ws.TRIM_S
    first, hits, n = None, 0, 0
    for now in np.arange(t0 + 1.0, t1 + 1e-9, 1.0):
        still, _ = smooth.still_flat(acc, now)
        f = smooth.window_feature(mag, now, 1.0)
        if not still or f is None:
            continue
        guess = str(m.classes_[int(np.argmax(m.predict_proba(f[None, :])[0]))])
        first = guess if first is None else first
        hits += guess == st['place']; n += 1
    return first, hits, n


def main():
    model = ws.PlaceModel(ws.training_stops(device=DEVICE, sessions=TRAIN, exclude=ws.TRAIN_EXCLUDE))
    test = sorted(ws.training_stops(sessions=(TEST,)), key=lambda s: s['start'])
    session = ws.Session(5, rule=ws.floor_rule_for(DEVICE))
    rows, first_ok, sec_hits, sec_n = [], 0, 0, 0
    for st in test:
        rec = {**st['rec'], 'device': DEVICE, 'start_epoch': st['start']}
        res = ws.analyse(rec, session, {DEVICE: model}, kind='stop', truth=st['place'])
        first, hits, n = one_second(model, st)
        first_ok += first == st['place']; sec_hits += hits; sec_n += n
        rows.append({'place': st['place'], 'true_floor': st['floor'], 'floor': res['floor'], 'floor_note': res['floor_note'],
                     'top3': res['top3'], 'lit': res['lit'], 'right': res['correct'], 'first_1s': first,
                     'per_second': f'{hits}/{n}'})
    n = len(rows)
    out = {'what': __doc__.strip().splitlines()[0], 'train_sessions': list(TRAIN), 'test_session': TEST, 'device': DEVICE,
           'n_train_stops': sum(1 for _ in ws.training_stops(device=DEVICE, sessions=TRAIN, exclude=ws.TRAIN_EXCLUDE)),
           'n_test_stops': n,
           'whole_stop_top1': f"{sum(r['right'] for r in rows)}/{n}",
           'whole_stop_top3': f"{sum(r['place'] in [p for p, _ in r['top3']] for r in rows)}/{n}",
           'lit': sum(r['lit'] is not None for r in rows), 'lit_right': sum(r['lit'] == r['place'] for r in rows),
           'first_1s_top1': f'{first_ok}/{n}', 'per_second_top1': f'{sec_hits}/{sec_n}',
           'per_second_top1_acc': round(sec_hits / sec_n, 3) if sec_n else None,
           'floor_right': f"{sum(r['floor'] == r['true_floor'] for r in rows)}/{n}", 'floor_rule': session.rule,
           'stops': rows}
    ws.OUT.mkdir(exist_ok=True)
    (ws.OUT / 'ip18_27nov_test.json').write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != 'stops'}, indent=1))
    for r in rows:
        print(f"  {r['true_floor']}F {r['place']:22} floor {r['floor']}F  guess {r['top3'][0] if r['top3'] else '-'}  1s {r['first_1s']}  per-s {r['per_second']}")


if __name__ == '__main__':
    main()
