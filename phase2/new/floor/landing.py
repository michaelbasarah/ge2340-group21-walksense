#!/usr/bin/env python3
"""Connector-gated floor rules (e): tune on the tuning sessions, freeze, score every rule on every session x phone
slot, transitions table, gate statistics, decision, figures. Rules, grids and decision: PREREGISTRATION_landing.md
(committed 0e8ef6a before any gated rule was run).

  python phase2/new/floor/landing.py      # about a minute (the app place model is trained once per test session)
Writes out/landing_pred_app.json, out/landing_tuning.json, out/landing_params.json, out/landing_scores.json,
out/landing_table.csv, out/transitions.json, out/landing_gate_stats.json, out/landing_decision.json, out/fig_landing_*.png
"""
from __future__ import annotations

import itertools
import json
from collections import Counter

import numpy as np
import pandas as pd

import candidates as cand
import floorlib as fl
import landing_rules as lr
import rules

ws, d3 = fl.ws, fl.d3
TS = (5, 10, 20, 30, 45, 60)              # minutes
THETAS = (0.30, 0.40)
SOURCES = ('true', 'pred_d3', 'pred_app')
GATED = ('eR0', 'eR0n', 'eR1', 'ed')
BASE = ('R0', 'R1', 'd')
D_PRM = json.loads((fl.OUT / 'params.json').read_text())     # (d) frozen in entry 74


# ----------------------------------------------------------------------------- gate sources
def pred_d3():
    S = pd.read_csv(fl.NEW / 'day3' / 'out' / 'fused_sample_predictions.csv')
    S = S[S['scheme'] == 'leave_one_session_out']
    return dict(zip(S['key'], S['pred']))


def pred_app(R):
    """Upload-app PlaceModel ('xyz') top-1 per stop and per floor, trained on the OTHER upload-app sessions' stops of
    the same phone model (25 spots: all six). Cached in out/landing_pred_app.json."""
    f = fl.OUT / 'landing_pred_app.json'
    if f.exists():
        return {k: {int(a): b for a, b in v.items()} for k, v in json.loads(f.read_text())['top1'].items()}
    cfg = {s['id']: s for s in d3.config()['sessions']}
    app_sessions = list(fl.UPLOAD_NAME.values())
    cache_tr, out, info = {}, {}, {}
    for (sid, slot), rows in R[R['session'] != '23nov'].groupby(['session', 'slot']):
        dev = rows['device'].iloc[0]
        others = tuple(s for s in app_sessions if s != fl.UPLOAD_NAME.get(sid))
        if (dev, others) not in cache_tr:
            tr = ws.training_stops(device=dev, sessions=others)
            cache_tr[(dev, others)] = ws.PlaceModel(tr) if tr else None
        m = cache_tr[(dev, others)]
        info[f'{sid} {slot}'] = {'device': dev, 'trained_on': list(others) if m else [], 'model': m is not None}
        if m is None:
            continue
        root = (d3.HERE / cfg[sid]['path']).resolve()
        for r in rows[rows['type'] == 'stop'].itertuples():
            rec = ws.read_folder(root / r.folder / r.slot, dev)
            if 'mag' not in rec or 'acc' not in rec or len(rec['mag']) < 20 or len(rec['acc']) < 20:
                continue
            out[r.key] = {fl_: (m.top3(rec, fl_) or [('', 0)])[0][0] for fl_ in (4, 5)}
    f.write_text(json.dumps({'what': 'upload app PlaceModel xyz top-1 per stop, asked on 4F and on 5F; same phone model, '
                                     'trained on the other upload-app sessions (PREREGISTRATION_landing.md pred_app)',
                             'units': info, 'top1': out}, indent=1))
    return out


