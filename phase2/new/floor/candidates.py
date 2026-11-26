#!/usr/bin/env python3
"""Steps 2-4: tune the pre-registered candidates on the tuning sessions, freeze the parameters, score every rule on
every session x phone slot, and draw the figures. Rules and grids: PREREGISTRATION.md (committed first, a884c97).

  python phase2/new/floor/candidates.py     # a few seconds; needs the day-3 feature cache (day3/data.py load())
Writes out/tuning.json, out/params.json, out/scores.json, out/table.csv, out/motion_check.json, out/fig_*.png.
"""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

import floorlib as fl
import rules

KS, PS, HS, MS = (5, 15, 25), (0.5, 0.6, 0.7, 0.8, 0.9), (1, 2), (0, 3)
TS = (5 * 60, 10 * 60, 15 * 60, 30 * 60, 60 * 60, float('inf'))
MASK_S = 20 * 60
RULES = ['R0', 'R1', 'c1', 'c2', 'a', 'd']
NAMES = {'R0': 'R0 upload app (0.40 hPa, last 6, 15-min gap)', 'R1': 'R1 day-3 step tracking (stop medians)',
         'c1': 'c1 R0 with the tuned gap T', 'c2': 'c2 drift-extrapolated reference, no reset',
         'a': '(a) magnetic floor vote only', 'd': '(d) pressure, else magnetic vote, hysteresis'}


def masked(rows):
    """PREREGISTRATION.md: pressure missing for every recording starting within +-20 min of the first floor change."""
    f = rows['floor'].to_numpy()
    ch = np.where(f != f[0])[0]
    t_c = rows['start'].to_numpy()[ch[0]]
    sel = np.abs(rows['start'].to_numpy() - t_c) <= MASK_S
    out = rows.copy()
    out.loc[sel, ['p0', 'p1', 'pmed']] = None
    return out, int(sel.sum())


def score(rows, pred):
    f, st = rows['floor'].to_numpy(), (rows['type'] == 'stop').to_numpy()
    ok = pred == f
    wrong = [{'time': fl.hhmm(r.session, r.start), 'place': r.place, 'true': int(r.floor), 'shown': int(p),
              'pressure': r.p0 is not None and not (isinstance(r.p0, float) and np.isnan(r.p0))}
             for r, p, o, s in zip(rows.itertuples(), pred, ok, st) if s and not o]
    return {'stops': f'{int(ok[st].sum())}/{int(st.sum())}', 'walks': f'{int(ok[~st].sum())}/{int((~st).sum())}',
            'stops_ok': int(ok[st].sum()), 'stops_n': int(st.sum()), 'walks_ok': int(ok[~st].sum()),
            'walks_n': int((~st).sum()), 'wrong_stops': wrong}


def has_pressure(rows):
    return rows['p0'].notna().any()


def run(rule, rows, sid, slot, prm, pool):
    sf = int(rows['floor'].iloc[0])
    dev = rows['device'].iloc[0]
    if rule == 'R0':
        return rules.r0(rows, sf)
    if rule == 'c1':
        return rules.r0(rows, sf, long_gap_s=prm['T'])
    if rule == 'c2':
        return rules.c2(rows, sf)
    if rule == 'R1':
        if slot not in ('iphone', 's24') or not has_pressure(rows):
            return np.full(len(rows), sf)
        return rules.r1(rows, sf, rules.r1_threshold(fl.day3()['V'], sid, slot))
    if rule == 'a':
        return rules.mag(rows, sf, rules.mag_votes(sid, dev, prm['k_a'], pool)[0])
    if rule == 'd':
        v = rules.mag_votes(sid, dev, prm['k_d'], pool)[0]
        return rules.comb(rows, sf, v, prm['P'], prm['H'], prm['M'], use_pressure=slot == 'iphone')
    raise KeyError(rule)


def units(R, sessions):
    for (sid, slot), rows in R[R['session'].isin(sessions)].groupby(['session', 'slot'], sort=False):
        yield sid, slot, rows.reset_index(drop=True)


