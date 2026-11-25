"""python -m unittest phase2/new/routing/test_route.py   (from the repo root, or run inside this folder)"""
import unittest

import route as R


class RouteTests(unittest.TestCase):
    def test_astar_equals_dijkstra_all_pairs(self):
        g = R.graph()
        for a in g.nodes:
            for b in g.nodes:
                if a != b:
                    self.assertAlmostEqual(g.search(a, b, True)[1], g.search(a, b, False)[1], places=9)

    def test_heuristic_admissible_consistent(self):
        g = R.graph()
        for goal in g.nodes:
            for u in g.nodes:
                self.assertLessEqual(g.h(u, goal), g.search(u, goal, False)[1] + 1e-9)
                for v, sec, _, _ in g.adj[u]:
                    self.assertLessEqual(g.h(u, goal), sec + g.h(v, goal) + 1e-9)

    def test_escalators_one_way(self):
        g = R.graph()
        self.assertIn(('escalator_down', 'escalator_down_4F'), g.edge)
        self.assertNotIn(('escalator_down_4F', 'escalator_down'), g.edge)
        self.assertIn(('escalator_up_4F', 'escalator_up'), g.edge)
        self.assertNotIn(('escalator_up', 'escalator_up_4F'), g.edge)
        p = R.route('escalator_up', 'escalator_down_4F').path       # 5F up escalator cannot go down: must walk first
        self.assertEqual(p[:2], ['escalator_up', 'escalator_down'])

    def test_route_api(self):
        r = R.route('canteen', 'lt1a')
        path, metres, seconds, instr = r
        self.assertEqual((path[0], path[-1]), ('canteen', 'lt1a'))
        self.assertGreater(seconds, 0)
        self.assertTrue(instr[0].startswith('Start at') and instr[-1].startswith('You have arrived'))
        self.assertEqual(R.route('canteen', 'canteen').path, ['canteen'])


if __name__ == '__main__':
    unittest.main()
