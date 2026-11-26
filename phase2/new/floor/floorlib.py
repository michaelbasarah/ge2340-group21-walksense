"""Shared data layer for the floor-rule study (PROCESS-LOG entry 76). Read-only use of upload/ and day3/.

One table of RECORDINGS (every stop and walk of every phone slot, in time order per session and slot):
  session, slot (iphone / s24 / a55 / a56), device, handset, type, floor (label), place, start (s), dur (s),
  p0 / p1 (edge pressure, upload/walksense.py edge_pressure: median of the first / last 3 s), pmed (median),
  key (day-3 window key '<session>:<folder>:<slot>', for the magnetic vote).
23 Nov comes from the day-3 visit table (stops only, ip16 pressure median per stop; no walks).
Magnetic windows (5 s, x/y/z mean) come from the day-3 feature table (day3/data.py load()).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEW = HERE.parent
OUT = HERE / 'out'
sys.path.insert(0, str(NEW / 'day3'))
sys.path.insert(0, str(NEW / 'upload'))
import data as d3                      # noqa: E402  (day-3 data layer, read-only)
import walksense as ws                 # noqa: E402  (upload app, read-only: Session, edge_pressure, hk_epoch, _table)

TUNING = ['23nov', '24s1', '24s2', '25nov']
HELDOUT = ['25night', '25night_tian', '26tian', '25spots']
SESSIONS = TUNING + HELDOUT
PRESSURE_FILES = ('Barometer.csv', 'Pressure.csv')
# day-3 session id -> upload app session name (for the eval.json reproduction)
UPLOAD_NAME = {'24s1': 'sesi1', '24s2': 'sesi2', '25nov': '25nov', '25night': '25night',
               '25night_tian': '25night_tian', '26tian': '26tian'}

_D = None


def day3():
    global _D
    if _D is None:
        _D = d3.load()
    return _D


def _pressure(folder: Path):
    for n in PRESSURE_FILES:
        f = folder / n
        if f.exists():
            a = ws._table(f.read_text(encoding='utf-8'))
            if len(a) >= 2:
                return a
    return None


def recordings() -> pd.DataFrame:
    cfg = {s['id']: s for s in d3.config()['sessions']}
    rows = []
    for sid in SESSIONS:
        s = cfg[sid]
        if s['loader'] == 'crossday_23nov':
            V = day3()['V']
            for _, v in V[V['session'] == sid].iterrows():
                p = float(v['hpa_iphone'])
                rows.append({'session': sid, 'slot': 'iphone', 'device': v['devices'], 'handset': v['iphone_handset'],
                             'type': 'stop', 'floor': int(v['floor']), 'place': v['place'], 'start': float(v['start']),
                             'dur': float(v['end'] - v['start']), 'p0': p, 'p1': p, 'pmed': p,
                             'key': f"{v['visit']}:iphone", 'folder': v['visit'].split(':', 1)[1]})
            continue
        root = (d3.HERE / s['path']).resolve()
        m = pd.read_csv(root / 'manifest.csv', dtype=str).fillna('')
        ex = d3.excluded_sources(s)
        if ex:
            m = m[~m['source_zip'].isin(ex)]
        for _, r in m.iterrows():
            a = _pressure(root / r['folder'] / r['phone'])
            p0, p1 = ws.edge_pressure({'baro': a}) if a is not None else (None, None)
            rows.append({'session': sid, 'slot': r['phone'], 'device': r['device'], 'handset': d3.handset(r['device']),
                         'type': r['type'], 'floor': int(r['floor']),
                         'place': r['node'] if r['type'] == 'stop' else f"{r['from_node']}->{r['to_node']}",
                         'start': float(ws.hk_epoch(r['start_hk'])), 'dur': float(r['duration_s']),
                         'p0': p0, 'p1': p1, 'pmed': None if a is None else float(np.median(a[:, 1])),
                         'key': f"{sid}:{r['folder']}:{r['phone']}", 'folder': r['folder'], 'start_hk': r['start_hk']})
    R = pd.DataFrame(rows)
    R = R.sort_values(['session', 'slot', 'start'], kind='stable').reset_index(drop=True)
    return R


def hhmm(sid, start):
    """Clock time of a recording start (23 Nov: epoch; others: seconds since midnight, after midnight > 24 h)."""
    if sid == '23nov':
        return pd.Timestamp(start, unit='s', tz='Asia/Hong_Kong').strftime('%H:%M')
    h, mi = int(start // 3600), int(start % 3600 // 60)
    return f'{h:02d}:{mi:02d}'
