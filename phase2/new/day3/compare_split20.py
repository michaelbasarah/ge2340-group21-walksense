#!/usr/bin/env python3
"""Before/after table: the original day-3 outputs (out/) vs a variant (out-<variant>/, default split20).

Only reads the JSON files the pipeline wrote; computes nothing new. Writes out-<variant>/compare_before_after.csv
and prints it. Sample unit: "before" = one whole stop take (recording), "after" = one 20 s piece of a take, except
the tracker rows, which are always per stop visit (the tracker replays the session in time order).

Run after both pipelines:  python phase2/new/day3/compare_split20.py [variant ...]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(folder):
    j = lambda n: json.loads((folder / n).read_text())
    return {'R': j('results.json')['stop_results'], 'F': j('fused_knn.json'), 'T': j('track24_results.json'),
            'M': j('phone_session_matrix.json'), 'model': j('fused_model.json')}


def rows_for(d):
    out = []
    F = d['F']['schemes']
    for scheme, label in [('leave_one_session_out', 'fused weighted kNN, leave one session out'),
                          ('grouped_by_stop', 'fused weighted kNN, GroupKFold(5) by stop'),
                          ('by_recording_partly_leaky', 'fused weighted kNN, by recording/take (partly leaky)'),
                          ('random_LEAKY', 'fused weighted kNN, random windows (LEAKY)')]:
        o = F[scheme]['overall']['fused (learned weights)']
        out.append((label, o['exact'], o['n_recordings_scored'], F[scheme]['chance_mean']))
    fs = '|B|+xyz + baro floor'
    for key, label in [('xday_23nov_to_24s2_iphone', 'same iPhone ip16, 23 Nov -> 24 s2, |B|+xyz + floor'),
                       ('xday_24s2_to_23nov_iphone', 'same iPhone ip16, 24 s2 -> 23 Nov, |B|+xyz + floor'),
                       ('xsession_24s1_to_24s2_iphone', 'cross-session iPhone s1 -> s2 (ip18 -> ip16), |B|+xyz + floor'),
                       ('xsession_24s2_to_24s1_iphone', 'cross-session iPhone s2 -> s1 (ip16 -> ip18), |B|+xyz + floor'),
                       ('xsession_24s1_to_24s2_s24', 'cross-session S24 s1 -> s2, |B|+xyz + floor'),
                       ('xsession_24s2_to_24s1_s24', 'cross-session S24 s2 -> s1, |B|+xyz + floor')]:
        r = d['R'][key]
        out.append((label, r[fs]['exact'], r[fs]['n_recordings'], r['_split']['chance']))
    t = d['T']['results']['all_26_stops']['tracker']['exact']
    out.append(('tracker s1 -> s2 (per stop visit), exact', t['k'], t['n'], round(1 / d['T']['n_places'], 3)))
    t = d['T']['same_handset_variant']['results']['all_26_stops']['tracker']['exact']
    out.append(('tracker, same-handset variant (23 Nov -> 24 s2), exact', t['k'], t['n'], round(1 / d['T']['n_places'], 3)))
    for c in d['M']['cells']:
        if c['mode'] == 'same' and c['col'] == 'leave one session out' and c['rec_n']:
            out.append((f"playground recipe, same phone only, {c['phone']} leave one session out", c['rec_hit'], c['rec_n'],
                        None if c['chance'] is None else round(c['chance'], 3)))
    return out


def main():
    variants = sys.argv[1:] or ['split20']
    before = rows_for(load(HERE / 'out'))
    table = []
    for v in variants:
        after = {r[0]: r for r in rows_for(load(HERE / f'out-{v}'))}
        for label, k, n, ch in before:
            a = after.get(label)
            table.append({'variant': v, 'test': label, 'before_correct': k, 'before_n': n, 'before_acc': round(k / n, 3),
                          'before_chance': ch, 'after_correct': a[1] if a else '', 'after_n': a[2] if a else '',
                          'after_acc': round(a[1] / a[2], 3) if a and a[2] else '', 'after_chance': a[3] if a else ''})
    m_before = json.loads((HERE / 'out' / 'fused_model.json').read_text())
    for v in variants:
        m = json.loads((HERE / f'out-{v}' / 'fused_model.json').read_text())
        print(f"deployable weights/k  before {m_before['weights']} k {m_before['k']}   {v} {m['weights']} k {m['k']}")
        with (HERE / f'out-{v}' / 'compare_before_after.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows([r for r in table if r['variant'] == v])
    # Same test pieces: score the control variant (split20_only) only on the pieces split20 kept, for the named splits
    # whose predictions are saved per piece (results.json). Separates "fewer/easier test pieces" from "better model".
    if 'split20' in variants and 'split20_only' in variants:
        kept = {r['key'] for r in csv.DictReader((HERE / 'out-split20' / 'pieces.csv').open()) if r['status'] == 'kept'}
        same = {}
        for key in ['xday_23nov_to_24s2_iphone', 'xday_24s2_to_23nov_iphone', 'xsession_24s1_to_24s2_iphone',
                    'xsession_24s2_to_24s1_iphone', 'xsession_24s1_to_24s2_s24', 'xsession_24s2_to_24s1_s24']:
            for v in ['split20_only', 'split20']:
                pr = json.loads((HERE / f'out-{v}' / 'results.json').read_text())['stop_results'][key]['|B|+xyz + baro floor']['predictions']
                sub = {k: tp for k, tp in pr.items() if k in kept}
                same[f'{key} | {v}'] = {'all_pieces': f'{sum(t == q for t, q in pr.values())}/{len(pr)}',
                                        'on_split20_kept_pieces': f'{sum(t == q for t, q in sub.values())}/{len(sub)}'}
        (HERE / 'out-split20' / 'compare_same_pieces.json').write_text(json.dumps(same, indent=1))
        for k, v in same.items():
            print(f'same pieces  {k:55} all {v["all_pieces"]:>8}  on split20-kept pieces {v["on_split20_kept_pieces"]:>8}')
    for r in table:
        print(f"{r['variant']:12} {r['test']:72} {r['before_correct']:>4}/{r['before_n']:<4} {r['before_acc']:<6} -> "
              f"{r['after_correct']:>4}/{r['after_n']:<4} {r['after_acc']:<6} chance {r['before_chance']} / {r['after_chance']}")


if __name__ == '__main__':
    main()
