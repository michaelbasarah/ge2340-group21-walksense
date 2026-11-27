#!/usr/bin/env python3
"""Step 1: reproduce the two current floor rules from their own code and check them against the committed outputs.

  R0 = upload app (upload/walksense.py Session.track_floor, 0.40 hPa vs the median of the last 6 edge readings,
       15-min gap rule), over every iPhone recording in time order  -> must equal upload/out/eval.json
       floor_tracking_by_rule[key]['R0']['stops'] (since entry 90 `floor_tracking` holds the app default, rule (d), so it
       is only the fallback for an eval.json without floor_tracking_by_rule)
  R1 = day-3 step tracking (day3/evaluate.py floor_eval)             -> must equal day3/out/results.json floor
Writes out/baseline.json. Exit code 1 if a number does not match.
"""
from __future__ import annotations

import json
import sys

import floorlib as fl
import rules

sys.path.insert(0, str(fl.NEW / 'day3'))
import evaluate as d3eval              # noqa: E402


def main():
    fl.OUT.mkdir(exist_ok=True)
    R = fl.recordings()
    eval_all = json.loads((fl.NEW / 'upload' / 'out' / 'eval.json').read_text())
    eval_json = eval_all['floor_tracking']                          # app default (rule d since entry 90): old-layout fallback only
    by_rule = eval_all.get('floor_tracking_by_rule', {})
    res_json = json.loads((fl.NEW / 'day3' / 'out' / 'results.json').read_text())['floor']
    out, ok = {'r0_upload': {}, 'r1_day3': {}}, True
    for sid, name in fl.UPLOAD_NAME.items():
        rows = R[(R['session'] == sid) & (R['slot'] == 'iphone')]
        pred = rules.r0(rows, int(rows['floor'].iloc[0]))
        st = (rows['type'] == 'stop').to_numpy()
        n, c = int(st.sum()), int((pred[st] == rows['floor'].to_numpy()[st]).sum())
        key = f'{name} iphone'
        want = by_rule[key]['R0']['stops'] if key in by_rule and 'R0' in by_rule[key] else eval_json[key]['stops_correct']
        out['r0_upload'][sid] = {'reproduced': f'{c}/{n}', 'eval_json': want, 'match': f'{c}/{n}' == want}
        ok &= f'{c}/{n}' == want
    got, _ = d3eval.floor_eval(fl.day3()['V'])
    for k, v in got.items():
        want = res_json[k]['step_tracking']
        out['r1_day3'][k] = {'reproduced': v['step_tracking'], 'results_json': want, 'threshold_hpa': v['jump_threshold_hpa'],
                             'match': v['step_tracking'] == want}
        ok &= v['step_tracking'] == want
    out['all_match'] = bool(ok)
    (fl.OUT / 'baseline.json').write_text(json.dumps(out, indent=1))
    for part in ('r0_upload', 'r1_day3'):
        for k, v in out[part].items():
            print(part, k, v['reproduced'], 'match' if v['match'] else 'MISMATCH')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