def tune(R):
    T = {'a': {}, 'c1': {}, 'd': {}}
    tun = list(units(R, fl.TUNING))
    ip = [(s, sl, r) for s, sl, r in tun if sl == 'iphone']
    ipm = [(s, sl, masked(r)[0]) for s, sl, r in ip]
    pool = fl.TUNING
    for k in KS:
        T['a'][k] = sum(score(r, rules.mag(r, int(r['floor'].iloc[0]), rules.mag_votes(s, r['device'].iloc[0], k, pool)[0]))['stops_ok']
                        for s, sl, r in tun)
    for t in TS:
        T['c1'][t] = sum(score(r, rules.r0(r, int(r['floor'].iloc[0]), long_gap_s=t))['stops_ok'] for s, sl, r in ip + ipm)
    d_units = ip + ipm + [(s, sl, r) for s, sl, r in tun if sl != 'iphone']
    for k, P, H, M in itertools.product(KS, PS, HS, MS):
        T['d'][(k, P, H, M)] = sum(score(r, rules.comb(r, int(r['floor'].iloc[0]), rules.mag_votes(s, r['device'].iloc[0], k, pool)[0],
                                                      P, H, M, use_pressure=sl == 'iphone'))['stops_ok'] for s, sl, r in d_units)
    k_a = max(KS, key=lambda k: (T['a'][k], k))
    best_c1 = max(T['c1'].values())
    t_c1 = 15 * 60 if T['c1'][15 * 60] == best_c1 else max(t for t in TS if T['c1'][t] == best_c1)
    k_d, P, H, M = max(T['d'], key=lambda q: (T['d'][q], q[2], q[1], -q[3], q[0]))
    n_stops = {'a': sum(int((r['type'] == 'stop').sum()) for _, _, r in tun),
               'c1': sum(int((r['type'] == 'stop').sum()) for _, _, r in ip + ipm),
               'd': sum(int((r['type'] == 'stop').sum()) for _, _, r in d_units)}
    tuning = {'what': 'stops correct summed over the tuning units of each grid point (PREREGISTRATION.md)', 'n_stops': n_stops,
              'masked_recordings': {s: masked(r)[1] for s, _, r in ip},
              'a_k': {str(k): v for k, v in T['a'].items()},
              'c1_T_min': {('never' if t == float('inf') else str(int(t // 60))): v for t, v in T['c1'].items()},
              'd_grid': [{'k': q[0], 'P': q[1], 'H': q[2], 'M': q[3], 'stops_ok': v} for q, v in sorted(T['d'].items(), key=lambda x: -x[1])]}
    params = {'k_a': k_a, 'T': t_c1, 'k_d': k_d, 'P': P, 'H': H, 'M': M,
              'T_min': 'never' if t_c1 == float('inf') else t_c1 / 60}
    return tuning, params


def motion_check(R):
    """(b) data-support test: does any recording contain a floor step of pressure (|p1 - p0| > 0.40 hPa)?"""
    P = R[R['p0'].notna() & (R['session'] != '23nov')].copy()
    P['dp'] = (P['p1'] - P['p0']).astype(float)
    big = P[P['dp'].abs() > 0.40]
    out = {'what': 'PREREGISTRATION.md (b): |p1 - p0| (edge medians) of every recording with pressure; > 0.40 hPa would '
                   'mean a floor change inside the recording', 'n_recordings': {}, 'max_abs_dp_hpa': {}, 'over_0.40': {}}
    for slot, g in P.groupby('slot'):
        out['n_recordings'][slot] = len(g)
        out['max_abs_dp_hpa'][slot] = round(float(g['dp'].abs().max()), 3)
        out['over_0.40'][slot] = [{'session': r.session, 'time': fl.hhmm(r.session, r.start), 'type': r.type, 'place': r.place,
                                   'dp_hpa': round(float(r.dp), 3)} for r in big[big['slot'] == slot].itertuples()]
    ip = P[P['slot'] == 'iphone']
    out['iphone_testable'] = bool((ip['dp'].abs() > 0.40).any())
    return out, P


def main():
    fl.OUT.mkdir(exist_ok=True)
    R = fl.recordings()
    tuning, prm = tune(R)
    (fl.OUT / 'tuning.json').write_text(json.dumps(tuning, indent=1))
    (fl.OUT / 'params.json').write_text(json.dumps({'frozen_from': 'tuning sessions ' + ', '.join(fl.TUNING), **prm,
                                                      'T': None if prm['T'] == float('inf') else prm['T']}, indent=1))
    print('params', prm)
    scores, table = {}, []
    for phase, sessions, pool in (('tuning', fl.TUNING, fl.TUNING), ('held-out', fl.HELDOUT, fl.SESSIONS)):
        for sid, slot, rows in units(R, sessions):
            variants = [('', rows)]
            if phase == 'tuning' and slot == 'iphone':
                variants.append((' masked', masked(rows)[0]))
            for tag, rr in variants:
                u = f'{sid} {slot}{tag}'
                scores[u] = {'phase': phase, 'session': sid, 'slot': slot, 'handset': rr['handset'].iloc[0],
                             'pressure_recordings': f"{int(rr['p0'].notna().sum())}/{len(rr)}", 'rules': {}}
                row = {'unit': u, 'phase': phase, 'handset': rr['handset'].iloc[0], 'pressure': scores[u]['pressure_recordings']}
                for rule in RULES:
                    s = score(rr, run(rule, rr, sid, slot, prm, pool))
                    scores[u]['rules'][rule] = s
                    row[f'{rule} stops'] = s['stops']
                    row[f'{rule} walks'] = s['walks']
                vt, vpool = rules.mag_votes(sid, rr['device'].iloc[0], prm['k_d'], pool)
                scores[u]['vote_pool'] = vpool
                scores[u]['votes_k_d'] = [{'time': fl.hhmm(sid, r.start), 'place': r.place, 'true': int(r.floor),
                                           'vote': vt[r.key][0], 'p': round(vt[r.key][1], 2), 'pressure': bool(pd.notna(r.p0))}
                                          for r in rr.itertuples() if r.type == 'stop' and r.key in vt]
                table.append(row)
    mc, P = motion_check(R)
    (fl.OUT / 'motion_check.json').write_text(json.dumps(mc, indent=1))
    (fl.OUT / 'scores.json').write_text(json.dumps({'rules': NAMES, 'params': {**prm, 'T': None if prm['T'] == float('inf') else prm['T']}, 'units': scores}, indent=1))
    T = pd.DataFrame(table)
    T.to_csv(fl.OUT / 'table.csv', index=False)
    print(T[['unit', 'pressure'] + [f'{r} stops' for r in RULES]].to_string(index=False))
    (fl.OUT / 'decision.json').write_text(json.dumps(decision(scores), indent=1))
    figures(R, scores, prm, P)


def decision(scores):
    """The decision rule of PREREGISTRATION.md, applied to every candidate."""
    U = scores
    wrong = lambda u, r: {(w['time'], w['place']) for w in U[u]['rules'][r]['wrong_stops']}
    out = {'what': 'PREREGISTRATION.md decision rule', 'iphone': {}, 'no_pressure': {}}
    complete = ['25night_tian iphone', '26tian iphone', '25spots iphone']
    for r in ['R1', 'c1', 'c2', 'a', 'd']:
        lost = {u: sorted(map(list, wrong(u, r) - wrong(u, 'R0'))) for u in complete}
        gain = U['25night iphone']['rules'][r]['stops_ok'] - U['25night iphone']['rules']['R0']['stops_ok']
        out['iphone'][r] = {'R0_correct_stops_lost_where_pressure_complete': lost, 'gain_25night_ip18': gain,
                            'recommended': not any(lost.values()) and gain > 0}
    tun = ['24s1 a55', '24s1 a56', '25nov a55', '25nov a56', '24s1 s24', '24s2 s24']
    for r in ['a', 'd']:
        held = (U['25night a56']['rules'][r]['stops_ok'], U['25night a56']['rules']['R0']['stops_ok'])
        t = (sum(U[u]['rules'][r]['stops_ok'] for u in tun), sum(U[u]['rules']['R0']['stops_ok'] for u in tun),
             sum(U[u]['rules'][r]['stops_n'] for u in tun))
        out['no_pressure'][r] = {'held_out_25night_a56': f'{held[0]} vs kept floor {held[1]} of 32',
                                 'tuning_a55_a56_s24_sum': f'{t[0]} vs kept floor {t[1]} of {t[2]}',
                                 'recommended': held[0] > held[1] and t[0] > t[1]}
    return out


def figures(R, scores, prm, P):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # 1. accuracy grid
    U = list(scores)
    A = np.array([[scores[u]['rules'][r]['stops_ok'] / max(1, scores[u]['rules'][r]['stops_n']) for r in RULES] for u in U])
    fig, ax = plt.subplots(figsize=(7.5, 0.28 * len(U) + 1.2), dpi=110)
    ax.imshow(A, cmap='Greens', vmin=0.3, vmax=1, aspect='auto')
    for i, u in enumerate(U):
        for j, r in enumerate(RULES):
            ax.text(j, i, scores[u]['rules'][r]['stops'], ha='center', va='center', fontsize=7)
    ax.set_xticks(range(len(RULES)), RULES, fontsize=8)
    ax.set_yticks(range(len(U)), [f"{u} ({scores[u]['handset']})" for u in U], fontsize=7)
    ax.xaxis.tick_top()
    ax.set_title('Stops on the right floor (tuning units first, then held-out)', fontsize=9, pad=18)
    n_t = sum(scores[u]['phase'] == 'tuning' for u in U)
    ax.axhline(n_t - 0.5, color='k', lw=1)
    fig.tight_layout(); fig.savefig(fl.OUT / 'fig_scores.png'); plt.close(fig)
    # 2. 25-night timeline: Dicta ip18 pressure + floors per rule; Chris a56 floors
    fig, axs = plt.subplots(2, 1, figsize=(8, 5), dpi=110, sharex=True, gridspec_kw={'height_ratios': [2, 1.3]})
    rows = R[(R['session'] == '25night') & (R['slot'] == 'iphone')].reset_index(drop=True)
    h = rows['start'] / 3600
    ok = rows['p0'].notna()
    axs[0].scatter(h[ok], rows.loc[ok, 'pmed'], c=['tab:blue' if f == 5 else 'tab:orange' for f in rows.loc[ok, 'floor']], s=10)
    for x in h[~ok]:
        axs[0].axvline(x, color='0.85', lw=0.8, zorder=0)
    axs[0].set_ylabel('ip18 pressure (hPa)', fontsize=8)
    axs[0].set_title('25 Nov night: Dicta ip18 pressure (blue 5F, orange 4F; grey lines = takes without pressure)', fontsize=8)
    sf = int(rows['floor'].iloc[0])
    lines = [('true', rows['floor'].to_numpy(), 'k', 0)]
    for k, rule in enumerate(['R0', 'R1', 'd']):
        lines.append((f'ip18 {rule}', run(rule, rows, '25night', 'iphone', prm, fl.SESSIONS), f'C{k}', 0.06 * (k + 1)))
    a56 = R[(R['session'] == '25night') & (R['slot'] == 'a56')].reset_index(drop=True)
    for lab, y, c, off in lines:
        axs[1].step(h, y + off, where='post', color=c, label=lab, lw=1.2)
    axs[1].step(a56['start'] / 3600, run('d', a56, '25night', 'a56', prm, fl.SESSIONS) - 0.08, where='post', color='tab:red', lw=1.2, label='a56 (d)')
    axs[1].step(a56['start'] / 3600, a56['floor'] - 0.14, where='post', color='0.5', lw=1, ls=':', label='a56 true')
    axs[1].set_yticks([4, 5], ['4F', '5F']); axs[1].legend(fontsize=6, ncol=3, loc='center right')
    axs[1].set_xlabel('hour (after midnight > 24)', fontsize=8)
    fig.tight_layout(); fig.savefig(fl.OUT / 'fig_25night_timeline.png'); plt.close(fig)
    # 3. (b) within-recording pressure change vs one floor step
    fig, ax = plt.subplots(figsize=(5, 2.6), dpi=110)
    for slot, c in (('iphone', 'tab:blue'), ('s24', 'tab:gray')):
        g = P[P['slot'] == slot]['dp']
        ax.hist(g, bins=np.linspace(-1.5, 1.5, 61), color=c, alpha=0.7, label=f'{slot} (n={len(g)})')
    ax.axvline(0.40, color='r', ls='--', lw=1); ax.axvline(-0.40, color='r', ls='--', lw=1)
    ax.set_xlabel('pressure end - start inside one recording (hPa); red = 0.40', fontsize=8)
    ax.legend(fontsize=7); ax.set_yscale('log')
    fig.tight_layout(); fig.savefig(fl.OUT / 'fig_motion_check.png'); plt.close(fig)


if __name__ == '__main__':
    main()
