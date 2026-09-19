#!/usr/bin/env bash
# r20_gate_run.sh — lead pre-harvest verification of wfx/r20/byof (six gates).
# Runs detached; appends a verdict block to flags/r20d_harvest_gates.log.
set -uo pipefail
BR="wfx/r20/byof"
WT="/home/z/r20d-verify"
LOG="/home/z/replay2/scripts/flags/r20d_harvest_gates.log"
PY=/home/z/.venv/bin/python3

ts(){ date -u +%H:%M:%S; }
{
echo "=== R20-DESKTOP BRANCH GATE RUN start $(ts) UTC ==="
echo "HEAD: $(git -C $WT rev-parse HEAD) ($(git -C $WT log -1 --format=%s | head -c 60))"
} >> "$LOG"

cd "$WT" || { echo "FATAL: worktree missing" >> "$LOG"; exit 1; }

run_gate(){
  local name="$1"; shift
  local t0=$(date +%s)
  echo "--- gate: $name ($(ts)) ---" >> "$LOG"
  if "$@" >> "$LOG" 2>&1; then
    local t1=$(date +%s)
    echo "GATE $name: PASS ($((t1-t0))s)" >> "$LOG"
  else
    local t1=$(date +%s)
    echo "GATE $name: FAIL ($((t1-t0))s) — see above" >> "$LOG"
  fi
}

run_gate "install" nice -n 19 bun install --frozen-lockfile
run_gate "lint" bun run lint
run_gate "typecheck" bun run typecheck
run_gate "test" bun run test
run_gate "contract-check" bun run contract-check
run_gate "lane-check" bun run lane-check

# test summary line extraction
echo "--- test tally ---" >> "$LOG"
rg -o "[0-9]+ pass|([0-9]+) skip|[0-9]+ fail" "$LOG" | tail -3 >> "$LOG" 2>/dev/null || true

echo "=== R20-DESKTOP BRANCH GATE RUN done $(ts) UTC — verdict: $(rg -c 'GATE .*: PASS' "$LOG" | tail -1)/6 pass (cumulative count includes prior runs) ===" >> "$LOG"
