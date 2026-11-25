"""A* against Dijkstra on every ordered pair, heuristic checks, speed sensitivity -> out/astar_check.json"""
import copy
import itertools
import json
import time
from pathlib import Path

from route import Graph, graph

HERE = Path(__file__).resolve().parent


def main():
    g = graph()
    ids = sorted(g.nodes)
    pairs = [(a, b) for a, b in itertools.product(ids, ids) if a != b]
    cost_diff = 0.0
    mismatched = []
    exp_a = exp_d = 0
    inadmissible = inconsistent = 0
    t_a = t_d = 0.0
    truth = {}
    for a, b in pairs:
        t = time.perf_counter(); pa, ca, ea = g.search(a, b, True); t_a += time.perf_counter() - t
        t = time.perf_counter(); pd, cd, ed = g.search(a, b, False); t_d += time.perf_counter() - t
        truth[(a, b)] = cd
        exp_a += ea; exp_d += ed
        diff = abs(ca - cd)
        cost_diff = max(cost_diff, diff)
        if diff > 1e-9:
            mismatched.append((a, b, ca, cd))
        pc = g.path_cost(pa)
        assert pc is not None and abs(pc[0] - ca) < 1e-9
    # heuristic: admissible h(n,goal) <= true cost, consistent h(u,goal) <= w(u,v) + h(v,goal)
    for (a, b), c in truth.items():
        if g.h(a, b) > c + 1e-9:
            inadmissible += 1
    for goal in ids:
        for u in ids:
            for v, sec, _, _ in g.adj[u]:
                if g.h(u, goal) > sec + g.h(v, goal) + 1e-9:
                    inconsistent += 1
    # strongly connected
    unreachable = [(a, b) for a, b in pairs if truth.get((a, b)) is None]
    # speed sensitivity: does the optimal path change if people walk slower (the team's own walks: 0.54 m/step x 1.55 steps/s)?
    sens = {}
    for speed in (0.84, 1.0, 1.3, 1.5):
        d = copy.deepcopy(g.data)
        d['speed_mps'] = speed
        for e in d['edges']:
            if e['mode'] == 'walk':
                e['seconds'] = e['metres'] / speed
        g2 = Graph(d)
        changed = sum(1 for a, b in pairs if g2.search(a, b)[0] != g.search(a, b)[0])
        sens[str(speed)] = {'pairs_with_different_path_vs_1.3': changed}
    out = {
        'nodes': len(ids), 'ordered_pairs': len(pairs), 'pairs_cost_mismatch_astar_vs_dijkstra': len(mismatched),
        'max_abs_cost_difference_s': cost_diff, 'mismatches': mismatched,
        'heuristic_inadmissible_pairs': inadmissible, 'heuristic_inconsistent_edges': inconsistent,
        'heuristic_scale_per_floor': {str(k): round(v, 4) for k, v in g.scale.items()},
        'expansions_total_astar': exp_a, 'expansions_total_dijkstra': exp_d,
        'expansions_mean_astar': round(exp_a / len(pairs), 2), 'expansions_mean_dijkstra': round(exp_d / len(pairs), 2),
        'time_per_query_ms_astar': round(1000 * t_a / len(pairs), 4), 'time_per_query_ms_dijkstra': round(1000 * t_d / len(pairs), 4),
        'walking_speed_sensitivity': sens,
    }
    (HERE / 'out').mkdir(exist_ok=True)
    (HERE / 'out' / 'astar_check.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'mismatches'}, indent=1))


if __name__ == '__main__':
    main()
