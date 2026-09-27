#!/usr/bin/env bash
# finish-clone.sh — deepen the blobless gate repo + Lead git identity.
# Idempotent; safe to re-run after any sandbox reset.
set -euo pipefail
cd /home/z/Flauz
git config user.name "Flauz TL1 Lead"
git config user.email "tl1-lead@flauz.local"
echo "[finish-clone] deepening 500…"
git fetch --deepen=500 origin main 2>&1 | tail -2 || true
echo "[finish-clone] fetching upstream/main ref…"
git fetch origin refs/heads/upstream/main:refs/remotes/upstream/main 2>&1 | tail -2 || true
echo "[finish-clone] verifying pin objects present…"
for sha in bfeb5e2df916ff220e750e93ae89e7412d109f19 2ad07ba74dfc07af529a2dd89a0d17ac9f11dd2e; do
  if git cat-file -e "$sha" 2>/dev/null; then echo "  ok $sha"; else echo "  MISSING $sha (will fetch on demand)"; fi
done
echo "[finish-clone] done. HEAD=$(git rev-parse --short HEAD)"
