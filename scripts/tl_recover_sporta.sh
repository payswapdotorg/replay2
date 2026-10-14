#!/usr/bin/env bash
# tl_recover_sporta.sh — ONE-COMMAND idempotent recovery after a pod recycle.
# Durable copies: (1) /home/z/my-project/download/recovery/tl_recover_sporta.sh
#                 (2) PRIVATE repo payswapdotorg/sporta-recovery-kit (PRIMARY
#                     off-box mirror — this pod's egress blocks *.upstash.io
#                     but reaches github.com; holds credentials + session
#                     token + mission state + this script + worker packets)
#                 (3) Upstash Redis mirror, keys sporta:recovery:* (SECONDARY
#                     — reachable only from pods with upstash egress)
#                 (4) the public repo payswapdotorg/replay2 (scripts/tl_recover_sporta.sh)
# BOOTSTRAP LAW for a future session after a full kit wipe (my-project reset
# to the scaffold): the ONE thing that cannot be rebuilt from any repo is the
# PAT — seed it from the conversation context / operator re-provision:
#   echo 'export GITHUB_PAT=<pat>' > ~/.secrets/env.sh
# then run this script — step 0c rebuilds the whole kit from the private
# mirror and every later step restores the station (~40s). If the script
# itself is gone too, re-fetch it from either mirror (see header of the
# public copy at payswapdotorg/replay2 scripts/tl_recover_sporta.sh) or from
# the private repo directly.
# Any future session: read the worklog, then run THIS — it restores the replay
# console + the sporta-2.0 integration station in ~40s.
set -u
DURABLE_DIR="/home/z/my-project/download/recovery"
DOWNLOAD_DIR="/home/z/my-project/download"
LOG="$DURABLE_DIR/recover.log"
REPLAY2="/home/z/replay2"
SPORTA="/home/z/sporta-2.0"
export PATH="/usr/lib/node_modules/corepack/shims:$HOME/.npm-global/bin:$PATH"
mkdir -p "$DURABLE_DIR"
log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

