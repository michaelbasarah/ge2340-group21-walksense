#!/usr/bin/env python3
"""GE2340 positioning pilot — feasibility check on the 2026-11-17 session.

WHAT THIS IS
  A dry run of the positioning pipeline on ONE collected session, to answer:
    1. Can the magnetometer tell the 26 stops apart at all? (method C feasibility)
    2. Does the barometer cleanly separate the two floors? (part of method D)
    3. Is the training/evaluation code working, ready for more days of data?

WHAT THIS IS NOT
  A real accuracy result. With a single visit per stop, train and test slices come
  from the SAME walk, so the numbers below are OPTIMISTIC (upper bound), not the
  grade result. The real evaluation needs a different day's visit as the test set
  (train on days 1-2, test on day 3). Wi-Fi is excluded here because scan throttling
  left 12 of 26 stops with no Wi-Fi in this session.

Run:  python pilot_train.py
Reads the cleaned dataset in ../clean-data/2026-11-17/.
Writes features, metrics and figures into ./out/.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, silhouette_score, confusion_matrix

ROOT = Path(__file__).resolve().parent
DATA = ROOT / '..' / 'clean-data' / '2026-11-17'
OUT = ROOT / 'out'; OUT.mkdir(exist_ok=True)
WINDOW_S = 2.0          # slice length (the plan's 2-second windows)
MIN_READINGS = 40       # minimum magnetometer readings to accept a slice
MAG_FEATURES = ['mag_mean', 'mag_std', 'mag_min', 'mag_max', 'x_mean', 'y_mean', 'z_mean']

def load():
    s = pd.read_csv(DATA / 'sensor_samples.csv')
    loc = pd.read_csv(DATA / 'locations_provisional.csv')
    label = dict(zip(loc['stop_id'], loc['location_label']))
    order = [f'BM{n:02}' for n in range(1, 27)]      # route order
    return s, label, order

def build_slices(samples, order):
    """Cut each stop's magnetometer stream into 2 s windows and summarise each."""
    mag = samples[(samples['sensor'] == 'magnetometer')].copy()
    baro = samples[samples['sensor'] == 'barometer']
    stop_pressure = baro.groupby('session_id')['x'].median()
    rows = []
    for sid, g in mag.groupby('session_id'):
        g = g.sort_values('relative_time_s')
        win = (g['relative_time_s'] // WINDOW_S).astype(int)
        for w, gw in g.groupby(win):
            if len(gw) < MIN_READINGS:
                continue
            m = gw['vector_magnitude'].to_numpy()
            rows.append({'stop_id': sid, 'window': int(w), 'route_index': order.index(sid),
                         'mag_mean': m.mean(), 'mag_std': m.std(), 'mag_min': m.min(), 'mag_max': m.max(),
                         'x_mean': gw['x'].mean(), 'y_mean': gw['y'].mean(), 'z_mean': gw['z'].mean(),
                         'pressure': stop_pressure[sid], 'n_readings': len(gw)})
    return pd.DataFrame(rows)

def temporal_split(df):
    """First 60% of each stop's slices -> train, last 40% -> test (temporally separated)."""
    train, test = [], []
    for sid, g in df.groupby('stop_id'):
        g = g.sort_values('window'); k = max(1, int(round(len(g) * 0.6)))
        train.append(g.iloc[:k]); test.append(g.iloc[k:])
    return pd.concat(train), pd.concat(test)

def floor_labels(df):
    """Cluster stops into two floors by their median pressure."""
    per_stop = df.groupby('stop_id')['pressure'].first()
    km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(per_stop.to_numpy().reshape(-1, 1))
    # Lower pressure cluster = upper floor.
    hi_cluster = int(np.argmin(km.cluster_centers_.ravel()))
    floor = {sid: ('upper' if c == hi_cluster else 'lower') for sid, c in zip(per_stop.index, km.labels_)}
    return floor, per_stop

def main():
    samples, label, order = load()
    df = build_slices(samples, order)
    df.to_csv(OUT / 'magnetic_slices.csv', index=False)
    floor, per_stop = floor_labels(df)
    df['floor'] = df['stop_id'].map(floor)

    train, test = temporal_split(df)
    Xtr, Xte = train[MAG_FEATURES].to_numpy(), test[MAG_FEATURES].to_numpy()
    ytr, yte = train['stop_id'].to_numpy(), test['stop_id'].to_numpy()
    scaler = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)

    results = {'session': '2026-11-17', 'slices_total': len(df), 'slices_train': len(train), 'slices_test': len(test),
               'stops': int(df['stop_id'].nunique()), 'window_seconds': WINDOW_S,
               'DISCLAIMER': 'Single-session OPTIMISTIC upper bound (train/test from same visit). Not a day-3 result.'}

    knn = KNeighborsClassifier(n_neighbors=5).fit(Xtr_s, ytr)
    rf = RandomForestClassifier(n_estimators=300, random_state=0).fit(Xtr, ytr)
    nc = NearestCentroid().fit(Xtr_s, ytr)
    for name, model, X in [('knn_magnetic', knn, Xte_s), ('randomforest_magnetic', rf, Xte), ('nearest_centroid_magnetic', nc, Xte_s)]:
        pred = model.predict(X)
        idx_true = np.array([order.index(s) for s in yte])
        idx_pred = np.array([order.index(s) for s in pred])
        results[name] = {
            'stop_accuracy': round(accuracy_score(yte, pred), 3),
            'stop_accuracy_within_1_stop': round(float(np.mean(np.abs(idx_true - idx_pred) <= 1)), 3),
            'floor_accuracy': round(float(np.mean([floor[a] == floor[b] for a, b in zip(yte, pred)])), 3)}

    # Separability independent of any classifier.
    Xall = StandardScaler().fit_transform(df[MAG_FEATURES].to_numpy())
    results['magnetic_separability'] = {
        'silhouette_by_stop_26_classes': round(float(silhouette_score(Xall, df['stop_id'])), 3),
        'silhouette_by_floor_2_classes': round(float(silhouette_score(Xall, df['floor'])), 3),
        'note': 'Silhouette ~>0.5 strong, ~0.25-0.5 some structure, <0.25 weak/overlapping.'}
    results['barometer_floor_split'] = {
        'upper_floor_stops': sorted([s for s, f in floor.items() if f == 'upper']),
        'lower_floor_stops': sorted([s for s, f in floor.items() if f == 'lower']),
        'upper_median_hpa': round(float(per_stop[[s for s, f in floor.items() if f == 'upper']].median()), 3),
        'lower_median_hpa': round(float(per_stop[[s for s, f in floor.items() if f == 'lower']].median()), 3)}

    (OUT / 'results.json').write_text(json.dumps(results, indent=2))

    # ---- Figures ----
    # 1) Pressure per stop, coloured by floor.
    fig, ax = plt.subplots(figsize=(11, 4))
    colors = ['#126782' if floor[s] == 'upper' else '#d97915' for s in order]
    ax.bar(range(len(order)), [per_stop[s] for s in order], color=colors)
    ax.set_xticks(range(len(order))); ax.set_xticklabels([s[2:] for s in order], fontsize=8)
    ax.set_xlabel('stop (BM)'); ax.set_ylabel('median pressure (hPa)')
    ax.set_title('Barometer per stop — teal = upper floor, orange = lower floor')
    ax.set_ylim(min(per_stop) - 0.1, max(per_stop) + 0.1)
    fig.tight_layout(); fig.savefig(OUT / 'pressure_per_stop.png', dpi=120); plt.close(fig)

    # 2) PCA of magnetic slices, coloured by floor.
    pca = PCA(n_components=2).fit_transform(Xall)
    fig, ax = plt.subplots(figsize=(7, 6))
    for f, c in [('upper', '#126782'), ('lower', '#d97915')]:
        m = (df['floor'] == f).to_numpy()
        ax.scatter(pca[m, 0], pca[m, 1], s=12, alpha=0.6, label=f'{f} floor', color=c)
    ax.legend(); ax.set_xlabel('PC1'); ax.set_ylabel('PC2')
    ax.set_title('Magnetic 2 s slices (PCA) — do stops/floors separate?')
    fig.tight_layout(); fig.savefig(OUT / 'magnetic_pca.png', dpi=120); plt.close(fig)

    # Readable "guess vs truth" table: each held-back slice, the model's guess, right/wrong.
    pred = knn.predict(Xte_s)
    guesses = pd.DataFrame({
        'true_stop': yte, 'true_place': [label[s] for s in yte],
        'window_2s': test['window'].to_numpy(),
        'knn_guess': pred, 'guess_place': [label[s] for s in pred],
        'correct': (yte == pred)})
    guesses.to_csv(OUT / 'predictions_true_vs_guess.csv', index=False)
    shown = guesses.head(20)[['true_stop', 'true_place', 'knn_guess', 'guess_place', 'correct']]
    print('\n--- Sample of the test: what the model guessed vs the real answer ---')
    print(shown.to_string(index=False))
    print(f"...({len(guesses)} held-back slices total; {int(guesses['correct'].sum())} correct = "
          f"{guesses['correct'].mean():.1%} — single-session optimistic.)")

    # 3) Confusion matrix for the kNN (stop level).
    cm = confusion_matrix(yte, pred, labels=order)
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, cmap='Blues')
    ax.set_xticks(range(len(order))); ax.set_xticklabels([s[2:] for s in order], fontsize=6, rotation=90)
    ax.set_yticks(range(len(order))); ax.set_yticklabels([s[2:] for s in order], fontsize=6)
    ax.set_xlabel('predicted stop'); ax.set_ylabel('true stop')
    ax.set_title('Magnetic kNN confusion (single-session, optimistic)')
    fig.colorbar(im, ax=ax, shrink=0.8); fig.tight_layout(); fig.savefig(OUT / 'confusion_knn.png', dpi=120); plt.close(fig)

    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
