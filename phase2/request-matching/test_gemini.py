"""Gemini backend tests with a fake HTTP layer (no real API call, no key needed). Standard library only.
Run inside this folder: python -m unittest test_gemini"""
import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import evaluate as E
import gemini
import match as M

FAKE_KEY = 'test-key-not-real-0000'


def reply(text, status=200):
    body = json.dumps({'candidates': [{'content': {'parts': [{'text': text}], 'role': 'model'}, 'finishReason': 'STOP'}],
                       'modelVersion': 'fake-model-001'}).encode()

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    return R(body)


def http_error(code, message):
    return urllib.error.HTTPError('https://x', code, 'err', {}, io.BytesIO(json.dumps({'error': {'message': message}}).encode()))


class FakeAPI:
    """Stands in for urllib.request.urlopen; records requests; each call pops the next action."""

    def __init__(self, *actions):
        self.actions, self.requests = list(actions), []

    def __call__(self, req, timeout=None):
        self.requests.append((req, timeout))
        a = self.actions.pop(0)
        if isinstance(a, BaseException):
            raise a
        return reply(a)


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'GEMINI_API_KEY': FAKE_KEY, 'GEMINI_MODEL': 'fake-model'})
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        cache = Path(self.tmp.name) / 'cache.json'
        self.cachep = mock.patch.object(M, 'gemini_cache_path', lambda version=None: cache)
        self.cachep.start()
        self.no_net = mock.patch.object(gemini, 'URLOPEN', FakeAPI())     # any unexpected call fails (empty action list)
        self.no_net.start()
        M.GEMINI_CALLS = 0
        self.places = M.load_places()

    def tearDown(self):
        for p in (self.no_net, self.cachep, self.env):
            p.stop()
        self.tmp.cleanup()

    def api(self, *actions):
        f = FakeAPI(*actions)
        p = mock.patch.object(gemini, 'URLOPEN', f)
        p.start()
        self.addCleanup(p.stop)
        return f


