"""Replay a recorded 24-Nov session through Tian's live code, with a continuous estimate logged every tick.

Tian's files in ../upload/ (live.py, walksense.py, route.py) are imported and NOT modified.
ContTracker subclasses live.LiveTracker: super().update() runs Tian's rules exactly as in the app
(standing/walking, place after 3 s still, floor once per stop); after it, once per tick of phone
time, the continuous estimate (smooth.Continuous) is computed from the same buffers and logged.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

UPLOAD = Path(__file__).resolve().parent.parent / 'upload'
sys.path.insert(0, str(UPLOAD))
import live            # noqa: E402  (Tian's live mode, unchanged)
import walksense as ws  # noqa: E402

import smooth          # noqa: E402

DEVICE_OF = {'sesi1': 'iPhone19,2', 'sesi2': 'iPhone17,4'}


def stream_segments(session):
    """Same stream as live._stream (one session's iPhone recordings end to end on the real clock),
    plus every recording as a segment: {'type', 'floor', 'place' (stop) or 'from'/'to' (walk), 't0', 't1'}."""
    rows = sorted((r for r in ws.manifest(session) if r['phone'] == 'iphone'), key=lambda r: ws.hk_epoch(r['start_hk']))
    t_first, parts, segs, prev_end = ws.hk_epoch(rows[0]['start_hk']), {s: [] for s in live.SENSORS}, [], -1.0
    for r in rows:
        rec = ws.read_folder(ws.DATA / session / 'clean' / r['folder'] / 'iphone', r['device'])
        start = min(rec[s][0, 0] for s in live.SENSORS)
        t0 = max(ws.hk_epoch(r['start_hk']) - t_first, prev_end + 0.5)     # as live._stream
        prev_end = t0 + max(rec[s][-1, 0] for s in live.SENSORS) - start
        for s in live.SENSORS:
            a = rec[s].copy(); a[:, 0] += t0 - start; parts[s].append(a)
        seg = {'type': r['type'], 'floor': int(r['floor']), 't0': t0, 't1': prev_end}
        if r['type'] == 'stop':
            seg['place'] = ws.MERGE.get(r['node'], r['node'])
        else:
            seg['from'], seg['to'] = (ws.MERGE.get(r[k], r[k]) for k in ('from_node', 'to_node'))
        segs.append(seg)
    return {s: np.vstack(parts[s]) for s in live.SENSORS}, segs, int(rows[0]['floor'])


class ContTracker(live.LiveTracker):
    """Tian's LiveTracker unchanged, plus a continuous estimate every cfg.tick s of phone time."""

    def __init__(self, models, device, floor, graph, cfg: smooth.Config):
        super().__init__(models, device, floor, graph=graph)
        self.cfg, self.cont = cfg, smooth.Continuous(cfg, graph)
        self.tick_k, self.walk_ref, self.steps_ref, self.ticks, self.tick_ms = None, None, 0, [], []

    def update(self):
        st = super().update()
        acc = self.data['acc']
        if len(acc) < 50:
            return st
        now = float(acc[-1, 0])
        k = int(np.floor(now / self.cfg.tick + 1e-9))
        if k == self.tick_k:
            return st
        self.tick_k = k
        t_cpu = time.perf_counter()
        recent = acc[acc[:, 0] >= now - live.MOTION_S]
        moving = bool(np.linalg.norm(recent[:, 1:4], axis=1).std() >= live.STILL_STD)   # Tian's still test, recomputed
        still, tilt = smooth.still_flat(acc, now)
        steps = st.get('steps', 0) if self.walk_since is not None else 0
        dsteps = steps if self.walk_since != self.walk_ref else max(0, steps - self.steps_ref)
        self.walk_ref, self.steps_ref = self.walk_since, steps
        floor = self.session.floor
        m = self.model.models.get(floor)
        p = None
        if m is not None:
            f = smooth.window_feature(self.data['mag'], now, self.cfg.window, self.cfg.prefilter, self.cfg.shift)
            if f is not None:
                p = m.predict_proba(f[None, :])[0]
        est = self.cont.step(floor, list(m.classes_) if m is not None else [], p, dsteps,
                             smooth.gate_open(self.cfg.gate, still, tilt)) if m is not None else {'place': None, 'raw_place': None, 'prob': 0.0, 'top3': []}
        lit = est['place'] if est['place'] and not moving and est['prob'] >= ws.LIGHT_P else None
        self.tick_ms.append((time.perf_counter() - t_cpu) * 1000)
        self.ticks.append({'t': now, 'floor': floor, 'moving': moving, 'still': still, 'tilt': tilt, 'dsteps': dsteps,
                           'base_top3': [q for q, _ in st['top3']], 'base_lit': st['lit'] if st['mode'] == 'stop' else None,
                           'place': est['raw_place'], 'shown': est['place'], 'prob': est['prob'],
                           'top3': tuple(q for q, _ in est['top3']), 'lit': lit})
        return st


def replay(session, cfg, models, graph, device=None):
    """Stream a session through ContTracker in live.POLL_S steps (as live.replay) -> stream, segments, tick log, ms/tick."""
    stream, segs, floor = stream_segments(session)
    tr = ContTracker(models, device or DEVICE_OF[session], floor, graph, cfg)
    end = max(a[-1, 0] for a in stream.values())
    idx = {s: 0 for s in stream}
    for t in np.arange(0, end + 1, live.POLL_S):
        chunk = {}
        for s, a in stream.items():
            j = np.searchsorted(a[:, 0], t, side='right')
            if j > idx[s]:
                chunk[s] = a[idx[s]:j]; idx[s] = j
        if chunk:
            tr.add(chunk)
            tr.update()
    return stream, segs, tr.ticks, tr.tick_ms
