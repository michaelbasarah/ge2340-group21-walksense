#!/usr/bin/env python3
"""Text request matching (objective #9): turn a typed request into ONE place ID.

Import it:      from match import match
                place_id, score = match("where can I eat", "keyword")      # place_id is None = "no such place"

Methods (the three from the proposal, plus two older ones kept for comparison):
  keyword     alias rules, whole-word matching, floor hint (4F/bawah vs 5F/atas); offline, standard library only
  embed       sentence embeddings (all-MiniLM-L6-v2) of every place name/alias/tag, cosine top-1,
              "none" below a threshold tuned on the dev split (tuned.json); offline once the model is downloaded
  llm         the Claude Code CLI in headless mode (claude -p --model haiku) with the place list in the
              prompt, answer must be one real place ID or NONE; needs internet; every raw answer is cached
              in llm_cache_<prompt version>.json (model, date, prompt, raw reply)
  embed_doc   (extra) like embed but one vector per place from name + aliases + tags joined
  keyword_v1  (extra) the starter keyword method exactly as in the first version (substring match)
  tokens      (extra) the starter inverse-frequency token overlap

The place list is destinations.csv (built by build_destinations.py from graph-v2 + Tian's map labels).
Evaluation: evaluate.py. To plug into the app: copy match.py + destinations.csv + tuned.json (+ llm cache).
"""
import csv
import difflib
import json
import math
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METHODS = ('keyword', 'embed', 'llm')
EXTRA_METHODS = ('embed_doc', 'keyword_v1', 'tokens')
HYBRID_METHODS = ('fuzzy_keyword', 'hybrid')     # keyword -> difflib fuzzy (no LLM); keyword -> fuzzy -> LLM
EMBED_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
LLM_MODEL = 'haiku'
LLM_PROMPT_VERSION = 'v1'

STOP = set('a an the to of i you me my is are do how where can could would please need get '
           'take go show find nearest near closest some somewhere place here there for in on at '.split())


# ---------------------------------------------------------------- places
def norm(text):
    """Lower-case words (letters, digits, any script); everything else becomes a space."""
    return [t for t in re.sub(r'[^\w ]|_', ' ', text.lower()).split() if t]


def load_places(path=None):
    places = list(csv.DictReader((path or ROOT / 'destinations.csv').open(encoding='utf-8')))
    for d in places:
        d['tag_set'] = set(d['tags'].split(';')) if d['tags'] else set()
        d['alias_list'] = [a.strip() for a in d['aliases'].split(';') if a.strip()]
        d['floor_n'] = int(d['floor']) if d['floor'].isdigit() else None
    return places


def _norm_text(text):
    return ' '.join(norm(text))


FLOOR4 = re.compile(r'\b(4f|4 f|floor 4|4th floor|lantai 4|lower floor|lower|bawah)\b')
FLOOR5 = re.compile(r'\b(5f|5 f|floor 5|5th floor|lantai 5|upper floor|upper|atas)\b')


def floor_hint(q):
    """4, 5 or None from words such as 4F / lower floor / bawah (4F) and 5F / upper / atas (5F)."""
    a, b = bool(FLOOR4.search(q)), bool(FLOOR5.search(q))
    return 4 if a and not b else 5 if b and not a else None


# ---------------------------------------------------------------- keyword
def keyword_match(query, places):
    """Longest whole-word alias wins; ties go to the place on the hinted floor; then tag-word hits."""
    q = _norm_text(query)
    qtok, hint = set(q.split()), floor_hint(q)
    best, best_key = None, (0, 0, 0)
    for d in places:
        alias = max((len(' '.join(norm(a))) for a in d['alias_list'] if re.search(r'\b' + re.escape(' '.join(norm(a))) + r'\b', q)), default=0)
        tags = len(qtok & d['tag_set'])
        if not (alias or tags):
            continue
        key = (alias, int(hint is not None and d['floor_n'] == hint), tags)
        if key > best_key:
            best_key, best = key, d['place_id']
    return best, float(best_key[0] or best_key[2])


