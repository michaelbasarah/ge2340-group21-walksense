#!/usr/bin/env python3
"""Evaluate the request-matching methods on test_queries.csv (split dev / test made before any run).

  python evaluate.py --phase dev     tune on the DEV rows only: embedding "none" thresholds -> tuned.json,
                                     LLM answers for dev rows (cached); writes out/dev_results.json
  python evaluate.py --phase final   run everything on dev + test with the frozen settings; writes
                                     results.json, results.csv, failures.csv, confusion_pairs.csv, results.png
Needs: sentence-transformers, matplotlib (see README). LLM answers come from llm_cache_<version>.json;
missing ones are fetched with the Claude CLI (internet) unless --no-llm-calls.
"""
import argparse
import csv
import json
import platform
import statistics
import time
from collections import Counter
from datetime import date
from pathlib import Path

import match as M

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
MAIN = ['keyword', 'embed', 'llm']
ALL = MAIN + ['embed_doc', 'keyword_v1', 'tokens']


def is_ok(pred, expected, by_id):
    if expected == 'NONE':
        return pred is None
    if pred is None:
        return False
    for opt in expected.split('|'):
        if opt.startswith('tag:'):
            if opt[4:] in by_id[pred]['tag_set']:
                return True
        elif pred == opt:
            return True
    return False


def load_queries():
    return list(csv.DictReader((ROOT / 'test_queries.csv').open(encoding='utf-8')))


def run_method(method, queries, places, allow_calls):
    """One dict per query: pred (id/None), score, ms, invalid."""
    rows = []
    if method.startswith('embed'):
        M.match('warm up', method)                       # load model + place vectors outside the timing
    for q in queries:
        if method == 'llm':
            r = M.llm_answer(q['query'], places, allow_call=allow_calls)
            if r is None:
                rows.append({'pred': None, 'score': 0.0, 'ms': None, 'invalid': False, 'missing': True}); continue
            pred = r['parsed'] if r['valid'] and r['parsed'] != 'NONE' else None
            rows.append({'pred': pred, 'score': 1.0 if pred else 0.0, 'ms': r['latency_s'] * 1000, 'api_ms': r['api_ms'],
                         'invalid': not r['valid'], 'raw': r['raw'], 'cost': r['cost_usd']})
        else:
            t0 = time.perf_counter()
            pred, score = M.match(q['query'], method)
            rows.append({'pred': pred, 'score': float(score), 'ms': (time.perf_counter() - t0) * 1000, 'invalid': False})
    return rows


def metrics(idx, queries, res, by_id):
    n = len(idx)
    if not n:
        return None
    ok = [is_ok(res[i]['pred'], queries[i]['expected'], by_id) and not res[i]['invalid'] for i in idx]
    out = {'n': n, 'correct': sum(ok), 'accuracy': round(sum(ok) / n, 4)}
    exp_none = [i for i in idx if queries[i]['expected'] == 'NONE']
    pred_none = [i for i in idx if res[i]['pred'] is None and not res[i]['invalid']]
    tp = len([i for i in pred_none if queries[i]['expected'] == 'NONE'])
    out['reject'] = {'expected_none': len(exp_none), 'predicted_none': len(pred_none), 'true_none': tp,
                     'precision': round(tp / len(pred_none), 4) if pred_none else None,
                     'recall': round(tp / len(exp_none), 4) if exp_none else None}
    sup = [i for i in idx if queries[i]['expected'] != 'NONE']
    out['supported_only'] = {'n': len(sup), 'correct': sum(1 for i in sup if is_ok(res[i]['pred'], queries[i]['expected'], by_id) and not res[i]['invalid']),
                             'wrongly_rejected': sum(1 for i in sup if res[i]['pred'] is None and not res[i]['invalid'])}
    out['invalid'] = sum(1 for i in idx if res[i]['invalid'])
    ms = sorted(res[i]['ms'] for i in idx if res[i].get('ms') is not None)
    if ms:
        out['latency_ms'] = {'mean': round(statistics.mean(ms), 3), 'median': round(statistics.median(ms), 3),
                             'p95': round(ms[min(len(ms) - 1, int(0.95 * len(ms)))], 3), 'max': round(ms[-1], 3)}
    return out


