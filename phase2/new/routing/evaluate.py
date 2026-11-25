"""Score the cached LLM answers against the graph; write out/results.json, results_table.csv, llm_answers.csv, routing_results.png.

    python phase2/new/routing/evaluate.py      (after check_astar.py and llm_baseline.py run)
"""
import csv
import json
import math
import re
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from route import graph

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
CONDS = [('dist', 'LLM + plan with distances'), ('adj', 'LLM + plan, adjacency only'), ('names', 'LLM + place list only')]


def parse(text):
    """-> list of ids or None. Accepts a bare JSON array or one inside a ``` fence / other text."""
    if text is None:
        return None
    try:
        v = json.loads(text.strip())
    except json.JSONDecodeError:
        m = re.search(r'\[[^\[\]]*\]', text, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return v if isinstance(v, list) and all(isinstance(x, str) for x in v) else None


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def score(rec, g):
    s, goal = rec['start'], rec['goal']
    ans = parse(rec.get('response'))
    row = {'condition': rec['condition'], 'start': s, 'goal': goal, 'stratum': rec['stratum'], 'latency_s': rec['latency_s'],
           'api_ms': rec.get('api_ms'), 'parsed': ans is not None, 'answer': ' > '.join(ans) if ans else '',
           'hops': None, 'bad_hops': None, 'unknown_id_hops': 0, 'wrong_direction_hops': 0, 'invented_hops': 0,
           'starts_ok': False, 'reaches_goal': False, 'valid': False, 'success': False, 'seconds': None,
           'optimal_seconds': round(g.search(s, goal)[1], 2), 'ratio': None, 'optimal': False, 'bad_hop_list': ''}
    if not ans:
        return row
    bad = []
    for a, b in zip(ans, ans[1:]):
        if a not in g.nodes or b not in g.nodes:
            row['unknown_id_hops'] += 1; bad.append('%s>%s (unknown id)' % (a, b))
        elif (a, b) in g.edge:
            continue
        elif (b, a) in g.edge:
            row['wrong_direction_hops'] += 1; bad.append('%s>%s (one-way, wrong direction)' % (a, b))
        else:
            row['invented_hops'] += 1; bad.append('%s>%s (no such corridor)' % (a, b))
    row.update(hops=max(len(ans) - 1, 0), bad_hops=len(bad), bad_hop_list='; '.join(bad),
               starts_ok=ans[0] == s, reaches_goal=ans[-1] == goal)
    row['valid'] = not bad and row['starts_ok']
    row['success'] = row['valid'] and row['reaches_goal'] and len(ans) > 1
    if row['success']:
        row['seconds'] = round(g.path_cost(ans)[0], 2)
        row['ratio'] = round(row['seconds'] / row['optimal_seconds'], 4)
        row['optimal'] = row['ratio'] <= 1 + 1e-9
    return row


def summarise(rows):
    n = len(rows)
    ok = [r for r in rows if r['success']]
    hops = sum(r['hops'] or 0 for r in rows)
    bad = sum(r['bad_hops'] or 0 for r in rows)
    lat = sorted(r['latency_s'] for r in rows)
    ratios = [r['ratio'] for r in ok]
    return {
        'n_answers': n, 'parsed': sum(r['parsed'] for r in rows),
        'success_valid_and_reaches_goal': len(ok), 'success_rate': round(len(ok) / n, 3), 'success_ci95': wilson(len(ok), n),
        'answers_with_a_bad_hop': sum(1 for r in rows if r['bad_hops']), 'bad_hop_answer_rate': round(sum(1 for r in rows if r['bad_hops']) / n, 3),
        'hops_total': hops, 'bad_hops_total': bad, 'invented_edge_rate_per_hop': round(bad / hops, 4) if hops else None,
        'unknown_id_hops': sum(r['unknown_id_hops'] for r in rows), 'wrong_direction_hops': sum(r['wrong_direction_hops'] for r in rows),
        'no_such_corridor_hops': sum(r['invented_hops'] for r in rows),
        'reaches_goal_rate': round(sum(r['reaches_goal'] for r in rows) / n, 3),
        'optimal_count': sum(r['optimal'] for r in rows), 'optimal_rate': round(sum(r['optimal'] for r in rows) / n, 3),
        'optimal_ci95': wilson(sum(r['optimal'] for r in rows), n),
        'cost_ratio_successful_mean': round(st.mean(ratios), 4) if ratios else None,
        'cost_ratio_successful_median': round(st.median(ratios), 4) if ratios else None,
        'cost_ratio_successful_max': round(max(ratios), 4) if ratios else None,
        'latency_s_mean': round(st.mean(lat), 2), 'latency_s_median': round(st.median(lat), 2), 'latency_s_p90': round(lat[int(0.9 * (n - 1))], 2),
        'api_ms_median': st.median([r['api_ms'] for r in rows if r['api_ms'] is not None]) if any(r['api_ms'] for r in rows) else None,
    }


def main():
    g = graph()
    recs = [json.loads(f.read_text()) for f in sorted((OUT / 'llm_cache').glob('*.json'))]
    rows = [score(r, g) for r in recs]
    by_cond = {c: [r for r in rows if r['condition'] == c] for c, _ in CONDS}
    summary = {c: summarise(v) for c, v in by_cond.items() if v}
    strata = {}
    for c, v in by_cond.items():
        for s in sorted({r['stratum'] for r in v}):
            sub = [r for r in v if r['stratum'] == s]
            strata.setdefault(c, {})[s] = {'n': len(sub), 'success': sum(r['success'] for r in sub), 'optimal': sum(r['optimal'] for r in sub)}
    ck = json.loads((OUT / 'astar_check.json').read_text())
    models = sorted({m for r in recs for m in r.get('model_used', [])})
    examples = {}
    for c, v in by_cond.items():
        fails = [r for r in v if not r['success']]
        # prefer answers with an invented/wrong-direction hop, then the others
        fails.sort(key=lambda r: (not (r['invented_hops'] or r['wrong_direction_hops'] or r['unknown_id_hops']), r['stratum'], r['start']))
        examples[c] = [{k: r[k] for k in ('start', 'goal', 'stratum', 'answer', 'bad_hop_list', 'reaches_goal')} for r in fails[:6]]
    suboptimal = {c: [{k: r[k] for k in ('start', 'goal', 'answer', 'ratio')} for r in sorted((x for x in v if x['success'] and not x['optimal']), key=lambda x: -x['ratio'])[:4]] for c, v in by_cond.items()}
    gj = g.data
    status = {}
    for e in gj['edges']:
        status[e['length_status']] = status.get(e['length_status'], 0) + 1
    res = {
        'model_requested': 'haiku', 'models_that_answered': models, 'cli_versions': sorted({r.get('cli_version') for r in recs}),
        'dates_utc': sorted({r['date_utc'][:10] for r in recs}), 'llm_calls_cached': len(recs),
        'llm_calls_total_attempts': sum(r.get('attempt', 1) for r in recs), 'pairs': len({(r['start'], r['goal']) for r in recs}),
        'graph': {'nodes': len(gj['nodes']), 'edges': len(gj['edges']), 'edge_length_status': status,
                  'speed_mps': gj['speed_mps'], 'stride_m': gj['stride_m'], 'escalator_ride_s_guess': gj['escalator_ride_s']},
        'astar': {'ordered_pairs_checked': ck['ordered_pairs'], 'cost_mismatches_vs_dijkstra': ck['pairs_cost_mismatch_astar_vs_dijkstra'],
                  'success_rate': 1.0, 'optimal_rate': 1.0, 'cost_ratio': 1.0, 'invented_edge_rate_per_hop': 0.0,
                  'time_per_query_ms': ck['time_per_query_ms_astar'], 'expansions_mean_astar': ck['expansions_mean_astar'],
                  'expansions_mean_dijkstra': ck['expansions_mean_dijkstra']},
        'llm': summary, 'llm_by_stratum': strata, 'failure_examples': examples, 'suboptimal_examples': suboptimal,
    }
    (OUT / 'results.json').write_text(json.dumps(res, indent=1) + '\n')
    cols = list(rows[0].keys())
    with open(OUT / 'llm_answers.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r['condition'], r['stratum'], r['start'], r['goal'])))
    with open(OUT / 'results_table.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['method', 'n', 'success_valid_and_reaches_goal', 'success_rate', 'optimal_count', 'optimal_rate', 'cost_ratio_mean_successful',
                    'cost_ratio_median_successful', 'invented_edge_rate_per_hop', 'answers_with_bad_hop', 'latency_s_median', 'latency_s_mean'])
        a = res['astar']
        w.writerow(['A* (graph.json)', len(set((r['start'], r['goal']) for r in rows)), len(set((r['start'], r['goal']) for r in rows)), 1.0,
                    len(set((r['start'], r['goal']) for r in rows)), 1.0, 1.0, 1.0, 0.0, 0, round(a['time_per_query_ms'] / 1000, 6), round(a['time_per_query_ms'] / 1000, 6)])
        for c, label in CONDS:
            if c in summary:
                s = summary[c]
                w.writerow([label, s['n_answers'], s['success_valid_and_reaches_goal'], s['success_rate'], s['optimal_count'], s['optimal_rate'],
                            s['cost_ratio_successful_mean'], s['cost_ratio_successful_median'], s['invented_edge_rate_per_hop'],
                            s['answers_with_a_bad_hop'], s['latency_s_median'], s['latency_s_mean']])
    figure(res, by_cond)
    print(json.dumps({c: {k: v[k] for k in ('success_rate', 'optimal_rate', 'cost_ratio_successful_mean', 'invented_edge_rate_per_hop', 'latency_s_median')} for c, v in summary.items()}, indent=1))


def figure(res, by_cond):
    col = {'A*': '#0072B2', 'dist': '#E69F00', 'adj': '#009E73', 'names': '#CC79A7'}
    SHORT = {'dist': 'LLM\n+ distances', 'adj': 'LLM\n+ adjacency only', 'names': 'LLM\n+ places only'}
    labels = [('A*', 'A*')] + [(c, SHORT[c]) for c, l in CONDS if c in res['llm']]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    # (a) rates
    x = range(len(labels))
    succ = [1.0] + [res['llm'][c]['success_rate'] for c, _ in labels[1:]]
    opt = [1.0] + [res['llm'][c]['optimal_rate'] for c, _ in labels[1:]]
    w = 0.38
    ax[0].bar([i - w / 2 for i in x], succ, w, color=[col[c] for c, _ in labels], label='valid route that reaches the goal')
    ax[0].bar([i + w / 2 for i in x], opt, w, color=[col[c] for c, _ in labels], alpha=0.45, hatch='//', label='...and the fastest route')
    for i, (a, b) in enumerate(zip(succ, opt)):
        ax[0].text(i - w / 2, a + 0.02, '%.0f%%' % (100 * a), ha='center', fontsize=8); ax[0].text(i + w / 2, b + 0.02, '%.0f%%' % (100 * b), ha='center', fontsize=8)
    ax[0].set_xticks(list(x)); ax[0].set_xticklabels([l for _, l in labels], fontsize=8); ax[0].set_ylim(0, 1.12)
    ax[0].set_ylabel('share of the %d pairs' % res['pairs']); ax[0].set_title('Valid and fastest routes'); ax[0].legend(fontsize=7, loc='center left')
    # (b) cost ratio of successful answers
    for i, (c, _) in enumerate(labels):
        vals = [1.0] * res['pairs'] if c == 'A*' else [r['ratio'] for r in by_cond[c] if r['ratio'] is not None]
        jitter = [(((k * 37) % 100) / 100 - 0.5) * 0.5 for k in range(len(vals))]
        ax[1].scatter([i + j for j in jitter], vals, s=14, color=col[c], alpha=0.7)
        if vals:
            ax[1].hlines(st.median(vals), i - 0.3, i + 0.3, color='k', lw=1.5)
    ax[1].axhline(1.0, color='grey', lw=0.8, ls=':')
    ax[1].set_xticks(list(range(len(labels)))); ax[1].set_xticklabels([l for _, l in labels], fontsize=8)
    ax[1].set_ylabel('travel time / fastest travel time'); ax[1].set_title('Cost ratio (only valid answers; bar = median)')
    for i, (c, _) in enumerate(labels[1:], 1):
        ax[1].text(i, ax[1].get_ylim()[1] * 0.995, 'n=%d' % res['llm'][c]['success_valid_and_reaches_goal'], ha='center', va='top', fontsize=8)
    # (c) invented hops
    inv = [0.0] + [res['llm'][c]['invented_edge_rate_per_hop'] for c, _ in labels[1:]]
    ax[2].bar(list(x), inv, color=[col[c] for c, _ in labels])
    for i, v in enumerate(inv):
        ax[2].text(i, v + 0.005, '%.1f%%' % (100 * v), ha='center', fontsize=8)
    ax[2].set_xticks(list(x)); ax[2].set_xticklabels([l for _, l in labels], fontsize=8)
    ax[2].set_ylabel('share of hops that are not a real corridor'); ax[2].set_title('Invented or wrong-way hops (per hop)')
    ax[2].set_ylim(0, max(inv) * 1.2 + 0.02)
    for a in ax:
        a.spines[['top', 'right']].set_visible(False)
    fig.suptitle('WalkSense routing: A* on the measured graph vs Claude Haiku given a text floor plan (same %d ordered pairs)' % res['pairs'], fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / 'routing_results.png', dpi=150)


if __name__ == '__main__':
    main()
