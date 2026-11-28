#!/usr/bin/env python3
"""One-shot Gemini check: reads the repo-root .env, makes ONE tiny API call, prints OK + the model, or what is wrong.

    python phase2/v2/upload/check_gemini.py      (from the repo root, or python check_gemini.py in this folder)

Exit code 0 = OK, 1 = not working (the app still searches offline with keyword + fuzzy).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'request-matching'))
import gemini  # noqa: E402


def main():
    key, model = gemini.settings()
    if not key:
        print(f'NOT SET: there is no Gemini API key yet.\n'
              f'  1. Get a key at https://aistudio.google.com/apikey\n'
              f'  2. Paste it after GEMINI_API_KEY= in {gemini.ENV_FILE}\n'
              f'     (no file there? copy .env.example to .env first)\n'
              f'  3. Run this check again.')
        return 1
    print(f'Key found ({len(key)} characters, not shown). Asking {model} one tiny question ...')
    try:
        text, info = gemini.generate('', 'Reply with the single word OK.')
    except gemini.GeminiError as e:
        print(f'NOT WORKING ({e.kind}): {e}')
        return 1
    print(f"OK: Gemini answered in {info['latency_s']} s. Model: {info['model_version'] or model}. Reply: {text.strip()[:40]!r}")
    print('Restart server.py (if it is running) so search uses Gemini.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