# ----------------------------------------------------------------------------- running a rule
def run(rule, rows, sid, slot, prm, pool, src=None, preds=None):
    sf = int(rows['floor'].iloc[0])
    dev = rows['device'].iloc[0]
    if rule in BASE:
        return cand.run(rule, rows, sid, slot, D_PRM | {'T': None}, pool)
    if src == 'pred_app' and sid == '23nov':
        src = None                                   # not an app session: ungated (pre-registered)
    T = prm['T'] * 60 if src else None
    g = lr.Gate(src, T, (preds or {}).get(src))
    if rule == 'eR0':
        return lr.er0(rows, sf, g)
    if rule == 'eR0n':
        return lr.er0(rows, sf, g, theta=prm['theta'], reset=False)
    if rule == 'eR1':
        if slot not in ('iphone', 's24') or not cand.has_pressure(rows):
            return np.full(len(rows), sf)
        return lr.er1(rows, sf, rules.r1_threshold(fl.day3()['V'], sid, slot), g)
    if rule == 'ed':
        v = rules.mag_votes(sid, dev, D_PRM['k_d'], pool)[0]
        return lr.ed(rows, sf, v, D_PRM['P'], D_PRM['H'], D_PRM['M'], g, use_pressure=slot == 'iphone')
    raise KeyError(rule)


def tuning_units(R):
    tun = list(cand.units(R, fl.TUNING))
    out = []
    for s, sl, r in tun:
        out.append((s, sl, r))
        if sl == 'iphone':
            out.append((s, sl + ' masked', cand.masked(r)[0]))
    return out


def tune(R, preds):
    tu = tuning_units(R)
    grid, best = {}, {}
    for rule, src in itertools.product(GATED, SOURCES):
        cells = []
        for T, th in itertools.product(TS, THETAS if rule == 'eR0n' else (0.40,)):
            prm = {'T': T, 'theta': th}
            n = sum(cand.score(r, run(rule, r, s, sl.split()[0], prm, fl.TUNING, src, preds))['stops_ok']
                    for s, sl, r in tu if not (src == 'pred_app' and s == '23nov'))
            cells.append({'T_min': T, 'theta': th, 'stops_ok': n})
        grid[f'{rule}-{src}'] = cells
        top = max(c['stops_ok'] for c in cells)
        pick = min((c for c in cells if c['stops_ok'] == top), key=lambda c: (c['T_min'], -c['theta']))   # ties: smaller T, theta 0.40
        best[f'{rule}-{src}'] = {'T': pick['T_min'], 'theta': pick['theta']}
    ungated = {}
    for rule in GATED:
        for scope, skip23 in (('all tuning units', False), ('without 23 Nov (pred_app scope)', True)):
            n = sum(cand.score(r, run(rule, r, s, sl.split()[0], {'T': 0, 'theta': 0.40}, fl.TUNING, None, preds))['stops_ok']
                    for s, sl, r in tu if not (skip23 and s == '23nov'))
            ungated[f'{rule} ungated, {scope}'] = n
    n_stops = {src: sum(int((r['type'] == 'stop').sum()) for s, _, r in tu if not (src == 'pred_app' and s == '23nov'))
               for src in SOURCES}
    return {'what': 'stops right summed over the tuning units (iphone, iphone masked, s24, a55, a56) per grid cell '
                    '(PREREGISTRATION_landing.md); pred_app leaves 23 Nov out', 'n_stops': n_stops,
            'ungated_reference': ungated, 'grid': grid}, best


# ----------------------------------------------------------------------------- descriptive outputs
def touches(rows, src, preds, floors):
    """(index, kinds) of every touch; pred_app is asked on `floors` = the floor shown before each recording (here the
    true floor of the previous recording, i.e. a tracker that was right until then)."""
    g = lr.Gate(src, 1e9, preds.get(src))
    out = []
    for i, (r, f) in enumerate(zip(rows.itertuples(), floors)):
        n = len(g.touches)
        g.observe(r, int(f))
        if len(g.touches) > n:
            out.append((i, sorted(g.touches[-1][1])))
    return out