class TestEnv(unittest.TestCase):
    def test_env_file_and_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.env'
            p.write_text('# comment\nexport A_TEST_X="quoted value"\nB_TEST_X=plain # note\nC_TEST_X=from file\n\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {'C_TEST_X': 'from real env'}):
                vals = gemini.load_env(p, force=True)
                self.assertEqual(vals['A_TEST_X'], 'quoted value')
                self.assertEqual(os.environ['B_TEST_X'], 'plain')
                self.assertEqual(os.environ['C_TEST_X'], 'from real env')    # real environment wins
                for k in ('A_TEST_X', 'B_TEST_X'):
                    os.environ.pop(k, None)

    def test_example_has_no_key(self):
        ex = (gemini.REPO / '.env.example').read_text(encoding='utf-8')
        line = next(l for l in ex.splitlines() if l.startswith('GEMINI_API_KEY='))
        self.assertEqual(line, 'GEMINI_API_KEY=')


class TestGenerate(Base):
    def test_request_shape_key_in_header_only(self):
        f = self.api('OK')
        text, info = gemini.generate('sys', 'hello', json_mode=True)
        self.assertEqual(text, 'OK')
        self.assertEqual(info['model_version'], 'fake-model-001')
        req, timeout = f.requests[0]
        self.assertNotIn(FAKE_KEY, req.full_url)
        self.assertEqual(req.get_header('X-goog-api-key'), FAKE_KEY)
        self.assertIn('/v1beta/models/fake-model:generateContent', req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
        self.assertEqual(body['systemInstruction']['parts'][0]['text'], 'sys')
        self.assertEqual(timeout, gemini.DEFAULT_TIMEOUT_S)

    def test_errors_are_plain_english(self):
        cases = [(http_error(400, 'API key not valid. Please pass a valid API key.'), 'bad_key'),
                 (http_error(403, 'Permission denied'), 'bad_key'), (http_error(429, 'Resource exhausted'), 'quota'),
                 (http_error(404, 'models/x is not found'), 'bad_model'), (http_error(500, 'internal'), 'server'),
                 (http_error(400, 'Invalid JSON payload'), 'bad_request'), (socket.timeout('timed out'), 'timeout'),
                 (urllib.error.URLError(socket.timeout('timed out')), 'timeout'),
                 (urllib.error.URLError(socket.gaierror(-3, 'Temporary failure in name resolution')), 'network')]
        for exc, kind in cases:
            self.api(exc)
            with self.assertRaises(gemini.GeminiError) as cm:
                gemini.generate('', 'x')
            self.assertEqual(cm.exception.kind, kind, exc)
            self.assertNotIn(FAKE_KEY, str(cm.exception))

    def test_no_key(self):
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with self.assertRaises(gemini.GeminiError) as cm:
                gemini.generate('', 'x')
        self.assertEqual(cm.exception.kind, 'no_key')

    def test_empty_or_blocked_reply(self):
        self.api('   ')
        with self.assertRaises(gemini.GeminiError) as cm:
            gemini.generate('', 'x')
        self.assertEqual(cm.exception.kind, 'bad_reply')


class TestMatchBackend(Base):
    def test_gemini_same_prompt_and_cache(self):
        f = self.api('y5401')
        self.assertEqual(M.match('room y5 401 please', 'gemini'), ('y5401', 1.0))
        body = json.loads(f.requests[0][0].data)
        self.assertEqual(body['systemInstruction']['parts'][0]['text'], M.LLM_SYSTEM)
        self.assertEqual(body['contents'][0]['parts'][0]['text'], M.llm_prompt('room y5 401 please', self.places))
        self.assertEqual(M.match('room y5 401 please', 'gemini'), ('y5401', 1.0))   # second time: cache, no call
        self.assertEqual(M.GEMINI_CALLS, 1)

    def test_none_and_garbage(self):
        self.api('NONE', 'I think it is the canteen!')
        self.assertEqual(M.gemini_match('chemistry lab', self.places), (None, 0.0))
        self.assertEqual(M.gemini_match('blah', self.places), (None, 0.0))
        self.assertFalse(M.gemini_answer('blah', self.places, allow_call=False)['valid'])

    def test_errors_not_cached(self):
        self.api(http_error(429, 'quota'))
        with self.assertRaises(gemini.GeminiError):
            M.gemini_answer('xyz', self.places)
        self.assertIsNone(M.gemini_answer('xyz', self.places, allow_call=False))

    def test_hybrid_gemini_keyword_first(self):
        self.assertEqual(M.hybrid_gemini_match('canteen', self.places)[2], 'keyword')     # no call (fake would fail)
        self.api('sr9')
        pid, _, stage, _ = M.hybrid_gemini_match('a calm spot for homework', self.places, allow_call=True)
        self.assertEqual((pid, stage), ('sr9', 'llm'))

    def test_eval_cap_and_stop(self):
        qs = E.load_queries()[:6]
        self.api(*(['NONE'] * 3))
        rows, stop = E.run_gemini('gemini', qs, self.places, True, max_calls=3)
        self.assertEqual(M.GEMINI_CALLS, 3)
        self.assertEqual(sum(1 for r in rows if r.get('missing')), 3)
        self.assertIn('--max-calls 3', stop)
        M.GEMINI_CALLS = 0
        self.api(http_error(403, 'denied'))
        rows, stop = E.run_gemini('gemini', qs[3:], self.places, True, max_calls=150)
        self.assertEqual(M.GEMINI_CALLS, 1)                     # stopped after the first error
        self.assertIn('rejected', stop)

    def test_pacing_and_resume_after_429(self):
        qs = E.load_queries()[:6]
        self.api('NONE', 'NONE', http_error(429, 'rate limit'))
        with mock.patch.object(E.time, 'sleep') as sl:
            rows, stop = E.run_gemini('gemini', qs, self.places, True, 150, sleep_s=4.5)
        self.assertEqual(M.GEMINI_CALLS, 3)                      # stopped at the 429, no retry
        self.assertIn('429', stop)
        self.assertEqual(sum(1 for r in rows if r.get('missing')), 4)
        self.assertEqual(sl.call_count, 2)                       # gap before call 2 and 3 only (not before the first)
        for c in sl.call_args_list:
            self.assertGreater(c[0][0], 4.0)
            self.assertLessEqual(c[0][0], 4.5)
        M.GEMINI_CALLS = 0                                       # rerun: the two good answers come from the cache
        self.api('NONE', 'NONE', 'NONE', 'NONE')
        with mock.patch.object(E.time, 'sleep') as sl:
            rows, stop = E.run_gemini('gemini', qs, self.places, True, 150, sleep_s=4.5)
        self.assertEqual(M.GEMINI_CALLS, 4)                      # only the 4 missing queries are called
        self.assertIsNone(stop)
        self.assertFalse(any(r.get('missing') for r in rows))
        self.assertEqual(sl.call_count, 3)                       # cached rows are never delayed
        M.GEMINI_CALLS = 0
        with mock.patch.object(E.time, 'sleep') as sl:           # everything cached: no call, no sleep
            E.run_gemini('gemini', qs, self.places, True, 150, sleep_s=4.5)
        self.assertEqual((M.GEMINI_CALLS, sl.call_count), (0, 0))

    def test_default_no_sleep(self):
        qs = E.load_queries()[:3]
        self.api('NONE', 'NONE', 'NONE')
        with mock.patch.object(E.time, 'sleep') as sl:
            E.run_gemini('gemini', qs, self.places, True, 150)
        self.assertEqual(sl.call_count, 0)

    def test_eval_no_key_exits_cleanly(self):
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': ''}), mock.patch('builtins.print') as p:
            E.gemini_eval('hybrid_gemini', E.load_queries(), self.places, {d['place_id']: d for d in self.places}, True, 150)
        self.assertIn('No Gemini API key', p.call_args[0][0])


class TestAskParse(unittest.TestCase):
    ids = {'sr9', 'canteen'}

    def test_parse(self):
        self.assertEqual(M.parse_ask('{"place_id": "sr9", "answer": "Study rooms on 5F."}', self.ids), ('sr9', 'Study rooms on 5F.'))
        self.assertEqual(M.parse_ask('```json\n{"place_id": "NONE", "answer": "Not covered."}\n```', self.ids), (None, 'Not covered.'))
        for bad in ('sr9', '{"place_id": "chem_lab", "answer": "x"}', '[1]', ''):
            with self.assertRaises(ValueError):
                M.parse_ask(bad, self.ids)

    def test_parse_route_v2(self):
        """Entry 93: the app's v2 reply {"from_id", "place_id"}; no sentence needed; from_id optional."""
        p = M.parse_ask_route
        self.assertEqual(p('{"from_id": "canteen", "place_id": "sr9"}', self.ids), ('canteen', 'sr9', ''))
        self.assertEqual(p('{"from_id": "NONE", "place_id": "sr9"}', self.ids), (None, 'sr9', ''))
        self.assertEqual(p('{"place_id": "sr9"}', self.ids), (None, 'sr9', ''))
        self.assertEqual(p('{"from_id": null, "place_id": "NONE"}', self.ids), (None, None, ''))
        self.assertEqual(p('```json\n{"from_id": "sr9", "place_id": "NONE"}\n```', self.ids), ('sr9', None, ''))
        for bad in ('{"from_id": "chem_lab", "place_id": "sr9"}', '{"from_id": "sr9"}', '{"place_id": ""}'):
            with self.assertRaises(ValueError):
                p(bad, self.ids)
        self.assertIn('from_id', M.ask_prompt('x', [{'place_id': 'sr9', 'name': 'SR9', 'floor': '5', 'tag_set': set(),
                                                     'alias_list': []}]))
        self.assertEqual(M.ASK_PROMPT_VERSION, 'v2')


if __name__ == '__main__':
    unittest.main()
