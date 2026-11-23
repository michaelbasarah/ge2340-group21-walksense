# WalkSense prototype (simple product)

A local web app that demonstrates the pipeline before the real UI is built.

## Run it
```bash
cd WalkSense-Work/prototype
python server.py
```
Then open **http://127.0.0.1:5173** in your browser. (Ctrl+C in the terminal to stop.)

Needs: `pandas numpy scikit-learn model2vec` (all already installed on this laptop).
First run downloads a ~30 MB embedding model once, then works offline.

## What's inside
1. **Where do you want to go?** — type a request; see the **keyword** method and the
   **embedding** method each pick a place. Try "i want noodles" (keyword misses, embedding
   gets Canteen) to see the difference. (LLM method can be added later with an API key.)
2. **Replay a walk** — replays the real 17-Nov walk: barometer floor + magnetometer
   checkpoint guess + step count, as a moving dot. Green ring = right checkpoint, red = wrong.

## Important
- This is a **sanity prototype**, not the final UI (that's the teammate's job). The dot
  positions are schematic (route order + floor), **not** real map metres — that needs the
  floor plan + checkpoint coordinates.
- The replay accuracy is **single-session optimistic**, not a graded result.
- The matcher here is the same code as `../request-matching/` — later it plugs into the real UI.

## Files
- `server.py` — tiny Python web server (stdlib) + the matchers + builds the replay.
- `index.html` — the page (search UI + replay map).
