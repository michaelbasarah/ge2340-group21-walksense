# Request matching (objective #9): three methods compared

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Turns a typed request ("where can I eat", "lecture theatre 2b") into **one place ID** from our list, or says **none** when the place does not exist. Three methods from the proposal are compared on the same queries: (1) keyword rules, (2) sentence embeddings, (3) an LLM that may only answer with a real place ID or `NONE`. All numbers below come from `results.json` (written by `evaluate.py`).

## Run
```bash
cd phase2/request-matching
python build_destinations.py            # destinations.csv from graph-v2 + Tian's map labels (standard library)
python build_test_set.py                # test_queries.csv incl. the fixed dev/test split (standard library)
# needs: python -m venv .venv && .venv/bin/pip install sentence-transformers matplotlib   (the venv is gitignored)
python evaluate.py --phase dev          # tune on dev rows only (writes tuned.json, caches LLM answers for dev rows)
python evaluate.py --phase final        # all rows with frozen settings: results.json/.csv, failures.csv, confusion_pairs.csv, results.png
python evaluate.py --phase tune-fuzzy   # fuzzy cut-off on dev rows only (no LLM; writes tuned.json "fuzzy")
python match.py "kantin dimana" all     # try one request; in Python: from match import match; match(q, "keyword"|"embed"|"llm"|"fuzzy_keyword"|"hybrid") -> (place_id | None, score)
```
`evaluate.py --no-llm-calls` re-scores from the cached LLM answers without any call.

## Files
- `destinations.csv`: 26 real places (graph-v2 `nodes.csv`, floors 5 and 4) with `map_key` = the label Tian's app uses (`phase2/new/upload/map/places.json`; every key is checked by the build script), tags and aliases (English, Indonesian: kantin, toilet cowo/cewe, esca naik/turun, lt, sr9, Y5302, ...). Old 15-place file kept as `destinations_v1.csv`. **Names, tags and aliases are an agent draft: the team should check and edit.**
- `test_queries.csv`: 128 queries. Columns: `set` (easy / hard), `category`, `split` (dev / test), `source`, `expected`, `note`. `expected` is a place ID, several IDs joined by `|` (any is right, e.g. the lift on either floor), `tag:<tag>` (any place with that tag) or `NONE` (no such place in our list: the right answer is to reject).
  - **easy (23)**: the starter queries, kept; `expected` remapped to the new IDs (old `EXIT5` for "way out / nearest exit / how do I get out" became `tag:exit`, `TOILET` became `tag:toilet`, "sr11" became `sr9` because graph-v2 merges SR8 to SR11). Old file: `test_queries_v1.csv`.
  - **hard (105), all `source=agent_draft`**: vague/indirect requests, accessibility, typos, Indonesian/Cantonese-English mixes, floor-specific requests, and 26 requests for places we do not have. **These are drafts written by an agent; the team must read, correct and extend them** (the `note` column marks the readings I was unsure of). The dev/test split was made by `build_test_set.py` (seed 2340, stratified by category) and committed before any method was run.
- `match.py`: the three methods, two combinations (`fuzzy_keyword` = keyword, then a difflib fuzzy match of 1- to 3-word pieces of the request against aliases of at least 4 characters; `hybrid` = keyword, then fuzzy, then the LLM only when neither finds a place) plus three older ones (`keyword_v1` = the starter substring rules, `tokens` = the starter token overlap, `embed_doc` = one vector per place). `evaluate.py`: scoring.
- `tuned.json`: the embedding "none" thresholds and the fuzzy cut-off (0.825), tuned on dev only. `llm_cache_v1.json`: every raw LLM answer with model, time, latency, cost, the system prompt and the command (cite from here).
- Outputs: `results.json` (all numbers), `results.csv` (one row per query and method), `failures.csv` (every miss: expected vs predicted), `confusion_pairs.csv` (counts of expected -> predicted), `results.png` (bar chart), `out/dev_results.json` (dev-phase check, superseded by `results.json`).
- `results_v1.csv`: starter methods re-run on the old files, see PROCESS-LOG entry 56.