def keyword_v1_match(query, places):
    """The starter method as it was: substring alias match (so 'eat' matches inside 'theatre')."""
    q = re.sub(r'[^a-z0-9 ]', ' ', query.lower()); q = ' '.join(q.split()); qtok = set(q.split())
    best, best_key = None, (0, 0)
    for d in places:
        alias = max((len(a) for a in d['alias_list'] if a in q), default=0)
        tags = len(qtok & d['tag_set'])
        key = (alias, tags)
        if key > best_key and (alias or tags):
            best_key, best = key, d['place_id']
    return best, float(best_key[0] or best_key[1])


_IDF = {}


def tokens_match(query, places):
    if not _IDF:
        docs = {d['place_id']: set(norm(' '.join([d['name']] + d['alias_list'] + list(d['tag_set'])))) for d in places}
        df = Counter(t for toks in docs.values() for t in toks)
        _IDF['docs'] = docs
        _IDF['idf'] = {t: math.log((len(docs) + 1) / (c + 0.5)) for t, c in df.items()}
    qtok = [t for t in norm(query) if t not in STOP]
    best, best_score = None, 0.0
    for d in places:
        score = sum(_IDF['idf'].get(t, 0) for t in qtok if t in _IDF['docs'][d['place_id']])
        if score > best_score:
            best_score, best = score, d['place_id']
    return best, best_score


# ---------------------------------------------------------------- embeddings
_EMB = {}


def _tuned():
    p = ROOT / 'tuned.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def _emb_model():
    if 'model' not in _EMB:
        from sentence_transformers import SentenceTransformer
        _EMB['model'] = SentenceTransformer(EMBED_MODEL)
    return _EMB['model']


def _emb_index(places, variant):
    """variant 'embed': one vector per name, per alias and per tag, score = max over a place's vectors.
    variant 'embed_doc': one vector per place from 'name; aliases; tags'."""
    if variant in _EMB:
        return _EMB[variant]
    texts, owner = [], []
    for i, d in enumerate(places):
        if variant == 'embed':
            for t in [d['name']] + d['alias_list'] + sorted(d['tag_set']):
                texts.append(t); owner.append(i)
        else:
            texts.append('; '.join([d['name']] + d['alias_list'] + sorted(d['tag_set']))); owner.append(i)
    vecs = _emb_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    _EMB[variant] = (vecs, owner)
    return _EMB[variant]


def embed_scores(query, places, variant='embed'):
    """Cosine score per place (list in places order)."""
    vecs, owner = _emb_index(places, variant)
    qv = _emb_model().encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    sims = vecs @ qv
    best = [-1.0] * len(places)
    for s, o in zip(sims, owner):
        best[o] = max(best[o], float(s))
    return best


def embed_match(query, places, variant='embed', threshold=None):
    sc = embed_scores(query, places, variant)
    i = max(range(len(sc)), key=sc.__getitem__)
    th = threshold if threshold is not None else _tuned().get(variant, {}).get('threshold', 0.0)
    return (places[i]['place_id'] if sc[i] >= th else None), sc[i]


# ---------------------------------------------------------------- LLM
LLM_SYSTEM = (
    "You map a typed request from a student in one university building to exactly ONE place from a fixed list. "
    "Reply with one place ID copied exactly from the list, or the word NONE. Output only that single token: no "
    "explanation, no punctuation, no quotes. "
    "Answer NONE when no place in the list fits the request, when the request names a place that is not in the list "
    "(for example a room number that does not exist), or when the request is not about finding a place. "
    "The request may contain typos, Indonesian, Cantonese or a mix of languages. "
    "When several places fit equally (for example toilets or escalators on different floors) and the request does not "
    "say which floor, pick any one of them. Floor 5 is the upper floor (atas), floor 4 the lower floor (bawah).")


