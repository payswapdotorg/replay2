#!/usr/bin/env bash
# flauz_station_gates.sh — the TL-B station gate runner for payswapdotorg/Flauz
# Usage: bash flauz_station_gates.sh [repo-dir] (default /home/z/flauz)
# Gates (the never-trust-reported-numbers law — the station re-runs everything):
#   1. scoped tsc per harness family (EXIT 0 each)
#   2. the lab family tsc gate (the GAP-1 addition) + full mocha batteries
#   3. the 13-family sweep totals vs the registry pin (1868 + lab 210)
#   4. determinism greps over the family modules
set -uo pipefail
R="${1:-/home/z/flauz}"
cd "$R" || exit 1
# mocha invocation: NODE_OPTIONS="--import tsx" (quoted — the value contains a space)
FAIL=0

echo "== gate 1: scoped tsc per harness family =="
for fam in contract onboarding roles ontology templates bodies packs profiles benchmarks projections activation optimization acceptance; do
  if [[ -f "build/flauz/harness/$fam/tsconfig.json" ]]; then
    if node_modules/.bin/tsc -p "build/flauz/harness/$fam/tsconfig.json" >/tmp/tsc-$fam.log 2>&1; then
      echo "  tsc $fam: EXIT 0"
    else
      echo "  tsc $fam: FAIL"; tail -5 /tmp/tsc-$fam.log; FAIL=1
    fi
  fi
done

echo "== gate 2: the lab family (tsconfig if present + battery) =="
if [[ -f build/flauz/lab/tsconfig.json ]]; then
  if node_modules/.bin/tsc -p build/flauz/lab/tsconfig.json >/tmp/tsc-lab.log 2>&1; then
    echo "  tsc lab: EXIT 0"
  else
    echo "  tsc lab: FAIL"; tail -5 /tmp/tsc-lab.log; FAIL=1
  fi
else
  echo "  tsc lab: (no scoped tsconfig yet)"
fi

echo "== gate 3: mocha battery sweep =="
TOTAL=0
for famdir in build/flauz/harness/contract build/flauz/harness/onboarding build/flauz/harness/roles build/flauz/harness/ontology build/flauz/harness/templates build/flauz/harness/bodies build/flauz/harness/packs build/flauz/harness/profiles build/flauz/harness/benchmarks build/flauz/harness/projections build/flauz/harness/activation build/flauz/harness/optimization build/flauz/harness/acceptance build/flauz/lab; do
  files=$(find "$famdir/test" -name "*.test.ts" 2>/dev/null)
  [[ -z "$files" ]] && continue
  n=$(NODE_OPTIONS="--import tsx" node_modules/.bin/mocha --ui tdd $files 2>&1 | rg -o "([0-9]+) passing" | head -1 | rg -o "[0-9]+" )
  f=$(NODE_OPTIONS="--import tsx" node_modules/.bin/mocha --ui tdd $files 2>&1 | rg -o "([0-9]+) failing" | head -1 | rg -o "[0-9]+")
  echo "  $(basename $famdir): ${n:-0} passing, ${f:-0} failing"
  TOTAL=$((TOTAL + ${n:-0}))
  [[ "${f:-0}" != "0" ]] && FAIL=1
done
echo "  SWEEP TOTAL: $TOTAL (registry pin pre-GAP-1: 1868 + 210 lab = 2078)"

echo "== gate 4: determinism greps (family modules, law-comments excluded is worker's duty; raw grep here) =="
for pat in "Math\.random" "Date\.now" "new Date\(" "process\.env"; do
  hits=$(rg -c "$pat" build/flauz/lab/common build/flauz/harness/*/common 2>/dev/null | rg -v "\.test\.|README" | wc -l)
  echo "  $pat: $hits files with hits (review each: law-comment lines excepted per family convention)"
done

echo "== RESULT: $([[ $FAIL == 0 ]] && echo ALL-GREEN || echo GATE-FAIL) =="
exit $FAIL