def transitions(R, preds, params):
    res = []
    for sid, slot, rows in cand.units(R, fl.SESSIONS):
        f = rows['floor'].to_numpy()
        t = rows['start'].to_numpy()
        for i in np.where(np.diff(f) != 0)[0] + 1:
            a, b = int(f[i - 1]), int(f[i])
            prev_p = [j for j in range(i) if pd.notna(rows.loc[j, 'p1'])]
            next_p = [j for j in range(i, len(rows)) if pd.notna(rows.loc[j, 'p0'])]
            step = None
            if prev_p and next_p and slot == 'iphone':
                step = round(float(rows.loc[next_p[0], 'p0'] - rows.loc[prev_p[-1], 'p1']), 3)
            e = {'unit': f'{sid} {slot}', 'change': f'{a}F->{b}F', 'time': fl.hhmm(sid, t[i]),
                 'last_on_old_floor': rows.loc[i - 1, 'place'], 'first_on_new_floor': rows.loc[i, 'place'],
                 'arrival_is_landing': lr.kind(rows.loc[i, 'place'].split('->')[0]) is not None,
                 'gap_min': round(float(t[i] - (t[i - 1] + rows.loc[i - 1, 'dur'])) / 60, 1),
                 'pressure_step_hpa': step,
                 'pressure_last_before': None if not prev_p else {'time': fl.hhmm(sid, t[prev_p[-1]]), 'min_before': round(float(t[i] - t[prev_p[-1]]) / 60, 1)},
                 'pressure_first_after': None if not next_p else {'time': fl.hhmm(sid, t[next_p[0]]), 'min_after': round(float(t[next_p[0]] - t[i]) / 60, 1)},
                 'departure_touch': {}}
            for src in SOURCES:
                if src == 'pred_app' and sid == '23nov':
                    e['departure_touch'][src] = 'n/a'
                    continue
                tc = [(j, k) for j, k in touches(rows, src, preds, np.r_[f[0], f[:-1]]) if j <= i and any((a, b) in lr.ALLOWS[x] for x in k)]
                tc_old = [(j, k) for j, k in tc if j < i]
                e['departure_touch'][src] = {
                    'last_on_old_floor': None if not tc_old else {'true_place': rows.loc[tc_old[-1][0], 'place'], 'touch_kinds': tc_old[-1][1],
                                                                 'min_before': round(float(t[i] - t[tc_old[-1][0]]) / 60, 1)},
                    'arrival_touch': bool(tc and tc[-1][0] == i)}
            res.append(e)
    # 23-Nov ACC23: the only recording across a floor change (stairs, walk without barometer)
    V = fl.day3()['V']
    v = V[V['session'] == '23nov'].sort_values('start')
    bm = dict(zip(v['visit'].str.split(':').str[1], v['hpa_iphone']))
    acc23 = {'walk': 'ACC23 "From exit 5 stairs" (exit 5 stairs -> exit 5 stairs bawah), 18:34:17 to 18:34:47, 30 s, no barometer',
             'source': 'phase2/clean-data/2026-11-23/accelerometer_edges.csv, recording_intervals.csv',
             'stop_before': {'stop': 'BM26 lift_stairs 5F', 'end_hk': '18:32:53', 'hpa': round(float(bm.get('BM26', np.nan)), 3)},
             'stop_after': {'stop': 'BM27 lift_stairs_4F', 'start_hk': '18:34:54', 'hpa': round(float(bm.get('BM27', np.nan)), 3)}}
    acc23['pressure_step_hpa'] = round(acc23['stop_after']['hpa'] - acc23['stop_before']['hpa'], 3)
    # within-walk check: walks starting/ending at a connector landing, does the walk's own pressure move a floor step?
    W = R[(R['type'] == 'walk') & R['p0'].notna() & (R['slot'] == 'iphone')].copy()
    W = W[[any(lr.kind(x) for x in p.split('->')) for p in W['place']]]
    W['dp'] = (W['p1'] - W['p0']).astype(float)
    within = {'n_walks_with_connector_endpoint_and_pressure': int(len(W)),
              'max_abs_dp_hpa': round(float(W['dp'].abs().max()), 3) if len(W) else None,
              'over_0.40': int((W['dp'].abs() > 0.40).sum())}
    return {'what': 'every labelled floor change (consecutive recordings on different floors) per unit; departure touch = '
                    'last touch on the old floor whose connector allows the change; PREREGISTRATION_landing.md',
            'changes': res, 'acc23_23nov': acc23, 'within_walk': within}


