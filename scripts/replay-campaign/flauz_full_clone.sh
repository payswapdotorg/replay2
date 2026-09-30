#!/usr/bin/env bash
# flauz_full_clone.sh — memory-safe two-phase full clone of Flauz (station asset).
#
# WHY THIS EXISTS: the single-pack `git clone` OOM-dies at ~1.5-1.7G of
# downloaded objects on this 4G/no-swap sandbox (observed three times on
# 2026-09-29 — SIGKILL signature: no git self-cleanup, partial dir left).
# Phase 1 clones blobless (commits+trees only — small packs, low index-pack
# memory); phase 2 checks out main, streaming blobs on demand in batches.
#
# Tradeoff (accepted): later checkouts of old pinned SHAs fetch missing
# blobs from the network on demand — a latency cost, never a correctness
# cost. The station keeps network access.
#
# Usage: flauz_full_clone.sh [URL] [DEST]
# Exit codes: 0 complete; 3 refused (destination already has .git).
set -euo pipefail

URL="${1:-https://github.com/payswapdotorg/Flauz.git}"
DEST="${2:-/home/z/Flauz}"

if [ -d "$DEST/.git" ]; then
  echo "refusing: $DEST/.git already exists"
  exit 3
fi

echo "[flauz_full_clone $(date +%H:%M:%S)] phase 1: blobless clone (commits+trees)"
git clone --filter=blob:none --no-checkout "$URL" "$DEST"

echo "[flauz_full_clone $(date +%H:%M:%S)] phase 2: checkout main (blobs streamed on demand)"
git -C "$DEST" checkout -q main

echo "[flauz_full_clone $(date +%H:%M:%S)] FLAUZ FULL CLONE COMPLETE (blobless + main checked out)"
