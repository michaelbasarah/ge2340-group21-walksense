#!/usr/bin/env python3
"""Does pooling iPhone 16 (iPhone17,4) training data with iPhone 18 (iPhone19,2) data help when testing on iPhone 18?

Same recipe and scoring as `walksense.py evaluate` (out/eval.json): 2 s windows, per-floor kNN (crossday.make_model),
visit answer = mean kNN probability over its windows among the places on the true floor, leave one session out.
walksense.py is imported read-only; nothing in out/eval.json is touched. Writes out/iphone_pool.json.

  python eval_iphone_pool.py            # all folds, about 3 min

Training sets for each held-out session (the 'iphone' phone folder only):
  a  ip18 only        = the other ip18 sessions (must equal eval.json same_model)
  b  ip18 + ip16      = the other ip18 sessions + ALL ip16 sessions
  c  ip16 only        = all ip16 sessions (must equal eval.json cross_handset)
ip18 sessions: sesi1, 25nov, 25night (Dicta, iPhone19,2). ip16 sessions: sesi2, 25night_tian, 26tian (Tian, iPhone17,4).
The 23-Nov session is NOT in walksense.ALL_SESSIONS (different tree: sensor_samples.csv, no clean/manifest.csv), so it is not used.
Supplementary: the mirror test (held-out ip16 sessions: ip16-only vs pooled), and an exploratory per-session x phone median-xyz offset.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import walksense as w                          # noqa: E402  (read-only use)
from crossday import make_model                # noqa: E402

IP18, IP16 = 'iPhone19,2', 'iPhone17,4'
S18 = ['sesi1', '25nov', '25night']
S16 = ['sesi2', '25night_tian', '26tian']
EVAL = HERE / 'out' / 'eval.json'
OUT = HERE / 'out' / 'iphone_pool.json'


class OffsetModel:
    """PlaceModel with an optional per-(session, phone) offset subtracted from the xyz windows (exploratory).
    With offsets=None it is the same model as walksense.PlaceModel (checked below)."""

    def __init__(self, stops, kind='xyz', offsets=None):
        self.kind, self.offsets, self.models, self.places = kind, offsets, {}, {}
        for floor in sorted({s['floor'] for s in stops}):
            X, y = [], []
            for s in (s for s in stops if s['floor'] == floor):
                f = self.feat(s)
                X.append(f); y += [s['place']] * len(f)
            X = np.vstack(X)
            self.models[floor] = make_model('knn', len(y)).fit(X, y)
            self.places[floor] = sorted(set(y))

    def feat(self, s):
        f = w.stop_features(s['rec'], self.kind)
        if self.offsets is not None and len(f):
            f = f - self.offsets[s['session']]
        return f

    def top3(self, st):
        if st['floor'] not in self.models:
            return []
        f = self.feat(st)
        if not len(f):
            return []
        m = self.models[st['floor']]
        p = m.predict_proba(f).mean(0)
        order = np.argsort(-p)[:3]
        return [(str(m.classes_[i]), round(float(p[i]), 3)) for i in order]


def load():
    stops = {}
    for s in S18 + S16:
        stops[s] = w.training_stops(sessions=(s,), phone='iphone')
        devs = {r['device'] for r in stops[s]}
        assert devs == {IP18 if s in S18 else IP16}, (s, devs)
    return stops


def offsets_for(stops):
    """Median xyz over all 2 s windows of every stop of a session (all floors). Test session included (transductive)."""
    out = {}
    for s, st in stops.items():
        out[s] = np.median(np.vstack([w.stop_features(r['rec'], 'xyz') for r in st]), axis=0)
    return out


def predict(model, te):
    rows = []
    for st in te:
        t3 = model.top3(st['rec'], st['floor']) if isinstance(model, w.PlaceModel) else model.top3(st)
        t3 = t3 or [('', 0.0)]
        rows.append({'session': st['session'], 'floor': st['floor'], 'truth': st['place'], 'guess': t3[0][0], 'p': t3[0][1],
                     'top3': st['place'] in [p for p, _ in t3]})
    return rows


def macro(rows):
    """Macro precision / recall over (floor, place) classes that occur as truth or as a guess in rows.
    recall = TP / true visits; precision = TP / guesses (0 if never guessed)."""
    tp, n_true, n_pred = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in rows:
        n_true[(r['floor'], r['truth'])] += 1
        n_pred[(r['floor'], r['guess'])] += 1
        tp[(r['floor'], r['truth'])] += r['guess'] == r['truth']
    truths = list(n_true)
    rec = [tp[c] / n_true[c] for c in truths]
    prec = [tp[c] / n_pred[c] if n_pred[c] else 0.0 for c in truths]    # classes with at least one true visit
    return {'macro_recall': round(float(np.mean(rec)), 3), 'macro_precision': round(float(np.mean(prec)), 3),
            'n_classes': len(truths),
            'n_classes_never_guessed': sum(1 for c in truths if not n_pred[c])}


def summarise(rows):
    n = len(rows)
    t1 = sum(r['guess'] == r['truth'] for r in rows)
    t3 = sum(r['top3'] for r in rows)
    return {'top1': f'{t1}/{n}', 'top1_acc': round(t1 / n, 3), 'top3': f'{t3}/{n}', 'top3_acc': round(t3 / n, 3), **macro(rows)}


def per_place(rows):
    d = defaultdict(lambda: [0, 0])
    for r in rows:
        d[f"{r['floor']}F {r['truth']}"][0] += r['guess'] == r['truth']
        d[f"{r['floor']}F {r['truth']}"][1] += 1
    return {k: f'{a}/{b}' for k, (a, b) in sorted(d.items())}


def wins_losses(rows_b, rows_a):
    """Per place: stops that are right in b and wrong in a (win) and the reverse (loss)."""
    d = defaultdict(lambda: [0, 0])
    for rb, ra in zip(rows_b, rows_a):
        assert (rb['session'], rb['truth'], rb['floor']) == (ra['session'], ra['truth'], ra['floor'])
        ok_b, ok_a = rb['guess'] == rb['truth'], ra['guess'] == ra['truth']
        k = f"{rb['floor']}F {rb['truth']}"
        d[k][0] += ok_b and not ok_a
        d[k][1] += ok_a and not ok_b
    return {k: {'wins': a, 'losses': b} for k, (a, b) in sorted(d.items()) if a or b}


def run_setting(stops, test_sessions, own, other, kind, offsets=None):
    """own = sessions of the test phone, other = sessions of the other phone. Returns {a, b, c} rows, concatenated over folds."""
    res = {'a': [], 'b': [], 'c': []}
    for t in test_sessions:
        te = stops[t]
        tr_a = [r for s in own if s != t for r in stops[s]]
        tr_o = [r for s in other for r in stops[s]]
        for key, tr in (('a', tr_a), ('b', tr_a + tr_o), ('c', tr_o)):
            m = OffsetModel(tr, kind, offsets) if offsets is not None else w.PlaceModel(tr, kind)
            res[key] += predict(m, te)
    return res


def block(res, test_sessions):
    out = {}
    for key, name in (('a', 'own phone only'), ('b', 'own + other phone pooled'), ('c', 'other phone only')):
        rows = res[key]
        out[key] = {'train': name, 'total': summarise(rows),
                    'per_session': {t: summarise([r for r in rows if r['session'] == t]) for t in test_sessions}}
    out['per_place_top1'] = {k: per_place(res[k]) for k in 'abc'}
    out['b_vs_a'] = {'wins_total': sum(v['wins'] for v in wins_losses(res['b'], res['a']).values()),
                     'losses_total': sum(v['losses'] for v in wins_losses(res['b'], res['a']).values()),
                     'by_place': wins_losses(res['b'], res['a'])}
    out['c_vs_a'] = {'wins_total': sum(v['wins'] for v in wins_losses(res['c'], res['a']).values()),
                     'losses_total': sum(v['losses'] for v in wins_losses(res['c'], res['a']).values())}
    return out


def check_against_eval(res18, stops):
    """a and c on xyz/tilt/magnitude must equal out/eval.json (same_model / cross_handset), per held-out ip18 session."""
    ev = json.load(open(EVAL))['place']
    keymap = {'a': {'sesi1': 'iphone 25nov+25night->sesi1', '25nov': 'iphone sesi1+25night->25nov', '25night': 'iphone sesi1+25nov->25night'},
              'c': {'sesi1': 'iphone sesi2+25night_tian+26tian->sesi1', '25nov': 'iphone sesi2+25night_tian+26tian->25nov',
                    '25night': 'iphone sesi2+25night_tian+26tian->25night'}}
    report = {}
    for kind, rr in res18.items():
        for key in 'ac':
            for t in S18:
                rows = [r for r in rr[key] if r['session'] == t]
                got = (f"{sum(r['guess'] == r['truth'] for r in rows)}/{len(rows)}", f"{sum(r['top3'] for r in rows)}/{len(rows)}")
                e = ev[f'{keymap[key][t]} {kind}']
                want = (e['top1'], e['top3'])
                report[f'{kind} {key} {t}'] = {'got_top1_top3': list(got), 'eval_json_top1_top3': list(want), 'match': got == want}
    return report


def main():
    stops = load()
    n18 = sum(len(stops[s]) for s in S18)
    n16 = sum(len(stops[s]) for s in S16)
    print(f'ip18 stops {n18} ({ {s: len(stops[s]) for s in S18} }), ip16 stops {n16} ({ {s: len(stops[s]) for s in S16} })', flush=True)
    result = {'what': __doc__.strip().split('\n\n')[0], 'train_sets': {'a': 'ip18 only (other ip18 sessions)', 'b': 'ip18 other sessions + all ip16 sessions',
              'c': 'ip16 only (all ip16 sessions)'}, 'ip18_sessions': S18, 'ip16_sessions': S16,
              'n_test_stops_ip18': n18, 'n_test_stops_ip16': n16,
              'not_used': '23-Nov is not loadable by walksense.py (ALL_SESSIONS has no 23-Nov entry; its tree has sensor_samples.csv, no clean/manifest.csv)',
              'scoring': 'visit answer = mean kNN probability over 2 s windows among places on the true floor. macro precision/recall over (floor, place) '
                         'classes with >=1 true visit; precision of a never-guessed class counts 0.',
              'test_on_ip18': {}, 'test_on_ip16_mirror': {}, 'exploratory_offset': {}}
    res18 = {}
    for kind in ('xyz', 'tilt', 'magnitude'):
        res18[kind] = run_setting(stops, S18, S18, S16, kind)
        result['test_on_ip18'][kind] = block(res18[kind], S18)
        print(kind, {k: result['test_on_ip18'][kind][k]['total']['top1'] for k in 'abc'}, flush=True)
    result['check_against_eval_json'] = check_against_eval(res18, stops)
    result['check_all_match'] = all(v['match'] for v in result['check_against_eval_json'].values())
    print('matches eval.json:', result['check_all_match'], flush=True)
    for kind in ('xyz', 'tilt', 'magnitude'):          # mirror: test on ip16 sessions; a = ip16 only, c = ip18 only
        r16 = run_setting(stops, S16, S16, S18, kind)
        result['test_on_ip16_mirror'][kind] = block(r16, S16)
        print('mirror', kind, {k: result['test_on_ip16_mirror'][kind][k]['total']['top1'] for k in 'abc'}, flush=True)
    off = offsets_for(stops)                            # exploratory: subtract the session x phone median xyz
    result['exploratory_offset']['offsets_xyz_uT'] = {s: [round(float(x), 2) for x in v] for s, v in off.items()}
    ctrl = run_setting(stops, S18, S18, S16, 'xyz', offsets={s: np.zeros(3) for s in off})
    result['exploratory_offset']['control_zero_offset_equals_plain'] = all(
        [(r['guess']) for r in ctrl[k]] == [r['guess'] for r in res18['xyz'][k]] for k in 'abc')
    r_off = run_setting(stops, S18, S18, S16, 'xyz', offsets=off)
    result['exploratory_offset']['test_on_ip18_xyz'] = block(r_off, S18)
    print('offset', {k: result['exploratory_offset']['test_on_ip18_xyz'][k]['total']['top1'] for k in 'abc'}, flush=True)
    r16o = run_setting(stops, S16, S16, S18, 'xyz', offsets=off)
    result['exploratory_offset']['test_on_ip16_mirror_xyz'] = block(r16o, S16)
    print('offset mirror', {k: result['exploratory_offset']['test_on_ip16_mirror_xyz'][k]['total']['top1'] for k in 'abc'}, flush=True)
    OUT.write_text(json.dumps(result, indent=1))
    print('wrote', OUT)


if __name__ == '__main__':
    main()
