#!/usr/bin/env bash
# r31_station_gates.sh — the lead's re-verification battery for the R31 lane.
# Usage: r31_station_gates.sh <lane-branch> <out-log>
# Runs at the station on the fetched lane head; every gate's output captured.
set -u
LANE="${1:?lane branch}"
OUT="${2:?out log}"
cd /home/z/webflix || exit 2

run() {
  echo "" >> "$OUT"
  echo "===== GATE: $1 =====" >> "$OUT"
  shift
  "$@" >> "$OUT" 2>&1
  echo "[exit $?]" >> "$OUT"
}

{
  echo "R31 STATION RE-VERIFICATION — lane $LANE @ $(git rev-parse HEAD)"
  echo "base: $(git merge-base HEAD main 2>/dev/null || echo n/a) | started $(date -u +%H:%M:%SZ)"
} > "$OUT"

git status -s | head -n 5 >> "$OUT" 2>&1
run "battery-serial (5188/1/0 claim)" nice -n 19 ionice -c3 bun test --parallel=1
run "typecheck root+journeys" bun run typecheck
run "contract-check" bun run contract-check
run "lane-check" bun run lane-check
run "parity-conformance (scoped)" bun test tests/parity-conformance.test.ts --parallel=1
run "build web" env NODE_OPTIONS=--max-old-space-size=2048 bun run --filter '@wfx/app-web' build

echo "" >> "$OUT"
echo "===== GATE: scoped lint (lane files vs merge-base) =====" >> "$OUT"
FILES=$(git diff --name-only main..."$LANE" -- 'apps/web/**' | tr '\n' ' ')
echo "lane files: $FILES" >> "$OUT"
# shellcheck disable=SC2086
bunx eslint $FILES >> "$OUT" 2>&1
echo "[exit $?]" >> "$OUT"

echo "" >> "$OUT"
echo "===== SUMMARY =====" >> "$OUT"
grep -E "^\[exit" "$OUT" | cat -n
echo "done $(date -u +%H:%M:%SZ)" >> "$OUT"
