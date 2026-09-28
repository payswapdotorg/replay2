#!/usr/bin/env bash
# integration_check.sh <branch> — Lead-side gate verification of a delivery branch.
# Doctrine: NEVER trust reported test numbers; re-run the trio at the pushed head.
# Usage: integration_check.sh qa002-delivery
set -uo pipefail
BRANCH="${1:?usage: integration_check.sh <branch>}"
cd /home/z/aise-integration || exit 1
echo "── fetching $BRANCH"
git fetch origin "$BRANCH" || { echo "FETCH FAIL — branch not on remote"; exit 2; }
git rev-parse "origin/$BRANCH"
git checkout -B "verify/$BRANCH" "origin/$BRANCH" || exit 3
git log --oneline -3
echo "── install"
bun install --frozen-lockfile >/dev/null 2>&1 || { echo "INSTALL FAIL"; exit 4; }
echo "── typecheck"
bun run typecheck 2>&1 | tail -3
TC=$?
echo "── lint"
bun run lint 2>&1 | tail -3
LN=$?
echo "── verify (full battery)"
bun run verify 2>&1 | tail -6
VF=$?
echo "── diffstat vs main"
git diff --stat origin/main...HEAD | tail -5
echo "═══ GATES: typecheck=$TC lint=$LN verify=$VF ═══"
[ "$TC" -eq 0 ] && [ "$LN" -eq 0 ] && [ "$VF" -eq 0 ] && echo "ALL GREEN — approve-candidate" || echo "GATE FAILURE — require-changes"
