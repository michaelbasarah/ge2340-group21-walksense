# Fresh recording labels — team workflow

1. Open `labeling/assignments.csv` and agree on ownership of source IDs with the team. Enter your GitHub username or team alias and `claimed` in the relevant rows. Keep an owner for each ID; coordinate claims before simultaneously editing this shared file. No one has been assigned automatically.
2. Download `phase2/clean-data/2026-11-14/RELABEL_TEMPLATE.csv` using GitHub's Raw/Download button, or copy it from a clone. Save your copy as `labeling/submissions/<your-alias>.csv`. Use a short alias without contact details. Each submission keeps all 49 original rows; edit only your claimed IDs. Keep the master template blank until the team explicitly reconciles returns.
3. Open your CSV in Excel/LibreOffice. Preserve headers, stable `source_recording_id`, source ZIP filename/SHA-256 and all timestamps exactly (import identity and time columns as text). Sort whole rows together. IDs BM01–BM26 and ACC01–ACC23 identify real files, not location order. Sender contact details are withheld; filenames and IDs link to `phase2/clean-data/2026-11-14/raw/attachments/` for inspection. ACC15 is the original P16–18 file, not a missing P15 file.
4. For each **BM** recording, fill `confirmed_stop_name` and `confirmed_floor`; a new `confirmed_stop_number` is optional. For each **ACC** recording fill `walking_from_stop_name` and `walking_to_stop_name`; endpoint numbers are optional. Use recognizable physical names and a consistent floor convention (4/5). Keep uncertainty blank and explain it in `review_notes`; never guess from an old provisional label.
5. Use `recording_status` as `valid`, `repeat`, `test`, or `uncertain`. A repeat still gets a name; optionally set `repeat_visit_of_source_id` to the earlier source ID of the same recording kind. For a test/uncertain recording explain in notes. Do not remove a recording to force 26 stops into 25 descriptions. Preserve the existing measured data, raw ZIPs and historical manifests.
6. Save **CSV UTF-8** (not XLSX with a CSV extension). From repository root run `python3 scripts/validate_labels.py labeling/submissions/<your-alias>.csv`. This checks structure/identity and reports how many rows are complete; a successful structural check does **not** mean all rows have been labeled or physical labels are true. `--require-complete` fails until every row is confirmed or explicitly marked test with notes.
7. Return via a branch and pull request containing your submission and assignment status update. With the GitHub web UI, choose Add file → Upload files in `labeling/submissions/`, upload your CSV and select a new branch/pull request where available. If you cannot access GitHub, send the CSV privately to the project owner; the owner can upload it without copying raw chat.
8. The team reviewer compares submissions by stable ID, resolves conflicting labels with the recorder, and creates a separate `labeling/reconciled.csv` retaining all 49 rows. Run the validator and, when ready, `--require-complete`. Keep individual returns for provenance. Applying accepted labels to old manifests, synthetic connector endpoints and the map graph requires a deliberate follow-up; this repository does not silently apply them.

Optional Git return (replace `your-alias` with your actual alias):

```sh
git switch -c labels/your-alias
# Save labeling/submissions/your-alias.csv and update your assignment rows.
python3 scripts/validate_labels.py labeling/submissions/your-alias.csv
git add labeling/submissions/your-alias.csv labeling/assignments.csv
git commit -m "Add recording labels from your-alias"
git push -u origin labels/your-alias
```

Owner-supplied training/test splits must keep a source acquisition and its copied proxy together. Labeling creates ground truth candidates; it is not permission to train or publish.
