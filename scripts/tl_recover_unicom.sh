#!/usr/bin/env bash
# tl_recover_unicom.sh — ONE-COMMAND idempotent recovery from a sandbox pod
# recycle. Proven path: recycle #3 recovery 2026-10-05 19:53Z (deploy clean
# on first pass, session auto-restored from the durable token).
#
# Durability architecture (recycle #3 lesson):
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
UNICOM="/home/z/UniCom"
export PATH="$HOME/.npm-global/bin:$PATH"

log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

stack_healthy() {
  # console identity + login API + replayd health
  curl -sf --max-time 5 http://127.0.0.1:3000/api/status >/dev/null 2>&1 || return 1
  local title
  title=$(curl -sf --max-time 5 http://127.0.0.1:3000/ 2>/dev/null | grep -o "<title>[^<]*</title>" || true)
  [[ "$title" == *"Replay Console"* ]] || return 1
  curl -sf --max-time 5 http://127.0.0.1:3100/healthz >/dev/null 2>&1 || return 1
  return 0
}

keeper_running() { # <script-basename> — pgrep the double-forked daemon
  # (log-mtime is UNRELIABLE: keepers log only on events, so quiet logs go
  # stale and caused duplicate launches in the 20:08Z test — recycle-#3 fix)
  pgrep -f "$1\$" >/dev/null 2>&1
}

log "=== TL recover start ==="

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
  # IDEMPOTENT seed append (the 20:08Z test appended duplicates — recycle-#3
  # fix): only records whose (name,url,sent) tuple is not already present.
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

# 4b. lane-history materialization (recovery #10 lesson, 2026-10-12 ~22:4xZ
#     recycle: the registry/seed + prompt + marker trio was WIPE-VULNERABLE —
#     only the script itself survives every recycle via git clone, so the
#     retired tradrl-w28f lane's render state reconstructs from HERE now)
if ! grep -q '"name": "tradrl-w28f", "action": "done"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "tradrl-w28f", "action": "create", "ts": 1791348407, "prompt_file": "/home/z/replay2/scripts/worker-prompts/tradrl-w28f.md", "tab_id": ""}
{"name": "tradrl-w28f", "action": "send", "ts": 1791359787, "url": "https://chat.z.ai/c/542e25b0-cb3b-41dd-82c4-20f415143045", "sent": true}
{"name": "tradrl-w28f", "action": "done", "ts": 1791377191}
LANEEOF
  log "tradrl-w28f lane history materialized"
fi
[[ -f "$REPLAY2/scripts/flags/tradrl-w28f-complete.marker" ]] || \
  { touch "$REPLAY2/scripts/flags/tradrl-w28f-complete.marker"; log "tradrl-w28f complete marker materialized"; }
if [[ ! -s "$REPLAY2/scripts/worker-prompts/tradrl-w28f.md" ]]; then
  cat > "$REPLAY2/scripts/worker-prompts/tradrl-w28f.md" << 'PROMPTEOF'
# WORK ORDER W-28 (lane B) — the Neon DDL runbook route (internal plane)

> [recovery #10 provenance, 2026-10-13] The original work-order body was
> lost to the pod recycle of 2026-10-12 ~22:4xZ (worker-prompts was
> wipe-vulnerable). This stub preserves the H1 — the console's live-Workers
> title derivation reads line 1. The lane is RETIRED: delivered + merged
> (registry done @ 1791377191; complete marker present).
PROMPTEOF
  log "tradrl-w28f prompt stub materialized"
fi

# 4c. w2-027 lane-history materialization (recycle #12 lesson, 2026-10-13
#     ~14:1xZ: the lane retired 09:59Z in Task 8-4 [merged d5d42aa, issue #20
#     closed] but its trio was never added HERE — the recycle erased the
#     zcode-chain lane from the workers strip. Doctrine: EVERY retired lane
#     gets its trio in this script AT RETIREMENT TIME.)
if ! grep -q '"name": "w2-027", "action": "done"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "w2-027", "action": "create", "ts": 1791880460, "prompt_file": "/home/z/replay2/scripts/worker-prompts/w2-027.md", "tab_id": ""}
{"name": "w2-027", "action": "send", "ts": 1791880590, "url": "https://chat.z.ai/c/46a38270-98f4-4885-b750-7e7424214677", "sent": true}
{"name": "w2-027", "action": "done", "ts": 1791885586}
LANEEOF
  log "w2-027 lane history materialized"
fi
[[ -f "$REPLAY2/scripts/flags/w2-027-complete.marker" ]] || \
  { touch "$REPLAY2/scripts/flags/w2-027-complete.marker"; log "w2-027 complete marker materialized"; }
if [[ ! -s "$REPLAY2/scripts/worker-prompts/w2-027.md" ]]; then
  cat > "$REPLAY2/scripts/worker-prompts/w2-027.md" << 'PROMPTEOF'
# W2-027 — zcode-cli Subtree Chain Closure: the Fresh-Clone Clean Build Path

> [recovery #12 provenance, 2026-10-13] The original dispatch prompt (the
> 8,394-char work-order-verbatim + operational contract) was lost to the pod
> recycle of 2026-10-13 ~14:1xZ (worker-prompts was wipe-vulnerable). This
> stub preserves the H1 — the console's live-Workers title derivation reads
> line 1. The work order itself survives verbatim in-repo:
> payswapdotorg/UniCom docs/work-orders/W2-027.md (the completion report at
> docs/work-orders/reports/W2-027-completion-report.md). The lane is RETIRED:
> delivered + merged (d5d42aa, issue #20 closed 09:59:46Z; registry done @
> 1791885586; complete marker present). Chat ground truth: title "W2-027
> Subtree Chain Closure Build Path", created 08:33:03Z, last update 09:25:24Z.
PROMPTEOF
  log "w2-027 prompt stub materialized"
fi

# 5. deploy (only if unhealthy — idempotent)
if stack_healthy; then
  log "replay stack already healthy — skipping deploy"
else
  log "deploying replay stack (flags-first canonical path)…"
  (cd "$REPLAY2" && CONSOLE_LAUNCHER=scripts/launch_dev.py bash deploy.sh >> "$LOG" 2>&1)
  if stack_healthy; then log "deploy OK — stack healthy"; else log "WARN: stack health check failed post-deploy — check $LOG"; fi
fi

# 6. login keeper (auto-restores ali26 from the durable token — no operator
#    login needed; snapshots the token every 20 min once logged in)
if keeper_running login_keeper.py; then
  log "login_keeper already live"
else
  # 2026-10-13 recycle #11 (parallel station's eb46e76): system python3 on a
  # fresh pod lacks websocket-client (ModuleNotFoundError kills the keeper) —
  # prefer the venv python (/home/z/.venv, provisioned from pyproject.toml).
  _KEEPER_PY="$( [[ -x /home/z/.venv/bin/python3 ]] && echo /home/z/.venv/bin/python3 || echo python3 )"
  (cd "$REPLAY2/scripts" && "$_KEEPER_PY" dfork_launch.py logs/login_keeper.log "$_KEEPER_PY" login_keeper.py)
  log "login_keeper launched (dfork'd, py=$_KEEPER_PY)"
fi

# 7. lane watcher (console strip: server-side lane probes every 120s)
if keeper_running lane_watch_unicom.py; then
  log "lane_watch already live"
else
  (cd "$REPLAY2/scripts" && python3 dfork_launch.py logs/lane_watch_unicom.log python3 lane_watch_unicom.py)
  log "lane_watch_unicom launched (dfork'd)"
fi

# 8. UniCom clone + PAT remote + pnpm
if [[ ! -d "$UNICOM/.git" ]]; then
  git clone --quiet "https://github.com/payswapdotorg/UniCom.git" "$UNICOM" \
    && log "UniCom cloned @ $(cd "$UNICOM" && git rev-parse --short HEAD)" \
    || log "WARN: UniCom clone failed"
else
  (cd "$UNICOM" && git fetch --quiet origin && log "UniCom refreshed (main @ $(git rev-parse --short origin/main))")
fi
if [[ -n "${GITHUB_PAT:-}" ]] && [[ -d "$UNICOM/.git" ]]; then
  (cd "$UNICOM" && git remote set-url origin "https://${GITHUB_PAT}@github.com/payswapdotorg/UniCom.git" >/dev/null 2>&1)
  log "UniCom PAT remote set"
fi
command -v pnpm >/dev/null 2>&1 || corepack prepare pnpm@10.33.2 --activate >/dev/null 2>&1
# 2026-10-13 recycle #11 (eb46e76): corepack shims land outside PATH on fresh
# pods — npm -g is the reliable fallback (the recorded #9 doctrine).
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@10.33.2 >/dev/null 2>&1
log "pnpm: $(pnpm --version 2>/dev/null || echo MISSING)"

log "=== TL recover done ==="
exit 0
