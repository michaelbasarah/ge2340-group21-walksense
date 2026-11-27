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
        """Standard: ordinary toilets only (disabled ones stay free); Step-free: disabled toilets only (entry 90)."""
        starts = ['canteen', 'y5202', 'y5401', 'exit_10', 'lt1a', 'y4502', 'lt2b', 'entrance_exit']   # 4 on 5F, 4 on 4F
        allowed = {('standard', 'any'): {'male_toilet', 'female_toilet'},
                   ('standard', 'male'): {'male_toilet'},
                   ('standard', 'female'): {'female_toilet'},
                   ('accessible', 'any'): {'disabled_toilet', 'disabled_toilet_4F'},
                   ('accessible', 'male'): {'disabled_toilet', 'disabled_toilet_4F'},
                   ('accessible', 'female'): {'disabled_toilet_4F'}}
        for s in starts:
            for (mode, gender), ok in allowed.items():
                t = R.nearest_toilet(s, mode, gender)
                self.assertEqual({o['id'] for o in t['options']}, ok, (s, mode, gender))
                self.assertEqual(t['policy'], 'ordinary' if mode == 'standard' else 'disabled_only', (s, mode, gender))
                # the choice is the cheapest allowed toilet by an independent Dijkstra in that mode
                best = min(ok, key=lambda x: (R.graph(mode).search(s, x, False)[1], x))
                self.assertEqual(t['toilet'], best, (s, mode, gender))
                self.assertEqual(t['choice'].path[-1], best)
                if mode == 'accessible':
                    self.assertFalse({e['kind'] for e in t['choice'].legs} & {'stairs', 'escalator'})
                else:                                   # every disabled toilet that fits the gender is listed as kept free
                    kept = {x['id'] for x in t['excluded'] if x['reason'].startswith('disabled toilet, kept free')}
                    self.assertEqual(kept, {k for k, v in R.TOILETS.items() if v['accessible'] and not R.toilet_allowed(k, mode, gender)})
                    self.assertIn('disabled toilets stay free', t['policy_note'])
                # "disabled" / "accessible" words in Standard = accessible_only: same answer as Step-free toilets
                a = R.nearest_toilet(s, mode, gender, accessible_only=True)
                self.assertTrue(all(R.TOILETS[o['id']]['accessible'] for o in a['options']), (s, mode, gender))
                self.assertEqual(a['policy'], 'disabled_only')
        # spot checks (5F female, accessible female from 5F has to go down by lift)
        self.assertEqual(R.nearest_toilet('y5202', 'standard', 'female')['toilet'], 'female_toilet')
        t = R.nearest_toilet('y5401', 'accessible', 'female')
        self.assertEqual((t['toilet'], [c['kind'] for c in t['choice'].connectors]), ('disabled_toilet_4F', ['lift']))
        # 4F start, Standard: up to the 5F ordinary toilet, not the nearer 4F mixed disabled toilet
        t = R.nearest_toilet('lt1a', 'standard', 'male')
        self.assertEqual(t['toilet'], 'male_toilet')
        self.assertEqual(R.graph('standard').nodes[t['toilet']]['floor'], 5)
        self.assertLess(R.graph('standard').search('lt1a', 'disabled_toilet_4F', False)[1], t['choice'].seconds)
        self.assertEqual(R.nearest_toilet('canteen', 'standard', 'male')['toilet'], 'male_toilet')

    def test_toilet_floor_filter_fallback(self):
        """Every start x mode x gender with a 5F / 4F filter: Standard falls back to a disabled toilet only on 4F."""
        starts = ['canteen', 'y5202', 'y5401', 'exit_10', 'lt1a', 'y4502', 'lt2b', 'entrance_exit']
        want = {('standard', 'any', 5): ({'male_toilet', 'female_toilet'}, 'ordinary'),
                ('standard', 'male', 5): ({'male_toilet'}, 'ordinary'),
                ('standard', 'female', 5): ({'female_toilet'}, 'ordinary'),
                ('standard', 'any', 4): ({'disabled_toilet_4F'}, 'disabled_fallback'),
                ('standard', 'male', 4): ({'disabled_toilet_4F'}, 'disabled_fallback'),
                ('standard', 'female', 4): ({'disabled_toilet_4F'}, 'disabled_fallback'),
                ('accessible', 'any', 5): ({'disabled_toilet'}, 'disabled_only'),
                ('accessible', 'male', 5): ({'disabled_toilet'}, 'disabled_only'),
                ('accessible', 'female', 5): (set(), 'disabled_only'),
                ('accessible', 'any', 4): ({'disabled_toilet_4F'}, 'disabled_only'),
                ('accessible', 'male', 4): ({'disabled_toilet_4F'}, 'disabled_only'),
                ('accessible', 'female', 4): ({'disabled_toilet_4F'}, 'disabled_only')}
        for s in starts:
            for (mode, gender, floor), (ok, policy) in want.items():
                t = R.nearest_toilet(s, mode, gender, floor=floor)
                self.assertEqual(({o['id'] for o in t['options']}, t['policy']), (ok, policy), (s, mode, gender, floor))
                if policy == 'disabled_fallback':
                    self.assertIn('No ordinary', t['policy_note'])
                    self.assertIn('on 4F', t['policy_note'])
        # a gender no ordinary toilet fits (made-up table): Standard falls back to the fitting disabled toilet
        no_male = {k: v for k, v in R.TOILETS.items() if k != 'male_toilet'}
        t = R.nearest_toilet('canteen', 'standard', 'male', toilets=no_male)
        self.assertEqual((t['policy'], R.TOILETS[t['toilet']]['accessible']), ('disabled_fallback', True))
        self.assertIn(t['toilet'], {'disabled_toilet', 'disabled_toilet_4F'})

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


