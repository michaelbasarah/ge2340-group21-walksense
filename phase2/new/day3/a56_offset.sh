#!/bin/sh
# a56 night offset: keep / exclude / recalibrate comparison (PROCESS-LOG entry 73), offline analysis only.
# Writes phase2/new/day3/out-a56/ only; config.json, out/ and out-split20/ are not changed.
#   sh phase2/new/day3/a56_offset.sh          (PYTHON=/path/to/python; JOBS=parallel runs, default 6)
set -e
cd "$(dirname "$0")/../../.."
PY=${PYTHON:-python3}
JOBS=${JOBS:-6}
"$PY" -I phase2/clean-data/2026-11-25-night/scripts/build_night.py > /dev/null
"$PY" -I phase2/clean-data/2026-11-25-spots/scripts/build_clean.py > /dev/null
"$PY" phase2/new/day3/data.py > /dev/null                      # default feature cache
"$PY" phase2/new/day3/a56_offset.py fields > phase2/new/day3/out-a56/fields.log
"$PY" phase2/new/day3/a56_offset.py prepare                    # build every option's feature tables once (no races)
mkdir -p phase2/new/day3/out-a56/logs
# one line per run: "<option> <default|--split20>" (no trailing blank: xargs -L would join the lines)
for o in A B C C1 C2 C21; do for v in default --split20; do echo "$o $v"; done; done |
  xargs -P "$JOBS" -L 1 sh -c 'PY="$0"; "$PY" phase2/new/day3/a56_offset.py run "$1" "$2" > "phase2/new/day3/out-a56/logs/$1$2.log" 2>&1' "$PY"
"$PY" phase2/new/day3/a56_offset.py report
