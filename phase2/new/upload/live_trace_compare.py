#!/usr/bin/env python3
"""A real live capture through the old and the new LiveTracker, with the phone's pressure lag (PROCESS-LOG 95).

  git show <old commit>:phase2/new/upload/live.py > /tmp/live_old.py
  python live_trace_compare.py <capture folder or live ZIP> /tmp/live_old.py [start floor] [name]
      -> out/live_trace_<name>.json: per tracker the floor changes, the rides found in the pressure with the
         seconds from ride end to the floor change, and every stop (time, floor, first floor, top-3, floor note)
The place models are trained once (all sessions, as the server does) and shared by both trackers.
"""
import importlib.util
import json
import sys

import live
import walksense as ws


def main(src, old_path, floor=5, name='capture'):
    spec = importlib.util.spec_from_file_location('live_old', old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    models, res = ws.build_models(), {'source': str(src), 'old_tracker': old_path, 'baro_lag_s': live.PHONE_BARO_LAG_S}
    for key, cls in (('before', old.LiveTracker), ('after', live.LiveTracker)):
        keep = live.LiveTracker
        live.LiveTracker = cls                     # trace() builds live.LiveTracker
        try:
            res[key] = live.trace(src, floor, models=models)
        finally:
            live.LiveTracker = keep
        for r in res[key]['rides']:
            print(key, r['direction'], r['start'], '-', r['end'], 'latency', r['latency_after_ride_end_s'])
    (ws.OUT / f'live_trace_{name}.json').write_text(json.dumps(res, indent=1))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5, sys.argv[4] if len(sys.argv) > 4 else 'capture')
