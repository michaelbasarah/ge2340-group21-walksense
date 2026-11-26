#!/usr/bin/env python3
"""a56 night-run magnetometer offset: numbers for the keep / exclude / recalibrate decision (PROCESS-LOG entry 77).

OFFLINE ANALYSIS ONLY. config.json, out/ and out-split20/ are not changed; everything is written to out-a56/.

Chris's a56 (SM-A566B) read a median |B| of 110.9 uT on the 25-Nov night run against 40-45 uT on every other day
(clean-data/2026-11-25-night/field_check.csv). Options, each run through the unchanged day-3 pipeline (evaluate.py +
fused_knn.py, default and split20):

  A    keep as now (must reproduce out/ and out-split20/)
  B    exclude the a56 night takes (config `exclude_sources` on session 25night, a derived config in out-a56/)
  C    hard-iron correction, SAME rule for every phone and session: offset = centre of a robust circle fitted to the
       take-mean x/y of all stop takes of that phone in that session (`fit_session`); z is not corrected
  C1   rule C applied only to the a56 night takes (C' in the log)
  C2   time-local version of C for every phone and session: the circle is fitted to the phone's takes within
       LOCAL_MIN minutes of each take (falls back to the session fit, then to no correction)
  C21  rule C2 applied only to the a56 night takes (C2' in the log)

Why a circle in x/y and not "subtract the recording mean": a stop take is 60 s of a phone held still, so its mean
vector IS the fingerprint; subtracting it leaves only noise. A hard-iron offset is a constant vector in the phone's
frame; rotating the phone moves the true field on a circle around that offset. Every stop take was recorded with the
phone flat (gravity along +z, `fits.csv` g_z_min), so the takes at doors facing different ways lie on a circle in the
x/y plane whose centre is the x/y offset. Rotation about z alone carries no information on the z offset, so z is left
as recorded. The rule uses no labels and no accuracy; its guards were fixed before any accuracy was computed:
at least N_MIN takes after outlier removal (|residual| > 3 robust sd), radius R_LO..R_HI uT, and the takes must
cover the circle with no angular gap over GAP_MAX degrees; otherwise the offset is 0 (no correction).

The correction is applied to the raw magnetometer samples of every stop take before the 5 s window features, so it
changes x/y/z (x and y shift), |B| (mean/sd/p10/p90) and tilt (B_vertical/B_horizontal use the corrected mean field;
gravity is unchanged). Wi-Fi and the barometer are not touched. Walk recordings are not corrected (they are only used
by the walk-endpoint test in results.json, which is not part of this comparison).

    python phase2/new/day3/a56_offset.py fields              # offsets, fits, a56 night time series + figure
    python phase2/new/day3/a56_offset.py run A [--split20]   # one option -> out-a56/<option>[-split20]/
    python phase2/new/day3/a56_offset.py report              # out-a56/comparison.csv / comparison.json
    python phase2/new/day3/a56_offset.py xlsx ["tab name"]   # append one tab to out/phone_place_performance.xlsx
    sh phase2/new/day3/a56_offset.sh                         # all of the above (about 15 min, runs in parallel)
"""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and '--split20' in sys.argv:
    os.environ['DAY3_VARIANT'] = 'split20'          # data.py reads the variant at import

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data  # noqa: E402

OUTA = HERE / 'out-a56'
OPTIONS = {'A': 'keep as now', 'B': 'exclude the a56 night takes',
           'C': 'hard-iron x/y correction, session circle fit, every phone and session',
           'C1': "C applied to the a56 night takes only (C')",
           'C2': 'hard-iron x/y correction, time-local circle fit (+-30 min), every phone and session',
           'C21': "C2 applied to the a56 night takes only (C2')"}
N_MIN, R_LO, R_HI, GAP_MAX = 10, 20.0, 60.0, 180.0
LOCAL_MIN, N_MIN_LOCAL = 30.0, 8
NIGHT, A56 = '25night', 'a56'
PHONES = ['ip18', 'ip16', 'a56', 's24', 'a55']


# ----------------------------------------------------------------------------- circle fit
def _geo(P):
    """Least-squares circle: algebraic (Kasa) start, then Gauss-Newton on the geometric distance."""
    A = np.c_[2 * P, np.ones(len(P))]
    sol, *_ = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)
    c = sol[:2]
    for _ in range(100):
        d = np.linalg.norm(P - c, axis=1)
        d = np.maximum(d, 1e-9)
        R = d.mean()
        J = np.c_[-(P - c) / d[:, None], -np.ones(len(P))]
        st, *_ = np.linalg.lstsq(J, -(d - R), rcond=None)
        c = c + st[:2]
        if np.abs(st[:2]).max() < 1e-6:
            break
    d = np.linalg.norm(P - c, axis=1)
    return c, float(d.mean())


