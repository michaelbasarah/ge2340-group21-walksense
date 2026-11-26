#!/usr/bin/env python3
"""Evaluate the request-matching methods on test_queries.csv (split dev / test made before any run).

  python evaluate.py --phase dev     tune on the DEV rows only: embedding "none" thresholds -> tuned.json,
                                     LLM answers for dev rows (cached); writes out/dev_results.json
  python evaluate.py --phase final   run everything on dev + test with the frozen settings; writes
                                     results.json, results.csv, failures.csv, confusion_pairs.csv, results.png
  python evaluate.py --phase tune-fuzzy   tune ONLY the difflib cut-off of fuzzy_keyword on the DEV rows (no LLM, no
                                     embeddings); adds the key "fuzzy" to tuned.json and leaves the other keys as they are
Hybrid = keyword (whole word + aliases) -> difflib fuzzy alias match -> LLM only if neither finds a place. With
--no-llm-calls it is scored from llm_cache_<version>.json only; a query whose LLM answer is not cached is reported.

  python evaluate.py --method hybrid_gemini   (or --method gemini) the Gemini API with the same prompt, on all 128 rows
                                     (prompt frozen, nothing tuned). Key: GEMINI_API_KEY in the repo-root .env. At most
                                     --max-calls real calls (default 150) and --sleep-s seconds between real calls (default 0; use 4.5 on the free
                                     tier, about 15 requests/min; on HTTP 429 the run stops and a rerun resumes); answers cached in llm_cache_gemini_v1.json, so a
                                     rerun is free. Writes out/gemini_results.json + out/gemini_failures_<method>.csv only (the
                                     Claude results.json is not touched). No key: prints how to add one and exits 0.
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
HYB = ['fuzzy_keyword', 'hybrid']
ALL = MAIN + HYB + ['embed_doc', 'keyword_v1', 'tokens']
FIG = MAIN + HYB


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
        if method in HYB:
            t0 = time.perf_counter()
            pid, sc, stage = M.fuzzy_keyword_match(q['query'], places)
            local_ms = (time.perf_counter() - t0) * 1000
            row = {'pred': pid, 'score': float(sc), 'ms': local_ms, 'local_ms': local_ms, 'invalid': False, 'stage': stage}
            if method == 'hybrid' and pid is None:
                r = M.llm_answer(q['query'], places, allow_call=allow_calls)
                if r is None:
                    rows.append({'pred': None, 'score': 0.0, 'ms': None, 'invalid': False, 'missing': True, 'stage': 'llm_missing',
                                 'query': q['query']}); continue
                pred = r['parsed'] if r['valid'] and r['parsed'] != 'NONE' else None
                row = {'pred': pred, 'score': 1.0 if pred else 0.0, 'ms': local_ms + r['latency_s'] * 1000, 'local_ms': local_ms,
                       'llm_ms': r['latency_s'] * 1000, 'invalid': not r['valid'], 'raw': r['raw'], 'cost': r['cost_usd'], 'stage': 'llm'}
            rows.append(row)
            continue
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
        out['latency_ms'] = lat(ms)
    if 'stage' in res[idx[0]]:
        st = Counter(res[i]['stage'] for i in idx)
        out['stages'] = dict(st)
        out['llm_share'] = round(st.get('llm', 0) / n, 4)
        out['offline_coverage'] = round((st.get('keyword', 0) + st.get('fuzzy', 0)) / n, 4)   # answered without the LLM
        for name, key, sel in (('local_ms_keyword_or_fuzzy', 'local_ms', lambda r: r['stage'] in ('keyword', 'fuzzy')),
                               ('ms_when_llm_called', 'ms', lambda r: r['stage'] == 'llm')):
            v = sorted(res[i][key] for i in idx if sel(res[i]) and res[i].get(key) is not None)
            if v:
                out[name] = lat(v)
    return out


def lat(ms):
    return {'n': len(ms), 'mean': round(statistics.mean(ms), 3), 'median': round(statistics.median(ms), 3),
            'p95': round(ms[min(len(ms) - 1, int(0.95 * len(ms)))], 3), 'max': round(ms[-1], 3)}


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


def tune_fuzzy(queries, places, by_id):
    """difflib cut-off of fuzzy_keyword that maximises DEV accuracy (queries = dev rows only; no LLM). Ties: median."""
    curve = []
    for k in range(60, 100):
        th = k / 100
        acc = sum(is_ok(M.fuzzy_keyword_match(q['query'], places, th)[0], q['expected'], by_id) for q in queries) / len(queries)
        curve.append((th, round(acc, 6)))
    best = max(a for _, a in curve)
    ths = [t for t, a in curve if a == best]
    return {'cutoff': round(statistics.median(ths), 3), 'dev_accuracy': round(best, 4), 'best_range': [min(ths), max(ths)],
            'grid': [0.60, 0.99, 0.01], 'min_alias_chars': M.FUZZY_MIN_ALIAS, 'n_dev': len(queries),
            'note': 'tuned on dev rows only for fuzzy_keyword (no LLM); hybrid uses the same cut-off'}


def figure(results, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cols = {'keyword': '#0072B2', 'embed': '#E69F00', 'llm': '#009E73', 'fuzzy_keyword': '#56B4E9', 'hybrid': '#D55E00'}
    meths = [m for m in FIG if m in results]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={'width_ratios': [3, 2]})
    groups = [('easy', 'easy (23)'), ('hard_dev', 'hard dev'), ('hard_test', 'hard test'), ('test', 'all test')]
    w = 0.8 / len(meths)
    for j, m in enumerate(meths):
        vals = [results[m]['slices'][g]['accuracy'] for g, _ in groups]
        lab = m if m != 'hybrid' else f"hybrid (LLM on {results[m]['slices']['all']['llm_share']:.0%} of queries)"
        b = ax[0].bar([i + (j - (len(meths) - 1) / 2) * w for i in range(len(groups))], vals, w, label=lab, color=cols[m])
        for r, v in zip(b, vals):
            ax[0].text(r.get_x() + r.get_width() / 2, v + 0.01, f'{v:.0%}', ha='center', fontsize=6)
    ax[0].set_xticks(range(len(groups)))
    ax[0].set_xticklabels([n.replace('(23)', f"({results['keyword']['slices']['easy']['n']})") if g == 'easy' else
                           f"{n} ({results['keyword']['slices'][g]['n']})" for g, n in groups], fontsize=8)
    ax[0].set_ylim(0, 1.12); ax[0].set_ylabel('top-1 accuracy'); ax[0].set_title('Accuracy per split')
    ax[0].legend(fontsize=7, frameon=False, ncol=3, loc='upper center', bbox_to_anchor=(0.5, -0.12))
    w2 = 0.35
    for j, key in enumerate(('precision', 'recall')):
        vals = [(results[m]['slices']['hard']['reject'][key] or 0) for m in meths]
        b = ax[1].bar([i + (j - 0.5) * w2 for i in range(len(meths))], vals, w2, label=f'rejection {key}', color=['#56B4E9', '#CC79A7'][j])
        for r, v in zip(b, vals):
            ax[1].text(r.get_x() + r.get_width() / 2, v + 0.01, f'{v:.0%}', ha='center', fontsize=6)
    ax[1].set_xticks(range(len(meths))); ax[1].set_xticklabels([m.replace('_', ' ') for m in meths], fontsize=7); ax[1].set_ylim(0, 1.12)
    ax[1].set_title('"none" handling, hard set'); ax[1].legend(fontsize=8, frameon=False, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.12))
    for a in ax:
        a.spines[['top', 'right']].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=150)


def run_gemini(method, queries, places, allow_calls, max_calls, sleep_s=0.0):
    """Rows like run_method(); stops calling the API after the first error (key, quota, network) or max_calls.
    sleep_s = minimum gap in seconds between two REAL API calls (free tier: about 15 requests/min -> 4.5); cached answers
    are never delayed."""
    import gemini as G
    rows, stop, last_call = [], None, None
    for q in queries:
        local_ms = None
        if method == 'hybrid_gemini':
            t0 = time.perf_counter()
            pid, sc, stage = M.fuzzy_keyword_match(q['query'], places)
            local_ms = (time.perf_counter() - t0) * 1000
            if pid is not None:
                rows.append({'pred': pid, 'score': float(sc), 'ms': local_ms, 'local_ms': local_ms, 'invalid': False, 'stage': stage})
                continue
        allow = allow_calls and stop is None and M.GEMINI_CALLS < max_calls
        if allow and sleep_s > 0 and last_call is not None and M.gemini_answer(q['query'], places, allow_call=False) is None:
            wait = sleep_s - (time.monotonic() - last_call)         # a real call is coming: keep the gap since the last one
            if wait > 0:
                time.sleep(wait)
        calls_before = M.GEMINI_CALLS
        try:
            r = M.gemini_answer(q['query'], places, allow_call=allow)
        except G.GeminiError as e:
            stop, r = str(e), None
        if M.GEMINI_CALLS > calls_before:
            last_call = time.monotonic()
        if r is None:
            row = {'pred': None, 'score': 0.0, 'ms': None, 'invalid': False, 'missing': True, 'query': q['query']}
            if method == 'hybrid_gemini':
                row['stage'] = 'llm_missing'
            rows.append(row)
            continue
        pred = r['parsed'] if r['valid'] and r['parsed'] != 'NONE' else None
        row = {'pred': pred, 'score': 1.0 if pred else 0.0, 'ms': (local_ms or 0.0) + r['latency_s'] * 1000,
               'invalid': not r['valid'], 'raw': r['raw']}
        if method == 'hybrid_gemini':
            row.update(stage='llm', local_ms=local_ms, llm_ms=r['latency_s'] * 1000)
        rows.append(row)
    if stop is None and allow_calls and M.GEMINI_CALLS >= max_calls and any(r.get('missing') for r in rows):
        stop = f'--max-calls {max_calls} reached'
    return rows, stop


def gemini_eval(method, queries, places, by_id, allow_calls, max_calls, sleep_s=0.0):
    import gemini as G
    key, model = G.settings()
    if allow_calls and not key:
        print(f'No Gemini API key, so nothing was run. Paste your key after GEMINI_API_KEY= in {G.ENV_FILE} '
              '(get one at aistudio.google.com/apikey), then run this again. '
              f'(--no-llm-calls scores only what is already cached in {M.gemini_cache_path().name}.)')
        return
    res, stop = run_gemini(method, queries, places, allow_calls, max_calls, sleep_s)
    miss = [r['query'] for r in res if r.get('missing')]
    print(f'{method}: {M.GEMINI_CALLS} Gemini API calls made in this run (cap {max_calls}), model {model}')
    if miss:
        print(f'{method}: {len(miss)} of {len(queries)} queries have no Gemini answer yet' + (f' ({stop})' if stop else '') +
              '. Answers so far are cached; run again to continue. Nothing written.')
        return
    s = {k: metrics(v, queries, res, by_id) for k, v in slices(queries).items()}
    print(f"{method:13} " + '  '.join(f"{k} {s[k]['correct']}/{s[k]['n']}" for k in ('easy', 'hard', 'dev', 'test') if k in s))
    out = OUT / 'gemini_results.json'
    prev = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {'methods': {}}
    cache = M._load_gemini_cache()
    prev['meta'] = {'date': str(date.today()), 'python': platform.python_version(), 'n_queries': len(queries),
                    'n_places': len(places), 'model_setting': model,
                    'models_reported': sorted({r.get('model_version') or r.get('model') for r in cache['responses'].values()} - {None}),
                    'prompt_version': M.GEMINI_PROMPT_VERSION, 'cache_file': M.gemini_cache_path().name,
                    'cached_responses': len(cache['responses']), 'fuzzy_cutoff': M._fuzzy_cutoff(),
                    'note': 'same system prompt and place list as the Claude llm method; latency = wall clock of the HTTPS call'}
    prev['methods'][method] = {'slices': s, 'api_calls_in_last_run': M.GEMINI_CALLS, 'sleep_s': sleep_s}
    out.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding='utf-8')
    with (OUT / f'gemini_failures_{method}.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['method', 'id', 'split', 'set', 'category', 'query', 'expected', 'predicted', 'raw'])
        for q, r in zip(queries, res):
            if not (is_ok(r['pred'], q['expected'], by_id) and not r['invalid']):
                w.writerow([method, q['id'], q['split'], q['set'], q['category'], q['query'], q['expected'],
                            'INVALID' if r['invalid'] else (r['pred'] or 'none'), r.get('raw', '')])
    print('wrote', out.relative_to(ROOT), f'and out/gemini_failures_{method}.csv')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['dev', 'final', 'tune-fuzzy'])
    ap.add_argument('--no-llm-calls', action='store_true')
    ap.add_argument('--methods', default=','.join(ALL))
    ap.add_argument('--method', choices=M.GEMINI_METHODS, help='Gemini evaluation (see the top of this file)')
    ap.add_argument('--max-calls', type=int, default=150, help='hard cap on real Gemini API calls in this run')
    ap.add_argument('--sleep-s', type=float, default=0.0, help='minimum seconds between two real Gemini calls (free tier: 4.5)')
    a = ap.parse_args()
    places = M.load_places()
    by_id = {d['place_id']: d for d in places}
    queries = load_queries()
    if a.method:
        return gemini_eval(a.method, queries, places, by_id, not a.no_llm_calls, a.max_calls, a.sleep_s)
    if not a.phase:
        ap.error('--phase is required (or --method gemini / hybrid_gemini)')
    methods = a.methods.split(',')
    OUT.mkdir(exist_ok=True)
    if a.phase == 'tune-fuzzy':
        dev = [q for q in queries if q['split'] == 'dev']           # test rows are not used
        t = json.loads((ROOT / 'tuned.json').read_text(encoding='utf-8'))
        t['fuzzy'] = {**tune_fuzzy(dev, places, by_id), 'date': str(date.today())}
        (ROOT / 'tuned.json').write_text(json.dumps(t, indent=1), encoding='utf-8')
        print('tuned.json fuzzy:', t['fuzzy'])
        return
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
            miss = [r.get('query', '') for r in res if r.get('missing')]
            print(f'{m}: {len(miss)} queries need an LLM answer that is not cached: {miss}'); continue
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
            'offline': {'keyword': True, 'embed': True, 'embed_doc': True, 'keyword_v1': True, 'tokens': True, 'llm': False,
                        'fuzzy_keyword': True, 'hybrid': 'partly: offline for the queries keyword or fuzzy answer (offline_coverage); the rest need the LLM'},
            'hybrid_note': ('hybrid = keyword (whole word + aliases) -> difflib fuzzy alias match (cut-off in thresholds.fuzzy, '
                            'tuned on dev for fuzzy_keyword) -> LLM only when neither finds a place; LLM answers from the cache '
                            'only (no new call); latency = local keyword+fuzzy ms, plus the cached wall-clock LLM latency when it falls through'),
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
                                round(r['score'], 4), r.get('raw', '') if m in ('llm', 'hybrid') else ''])
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
