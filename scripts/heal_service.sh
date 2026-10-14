#!/usr/bin/env bash
# heal.sh — the recycle-proof self-healing watchdog (mini-services/heal).
#
# 2026-10-14 recycle #16 lesson (the permanence ladder):
#   - /home/z/replay2 .............. wiped every recycle (re-cloned from GitHub)
#   - my-project/download/recovery/  wiped THIS recycle (not durable after all)
#   - my-project/package.json wiring  rolls back with the snapshot restore
#   - my-project/recovery/secrets.env survived every recycle so far (snapshot vintage)
#   - my-project/mini-services/ ..... SURVIVED and the platform dev.sh AUTO-STARTS
#     every service at boot (proven live: replayd came up on :3100 unattended at
#     recycles #15 and #16). THIS service is therefore the permanent boot hook.
#
# What this does: poll the replay stack every 300s; when unhealthy, re-materialize
# the download/recovery kit from the embedded copies, clone replay2 if missing,
# and run the repo's canonical tl_recover.sh (idempotent, flags-first, port-guard).
# Credentials: embedded credentials.env (survives here), with fallback to the
# snapshot-vintage my-project/recovery/secrets.env; token relay re-seeded by
# tl_recover itself. The EADDRINUSE loser-dies doctrine lets the recovered Replay
# Console take :3000 from the scaffold app (proven steady state).
set -u
KIT="/home/z/my-project/mini-services/heal"
DURABLE="/home/z/my-project/download/recovery"
REPLAY2="/home/z/replay2"
LOG="$KIT/heal.log"
mkdir -p "$DURABLE"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

stack_healthy() {
  curl -sf --max-time 5 http://127.0.0.1:3000/api/status >/dev/null 2>&1 || return 1
  curl -sf --max-time 5 http://127.0.0.1:3000/ 2>/dev/null | grep -q "<title>Replay Console</title>" || return 1
  curl -sf --max-time 5 http://127.0.0.1:3100/healthz 2>/dev/null | grep -q '"ok": *true' || return 1
  return 0
}

seed_kit() {
  # 1. credentials: embedded copy first; snapshot-vintage secrets.env as fallback
  if [[ ! -s "$DURABLE/credentials.env" ]]; then
    if [[ -s "$KIT/credentials.env" ]]; then
      cp "$KIT/credentials.env" "$DURABLE/credentials.env"
    elif [[ -s /home/z/my-project/recovery/secrets.env ]]; then
      cp /home/z/my-project/recovery/secrets.env "$DURABLE/credentials.env"
    fi
    [[ -f "$DURABLE/credentials.env" ]] && chmod 600 "$DURABLE/credentials.env"
  fi
  # 2. repos.txt (deployment project set — operator directive: Zeck only)
  [[ -s "$KIT/repos.txt" ]] && cp "$KIT/repos.txt" "$DURABLE/repos.txt"
  # 3. dfork + predev-heal masters (tl_recover §9 re-syncs the rest)
  [[ -s "$KIT/dfork_launch.py" ]] && cp "$KIT/dfork_launch.py" "$DURABLE/dfork_launch.py"
  return 0
}

recover_now() {
  # never double-run against a live tl_recover (mine or a manual Lead run)
  if pgrep -f "tl_recover\.sh" >/dev/null 2>&1; then
    log "recovery already in flight — standing by"
    return 0
  fi
  seed_kit
  if [[ ! -d "$REPLAY2/.git" ]]; then
    # public repo — zero PAT needed (recycle-#14 doctrine)
    if git clone --quiet https://github.com/payswapdotorg/replay2.git "$REPLAY2" >> "$LOG" 2>&1; then
      log "replay2 cloned @ $(cd "$REPLAY2" && git rev-parse --short HEAD)"
    else
      log "FATAL: replay2 clone failed — retry next cycle"
      return 1
    fi
  fi
  log "running tl_recover.sh…"
  bash "$REPLAY2/scripts/tl_recover.sh" >> "$LOG" 2>&1
  if stack_healthy; then
    log "recovery OK — stack healthy"
  else
    log "WARN: stack still unhealthy after recovery — will retry next cycle"
  fi
}

log "=== heal service started (pid $$, host $(hostname)) ==="
# one immediate cycle at boot (the scaffold owns :3000 at this moment — the
# recovery's port guard will hand it to the Replay Console), then poll forever
while true; do
  if stack_healthy; then
    : # healthy — silent (log only on state changes, below)
  else
    log "stack unhealthy — engaging recovery"
    recover_now
  fi
  sleep 300
done
