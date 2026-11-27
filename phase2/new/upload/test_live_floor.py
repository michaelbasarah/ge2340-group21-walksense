"""Live floor from the barometer (PROCESS-LOG 95), on synthetic streams shaped like Dicta's iPhone 18 in live mode:
100 Hz acc/mag, pressure at ~1 Hz that reaches the laptop ~3.2 s after the acc samples of the same time.
No place models are trained (a stub model), so this runs in about a second.
Run: python -m unittest test_live_floor.py"""
import unittest

import numpy as np

import live
import walksense as ws

HZ, P5, FLOOR_HPA = 100, 1014.9, 0.7      # one floor down on 27 Nov: 1014.89 -> 1015.61 hPa (advisor's reading)


class StubModel:
    places = {5: ['a', 'b', 'c'], 4: ['d', 'e']}

    def top3(self, win, floor, trim=0.0):
        return [('a' if floor == 5 else 'd', 1.0), ('b' if floor == 5 else 'e', 0.0), ('c', 0.0)]

    def vote_floor(self, win, trim=0.0):
        return None


def stream(segments, rng=np.random.default_rng(0)):
    """segments: (kind, seconds, p_start, p_end); kind = 'still' or 'walk'. Returns {sensor: array}."""
    acc, mag, baro, t0 = [], [], [], 0.0
    for kind, secs, p0, p1 in segments:
        t = t0 + np.arange(0, secs, 1 / HZ)
        g = np.tile([0.0, 0.0, 9.81], (len(t), 1)) + rng.normal(0, 0.03, (len(t), 3))
        if kind == 'walk':
            g[:, 2] += 2.0 * np.sin(2 * np.pi * 2.0 * (t - t0))
        acc.append(np.column_stack([t, g]))
        mag.append(np.column_stack([t, np.tile([-33.7, -16.4, -9.1], (len(t), 1)) + rng.normal(0, 0.3, (len(t), 3))]))
        tb = t0 + np.arange(0.3, secs, 1.067)
        baro.append(np.column_stack([tb, p0 + (p1 - p0) * (tb - t0) / secs + rng.normal(0, 0.01, len(tb))]))
        t0 += secs
    return {'acc': np.vstack(acc), 'gyr': np.vstack(acc), 'mag': np.vstack(mag), 'baro': np.vstack(baro)}


def run(segments, floor=5, lag=3.2, device='iPhone19,2'):
    tr = live.LiveTracker({device: StubModel()}, device, floor, graph={})
    s = stream(segments)
    changes, prev = [], floor
    end = max(a[-1, 0] for a in s.values())
    for t in np.arange(0, end + 1 + lag, live.POLL_S):
        chunk = {}
        for k, a in s.items():
            d = lag if k == 'baro' else 0.0
            i, j = np.searchsorted(a[:, 0], [t - live.POLL_S - d, t - d], side='right')
            if j > i:
                chunk[k] = a[i:j]
        tr.add(chunk)
        st = tr.update()
        if st['floor'] != prev:
            changes.append((float(t), st['floor'], st['floor_note']))
            prev = st['floor']
    return tr, changes


