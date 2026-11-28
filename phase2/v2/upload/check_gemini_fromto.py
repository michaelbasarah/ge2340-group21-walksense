#!/usr/bin/env python3
"""Two live Gemini calls with the app's v2 search prompt (entry 93), recorded for the log; the key is never printed.

  python check_gemini_fromto.py [--env PATH]   # needs GEMINI_API_KEY (repo-root .env, the environment, or the .env
                                               # file at PATH, e.g. the main checkout's from a worktree); 2 real calls

Query 1: the user's example "im in y5202, find me the nearest exit" from Current location (no live fix).
Query 2: a to-only query "where is lecture theatre 1a" with From = Canteen (From must stay).
Each raw reply is parsed and put into search.py's in-memory cache, then search.search() answers from it, so the app's
own post-processing (start from the query, nearest exit by route) runs exactly as in the server. Writes
out/search_samples_gemini_v2.json (query, raw reply, model, latency, the app's answer). Nothing else is called.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import search as S

HERE = Path(__file__).resolve().parent
QUERIES = [('im in y5202, find me the nearest exit', 'here'), ('where is lecture theatre 1a', 'canteen')]


def main():
    if sys.argv[1:2] == ['--env']:
        S.gemini.load_env(sys.argv[2])                    # read only; the key is never printed or copied
    key, model = S.gemini.settings()
    if not key:
        print('GEMINI_API_KEY not set: nothing called.')
        return
    rows = []
    for q, from_id in QUERIES:
        raw, info = S.gemini.generate(S.M.ASK_SYSTEM, S.M.ask_prompt(q, S.PLACES), json_mode=True)
        fid, pid, ans = S.M.parse_ask_route(raw, set(S.BY_ID))
        S._cache[(S.M.ASK_PROMPT_VERSION, ' '.join(q.lower().split()))] = (fid, pid, ans)
        r = S.search(q, from_id=from_id)
        rows.append({'query': q, 'from_list': from_id, 'raw_reply': raw, 'model': info['model'],
                     'model_version': info['model_version'], 'latency_s': info['latency_s'],
                     'gemini_from_id': fid, 'gemini_place_id': pid,
                     'app': {'method': r['method'], 'from': r['from'], 'from_query': r['from_query'], 'to': r['to'],
                             'place_id': r['place_id'], 'matched_place': r.get('matched_place'),
                             'distance_m': r['distance_m'], 'seconds': r['seconds'],
                             'path': r.get('path'), 'waiting': bool(r.get('waiting'))}})
        print(json.dumps(rows[-1], ensure_ascii=False))
        time.sleep(4.5)                                   # free tier pacing (entry 75)
    out = {'about': 'two live Gemini calls, app prompt ' + S.M.ASK_PROMPT_VERSION + ' (PROCESS-LOG entry 93)',
           'time_local': time.strftime('%Y-%m-%d %H:%M:%S'), 'rows': rows}
    (HERE / 'out' / 'search_samples_gemini_v2.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n',
                                                                 encoding='utf-8')
    print('wrote out/search_samples_gemini_v2.json')


if __name__ == '__main__':
    main()
