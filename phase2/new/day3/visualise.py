#!/usr/bin/env python3
"""Figures and the interactive data explorer for the day-3 evaluation.

Run after evaluate.py and fused_knn.py:  python phase2/new/day3/visualise.py
Writes PNGs and explore.html into out/ (and out/embeddings.json for the HTML).

Colour rules: at most 3 categorical colours per static chart (sessions / series), place identity by
direct text labels; the 26 places are told apart in the interactive HTML (legend toggle + hover).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from sklearn.decomposition import PCA
from sklearn.manifold import MDS, TSNE

import data
import gknn

DISP = data.place_display()   # display names only (config.json place_display); ids stay the keys

OUT = data.OUT
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'          # categorical slots 1-3 (validated all-pairs)
S4 = '#8f4fd1'                                         # 4th session (25 Nov)
S5 = '#b0306a'                                         # 5th session (25 Nov spot recordings)
SESS_COL = {'23nov': S1, '24s1': S2, '24s2': S3, '25nov': S4, '25spots': S5}
SESS_MARK = {'23nov': 'o', '24s1': 's', '24s2': '^', '25nov': 'D', '25spots': 'v'}
SESS_NAME = {'23nov': '23 Nov', '24s1': '24 Nov session 1', '24s2': '24 Nov session 2', '25nov': '25 Nov', '25spots': '25 Nov spots'}
SESSIONS = [s['id'] for s in data.config()['sessions']]          # config order; every figure loops over these
for _i, _s in enumerate(SESSIONS):                               # a session added later without an entry above still draws
    SESS_COL.setdefault(_s, ['#5c5c5c', '#b0306a'][_i % 2]); SESS_MARK.setdefault(_s, 'v'); SESS_NAME.setdefault(_s, _s)
INK, INK2, GRID, AX = '#0b0b0b', '#52514e', '#e6e5e0', '#b5b4ad'
GREY = '#8a8983'
DN = data.display_names()           # handset id -> display name (config.json phones)


def style(ax, grid='y'):
    for s in ['top', 'right']:
        ax.spines[s].set_visible(False)
    for s in ['left', 'bottom']:
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=INK2, labelsize=8)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(OUT / name, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print('wrote', name)


# ----------------------------------------------------------------------------- accuracy vs chance
def fig_accuracy(R):
    sets = ['|B|', '|B|+xyz', 'tilt', '|B|+xyz+tilt', 'Wi-Fi', '|B|+xyz+Wi-Fi']
    sr = R['stop_results']

    def pooled(exps, fs):
        k = n = 0
        for e in exps:
            r = sr[e].get(fs + ' + baro floor', {})
            if 'exact' not in r:
                return None
            k += r['exact']; n += r['n_recordings']
        return k, n
    series = [(f"Session 1 <-> 2, iPhone, DIFFERENT handsets ({DN['ip18']} <-> {DN['ip16']}), n=53", ['xsession_24s1_to_24s2_iphone', 'xsession_24s2_to_24s1_iphone'], S1),
              (f"Session 1 <-> 2, Galaxy S24 (same handset {DN['s24']}), n=53", ['xsession_24s1_to_24s2_s24', 'xsession_24s2_to_24s1_s24'], S2),
              (f"Other day: 23 Nov -> 24 Nov s2, same handset {DN['ip16']}, n=26", ['xday_23nov_to_24s2_iphone'], S3)]
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    w = 0.26
    for j, (lab, exps, col) in enumerate(series):
        for i, fs in enumerate(sets):
            x = i + (j - 1) * w
            p = pooled(exps, fs)
            if p is None:
                ax.text(x, 0.01, 'n/a', ha='center', va='bottom', fontsize=7, color=INK2, rotation=90)
                continue
            v = p[0] / p[1]
            ax.bar(x, v, width=w - 0.03, color=col, label=lab if i == 0 else None, edgecolor='white', linewidth=1)
            ax.text(x, v + 0.012, f'{v:.0%}', ha='center', va='bottom', fontsize=7, color=INK)
    ch = sr['xsession_24s1_to_24s2_iphone']['_split']['chance']
    ax.axhline(ch, color=INK, linewidth=1, linestyle=(0, (1.5, 1.5)))
    ax.text(len(sets) - 0.45, ch + 0.01, f'chance {ch:.1%} (26 places)', fontsize=7, color=INK, ha='right')
    ax.set_xticks(range(len(sets))); ax.set_xticklabels([s + '\n+ baro floor' for s in sets], fontsize=8)
    ax.set_ylim(0, 0.8); ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel('exact place, per stop recording', fontsize=9, color=INK2)
    ax.set_title('24-Nov data, no recording in both train and test: place accuracy per feature set (kNN, k=5)', fontsize=10, loc='left', color=INK)
    style(ax); ax.legend(frameon=False, fontsize=8, loc='upper left')
    fig.text(0.01, -0.02, "n/a: 23-Nov stops logged no accelerometer, so no tilt features. Wi-Fi = s24 WiGLE rows within 120 s of the stop. "
             "Source: out/results.json", fontsize=7, color=INK2)
    save(fig, 'fig_accuracy_vs_chance.png')


def fig_leaky_vs_honest(F):
    order = [('random_LEAKY', 'Random windows\n(LEAKY, illustration)'), ('by_recording_partly_leaky', 'Whole recordings\n(other phones of the\nsame stop in training)'),
             ('grouped_by_stop', 'Whole stops\n(grouped CV)'), ('leave_one_session_out', 'Whole sessions\n(leave one session out)')]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for i, (k, lab) in enumerate(order):
        o = F['schemes'][k]['overall']['fused (learned weights)']
        v = o['exact_acc']
        col = GREY if i < 2 else S1
        ax.bar(i, v, width=0.55, color=col, edgecolor='white', hatch='//' if i == 0 else None)
        lo, hi = o['exact_ci95']
        ax.plot([i, i], [lo, hi], color=INK, linewidth=1)
        ax.text(i + 0.3, v, f"{v:.1%}\n({o['exact']}/{o['n_recordings_scored']})", fontsize=8, color=INK, va='center')
        ch = F['schemes'][k]['chance_mean']
        ax.plot([i - 0.3, i + 0.3], [ch, ch], color=INK, linewidth=1, linestyle=(0, (1.5, 1.5)))
    ax.set_xticks(range(len(order))); ax.set_xticklabels([l for _, l in order], fontsize=8)
    ax.set_ylim(0, 1.05); ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel('exact place, per stop recording', fontsize=9, color=INK2)
    ax.set_title('Same fused kNN, four ways to split the data (weights and k tuned inside training folds; dotted = chance)',
                 fontsize=10, loc='left', color=INK)
    style(ax)
    fig.text(0.01, -0.03, 'Grey: leaky splits, shown only to make the gap visible. Bars = 95% Wilson interval. Random windows: a recording is scored once '
             'per fold it has test windows in, so n is larger. Source: out/fused_knn.json',
             fontsize=7, color=INK2)
    save(fig, 'fig_leaky_vs_honest.png')


def confusion_panel(ax, truth, pred, labels, title):
    idx = {l: i for i, l in enumerate(labels)}
    M = np.zeros((len(labels), len(labels)))
    for t, p in zip(truth, pred):
        if t in idx and p in idx:
            M[idx[t], idx[p]] += 1
    n = M.sum(1, keepdims=True)
    im = ax.imshow(M / np.maximum(n, 1), cmap='Blues', vmin=0, vmax=1, aspect='auto')
    ax.set_xticks(range(len(labels))); ax.set_xticklabels([DISP.get(l, l) for l in labels], rotation=90, fontsize=6.5)
    ax.set_yticks(range(len(labels))); ax.set_yticklabels([DISP.get(l, l) for l in labels], fontsize=6.5)
    ax.set_xlabel('predicted place', fontsize=8, color=INK2); ax.set_ylabel('true place', fontsize=8, color=INK2)
    ax.set_title(title, fontsize=9, loc='left', color=INK)
    k = int(M.trace()); f5 = sum(1 for l in labels if not l.endswith('4F') and l not in FLOOR4)
    ax.axhline(f5 - 0.5, color=INK2, linewidth=0.6); ax.axvline(f5 - 0.5, color=INK2, linewidth=0.6)
    return im


FLOOR4 = set()


def fig_confusion(R, wp, P):
    global FLOOR4
    FLOOR4 = set(P[P['floor'] == 4].index)
    labels = sorted(P.index, key=lambda p: (-P.loc[p, 'floor'], P.loc[p, 'x']))
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.6), gridspec_kw={'wspace': 0.45})
    lw = wp[wp['scheme'] == 'leave_one_session_out']
    acc = (lw['true'] == lw['pred_window']).mean()
    confusion_panel(axes[0], lw['true'], lw['pred_window'], labels,
                    f'Fused kNN, leave one session out: every 5 s window\n(window accuracy {acc:.0%}, n={len(lw)}; rows normalised)')
    r = R['stop_results']['xday_23nov_to_24s2_iphone']['|B|+xyz + baro floor']
    tp = list(r['predictions'].values())
    im = confusion_panel(axes[1], [a for a, _ in tp], [b for _, b in tp], labels,
                         f"Other day, same handset ({DN['ip16']}): train 23 Nov, test 24 Nov s2\n|B|+xyz + baro floor, per recording ({r['exact']}/{r['n_recordings']} exact)")
    fig.colorbar(im, ax=list(axes), shrink=0.6, label='share of the row')
    fig.text(0.01, -0.12, 'Lines split floor 5 (top/left) from floor 4. Places ordered by floor, then west to east. '
             'Sources: out/fused_window_predictions.csv, out/results.json', fontsize=7, color=INK2)
    save(fig, 'fig_confusion.png')


def fig_floor(V, R):
    ns = len(SESSIONS)
    fig, axes = plt.subplots(1, ns, figsize=(14 * ns / 3, 4.2), sharey=True)
    if 'track' not in V:
        V = V.assign(track=V['session'])
    for ax, s in zip(axes, SESSIONS):
        vs = V[V['session'] == s]
        t0 = vs['start'].min()
        tracks = sorted(vs['track'].unique())
        for tk, v in vs.groupby('track'):                 # one line per track (25 Nov: route round and spot recordings)
            v = v.sort_values('start')
            t = (v['start'] - t0) / 60
            for ph, mk, lab in [('iphone', 'o', 'iPhone barometer'), ('s24', 'D', 'Galaxy S24 pressure')]:
                p = v[f'hpa_{ph}']
                if p.notna().sum() < 2:
                    continue
                rel = p - p.dropna().iloc[0]
                col = S1 if ph == 'iphone' else GREY
                ax.plot(t, rel, color=col, linewidth=1, alpha=0.6, linestyle='-' if tk == tracks[0] else '--')
                for f, fc in [(5, 'white'), (4, col)]:
                    m = (v['floor'] == f).to_numpy()
                    ax.scatter(t[m], rel[m], marker=mk, s=28, facecolor=fc, edgecolor=col, linewidth=1.3, zorder=3,
                               label=f'{lab}, floor {f}' if s == '24s1' or (s == '23nov' and ph == 'iphone') else None)
        fl = [R['floor'][f'iphone_test_{tk}'] for tk in tracks if f'iphone_test_{tk}' in R['floor']]
        steps = '+'.join(f['step_tracking'] for f in fl)
        fixed = '+'.join(f['absolute_threshold'] for f in fl)
        hsets = '/'.join(DN[h] for h in sorted(set(' '.join(vs['iphone_handset']).split())))
        trk = f", {len(tracks)} tracks (dashed = {', '.join(t.split(':')[-1] for t in tracks[1:])})" if len(tracks) > 1 else ''
        ax.set_title(f"{SESS_NAME[s]} ({hsets}){trk}\niPhone step tracking {steps} stops, fixed threshold {fixed}",
                     fontsize=9, loc='left', color=INK)
        ax.set_xlabel('minutes since first stop', fontsize=8, color=INK2)
        style(ax)
    axes[0].set_ylabel('pressure minus first stop (hPa)\n(higher = lower floor)', fontsize=8, color=INK2)
    axes[1].legend(frameon=False, fontsize=7, loc='upper left')
    fig.text(0.01, -0.04, 'Filled = floor 4, hollow = floor 5 (true floor from the route). Step tracking: floor changes when consecutive stops differ by more than '
             'half the floor step learned on the other sessions. Source: out/results.json (floor, floor_stats)', fontsize=7, color=INK2)
    save(fig, 'fig_floor_detection.png')


def fig_per_place(W, V, P):
    order = sorted(P.index, key=lambda p: (-P.loc[p, 'floor'], P.loc[p, 'x']))
    pos = {p: i for i, p in enumerate(order)}
    fig, axes = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True)
    rng = np.random.default_rng(0)
    iph = W[W['slot'] == 'iphone']
    off = lambda j: (j - (len(SESSIONS) - 1) / 2) * 0.25
    if 'track' not in V:
        V = V.assign(track=V['session'])
    for j, s in enumerate(SESSIONS):
        g = iph[iph['session'] == s]
        x = g['place'].map(pos) + off(j) + rng.uniform(-0.06, 0.06, len(g))
        axes[0].scatter(x, g['B_mean'], s=9, color=SESS_COL[s], alpha=0.75, label=SESS_NAME[s], marker=SESS_MARK[s], linewidths=0)
        v = V[V['session'] == s].sort_values('start')
        rel = v['hpa_iphone'] - v.groupby('track')['hpa_iphone'].transform(lambda h: h[v.loc[h.index, 'floor'] == 5].median())
        axes[1].scatter(v['place'].map(pos) + off(j), rel, s=30, color=SESS_COL[s], marker=SESS_MARK[s], label=SESS_NAME[s],
                        edgecolor='white', linewidth=0.8)
    axes[0].set_ylabel('|B| per 5 s window (uT), iPhone', fontsize=8, color=INK2)
    axes[0].set_title(f"Field strength per place and session (iPhone stops; 23 Nov and 24 s2 = {DN['ip16']} (iPhone17,4), 24 s1 = {DN['ip18']} (iPhone19,2))",
                      fontsize=10, loc='left', color=INK)
    axes[1].set_ylabel('stop pressure minus the session\'s\nfloor-5 median (hPa), iPhone', fontsize=8, color=INK2)
    axes[1].set_title('Barometer per place and session (one dot per stop)', fontsize=10, loc='left', color=INK)
    f5 = sum(P.loc[p, 'floor'] == 5 for p in order)
    for ax in axes:
        style(ax); ax.axvline(f5 - 0.5, color=AX, linewidth=1)
        ax.legend(frameon=False, fontsize=7, loc='upper left', ncol=3, markerscale=1.5)
    axes[1].set_xticks(range(len(order))); axes[1].set_xticklabels([DISP.get(o, o) for o in order], rotation=90, fontsize=7)
    axes[1].text(f5 - 0.4, axes[1].get_ylim()[1], 'floor 4 ->', fontsize=7, color=INK2, va='top')
    save(fig, 'fig_per_place_B_pressure.png')


# ----------------------------------------------------------------------------- embeddings
def embed_all(bank, model):
    W = bank.W
    emb = {}
    mag = W[gknn.NUMERIC['B'] + gknn.NUMERIC['xyz']].to_numpy(float)
    Z = (mag - mag.mean(0)) / mag.std(0)
    emb['magnetic |B|+xyz: PCA'] = (PCA(2, random_state=0).fit_transform(Z), np.arange(len(W)))
    emb['magnetic |B|+xyz: t-SNE'] = (TSNE(2, perplexity=30, random_state=0, init='pca').fit_transform(Z), np.arange(len(W)))
    ti = np.where(W['Bv'].notna())[0]
    T = W.loc[ti, gknn.NUMERIC['B'] + gknn.NUMERIC['tilt']].to_numpy(float)
    T = (T - T.mean(0)) / T.std(0)
    emb['magnetic |B|+tilt (24 Nov only): PCA'] = (PCA(2, random_state=0).fit_transform(T), ti)
    emb['magnetic |B|+tilt (24 Nov only): t-SNE'] = (TSNE(2, perplexity=30, random_state=0, init='pca').fit_transform(T), ti)
    idx = np.arange(len(W))
    sessions = sorted(set(bank.sess))
    dd = bank.dists(idx, idx, gknn.ALL_GROUPS, bank.floor_threshold(sessions))
    Dm = bank.combine(dd, model['weights'])
    Dm = np.nan_to_num(np.sqrt(np.maximum((Dm + Dm.T) / 2, 0)), posinf=np.nanmax(Dm[np.isfinite(Dm)]))
    np.fill_diagonal(Dm, 0)
    emb['fused (learned weights): t-SNE'] = (TSNE(2, metric='precomputed', init='random', perplexity=30, random_state=0).fit_transform(Dm), idx)
    # Wi-Fi: one point per stop visit (Wi-Fi is per stop), MDS on the Wi-Fi distance
    vis = list(bank.V.index)
    has = np.where(bank.wifi_has)[0]
    Dw = np.nan_to_num(bank.wifi_vd[np.ix_(has, has)], nan=1.0)
    Dw = np.sqrt(np.maximum((Dw + Dw.T) / 2, 0)); np.fill_diagonal(Dw, 0)
    xy = MDS(2, metric='precomputed', init='random', random_state=0, n_init=4).fit_transform(Dw)
    emb['_wifi_visits'] = (xy, [vis[i] for i in has])
    return emb


def fig_embeddings(bank, emb, P):
    W = bank.W
    area = P['area'].to_dict()
    keys = [k for k in emb if not k.startswith('_')]
    for k in keys:
        xy, ix = emb[k]
        g = W.iloc[ix].reset_index(drop=True)
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.6))
        for ax, fl in zip(axes, [5, 4]):
            m = (g['floor'] == fl).to_numpy()
            ax.scatter(xy[~m, 0], xy[~m, 1], s=4, color='#e6e5e0', linewidths=0)
            for s in SESSIONS:
                ms = m & (g['session'] == s).to_numpy()
                ax.scatter(xy[ms, 0], xy[ms, 1], s=10, color=SESS_COL[s], marker=SESS_MARK[s], alpha=0.7, linewidths=0, label=SESS_NAME[s])
            for p, gp in g[m].groupby('place'):
                c = xy[gp.index].mean(0)
                ax.text(c[0], c[1], p, fontsize=6.5, color=INK, ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.7))
            ax.set_title(f'floor {fl} windows (grey = other floor)', fontsize=9, loc='left', color=INK)
            style(ax, grid=None); ax.set_xticks([]); ax.set_yticks([])
        axes[0].legend(frameon=False, fontsize=7, loc='best', markerscale=2)
        fig.suptitle(f'{k}: one dot per 5 s stop window, colour = session, label = place centre', fontsize=10, x=0.01, ha='left', color=INK)
        name = 'fig_embed_' + k.split(':')[0].replace(' ', '_').replace('|', '').replace('+', '_').replace('(', '').replace(')', '') + \
               ('_pca' if 'PCA' in k else '_tsne') + '.png'
        save(fig, name)
    # Wi-Fi visits
    xy, vis = emb['_wifi_visits']
    V = bank.V.loc[vis]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    for s in SESSIONS:
        m = (V['session'] == s).to_numpy()
        ax.scatter(xy[m, 0], xy[m, 1], s=30, color=SESS_COL[s], marker=SESS_MARK[s], label=SESS_NAME[s], edgecolor='white', linewidth=0.8)
    for (x, y), p in zip(xy, V['place']):
        ax.text(x, y, p, fontsize=5.5, color=INK2, ha='left', va='bottom')
    ax.set_title('Wi-Fi (s24 WiGLE rows within 120 s of the stop): one dot per stop visit, MDS of the Wi-Fi distance\n'
                 'same place in different sessions should sit together', fontsize=9, loc='left', color=INK)
    style(ax, grid=None); ax.set_xticks([]); ax.set_yticks([]); ax.legend(frameon=False, fontsize=7)
    save(fig, 'fig_embed_wifi_mds.png')


def fig_neighbour_graph(wp, P):
    """Places at graph-v2 positions; arrow A->B = share of A's test windows whose nearest training window is at B (LOSO)."""
    lw = wp[wp['scheme'] == 'leave_one_session_out']
    E = pd.read_csv((data.HERE / data.config()['places_graph']).resolve().parent / 'edges.csv')
    fig, ax = plt.subplots(figsize=(14, 6.5))
    for a, b in zip(E['from'], E['to']):
        if a in P.index and b in P.index:
            ax.plot([P.loc[a, 'x'], P.loc[b, 'x']], [P.loc[a, 'y'], P.loc[b, 'y']], color=GRID, linewidth=3, zorder=1)
    cnt = lw.groupby(['true', 'nearest_neighbour_place']).size().unstack(fill_value=0)
    share = cnt.div(cnt.sum(axis=1), axis=0)
    for a in share.index:
        for b in share.columns:
            s = share.loc[a, b]
            if a == b or s < 0.15:
                continue
            col = S2 if P.loc[a, 'area'] != P.loc[b, 'area'] else S1
            ax.annotate('', xy=(P.loc[b, 'x'], P.loc[b, 'y']), xytext=(P.loc[a, 'x'], P.loc[a, 'y']),
                        arrowprops=dict(arrowstyle='->', color=col, lw=0.5 + 6 * s, alpha=0.6, connectionstyle='arc3,rad=0.15',
                                        shrinkA=8, shrinkB=8), zorder=2)
    for p in P.index:
        s = share.loc[p, p] if p in share.index and p in share.columns else 0
        ax.scatter(P.loc[p, 'x'], P.loc[p, 'y'], s=60 + 500 * s, color='white', edgecolor=INK, linewidth=1.2, zorder=3)
        ax.text(P.loc[p, 'x'], P.loc[p, 'y'] - 1.6, f'{p}\n{s:.0%}', fontsize=6.5, color=INK, ha='center', va='top', zorder=4)
    ax.text(-20, -20, 'FLOOR 5 (metre positions where pinned)', fontsize=9, color=INK2); ax.text(24, -20, 'FLOOR 4 (schematic positions)', fontsize=9, color=INK2)
    ax.plot([], [], color=S1, lw=3, label='nearest neighbour in the same area'); ax.plot([], [], color=S2, lw=3, label='nearest neighbour in another area')
    ax.legend(frameon=False, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.02), ncol=2)
    ax.set_aspect('equal'); ax.axis('off')
    ax.set_title('Where each place\'s windows find their nearest neighbour (fused kNN, leave one session out). Circle size and % = nearest neighbour '
                 'at the right place;\narrows = shares of at least 15% going elsewhere; grey lines = graph-v2 corridors. Source: out/fused_window_predictions.csv', fontsize=9, loc='left', color=INK)
    save(fig, 'fig_knn_neighbour_graph.png')


