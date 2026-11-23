#!/usr/bin/env python3
"""Text request matching (objective #9) — turn a typed request into a place ID.

Two working methods, compared on the same test set:
  1. keyword  — alias/keyword rules (simple, predictable).
  2. tokens   — token-overlap with inverse-frequency weighting (a lightweight, offline
                stand-in for sentence embeddings; swap in a real embedding model later).

A third method (an LLM constrained to answer with a real place ID) is left as a plug-in:
it needs internet and must be quoted/cited per the course rules, so it is not run here.

Standard library only. Edit destinations.csv / test_queries.csv to extend.
Run:  python match.py
"""
import csv
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STOP = set('a an the to of i you me my is are do how where can could would please need get '
           'take go show find nearest near closest some somewhere place here there for in on at '.split())

def norm(text):
    return [t for t in re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split() if t]

def load():
    dests = list(csv.DictReader((ROOT / 'destinations.csv').open(encoding='utf-8')))
    for d in dests:
        d['tag_set'] = set(d['tags'].split(';')) if d['tags'] else set()
        d['alias_list'] = [a.strip() for a in d['aliases'].split(';') if a.strip()]
    queries = list(csv.DictReader((ROOT / 'test_queries.csv').open(encoding='utf-8')))
    return dests, queries

def keyword_match(query, dests):
    """Longest alias substring wins; fall back to tag-keyword hits."""
    q = ' '.join(norm(query)); qtok = set(norm(query))
    best, best_key = None, (0, 0)
    for d in dests:
        alias = max((len(a) for a in d['alias_list'] if a in q), default=0)
        tags = len(qtok & {t for tag in d['tag_set'] for t in [tag]})
        key = (alias, tags)
        if key > best_key and (alias or tags):
            best_key, best = key, d['place_id']
    return best

def build_idf(dests):
    docs = {d['place_id']: set(norm(' '.join([d['name']] + d['alias_list'] + list(d['tag_set'])))) for d in dests}
    df = Counter(t for toks in docs.values() for t in toks)
    n = len(docs)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    return docs, idf

def token_match(query, dests, docs, idf):
    """Score each destination by inverse-frequency-weighted token overlap."""
    qtok = [t for t in norm(query) if t not in STOP]
    best, best_score = None, 0.0
    for d in dests:
        score = sum(idf.get(t, 0) for t in qtok if t in docs[d['place_id']])
        if score > best_score:
            best_score, best = score, d['place_id']
    return best

def is_correct(pred, expected, by_id):
    if pred is None:
        return False
    if expected.startswith('tag:'):
        return expected.split(':', 1)[1] in by_id[pred]['tag_set']
    return pred == expected

def main():
    dests, queries = load()
    by_id = {d['place_id']: d for d in dests}
    docs, idf = build_idf(dests)
    rows = []
    hits = {'keyword': 0, 'tokens': 0}
    for q in queries:
        kw = keyword_match(q['query'], dests)
        tk = token_match(q['query'], dests, docs, idf)
        kw_ok = is_correct(kw, q['expected'], by_id)
        tk_ok = is_correct(tk, q['expected'], by_id)
        hits['keyword'] += kw_ok; hits['tokens'] += tk_ok
        rows.append({'query': q['query'], 'expected': q['expected'],
                     'keyword': kw or '(no match)', 'keyword_ok': kw_ok,
                     'tokens': tk or '(no match)', 'tokens_ok': tk_ok})
    with (ROOT / 'results.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    n = len(queries)
    print(f"{n} test requests, {len(dests)} destinations\n")
    print(f"{'QUERY':38} {'EXPECTED':10} {'KEYWORD':11} {'TOKENS':11}")
    for r in rows:
        print(f"{r['query'][:37]:38} {r['expected']:10} "
              f"{(r['keyword']+('  OK' if r['keyword_ok'] else '  X')):11} "
              f"{(r['tokens']+('  OK' if r['tokens_ok'] else '  X')):11}")
    print(f"\nAccuracy  keyword: {hits['keyword']}/{n} = {hits['keyword']/n:.0%}"
          f"   |   tokens: {hits['tokens']}/{n} = {hits['tokens']/n:.0%}")
    print("(LLM method: plug in later — needs internet; quote & cite its output per course rules.)")

def answer(query, dests, docs, idf, by_id):
    name = lambda pid: by_id[pid]['name'] if pid in by_id else '(no match)'
    print(f'  keyword -> {name(keyword_match(query, dests))}')
    print(f'  tokens  -> {name(token_match(query, dests, docs, idf))}')

if __name__ == '__main__':
    import sys
    dests, _ = load()
    by_id = {d['place_id']: d for d in dests}
    docs, idf = build_idf(dests)
    if len(sys.argv) > 1:
        # One-shot:  python match.py "where can I eat"
        print(f'you typed : "{" ".join(sys.argv[1:])}"')
        answer(' '.join(sys.argv[1:]), dests, docs, idf, by_id)
    else:
        main()
        # Interactive: keep typing your own requests.
        print('\n=== Try your own! Type a request and press Enter (blank line to quit) ===')
        try:
            while True:
                q = input('\nyou: ').strip()
                if not q:
                    break
                answer(q, dests, docs, idf, by_id)
        except EOFError:
            pass
