#!/usr/bin/env bash
# station_battery.sh — TL4 station baseline battery at the current checkout.
# Recreated 2026-09-30 after sandbox reset #12 (the flauz-p2fix claim wave base).
# Mirrors the flauz-hygiene lane's zero-dep gate set + compat + budgets + the
# fixture family. Runs IN the Flauz clone; pass the clone root as $1 (default
# /home/z/Flauz). Everything logs to stdout; each gate's exit code is checked.
set -uo pipefail

ROOT="${1:-/home/z/Flauz}"
cd "$ROOT" || exit 2

pass=0; fail=0
gate() {
  local name="$1"; shift
  echo "=============================================================== "
  echo "[battery $(date +%H:%M:%S)] $name"
  if "$@" >"/tmp/gate_$$_$(echo "$name" | tr -c 'a-zA-Z0-9' '_').log" 2>&1; then
    tail -5 "/tmp/gate_$$_$(echo "$name" | tr -c 'a-zA-Z0-9' '_').log"
    echo "[battery] $name: GREEN"
    pass=$((pass + 1))
  else
    tail -25 "/tmp/gate_$$_$(echo "$name" | tr -c 'a-zA-Z0-9' '_').log"
    echo "[battery] $name: RED"
    fail=$((fail + 1))
  fi
}

echo "[battery] head: $(git rev-parse HEAD) ($(git log -1 --format=%s | head -c 80))"
echo "[battery] node: $(node --version)  upstream: $(git rev-parse --short origin/upstream/main 2>/dev/null || echo MISSING)"

gate "fork-critical-guard" sh build/flauz/scripts/fork-critical-guard.sh --base origin/upstream/main --head HEAD
gate "activation-lint"     node build/flauz/scripts/activation-lint.mjs --root .
gate "ia-gate"             node build/flauz/scripts/ia-gate.mjs --root . --require
gate "premium-ux-gate"     node build/flauz/scripts/premium-ux-gate.mjs --root . --require
gate "discovery-gate"      node build/flauz/discovery/p2-003-discovery-gate.mjs --root . --require
gate "verify-product"      node build/flauz/scripts/verify-product.mjs --root . --require
gate "budget-gate"         node build/flauz/scripts/budget-gate.mjs --root .
gate "compat-battery"      node build/flauz/scripts/compat-battery.mjs --root .
gate "verify-fixtures"     sh build/flauz/scripts/verify-fixtures.sh

echo "=============================================================== "
echo "[battery] SUMMARY: $pass GREEN / $fail RED  (head $(git rev-parse --short HEAD))"
[ "$fail" -eq 0 ] || exit 1
