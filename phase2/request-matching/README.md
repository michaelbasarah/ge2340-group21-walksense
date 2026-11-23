# Request matching (objective #9)

Turns a typed request ("where can I eat", "lecture theatre 2b") into a **place ID**.
Vibe-coded, standard library only, offline.

## Run
```bash
cd phase2/request-matching
python match.py
```

## Files
- `destinations.csv` — the ~15 places from our walk, with aliases + tags. **Edit to add places** (the proposal targets ~30).
- `test_queries.csv` — example requests + the expected place. **Edit to add harder phrases.**
- `match.py` — two methods compared: `keyword` (alias rules) and `tokens` (inverse-frequency overlap, a lightweight stand-in for sentence embeddings).
- `results.csv` — per-query output.

## Status & honest note
Both methods currently score **100%** — but that means the **starter test set is too easy**
(the phrases map cleanly to one place). For the report's comparative analysis we need
**vaguer requests** where simple keywords fail but meaning-based methods win, e.g.
*"somewhere calm to revise before my exam"*, *"I need to print something"*,
*"grab a bite"*. Add those to `test_queries.csv` to show the differences.

## To finish #9
1. Expand `destinations.csv` toward ~30 places with tags (quiet/food/lecture/...).
2. Add vaguer/trickier test phrases (the team should write these).
3. Plug in the two remaining proposal methods: a **sentence-embedding** model
   (e.g. sentence-transformers) and an **LLM constrained to a real place ID**
   (needs internet; quote & cite its output per course rules).
