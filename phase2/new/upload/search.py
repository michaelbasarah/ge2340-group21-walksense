"""Search and route planner for the upload app: typed question -> one of our 26 places + a route from where you are.

    import search
    search.search('where can I study', from_id=None, tracked=(5, 'canteen'))   # -> dict for GET /api/search
    search.plan_route('y5302', 'female_toilet', mode='accessible')            # -> dict for GET /api/route
    search.nearest('toilet', from_id='lt1a', gender='female')                 # -> dict for GET /api/nearest

Order: Gemini (if GEMINI_API_KEY is in the repo-root .env) -> keyword -> fuzzy (both offline, request-matching/match.py).
Gemini gets the same grounded place list as the request-matching LLM method and must answer one listed place ID or
NONE plus one short sentence. No key, no internet, a timeout, an HTTP error or an unusable reply all fall back to
keyword -> fuzzy, and the reply says which method answered. The key never leaves the server.
Route: A* of phase2/new/routing/route.py `plan()` on routing/graph.json (imported, not copied; named astar_route here
because this folder's route.py is the walking dot), with a mode: standard (every connector) or accessible (lifts only).
Toilet requests ("toilet", "restroom", or any place that resolves to a toilet) go to the nearest toilet that fits the
mode and the gender filter (routing/route.py nearest_toilet), not just the matched place. Standard mode answers with an
ordinary toilet whenever one fits and keeps the disabled toilets free (entry 90); Step-free or "disabled" words ->
disabled toilets only.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQ = HERE.parents[1] / 'request-matching'
ROUTING = HERE.parent / 'routing'
if str(REQ) not in sys.path:
    sys.path.insert(0, str(REQ))
import gemini                  # noqa: E402  (request-matching/gemini.py)
import match as M              # noqa: E402  (request-matching/match.py)

_spec = importlib.util.spec_from_file_location('astar_route', ROUTING / 'route.py')
if _spec is None or _spec.loader is None:
    raise ImportError(f'cannot load the routing code from {ROUTING / "route.py"}')
astar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(astar)

# routing graph id -> (floor, key in map/floorplan.json and map/places.json). Written out by hand from
# floorplan.json "graph_id" and destinations.csv "map_key"; test_search.py checks it against both files.
# Map keys repeat across floors (exit5_door, esca_up, ... and lift_stairs5 is also the 4F lift), so the floor is part of the key.
GRAPH_TO_MAP = {
    'canteen': (5, 'canteen'), 'exit_5': (5, 'exit5_door'), 'male_toilet': (5, 'male_toilet'), 'y5302': (5, 'y5302'),
    'sr9': (5, 'sr9'), 'y5202': (5, 'y5202'), 'female_toilet': (5, 'female_toilet'), 'exit_10': (5, 'exit10_door'),
    'escalator_up': (5, 'esca_up'), 'escalator_down': (5, 'esca_down'), 'disabled_toilet': (5, 'male_disabled_toilet'),
    'y5401': (5, 'y5401'), 'y5302_back': (5, 'y5302_point2'), 'lift_stairs': (5, 'lift_stairs5'),
    'disabled_toilet_4F': (4, 'disabled_toilet'), 'exit_5_4F': (4, 'exit5_door'), 'lt2a': (4, 'lt2a'), 'lt2b': (4, 'lt2b'),
    'escalator_down_4F': (4, 'esca_down'), 'y4502': (4, 'y4502'), 'escalator_up_4F': (4, 'esca_up'), 'lt1b': (4, 'lt1b'),
    'lt1a': (4, 'lt1a'), 'exit_10_4F': (4, 'exit10_door'), 'entrance_exit': (4, 'gate'), 'lift_stairs_4F': (4, 'lift_stairs5'),
}
MAP_TO_GRAPH = {v: k for k, v in GRAPH_TO_MAP.items()}
DEFAULT_FROM = 'entrance_exit'       # the 4F entrance gate, when nothing is tracked and nothing is chosen
MAX_QUERY = 200
PAUSE_S = 60                         # after no internet / timeout / quota: answer offline for this long, then try again

PLACES = M.load_places()
BY_ID = {d['place_id']: d for d in PLACES}
_state = {'paused_until': 0.0, 'disabled': '', 'last_error': ''}
_cache = {}                          # query -> (place_id, answer) from Gemini, for this server run
_lock = threading.Lock()


def gemini_status():
    key, model = gemini.settings()
    return {'configured': bool(key), 'model': model if key else None,
            'error': _state['disabled'] or _state['last_error'] or None}


def ask_gemini(query):
    """(place_id | None, answer, error | None). error set = Gemini not usable now (fall back)."""
    key, _ = gemini.settings()
    if not key:
        return None, '', 'no Gemini key in .env'
    if _state['disabled']:
        return None, '', _state['disabled']
    if time.time() < _state['paused_until']:
        return None, '', _state['last_error'] or 'Gemini paused'
    q = ' '.join(query.lower().split())
    with _lock:
        if q in _cache:
            return (*_cache[q], None)
    try:
        raw, _ = gemini.generate(M.ASK_SYSTEM, M.ask_prompt(query, PLACES), json_mode=True)
        pid, ans = M.parse_ask(raw, set(BY_ID))
    except gemini.GeminiError as e:
        _state['last_error'] = str(e)
        if e.kind in ('bad_key', 'bad_model'):
            _state['disabled'] = str(e)              # will not fix itself: needs a new .env and a restart
        elif e.kind in ('network', 'timeout', 'quota', 'server'):
            _state['paused_until'] = time.time() + PAUSE_S
        return None, '', str(e)
    except (ValueError, TypeError) as e:
        _state['last_error'] = f'Gemini reply not usable ({e})'
        return None, '', _state['last_error']
    _state['last_error'] = ''
    with _lock:
        if len(_cache) < 2000:
            _cache[q] = (pid, ans)
    return pid, ans, None


def place_line(pid):
    d = BY_ID[pid]
    return d['name'] if f"({d['floor']}F)" in d['name'] else f"{d['name']} ({d['floor']}F)"


MODES = tuple(astar.PROFILES)          # standard, accessible
GENDERS = astar.GENDERS                 # any, male, female
TOILET_WORDS = re.compile(r'\b(toilets?|restrooms?|washrooms?|bathrooms?|wc|lavatory|loo|pee|poo|gents|ladies|'
                          r'kamar kecil|kamar mandi)\b')
MALE_WORDS = re.compile(r'\b(male|men|mens|man|gents|gentlemen|boys?|cowo|cowok|laki|pria)\b')
FEMALE_WORDS = re.compile(r'\b(female|women|womens|woman|ladies|lady|girls?|cewe|cewek|perempuan|wanita)\b')
ACCESS_WORDS = re.compile(r'\b(disabled|disability|accessible|wheelchair|handicap|handicapped|disabilitas|difabel)\b')


def check_mode(mode, gender='any'):
    """-> (mode, gender) with defaults; KeyError with a plain message if one is not allowed."""
    mode, gender = (mode or 'standard'), (gender or 'any')
    if mode not in MODES:
        raise KeyError(f'mode must be one of {", ".join(MODES)}')
    if gender not in GENDERS:
        raise KeyError(f'gender must be one of {", ".join(GENDERS)}')
    return mode, gender


def route_payload(p):
    """routing Plan -> the JSON the page draws: steps (one per place), legs (one per hop), connectors, totals."""
    g = astar.graph(p.mode)
    steps = []
    for i, n in enumerate(p.path):
        floor, key = GRAPH_TO_MAP[n]
        st = {'id': n, 'name': g.nodes[n]['name'], 'floor': floor, 'map_key': key}
        if i:
            e = p.legs[i - 1]
            st.update(mode=e['kind'], metres=e['metres'], seconds=e['seconds'])
        steps.append(st)
    legs = [{'from': a, 'to': b, 'kind': e['kind'], 'metres': e['metres'], 'seconds': e['seconds'],
             'length_status': e['length_status'], 'from_floor': GRAPH_TO_MAP[a][0], 'to_floor': GRAPH_TO_MAP[b][0]}
            for a, b, e in zip(p.path, p.path[1:], p.legs)]
    return {'path': list(p.path), 'route': steps, 'legs': legs, 'connectors': p.connectors, 'instructions': p.instructions,
            'distance_m': p.metres, 'seconds': p.seconds, 'mode': p.mode}


def route_steps(start, goal, mode='standard'):
    """Planner route -> (steps, instructions, metres, seconds). steps: one dict per place on the path."""
    r = route_payload(astar.plan(start, goal, mode))
    return r['route'], r['instructions'], r['distance_m'], r['seconds']


def resolve_start(from_id=None, tracked=None):
    """-> {id, name, floor, source}: the chosen place, else the tracked (lit) place, else the 4F entrance gate."""
    if from_id in GRAPH_TO_MAP:
        start, how = from_id, 'chosen'
    elif tracked and tuple(tracked) in MAP_TO_GRAPH:
        start, how = MAP_TO_GRAPH[tuple(tracked)], 'tracked'
    else:
        start, how = DEFAULT_FROM, 'default'
    return {'id': start, 'name': astar.graph().nodes[start]['name'], 'floor': GRAPH_TO_MAP[start][0], 'source': how}


def plan_route(from_id, to_id, mode='standard', tracked=None):
    """The /api/route reply. KeyError for an unknown place or mode."""
    mode, _ = check_mode(mode)
    if to_id not in GRAPH_TO_MAP:
        raise KeyError('unknown destination %r' % to_id)
    if from_id and from_id not in GRAPH_TO_MAP:
        raise KeyError('unknown start %r' % from_id)
    start = resolve_start(from_id, tracked)
    out = {'from': start, 'to': {'id': to_id, 'name': astar.graph().nodes[to_id]['name'], 'floor': GRAPH_TO_MAP[to_id][0]},
           'mode': mode, 'speed_mps': astar.graph().speed}
    try:
        out.update(route_payload(astar.plan(start['id'], to_id, mode)))
    except ValueError as e:
        out.update(route=[], legs=[], connectors=[], instructions=[], distance_m=None, seconds=None, route_error=str(e))
    return out


def toilet_query(query):
    """-> None if the query is not about a toilet, else {gender, accessible, floor} read from its words."""
    q = ' '.join(M.norm(query))
    if not TOILET_WORDS.search(q):
        return None
    gender = 'female' if FEMALE_WORDS.search(q) else 'male' if MALE_WORDS.search(q) else None
    return {'gender': gender, 'accessible': bool(ACCESS_WORDS.search(q)), 'floor': M.floor_hint(q)}


def nearest(kind, from_id=None, mode='standard', gender='any', tracked=None, floor=None, accessible_only=False):
    """The /api/nearest reply (kind = toilet). Nearest suitable toilet by route, with every option and why the others
    were left out; place_id None + a clear message when the filter leaves no toilet."""
    mode, gender = check_mode(mode, gender)
    if kind != 'toilet':
        raise KeyError('type must be toilet')
    if from_id and from_id not in GRAPH_TO_MAP:
        raise KeyError('unknown start %r' % from_id)
    start = resolve_start(from_id, tracked)
    t = astar.nearest_toilet(start['id'], mode, gender, floor=floor, accessible_only=accessible_only)
    out = {'type': kind, 'mode': mode, 'gender': gender, 'floor_filter': floor, 'accessible_only': accessible_only or mode == 'accessible',
           'from': start, 'place_id': t['toilet'], 'answer': t['message'],
           'options': [{k: v for k, v in o.items() if k != 'plan'} for o in t['options']], 'excluded': t['excluded'],
           'policy': t['policy'], 'policy_note': t['policy_note'],
           'route': [], 'legs': [], 'connectors': [], 'instructions': [], 'distance_m': None, 'seconds': None}
    if t['choice'] is not None:
        pid = t['toilet']
        out.update(name=BY_ID[pid]['name'], floor=int(BY_ID[pid]['floor']), map_key=GRAPH_TO_MAP[pid][1])
        out.update(route_payload(t['choice']))
    else:
        out.update(name=None, floor=None)
    return out


def place_options():
    """[{id, name, floor, map_key, kind}] for the page's From / To lists and map taps, 5F first, in graph order."""
    g = astar.graph()
    return sorted(({'id': n, 'name': g.nodes[n]['name'], 'floor': GRAPH_TO_MAP[n][0], 'map_key': GRAPH_TO_MAP[n][1],
                    'kind': g.nodes[n]['kind']} for n in g.nodes), key=lambda o: -o['floor'])