def circle_fit(P, n_min=N_MIN):
    """Robust circle through the take-mean x/y points. Returns offset (0, 0) unless every guard passes."""
    P = np.asarray(P, float)
    out = {'n_takes': len(P), 'n_used': 0, 'cx': np.nan, 'cy': np.nan, 'R': np.nan, 'max_gap_deg': np.nan, 'ok': False}
    if len(P) < max(3, n_min):
        return {**out, 'status': f'fewer than {n_min} takes'}
    keep = np.ones(len(P), bool)
    for _ in range(10):
        c, R = _geo(P[keep])
        r = np.linalg.norm(P - c, axis=1) - R
        s = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
        new = np.abs(r - np.median(r[keep])) <= max(3 * s, 1e-6)
        if new.sum() < 3 or (new == keep).all():
            break
        keep = new
    c, R = _geo(P[keep])
    a = np.sort(np.degrees(np.arctan2(P[keep, 1] - c[1], P[keep, 0] - c[0])))
    gap = float(np.max(np.diff(np.r_[a, a[0] + 360])))
    out.update({'n_used': int(keep.sum()), 'cx': float(c[0]), 'cy': float(c[1]), 'R': R, 'max_gap_deg': gap})
    bad = [m for m, b in [(f'fewer than {n_min} takes kept', keep.sum() < n_min), (f'R outside {R_LO:g}-{R_HI:g} uT', not R_LO <= R <= R_HI),
                          (f'angular gap > {GAP_MAX:g} deg', gap > GAP_MAX)] if b]
    out['ok'] = not bad
    out['status'] = 'ok' if not bad else '; '.join(bad)
    return out


# ----------------------------------------------------------------------------- takes and offsets
def raw_tables(opt='A'):
    """The day-3 tables before any variant step (window features of every whole take), for option `opt`."""
    cfg = data.config()
    key = hashlib.md5(json.dumps(cfg, sort_keys=True).encode() + (HERE / 'data.py').read_bytes() + Path(__file__).read_bytes()
                      + b''.join((HERE / s['names']).read_bytes() for s in cfg['sessions'] if 'names' in s) + opt.encode()).hexdigest()[:12]
    pk = data.CACHE / 'a56' / f'features_{opt}_{key}.pkl'
    if pk.exists():            # this script's own local cache (gitignored), never downloaded data
        return pickle.loads(pk.read_bytes())
    parts = {k: [] for k in ['W', 'V', 'O', 'E', 'unmapped', 'A']}
    for s in cfg['sessions']:
        print('loading', s['id'], '...', flush=True)
        res = data.LOADERS[s['loader']](s, cfg['window_s'], cfg['wifi_nearest_stop_max_gap_s'])
        for k, v in zip(['W', 'V', 'O', 'E', 'unmapped', 'A'], res):
            parts[k].append(v)
    D = {k: pd.concat([p for p in parts[k] if len(p)], ignore_index=True) for k in ['W', 'V', 'O', 'E', 'A']}
    D['unmapped'] = [u for p in parts['unmapped'] for u in p]
    D['config'] = cfg
    pk.parent.mkdir(parents=True, exist_ok=True)
    pk.write_bytes(pickle.dumps(D))
    return D


def takes(D):
    """One row per stop take: mean x/y/z and |B| over its windows (sample-weighted), start time of its stop."""
    W = D['W'].assign(wx=lambda w: w['x_mean'] * w['n'], wy=lambda w: w['y_mean'] * w['n'], wz=lambda w: w['z_mean'] * w['n'],
                      wb=lambda w: w['B_mean'] * w['n'])
    T = W.groupby('key').agg(session=('session', 'first'), visit=('visit', 'first'), slot=('slot', 'first'), phone=('phone', 'first'),
                             place=('place', 'first'), floor=('floor', 'first'), n=('n', 'sum'), wx=('wx', 'sum'), wy=('wy', 'sum'),
                             wz=('wz', 'sum'), wb=('wb', 'sum'))
    T = T.assign(x=T['wx'] / T['n'], y=T['wy'] / T['n'], z=T['wz'] / T['n'], B=T['wb'] / T['n']).drop(columns=['wx', 'wy', 'wz', 'wb'])
    T['start'] = T['visit'].map(D['V'].set_index('visit')['start'])
    T['start_hk'] = pd.to_datetime(T['start'], unit='s', utc=True).dt.tz_convert('Asia/Hong_Kong').dt.strftime('%m-%d %H:%M')
    return T.reset_index().sort_values(['session', 'phone', 'start']).reset_index(drop=True)


