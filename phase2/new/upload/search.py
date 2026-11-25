"""Search for the upload app: typed question -> one of our 26 places + a route from where you are.

    import search
    search.search('where can I study', from_id=None, tracked=(5, 'canteen'))   # -> dict for GET /api/search

Order: Gemini (if GEMINI_API_KEY is in the repo-root .env) -> keyword -> fuzzy (both offline, request-matching/match.py).
Gemini gets the same grounded place list as the request-matching LLM method and must answer one listed place ID or
NONE plus one short sentence. No key, no internet, a timeout, an HTTP error or an unusable reply all fall back to
keyword -> fuzzy, and the reply says which method answered. The key never leaves the server.
Route: A* of phase2/new/routing/route.py on routing/graph.json (imported, not copied; named astar_route here because
this folder's route.py is the walking dot).
"""
from __future__ import annotations

import importlib.util
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


def route_steps(start, goal):
    """A* route -> (steps, instructions, metres, seconds). steps: one dict per place on the path."""
    r = astar.route(start, goal)
    g = astar.graph()
    steps = []
    for i, n in enumerate(r.path):
        node = g.nodes[n]
        floor, key = GRAPH_TO_MAP[n]
        st = {'id': n, 'name': node['name'], 'floor': floor, 'map_key': key}
        if i:
            e = g.edge[(r.path[i - 1], n)]
            st.update(mode=e['mode'], metres=e['metres'], seconds=e['seconds'])
        steps.append(st)
    return steps, r.instructions, r.metres, r.seconds


def place_options():
    """[{id, name, floor}] for the page's "from" list, 5F first, in graph order."""
    g = astar.graph()
    return sorted(({'id': n, 'name': g.nodes[n]['name'], 'floor': GRAPH_TO_MAP[n][0]} for n in g.nodes),
                  key=lambda o: -o['floor'])


def search(query, from_id=None, tracked=None):
    """The /api/search reply. tracked = (floor, map key) of the live / last lit place, or None."""
    query = ' '.join((query or '').split())[:MAX_QUERY]
    out = {'query': query, 'place_id': None, 'name': None, 'floor': None, 'method': 'none', 'answer': '',
           'route': [], 'instructions': [], 'distance_m': None, 'seconds': None, 'from': None, 'gemini': None}
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
    if pid is None:
        out['answer'] = ans or ('Sorry, I could not find that in the area WalkSense covers (AC1 floors 5 and 4). '
                                'Try a room like Y5-302, or "toilet", "canteen", "exit", "lift".')
        return out
    d = BY_ID[pid]
    out.update(place_id=pid, name=d['name'], floor=int(d['floor']), map_key=GRAPH_TO_MAP[pid][1],
               answer=ans or f'{place_line(pid)}: the route is below.')
    # start: the place chosen in the "from" list, else the tracked place, else the entrance gate
    if from_id in GRAPH_TO_MAP:
        start, how = from_id, 'chosen'
    elif tracked and tuple(tracked) in MAP_TO_GRAPH:
        start, how = MAP_TO_GRAPH[tuple(tracked)], 'tracked'
    else:
        start, how = DEFAULT_FROM, 'default'
    out['from'] = {'id': start, 'name': astar.graph().nodes[start]['name'], 'floor': GRAPH_TO_MAP[start][0], 'source': how}
    try:
        steps, instr, metres, sec = route_steps(start, pid)
        out.update(route=steps, instructions=instr, distance_m=metres, seconds=sec)
    except (KeyError, ValueError) as e:
        out['route_error'] = str(e)
    return out
