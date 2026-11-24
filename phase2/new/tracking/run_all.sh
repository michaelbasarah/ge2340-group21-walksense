#!/bin/sh
# One command: steps/turns -> graph edges + area check -> tracker, snapshot comparison, replay export.
# Run from anywhere:  sh phase2/new/tracking/run_all.sh     (PYTHON=... to choose the interpreter)
set -e
cd "$(dirname "$0")/../../.."
PY=${PYTHON:-python3}
"$PY" phase2/new/tracking/pdr.py > /dev/null
"$PY" phase2/new/graph/build_graph.py
"$PY" phase2/new/tracking/tracker.py
