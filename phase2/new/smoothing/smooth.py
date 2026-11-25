#!/usr/bin/env python3
"""Continuous place estimate for live mode: a kNN answer every tick, smoothed over time.

Every tick (DELTA s of phone time) the place kNN (walksense / crossday.make_model, the same
per-floor, same-phone-model models Tian's live mode uses) turns the mean magnetic x/y/z of the
last W s into class probabilities p_t. The estimators below turn the p_t sequence into the
place shown on the page:

  none   s_t = p_t                                   (control)
  fir    s_t = sum_i w_i p_(t-i), w_0 >= w_1 >= ... >= 0, sum w = 1   (the user's a, b, c)
  ema    s_t = alpha p_t + (1 - alpha) s_(t-1)       (w_i proportional to alpha (1 - alpha)^i)
  hmm    forward filter on the corridor graph: belief_t ~ (p_t + 0.001)^beta * T' belief_(t-1),
         T = stay / move to a neighbour (more likely the more steps were detected since the last
         tick) / teleport anywhere with eps
Options: a jump guard (the shown place may only move to a neighbour unless the new place stays on
top for M ticks), gating (feed the kNN only while the phone is still, or still and flat; while
gated the estimate is carried, for hmm only the step-driven transition runs), abstain (show
"not sure" when the top probability is below a threshold), a magnetometer pre-filter (drop samples
whose |B| jumps more than 5 uT from the rolling median of the previous 0.3 s), and a calibration
shift added to every feature (per-phone offset).
Tuned offline by tune.py on the recorded 24-Nov sessions (out/live_smoothing.json); not used by the app.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict

import numpy as np

STILL_STD = 0.4        # m/s^2, the same still threshold as live.py, here over 1 s
GATE_S = 1.0           # 1 s |acc| std < 0.4: 98.6% / 99.8% of stop seconds, 0% of walk seconds (live_smoothing.json 'gate_stats')
FLAT_DEG = 20.0        # phone flat = gravity within 20 deg of the phone's z axis (stop seconds p99: 12.3 / 11.8 deg)
PREF_MED_S = 0.3       # pre-filter: rolling median over the previous 0.3 s of |B|
PREF_JUMP_UT = 5.0     # ... samples more than 5 uT away are dropped (about the top 0.2% of samples on 24 Nov)
LIK_FLOOR = 1e-3       # hmm: kNN probability floor, so one zero cannot rule a place out for ever
MIN_MAG = 5            # fewer magnetometer samples in the window: no kNN answer this tick
METHODS = ('none', 'fir', 'ema', 'hmm')
GATES = ('none', 'still', 'still_flat')


@dataclass
class Config:
    tick: float = 0.5               # s between estimates
    window: float = 2.0             # s of magnetometer averaged per estimate
    method: str = 'fir'
    weights: tuple = (1.0,)         # fir
    alpha: float = 0.5              # ema
    guard: int = 0                  # jump guard M (0 = off)
    beta: float = 1.0               # hmm likelihood exponent
    eps: float = 0.01               # hmm teleport share per tick
    p_stay: float = 0.98            # hmm stay probability per tick while no steps
    gate: str = 'none'
    abstain: float = 0.0            # show "not sure" below this top probability (0 = never)
    prefilter: bool = False
    shift: tuple = (0.0, 0.0, 0.0)  # added to every feature (calibration)

    def __post_init__(self):
        if self.method not in METHODS or self.gate not in GATES:
            raise ValueError(f'method must be one of {METHODS}, gate one of {GATES}')
        if self.method == 'none':
            self.weights = (1.0,)
        w = np.asarray(self.weights, float)
        if self.method == 'fir' and (len(w) == 0 or (w < 0).any() or np.any(np.diff(w) > 1e-9) or w.sum() <= 0):
            raise ValueError('fir weights must be >= 0, non-increasing (a >= b >= c ...) and not all 0')
        self.weights = tuple(float(x) for x in w / w.sum())
        if not (0 < self.alpha <= 1 and self.tick > 0 and self.window > 0 and 0 <= self.eps < 1 and 0 < self.p_stay <= 1):
            raise ValueError('need 0 < alpha <= 1, tick > 0, window > 0, 0 <= eps < 1, 0 < p_stay <= 1')

    def label(self):
        m = {'none': 'none', 'fir': 'fir ' + ','.join(f'{x:.2f}' for x in self.weights), 'ema': f'ema a={self.alpha:g}',
             'hmm': f'hmm b={self.beta:g} e={self.eps:g} s={self.p_stay:g}'}[self.method]
        return (f'd={self.tick:g} W={self.window:g} {m}' + (f' guard{self.guard}' if self.guard else '') +
                (f' gate={self.gate}' if self.gate != 'none' else '') + (' pref' if self.prefilter else '') +
                (f' abstain<{self.abstain:g}' if self.abstain else ''))

    def as_dict(self):
        return asdict(self)


# ============================================================================ features
def window_feature(mag, now, window, prefilter=False, shift=None):
    """Mean magnetic x/y/z of the samples in (now - window, now]; None if too few samples."""
    if prefilter:
        i0 = np.searchsorted(mag[:, 0], now - window - PREF_MED_S, side='right')
        i1 = np.searchsorted(mag[:, 0], now, side='right')
        m = mag[i0:i1]
        if len(m) < MIN_MAG:
            return None
        b = np.linalg.norm(m[:, 1:4], axis=1)
        n = max(3, int(round(PREF_MED_S / max(np.median(np.diff(m[:, 0])), 1e-3))) if len(m) > 2 else 3)
        # trailing rolling median (sample itself included); the first n-1 samples use what exists
        med = _trailing_median(b, n) if len(b) >= n else np.full(len(b), np.median(b))
        m = m[(np.abs(b - med) <= PREF_JUMP_UT) & (m[:, 0] > now - window)]
    else:
        i0 = np.searchsorted(mag[:, 0], now - window, side='right')
        i1 = np.searchsorted(mag[:, 0], now, side='right')
        m = mag[i0:i1]
    if len(m) < MIN_MAG:
        return None
    f = m[:, 1:4].mean(0)
    return f if shift is None else f + np.asarray(shift, float)


def _trailing_median(b, n):
    out = np.empty(len(b))
    out[:n - 1] = [np.median(b[:i + 1]) for i in range(n - 1)]
    out[n - 1:] = np.median(np.lib.stride_tricks.sliding_window_view(b, n), axis=1)
    return out


def still_flat(acc, now):
    """(still over the last GATE_S, tilt in degrees) from the accelerometer."""
    a = acc[acc[:, 0] > now - GATE_S, 1:4]
    if len(a) < 10:
        return False, None
    g = a.mean(0)
    tilt = float(np.degrees(np.arccos(min(1.0, abs(g[2]) / max(np.linalg.norm(g), 1e-9)))))
    return bool(np.linalg.norm(a, axis=1).std() < STILL_STD), tilt


def gate_open(gate, still, tilt):
    if gate == 'none':
        return True
    if gate == 'still':
        return still
    return still and tilt is not None and tilt <= FLAT_DEG


# ============================================================================ estimators
class Linear:
    """FIR (free non-increasing weights), EMA or none over class-probability vectors."""

    def __init__(self, n, weights=(1.0,), alpha=None):
        self.w, self.alpha = np.asarray(weights, float), alpha
        self.hist, self.s = deque(maxlen=len(self.w)), None

    def step(self, p, dsteps=0.0):
        if p is None:
            return self.s
        if self.alpha is not None:
            self.s = p.copy() if self.s is None else self.alpha * p + (1 - self.alpha) * self.s
        else:
            self.hist.appendleft(p)
            w = self.w[:len(self.hist)]
            self.s = np.tensordot(w / w.sum(), np.array(self.hist), 1)
        return self.s


class HMM:
    """Forward filter over the places of one floor, transitions on the recorded corridors."""

    def __init__(self, classes, adj, edge_steps, beta=1.0, eps=0.01, p_stay=0.98):
        n = len(classes)
        self.beta, self.eps, self.p_stay = beta, eps, p_stay
        idx = {c: i for i, c in enumerate(classes)}
        A = np.zeros((n, n))
        for c, i in idx.items():
            nb = [idx[x] for x in adj.get(c, ()) if x in idx and x != c]
            A[i, nb if nb else [i]] = 1.0
        self.A = A / A.sum(1, keepdims=True)
        self.S = np.array([max(1.0, edge_steps.get(c, 20.0)) for c in classes])   # steps to the next place
        self.b, self.s = np.full(n, 1.0 / n), None

    def step(self, p, dsteps=0.0):
        m = np.minimum(1.0, (1 - self.p_stay) + max(0.0, dsteps) / self.S)
        b = (1 - self.eps) * ((1 - m) * self.b + self.A.T @ (m * self.b)) + self.eps / len(self.b)
        if p is not None:
            b = b * (p + LIK_FLOOR) ** self.beta
        self.b = b / b.sum()
        if p is not None or self.s is not None:
            self.s = self.b
        return self.s


class Guard:
    """Shown place may change only to a corridor neighbour, unless the new place leads M ticks in a row."""

    def __init__(self, m, adj):
        self.m, self.adj, self.shown, self.cand, self.streak = m, adj, None, None, 0

    def step(self, top):
        if top is None:
            return self.shown
        if self.shown is None or top == self.shown or top in self.adj.get(self.shown, ()):
            self.shown, self.cand, self.streak = top, None, 0
        else:
            self.streak = self.streak + 1 if top == self.cand else 1
            self.cand = top
            if self.streak >= self.m:
                self.shown, self.cand, self.streak = top, None, 0
        return self.shown


def adjacency(graph):
    """route.build() graph -> ({floor: {node: set(neighbours)}}, {floor: {node: median steps to a neighbour}})."""
    adj = {f: {a: {b for b, _, _ in outs} for a, outs in g.items()} for f, g in graph.items()}
    steps = {f: {a: float(np.median([s for _, _, s in outs])) for a, outs in g.items() if outs} for f, g in graph.items()}
    return adj, steps


class Continuous:
    """The whole chain for one walker: estimator per floor (reset on a floor change), guard, abstain."""

    def __init__(self, cfg: Config, graph):
        self.cfg = cfg
        self.adj, self.steps = adjacency(graph)
        self.floor, self.classes, self.est, self.guard = None, None, None, None

    def _reset(self, floor, classes):
        c = self.cfg
        self.floor, self.classes = floor, list(classes)
        if c.method == 'hmm':
            self.est = HMM(self.classes, self.adj.get(floor, {}), self.steps.get(floor, {}), c.beta, c.eps, c.p_stay)
        else:
            self.est = Linear(len(classes), c.weights, c.alpha if c.method == 'ema' else None)
        self.guard = Guard(c.guard, self.adj.get(floor, {})) if c.guard else None

    def step(self, floor, classes, p, dsteps=0.0, use=True):
        """p = kNN probabilities over classes (or None), use = gate open. Returns the shown estimate."""
        if floor != self.floor or list(classes) != self.classes:
            self._reset(floor, classes)
        s = self.est.step(p if use else None, dsteps)
        if s is None:
            return {'place': None, 'raw_place': None, 'prob': 0.0, 'top3': [], 'sure': False}
        order = np.argsort(-s, kind='stable')
        top = self.classes[order[0]]
        place = self.guard.step(top) if self.guard else top
        prob = float(s[self.classes.index(place)]) if place is not None else 0.0
        sure = prob >= self.cfg.abstain
        return {'place': place if sure else None, 'raw_place': place, 'prob': prob, 'sure': sure,
                'top3': [(self.classes[i], round(float(s[i]), 3)) for i in order[:3]]}