def offsets(T):
    """Per take: offset (ox, oy) under the session rule and the time-local rule, with the fit behind each. Labels unused."""
    fits, rows = [], []
    for (s, ph), g in T.groupby(['session', 'phone']):
        f = circle_fit(g[['x', 'y']].to_numpy())
        fits.append({'session': s, 'phone': ph, **f})
        for i, r in g.iterrows():
            near = g[(g['start'] - r['start']).abs() <= LOCAL_MIN * 60]
            fl = circle_fit(near[['x', 'y']].to_numpy(), N_MIN_LOCAL)
            if fl['ok']:
                lx, ly, ls = fl['cx'], fl['cy'], f"local fit on {fl['n_used']}/{fl['n_takes']} takes"
            elif f['ok']:
                lx, ly, ls = f['cx'], f['cy'], f"local fit failed ({fl['status']}); session fit"
            else:
                lx, ly, ls = 0.0, 0.0, f"local fit failed ({fl['status']}); session fit failed; no correction"
            rows.append({'key': r['key'], 'ox_session': f['cx'] if f['ok'] else 0.0, 'oy_session': f['cy'] if f['ok'] else 0.0,
                         'ox_local': lx, 'oy_local': ly, 'local_R': fl['R'], 'local_status': ls})
    return pd.DataFrame(fits), T.merge(pd.DataFrame(rows), on='key')


def option_offsets(opt, O):
    """take key -> (ox, oy) for a correction option (only takes with a nonzero offset)."""
    rule = 'session' if opt in ('C', 'C1') else 'local'
    only_night = opt in ('C1', 'C21')
    sel = O if not only_night else O[(O['session'] == NIGHT) & (O['phone'] == A56)]
    return {k: (x, y) for k, x, y in zip(sel['key'], sel[f'ox_{rule}'], sel[f'oy_{rule}']) if x or y}


# ----------------------------------------------------------------------------- patches for one option
def install(opt):
    """Make data.load() return option `opt` and data.OUT point at out-a56/<opt>[-split20]/."""
    if opt == 'B':
        cfg = json.loads((HERE / 'config.json').read_text())
        cfg['_comment_a56'] = 'Derived by a56_offset.py for option B only (offline analysis): session 25night leaves out every a56 recording.'
        for s in cfg['sessions']:
            if s['id'] == NIGHT:
                m = pd.read_csv((HERE / s['path']).resolve() / 'manifest.csv', dtype=str).fillna('')
                ex = m.loc[m['phone'] == A56, ['source_zip']].drop_duplicates().assign(status='excluded_a56_offset')
                OUTA.mkdir(exist_ok=True)
                ex.to_csv(OUTA / 'exclude_a56_night.csv', index=False)
                s['exclude_sources'] = 'out-a56/exclude_a56_night.csv'
        (OUTA / 'config_B.json').write_text(json.dumps(cfg, indent=1))
        os.environ['DAY3_CONFIG'] = 'out-a56/config_B.json'
    elif opt.startswith('C'):
        _, O = offsets(takes(raw_tables('A')))
        off = option_offsets(opt, O)
        cfg = data.config()
        bypath = {}
        for s in cfg['sessions']:
            if s['loader'] != 'clean_tree':
                continue
            root = (HERE / s['path']).resolve()
            for k, o in off.items():
                sid, folder, slot = k.split(':', 2)
                if sid == s['id']:
                    bypath[str(root / folder / slot / 'Magnetometer.csv')] = o
        orig_csv = data._csv

        def _csv(src):
            a = orig_csv(src)
            o = bypath.get(str(src))
            if a is None or o is None:
                return a
            a = a.copy()
            a[:, 1] -= o[0]
            a[:, 2] -= o[1]
            return a
        data._csv = _csv
        sys.path.insert(0, str(data.NEW / 'cross-day'))
        import crossday as cd
        orig_ls = cd.load_sensors

        def load_sensors(day):
            mag, baro = orig_ls(day)
            if day != cd.D_23:
                return mag, baro
            o = mag['stop_id'].map(lambda sid: off.get(f'23nov:{sid}:iphone', (0.0, 0.0)))
            mag = mag.assign(x=mag['x'] - o.map(lambda t: t[0]), y=mag['y'] - o.map(lambda t: t[1]))
            return mag, baro
        cd.load_sensors = load_sensors
        n = len(off)
        print(f'{opt}: {n} stop takes corrected', flush=True)
    data.load = lambda rebuild=False: data._finish(raw_tables(opt))
    data.OUT = OUTA / (opt + (f'-{data.VARIANT}' if data.VARIANT else ''))
    data.OUT.mkdir(parents=True, exist_ok=True)


