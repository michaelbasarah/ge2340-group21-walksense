#!/usr/bin/env python3
"""Floor rule (d) re-checked with the APP's features (PROCESS-LOG entry 90).

Entry 74 chose rule (d) with a magnetic floor vote on the day-3 5 s windows (floor/rules.py mag_votes). The app votes on
its own 2 s windows, first/last 5 s trimmed (walksense.FloorVote). This script scores the frozen (d) (k 15, P 0.7, H 2,
M 3; floor/out/params.json) both ways on the same units and applies the decision rule of floor/PREREGISTRATION.md
again, so we know whether (d) still passes with what the app actually computes.

  python floor_rule_check.py        # ~1 min; needs the day-3 feature cache (day3/data.py) -> out/floor_rule_check.json

Vote pools (same device model, all models if none; the test session is never in its own pool):
  d3        = floor/rules.py mag_votes as in entry 74 (tuning units: other tuning sessions; held-out: all other sessions)
  app_prereg = app features, the same pools as d3 minus 23 Nov (its tree has no per-recording folders the app can read)
  app       = app features, the app's own pool: walksense.SESSIONS minus the test session minus TRAIN_EXCLUDE
              (= walksense.py evaluate floor_tracking_by_rule; checked here, `app_matches_eval_json`)
floor/ is imported read-only (rules.comb runs the rule; the app's Session.update_floor must give the same floors).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'floor'))
import floorlib as fl          # noqa: E402
import rules                   # noqa: E402
import candidates as cand      # noqa: E402
import walksense as ws         # noqa: E402

PRM = json.loads((fl.OUT / 'params.json').read_text())
APP_NAME = fl.UPLOAD_NAME                  # day-3 id -> app session name
D3_NAME = {v: k for k, v in APP_NAME.items()}
APP_LOADABLE = [s for s in fl.SESSIONS if s != '23nov']
_REC = {}


def roots():
    cfg = {s['id']: s for s in fl.d3.config()['sessions']}
    return {sid: (fl.d3.HERE / cfg[sid]['path']).resolve() for sid in APP_LOADABLE}


def rec_of(root, r):
    k = (r.session, r.folder, r.slot)
    if k not in _REC:
        _REC[k] = ws.read_folder(root[r.session] / r.folder / r.slot, r.device)
    return _REC[k]


def stops_of(R, root, sessions):
    S = R[(R['type'] == 'stop') & R['session'].isin(sessions)]
    return [{'session': r.session, 'floor': int(r.floor), 'device': r.device, 'rec': rec_of(root, r)} for r in S.itertuples()]


def app_votes(R, root, rows, sid, pool_stops):
    dev = rows['device'].iloc[0]
    pool = [x for x in pool_stops if x['session'] != sid]
    same = [x for x in pool if x['device'] == dev]
    fv = ws.FloorVote(same or pool, k=PRM['k_d'])
    out = {}
    for r in rows.itertuples():
        if r.type == 'stop':
            v = fv.vote(rec_of(root, r))
            if v is not None:
                out[r.key] = v
    return out, 'same model' if same else 'all models'


_APP_STOPS = {}


def app_session_votes(rows, sid, root):
    """Pool exactly as walksense.floor_votes (app manifests, TRAIN_EXCLUDE out)."""
    name = APP_NAME.get(sid)
    if not _APP_STOPS:
        _APP_STOPS.update({(s, ph): ws.training_stops(sessions=(s,), phone=ph) for s in ws.SESSIONS for ph in ('iphone', 's24', 'a55', 'a56')})
    stops = _APP_STOPS
    fv, pool = ws.floor_votes(stops, name, rows['device'].iloc[0])
    return {r.key: fv.vote(rec_of(root, r)) for r in rows.itertuples() if r.type == 'stop'}, pool


def main():
    R = fl.recordings()
    root = roots()
    tun_stops = stops_of(R, root, [s for s in fl.TUNING if s != '23nov'])
    all_stops = stops_of(R, root, APP_LOADABLE)
    _app_cache = {}
    units, table = {}, []
    for phase, sessions, d3pool in (('tuning', fl.TUNING, fl.TUNING), ('held-out', fl.HELDOUT, fl.SESSIONS)):
        for sid, slot, rows in cand.units(R, sessions):
            variants = [('', rows)] + ([(' masked', cand.masked(rows)[0])] if phase == 'tuning' and slot == 'iphone' else [])
            dev = rows['device'].iloc[0]
            sf = int(rows['floor'].iloc[0])
            up = slot == 'iphone'                      # (d): S24 barometer treated as absent; a55/a56 have none
            votes = {'d3': rules.mag_votes(sid, dev, PRM['k_d'], d3pool)}
            if sid != '23nov':
                votes['app_prereg'] = app_votes(R, root, rows, sid, tun_stops if phase == 'tuning' else all_stops)
                if sid in APP_NAME:
                    if (sid, slot) not in _app_cache:
                        _app_cache[(sid, slot)] = app_session_votes(rows, sid, root)
                    votes['app'] = _app_cache[(sid, slot)]
            for tag, rr in variants:
                u = f'{sid} {slot}{tag}'
                res = {'phase': phase, 'handset': rr['handset'].iloc[0],
                       'pressure_recordings': f"{int(rr['p0'].notna().sum())}/{len(rr)}", 'rules': {}}
                res['rules']['R0'] = cand.score(rr, rules.r0(rr, sf))
                for vk, (v, pool) in votes.items():
                    res['rules'][f'd_{vk}'] = cand.score(rr, rules.comb(rr, sf, v, PRM['P'], PRM['H'], PRM['M'], use_pressure=up))
                    res['rules'][f'd_{vk}']['vote_pool'] = pool
                    res['rules'][f'd_{vk}']['vote_agree_with_d3'] = None if vk == 'd3' else \
                        f"{sum(v.get(k, (None,))[0] == votes['d3'][0][k][0] for k in votes['d3'][0])}/{len(votes['d3'][0])}"
                units[u] = res
                table.append({'unit': u, 'phase': phase, 'handset': res['handset'], 'pressure': res['pressure_recordings'],
                              **{k: f"{v['stops']} ({v['walks']})" for k, v in res['rules'].items()}})
    # decision rule (PREREGISTRATION.md), per vote version
    decision = {}
    for vk in ('d3', 'app_prereg', 'app'):
        r = f'd_{vk}'
        wrong = lambda u, rr: {(w['time'], w['place']) for w in units[u]['rules'][rr]['wrong_stops']}
        complete = ['25night_tian iphone', '26tian iphone', '25spots iphone']
        lost = {u: sorted(map(list, wrong(u, r) - wrong(u, 'R0'))) for u in complete if r in units[u]['rules']}
        gain = units['25night iphone']['rules'][r]['stops_ok'] - units['25night iphone']['rules']['R0']['stops_ok']
        d = {'iphone': {'R0_correct_stops_lost_where_pressure_complete': lost, 'gain_25night_ip18': gain,
                        'units_checked': sorted(lost),
                        'recommended': (not any(lost.values()) and gain > 0) if len(lost) == 3 else
                        'n/a: 25spots is not an app session, so the app pool cannot score all three units'}}
        tun = [u for u in ('24s1 a55', '24s1 a56', '25nov a55', '25nov a56', '24s1 s24', '24s2 s24') if r in units[u]['rules']]
        held = (units['25night a56']['rules'][r]['stops_ok'], units['25night a56']['rules']['R0']['stops_ok'])
        t = [sum(units[u]['rules'][k]['stops_ok'] for u in tun) for k in (r, 'R0')] + [sum(units[u]['rules'][r]['stops_n'] for u in tun)]
        d['no_pressure'] = {'held_out_25night_a56': f'{held[0]} vs kept floor {held[1]} of 32',
                            'tuning_a55_a56_s24_sum': f'{t[0]} vs kept floor {t[1]} of {t[2]}',
                            'recommended': held[0] > held[1] and t[0] > t[1]}
        if vk == 'app':
            d['note'] = ('app pool includes held-out sessions when a tuning unit is tested (the app trains on everything it has), '
                         'so its tuning rows are not the pre-registered tuning numbers; held-out rows are comparable')
        decision[vk] = d
    # the app's own Session(rule d) in walksense.evaluate must give what rules.comb gives with the same votes
    ev = json.loads(ws.out_file('eval').read_text()).get('floor_tracking_by_rule', {})
    match = {}
    for u, res in units.items():
        sid, slot = u.split(' ')[0], u.split(' ')[1]
        if ' masked' in u or sid not in APP_NAME or 'd_app' not in res['rules']:
            continue
        e = ev.get(f'{APP_NAME[sid]} {slot}')
        if e:
            match[u] = {'rules_comb': res['rules']['d_app']['stops'], 'eval_json': e['d']['stops'],
                        'R0_floorlib': res['rules']['R0']['stops'], 'R0_eval_json': e['R0']['stops']}
    out = {'what': __doc__.strip().split('\n\n')[0], 'params': PRM, 'decision': decision,
           'app_matches_eval_json': all(m['rules_comb'] == m['eval_json'] and m['R0_floorlib'] == m['R0_eval_json'] for m in match.values()),
           'app_vs_eval_json': match, 'table': table, 'units': units}
    ws.OUT.mkdir(exist_ok=True)
    (ws.OUT / 'floor_rule_check.json').write_text(json.dumps(out, indent=1))
    for row in table:
        print(f"{row['unit']:28} {row['pressure']:>6}  " + '  '.join(f"{k} {v}" for k, v in row.items() if k.startswith(('R0', 'd_'))))
    print(json.dumps(decision, indent=1))
    print('app matches eval.json:', out['app_matches_eval_json'])


if __name__ == '__main__':
    main()