# ----------------------------------------------------------------------------- interactive HTML
HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WalkSense data explorer</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js" integrity="sha384-cCVCZkAjYNxaYKbM8lsArLznDF/SvMFr1jcZrvOpSTCa0W40ZAdLzHCEulnUa5i7" crossorigin="anonymous"></script>
<style>
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e0}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#3a3a38}}
:root[data-theme="dark"]{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#3a3a38}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
h1{font-size:18px;margin:0 0 4px} p{color:var(--ink2);margin:0 0 10px;max-width:70em}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
select,button{font:inherit;padding:4px 8px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:6px;max-width:100%}
.phonepick,.placepick{font-weight:650}.phonepick select,.placepick select{border:2px solid #2a78d6;font-weight:600}
.plgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:2px 8px;max-height:200px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 8px;margin:4px 0}
.plgrid label{display:flex;align-items:center;gap:4px;font-size:12.5px}
details summary{cursor:pointer;color:var(--ink2);font-size:13px}
.seg{display:inline-flex;align-items:center;gap:6px}.seg .btns{display:inline-flex}
.seg button{border-radius:0;padding:4px 10px;cursor:pointer}.seg button:first-child{border-radius:6px 0 0 6px}.seg button:last-child{border-radius:0 6px 6px 0;border-left:0}
.seg button[aria-pressed=true]{background:#2a78d6;color:#fff;border-color:#2a78d6}
body{overflow-x:hidden}
#plot{width:100%;height:72vh;min-height:420px}
</style></head><body>
<h1>WalkSense: what the stop data looks like</h1>
<p>One dot per 5 s window of a stop recording (Wi-Fi view: one dot per stop). Colour = place (click a legend entry to hide it, double-click to show only that place).
Shape = session: circle 23 Nov, square 24 Nov session 1, triangle 24 Nov session 2, diamond 25 Nov (when present). Hover for place, session, phone and recording.
Use <b>Phone</b>, <b>Session</b> and <b>Place</b> to look at one handset, one day or one place at a time (a place or a floor from the dropdown, or tick several places in the list below), and <b>Colour by phone / session</b> to see where a place's spread comes from (with one place selected the colour switches to phone; colour by session uses the shape for the phone). The variance split per place is in the kNN playground (out/knn_playground.html) and out/variance_by_place.csv. The phone is the real handset (read from each recording's metadata): <span id="phnote"></span>
Same place in different sessions landing together = a fingerprint that carries over; separate clumps per session = drift. Internal team notes, not report text.</p>
<div class="row"><label>View <select id="view"></select></label>
<label class="phonepick">Phone <select id="phone"></select></label>
<label class="placepick">Place <select id="place"></select></label>
<span class="seg" id="colby"><span>Colour by:</span><span class="btns"><button data-c="place" aria-pressed="true">place</button><button data-c="phone" aria-pressed="false">phone</button><button data-c="session" aria-pressed="false">session</button></span></span>
<label>Floor <select id="floor"><option value="all">both</option><option value="5">5</option><option value="4">4</option></select></label>
<label>Session <select id="sess"><option value="all">all</option></select></label></div>
<details id="pldet"><summary>Place checklist (tick several places)</summary>
<div class="row"><button id="plall">all</button><button id="plnone">none</button></div><div class="plgrid" id="plgrid"></div></details>
<div id="plot"></div>
<script>
const DATA = __DATA__;
const SYM = {}, SESSCOL = {};
DATA.sessions.forEach((s, i) => { SYM[s] = ['circle', 'square', 'triangle-up', 'diamond', 'cross', 'star'][i % 6]; SESSCOL[s] = ['#6b4fd8', '#d99a00', '#0e9aa7', '#c2185b', '#5c5c5c', '#2e7d32'][i % 6];
  const o = document.createElement('option'); o.textContent = s; document.getElementById('sess').appendChild(o); });
document.getElementById('phnote').textContent = DATA.phones.map(p => `${DATA.phone_info[p].display} = ${DATA.phone_info[p].model}`).join(', ') + '.';
const pname = p => DATA.phone_info[p] ? DATA.phone_info[p].display : p;
const PHCOL = ['#2a78d6', '#e8812a', '#17a673', '#9b5de5', '#c2185b'];
const view = document.getElementById('view'), fsel = document.getElementById('floor'), ssel = document.getElementById('sess'), psel = document.getElementById('phone');
let colorBy = 'place';
const PHSYM = ['circle', 'square', 'triangle-up', 'diamond', 'cross'];
const NPL = DATA.places.length, placeOn = DATA.places.map(() => true);
const psel2 = document.getElementById('place'), plgrid = document.getElementById('plgrid'), plBoxes = [];
const FLOORS = [...new Set(DATA.floor)].sort((a, b) => b - a);
(function () {
  const add = (v, t, parent) => { const o = document.createElement('option'); o.value = v; o.textContent = t; (parent || psel2).appendChild(o); return o; };
  add('all', 'all places');
  FLOORS.forEach(fl => add('f' + fl, `all floor ${fl}`));
  FLOORS.forEach(fl => { const g = document.createElement('optgroup'); g.label = `floor ${fl}, one place`; psel2.appendChild(g); DATA.places.forEach((p, i) => { if (DATA.floor[i] === fl) add(String(i), p, g); }); });
  add('custom', 'custom (several)').hidden = true;
  DATA.places.forEach((p, i) => {
    const l = document.createElement('label'); l.innerHTML = `<input type="checkbox" checked> ${p} <span style="color:var(--ink2)">F${DATA.floor[i]}</span>`; plgrid.appendChild(l);
    plBoxes.push(l.firstChild); l.firstChild.onchange = e => { placeOn[i] = e.target.checked; placeChanged(); };
  });
})();
function syncPlace() {
  plBoxes.forEach((b, i) => { b.checked = placeOn[i]; });
  const on = placeOn.map((v, i) => v ? i : -1).filter(i => i >= 0);
  let v = 'custom';
  if (on.length === NPL) v = 'all'; else if (on.length === 1) v = String(on[0]);
  else FLOORS.forEach(fl => { if (placeOn.every((b, i) => b === (DATA.floor[i] === fl))) v = 'f' + fl; });
  psel2.value = v;
}
function setColorBy(c) { colorBy = c; document.querySelectorAll('#colby button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.c === c))); }
function placeChanged() { syncPlace(); if (placeOn.filter(Boolean).length === 1 && colorBy === 'place') setColorBy('phone'); draw(); }
psel2.onchange = e => { const v = e.target.value; if (v === 'custom') return; DATA.places.forEach((_, i) => { placeOn[i] = v === 'all' || v === 'f' + DATA.floor[i] || String(i) === v; }); placeChanged(); };
document.getElementById('plall').onclick = () => { placeOn.fill(true); placeChanged(); };
document.getElementById('plnone').onclick = () => { placeOn.fill(false); placeChanged(); };
Object.keys(DATA.views).forEach(k => { const o = document.createElement('option'); o.value = k; o.textContent = k; view.appendChild(o); });
// phone options show how many points the current view has per phone
function fillPhones() {
  const pts = DATA.views[view.value].pts, keep = psel.value || 'all', n = {};
  pts.forEach(q => { n[q[6]] = (n[q[6]] || 0) + 1; });
  psel.innerHTML = '';
  const add = (v, t) => { const o = document.createElement('option'); o.value = v; o.textContent = t; psel.appendChild(o); };
  add('all', `all phones (${pts.length})`);
  DATA.phones.forEach(p => add(p, `${pname(p)} (${n[p] || 0})`));
  psel.value = [...psel.options].some(o => o.value === keep) ? keep : 'all';
}
function draw(){
  const v = DATA.views[view.value], f = fsel.value, s = ssel.value, ph = psel.value;
  const css = getComputedStyle(document.documentElement);
  const keepPt = (q, i) => placeOn[i] && (f === 'all' || String(DATA.floor[i]) === f) && (s === 'all' || q[3] === s) && (ph === 'all' || q[6] === ph);
  const hover = q => `<b>${DATA.places[q[2]]}</b> (floor ${DATA.floor[q[2]]})<br>${q[3]} · ${q[4]}<br>${q[5]}`;
  const mk = (name, ix, color) => ({type: 'scattergl', mode: 'markers', name, x: ix.map(q => q[0]), y: ix.map(q => q[1]),
    marker: {size: v.size, color, symbol: ix.map(q => colorBy === 'session' ? PHSYM[DATA.phones.indexOf(q[6]) % PHSYM.length] : SYM[q[3]]), opacity: 0.8},
    text: ix.map(hover), hovertemplate: '%{text}<extra></extra>'});
  let traces;
  if (colorBy === 'phone') {
    const cnt = {}; v.pts.forEach(q => { cnt[q[6]] = (cnt[q[6]] || 0) + 1; });
    traces = DATA.phones.map((p, j) => mk(`${pname(p)} (${cnt[p] || 0})`, v.pts.filter(q => q[6] === p && keepPt(q, q[2])), PHCOL[j % PHCOL.length]));
  } else if (colorBy === 'session') {
    const ss = [...new Set(v.pts.map(q => q[3]))].sort();
    traces = ss.map(sn => mk(`${sn} (${v.pts.filter(q => q[3] === sn).length})`, v.pts.filter(q => q[3] === sn && keepPt(q, q[2])), SESSCOL[sn] || '#888'));
  } else {
    traces = DATA.places.map((p, i) => mk(p, v.pts.filter(q => q[2] === i && keepPt(q, i)), DATA.colours[i]));
  }
  Plotly.react('plot', traces, {paper_bgcolor: css.getPropertyValue('--bg'), plot_bgcolor: css.getPropertyValue('--bg'),
    font: {color: css.getPropertyValue('--ink'), size: 12}, margin: {l: 40, r: 10, t: 30, b: 40},
    title: {text: view.value, font: {size: 13}, x: 0}, xaxis: {title: v.xl, gridcolor: css.getPropertyValue('--line'), zeroline: false},
    yaxis: {title: v.yl, gridcolor: css.getPropertyValue('--line'), zeroline: false}, legend: {font: {size: 10}}, showlegend: window.innerWidth > 700}, {responsive: true});
}
view.addEventListener('change', fillPhones);
document.querySelectorAll('#colby button').forEach(b => b.addEventListener('click', () => { setColorBy(b.dataset.c); draw(); }));
[view, fsel, ssel, psel].forEach(e => e.addEventListener('change', draw)); fillPhones(); syncPlace(); draw();
window.__ex = {placeOn, placeChanged, setColorBy, draw};
</script></body></html>
"""


def explorer(bank, emb, P):
    W, V = bank.W, bank.V
    mdl = {h: m for h, m in W.groupby('phone')['device'].first().items()}          # handset id -> deviceModel
    phlab = lambda h, m: f'{DN[h]} ({m})'
    places = sorted(P.index, key=lambda p: (-P.loc[p, 'floor'], P.loc[p, 'x']))
    pi = {p: i for i, p in enumerate(places)}
    cmap = plt.get_cmap('tab20')(np.linspace(0, 1, 20)).tolist() + plt.get_cmap('Dark2')(np.linspace(0, 1, 8)).tolist()
    colours = [matplotlib.colors.to_hex(c) for c in cmap[:len(places)]]
    views = {}
    for k, (xy, ix) in emb.items():
        if k.startswith('_'):
            continue
        g = W.iloc[ix]
        views[k] = {'size': 6, 'xl': '', 'yl': '', 'pts': [[round(float(a), 3), round(float(b), 3), pi[p], s, phlab(ph, m), f'{kk} window {w}', ph]
                                                          for (a, b), p, s, ph, m, kk, w in zip(xy, g['place'], g['session'], g['phone'], g['device'], g['key'], g['window'])]}
    xy, vis = emb['_wifi_visits']
    vv = V.loc[vis]
    views['Wi-Fi per stop visit: MDS'] = {'size': 10, 'xl': '', 'yl': '', 'pts': [[round(float(a), 3), round(float(b), 3), pi[p], s, phlab('s24', 'SM-S9280') + ' (Wi-Fi scanner)', v, 's24']
                                                                                   for (a, b), p, s, v in zip(xy, vv['place'], vv['session'], vis)]}
    views['raw: |B| mean vs B_vertical (24 Nov)'] = {'size': 6, 'xl': '|B| mean (uT)', 'yl': 'B_vertical (uT)', 'pts': [
        [round(float(a), 2), round(float(b), 2), pi[p], s, phlab(ph, m), kk, ph] for a, b, p, s, ph, m, kk in
        zip(W['B_mean'], W['Bv'], W['place'], W['session'], W['phone'], W['device'], W['key']) if np.isfinite(b)]}
    Vs = V.reset_index().sort_values('start')
    rel = Vs['hpa_iphone'] - Vs.groupby('track')['hpa_iphone'].transform(lambda h: h.dropna().iloc[0] if h.notna().any() else np.nan)
    tmin = (Vs['start'] - Vs.groupby('session')['start'].transform('min')) / 60
    views['barometer: iPhone pressure per stop vs time'] = {'size': 10, 'xl': 'minutes since first stop', 'yl': 'hPa minus first stop (higher = lower floor)',
                                                            'pts': [[round(float(a), 2), round(float(b), 3), pi[p], s, phlab(h, mdl[h]), v, h]
                                                                    for a, b, p, s, v, h in zip(tmin, rel, Vs['place'], Vs['session'], Vs['visit'], Vs['iphone_handset'])
                                                                    if np.isfinite(b) and h in mdl]}
    payload = {'sessions': [s for s in SESSIONS if s in set(W['session'])], 'phones': sorted(W['phone'].unique()), 'phone_info': {h: {'display': DN[h], 'model': mdl[h]} for h in mdl}, 'places': places, 'floor': [int(P.loc[p, 'floor']) for p in places], 'colours': colours, 'views': views}
    (OUT / 'explore.html').write_text(HTML.replace('__DATA__', json.dumps(payload, separators=(',', ':'))))
    print('wrote explore.html')


def main():
    D = data.load()
    P = data.places()
    R = json.loads((OUT / 'results.json').read_text())
    F = json.loads((OUT / 'fused_knn.json').read_text())
    wp = pd.read_csv(OUT / 'fused_window_predictions.csv')
    bank = gknn.Bank(D, wifi_rows='near', wifi_scanner='s24')
    fig_accuracy(R)
    fig_leaky_vs_honest(F)
    fig_confusion(R, wp, P)
    fig_floor(D['V'], R)
    fig_per_place(D['W'], D['V'], P)
    fig_neighbour_graph(wp, P)
    emb = embed_all(bank, F['deployable_model'])
    fig_embeddings(bank, emb, P)
    explorer(bank, emb, P)


if __name__ == '__main__':
    main()