def run(opt):
    install(opt)
    import evaluate
    import fused_knn
    evaluate.main()
    fused_knn.main()


# ----------------------------------------------------------------------------- fields: offsets, |B| before/after, time series
def fields():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    OUTA.mkdir(exist_ok=True)
    D = raw_tables('A')
    T = takes(D)
    F, O = offsets(T)
    F.round(3).to_csv(OUTA / 'fits.csv', index=False)
    cols = ['session', 'phone', 'slot', 'key', 'place', 'floor', 'start_hk', 'B', 'x', 'y', 'z', 'ox_session', 'oy_session', 'ox_local', 'oy_local',
            'local_R', 'local_status']
    O[cols].round(3).to_csv(OUTA / 'offsets.csv', index=False)
    # |B| before / after per session x phone (median over takes), from the corrected window tables
    rows = []
    corrected = {opt: takes(raw_tables_opt(opt)) for opt in ['C', 'C1', 'C2', 'C21']}
    for (s, ph), gq in T.groupby(['session', 'phone']):
        r = {'session': s, 'phone': ph, 'takes': len(gq), 'B_median_before_uT': round(float(gq['B'].median()), 1)}
        for opt, Tc in corrected.items():
            q = Tc[(Tc['session'] == s) & (Tc['phone'] == ph)]
            r[f'B_median_{opt}_uT'] = round(float(q['B'].median()), 1)
        f = F[(F['session'] == s) & (F['phone'] == ph)].iloc[0]
        r.update({'session_fit': f['status'], 'session_offset_xy_uT': f"{f['cx']:.1f} {f['cy']:.1f}" if f['ok'] else '0 0',
                  'fit_R_uT': round(float(f['R']), 1), 'takes_with_B_over_100_before': int((gq['B'] > 100).sum())})
        for opt, Tc in corrected.items():
            q = Tc[(Tc['session'] == s) & (Tc['phone'] == ph)]
            r[f'takes_with_B_over_100_{opt}'] = int((q['B'] > 100).sum())
        rows.append(r)
    pd.DataFrame(rows).to_csv(OUTA / 'B_before_after.csv', index=False)
    # gravity check: share of windows with gravity within 18 deg of +z (|g_z| >= 0.95), from the raw accelerometer of each take
    flat = flat_check(D)
    flat.to_csv(OUTA / 'flat_check.csv', index=False)
    # a56 night time series: per take vs the same phone's take at the same place in the first 25-Nov run
    ref = T[T['session'] == '25nov'].groupby(['phone', 'place'])[['x', 'y', 'z']].mean()
    ts = O[O['session'] == NIGHT].copy()
    for c in 'xyz':
        ts[f'd{c}_vs_25nov'] = [r[c] - ref.loc[(r['phone'], r['place']), c] if (r['phone'], r['place']) in ref.index else np.nan for _, r in ts.iterrows()]
    ts['clock_h'] = (ts['start'] - pd.Timestamp('2026-11-25', tz='Asia/Hong_Kong').timestamp()) / 3600
    tcols = ['phone', 'place', 'floor', 'start_hk', 'clock_h', 'B', 'x', 'y', 'z', 'dx_vs_25nov', 'dy_vs_25nov', 'dz_vs_25nov',
             'ox_session', 'oy_session', 'ox_local', 'oy_local', 'local_status']
    ts = ts.sort_values(['phone', 'start'])
    ts[tcols].round(3).to_csv(OUTA / 'night_timeseries_takes.csv', index=False)
    tr = trace(NIGHT)
    tr.round(3).to_csv(OUTA / 'night_trace_1s.csv', index=False)
    drift = drift_summary(ts)
    (OUTA / 'night_drift.json').write_text(json.dumps(drift, indent=1))
    # figure
    col = {'a56': '#f47230', 'ip18': '#257de0'}
    fig, ax = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
    for ph in ['ip18', 'a56']:
        q = tr[tr['phone'] == ph]
        ax[0].plot(q['clock_h'], q['B'], '.', ms=1.5, color=col[ph], label=f'{ph} (1 s means, stops and walks)')
    ax[0].set_ylabel('|B| (uT)'); ax[0].set_ylim(0, 350); ax[0].legend(loc='upper right', frameon=False)
    ax[0].set_title('25-Nov night run: magnetometer over the night (a56 vs ip18 carried together)', loc='left')
    q = tr[tr['phone'] == 'a56']
    for c, cc in zip('xyz', ['#257de0', '#f47230', '#00b894']):
        ax[1].plot(q['clock_h'], q[c], '.', ms=1.5, color=cc, label=f'a56 {c}')
    ax[1].set_ylabel('a56 raw field (uT)'); ax[1].legend(loc='lower right', frameon=False, ncol=3); ax[1].axhline(0, color='#999', lw=0.8)
    for ph, mk in [('a56', 'o'), ('ip18', 's')]:
        q = ts[ts['phone'] == ph]
        for c, cc in zip('xy', ['#257de0', '#f47230']):
            ax[2].plot(q['clock_h'], q[f'd{c}_vs_25nov'], mk, ms=5 if ph == 'a56' else 4, mfc=cc if ph == 'a56' else 'none', color=cc,
                       label=f'{ph} take {c} minus same place, 25 Nov run')
    q = ts[ts['phone'] == 'a56']
    ax[2].step(q['clock_h'], q['ox_local'], where='mid', color='#257de0', lw=2, alpha=.6, label='a56 fitted x offset, time-local (C2)')
    ax[2].step(q['clock_h'], q['oy_local'], where='mid', color='#f47230', lw=2, alpha=.6, label='a56 fitted y offset, time-local (C2)')
    ax[2].axhline(q['ox_session'].iloc[0], color='#257de0', ls='--', lw=1, label='a56 fitted x offset, session (C)')
    ax[2].axhline(q['oy_session'].iloc[0], color='#f47230', ls='--', lw=1, label='a56 fitted y offset, session (C)')
    ax[2].axhline(0, color='#999', lw=0.8)
    ax[2].set_ylabel('offset (uT)'); ax[2].set_xlabel('clock time on 25 Nov (h; 24 = midnight)')
    ax[2].legend(loc='lower left', frameon=False, fontsize=7, ncol=2); ax[2].set_ylim(-200, 120)
    for a in ax:
        a.spines[['top', 'right']].set_visible(False); a.grid(axis='y', color='#eee')
    fig.tight_layout()
    fig.savefig(OUTA / 'fig_a56_night_offset.png', dpi=140, facecolor='white')
    print(F.round(1).to_string()); print(pd.DataFrame(rows).to_string()); print(json.dumps(drift, indent=1))


