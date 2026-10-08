#!/usr/bin/env bash
# predev-heal.sh — boot hook target (package.json "predev": this file).
# Fires when the platform boots `bun run dev` after a sandbox recycle.
# Runs the one-command recovery in the BACKGROUND so the dev command is
# not blocked; the recovery's own PORT GUARD evicts this scaffold squatter
# from :3000 once the Replay Console is ready (EADDRINUSE loser-dies is
# the proven steady state — the console owns :3000).
RECOVER=/home/z/replay2/scripts/tl_recover.sh
LOG=/home/z/my-project/download/recovery/predev.log
mkdir -p "$(dirname "$LOG")"
# never block the dev boot; never double-run
if pgrep -f "tl_recover\.sh" >/dev/null 2>&1; then
  echo "[predev-heal] recovery already running — skipping" >> "$LOG"
elif curl -sf --max-time 3 http://127.0.0.1:3000/ 2>/dev/null | grep -q "<title>Replay Console</title>"; then
  echo "[predev-heal $(date -u +%H:%M:%SZ)] console healthy — no action" >> "$LOG"
else
  echo "[predev-heal $(date -u +%H:%M:%SZ)] launching background recovery" >> "$LOG"
  setsid nohup bash "$RECOVER" >> "$LOG" 2>&1 &
fi
exit 0
