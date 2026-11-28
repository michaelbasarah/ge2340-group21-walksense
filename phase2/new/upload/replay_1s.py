#!/usr/bin/env python3
"""Live replay of every iPhone session, old live rules vs the 1 s rules (PROCESS-LOG entry 96).

    python replay_1s.py      -> out/live_1s_replay.json   (a few minutes)

Each session's iPhone recordings stream through live.LiveTracker in 0.5 s steps, pressure 4 s late (as the real
iPhone, entry 28). The place model is held out: the same phone model, trained on its OTHER sessions only.
Rules compared (decision rule written before scoring: keep walking-floor only if floor-at-stops is >= without it on
every session):
  old        MOTION_S 3, guess at 3 s, floor checked at the first look (no wait), no walking floor
  1s         MOTION_S 1, guess at 1 s, lit from 3 s, 1 s motion to end a stop, floor waits for pressure, no walking floor
  1s+walk    1s plus the walking floor change (5 s pressure median 0.40 hPa off for 5 s)
"""
import json

import live
import walksense as ws

RULES = {'old': dict(MOTION_S=3.0, NAME_AFTER_S=3.0, LIT_AFTER_S=0.0, WALK_CONFIRM_S=0.0, BARO_WAIT_S=0.0, WALK_FLOOR=False),
         '1s': dict(MOTION_S=1.0, NAME_AFTER_S=1.0, LIT_AFTER_S=3.0, WALK_CONFIRM_S=1.0, BARO_WAIT_S=8.0, WALK_FLOOR=False),
         '1s+walk': dict(MOTION_S=1.0, NAME_AFTER_S=1.0, LIT_AFTER_S=3.0, WALK_CONFIRM_S=1.0, BARO_WAIT_S=8.0, WALK_FLOOR=True)}
LAG = 4.0


def main():
    by_dev = {}
    for s in ws.SESSIONS:
        devs = {r['device'] for r in ws.manifest(s) if r['phone'] == 'iphone'}
        if len(devs) == 1:
            by_dev.setdefault(devs.pop(), []).append(s)
    out = {'what': __doc__.strip().splitlines()[0], 'baro_lag_s': LAG, 'rules': RULES, 'sessions': {}}
    for dev, sessions in sorted(by_dev.items()):
        for s in sessions:
            others = [o for o in sessions if o != s]
            if not others:
                continue
            model = {dev: ws.PlaceModel(ws.training_stops(device=dev, sessions=others, exclude=ws.TRAIN_EXCLUDE))}
            row = {'device': dev, 'trained_on': others}
            for name, rule in RULES.items():
                for k, v in rule.items():
                    setattr(live, k, v)
                row[name] = live.replay(s, dev, model, baro_lag=LAG)
            out['sessions'][s] = row
            print(s, dev, {n: {k: row[n][k] for k in ('n_stops', 'found', 'floor', 'first_top1', 'top1', 'lit', 'lit_right', 'extra_stops')}
                           for n in RULES})
    keep = all(r['1s+walk']['floor'] >= r['1s']['floor'] for r in out['sessions'].values())
    out['walking_floor_kept'] = keep
    tot = lambda n, k: sum(r[n][k] for r in out['sessions'].values())
    out['totals'] = {n: {k: tot(n, k) for k in ('n_stops', 'found', 'floor', 'first_top1', 'top1', 'top3', 'lit', 'lit_right', 'extra_stops')}
                     for n in RULES}
    ws.OUT.mkdir(exist_ok=True)
    (ws.OUT / 'live_1s_replay.json').write_text(json.dumps(out, indent=1))
    print(json.dumps({'totals': out['totals'], 'walking_floor_kept': keep}, indent=1))


if __name__ == '__main__':
    main()