def search(query, from_id=None, tracked=None, mode='standard', gender='any'):
    """The /api/search reply. tracked = (floor, map key) of the live / last lit place, or None.
    mode / gender: the viewer's settings (standard | accessible, any | male | female); a toilet request is answered
    with the nearest toilet that fits them (words in the query, e.g. "ladies", "disabled", "4F", win over the filter)."""
    mode, gender = check_mode(mode, gender)
    query = ' '.join((query or '').split())[:MAX_QUERY]
    out = {'query': query, 'place_id': None, 'name': None, 'floor': None, 'method': 'none', 'answer': '',
           'route': [], 'legs': [], 'connectors': [], 'instructions': [], 'distance_m': None, 'seconds': None, 'from': None,
           'gemini': None, 'mode': mode, 'gender': gender}
    if not query:
        out['answer'] = 'Type a place or a question, for example "toilet", "Y5-302" or "where can I study".'
        out['gemini'] = gemini_status()
        return out
    pid, ans, err = ask_gemini(query)
    if err is None:
        out['method'] = 'gemini'
    else:
        out['fallback_reason'] = err
        pid, _, stage = M.fuzzy_keyword_match(query, PLACES)
        out['method'] = stage                         # keyword / fuzzy / none
        ans = ''
    out['gemini'] = gemini_status()
    tq = toilet_query(query)
    if tq is None and pid is not None and BY_ID[pid]['kind'] == 'toilet':
        tq = {'gender': None, 'accessible': False, 'floor': None}     # resolved to a toilet without a toilet word
    if pid is None and tq is None:
        out['answer'] = ans or ('Sorry, I could not find that in the area WalkSense covers (AC1 floors 5 and 4). '
                                'Try a room like Y5-302, or "toilet", "canteen", "exit", "lift".')
        return out
    out['from'] = resolve_start(from_id, tracked)
    if tq is not None:                                # toilet: nearest one that fits the mode and the filter
        g_use = tq['gender'] or gender
        t = nearest('toilet', out['from']['id'], mode, g_use, floor=tq['floor'], accessible_only=tq['accessible'])
        out['toilet'] = {k: t[k] for k in ('gender', 'floor_filter', 'accessible_only', 'options', 'excluded', 'policy', 'policy_note')}
        if tq['gender'] and tq['gender'] != gender:
            out['toilet']['note'] = f'Your words asked for a {tq["gender"]} toilet, so the {gender} filter was not used.'
        if t['place_id'] is None:
            out.update(place_id=None, answer=t['answer'])
            if pid is not None:
                out['matched_place'] = pid
            return out
        if pid is not None and pid != t['place_id']:
            out['matched_place'] = pid                # what Gemini / keyword picked before the filter
            ans = ''
        pid = t['place_id']
        ans = ans or t['answer']
    d = BY_ID[pid]
    out.update(place_id=pid, name=d['name'], floor=int(d['floor']), map_key=GRAPH_TO_MAP[pid][1],
               answer=ans or f'{place_line(pid)}: the route is below.')
    if mode == 'accessible' and d['kind'] == 'escalator':
        out['answer'] += ' Step-free mode: the route avoids escalators and stairs; take the lift to change floor.'
    try:
        out.update(route_payload(astar.plan(out['from']['id'], pid, mode)))
    except (KeyError, ValueError) as e:
        out['route_error'] = str(e)
    return out