def slices(queries):
    def sel(f):
        return [i for i, q in enumerate(queries) if f(q)]
    s = {'all': sel(lambda q: True), 'easy': sel(lambda q: q['set'] == 'easy'), 'hard': sel(lambda q: q['set'] == 'hard'),
         'dev': sel(lambda q: q['split'] == 'dev'), 'test': sel(lambda q: q['split'] == 'test'),
         'easy_dev': sel(lambda q: q['set'] == 'easy' and q['split'] == 'dev'),
         'easy_test': sel(lambda q: q['set'] == 'easy' and q['split'] == 'test'),
         'hard_dev': sel(lambda q: q['set'] == 'hard' and q['split'] == 'dev'),
         'hard_test': sel(lambda q: q['set'] == 'hard' and q['split'] == 'test')}
    for cat in sorted({q['category'] for q in queries if q['set'] == 'hard'}):
        s['hard:' + cat] = sel(lambda q, c=cat: q['set'] == 'hard' and q['category'] == c)
    return {k: v for k, v in s.items() if v}


def tune_threshold(variant, queries, places, by_id):
    """Pick the cosine cut-off that maximises dev accuracy (queries = dev rows only). Ties: median of the best."""
    tops = []
    for q in queries:
        sc = M.embed_scores(q['query'], places, variant)
        i = max(range(len(sc)), key=sc.__getitem__)
        tops.append((places[i]['place_id'], sc[i]))
    curve = []
    for k in range(0, 91):
        th = k / 100
        acc = sum(is_ok(p if s >= th else None, q['expected'], by_id) for (p, s), q in zip(tops, queries)) / len(queries)
        curve.append((th, acc))
    best = max(a for _, a in curve)
    ths = [t for t, a in curve if abs(a - best) < 1e-12]
    return {'threshold': round(statistics.median(ths), 3), 'dev_accuracy': round(best, 4), 'best_range': [min(ths), max(ths)],
            'dev_accuracy_at_0': round(curve[0][1], 4), 'n_dev': len(queries)}


