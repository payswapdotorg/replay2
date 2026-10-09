#!/usr/bin/env bash
# tl_recover.sh — ONE-COMMAND idempotent recovery from a sandbox pod recycle
# (TradRL era; successor of tl_recover_unicom.sh — same proven path).
#
# Durability architecture (recycle lessons #3..#N):
#   - THIS SCRIPT lives in payswapdotorg/replay2 git (survives via clone) and
#     in my-project/download/recovery/ (proven-durable volume).
#   - SECRETS live ONLY in my-project/download/recovery/credentials.env
#     (never in git).
#   - The durable login token lives at
#     my-project/download/zai_session_token.txt (login_keeper snapshots it
#     every 20 min while logged in; restores the session automatically).
#
# Idempotent: safe to run repeatedly; healthy components are left alone.
set -u
DURABLE_DIR="/home/z/my-project/download/recovery"
LOG="$DURABLE_DIR/recover.log"
REPLAY2="/home/z/replay2"
TRADRL="/home/z/TradRL"
UNICOM="/home/z/UniCom"
FLEETOS="/home/z/Fleetos"
export PATH="$HOME/.npm-global/bin:$PATH"
mkdir -p "$DURABLE_DIR"
log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

stack_healthy() {
  curl -sf --max-time 5 http://127.0.0.1:3000/api/status >/dev/null 2>&1 || return 1
  local title
  title=$(curl -sf --max-time 5 http://127.0.0.1:3000/ 2>/dev/null | grep -o "<title>[^<]*</title>" || true)
  [[ "$title" == *"Replay Console"* ]] || return 1
  curl -sf --max-time 5 http://127.0.0.1:3100/healthz >/dev/null 2>&1 || return 1
  return 0
}

keeper_running() { pgrep -f "$1\$" >/dev/null 2>&1; }

log "=== TL recover (TradRL era) start ==="

# 1. secrets
if [[ -f "$DURABLE_DIR/credentials.env" ]]; then
  cp "$DURABLE_DIR/credentials.env" /home/z/.payswap-env
  chmod 600 /home/z/.payswap-env
  # shellcheck disable=SC1091
  source /home/z/.payswap-env
  log "credentials restored ($(grep -c '^export' /home/z/.payswap-env) exports)"
else
  log "WARN: no durable credentials.env — continuing without PAT"
fi

# 1b. watcher PAT relay (2026-10-09 fix, standing "always fix the replay"):
# watcher.py get_pat() reads ONLY ~/.secrets/env.sh (or scripts/env.sh) — it
# never inspects the process env, so sourcing the vault above does NOT reach
# it. Observed 2026-10-09: watcher booted 08:55:55 in degraded mode because
# the ops-vault reseed landed 08:56 — after the daemon started. Seed the
# relay file here so every recycle boots the watcher in full mode on its
# first cycle (it also re-reads this file every ~2min cycle mid-flight).
_pat="${PAYSWAP_PAT:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}"
if [[ -n "$_pat" ]]; then
  mkdir -p "$HOME/.secrets"
  printf '# PAT relay for replay watcher (auto-seeded by tl_recover.sh 2026-10-09)\nPAYSWAP_PAT=%s\nGITHUB_TOKEN=%s\n' "$_pat" "$_pat" \
    > "$HOME/.secrets/env.sh"
  chmod 600 "$HOME/.secrets/env.sh"
  log "watcher PAT relay seeded (~/.secrets/env.sh)"
else
  log "WARN: no PAT in credentials — watcher will run degraded (anonymous branch watch)"
fi
unset _pat

# 2. replay2 clone (public repo, no PAT needed)
if [[ ! -d "$REPLAY2/.git" ]]; then
  git clone --quiet https://github.com/payswapdotorg/replay2.git "$REPLAY2" \
    && log "replay2 cloned ($(cd "$REPLAY2" && git rev-parse --short HEAD))" \
    || { log "FATAL: replay2 clone failed"; exit 1; }
else
  (cd "$REPLAY2" && git fetch --quiet origin && git reset --quiet --hard origin/main \
    && git clean -qfd scripts/flags data 2>/dev/null; log "replay2 refreshed @ $(git rev-parse --short HEAD)")
fi

# 3. FLAGS FIRST — before ANY :3000 eviction (binding operator directive
#    2026-10-01 16:45Z: else the ring resurrects the platform scaffold app)
mkdir -p "$REPLAY2/scripts/flags" "$REPLAY2/scripts/logs" "$REPLAY2/scripts/worker-prompts"
printf 'launch_dev.py' > "$REPLAY2/scripts/flags/console_launcher.txt"
printf '3000'         > "$REPLAY2/scripts/flags/console_port.txt"

# 4. restore deployment-local state (mission-state, packets, registry seeds)
[[ -f "$DURABLE_DIR/mission-state.json" ]] && cp "$DURABLE_DIR/mission-state.json" "$REPLAY2/data/mission-state.json" && log "mission-state restored"
if [[ -d "$DURABLE_DIR/worker-prompts" ]] && [[ -n "$(ls -A "$DURABLE_DIR/worker-prompts" 2>/dev/null)" ]]; then
  cp "$DURABLE_DIR"/worker-prompts/*.md "$REPLAY2/scripts/worker-prompts/" 2>/dev/null && log "worker packets restored"
fi
if [[ -f "$DURABLE_DIR/session_registry.seed.jsonl" ]]; then
  python3 - "$DURABLE_DIR/session_registry.seed.jsonl" "$REPLAY2/scripts/flags/session_registry.jsonl" << 'PYEOF'
import json, sys, os
seed_path, reg_path = sys.argv[1], sys.argv[2]
try:
    reg = [json.loads(l) for l in open(reg_path) if l.strip()]
except FileNotFoundError:
    reg = []
have = {(r.get("name"), r.get("url"), bool(r.get("sent"))) for r in reg}
added = 0
with open(reg_path, "a") as fh:
    for l in open(seed_path):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if (r.get("name"), r.get("url"), bool(r.get("sent"))) not in have:
            fh.write(json.dumps(r) + "\n")
            added += 1
print(f"registry seed: {added} new records appended")
PYEOF
  log "registry seeds merged (idempotent)"
fi

# 5. deploy (only if unhealthy — idempotent)
if stack_healthy; then
  log "replay stack already healthy — skipping deploy"
else
  log "deploying replay stack (flags-first canonical path)…"
  (cd "$REPLAY2" && CONSOLE_LAUNCHER=scripts/launch_dev.py bash deploy.sh >> "$LOG" 2>&1)
  if stack_healthy; then log "deploy OK — stack healthy"; else log "WARN: stack health check failed post-deploy — check $LOG"; fi
fi

# 6. login keeper (auto-restores the session from the durable token)
if keeper_running login_keeper.py; then
  log "login_keeper already live"
else
  (cd "$REPLAY2/scripts" && python3 dfork_launch.py logs/login_keeper.log python3 login_keeper.py)
  log "login_keeper launched (dfork'd)"
fi

# 7. lane watcher (console strip: server-side lane probes every 120s)
if keeper_running lane_watch_unicom.py; then
  log "lane_watch already live"
else
  (cd "$REPLAY2/scripts" && python3 dfork_launch.py logs/lane_watch_unicom.log python3 lane_watch_unicom.py)
  log "lane_watch launched (dfork'd)"
fi

# 8. project clones + PAT remotes (TradRL is the live mission; UniCom/Fleetos
#    are closed-but-referenced)
for repo in TradRL UniCom Fleetos; do
  dir="/home/z/$repo"
  if [[ ! -d "$dir/.git" ]]; then
    git clone --quiet "https://github.com/payswapdotorg/$repo.git" "$dir" \
      && log "$repo cloned @ $(cd "$dir" && git rev-parse --short HEAD)" \
      || log "WARN: $repo clone failed"
  else
    (cd "$dir" && git fetch --quiet origin && log "$repo refreshed (main @ $(git rev-parse --short origin/main 2>/dev/null || echo '?'))")
  fi
  if [[ -n "${GITHUB_PAT:-}" ]] && [[ -d "$dir/.git" ]]; then
    (cd "$dir" && git remote set-url origin "https://${GITHUB_PAT}@github.com/payswapdotorg/$repo.git" >/dev/null 2>&1)
  fi
done
log "PAT remotes set (TradRL/UniCom/Fleetos)"
command -v pnpm >/dev/null 2>&1 || corepack prepare pnpm@10.33.2 --activate >/dev/null 2>&1
log "pnpm: $(pnpm --version 2>/dev/null || echo MISSING)"

# 9. predev boot hook durability (2026-10-08 recycle lesson: download/recovery/
#    is NOT fully durable — the hook died with it; the repo copy is the master).
#    Reinstall the hook + keep the durable copy + the package.json wiring in sync.
if [[ -f "$REPLAY2/scripts/predev_heal.sh" && ! -f "$DURABLE_DIR/predev-heal.sh" ]]; then
  cp "$REPLAY2/scripts/predev_heal.sh" "$DURABLE_DIR/predev-heal.sh"
  chmod +x "$DURABLE_DIR/predev-heal.sh"
  log "predev-heal.sh reinstalled from repo master"
fi
if [[ -f "$DURABLE_DIR/credentials.env" && ! -f "/home/z/my-project/browser-profile/ops-vault.env" ]]; then
  mkdir -p /home/z/my-project/browser-profile
  cp "$DURABLE_DIR/credentials.env" /home/z/my-project/browser-profile/ops-vault.env
  chmod 600 /home/z/my-project/browser-profile/ops-vault.env
  log "ops-vault reseeded from durable credentials"
fi

log "=== TL recover done ==="
exit 0
