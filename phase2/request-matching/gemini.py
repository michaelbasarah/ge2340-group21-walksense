"""Gemini API client for WalkSense (standard library only, no SDK) and the one .env loader of the repo.

    import gemini
    key, model = gemini.settings()          # reads <repo>/.env once; real environment variables win
    text, info = gemini.generate(system, prompt, json_mode=True)   # raises gemini.GeminiError

The key lives only in the repo-root `.env` (gitignored) or in the environment, is sent in the `x-goog-api-key`
header (never in the URL) and is never printed, logged or returned to a browser.

Endpoint and models checked on 26 Nov 2026 (aistudio.google.com/docs/models, /api-reference/generate-content,
/docs/pricing): POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent.
Default model gemini-3.5-flash-lite (stable, "fastest and most cost-effective" 3.5 model, free tier listed);
gemini-3.1-flash-lite is the other stable flash-lite. gemini-2.5-flash is deprecated (re-routed after 1 Dec 2026).
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / '.env'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
DEFAULT_TIMEOUT_S = 8.0
URLOPEN = urllib.request.urlopen       # tests replace this; nothing else should
_LOADED = {}


def load_env(path=None, force=False):
    """KEY=VALUE lines of the .env file into os.environ (comments, blank lines, `export ` and quotes allowed).
    A variable already set in the real environment is NOT overwritten. Returns the values read from the file."""
    path = Path(path or ENV_FILE)
    if str(path) in _LOADED and not force:
        return _LOADED[str(path)]
    vals = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            if k.startswith('export '):
                k = k[7:].strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            elif ' #' in v:
                v = v.split(' #', 1)[0].rstrip()
            vals[k] = v
            if k not in os.environ:
                os.environ[k] = v
    _LOADED[str(path)] = vals
    return vals


def settings():
    """(api_key or '', model). Loads the repo .env first."""
    load_env()
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    model = os.environ.get('GEMINI_MODEL', '').strip() or DEFAULT_MODEL
    return key, model


def timeout_s():
    load_env()
    try:
        return float(os.environ.get('GEMINI_TIMEOUT_S', '') or DEFAULT_TIMEOUT_S)
    except ValueError:
        return DEFAULT_TIMEOUT_S


class GeminiError(Exception):
    """kind: no_key, bad_key, bad_model, quota, network, timeout, server, bad_request, bad_reply. str() = plain English."""

    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind, self.status = kind, status


def _google_message(body):
    try:
        return json.loads(body).get('error', {}).get('message', '')[:200]
    except (ValueError, AttributeError):
        return ''


def _http_error(code, body):
    msg = _google_message(body)
    low = msg.lower()
    if code in (401, 403) or (code == 400 and ('api key' in low or 'api_key' in low)):
        return GeminiError('bad_key', 'The Gemini API key was rejected (invalid, restricted or not enabled for the '
                           'Gemini API). Make a new key at aistudio.google.com/apikey and paste it into .env. '
                           f'Google said: {msg or code}', code)
    if code == 429:
        return GeminiError('quota', 'Gemini quota or rate limit reached (HTTP 429). Wait a minute, or check the '
                           f'limits of this key in AI Studio. Google said: {msg or code}', code)
    if code == 404:
        return GeminiError('bad_model', 'Gemini does not know this model name (HTTP 404). Check GEMINI_MODEL in '
                           f'.env (the default is {DEFAULT_MODEL}). Google said: {msg or code}', code)
    if code >= 500:
        return GeminiError('server', f'Gemini server error (HTTP {code}); try again later. {msg}', code)
    return GeminiError('bad_request', f'Gemini refused the request (HTTP {code}). Google said: {msg or code}', code)


def generate(system, prompt, json_mode=False, key=None, model=None, timeout=None):
    """One generateContent call. Returns (text, info) with info = {model, model_version, latency_s, finish_reason}.
    Raises GeminiError for a missing key, HTTP errors, no internet, a timeout or an empty/blocked reply."""
    k, m = settings()
    key, model = key or k, model or m
    if not key:
        raise GeminiError('no_key', f'No Gemini API key: paste it after GEMINI_API_KEY= in {ENV_FILE} '
                          '(get one at aistudio.google.com/apikey).')
    body: dict = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}]}
    if system:
        body['systemInstruction'] = {'parts': [{'text': system}]}
    if json_mode:
        body['generationConfig'] = {'responseMimeType': 'application/json'}
    req = urllib.request.Request(ENDPOINT.format(model=model), data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    t0 = time.perf_counter()
    try:
        with URLOPEN(req, timeout=timeout or timeout_s()) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read()
        except Exception:
            err_body = b''
        raise _http_error(e.code, err_body) from None
    except (socket.timeout, TimeoutError):
        raise GeminiError('timeout', f'Gemini did not answer within {timeout or timeout_s():.0f} s.') from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise GeminiError('timeout', f'Gemini did not answer within {timeout or timeout_s():.0f} s.') from None
        raise GeminiError('network', 'Cannot reach Gemini (no internet on this network?). '
                          f'Detail: {e.reason}') from None
    except OSError as e:
        raise GeminiError('network', f'Cannot reach Gemini (no internet on this network?). Detail: {e}') from None
    latency = time.perf_counter() - t0
    try:
        j = json.loads(raw)
    except ValueError:
        raise GeminiError('bad_reply', 'Gemini sent something that is not JSON.') from None
    cands = j.get('candidates') or []
    if not cands:
        reason = (j.get('promptFeedback') or {}).get('blockReason', 'no candidates')
        raise GeminiError('bad_reply', f'Gemini returned no answer ({reason}).')
    parts = (cands[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    info = {'model': model, 'model_version': j.get('modelVersion'), 'latency_s': round(latency, 3),
            'finish_reason': cands[0].get('finishReason')}
    if not text.strip():
        raise GeminiError('bad_reply', f"Gemini returned an empty answer (finish reason {info['finish_reason']}).")
    return text, info