def gate_stats(R, preds, params):
    out = {}
    for sid, slot, rows in cand.units(R, fl.SESSIONS):
        f, t = rows['floor'].to_numpy(), rows['start'].to_numpy()
        ch = list(np.where(np.diff(f) != 0)[0] + 1)
        u = {}
        for src in SOURCES:
            if src == 'pred_app' and sid == '23nov':
                continue
            T = params[f'eR0-{src}']['T'] * 60
            tc = touches(rows, src, preds, np.r_[f[0], f[:-1]])
            useful = [j for j, k in tc if any(i >= j and t[i] - t[j] <= T and any((int(f[i - 1]), int(f[i])) in lr.ALLOWS[x] for x in k) for i in ch)]
            opened = [i for i in ch if any(j <= i and t[i] - t[j] <= T and any((int(f[i - 1]), int(f[i])) in lr.ALLOWS[x] for x in k) for j, k in tc)]
            u[src] = {'T_min': T / 60, 'touches': len(tc), 'touches_followed_by_change': len(useful),
                      'touches_without_change': len(tc) - len(useful), 'changes': len(ch), 'changes_with_open_gate': len(opened)}
        out[f'{sid} {slot}'] = u
    st = R[R['type'] == 'stop']
    rec = {}
    for src in ('pred_d3', 'pred_app'):
        P = preds[src]
        c = Counter()
        for r in st.itertuples():
            if r.key not in P or (src == 'pred_app' and r.session == '23nov'):
                continue
            v = P[r.key]
            k_true, k_pred = lr.kind(r.place), lr.kind(v.get(int(r.floor), '') if isinstance(v, dict) else v)
            if k_true:
                c['connector_stops'] += 1
                c['predicted_same_kind'] += k_pred == k_true
                c['predicted_other_connector_kind'] += bool(k_pred) and k_pred != k_true
            else:
                c['other_stops'] += 1
                c['predicted_a_connector'] += bool(k_pred)
        rec[src] = dict(c)
    return {'what': 'per unit and gate source, with the true floors (eR0 frozen T): touches, how many were followed by a '
                    'real floor change within T, and how many real changes had the gate open. connector_recognition: '
                    'top-1 kind at every stop (pred_app asked on the true floor), all units and phones', 'units': out,
            'connector_recognition': rec}


# ----------------------------------------------------------------------------- decision
def decision(S):
    wrong = lambda u, r: {(w['time'], w['place']) for w in S[u]['rules'][r]['wrong_stops']}
    complete = ['25night_tian iphone', '26tian iphone', '25spots iphone']
    held = [u for u in S if S[u]['phase'] == 'held-out']
    out = {'what': 'PREREGISTRATION_landing.md decision rule', 'iphone': {}, 'no_pressure': {}, 'app': {}}
    cands = [f'{r}-{s}' for r in GATED for s in SOURCES]
    for c in cands:
        lost = {u: sorted(map(list, wrong(u, c) - wrong(u, 'R0'))) for u in complete}
        gain = S['25night iphone']['rules'][c]['stops_ok'] - S['25night iphone']['rules']['R0']['stops_ok']
        lost_any = {u: sorted(map(list, wrong(u, c) - wrong(u, 'R0'))) for u in held}
        out['iphone'][c] = {'R0_correct_stops_lost_where_pressure_complete': lost, 'gain_25night_ip18': gain,
                            'gain_over_d_25night_ip18': S['25night iphone']['rules'][c]['stops_ok'] - S['25night iphone']['rules']['d']['stops_ok'],
                            'recommended': not any(lost.values()) and gain > 0,
                            'R0_correct_stops_lost_any_heldout_unit': {u: v for u, v in lost_any.items() if v},
                            'heldout_iphone_stops_ok': sum(S[u]['rules'][c]['stops_ok'] for u in held if u.endswith('iphone'))}
    tun = ['24s1 a55', '24s1 a56', '25nov a55', '25nov a56', '24s1 s24', '24s2 s24']
    for c in [f'ed-{s}' for s in SOURCES]:
        h = (S['25night a56']['rules'][c]['stops_ok'], S['25night a56']['rules']['R0']['stops_ok'])
        t = (sum(S[u]['rules'][c]['stops_ok'] for u in tun), sum(S[u]['rules']['R0']['stops_ok'] for u in tun),
             sum(S[u]['rules'][c]['stops_n'] for u in tun))
        out['no_pressure'][c] = {'held_out_25night_a56': f'{h[0]} vs kept floor {h[1]} of 32',
                                 'tuning_a55_a56_s24_sum': f'{t[0]} vs kept floor {t[1]} of {t[2]}', 'recommended': h[0] > h[1] and t[0] > t[1]}
    ok = [c for c in ('eR0-pred_app', 'eR0n-pred_app') if out['iphone'][c]['recommended'] and not out['iphone'][c]['R0_correct_stops_lost_any_heldout_unit']]
    pick = max(ok, key=lambda c: (out['iphone'][c]['heldout_iphone_stops_ok'], c == 'eR0-pred_app')) if ok else None
    out['app'] = {'eligible': ['eR0-pred_app', 'eR0n-pred_app'], 'passing': ok, 'wire': pick,
                  'ed_pred_app_passes_but_not_wired': out['iphone']['ed-pred_app']['recommended'] and
                  not out['iphone']['ed-pred_app']['R0_correct_stops_lost_any_heldout_unit']}
    return out