def raw_tables_opt(opt):
    """Corrected raw tables for a correction option (window features rebuilt from corrected samples), default variant."""
    saved = (data._csv, data.load, data.OUT)
    sys.path.insert(0, str(data.NEW / 'cross-day'))
    import crossday as cd
    saved_ls = cd.load_sensors
    try:
        install(opt)
        return raw_tables(opt)
    finally:
        data._csv, data.load, data.OUT = saved
        cd.load_sensors = saved_ls


def flat_check(D):
    """Per session x phone: median and minimum over stop windows of the gravity component along the phone's z axis."""
    rows = []
    for s in data.config()['sessions']:
        if s['loader'] != 'clean_tree':
            continue
        root = (HERE / s['path']).resolve()
        m = pd.read_csv(root / 'manifest.csv', dtype=str).fillna('')
        for ph, g in m[m['type'] == 'stop'].groupby('phone'):
            gz = []
            for f in g['folder']:
                a = data._csv(root / f / ph / 'Accelerometer.csv')
                if a is not None and len(a):
                    v = a[:, 1:4].mean(0)
                    gz.append(abs(v[2]) / np.linalg.norm(v))
            if gz:
                rows.append({'session': s['id'], 'phone_folder': ph, 'stop_takes': len(gz), 'g_z_median': round(float(np.median(gz)), 3),
                             'g_z_min': round(float(np.min(gz)), 3)})
    return pd.DataFrame(rows)


