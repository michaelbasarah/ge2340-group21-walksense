#!/usr/bin/env python3
"""Dead-reckoning pilot — count steps in each walk recording (method A feasibility).

Uses the accelerometer movement recordings in ../clean-data/2026-11-17/. Removes gravity
with a short moving-average high-pass, then counts peaks (each bounce = one step).

NOTE: this gives STEPS, not metres. Converting steps to metres needs a stride length, and
converting to a position on a map needs the checkpoint coordinates from the floor plan.
Neither is invented here.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / '..' / 'clean-data' / '2026-11-17'
OUT = ROOT / 'out'; OUT.mkdir(exist_ok=True)
PEAK_THRESHOLD = 0.9      # m/s^2 on the gravity-removed signal
REFRACTORY_S = 0.30       # min time between steps (caps cadence ~3.3 steps/s)
HIGHPASS_S = 0.40         # moving-average window used to remove gravity/slow drift

def moving_average(a, w):
    return np.convolve(a, np.ones(w) / w, mode='same') if w > 1 else a

def count_steps(t, mag):
    dt = np.median(np.diff(t)) if len(t) > 1 else 0.01
    fs = 1.0 / dt
    dyn = mag - moving_average(mag, max(1, int(round(HIGHPASS_S * fs))))
    gap = int(round(REFRACTORY_S * fs))
    steps = 0; last = -gap - 1; times = []
    for i in range(1, len(dyn) - 1):
        if dyn[i] > PEAK_THRESHOLD and dyn[i] >= dyn[i - 1] and dyn[i] > dyn[i + 1] and (i - last) >= gap:
            steps += 1; last = i; times.append(float(t[i]))
    return steps, fs, times

def main():
    s = pd.read_csv(DATA / 'sensor_samples.csv')
    edges = pd.read_csv(DATA / 'accelerometer_edges.csv')
    frm = dict(zip(edges['acc_session_id'], edges['from_location']))
    to = dict(zip(edges['acc_session_id'], edges['to_location']))
    acc = s[s['sensor'] == 'accelerometer']
    rows = []; total = 0
    for sid, g in sorted(acc.groupby('session_id')):
        g = g.sort_values('relative_time_s')
        t = g['relative_time_s'].to_numpy(); mag = g['vector_magnitude'].to_numpy()
        steps, fs, _ = count_steps(t, mag)
        dur = float(t[-1] - t[0]) if len(t) > 1 else 0.0
        total += steps
        rows.append({'acc_id': sid, 'from': frm.get(sid, ''), 'to': to.get(sid, ''),
                     'duration_s': round(dur, 1), 'sampling_hz': round(fs), 'readings': len(g),
                     'detected_steps': steps,
                     'cadence_steps_per_s': round(steps / dur, 2) if dur > 0 else ''})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / 'step_detection.csv', index=False)
    print(df.to_string(index=False))
    walking = df[df['cadence_steps_per_s'] != '']
    print(f"\nTOTAL detected steps across the walk: {total}")
    print(f"Median cadence: {walking['cadence_steps_per_s'].median():.2f} steps/s "
          f"(normal walking is ~1.5-2.2) -> sanity check on the detector.")
    print("Steps only; metres need a stride length and checkpoint coordinates from the floor plan.")

if __name__ == '__main__':
    main()
