# GE2340 Group 21 — WalkSense / Wayfind

Team workspace for the current sensor acquisition, fresh recording labels, indoor-navigation prototype and project source. Start with **[labeling/README.md](labeling/README.md)** if you are naming recordings.

## Start here

- **Label all 49 original recordings:** [RELABEL_TEMPLATE.csv](phase2/clean-data/2026-11-14/RELABEL_TEMPLATE.csv). Download the raw CSV, then open in Excel/LibreOffice; GitHub's preview is read-only. All confirmation cells intentionally start blank.
- **Coordinate work:** [labeling/assignments.csv](labeling/assignments.csv). Claim stable IDs before labeling; use separate submission files to avoid overwriting teammates.
- **Inspect measurements and limitations:** [dataset README](phase2/clean-data/2026-11-14/README.md), [processing history](phase2/clean-data/2026-11-14/PROCESSING_LOG.md), [feature explanation](phase2/clean-data/2026-11-14/features/FEATURES_EXPLAINED.md).
- **Try the map:** download/clone the repo and open [Wayfind.html](phase2/map-ui/dist/Wayfind.html) in your browser. GitHub displays HTML source rather than running the app. No installation is needed for the standalone file.
- **Project planning:** [GROUP-PLAN.md](phase2/GROUP-PLAN.md) and its HTML companion are prior planning context, not evidence every proposed feature exists.
- **Phase 1:** [sanitized copy of current submitted proposal source](phase1-work/Phase1_Proposal_v2.tex) preserves the technical content of the Phase1_Submission_Group21 proposal source, with student IDs/emails withheld. Other proposal drafts in that folder are historical. Identity-bearing PDFs, signed forms and the class roster remain privately preserved outside this repository; sanitized editable source is included.
- **Course instructions/templates:** [Project-Description.pdf](Project-Description.pdf), root LaTeX templates and style. Students must write the report; course policy permits LLM polishing only. No new submission prose or results have been generated for this handoff.

## What is ready and what remains

The latest acquisition is **2026-11-14 v4**, expanded under `phase2/clean-data/2026-11-14/`: 26 real stationary recordings, 23 real movement recordings, 46,124 accepted sensor readings and descriptive feature tables. Existing names/numbers in historical manifests are **untrusted candidate labels**. There are 26 stop recordings but only 25 older descriptions; no extra visit has been identified or deleted. BM IDs are source-file IDs, not physical location numbers. The new 49-row template has no old candidate names.

The explicitly synthetic 664-sample connector copies ACC15, shares its acquisition group, and is not an independent observation. Wi-Fi observations are selective exports, not complete scans; cross-device clocks are unverified and GPS is not indoor ground truth. No distance, compass calibration, indoor localization model or training result is supplied. The map app uses an illustrative floor plan and manual demo location, not measured physical tracking. Fresh labels do not automatically update the map graph or measurement tables.

This workspace includes raw sensor attachments and Wi-Fi BSSID/SSID/GPS metadata for team analysis. **The owner selected public publication at `michaelbasarah/ge2340-group21-walksense`.** Full WhatsApp exports/messages/contact identities, class rosters, student IDs and original signed/identity-bearing PDFs are excluded. Original local files were preserved. See [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) for included files, exclusions, original hashes and distributable hashes.

## Run and check

Python 3 and Node.js are sufficient for the core checks; no packages, model downloads or paid services are needed:

```sh
python3 scripts/validate_team.py
python3 scripts/validate_labels.py
cd phase2/map-ui
npm test
npm run build
npm start
```

The server prints its address (normally `http://127.0.0.1:4173`). Alternatively open `dist/Wayfind.html` directly. Browser photos/maps are stored on that browser only; keep originals separately. See the [app README](phase2/map-ui/README.md) for setup, optional DOM checks and manual browser QA.

To validate descriptive features independently:

```sh
cd phase2/clean-data/2026-11-14
python3 feature_extraction.py --validate-only
```

`clean.py --validate-only` requires the excluded full original chat archive. Historical `validation.json` records validation against the owner's original archive, not a new full-source validation of this private-source-free checkout. The team validator instead checks included raw hashes, feature source hashes and template identity locally. Rebuilding cleaning from scratch requires obtaining the original privately and following the dataset README; do this in a separate private working copy, because cleaning writes chat material to `raw/`. Never commit the private export or transcript. Feature regeneration is separate from human label reconciliation and does not apply confirmations.

Use [docs/GITHUB_HANDOFF.md](docs/GITHUB_HANDOFF.md) for owner upload/access steps and [labeling/README.md](labeling/README.md) for teammate returns. No repository has been published by preparing these files.