def trace(sid):
    """1 s means of every magnetometer recording (stops and walks) of one clean_tree session, on the clock."""
    s = next(x for x in data.config()['sessions'] if x['id'] == sid)
    root = (HERE / s['path']).resolve()
    m = pd.read_csv(root / 'manifest.csv', dtype=str).fillna('')
    day = pd.Timestamp(s['day'])
    out = []
    for _, r in m.iterrows():
        a = data._csv(root / r['folder'] / r['phone'] / 'Magnetometer.csv')
        if a is None or not len(a):
            continue
        h, mi, se = map(int, r['start_hk'].split(':'))
        t0 = h + mi / 60 + se / 3600
        b = pd.DataFrame(a[:, 1:4], columns=list('xyz')).groupby((a[:, 0] // 1).astype(int)).mean()
        out.append(b.assign(B=np.linalg.norm(b[list('xyz')].to_numpy(), axis=1), clock_h=t0 + b.index / 3600,
                            phone=data.handset(r['device']), type=r['type'], folder=r['folder']))
    _ = day
    return pd.concat(out, ignore_index=True).sort_values(['phone', 'clock_h'])


def drift_summary(ts):
    """Is the a56 offset constant over the night? Offsets vs the 25-Nov run per take, split at the 22:59 take."""
    out = {}
    for ph in ['a56', 'ip18']:
        q = ts[(ts['phone'] == ph)].dropna(subset=['dx_vs_25nov'])
        part = {'all': q, 'before 22:59': q[q['clock_h'] < 22 + 59 / 60 - 1e-6], 'from 23:00': q[q['clock_h'] >= 23]}
        out[ph] = {k: {'takes': len(v), 'median_dx_dy_dz_uT': [round(float(v[f'd{c}_vs_25nov'].median()), 1) for c in 'xyz'],
                       'sd_dx_dy_dz_uT': [round(float(v[f'd{c}_vs_25nov'].std()), 1) for c in 'xyz']} for k, v in part.items()}
    q = ts[ts['phone'] == 'a56']
    out['a56_local_offset_range_uT'] = {'ox': [round(float(q['ox_local'].min()), 1), round(float(q['ox_local'].max()), 1)],
                                        'oy': [round(float(q['oy_local'].min()), 1), round(float(q['oy_local'].max()), 1)]}
    out['a56_session_offset_uT'] = [round(float(q['ox_session'].iloc[0]), 1), round(float(q['oy_session'].iloc[0]), 1)]
    return out


# ----------------------------------------------------------------------------- report
def repro(d, o):
    """Does the run in d reproduce the official run in o? (fold timings `seconds` ignored)"""
    S, So = pd.read_csv(d / 'fused_sample_predictions.csv'), pd.read_csv(o / 'fused_sample_predictions.csv')
    cols = ['scheme', 'key', 'true', 'pred', 'top3']
    same = len(So) == len(S) and So.sort_values(['scheme', 'key']).reset_index(drop=True)[cols].equals(S.sort_values(['scheme', 'key']).reset_index(drop=True)[cols])
    F, Fo = json.loads((d / 'fused_knn.json').read_text()), json.loads((o / 'fused_knn.json').read_text())
    strip = lambda sc: {k: {**v, 'folds': [{a: b for a, b in f.items() if a != 'seconds'} for f in v['folds']]} for k, v in sc.items()}
    same_f = strip(F['schemes']) == strip(Fo['schemes']) and F['deployable_model'] == Fo['deployable_model']
    same_r = json.loads((d / 'results.json').read_text())['stop_results'] == json.loads((o / 'results.json').read_text())['stop_results']
    lo = F['schemes']['leave_one_session_out']['overall']['fused (learned weights)']
    loo = Fo['schemes']['leave_one_session_out']['overall']['fused (learned weights)']
    fo = [(a, b) for k in Fo['schemes'] for a, b in zip(Fo['schemes'][k]['folds'], F['schemes'][k]['folds'])]
    same_wk = sum(a['chosen_weights'] == b['chosen_weights'] and a['chosen_k'] == b['chosen_k'] for a, b in fo)
    d_inner = max(abs(a['inner_acc_chosen'] - b['inner_acc_chosen']) for a, b in fo)
    return {'folds_same_weights_and_k': f'{same_wk}/{len(fo)}', 'max_inner_acc_difference': round(d_inner, 3),
            'fused_sample_predictions.csv': bool(same), 'fused_knn.json schemes+model (timings ignored)': bool(same_f),
            'results.json stop_results': bool(same_r), 'loso': f"{lo['exact']}/{lo['n_recordings_scored']}",
            'loso_official': f"{loo['exact']}/{loo['n_recordings_scored']}", 'official_dir': o.name}


def report():
    rows, per_place, js = [], [], {}
    official = {'': HERE / 'out', '-split20': HERE / 'out-split20'}
    for var in ['', '-split20']:
        for opt in OPTIONS:
            d = OUTA / (opt + var)
            if not (d / 'fused_knn.json').exists():
                continue
            F = json.loads((d / 'fused_knn.json').read_text())
            R = json.loads((d / 'results.json').read_text())
            S = pd.read_csv(d / 'fused_sample_predictions.csv')
            L = S[S['scheme'] == 'leave_one_session_out'].assign(ok=lambda x: x['true'] == x['pred'])
            lo = F['schemes']['leave_one_session_out']['overall']['fused (learned weights)']
            gr = F['schemes']['grouped_by_stop']['overall']['fused (learned weights)']
            r = {'variant': 'split20' if var else 'default', 'option': opt, 'what': OPTIONS[opt],
                 'loso_correct': lo['exact'], 'loso_n': lo['n_recordings_scored'], 'loso_acc': lo['exact_acc'], 'loso_ci95': lo['exact_ci95'],
                 'grouped_correct': gr['exact'], 'grouped_n': gr['n_recordings_scored'], 'grouped_acc': gr['exact_acc']}
            for ph in PHONES:
                q = L[L['phone'] == ph]
                r[f'{ph}'] = f"{int(q['ok'].sum())}/{len(q)}"
                r[f'{ph}_acc'] = round(float(q['ok'].mean()), 3) if len(q) else None
            q = L[(L['session'] == NIGHT) & (L['phone'] == A56)]
            r['a56_night'] = f"{int(q['ok'].sum())}/{len(q)}" if len(q) else 'excluded'
            q = L[~((L['session'] == NIGHT) & (L['phone'] == A56))]          # the same test samples in every option
            r['loso_without_a56_night'] = f"{int(q['ok'].sum())}/{len(q)}"
            r['loso_without_a56_night_acc'] = round(float(q['ok'].mean()), 3)
            q = L[L['phone'] == A56]
            q = q[q['session'] != NIGHT]
            r['a56_other_sessions'] = f"{int(q['ok'].sum())}/{len(q)}"
            q = L[(L['session'] == NIGHT) & (L['phone'] == 'ip18')]
            r['ip18_night'] = f"{int(q['ok'].sum())}/{len(q)}"
            for ph in PHONES:
                for mode in ['allphones', 'samehandset']:
                    e = R['stop_results'].get(f'leave25nov_out_{mode}_test_{ph}', {}).get('|B|+xyz+tilt + baro floor')
                    if e and 'exact' in e:
                        r[f'leave25out_{mode}_{ph}'] = f"{e['exact']}/{e['n_recordings']}"
            r['stops_over_100uT'] = len(R['magnetic_check']['stops_with_median_B_above_100uT'])
            m = F['deployable_model']
            r['deployable'] = ' '.join(f'{k} {v:g}' for k, v in m['weights'].items()) + f" k {m['k']}"
            if opt == 'A':
                rep = repro(d, official[var])
                r['reproduces_official'] = all(v for k, v in rep.items() if k != 'official_dir')
                js[f'A{var}_reproduces'] = rep
                if (OUTA / f'A_mt{var}' / 'fused_knn.json').exists():
                    js[f'A_mt{var}_reproduces'] = repro(OUTA / f'A_mt{var}', official[var])
            rows.append(r)
            q = L[(L['session'] == NIGHT) & (L['phone'] == A56)]
            for p, g in q.groupby('true'):
                per_place.append({'variant': r['variant'], 'option': opt, 'place': p, 'correct': int(g['ok'].sum()), 'n': len(g),
                                  'predicted': '|'.join(f'{k}:{v}' for k, v in g['pred'].value_counts().items())})
    C = pd.DataFrame(rows)
    C.to_csv(OUTA / 'comparison.csv', index=False)
    P = pd.DataFrame(per_place)
    if len(P):
        P.to_csv(OUTA / 'a56_night_per_place.csv', index=False)
        wide = P.assign(cell=P['correct'].astype(str) + '/' + P['n'].astype(str)).pivot_table(index='place', columns=['variant', 'option'], values='cell', aggfunc='first')
        wide.to_csv(OUTA / 'a56_night_per_place_wide.csv')
    js['options'] = OPTIONS
    js['rule'] = {'n_min': N_MIN, 'R_uT': [R_LO, R_HI], 'max_gap_deg': GAP_MAX, 'local_window_min': LOCAL_MIN, 'n_min_local': N_MIN_LOCAL,
                  'z': 'not corrected'}
    js['rows'] = rows
    (OUTA / 'comparison.json').write_text(json.dumps(js, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
    print(C.drop(columns=['what', 'loso_ci95']).to_string())


def xlsx(tab='2026-11-26 a56 options'):
    """Append ONE new tab to out/phone_place_performance.xlsx (existing tabs are never changed; refuses if the tab exists)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    path = HERE / 'out' / 'phone_place_performance.xlsx'
    wb = openpyxl.load_workbook(path)
    if tab in wb.sheetnames:
        raise SystemExit(f'tab {tab!r} already exists in {path}; pick another name (tabs are never overwritten)')
    before = {n: [[c.value for c in row] for row in wb[n].iter_rows()] for n in wb.sheetnames}
    ws = wb.create_sheet(tab)
    bold, head = Font(bold=True), PatternFill('solid', fgColor='DDEBF7')
    C = pd.read_csv(OUTA / 'comparison.csv')

    def block(title, hdr, rows, pct=()):
        ws.append([title]); ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        ws.append(hdr)
        for c in ws[ws.max_row]:
            c.font, c.fill = bold, head
        for r in rows:
            ws.append(list(r))
            for j, h in enumerate(hdr):
                if h in pct and isinstance(r[j], float):
                    ws.cell(ws.max_row, j + 1).number_format = '0.0%'
        ws.append([])
    ws.append(['a56 night-run magnetometer offset: keep / exclude / recalibrate (offline analysis, PROCESS-LOG 77; internal team sheet, numbers only)'])
    ws['A1'].font = Font(bold=True, size=13)
    ws.append(['Source: phase2/new/day3/out-a56/comparison.csv (a56_offset.py). Official config.json, out/ and out-split20/ unchanged; option A reproduces them.'])
    ws.append(['Scheme: learned-weight fused kNN, leave one session out (per take in default, per 20 s piece in split20). '
               'Leave-25-Nov-out = results.json, |B|+xyz+tilt + baro floor, kNN k=5.'])
    ws.append([])
    block('Options', ['option', 'what'], [[k, v] for k, v in OPTIONS.items()])
    cols = ['variant', 'option', 'loso_correct', 'loso_n', 'loso_acc', 'loso_without_a56_night', 'loso_without_a56_night_acc', 'grouped_acc'] + [f'{p}' for p in PHONES] + [f'{p}_acc' for p in PHONES] + \
           ['a56_night', 'a56_other_sessions', 'ip18_night', 'stops_over_100uT', 'deployable']
    block('Leave one session out, overall and per phone (correct / n)', cols, C[cols].itertuples(index=False),
          pct={'loso_acc', 'loso_without_a56_night_acc', 'grouped_acc'} | {f'{p}_acc' for p in PHONES})
    lc = [c for c in C.columns if c.startswith('leave25out_')]
    block('Leave 25 Nov out (train earlier days, test every 25-Nov session), correct / n', ['variant', 'option'] + lc, C[['variant', 'option'] + lc].itertuples(index=False))
    if (OUTA / 'a56_night_per_place_wide.csv').exists():
        Wd = pd.read_csv(OUTA / 'a56_night_per_place_wide.csv', header=[0, 1], index_col=0)
        block('a56 night takes per place (correct / n, leave one session out)', ['place'] + [f'{v} {o}' for v, o in Wd.columns],
              [[i] + list(r) for i, r in Wd.fillna('').iterrows()])
    Bb = pd.read_csv(OUTA / 'B_before_after.csv')
    bc = ['session', 'phone', 'takes', 'B_median_before_uT', 'B_median_C_uT', 'B_median_C2_uT', 'session_offset_xy_uT', 'fit_R_uT', 'session_fit',
          'takes_with_B_over_100_before', 'takes_with_B_over_100_C', 'takes_with_B_over_100_C2']
    block('|B| before / after the correction (median over stop takes, uT); session circle-fit offset (x y)', bc, Bb[bc].itertuples(index=False))
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(40, max(8, max(len(str(c.value)) if c.value is not None and c.row > 4 else 0 for c in col) + 2))
    data.relabel_sheet(ws)
    wb.save(path)
    wb2 = openpyxl.load_workbook(path)
    assert wb2.sheetnames[:-1] == list(before) and wb2.sheetnames[-1] == tab
    for n, rows in before.items():
        assert [[c.value for c in row] for row in wb2[n].iter_rows()] == rows, f'tab {n} changed'
    print(f'appended tab {tab!r} to {path}; earlier {len(before)} tabs unchanged')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'fields':
        fields()
    elif cmd == 'run' and len(sys.argv) > 2 and sys.argv[2] in OPTIONS:
        run(sys.argv[2])
    elif cmd == 'prepare':
        for o in OPTIONS:
            saved = (data._csv, data.load, data.OUT, os.environ.get('DAY3_CONFIG'))
            sys.path.insert(0, str(data.NEW / 'cross-day'))
            import crossday as cd
            saved_ls = cd.load_sensors
            install(o)
            raw_tables(o)
            data._csv, data.load, data.OUT = saved[:3]
            cd.load_sensors = saved_ls
            os.environ.pop('DAY3_CONFIG', None)
            if saved[3]:
                os.environ['DAY3_CONFIG'] = saved[3]
    elif cmd == 'report':
        report()
    elif cmd == 'xlsx':
        xlsx(*sys.argv[2:3])
    else:
        print(__doc__)
        sys.exit(1)
