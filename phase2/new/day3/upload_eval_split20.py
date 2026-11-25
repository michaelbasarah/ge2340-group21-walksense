#!/usr/bin/env python3
"""The teammates' upload-pipeline evaluation (../upload/walksense.py `evaluate`) scored on 20 s pieces.

Their code is imported and NOT changed. Training is exactly theirs (PlaceModel on whole 24-Nov stop takes of one
session and phone slot, their 5 s trim, 2 s windows, kNN per floor). The test is every 20 s piece of every stop take
of the other session ([0,20), [20,40), [40,60) s from the take's first magnetometer sample, trim 0 inside a piece),
scored as its own sample (top-1 / top-3 among the places on the true floor). Pieces removed by the day-3 split20
rules (out-split20/pieces.csv, status != kept) are skipped; the script stops if a removed piece would be in training.

Train and test are different sessions, so the three pieces of one take are never split across train and test.

Run (after `DAY3_VARIANT=split20 python data.py`):  python phase2/new/day3/upload_eval_split20.py
Writes out-split20/upload_eval_split20.json.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault('DAY3_VARIANT', 'split20')
import data                                                      # noqa: E402

sys.path.insert(0, str(data.NEW / 'upload'))
import walksense as ws                                           # noqa: E402  (teammates' code, unchanged)

SID = {'sesi1': '24s1', 'sesi2': '24s2'}


def piece_rec(rec, a, b):
    """Slice every sensor of a phyphox record to [a, b) on its own clock (relative to the first magnetometer sample)."""
    t0 = rec['mag'][0, 0]
    out = dict(rec)
    for k in ('mag', 'acc', 'gyr', 'baro'):
        if k in rec and rec[k] is not None and len(rec[k]):
            x = rec[k]
            out[k] = x[(x[:, 0] >= t0 + a) & (x[:, 0] < t0 + b)]
    return out


def main():
    vc = data.config()['variants'][data.VARIANT]
    piece_s = vc['piece_s']
    P = pd.read_csv(data.OUT / 'pieces.csv')
    status = {(r.take, int(r.piece)): r.status for r in P.itertuples()}
    res = {'what': 'walksense.py PlaceModel (unchanged): train on whole takes of one 24-Nov session, test every kept 20 s piece '
                   'of the other session (top-1/top-3 among places on the true floor). Computed by upload_eval_split20.py.',
           'piece_s': piece_s, 'trim_inside_piece_s': 0, 'training': 'whole takes, walksense TRIM_S = %.0f s, unchanged' % ws.TRIM_S,
           'place': {}}
    for phone in ('iphone', 's24'):
        st = {s: ws.training_stops(sessions=(s,), phone=phone) for s in ws.SESSIONS}
        folders = {s: [r['folder'] for r in ws.manifest(s) if r['type'] == 'stop' and r['phone'] == phone] for s in ws.SESSIONS}
        for tr, te in (('sesi1', 'sesi2'), ('sesi2', 'sesi1')):
            bad = [k for k, v in status.items() if k[0].startswith(SID[tr] + ':') and k[0].endswith(':' + phone) and v != 'kept']
            assert not bad, f'removed pieces in the training session would change their training set: {bad}'
            devs = f"{st[tr][0]['device']} -> {st[te][0]['device']}"
            for kind in ('tilt', 'xyz', 'magnitude'):
                m = ws.PlaceModel(st[tr], kind)
                top1 = top3 = n = skipped = 0
                rows = []
                for s, folder in zip(st[te], folders[te]):
                    take = f'{SID[te]}:{folder}:{phone}'
                    j = 0
                    while (take, j) in status:
                        if status[(take, j)] != 'kept':
                            skipped += 1; j += 1
                            continue
                        t3 = m.top3(piece_rec(s['rec'], j * piece_s, (j + 1) * piece_s), s['floor'], trim=0.0)
                        n += 1
                        top1 += t3[0][0] == s['place']; top3 += s['place'] in [p for p, _ in t3]
                        rows.append({'floor': s['floor'], 'truth': s['place'], 'piece': j, 'guess': t3[0][0], 'p': t3[0][1]})
                        j += 1
                res['place'][f'{phone} {tr}->{te} {kind}'] = {
                    'devices': devs, 'n_test_pieces': n, 'n_test_takes': len(st[te]), 'pieces_skipped_removed': skipped,
                    'top1': f'{top1}/{n}', 'top1_acc': round(top1 / n, 3), 'top3': f'{top3}/{n}', 'top3_acc': round(top3 / n, 3),
                    'chance_top1': round(float(np.mean([1 / len(m.places[r['floor']]) for r in rows])), 3),
                    **({'pieces': rows} if kind == 'xyz' else {})}
    data.OUT.mkdir(exist_ok=True)
    (data.OUT / 'upload_eval_split20.json').write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    for k, v in res['place'].items():
        print(f"{k:32} {v['devices']:28} top1 {v['top1']:>7}  top3 {v['top3']:>7}  chance {v['chance_top1']}")


if __name__ == '__main__':
    main()