# ----------------------------------------------------------------------------- main
def main():
    R = fl.recordings()
    preds = {'pred_d3': pred_d3(), 'pred_app': pred_app(R)}
    stop_keys = set(R.loc[R['type'] == 'stop', 'key'])
    cover = {s: f'{len(stop_keys & set(p))}/{len(stop_keys)}' for s, p in preds.items()}
    print('prediction coverage of stops', cover)
    # sanity: the gated code with the gate always open must equal the ungated rules
    for sid, slot, rows in cand.units(R, fl.SESSIONS):
        sf = int(rows['floor'].iloc[0])
        assert (lr.er0(rows, sf, lr.Gate()) == rules.r0(rows, sf)).all(), (sid, slot)
        v = rules.mag_votes(sid, rows['device'].iloc[0], D_PRM['k_d'], fl.SESSIONS)[0]
        assert (lr.ed(rows, sf, v, D_PRM['P'], D_PRM['H'], D_PRM['M'], lr.Gate(), use_pressure=slot == 'iphone') ==
                rules.comb(rows, sf, v, D_PRM['P'], D_PRM['H'], D_PRM['M'], use_pressure=slot == 'iphone')).all(), (sid, slot)
        if slot in ('iphone', 's24') and cand.has_pressure(rows):
            thr = rules.r1_threshold(fl.day3()['V'], sid, slot)
            assert (lr.er1(rows, sf, thr, lr.Gate()) == rules.r1(rows, sf, thr)).all(), (sid, slot)
    tuning, params = tune(R, preds)
    (fl.OUT / 'landing_tuning.json').write_text(json.dumps(tuning, indent=1))
    (fl.OUT / 'landing_params.json').write_text(json.dumps({'frozen_from': 'tuning sessions ' + ', '.join(fl.TUNING),
                                                              'd_params_entry74': D_PRM, **params}, indent=1))
    print('params', params)
    S, table = {}, []
    all_rules = list(BASE) + [f'{r}-{s}' for r in GATED for s in SOURCES]
    for phase, sessions, pool in (('tuning', fl.TUNING, fl.TUNING), ('held-out', fl.HELDOUT, fl.SESSIONS)):
        for sid, slot, rows in cand.units(R, sessions):
            variants = [('', rows)] + ([(' masked', cand.masked(rows)[0])] if phase == 'tuning' and slot == 'iphone' else [])
            for tag, rr in variants:
                u = f'{sid} {slot}{tag}'
                S[u] = {'phase': phase, 'session': sid, 'slot': slot, 'handset': rr['handset'].iloc[0],
                        'pressure_recordings': f"{int(rr['p0'].notna().sum())}/{len(rr)}", 'rules': {}}
                row = {'unit': u, 'phase': phase, 'handset': rr['handset'].iloc[0], 'pressure': S[u]['pressure_recordings']}
                for c in all_rules:
                    if c in BASE:
                        pred = run(c, rr, sid, slot, {}, pool)
                    else:
                        rule, src = c.split('-', 1)
                        pred = run(rule, rr, sid, slot, params[c], pool, src, preds)
                    s = cand.score(rr, pred)
                    S[u]['rules'][c] = s
                    row[f'{c} stops'], row[f'{c} walks'] = s['stops'], s['walks']
                table.append(row)
    (fl.OUT / 'landing_scores.json').write_text(json.dumps({'params': params, 'units': S}, indent=1))
    T = pd.DataFrame(table)
    T.to_csv(fl.OUT / 'landing_table.csv', index=False)
    show = ['unit'] + [f'{c} stops' for c in ['R0', 'R1', 'd', 'eR0-true', 'eR0-pred_d3', 'eR0-pred_app', 'eR0n-true',
                                               'eR0n-pred_app', 'eR1-true', 'eR1-pred_app', 'ed-true', 'ed-pred_d3', 'ed-pred_app']]
    print(T[show].to_string(index=False))
    (fl.OUT / 'transitions.json').write_text(json.dumps(transitions(R, preds, params), indent=1))
    (fl.OUT / 'landing_gate_stats.json').write_text(json.dumps(gate_stats(R, preds, params), indent=1))
    dec = decision(S)
    (fl.OUT / 'landing_decision.json').write_text(json.dumps(dec, indent=1))
    print(json.dumps(dec['app'], indent=1))
    figures(R, S, params, preds)