def figure(results, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cols = {'keyword': '#0072B2', 'embed': '#E69F00', 'llm': '#009E73'}
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={'width_ratios': [3, 2]})
    groups = [('easy', 'easy (23)'), ('hard_dev', 'hard dev'), ('hard_test', 'hard test'), ('test', 'all test')]
    w = 0.26
    for j, m in enumerate(MAIN):
        vals = [results[m]['slices'][g]['accuracy'] for g, _ in groups]
        b = ax[0].bar([i + (j - 1) * w for i in range(len(groups))], vals, w, label=m, color=cols[m])
        for r, v in zip(b, vals):
            ax[0].text(r.get_x() + r.get_width() / 2, v + 0.01, f'{v:.0%}', ha='center', fontsize=7)
    ax[0].set_xticks(range(len(groups)))
    ax[0].set_xticklabels([n.replace('(23)', f"({results['keyword']['slices']['easy']['n']})") if g == 'easy' else
                           f"{n} ({results['keyword']['slices'][g]['n']})" for g, n in groups], fontsize=8)
    ax[0].set_ylim(0, 1.12); ax[0].set_ylabel('top-1 accuracy'); ax[0].set_title('Accuracy per split')
    ax[0].legend(fontsize=8, frameon=False, ncol=3, loc='upper center', bbox_to_anchor=(0.5, -0.12))
    w2 = 0.35
    for j, key in enumerate(('precision', 'recall')):
        vals = [(results[m]['slices']['hard']['reject'][key] or 0) for m in MAIN]
        b = ax[1].bar([i + (j - 0.5) * w2 for i in range(3)], vals, w2, label=f'rejection {key}', color=['#56B4E9', '#CC79A7'][j])
        for r, v in zip(b, vals):
            ax[1].text(r.get_x() + r.get_width() / 2, v + 0.01, f'{v:.0%}', ha='center', fontsize=7)
    ax[1].set_xticks(range(3)); ax[1].set_xticklabels(MAIN, fontsize=8); ax[1].set_ylim(0, 1.12)
    ax[1].set_title('"none" handling, hard set'); ax[1].legend(fontsize=8, frameon=False, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.12))
    for a in ax:
        a.spines[['top', 'right']].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=150)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['dev', 'final'], required=True)
    ap.add_argument('--no-llm-calls', action='store_true')
    ap.add_argument('--methods', default=','.join(ALL))
    a = ap.parse_args()
    places = M.load_places()
    by_id = {d['place_id']: d for d in places}
    queries = load_queries()
    methods = a.methods.split(',')
    OUT.mkdir(exist_ok=True)
    if a.phase == 'dev':
        queries = [q for q in queries if q['split'] == 'dev']      # test rows are not even loaded
        tuned = {}
        for v in ('embed', 'embed_doc'):
            if v in methods:
                tuned[v] = tune_threshold(v, queries, places, by_id)
        if tuned:
            (ROOT / 'tuned.json').write_text(json.dumps({**tuned, 'tuned_on': 'dev split only', 'date': str(date.today()),
                                                         'embed_model': M.EMBED_MODEL}, indent=1), encoding='utf-8')
            print('tuned.json:', tuned)
    results = {}
    per_query = {}
    for m in methods:
        res = run_method(m, queries, places, not a.no_llm_calls)
        if any(r.get('missing') for r in res):
            print(f'{m}: {sum(1 for r in res if r.get("missing"))} queries have no cached answer'); continue
        per_query[m] = res
        results[m] = {'slices': {k: metrics(v, queries, res, by_id) for k, v in slices(queries).items()}}
        s = results[m]['slices']
        print(f"{m:11} " + '  '.join(f"{k} {s[k]['correct']}/{s[k]['n']}" for k in ('easy', 'hard', 'dev', 'test') if k in s))
    if a.phase == 'dev':
        (OUT / 'dev_results.json').write_text(json.dumps({'date': str(date.today()), 'rows': len(queries), 'methods': results}, indent=1), encoding='utf-8')
        # failures on dev only, to read while tuning (test failures are not looked at before the final run)
        for m in methods:
            if m in per_query:
                for q, r in zip(queries, per_query[m]):
                    if not (is_ok(r['pred'], q['expected'], by_id) and not r['invalid']):
                        print(f"  FAIL {m:10} {q['id']} {q['query'][:44]:44} exp {q['expected'][:28]:28} got {r['pred'] or ('INVALID:' + r['raw'][:20] if r['invalid'] else 'none')}")
        return
    # ---------------- final: write all artefacts
    llm_cache = M._load_cache()
    llm_rows = [v for v in llm_cache['responses'].values()]
    meta = {'date': str(date.today()), 'python': platform.python_version(), 'n_queries': len(queries),
            'n_places': len(places), 'split_counts': dict(Counter(q['set'] + '/' + q['split'] for q in queries)),
            'embed_model': M.EMBED_MODEL, 'thresholds': json.loads((ROOT / 'tuned.json').read_text(encoding='utf-8')),
            'llm': {'cli_model_flag': M.LLM_MODEL, 'models_reported': sorted({r['model'] for r in llm_rows if r.get('model')}),
                    'prompt_version': M.LLM_PROMPT_VERSION, 'cache_file': M.llm_cache_path().name,
                    'cached_responses': len(llm_rows), 'total_cost_usd': round(sum(r['cost_usd'] or 0 for r in llm_rows), 5),
                    'note': 'latency = wall clock of the whole claude -p call (process start included)'},
            'offline': {'keyword': True, 'embed': True, 'embed_doc': True, 'keyword_v1': True, 'tokens': True, 'llm': False},
            'offline_note': 'embed needs the one-off model download (about 90 MB), then runs without internet'}
    for m in results:
        results[m]['offline'] = meta['offline'][m]
    (ROOT / 'results.json').write_text(json.dumps({'meta': meta, 'methods': results}, indent=1, ensure_ascii=False), encoding='utf-8')
    cols = ['id', 'query', 'expected', 'set', 'category', 'split', 'source']
    with (ROOT / 'results.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(cols + [f'{m}_{c}' for m in per_query for c in ('pred', 'score', 'ok', 'ms')])
        for i, q in enumerate(queries):
            row = [q[c] for c in cols]
            for m in per_query:
                r = per_query[m][i]
                ok = is_ok(r['pred'], q['expected'], by_id) and not r['invalid']
                row += ['INVALID' if r['invalid'] else (r['pred'] or 'none'), round(r['score'], 4), ok,
                        round(r['ms'], 3) if r['ms'] is not None else '']
            w.writerow(row)
    pairs = Counter()
    with (ROOT / 'failures.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['method', 'id', 'split', 'set', 'category', 'query', 'expected', 'predicted', 'score', 'llm_raw'])
        for m in per_query:
            for q, r in zip(queries, per_query[m]):
                if not (is_ok(r['pred'], q['expected'], by_id) and not r['invalid']):
                    got = 'INVALID' if r['invalid'] else (r['pred'] or 'none')
                    w.writerow([m, q['id'], q['split'], q['set'], q['category'], q['query'], q['expected'], got,
                                round(r['score'], 4), r.get('raw', '') if m == 'llm' else ''])
                    pairs[(m, q['expected'], got)] += 1
    with (ROOT / 'confusion_pairs.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['method', 'expected', 'predicted', 'count'])
        for (m, e, g), c in sorted(pairs.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])):
            w.writerow([m, e, g, c])
    figure(results, ROOT / 'results.png')
    print('wrote results.json results.csv failures.csv confusion_pairs.csv results.png')


if __name__ == '__main__':
    main()
