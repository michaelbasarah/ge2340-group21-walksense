#!/bin/sh
# Day-3 (24 Nov) evaluation, one command, from anywhere:   sh phase2/new/day3/run_all.sh
# PYTHON=/path/to/python to pick an interpreter (needs numpy pandas scikit-learn scipy matplotlib).
# Sessions come from config.json; add a new session there and rerun this.
set -e
cd "$(dirname "$0")/../../.."
PY=${PYTHON:-python3}
"$PY" phase2/new/day3/data.py            # parse every session into window/visit tables (cached in day3/cache/)
"$PY" phase2/new/day3/wifi_check.py      # out/wifi_diagnosis.json
"$PY" phase2/new/day3/evaluate.py        # out/results.json, out/summary_table.csv
"$PY" phase2/new/day3/fused_knn.py       # out/fused_knn.json, out/fused_model.json (about 10 min)
"$PY" phase2/new/day3/track24.py         # out/track24_results.json, out/replay_24nov_s2.json
"$PY" phase2/new/day3/visualise.py       # out/*.png, out/explore.html
"$PY" phase2/new/day3/playground.py      # out/knn_playground.html (interactive kNN playground, internal)
