"""Connector-gated floor rules (PREREGISTRATION_landing.md, committed 0e8ef6a before any of these was run).

A floor change can only happen through a connector, so a floor switch is allowed only while the gate is open:
some recording j <= i touched a connector (lift / down escalator / up escalator) whose direction allows
current floor -> other floor, and start(i) - start(j) <= T. Gate sources: 'true' (true place names, stops and walk
endpoints), 'pred_d3' (day-3 leave-one-session-out fused kNN top-1, stops only), 'pred_app' (the upload app's own
PlaceModel top-1 among the places of the floor the tracker shows before the recording, stops only).
"""
from __future__ import annotations

import numpy as np

import floorlib as fl
import rules

ws = fl.ws
_p = rules._p
ALLOWS = {'lift': {(5, 4), (4, 5)}, 'down': {(5, 4)}, 'up': {(4, 5)}}   # graph.json: escalators are one-way


def kind(place: str):
    """Connector kind of a place name, floor-agnostic (PREREGISTRATION_landing.md 'Connectors')."""
    p = str(place)
    if p.startswith('lift'):
        return 'lift'
    if p.startswith('esca'):
        return 'down' if 'down' in p else 'up' if 'up' in p else None
    return None


class Gate:
    """source None = always open (the ungated rule). pred = {window key -> place} (pred_d3) or
    {window key -> {floor -> place}} (pred_app, asked on the floor shown before the recording)."""

    def __init__(self, source=None, T=None, pred=None):
        self.source, self.T, self.pred, self.touches = source, T, pred or {}, []

    def observe(self, r, floor):
        if self.source is None:
            return
        names = []
        if self.source == 'true':
            names = r.place.split('->')
        elif r.type == 'stop' and r.key in self.pred:
            v = self.pred[r.key]
            names = [v.get(floor, '') if isinstance(v, dict) else v]
        ks = {k for k in map(kind, names) if k}
        if ks:
            self.touches.append((r.start, ks))

    def open(self, t, cur, to):
        if self.source is None:
            return True
        return any(t - tj <= self.T and (cur, to) in ALLOWS[k] for tj, ks in self.touches for k in ks)


# ----------------------------------------------------------------------------- eR0 / eR0n
def er0(rows, start_floor, gate, theta=ws.FLOOR_JUMP_HPA, reset=True, use_pressure=True):
    """walksense.Session.track_floor with the gate: a jump switches only if the gate is open; otherwise the reading
    joins the reference and the floor is kept. reset=False drops the 15-min reset (eR0n)."""
    F, recent, last_t, out = start_floor, [], None, []
    for r in rows.itertuples():
        gate.observe(r, F)
        p0, p1 = (_p(r.p0), _p(r.p1)) if use_pressure else (None, None)
        if p0 is not None:
            if reset and recent and last_t is not None and r.start - last_t > ws.LONG_GAP_S:
                recent = []
            for p in (p0, p1):
                if recent:
                    d = p - float(np.median(recent))
                    if d > theta and F == 5 and gate.open(r.start, 5, 4):
                        F, recent = 4, []
                    elif d < -theta and F == 4 and gate.open(r.start, 4, 5):
                        F, recent = 5, []
                recent = (recent + [p])[-ws.REF_N:]
            last_t = r.start + r.dur
        out.append(F)
    return np.array(out)


# ----------------------------------------------------------------------------- eR1
def er1(rows, start_floor, thr, gate):
    """day-3 data.track_floor on the stop medians, a step switches only if the gate is open at that stop."""
    F, prev, out = start_floor, None, []
    for r in rows.itertuples():
        gate.observe(r, F)
        if r.type == 'stop':
            h = _p(r.pmed)
            if h is not None and np.isfinite(h):
                if prev is not None:
                    if h - prev > thr and F == 5 and gate.open(r.start, 5, 4):
                        F = 4
                    elif prev - h > thr and F == 4 and gate.open(r.start, 4, 5):
                        F = 5
                prev = h
        out.append(F)
    return np.array(out)


# ----------------------------------------------------------------------------- ed = (d) with the gate
def ed(rows, start_floor, votes, P, H, M, gate, use_pressure=True, long_gap_s=ws.LONG_GAP_S):
    """rules.comb (pressure = R0, magnetic vote at stops without pressure / first M stops after a long gap,
    H confident votes in a row switch) where both kinds of switch need the gate open; closed-gate votes are ignored."""
    F, recent, last_t = start_floor, [], None
    streak_f, streak, consult_left, out = None, 0, 0, []
    for r in rows.itertuples():
        gate.observe(r, F)
        p0, p1 = (_p(r.p0), _p(r.p1)) if use_pressure else (None, None)
        has_p = p0 is not None
        if has_p:
            if last_t is not None and r.start - last_t > long_gap_s:
                consult_left = M
            before = F
            if recent and last_t is not None and r.start - last_t > ws.LONG_GAP_S:
                recent = []
            for p in (p0, p1):
                if recent:
                    d = p - float(np.median(recent))
                    if d > ws.FLOOR_JUMP_HPA and F == 5 and gate.open(r.start, 5, 4):
                        F, recent = 4, []
                    elif d < -ws.FLOOR_JUMP_HPA and F == 4 and gate.open(r.start, 4, 5):
                        F, recent = 5, []
                recent = (recent + [p])[-ws.REF_N:]
            last_t = r.start + r.dur
            if F != before:
                streak, consult_left = 0, 0
        consult = (not has_p) or consult_left > 0
        if r.type == 'stop' and consult and r.key in votes:
            f, pf = votes[r.key]
            if pf >= P and f != F:
                if gate.open(r.start, F, f):
                    streak = streak + 1 if streak_f == f else 1
                    streak_f = f
                    if streak >= H:
                        F = f
                        recent = [p0, p1] if has_p else []
                        streak, consult_left = 0, 0
            elif pf >= P:
                streak = 0
        if has_p and r.type == 'stop' and consult_left > 0:
            consult_left -= 1
        out.append(F)
    return np.array(out)