class LiveFloorTest(unittest.TestCase):
    def test_stop_reads_its_pressure_despite_the_lag(self):
        tr, _ = run([('walk', 10, P5, P5), ('still', 12, P5, P5), ('walk', 6, P5, P5)])
        notes = [s['floor_note'] for s in tr.state['stops']]
        self.assertTrue(notes, 'no stop found')
        self.assertFalse(any('no barometer' in (n or '') for n in notes), notes)   # the bug of 27 Nov
        self.assertGreater(len(tr.session.recent), 0)                              # the stop set the floor reference

    def test_escalator_ride_down_walking(self):
        ride_end = 10 + 12 + 6 + 15
        tr, ch = run([('walk', 10, P5, P5), ('still', 12, P5, P5), ('walk', 6, P5, P5),
                      ('walk', 15, P5, P5 + FLOOR_HPA), ('walk', 10, P5 + FLOOR_HPA, P5 + FLOOR_HPA)])
        self.assertEqual(tr.session.floor, 4, ch)
        t, floor, note = ch[0]
        self.assertEqual(floor, 4); self.assertIn('pressure rose', note)
        self.assertLess(t - ride_end, 5.0, ch)       # within a few seconds of the ride's end (here: during the ride)

    def test_standing_ride_down_then_up(self):
        """Standing still on the escalator / in the lift: the tracker calls it a stop, the floor must still switch."""
        down_end = 10 + 12 + 15
        tr, ch = run([('walk', 10, P5, P5), ('still', 12, P5, P5), ('still', 15, P5, P5 + FLOOR_HPA),
                      ('still', 10, P5 + FLOOR_HPA, P5 + FLOOR_HPA), ('walk', 8, P5 + FLOOR_HPA, P5 + FLOOR_HPA),
                      ('still', 12, P5 + FLOOR_HPA, P5 + FLOOR_HPA), ('still', 15, P5 + FLOOR_HPA, P5),
                      ('still', 10, P5, P5)])
        self.assertEqual([f for _, f, _ in ch], [4, 5], ch)
        self.assertLess(ch[0][0] - down_end, 5.0, ch)
        self.assertLess(ch[1][0] - (down_end + 10 + 8 + 12 + 15), 5.0, ch)

    def test_weather_drift_does_not_switch(self):
        tr, ch = run([('walk', 10, P5, P5)] + [('still', 12, P5 + 0.03 * i, P5 + 0.03 * i) if i % 2 else
                                                ('walk', 10, P5 + 0.03 * i, P5 + 0.03 * (i + 1)) for i in range(1, 16)])
        self.assertEqual(ch, [])                       # 0.45 hPa over ~3 min, a little at every stop: the reference follows

    def test_no_zero_probability_fillers(self):
        tr, _ = run([('walk', 10, P5, P5), ('still', 12, P5, P5)])
        self.assertEqual(tr.state['top3'], [('a', 1.0)])

    def test_manual_floor_keeps_the_pressure_watch(self):
        tr, _ = run([('walk', 10, P5, P5), ('still', 12, P5, P5)])
        tr.set_floor(4)                                # "I'm on 4F" (wrong on purpose): pressure now = 4F reference
        self.assertEqual(len(tr.session.recent), 1)
        self.assertEqual(tr.state['floor'], 4)

    def test_phone_without_barometer(self):
        tr = live.LiveTracker({'SM-A566B': StubModel()}, 'SM-A566B', 5, graph={})
        s = stream([('walk', 10, P5, P5), ('still', 12, P5, P5)])
        del s['baro']
        for t in np.arange(0, 23, live.POLL_S):
            tr.add({k: a[(a[:, 0] > t - live.POLL_S) & (a[:, 0] <= t)] for k, a in s.items()
                    if ((a[:, 0] > t - live.POLL_S) & (a[:, 0] <= t)).any()})
            tr.update()
        self.assertIn('no barometer data', tr.state['stops'][-1]['floor_note'])

    def test_uses_the_model_the_phone_reports(self):
        class Phone:
            bufs, last = {}, {}

            def discover(self):
                self.bufs = {'acc': 1, 'mag': 1}
                return {}

            def device_model(self):
                return 'iPhone19,2'

            def fetch(self):
                raise KeyboardInterrupt                 # stop the loop after the device check

        tr = live.LiveTracker({'iPhone17,4': StubModel(), 'iPhone19,2': StubModel()}, 'iPhone17,4', 5, graph={})
        status = {}
        with self.assertRaises(KeyboardInterrupt):
            live.run(Phone(), tr, status, type('E', (), {'is_set': lambda s: False, 'wait': lambda s, t: None})())
        self.assertEqual(tr.device, 'iPhone19,2')
        self.assertIn('iPhone19,2', status['device_note'])
        self.assertEqual(tr.session.rule, ws.floor_rule_for('iPhone19,2'))


if __name__ == '__main__':
    unittest.main()
