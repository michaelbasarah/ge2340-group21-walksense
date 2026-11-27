#!/bin/sh
# Day-3 (24 Nov) evaluation, one command, from anywhere:   sh phase2/new/day3/run_all.sh
# PYTHON=/path/to/python to pick an interpreter (needs numpy pandas scikit-learn scipy matplotlib).
# Sessions come from config.json; add a new session there and rerun this.
# sh phase2/new/day3/run_all.sh --split20   runs the split20 variant (20 s pieces, 23-Nov exclusions, outlier pieces
#   removed; config.json "variants") into phase2/new/day3/out-split20/; the default run and out/ are unchanged.
set -e
cd "$(dirname "$0")/../../.."
PY=${PYTHON:-python3}
# One BLAS/OpenMP thread unless the caller sets otherwise: rules out thread-count rounding in the float32 Wi-Fi matrix
# products (PROCESS-LOG 91: reruns must give identical fused_knn.json; the kNN itself is single-threaded numpy/scipy).
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1} MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
if [ "$1" = "--split20" ]; then export DAY3_VARIANT=split20; fi
if [ "$1" = "--variant" ]; then export DAY3_VARIANT="$2"; fi      # e.g. --variant split20_only (control: pieces only)
if [ -f phase2/clean-data/2026-11-25-night/scripts/build_night.py ]; then
  "$PY" -I phase2/clean-data/2026-11-25-night/scripts/build_night.py > /dev/null   # 25 Nov night raw/ + labels_night.csv -> clean/
fi
if [ -f phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py ]; then
  "$PY" -I phase2/clean-data/2026-11-26-tian/scripts/build_tian26.py > /dev/null   # 26 Nov morning (Tian) raw/ + labels_tian26.csv -> clean/
fi
if [ -f phase2/clean-data/2026-11-25-spots/scripts/build_clean.py ]; then
  "$PY" -I phase2/clean-data/2026-11-25-spots/scripts/build_clean.py > /dev/null   # 25 Nov raw/attachments -> clean/ (labels_used.csv, summary.json)
fi
"$PY" phase2/new/day3/phone_map.py       # raw ZIP metadata -> handset per recording (phone_map.csv); stops if a model is unknown
"$PY" phase2/new/day3/data.py            # parse every session into window/visit tables (cached in day3/cache/)
"$PY" phase2/new/day3/wifi_check.py      # out/wifi_diagnosis.json
"$PY" phase2/new/day3/evaluate.py        # out/results.json, out/summary_table.csv
"$PY" phase2/new/day3/fused_knn.py       # out/fused_knn.json, out/fused_model.json (about 40 min since 26 Nov)
"$PY" phase2/new/day3/track24.py         # out/track24_results.json, out/replay_24nov_s2.json
"$PY" phase2/new/day3/visualise.py       # out/*.png, out/explore.html
"$PY" phase2/new/day3/playground.py      # out/knn_playground.html (interactive kNN playground, internal)
if [ -n "$DAY3_VARIANT" ]; then
  "$PY" phase2/new/day3/upload_eval_split20.py   # teammates' walksense.py model scored on 20 s pieces (their code unchanged)
fi
