"""LLM directions baseline: ask `claude -p --model haiku` for routes given a text floor plan made from graph.json.

    python llm_baseline.py plan            # print the floor-plan text and the sample of pairs, no calls
    python llm_baseline.py run [--limit N] # call the CLI for every (condition, pair) not yet cached (4 in parallel)

Three conditions on the same fixed pair sample:
  dist  : plan lists every connection with its walking distance (m) and escalator/stairs time (s)  (headline)
  adj   : plan lists the same connections without any numbers (adjacency in words only)
  names : plan lists only the places (no connections at all): shows what the model invents when it must guess
Each answer is cached as out/llm_cache/<condition>__<start>__<goal>.json with the prompt, the raw response, the model
that answered, the date, the CLI version and the latency. Existing cache files are never overwritten.
"""
import json
import random
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from route import graph

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'out' / 'llm_cache'
MODEL = 'haiku'
SEED = 2340
STRATA = {'5F_same_floor': 20, '4F_same_floor': 8, 'cross_5F_to_4F': 11, 'cross_4F_to_5F': 11}
SYSTEM = 'You are a careful navigation assistant. Follow the requested output format exactly.'


def sample_pairs():
    """Fixed sample: seeded draw per stratum from the ordered pairs whose optimal route has at least 2 hops."""
    g = graph()
    ids = sorted(g.nodes)
    rng = random.Random(SEED)
    pools = {k: [] for k in STRATA}
    for a in ids:
        for b in ids:
            if a == b or len(g.search(a, b)[0]) < 3:
                continue
            fa, fb = g.nodes[a]['floor'], g.nodes[b]['floor']
            key = ('5F_same_floor' if fa == 5 else '4F_same_floor') if fa == fb else ('cross_5F_to_4F' if fa == 5 else 'cross_4F_to_5F')
            pools[key].append((a, b))
    out = []
    for k, n in STRATA.items():
        for a, b in rng.sample(pools[k], n):
            out.append({'start': a, 'goal': b, 'stratum': k})
    return out


def floor_plan(numbers, connections=True):
    g = graph()
    L = ['FLOOR PLAN of a university building (floors 5 and 4). Each place has an ID, a name and a floor.', '', 'PLACES']
    for n in sorted(g.nodes.values(), key=lambda n: (-n['floor'], n['id'])):
        L.append('- %s: %s, floor %d' % (n['id'], n['name'], n['floor']))
    if not connections:
        return '\n'.join(L + ['', 'No list of corridors is available for this building.'])
    L += ['', 'CONNECTIONS (from each place, what you can reach in one step; a connection can only be used in the direction listed)']
    for n in sorted(g.nodes.values(), key=lambda n: (-n['floor'], n['id'])):
        parts = []
        for v, sec, met, e in sorted(g.adj[n['id']], key=lambda t: t[0]):
            if e['mode'] == 'walk':
                parts.append('walk to %s%s' % (v, ' (%.1f m)' % met if numbers else ''))
            elif e['mode'] == 'escalator':
                parts.append('ride the escalator %s to %s%s' % ('down' if g.nodes[v]['floor'] < n['floor'] else 'up', v,
                                                                 ' (about %.0f s)' % sec if numbers else ''))
            else:
                parts.append('take the stairs or lift to %s%s' % (v, ' (about %.0f s)' % sec if numbers else ''))
        L.append('- %s: %s.' % (n['id'], '; '.join(parts)))
    if numbers:
        L += ['', 'People walk at %.1f m/s. Walking time = distance / speed. Escalator and stairs times are given in seconds.' % g.speed]
    return '\n'.join(L)


def prompt(cond, start, goal):
    g = graph()
    goal_txt = 'the quickest route (least total travel time)' if cond == 'dist' else 'the quickest route'
    rule = ('Use only places and connections that appear in the floor plan above, in the listed direction. ' if cond != 'names'
            else 'Use only the place IDs listed above. ')
    return ('%s\n\nTASK: Give %s from "%s" (%s) to "%s" (%s).\n'
            '%s'
            'Answer with ONLY a JSON array of place IDs in order, starting with %s and ending with %s, nothing else.'
            % (floor_plan(cond == 'dist', cond != 'names'), goal_txt, start, g.nodes[start]['name'], goal, g.nodes[goal]['name'], rule, start, goal))


def call(cond, pair):
    f = CACHE / ('%s__%s__%s.json' % (cond, pair['start'], pair['goal']))
    if f.exists():
        return 'cached'
    p = prompt(cond, pair['start'], pair['goal'])
    cmd = ['claude', '-p', '--model', MODEL, '--tools', '', '--no-session-persistence', '--setting-sources', '',
           '--system-prompt', SYSTEM, '--output-format', 'json', p]
    rec = {'condition': cond, 'start': pair['start'], 'goal': pair['goal'], 'stratum': pair['stratum'], 'model_requested': MODEL,
           'date_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'prompt': p,
           'cli_command': 'claude -p --model haiku --tools "" --no-session-persistence --setting-sources "" --system-prompt <SYSTEM> --output-format json <prompt>',
           'system_prompt': SYSTEM}
    for attempt in (1, 2):
        t = time.perf_counter()
        with tempfile.TemporaryDirectory() as cwd:           # neutral folder: no CLAUDE.md of this repo is read
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=180)
        rec['latency_s'] = round(time.perf_counter() - t, 3)
        rec['attempt'] = attempt
        if r.returncode == 0:
            try:
                j = json.loads(r.stdout)
                rec.update(response=j.get('result'), api_ms=j.get('duration_api_ms'), is_error=j.get('is_error'),
                           model_used=list((j.get('modelUsage') or {}).keys()), usage=j.get('usage'), cost_usd=j.get('total_cost_usd'))
                break
            except json.JSONDecodeError:
                rec['error'] = 'bad json from CLI: ' + r.stdout[:300]
        else:
            rec['error'] = 'exit %d: %s' % (r.returncode, r.stderr[:300])
    rec['cli_version'] = subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, indent=1) + '\n', encoding='utf-8')
    return 'error' if 'response' not in rec else 'ok'


def main():
    pairs = sample_pairs()
    if sys.argv[1:2] == ['plan']:
        print(prompt('dist', pairs[0]['start'], pairs[0]['goal']))
        print('\n---- adj condition floor plan ----\n' + floor_plan(False))
        print(json.dumps(pairs))
        return
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    jobs = [(c, p) for c in ('dist', 'adj', 'names') for p in pairs]
    if limit:
        jobs = jobs[:limit]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda j: call(*j), jobs))
    print({k: res.count(k) for k in set(res)})


if __name__ == '__main__':
    main()