class ExitTests(unittest.TestCase):
    """Entry 93: nearest exit by route; emergency = destinations.csv tag; floor filter."""
    def test_exit_table_matches_graph_and_tags(self):
        import csv
        from pathlib import Path
        g = R.graph()
        self.assertEqual(set(R.EXITS), {n for n in g.nodes if g.nodes[n]['kind'] == 'exit'})
        dest = {d['place_id']: d for d in csv.DictReader((Path(R.HERE).parents[1] / 'request-matching' / 'destinations.csv').open(encoding='utf-8'))}
        for eid, e in R.EXITS.items():
            self.assertEqual(e['emergency'], 'emergency' in dest[eid]['tags'].split(';'), eid)

    def test_nearest_exit_every_start(self):
        g = R.graph()
        for st in g.nodes:
            for mode in R.PROFILES:
                for em in (False, True):
                    for fl in (None, 5, 4):
                        t = R.nearest_exit(st, mode, em, fl)
                        ok = [e for e in R.EXITS if (not em or R.EXITS[e]['emergency']) and (fl is None or g.nodes[e]['floor'] == fl)]
                        best = min(ok, key=lambda e: (R.plan(st, e, mode).seconds, R.plan(st, e, mode).metres, e))
                        self.assertEqual(t['exit'], best, (st, mode, em, fl))
                        self.assertEqual(len(t['options']) + len(t['excluded']), len(R.EXITS))
        t = R.nearest_exit('y5202', 'standard')
        self.assertEqual((t['exit'], t['choice'].metres), ('exit_10', 15.1))
        # entry 94 (user decision 27 Nov): every exit is an emergency exit, so emergency = the same answer as the plain nearest exit
        self.assertTrue(all(e['emergency'] for e in R.EXITS.values()))
        te = R.nearest_exit('y5202', 'standard', emergency=True)
        self.assertEqual((te['exit'], te['choice'].metres, te['excluded']), ('exit_10', 15.1, []))
        self.assertEqual(len(te['options']), len(R.EXITS))
        # a table with no emergency exit still gives no answer (the filter itself is kept)
        self.assertIsNone(R.nearest_exit('y5202', 'standard', emergency=True, exits={'exit_10': {'emergency': False}})['exit'])
        with self.assertRaises(KeyError):
            R.nearest_exit('lt1a', 'fly')


if __name__ == '__main__':
    unittest.main()