def llm_places_block(places):
    lines = []
    for d in places:
        lines.append(f"{d['place_id']} | {d['name']} | floor {d['floor']} | tags: {', '.join(sorted(d['tag_set']))} | "
                     f"also called: {', '.join(d['alias_list'])}")
    return '\n'.join(lines)


def llm_prompt(query, places):
    return ("Place list (ID | name | floor | tags | also called):\n" + llm_places_block(places) +
            "\n\nRequest: " + json.dumps(query, ensure_ascii=False) + "\nAnswer (one ID from the list, or NONE):")


def llm_cache_path(version=None):
    return ROOT / f'llm_cache_{version or LLM_PROMPT_VERSION}.json'


def _load_cache(version=None):
    p = llm_cache_path(version)
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {'meta': {}, 'responses': {}}


def parse_llm(raw, valid_ids):
    """(parsed, valid): strip quotes/backticks/trailing punctuation; valid = a real ID or NONE exactly."""
    t = raw.strip().strip('`"\'*').strip().rstrip('.').strip('`"\'*').strip()
    return t, (t in valid_ids or t == 'NONE')


def llm_answer(query, places, allow_call=True, version=None):
    """Cached raw reply of the model for this query (calls the Claude CLI if not cached and allow_call)."""
    cache = _load_cache(version)
    r = cache['responses'].get(query)
    if r is not None or not allow_call:
        return r
    prompt = llm_prompt(query, places)
    cmd = ['claude', '-p', '--model', LLM_MODEL, '--tools', '', '--no-session-persistence', '--disable-slash-commands',
           '--setting-sources', '', '--strict-mcp-config', '--system-prompt', LLM_SYSTEM, '--output-format', 'json', prompt]
    with tempfile.TemporaryDirectory() as cwd:          # neutral folder: no project CLAUDE.md is picked up
        t0 = time.perf_counter()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=cwd)
        dt = time.perf_counter() - t0
    try:
        j = json.loads(p.stdout)
        raw, cost, model = j.get('result', ''), j.get('total_cost_usd'), next(iter(j.get('modelUsage', {})), None)
        err = j.get('is_error', False)
        api_ms = j.get('duration_api_ms')
    except json.JSONDecodeError:
        raw, cost, model, err, api_ms = p.stdout + p.stderr, None, None, True, None
    ids = {d['place_id'] for d in places}
    parsed, valid = parse_llm(raw, ids)
    r = {'raw': raw, 'parsed': parsed, 'valid': bool(valid and not err), 'latency_s': round(dt, 3), 'api_ms': api_ms,
         'cost_usd': cost, 'model': model, 'error': bool(err),
         'time_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
    cache = _load_cache(version)                         # reload: another call may have written meanwhile
    cache['meta'] = {'cli_model_flag': LLM_MODEL, 'prompt_version': version or LLM_PROMPT_VERSION,
                     'command': 'claude -p --model ' + LLM_MODEL + " --tools '' --no-session-persistence "
                                "--disable-slash-commands --setting-sources '' --strict-mcp-config "
                                "--system-prompt <system> --output-format json <prompt>  (run from an empty temp dir)",
                     'system_prompt': LLM_SYSTEM, 'user_prompt_example': llm_prompt('<request>', places),
                     'claude_cli_version': subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()}
    cache['responses'][query] = r
    llm_cache_path(version).write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')
    return r


def llm_match(query, places, allow_call=True):
    r = llm_answer(query, places, allow_call)
    if r is None or not r['valid'] or r['parsed'] == 'NONE':
        return None, 0.0
    return r['parsed'], 1.0


# ---------------------------------------------------------------- fuzzy keyword and hybrid (keyword -> fuzzy -> LLM)
FUZZY_MIN_ALIAS = 4          # aliases shorter than this (wc, lt, sr, ...) are never fuzzy-matched: too many false hits


def _fuzzy_cutoff():
    return _tuned().get('fuzzy', {}).get('cutoff', 0.85)


def fuzzy_match(query, places, cutoff=None):
    """Typo-tolerant alias match (stdlib difflib): every alias of >= FUZZY_MIN_ALIAS characters is compared with the
    query n-grams of the same number of words; best SequenceMatcher ratio >= cutoff wins (ties: longer alias, then the
    hinted floor). Returns (place_id | None, ratio)."""
    cutoff = _fuzzy_cutoff() if cutoff is None else cutoff
    toks = norm(query)
    hint = floor_hint(' '.join(toks))
    grams = {}
    for n in (1, 2, 3):
        grams[n] = [' '.join(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    best, best_key = None, (0.0, 0, 0)
    for d in places:
        for a in d['alias_list']:
            an = ' '.join(norm(a))
            if len(an) < FUZZY_MIN_ALIAS:
                continue
            n = len(an.split())
            for g in grams.get(n, []):
                if n == 1 and g in STOP:
                    continue
                r = difflib.SequenceMatcher(None, an, g).ratio()
                key = (round(r, 6), len(an), int(hint is not None and d['floor_n'] == hint))
                if r >= cutoff and key > best_key:
                    best_key, best = key, d['place_id']
    return best, float(best_key[0])


def fuzzy_keyword_match(query, places, cutoff=None):
    """Keyword first (whole word + aliases); only if it finds nothing, the fuzzy alias match. No LLM."""
    pid, sc = keyword_match(query, places)
    if pid is not None:
        return pid, sc, 'keyword'
    pid, sc = fuzzy_match(query, places, cutoff)
    return pid, sc, ('fuzzy' if pid is not None else 'none')


def hybrid_match(query, places, allow_call=False):
    """Keyword -> fuzzy -> LLM, the LLM only when neither finds a place. Returns (place_id | None, score, stage, llm_reply).
    stage: 'keyword', 'fuzzy', 'llm' (the LLM was asked) or 'llm_missing' (no cached answer and calls not allowed)."""
    pid, sc, stage = fuzzy_keyword_match(query, places)
    if pid is not None:
        return pid, sc, stage, None
    r = llm_answer(query, places, allow_call=allow_call)
    if r is None:
        return None, 0.0, 'llm_missing', None
    pid = r['parsed'] if r['valid'] and r['parsed'] != 'NONE' else None
    return pid, (1.0 if pid else 0.0), 'llm', r


# ---------------------------------------------------------------- one entry point
_PLACES = []


def match(query, method='keyword'):
    """Return (place_id or None, score). None = "no place in our list fits".
    The score is method specific: keyword = matched alias length, embed = cosine, llm = 1.0 (0.0 for NONE/invalid)."""
    if not _PLACES:
        _PLACES.extend(load_places())
    places = _PLACES
    if method == 'keyword':
        return keyword_match(query, places)
    if method == 'keyword_v1':
        return keyword_v1_match(query, places)
    if method == 'tokens':
        return tokens_match(query, places)
    if method in ('embed', 'embed_doc'):
        return embed_match(query, places, method)
    if method == 'llm':
        return llm_match(query, places)
    if method == 'fuzzy_keyword':
        return fuzzy_keyword_match(query, places)[:2]
    if method == 'hybrid':
        return hybrid_match(query, places, allow_call=True)[:2]
    raise ValueError('unknown method ' + method)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        sys.exit('usage: python match.py "where can I eat" [keyword|embed|llm|fuzzy_keyword|hybrid|all]')
    q = sys.argv[1]
    names = {d['place_id']: d['name'] for d in load_places()}
    for m in (METHODS if len(sys.argv) < 3 or sys.argv[2] == 'all' else sys.argv[2:]):
        pid, sc = match(q, m)
        print(f'{m:11} -> {pid or "(none)":20} {names.get(pid, ""):38} score {sc:.3f}')