def figures(R, S, params, preds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cols = ['R0', 'R1', 'd'] + [f'{r}-{s}' for r in GATED for s in SOURCES]
    U = list(S)
    A = np.array([[S[u]['rules'][c]['stops_ok'] / max(1, S[u]['rules'][c]['stops_n']) for c in cols] for u in U])
    fig, ax = plt.subplots(figsize=(12, 0.3 * len(U) + 1.6), dpi=110)
    ax.imshow(A, cmap='Greens', vmin=0.3, vmax=1, aspect='auto')
    for i, u in enumerate(U):
        for j, c in enumerate(cols):
            ax.text(j, i, S[u]['rules'][c]['stops'], ha='center', va='center', fontsize=6)
    ax.set_xticks(range(len(cols)), cols, fontsize=7, rotation=45, ha='left')
    ax.set_yticks(range(len(U)), [f"{u} ({S[u]['handset']})" for u in U], fontsize=7)
    ax.xaxis.tick_top()
    ax.axhline(sum(S[u]['phase'] == 'tuning' for u in U) - 0.5, color='k', lw=1)
    ax.set_title('Stops on the right floor: current rules, (d), and connector-gated rules (tuning units first, then held-out)', fontsize=9, pad=40)
    fig.tight_layout(); fig.savefig(fl.OUT / 'fig_landing_scores.png'); plt.close(fig)
    # 25-night ip18 timeline with touches per source
    rows = R[(R['session'] == '25night') & (R['slot'] == 'iphone')].reset_index(drop=True)
    h = rows['start'] / 3600
    fig, axs = plt.subplots(2, 1, figsize=(9, 5), dpi=110, sharex=True, gridspec_kw={'height_ratios': [1.6, 1.6]})
    ok = rows['p0'].notna()
    axs[0].scatter(h[ok], rows.loc[ok, 'pmed'], c=['tab:blue' if f == 5 else 'tab:orange' for f in rows.loc[ok, 'floor']], s=10)
    for x in h[~ok]:
        axs[0].axvline(x, color='0.88', lw=0.8, zorder=0)
    for k, (src, c) in enumerate((('true', 'k'), ('pred_d3', 'tab:purple'), ('pred_app', 'tab:green'))):
        fr = rows['floor'].to_numpy()
        for j, kk in touches(rows, src, preds, np.r_[fr[0], fr[:-1]]):
            axs[0].plot(h[j], 1018.2 - 0.12 * k, marker='v', color=c, ms=4)
        axs[0].text(h.iloc[0], 1018.2 - 0.12 * k, f'  touches: {src}', fontsize=6, va='center', color=c)
    axs[0].set_ylabel('ip18 pressure (hPa)', fontsize=8)
    axs[0].set_title('25 Nov night, Dicta ip18: pressure (blue 5F, orange 4F; grey = no pressure) and connector touches', fontsize=8)
    lines = [('true', rows['floor'].to_numpy(), 'k', 0), ('R0', run('R0', rows, '25night', 'iphone', {}, fl.SESSIONS), 'C0', 0.05),
             ('(d)', run('d', rows, '25night', 'iphone', {}, fl.SESSIONS), 'C1', 0.10)]
    for k, c in enumerate(('eR0-pred_app', 'ed-true', 'ed-pred_app')):
        rule, src = c.split('-', 1)
        lines.append((c, run(rule, rows, '25night', 'iphone', params[c], fl.SESSIONS, src, preds), f'C{k + 2}', 0.05 * (k + 3)))
    for lab, y, c, off in lines:
        axs[1].step(h, y - off, where='post', color=c, label=lab, lw=1.2)
    axs[1].set_yticks([4, 5], ['4F', '5F']); axs[1].legend(fontsize=6, ncol=3, loc='center right')
    axs[1].set_xlabel('hour (after midnight > 24)', fontsize=8)
    fig.tight_layout(); fig.savefig(fl.OUT / 'fig_landing_25night.png'); plt.close(fig)


if __name__ == '__main__':
    main()
