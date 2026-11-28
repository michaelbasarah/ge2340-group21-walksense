#!/usr/bin/env python3
"""Offline check of the app's search (search.py) after entry 93: start (From) and destination (To). No Gemini call.

  python eval_search_app.py      -> out/search_app_eval.json

1. To-only: the 128 queries of request-matching/test_queries.csv through search.search() with Gemini off (the
   keyword -> fuzzy path the app uses offline), from three starts (no From = the old default 4F gate, the Canteen on
   5F, LT1a on 4F), scored with request-matching/evaluate.py is_ok (same lenient tag: rows). "matcher" = the
   request-matching fuzzy_keyword answer on the whole query (what the app's offline search gave before entry 93, apart
   from the toilet rule of entries 78/90, which is applied to both). Every query whose answer changed is listed.
2. From + To: from_to_queries.csv (24 rows drafted by the agent on 27 Nov from the user's example and the rules of
   entry 93, expected values written before this script was run), scored offline: start right, destination right.
The Gemini path is covered by mocked tests (test_search.py) and two live queries (PROCESS-LOG entry 93), not here.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import search as S

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(S.REQ))
import evaluate as E  # noqa: E402  (request-matching/evaluate.py: is_ok, load_queries)

STARTS = [None, 'canteen', 'lt1a']


def offline():
    S._state.update(disabled='offline evaluation (Gemini not called)', paused_until=0.0, last_error='')


def to_only():
    by_id = {d['place_id']: d for d in S.PLACES}
    out = {}
    for start in STARTS:
        rows, changed = [], []
        for q in E.load_queries():
            r = S.search(q['query'], from_id=start)
            old, _, _ = S.M.fuzzy_keyword_match(q['query'], S.PLACES)
            tq = S.toilet_query(q['query'])
            if old is not None and (tq is not None or by_id[old]['kind'] == 'toilet'):   # the toilet rule, as before
                t = S.astar.nearest_toilet(S.resolve_start(start)['id'], 'standard', (tq or {}).get('gender') or 'any',
                                           floor=(tq or {}).get('floor'), accessible_only=bool((tq or {}).get('accessible')))
                old = t['toilet'] or old
            elif old is None and tq is not None:
                old = S.astar.nearest_toilet(S.resolve_start(start)['id'], 'standard', tq['gender'] or 'any',
                                             floor=tq['floor'], accessible_only=tq['accessible'])['toilet']
            new = r['place_id']
            ok_old, ok_new = E.is_ok(old, q['expected'], by_id), E.is_ok(new, q['expected'], by_id)
            rows.append((ok_old, ok_new))
            if old != new:
                changed.append({'id': q['id'], 'query': q['query'], 'expected': q['expected'], 'before': old, 'after': new,
                                'ok_before': ok_old, 'ok_after': ok_new, 'from_query': (r['from_query'] or {}).get('id')})
        out[start or 'default (4F gate)'] = {'n': len(rows), 'correct_before': sum(a for a, _ in rows),
                                             'correct_after': sum(b for _, b in rows), 'changed': changed,
                                             'start_found_in_query': sum(1 for q in E.load_queries()
                                                                         if S.search(q['query'], from_id=start)['from_query'])}
    return out


def tracked_key(pid):
    return S.GRAPH_TO_MAP[pid] if pid else None


def from_to():
    rows = list(csv.DictReader((HERE / 'from_to_queries.csv').open(encoding='utf-8')))
    res = []
    for q in rows:
        r = S.search(q['query'], from_id=q['from_list'] or None, tracked=tracked_key(q['tracked']), mode=q['mode'],
                     gender=q['gender'])
        got_from = r['from']['id'] if r['from'] and r['from']['id'] else ('waiting' if r.get('waiting') else None)
        to = r.get('to') or {}
        got_to = to.get('id') or (('nearest:' + to['nearest']) if to.get('nearest') else '')
        res.append({'id': q['id'], 'query': q['query'], 'expected_from': q['expected_from'], 'got_from': got_from,
                    'expected_to': q['expected_to'], 'got_to': got_to, 'from_ok': got_from == q['expected_from'],
                    'to_ok': got_to == q['expected_to'], 'method': r['method'], 'metres': r['distance_m'],
                    'seconds': r['seconds'], 'waiting': bool(r.get('waiting'))})
    return {'n': len(res), 'from_ok': sum(x['from_ok'] for x in res), 'to_ok': sum(x['to_ok'] for x in res),
            'both_ok': sum(x['from_ok'] and x['to_ok'] for x in res), 'rows': res}


def main():
    offline()
    out = {'about': __doc__.strip().splitlines()[0], 'to_only': to_only(), 'from_to': from_to()}
    p = HERE / 'out' / 'search_app_eval.json'
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for k, v in out['to_only'].items():
        print(f"to-only, start {k}: {v['correct_before']}/{v['n']} -> {v['correct_after']}/{v['n']}, "
              f"{len(v['changed'])} answers changed, start found in {v['start_found_in_query']} queries")
        for c in v['changed']:
            print(f"   {c['id']} {c['query']!r} expected {c['expected']}: {c['before']} -> {c['after']}")
    f = out['from_to']
    print(f"from+to set: start {f['from_ok']}/{f['n']}, destination {f['to_ok']}/{f['n']}, both {f['both_ok']}/{f['n']}")
    for x in f['rows']:
        if not (x['from_ok'] and x['to_ok']):
            print('   MISS', x)
    print('wrote', p)


if __name__ == '__main__':
    main()