## Results (from `results.json`)
Top-1 accuracy, a miss = wrong place, wrongly rejected, or (LLM) an invalid answer.

| method | easy 23 | hard dev 54 | hard test 51 | all test 62 | all 128 |
|---|---|---|---|---|---|
| keyword | 22/23 | 30/54 | 34/51 | 44/62 | 86/128 |
| embed (MiniLM, threshold 0.38 from dev) | 22/23 | 40/54 | 34/51 | 44/62 | 96/128 |
| llm (claude haiku via the CLI) | 23/23 | 53/54 | 49/51 | 60/62 | 125/128 |
| fuzzy_keyword (cut-off 0.825 from dev) | 22/23 | 34/54 | 39/51 | 49/62 | 95/128 |
| hybrid (keyword -> fuzzy -> LLM, cached answers) | 22/23 | 47/54 | 46/51 | 56/62 | 115/128 |

"None" handling on the hard set (26 requests whose right answer is NONE; precision = share of the method's rejections that were right, recall = share of the 26 it rejected): keyword 22/53 and 22/26, embed 15/25 and 15/26, llm 26/29 and 26/26, fuzzy_keyword 22/42 and 22/26, hybrid 22/22 and 22/26. Supported hard requests wrongly rejected (of 79): keyword 31, embed 10, llm 3, fuzzy_keyword 20, hybrid 0.

Cost and speed (all rows, `results.json`): LLM invalid-ID answers 0/128; LLM median 5309.5 ms per query (p95 7442, max 10960; wall clock of `claude -p`), 128 calls, total cost 0.09649 USD (reported by the CLI), needs internet. Embeddings median 5.024 ms per query on CPU after the one-off model download (about 90 MB), offline. Keyword median 0.474 ms, offline (latencies of the 25-Nov rerun; the earlier run had 9.297 and 1.121 ms).

Hybrid (`results.json` `stages`, `llm_share`, `offline_coverage`, `ms_when_llm_called`): of all 128 requests keyword answers 75, fuzzy 11 and 42 fall through to the LLM (share 0.3281; offline coverage 0.6719); on test 38 / 5 / 19 (LLM share 0.3065). Latency = local keyword + fuzzy time, plus the cached wall-clock LLM latency when it falls through: median 0.585 ms over all rows (mean 1813.466, p95 6614.252), 0.531 ms when answered locally, 5285.323 ms when the LLM is called (test 5938.766). No new LLM call was made: every fall-through answer came from `llm_cache_v1.json` (none missing). The 13 hybrid misses are all requests the LLM alone gets right: 11 answered wrongly by the keyword stage (e.g. `lecture theatre 3a` -> lt2a, `toilet on floor 6` -> male_toilet, `exit 10 on floor 4` -> exit_10) and 2 by the fuzzy stage (`lecure theater 2b` -> lt2a, `washrom femail` -> male_toilet); they never reach the LLM.

Extras: starter token overlap 48/62 on test (hard 69/105), `embed_doc` 40/62, `keyword_v1` 43/62. So on this set the old token method beat both the new keyword rules and the embeddings on test; the embeddings gained on dev (52/66 vs 42/66) but not on test (44/62 both).

## Read before quoting
- The hard queries and their expected answers are agent drafts, and the same agent wrote the aliases; the LLM is also a Claude model answering queries written by Claude. Treat the numbers as provisional until the team has reviewed the queries.
- One run per query, no repeats (the CLI gives no temperature control), so LLM numbers can move a little on a rerun.
- Several places exist on both floors (escalators, lift/stairs, exits); a request without a floor accepts either (`a|b` or a tag), so those rows are lenient for every method.
- The LLM prompt (v1) was not changed after seeing dev results (1 dev miss out of 66), so there was no prompt tuning to hide.
