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


class PlannerTests(unittest.TestCase):
    """Route planner: connectors split into lift / stairs / escalator, modes, toilets."""
    KINDS_CHANGE = {'lift', 'stairs', 'escalator'}

    def test_connectors_split(self):
        g = R.graph('standard')
        par = g.parallel[('lift_stairs', 'lift_stairs_4F')]
        self.assertEqual(sorted(e['kind'] for e in par), ['lift', 'stairs'])
        self.assertEqual(sorted(e['kind'] for e in g.parallel[('lift_stairs_4F', 'lift_stairs')]), ['lift', 'stairs'])
        lift = next(e for e in par if e['kind'] == 'lift')
        self.assertEqual(lift['seconds'], R.LIFT_WAIT_S + R.LIFT_RIDE_S)
        self.assertEqual(lift['metres'], 0.0)
        # the research graph (profile None) is graph.json unchanged: one lift_stairs edge
        self.assertEqual(R.graph().edge[('lift_stairs', 'lift_stairs_4F')]['mode'], 'lift_stairs')

    def test_escalators_directional_in_every_mode(self):
        for mode in R.PROFILES:
            g = R.graph(mode)
            for (a, b), e in g.edge.items():
                if e['kind'] == 'escalator':
                    self.assertIn((a, b), {('escalator_down', 'escalator_down_4F'), ('escalator_up_4F', 'escalator_up')})
        g = R.graph('standard')
        self.assertNotIn(('escalator_down_4F', 'escalator_down'), g.edge)
        self.assertNotIn(('escalator_up', 'escalator_up_4F'), g.edge)
        # standard 4F -> 5F from the up escalator rides it; 5F -> 4F from the down escalator rides it
        self.assertEqual(R.plan('escalator_up_4F', 'escalator_up').connectors[0]['kind'], 'escalator')
        self.assertEqual(R.plan('escalator_down', 'escalator_down_4F').connectors[0]['kind'], 'escalator')
        # the 5F up escalator cannot take you down: walk to the down escalator first
        p = R.plan('escalator_up', 'escalator_down_4F')
        self.assertEqual(p.path[:3], ['escalator_up', 'escalator_down', 'escalator_down_4F'])

    def test_accessible_never_stairs_or_escalator(self):
        g = R.graph('accessible')
        self.assertFalse({e['kind'] for e in g.edge.values()} & {'stairs', 'escalator'})
        for a in g.nodes:
            for b in g.nodes:
                if a == b:
                    continue
                p = R.plan(a, b, 'accessible')
                kinds = {e['kind'] for e in p.legs}
                self.assertFalse(kinds & {'stairs', 'escalator'}, (a, b))
                if g.nodes[a]['floor'] != g.nodes[b]['floor']:
                    self.assertEqual([c['kind'] for c in p.connectors], ['lift'], (a, b))
                    self.assertTrue(any(t.startswith('Take the lift') for t in p.instructions))

    def test_lift_chosen_when_stairs_excluded(self):
        # lift core to lift core: standard takes the stairs (30 s < 42 s lift), accessible the lift
        self.assertEqual(R.plan('lift_stairs', 'lift_stairs_4F', 'standard').connectors[0]['kind'], 'stairs')
        self.assertEqual(R.plan('lift_stairs', 'lift_stairs_4F', 'accessible').connectors[0]['kind'], 'lift')
        s = R.plan('lift_stairs', 'lift_stairs_4F', 'standard').instructions
        self.assertTrue(any('stairs' in t and 'lift is next to them' in t for t in s))
        # canteen -> LT1a: standard rides the escalator, accessible takes the lift (a different connector)
        st, ac = R.plan('canteen', 'lt1a', 'standard'), R.plan('canteen', 'lt1a', 'accessible')
        self.assertEqual([c['kind'] for c in st.connectors], ['escalator'])
        self.assertEqual([c['kind'] for c in ac.connectors], ['lift'])
        self.assertGreater(ac.seconds, st.seconds)

    def test_standard_same_cost_as_research_graph(self):
        # lift edges are dearer than the stairs at the same landing, so the standard planner keeps every cost
        g0, g1 = R.graph(), R.graph('standard')
        for a in g0.nodes:
            for b in g0.nodes:
                if a != b:
                    self.assertAlmostEqual(g0.search(a, b)[1], g1.search(a, b)[1], places=9)
                    self.assertAlmostEqual(g1.search(a, b, True)[1], g1.search(a, b, False)[1], places=9)
        g2 = R.graph('accessible')
        for a in g2.nodes:                         # A* = Dijkstra in accessible mode too
            for b in g2.nodes:
                if a != b:
                    self.assertAlmostEqual(g2.search(a, b, True)[1], g2.search(a, b, False)[1], places=9)

    def test_plan_totals(self):
        p = R.plan('canteen', 'lt1a', 'standard')
        self.assertAlmostEqual(p.metres, round(sum(e['metres'] for e in p.legs), 1))
        self.assertAlmostEqual(p.seconds, round(sum(e['seconds'] for e in p.legs), 1))
        with self.assertRaises(KeyError):
            R.plan('canteen', 'lt1a', 'wheelchair')

    def test_toilet_table_matches_graph(self):
        g = R.graph()
        self.assertEqual(set(R.TOILETS), {n for n, d in g.nodes.items() if d['kind'] == 'toilet'})
        self.assertEqual(g.nodes['disabled_toilet']['name'], 'Male disabled toilet (5F)')
        self.assertEqual(g.nodes['disabled_toilet_4F']['name'], 'Mixed disabled toilet (4F)')

    def test_toilet_every_mode_and_gender(self):
        starts = ['canteen', 'y5202', 'y5401', 'exit_10', 'lt1a', 'y4502', 'lt2b', 'entrance_exit']   # 4 on 5F, 4 on 4F
        allowed = {('standard', 'any'): set(R.TOILETS),
                   ('standard', 'male'): {'male_toilet', 'disabled_toilet', 'disabled_toilet_4F'},
                   ('standard', 'female'): {'female_toilet', 'disabled_toilet_4F'},
                   ('accessible', 'any'): {'disabled_toilet', 'disabled_toilet_4F'},
                   ('accessible', 'male'): {'disabled_toilet', 'disabled_toilet_4F'},
                   ('accessible', 'female'): {'disabled_toilet_4F'}}
        for s in starts:
            for (mode, gender), ok in allowed.items():
                t = R.nearest_toilet(s, mode, gender)
                self.assertEqual({o['id'] for o in t['options']}, ok, (s, mode, gender))
                # the choice is the cheapest allowed toilet by an independent Dijkstra in that mode
                best = min(ok, key=lambda x: (R.graph(mode).search(s, x, False)[1], x))
                self.assertEqual(t['toilet'], best, (s, mode, gender))
                self.assertEqual(t['choice'].path[-1], best)
                if mode == 'accessible':
                    self.assertFalse({e['kind'] for e in t['choice'].legs} & {'stairs', 'escalator'})
        # spot checks (5F female, accessible female from 5F has to go down by lift, 4F anyone -> the mixed toilet)
        self.assertEqual(R.nearest_toilet('y5202', 'standard', 'female')['toilet'], 'female_toilet')
        t = R.nearest_toilet('y5401', 'accessible', 'female')
        self.assertEqual((t['toilet'], [c['kind'] for c in t['choice'].connectors]), ('disabled_toilet_4F', ['lift']))
        self.assertEqual(R.nearest_toilet('lt1a', 'standard', 'male')['toilet'], 'disabled_toilet_4F')

    def test_toilet_no_option(self):
        t = R.nearest_toilet('canteen', 'accessible', 'female', floor=5)     # the only 5F disabled toilet is male only
        self.assertIsNone(t['choice'])
        self.assertIsNone(t['toilet'])
        self.assertIn('No disabled female toilet on 5F', t['message'])
        self.assertEqual({x['id']: x['reason'] for x in t['excluded']}['disabled_toilet'], 'male only')
        only_male = {'male_toilet': R.TOILETS['male_toilet']}
        t = R.nearest_toilet('lt1a', 'standard', 'female', toilets=only_male)
        self.assertIsNone(t['choice'])
        self.assertIn('No female toilet', t['message'])
        with self.assertRaises(KeyError):
            R.nearest_toilet('lt1a', 'standard', 'other')


if __name__ == '__main__':
    unittest.main()
