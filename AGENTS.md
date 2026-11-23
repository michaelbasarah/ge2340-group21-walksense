# GE2340 Group 21 (WalkSense): standing rules for agents and teammates

## The one rule: log everything in PROCESS-LOG.md
Every piece of work MUST append a dated entry to `PROCESS-LOG.md` (repo root, newest at the bottom) in the same commit as the work. This covers collection sessions, analysis runs, **failed attempts**, relabels, reorganisations and decisions. Failures are logged as carefully as successes.

Each entry uses the same format as the existing ones: heading `## N. DD Mon: title`, then **What we tried / Why / How** (scripts, commands, files) **/ Result** (real numbers) **/ Outcome** (success or failure, and why) **/ What changed because of it / Links** (files and commit hashes). Take every number from an output file (`results.json`, `tilt_results.json`, `summary.json`, a README) or a commit message, never from memory. If a number is not in a file, do not write it. Also update the contents list, "Lessons learned" and "Open questions / next steps" at the end of the log.

## Course rule (LLM use)
The course allows an LLM only to polish the team's own writing, not to write report text. `PROCESS-LOG.md`, the READMEs, `phase2/new/TEAM-SUMMARY-2026-11-24.md` and `phase2/new/DAY3-CHECKLIST.md` are internal team notes, not report text. Do not draft report prose for submission.

## Layout
- `phase2/old/`: superseded work, kept for history (the leaky 94% positioning pilot, the old collect list). Do not extend it; do not quote its numbers as results.
- `phase2/new/`: current work: `cross-day/` (analysis code, labels, outputs), `TEAM-SUMMARY-2026-11-24.md`, `DAY3-CHECKLIST.md` (collection rules).
- Shared folders, used by both: `phase2/clean-data/` (cleaned sessions 14, 17, 23 Nov), `phase2/map/`, `phase2/prototype/`, `phase2/request-matching/`, `phase2/map-ui/`, `phase2/field-sheet.html`.
- Other: `labeling/`, `scripts/`, `docs/`, `phase1-work/`.
- Use `git mv` when moving files so history is kept. Moving means relocating, never deleting content.

## Data and reruns
- The big CSVs are gitignored (see `.gitignore`: `phase2/clean-data/2026-11-23/sensor_samples.csv`, `sensors/`, `excluded_sensor_rows.csv`, `wifi/observations.csv`). Regenerate them with `clean.py` in the session folder. Raw ZIPs stay byte-identical in `raw/attachments/`.
- Rerun the cross-day analysis from the repo root (needs `numpy pandas scikit-learn matplotlib`; make a virtual environment if the system Python lacks them):
  ```sh
  python phase2/new/cross-day/crossday.py   # about 30 s, writes out/results.json and figures
  python phase2/new/cross-day/tilt.py       # after crossday.py, writes the tilt outputs
  ```
  On the first run `crossday.py` rebuilds the 23-Nov sensor CSVs into `phase2/new/cross-day/cache/` (ignored by git). Edit `phase2/new/cross-day/labels_23nov_confirmed.csv` to change a label, then rerun.
- After a rerun, check that `out/` files did not change unexpectedly (`git status`); if numbers change, explain why in a log entry.

## Git
- Work on `main` or a branch the user names. Do not push or merge the local `prep/*` branches (`prep/training`, `prep/map`, `prep/ready`) and do not touch their worktrees.
- Never commit `cache/`, `__pycache__/`, private chat exports (`WhatsApp Chat with GE2340.*`), rosters or credentials.
- Do not delete features or data without the user's approval. Commit messages end with the co-author line the user's tooling asks for.
