#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="$REPO_ROOT/reports/night-shift/hangzhou/$STAMP"

mkdir -p "$REPORT_DIR"

echo "== Hangzhou Night Shift =="
echo "Report dir: $REPORT_DIR"

python3 backend/tools/build_hangzhou_school_directory.py > "$REPORT_DIR/build.json"
python3 backend/tools/check_hangzhou_seed.py > "$REPORT_DIR/qa.json"
python3 backend/tools/plan_hangzhou_night_shift.py \
  --qa "$REPORT_DIR/qa.json" \
  --out-md "$REPORT_DIR/main-plan.md" \
  --out-json "$REPORT_DIR/main-plan.json" \
  > "$REPORT_DIR/plan.stdout.json"

cp "$REPORT_DIR/qa.json" "$REPO_ROOT/reports/night-shift/hangzhou/latest-qa.json"
cp "$REPORT_DIR/main-plan.md" "$REPO_ROOT/reports/night-shift/hangzhou/latest-main-plan.md"
cp "$REPORT_DIR/main-plan.json" "$REPO_ROOT/reports/night-shift/hangzhou/latest-main-plan.json"

echo "Night shift reports updated."