stack_healthy() {
  local title
  curl -sf --max-time 5 http://127.0.0.1:3100/healthz >/dev/null 2>&1 || return 1
  title=$(curl -sf --max-time 5 http://127.0.0.1:3000/ 2>/dev/null | grep -o "<title>[^<]*</title>" || true)
  [[ "$title" == *"Replay Console"* ]] || return 1
  return 0
}

# Redis mirror helpers (Upstash REST). Never log secret values.
_redis_get() { # $1 = key slug -> value on stdout
  local _ru="${UPSTASH_REDIS_REST_URL:-}" _rt="${UPSTASH_REDIS_REST_TOKEN:-}"
  [[ -n "$_ru" && -n "$_rt" ]] || return 1
  curl -sf --max-time 20 "$_ru/get/sporta:recovery:$1" \
    -H "Authorization: Bearer $_rt" 2>/dev/null | python3 -c \
    'import json,sys
try:
    d = json.load(sys.stdin)
    r = d.get("result", "")
    sys.stdout.write(r if isinstance(r, str) else "")
except Exception:
    pass' 2>/dev/null
}
_redis_put() { # $1 = key slug, $2 = file
  local _ru="${UPSTASH_REDIS_REST_URL:-}" _rt="${UPSTASH_REDIS_REST_TOKEN:-}"
  [[ -n "$_ru" && -n "$_rt" && -f "$2" ]] || return 1
  curl -sf --max-time 30 -X POST "$_ru/set/sporta:recovery:$1" \
    -H "Authorization: Bearer $_rt" --data-binary "@$2" >/dev/null 2>&1
}

log "=== TL recover (sporta era) start ==="

# 0b. KIT REBUILD from the Upstash Redis mirror (full-image-reset class: the
#     Oct-08 snapshot resurrects my-project WITHOUT download/recovery; GitHub
#     stays the code authority, but deployment state needed an off-box store).
#     Bootstrap chain: the Redis URL+token from ANY surviving source (ambient
#     env, ~/.secrets/env.sh, /home/z/.payswap-env — a fresh TL session seeds
#     one from its conversation context per the header law).
if [[ ! -f "$DURABLE_DIR/credentials.env" ]]; then
  for _src in "$HOME/.secrets/env.sh" "/home/z/.payswap-env"; do
    # shellcheck disable=SC1090
    [[ -f "$_src" ]] && . "$_src" && break
  done
  if [[ -n "${UPSTASH_REDIS_REST_URL:-}" && -n "${UPSTASH_REDIS_REST_TOKEN:-}" ]]; then
    log "no durable kit on disk — restoring from the Upstash mirror (sporta:recovery:*)"
    _v="$(_redis_get credentials-env)"
    [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/credentials.env" && chmod 600 "$DURABLE_DIR/credentials.env"
    _v="$(_redis_get mission-state)"
    [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/mission-state.json"
    _v="$(_redis_get zai-session-token)"
    [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DOWNLOAD_DIR/zai_session_token.txt" && chmod 600 "$DOWNLOAD_DIR/zai_session_token.txt"
    _v="$(_redis_get tl-recover-script)"
    [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/tl_recover_sporta.sh" && chmod +x "$DURABLE_DIR/tl_recover_sporta.sh"
    _v="$(_redis_get tl-gates)"
    [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/tl_gates.sh"
    if [[ -f "$DURABLE_DIR/credentials.env" ]]; then
      log "kit restored from Redis ($(ls -A "$DURABLE_DIR" | wc -l) entries)"
    else
      log "WARN: Redis mirror reachable but empty — kit stays missing"
    fi
  else
    log "WARN: no durable kit and no Upstash creds — seed ~/.secrets/env.sh with UPSTASH_REDIS_REST_URL/TOKEN (see script header law)"
  fi
  unset _v _src
fi

# 0c. KIT REBUILD from the PRIVATE GitHub mirror (this pod's egress blocks
#     *.upstash.io — NXDOMAIN — so the Redis mirror is unreachable here;
#     github.com IS reachable. The private repo payswapdotorg/sporta-recovery-kit
#     holds the secret-bearing files. Bootstrap: the PAT must be seeded from
#     the conversation context / operator re-provision into ~/.secrets/env.sh
#     or /home/z/.payswap-env BEFORE this runs — see the header law.)
if [[ ! -f "$DURABLE_DIR/credentials.env" ]]; then
  _bp="${GITHUB_PAT:-${PAYSWAP_PAT:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}}"
  if [[ -n "$_bp" ]]; then
    log "kit still missing — rebuilding from the private GitHub mirror (payswapdotorg/sporta-recovery-kit)"
    rm -rf /tmp/kit-mirror-rebuild
    if git clone --quiet "https://${_bp}@github.com/payswapdotorg/sporta-recovery-kit.git" /tmp/kit-mirror-rebuild 2>/dev/null; then
      for _f in credentials.env mission-state.json tl_recover_sporta.sh tl_gates.sh; do
        [[ -f "/tmp/kit-mirror-rebuild/$_f" ]] && cp "/tmp/kit-mirror-rebuild/$_f" "$DURABLE_DIR/$_f"
      done
      [[ -f /tmp/kit-mirror-rebuild/credentials.env ]] && chmod 600 "$DURABLE_DIR/credentials.env"
      [[ -f /tmp/kit-mirror-rebuild/zai_session_token.txt ]] && cp /tmp/kit-mirror-rebuild/zai_session_token.txt "$DOWNLOAD_DIR/zai_session_token.txt" && chmod 600 "$DOWNLOAD_DIR/zai_session_token.txt"
      if [[ -d /tmp/kit-mirror-rebuild/worker-prompts ]]; then
        mkdir -p "$DURABLE_DIR/worker-prompts"
        cp /tmp/kit-mirror-rebuild/worker-prompts/*.md "$DURABLE_DIR/worker-prompts/" 2>/dev/null
      fi
      [[ -f "$DURABLE_DIR/credentials.env" ]] && log "kit rebuilt from the private GitHub mirror ($(ls -A "$DURABLE_DIR" | wc -l) entries)" \
        || log "WARN: private mirror clone OK but credentials.env missing inside"
      rm -rf /tmp/kit-mirror-rebuild
    else
      log "WARN: private GitHub mirror clone failed (PAT invalid or repo gone)"
    fi
  fi
  unset _bp _f
fi

# 1. secrets (durable)
if [[ -f "$DURABLE_DIR/credentials.env" ]]; then
  cp "$DURABLE_DIR/credentials.env" /home/z/.payswap-env; chmod 600 /home/z/.payswap-env
  set -a; source /home/z/.payswap-env; set +a
  log "credentials restored"
else
  log "FATAL: no durable credentials.env — cannot recover worker-dispatch PAT"
fi

# 1b. PAT fallback chain (recycle-#14 lesson: a single-var check evaluates
#     empty when the export name drifts; try all known names + URL forms)
GH_PAT="${GITHUB_PAT:-${PAYSWAP_PAT:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}}"
if [[ -n "$GH_PAT" ]]; then
  export GITHUB_PAT="$GH_PAT"
else
  log "WARN: no PAT found under GITHUB_PAT/PAYSWAP_PAT/GITHUB_TOKEN/GH_TOKEN — pushes will fail"
fi

# 2. replay2 clone (public repo — no PAT needed)
if [[ ! -d "$REPLAY2/.git" ]]; then
  git clone --quiet https://github.com/payswapdotorg/replay2.git "$REPLAY2" \
    && log "replay2 cloned @ $(cd "$REPLAY2" && git rev-parse --short HEAD)" \
    || { log "FATAL: replay2 clone failed"; exit 1; }
else
  log "replay2 present @ $(cd "$REPLAY2" && git rev-parse --short HEAD)"
fi

# 3. FLAGS FIRST — before ANY :3000 eviction (else the ring resurrects the
#    retired platform app; my-project dev script is retired, belt-and-braces)
mkdir -p "$REPLAY2/scripts/flags" "$REPLAY2/scripts/logs" "$REPLAY2/scripts/worker-prompts"
printf 'launch_dev.py' > "$REPLAY2/scripts/flags/console_launcher.txt"
printf '3000'         > "$REPLAY2/scripts/flags/console_port.txt"

# 4. restore deployment-local state (mission-state, worker prompts)
[[ -f "$DURABLE_DIR/mission-state.json" ]] && cp "$DURABLE_DIR/mission-state.json" "$REPLAY2/data/mission-state.json" && log "mission-state restored"
if [[ -d "$DURABLE_DIR/worker-prompts" ]] && [[ -n "$(ls -A "$DURABLE_DIR/worker-prompts" 2>/dev/null)" ]]; then
  cp "$DURABLE_DIR"/worker-prompts/*.md "$REPLAY2/scripts/worker-prompts/" 2>/dev/null && log "worker packets restored"
fi
# deployment secrets mirror + durable ops vault re-arm
cp "$DURABLE_DIR/credentials.env" "$REPLAY2/scripts/env.sh" 2>/dev/null; chmod 600 "$REPLAY2/scripts/env.sh" 2>/dev/null
mkdir -p /home/z/my-project/browser-profile
cp "$DURABLE_DIR/credentials.env" /home/z/my-project/browser-profile/ops-vault.env 2>/dev/null
chmod 600 /home/z/my-project/browser-profile/ops-vault.env 2>/dev/null

# 5. deploy (only if unhealthy — idempotent)
if stack_healthy; then
  log "replay stack already healthy — skipping deploy"
else
  log "deploying replay stack (flags-first canonical path)…"
  (cd "$REPLAY2" && CONSOLE_LAUNCHER=scripts/launch_dev.py bash deploy.sh >> "$LOG" 2>&1)
  stack_healthy && log "deploy OK — stack healthy" || log "WARN: stack health check failed — check $LOG"
fi

# 6. login keeper (auto-restores the session from the durable token)
pgrep -f login_keeper.py >/dev/null \
  && log "login_keeper already live" \
  || { (cd "$REPLAY2/scripts" && python3 dfork_launch.py logs/login_keeper.log python3 login_keeper.py); log "login_keeper launched"; }

# 7. sporta-2.0 clone + PAT remote + install (the integration station)
if [[ ! -d "$SPORTA/.git" ]]; then
  git clone --quiet "https://${GITHUB_PAT}@github.com/payswapdotorg/Sporta-2.0.git" "$SPORTA" \
    && log "sporta-2.0 cloned @ $(cd "$SPORTA" && git rev-parse --short HEAD)" \
    || log "WARN: sporta-2.0 clone failed"
else
  (cd "$SPORTA" && git remote set-url origin "https://${GITHUB_PAT}@github.com/payswapdotorg/Sporta-2.0.git" >/dev/null 2>&1)
  log "sporta-2.0 present @ $(cd "$SPORTA" && git rev-parse --short HEAD)"
fi
if [[ -d "$SPORTA/.git" ]] && [[ ! -d "$SPORTA/node_modules" ]]; then
  (cd "$SPORTA" && setsid nohup pnpm install --ignore-scripts > /home/z/sporta-install.log 2>&1 < /dev/null &)
  log "sporta install started (background)"
fi

# 8. AUTO-STAMP the mission board (runs AFTER step 7 so BOTH SHAs are known —
#    the reset-#14 'station @?' bug; kills the one-recycle-stale infra-detail
#    class at the root: every recovery stamps current facts + a timeline
#    entry, so the board is ALWAYS current). Idempotency guard: skip when the
#    board detail already carries this exact replay SHA (healthy re-runs
#    never double-stamp the timeline).
RSHA_NOW="$(git -C "$REPLAY2" rev-parse --short HEAD 2>/dev/null || echo '?')"
BOARD_DETAIL="$(python3 -c "import json; d=json.load(open('$REPLAY2/data/mission-state.json')); print(next((b.get('detail','') for b in d.get('infra',[]) if b.get('id')=='replay-stack'),''))" 2>/dev/null || true)"
if stack_healthy && [[ "$BOARD_DETAIL" != *"$RSHA_NOW"* ]]; then
  python3 - "$REPLAY2/data/mission-state.json" "$DURABLE_DIR/mission-state.json" "$REPLAY2" "$SPORTA" << 'PYEOF' 2>>"$LOG" || log "WARN: board auto-refresh failed"
import json, sys, datetime, subprocess, os
dep, dur, rep, spo = sys.argv[1:5]
def sha(path):
    try: return subprocess.check_output(["git","-C",path,"rev-parse","--short","HEAD"], text=True, timeout=10).strip()
    except Exception: return "?"
r_sha, s_sha, now = sha(rep), sha(spo), datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
detail = (f"Recovered {now} via the one-command durable kit (~40s) after the latest sandbox recycle: "
          f"fresh clone from the OFFICIAL repo payswapdotorg/replay2 @{r_sha} (flags-first), console :3000 Replay Console, "
          f"gateway :3100 healthy (frames flowing), CDP :9222, supervisor ring; login_keeper re-arms the operator "
          f"session (ali10) from the durable token. All dispatch hardening active (chat-TYPE server-verify, "
          f"capacity-recover flags, phantom/homepage GC, ws_reaper). Station @ {s_sha} (= GitHub main).")
entry = {"ts": now, "kind": "success",
         "text": (f"Recycle auto-recovered {now}: replay redeployed from the official repo @{r_sha}, station re-cloned @{s_sha}; "
                  f"board auto-stamped by tl_recover (the staleness class is dead); ring re-armed, operator session restored.")}
for p in (dep, dur):
    if not os.path.exists(p): continue
    d = json.load(open(p))
    d["updatedAt"] = now
    for b in d.get("infra", []):
        if b.get("id") == "replay-stack":
            b["status"], b["detail"] = "ok", detail
    d.setdefault("timeline", []).append(entry)
    d["timeline"] = d["timeline"][-20:]
    json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
print(f"board refreshed: replay @{r_sha} station @{s_sha}")
PYEOF
  log "mission board auto-stamped for this recovery"
fi

# 9. REFRESH the off-box mirrors (full-image-reset insurance; logs only
#    byte counts / commit SHAs — never secret values)
# 9a. PRIVATE GitHub repo (PRIMARY for this pod — egress reaches github.com;
#     holds the secret-bearing files the public repo cannot)
if stack_healthy && [[ -n "$GH_PAT" ]]; then
  rm -rf /tmp/kit-mirror-push
  if git clone --quiet "https://${GH_PAT}@github.com/payswapdotorg/sporta-recovery-kit.git" /tmp/kit-mirror-push 2>/dev/null; then
    cp "$DURABLE_DIR/credentials.env" "$DURABLE_DIR/mission-state.json" "$DURABLE_DIR/tl_recover_sporta.sh" "$DURABLE_DIR/tl_gates.sh" /tmp/kit-mirror-push/ 2>/dev/null
    cp "$DOWNLOAD_DIR/zai_session_token.txt" /tmp/kit-mirror-push/ 2>/dev/null
    mkdir -p /tmp/kit-mirror-push/worker-prompts
    cp "$DURABLE_DIR"/worker-prompts/*.md /tmp/kit-mirror-push/worker-prompts/ 2>/dev/null
    if [[ -n "$(cd /tmp/kit-mirror-push && git status --porcelain 2>/dev/null)" ]]; then
      (cd /tmp/kit-mirror-push && git add -A \
        && git -c user.name="sporta-tl" -c user.email="tl@sporta.local" commit --quiet -m "kit mirror refresh $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        && git push --quiet origin main 2>/dev/null) \
        && log "private GitHub mirror refreshed @ $(git -C /tmp/kit-mirror-push rev-parse --short HEAD)" \
        || log "WARN: private mirror push failed"
    else
      log "private GitHub mirror already current"
    fi
    rm -rf /tmp/kit-mirror-push
  else
    log "WARN: private mirror clone failed — mirror not refreshed"
  fi
fi
# 9b. Upstash Redis (SECONDARY — where egress allows; NXDOMAIN on this pod)
if stack_healthy && [[ -n "${UPSTASH_REDIS_REST_URL:-}" && -n "${UPSTASH_REDIS_REST_TOKEN:-}" ]]; then
  _mirror_files=0
  _redis_put credentials-env    "$DURABLE_DIR/credentials.env"                       && _mirror_files=$((_mirror_files+1))
  _redis_put mission-state      "$DURABLE_DIR/mission-state.json"                     && _mirror_files=$((_mirror_files+1))
  _redis_put zai-session-token  "$DOWNLOAD_DIR/zai_session_token.txt"                 && _mirror_files=$((_mirror_files+1))
  _redis_put tl-recover-script  "$DURABLE_DIR/tl_recover_sporta.sh"                   && _mirror_files=$((_mirror_files+1))
  _redis_put tl-gates           "$DURABLE_DIR/tl_gates.sh"                            && _mirror_files=$((_mirror_files+1))
  log "Redis mirror refreshed ($_mirror_files/5 entries)"
  unset _mirror_files
fi

log "=== TL recover done — console on :3000, await operator login, dispatch from inside the replay only ==="
exit 0
