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
#   - 2026-10-14 recycle #15: FULL image resets wipe download/recovery
#     entirely (the sandbox resurrects from an old snapshot). GitHub stays
#     the code authority; the DEPLOYMENT state (credentials/repos/mission
#     cards) is mirrored to Upstash Redis under payswap:recovery:* — step 0b
#     below rebuilds the kit from that mirror when only the Redis URL+token
#     survive (any of: ambient env, ~/.secrets/env.sh, /home/z/.payswap-env).
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

# 0b. Upstash Redis kit restore (recycle #15: full image reset wipes the
#     durable kit; the mirror under payswap:recovery:* rebuilds it. Bootstrap
#     chain: the Redis URL+token must be available from ANY of the ambient
#     env, ~/.secrets/env.sh, /home/z/.payswap-env — a fresh TL session seeds
#     one of those from its conversation context, then this step pulls the
#     whole kit. Never logs secret values.)
#     2026-10-14 recycle #18 lesson: the OLD all-or-nothing gate (pull only
#     when credentials.env was absent) silently skipped the mirror whenever
#     heal's seed_kit had re-created credentials.env from its embedded copy —
#     so the mission-state entry was never fetched and the console booted
#     with an empty board ("No mission loaded" — the 'wrong replay'
#     symptom, live-caught after R18). Per-entry doctrine now: creds resolve
#     whenever ANY kit entry is missing; each entry restores ONLY when its
#     local file is absent/empty (seed wins, never clobbers a fresher local).
_kit_gaps() {
  [[ ! -s "$DURABLE_DIR/credentials.env" ]] && return 0
  [[ ! -s "$DURABLE_DIR/repos.txt" ]] && return 0
  [[ ! -s "$DURABLE_DIR/watch_repo.txt" ]] && return 0
  [[ ! -s "$DURABLE_DIR/mission-state.json" ]] && return 0
  # 2026-10-17 recycle lesson: the desktop-release spec is a kit entry too —
  # a rollback that reverts it must trigger the mirror path so §4b can
  # restore the console /desktop/ artifacts at recover time.
  [[ ! -s "$DURABLE_DIR/desktop-release.env" ]] && return 0
  return 1
}
# 2026-10-14 recycles #18-#20 lesson: the snapshot-pinned kit carries a
# DELETED Upstash endpoint (meet-ewe-145933) — present-but-stale entries
# pass _kit_gaps yet the mirror is unreachable. Liveness is a gap too: a
# dead endpoint must trigger the mirror path (and when the mirror itself
# is what died, vault_guard.py — supervised by supervisor.py — heals from
# the private payswapdotorg/ops-vault repo instead).
_kit_creds_dead() {
  local _u _t
  _u="$(sed -n 's/^export UPSTASH_REDIS_REST_URL="\?\([^"]*\)"\?$/\1/p' "$DURABLE_DIR/credentials.env" 2>/dev/null | head -1)"
  _t="$(sed -n 's/^export UPSTASH_REDIS_REST_TOKEN="\?\([^"]*\)"\?$/\1/p' "$DURABLE_DIR/credentials.env" 2>/dev/null | head -1)"
  [[ -z "$_u" || -z "$_t" ]] && return 1   # no creds at all → gaps path handles
  curl -sf --max-time 10 "$_u/ping" -H "Authorization: Bearer $_t" 2>/dev/null | grep -q PONG && return 1
  return 0
}
if _kit_gaps || _kit_creds_dead; then
  _creds_dead=0; _kit_creds_dead && _creds_dead=1
  for _src in "$HOME/.secrets/env.sh" "/home/z/.payswap-env"; do
    # shellcheck disable=SC1090
    [[ -f "$_src" ]] && . "$_src" && break
  done
  _ru="${UPSTASH_REDIS_REST_URL:-}"; _rt="${UPSTASH_REDIS_REST_TOKEN:-}"
  # Dead-credentials heal (recycles #18-#20): ambient sources carry the
  # SAME stale endpoint as the kit — the mirror is unreachable with them.
  # The GitHub tier is the only one that rolls forward: pull the live
  # vault from the PRIVATE payswapdotorg/ops-vault repo with the kit PAT,
  # install, and re-resolve. vault_guard.py (supervised) covers the
  # steady-state; this covers the recovery path.
  if [[ -n "$_ru" && -n "$_rt" ]] && ! curl -sf --max-time 10 "$_ru/ping" -H "Authorization: Bearer $_rt" 2>/dev/null | grep -q PONG; then
    _vp=""
    _sp="$(sed -n 's/^export PAYSWAP_PAT="\?\([^"]*\)"\?$/\1/p' "$DURABLE_DIR/credentials.env" 2>/dev/null | head -1)"
    [[ -z "$_sp" ]] && _sp="$(sed -n 's/^export GITHUB_TOKEN="\?\([^"]*\)"\?$/\1/p' "$DURABLE_DIR/credentials.env" 2>/dev/null | head -1)"
    if [[ -n "$_sp" ]]; then
      rm -rf /tmp/tlr-vault-pull
      if GIT_TERMINAL_PROMPT=0 git clone --quiet --depth 1 \
          "https://x-access-token:${_sp}@github.com/payswapdotorg/ops-vault.git" \
          /tmp/tlr-vault-pull >/dev/null 2>&1 && [[ -s /tmp/tlr-vault-pull/credentials.env ]]; then
        _nu="$(sed -n 's/^export UPSTASH_REDIS_REST_URL="\?\([^"]*\)"\?$/\1/p' /tmp/tlr-vault-pull/credentials.env | head -1)"
        _nt="$(sed -n 's/^export UPSTASH_REDIS_REST_TOKEN="\?\([^"]*\)"\?$/\1/p' /tmp/tlr-vault-pull/credentials.env | head -1)"
        if [[ -n "$_nu" && -n "$_nt" ]] && curl -sf --max-time 10 "$_nu/ping" -H "Authorization: Bearer $_nt" 2>/dev/null | grep -q PONG; then
          cp /tmp/tlr-vault-pull/credentials.env "$DURABLE_DIR/credentials.env"
          chmod 600 "$DURABLE_DIR/credentials.env"
          cp "$DURABLE_DIR/credentials.env" /home/z/.payswap-env
          [[ -d /home/z/my-project/browser-profile ]] && cp "$DURABLE_DIR/credentials.env" /home/z/my-project/browser-profile/ops-vault.env
          _ru="$_nu"; _rt="$_nt"; _creds_dead=0
          log "kit creds were DEAD — live vault installed from private ops-vault repo"
        else
          log "WARN: private ops-vault repo reachable but its endpoint is also dead — operator rotation needed"
        fi
      else
        log "WARN: private ops-vault repo unreachable — steady-state heal deferred to vault_guard.py"
      fi
      rm -rf /tmp/tlr-vault-pull
    fi
    unset _vp _sp _nu _nt
  fi
  if [[ -n "$_ru" && -n "$_rt" ]]; then
    log "durable kit incomplete — restoring missing entries from the Upstash Redis mirror"
    _redis_get() {
      curl -sf --max-time 20 "$_ru/get/payswap:recovery:$1" \
        -H "Authorization: Bearer $_rt" 2>/dev/null | python3 -c \
        'import json,sys
try:
    d = json.load(sys.stdin)
    r = d.get("result", "")
    print(r if isinstance(r, str) else "")
except Exception:
    pass' 2>/dev/null
    }
    if [[ ! -s "$DURABLE_DIR/credentials.env" || "$_creds_dead" == 1 ]]; then
      # liveness override: a DEAD seed must NOT win over the mirror's live vault
      _v="$(_redis_get credentials-env)"
      [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/credentials.env" && chmod 600 "$DURABLE_DIR/credentials.env"
    fi
    if [[ ! -s "$DURABLE_DIR/repos.txt" ]]; then
      _v="$(_redis_get repos-txt)"
      [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/repos.txt"
    fi
    if [[ ! -s "$DURABLE_DIR/watch_repo.txt" ]]; then
      _v="$(_redis_get watch-repo)"
      [[ -n "$_v" ]] && printf '%s'   "$_v" > "$DURABLE_DIR/watch_repo.txt"
    fi
    if [[ ! -s "$DURABLE_DIR/mission-state.json" ]]; then
      # Per-station board key (2026-10-15 doctrine, live-caught on the
      # Epoch-2.0 station): the SHARED mission-state key holds whichever
      # station healed last — a full-image reset restored the PARALLEL
      # station's board onto this console. This station's board lives under
      # mission-state:<slug> (slug = watch-repo, restored just above or
      # carried by the snapshot kit); the legacy shared key is the fallback
      # for stations that have not adopted per-station keys.
      _slug="$(tr 'A-Z' 'a-z' < "$DURABLE_DIR/watch_repo.txt" 2>/dev/null | sed 's/[^a-z0-9]\+/-/g; s/^-*//; s/-*$//')"
      _v=""
      if [[ -n "$_slug" ]]; then
        _v="$(_redis_get "mission-state:$_slug")"
        [[ -n "$_v" ]] && log "mission-state restored from PER-STATION mirror key (mission-state:$_slug)"
      fi
      if [[ -z "$_v" ]]; then
        _v="$(_redis_get mission-state)"
      fi
      [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/mission-state.json"
      unset _slug
    fi
    if [[ ! -s "$DURABLE_DIR/agent_outbox.seed.jsonl" ]]; then
      _v="$(_redis_get outbox)"
      # staged, NOT written to flags/ directly: step 2's `git clean -qfd
      # scripts/flags` would remove an untracked outbox there; step 4 installs
      # it after the clone refresh (seed wins only when the live outbox is
      # absent/empty — never clobbers a fresher local thread).
      [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/agent_outbox.seed.jsonl"
    fi
    if [[ ! -s "$DURABLE_DIR/desktop-release.env" ]]; then
      # Per-station key ONLY (outbox doctrine): a station's desktop-release
      # spec is never another station's content — no shared fallback. The
      # spec feeds the generic §4b console mirror; restored here so the
      # mirror materializes at RECOVER time (vault_guard's cycle covers
      # steady-state self-heal) — 2026-10-17 recycle lesson: without this,
      # a reverted spec 404'd /desktop/* until manually fixed.
      _slug="$(tr 'A-Z' 'a-z' < "$DURABLE_DIR/watch_repo.txt" 2>/dev/null | sed 's/[^a-z0-9]\+/-/g; s/^-*//; s/-*$//')"
      if [[ -n "$_slug" ]]; then
        _v="$(_redis_get desktop-release:$_slug)"
        [[ -n "$_v" ]] && printf '%s\n' "$_v" > "$DURABLE_DIR/desktop-release.env" && chmod 600 "$DURABLE_DIR/desktop-release.env" && log "desktop-release.env restored from PER-STATION mirror key (desktop-release:$_slug)"
      fi
      unset _slug
    fi
    log "Redis per-entry restore done ($(ls -A "$DURABLE_DIR" | wc -l) kit entries on disk)"
  else
    log "NOTE: durable kit has gaps and no Upstash credentials in env — seed ~/.secrets/env.sh with UPSTASH_REDIS_REST_URL/TOKEN to pull the mirror"
  fi
  unset _ru _rt _v _src _creds_dead
  unset -f _redis_get 2>/dev/null || true
fi
unset -f _kit_gaps _kit_creds_dead 2>/dev/null || true

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
  {
    printf '# PAT relay for replay watcher (auto-seeded by tl_recover.sh 2026-10-09)\n'
    # REPO relay (generic, §0-clean): propagate the deployment-local repo
    # designation into the relay file so bridge.py's repo card +
    # launch_prod.py env parity survive recycles. 2026-10-15 fallback
    # (ali23/LikeWise regression, post-R22): the ops-vault credentials.env
    # carries NO REPO line — the relay lost the station designation and the
    # repo card went blank. The vault is fleet-shared; the designation is
    # station-local. §0-clean source: the kit's repos.txt first line. Never
    # guess; skip the line if no source has one.
    _repo_line=""
    if [[ -n "${REPO:-}" ]]; then
      _repo_line="REPO=$REPO"
    elif [[ -s "${DURABLE_DIR:-}/repos.txt" ]]; then
      _repo_line="REPO=$(head -1 "${DURABLE_DIR}/repos.txt")"
    fi
    [[ -n "$_repo_line" ]] && printf '%s\n' "$_repo_line"
    printf 'PAYSWAP_PAT=%s\nGITHUB_TOKEN=%s\n' "$_pat" "$_pat"
  } > "$HOME/.secrets/env.sh"
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
#    2026-10-14 recycle #18: the deep-rollback class wipes download/recovery
#    AND my-project/data — but browser-profile/ has survived EVERY recycle
#    class so far (ops-vault + login-cookie precedent). It is now the
#    last-resort seed vault for the mission board + local-services spec.
if [[ ! -s "$DURABLE_DIR/mission-state.json" && -s "/home/z/my-project/browser-profile/mission-state.json" ]]; then
  cp "/home/z/my-project/browser-profile/mission-state.json" "$DURABLE_DIR/mission-state.json"
  log "mission-state seeded from browser-profile vault"
fi
if [[ ! -s "$DURABLE_DIR/local-services.json" && -s "/home/z/my-project/browser-profile/local-services.json" ]]; then
  cp "/home/z/my-project/browser-profile/local-services.json" "$DURABLE_DIR/local-services.json"
  log "local-services spec seeded from browser-profile vault"
fi
if [[ -f "$DURABLE_DIR/mission-state.json" ]]; then
  cp "$DURABLE_DIR/mission-state.json" "$REPLAY2/data/mission-state.json"
  # 2026-10-14 recycle #16: the platform-app console port (my-project Next-16
  # scaffold, the recycle-#10 architecture) may own :3000 — its mission-state
  # path is CWD-relative (my-project/data/). Mirror so BOTH consoles serve the
  # current board whichever owns the port (deploy health checks pass on either).
  mkdir -p /home/z/my-project/data 2>/dev/null
  cp "$DURABLE_DIR/mission-state.json" /home/z/my-project/data/mission-state.json 2>/dev/null
  log "mission-state restored (replay2 + platform-port mirror)"
fi
[[ -f "$DURABLE_DIR/watch_repo.txt" ]] && cp "$DURABLE_DIR/watch_repo.txt" "$REPLAY2/scripts/flags/watch_repo.txt" \
  && log "watcher repo designation restored"
[[ -f "$DURABLE_DIR/local-services.json" ]] && cp "$DURABLE_DIR/local-services.json" "$REPLAY2/scripts/flags/local_services.json" \
  && log "local services spec restored (supervisor re-arms the deployment daemons)"
if [[ -d "$DURABLE_DIR/worker-prompts" ]] && [[ -n "$(ls -A "$DURABLE_DIR/worker-prompts" 2>/dev/null)" ]]; then
  cp "$DURABLE_DIR"/worker-prompts/*.md "$REPLAY2/scripts/worker-prompts/" 2>/dev/null && log "worker packets restored"
fi
# 4b. desktop-release mirror (generic, 2026-10-17): if the durable kit
#     describes a desktop release (desktop-release.env: artifact URLs +
#     sha256), mirror the artifacts into replay2/public/desktop/ so the
#     console serves them at /desktop/<name> (survives recycles). sha256-
#     verified when a checksum is given; every failure is a WARN-logged
#     skip, NEVER fatal — the canonical release URLs (mission-state
#     downloads) keep working regardless. The spec file is deployment-
#     local (durable kit, gitignored); this script stays project-agnostic
#     (governance §0).
if [[ -s "$DURABLE_DIR/desktop-release.env" ]]; then
  (
    set -a; . "$DURABLE_DIR/desktop-release.env"; set +a
    _sha="${DESKTOP_RELEASE_SHA256:-}"
    _ok=0
    _mirror_one() { # $1=url $2=name (uses _sha, increments _ok)
      local url="${1:-}" name="${2:-}" dest need=1
      [[ -z "$url" || -z "$name" ]] && return 0
      dest="$REPLAY2/public/desktop/$name"
      mkdir -p "$REPLAY2/public/desktop"
      if [[ -s "$dest" ]]; then
        if [[ "$name" == *.deb && -n "$_sha" ]]; then
          if echo "$_sha  $dest" | sha256sum -c --status 2>/dev/null; then need=0; fi
        else
          need=0
        fi
      fi
      if [[ "$need" -eq 1 ]]; then
        if curl -fsSL --max-time 120 -o "$dest" "$url"; then
          if [[ "$name" == *.deb && -n "$_sha" ]] && ! echo "$_sha  $dest" | sha256sum -c --status 2>/dev/null; then
            rm -f "$dest"
            echo "[recover] desktop-release mirror: sha256 MISMATCH on $name — dropped (canonical release URLs unaffected)"
            return 0
          fi
          _ok=$((_ok+1))
        else
          rm -f "$dest" 2>/dev/null
          echo "[recover] desktop-release mirror: download FAILED for $name (canonical release URLs unaffected)"
          return 0
        fi
      else
        _ok=$((_ok+1))
      fi
      return 0
    }
    _mirror_one "${DESKTOP_RELEASE_DEB_URL:-}" "${DESKTOP_RELEASE_DEB_NAME:-}"
    _mirror_one "${DESKTOP_RELEASE_SCRIPT_URL:-}" "${DESKTOP_RELEASE_SCRIPT_NAME:-}"
    [[ "$_ok" -gt 0 ]] && echo "[recover] desktop-release mirror ready ($_ok artifact(s) at public/desktop/)"
    exit 0
  ) >> "$LOG" 2>&1
fi
# agent outbox seed (from the Redis mirror via step 0b): install only when
# the live thread is absent/empty — a fresher local outbox always wins.
if [[ -f "$DURABLE_DIR/agent_outbox.seed.jsonl" ]]; then
  _live="$REPLAY2/scripts/flags/agent_outbox.jsonl"
  if [[ ! -s "$_live" ]]; then
    cp "$DURABLE_DIR/agent_outbox.seed.jsonl" "$_live" && log "agent outbox thread restored from seed ($(wc -l < "$_live") msgs)"
  else
    log "agent outbox seed skipped (live thread present: $(wc -l < "$_live") msgs)"
  fi
  unset _live
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

# 5b. prod console upgrade (2026-10-09 OOM fix completion, replay2 c20d995):
#     dev-mode next-server RSS grows ~134MB/min under UI frame polling and
#     OOM-kills the console (15:59Z + 17:07Z deaths). deploy.sh boots DEV
#     (always works, deps installed there); upgrade to the PROD console here
#     once the bundle can be built, and flip the resurrection flag so console
#     deaths come back as PROD (supervisor whitelist accepts launch_prod.py).
#     Fallback doctrine preserved end-to-end: launch_prod.py itself delegates
#     to launch_dev.py when .next-prod is missing — the watchdog chain never
#     leaves the operator without a console.
if [[ -d "$REPLAY2/node_modules" ]]; then
  # 2026-10-10 poison-bundle guard: Next 15 writes BUILD_ID BEFORE
  # prerender-manifest.json. A build killed by the 420s bound (or an
  # OOM/timeout mid-finalize — observed live 2026-10-09 22:41Z) leaves
  # BUILD_ID present but the bundle incomplete; the next `next start`
  # then ENOENT-crash-loops on the missing manifest. Completeness = BOTH
  # files; a partial bundle MUST trigger a rebuild (next build rewrites
  # the distDir, self-healing the poison state).
  if [[ ! -f "$REPLAY2/.next-prod/BUILD_ID" || ! -f "$REPLAY2/.next-prod/prerender-manifest.json" ]]; then
    if [[ -f "$REPLAY2/.next-prod/BUILD_ID" ]]; then
      log "partial prod bundle detected (BUILD_ID without prerender-manifest) — rebuilding"
    fi
    log "building prod console bundle (.next-prod, bounded 420s)…"
    if (cd "$REPLAY2" && NEXT_DIST_DIR=.next-prod timeout 420 bun run build >>"$LOG" 2>&1); then
      log "prod bundle built"
    else
      log "WARN: prod bundle build failed — console stays DEV (leaky but functional)"
    fi
  fi
  if [[ -f "$REPLAY2/.next-prod/BUILD_ID" && -f "$REPLAY2/.next-prod/prerender-manifest.json" ]]; then
    printf 'launch_prod.py' > "$REPLAY2/scripts/flags/console_launcher.txt"
    if [[ -f "$REPLAY2/scripts/dev.pid" ]] && kill -0 "$(cat "$REPLAY2/scripts/dev.pid")" 2>/dev/null; then
      _dpid="$(cat "$REPLAY2/scripts/dev.pid")"
      log "switching console dev($_dpid) → prod…"
      kill -TERM -- "-$_dpid" 2>/dev/null; kill -TERM "$_dpid" 2>/dev/null; sleep 4
      kill -KILL -- "-$_dpid" 2>/dev/null; kill -KILL "$_dpid" 2>/dev/null
      (cd "$REPLAY2/scripts" && python3 launch_prod.py >>"$LOG" 2>&1)
      log "prod console launched"
    else
      log "console launcher flag → launch_prod.py (no live dev console to switch)"
    fi
  fi
else
  log "console stays DEV (no node_modules for a prod build this run)"
fi
unset _dpid 2>/dev/null || true

# 6. login keeper (auto-restores the session from the durable token)
if keeper_running login_keeper.py; then
  log "login_keeper already live"
else
  # 2026-10-13 recycle #11: system python3 on a fresh pod lacks websocket-client
  # (ModuleNotFoundError crashed login_keeper 60s after launch). The venv python
  # (/home/z/.venv, provisioned from /home/z/pyproject.toml) carries it — prefer it.
  _KEEPER_PY="$( [[ -x /home/z/.venv/bin/python3 ]] && echo /home/z/.venv/bin/python3 || echo python3 )"
  (cd "$REPLAY2/scripts" && "$_KEEPER_PY" dfork_launch.py logs/login_keeper.log "$_KEEPER_PY" login_keeper.py)
  log "login_keeper launched (dfork'd, py=$_KEEPER_PY)"
fi

# 7. lane watcher — DEPLOYMENT-OPT-IN (era-neutral fix, 2026-10-10 pod-recycle #3:
#    hardcoded lane_watch_unicom.py resurrected a DEAD ERA's watcher into the
#    LikeWise deployment). Launch ONLY when the durable volume carries the
#    opt-in marker lane-watch.enabled naming the watcher script.
if [[ -f "$DURABLE_DIR/lane-watch.enabled" ]]; then
  _lw="$(cat "$DURABLE_DIR/lane-watch.enabled" | head -1 | tr -d '[:space:]')"
  [[ -z "$_lw" ]] && _lw="lane_watch_unicom.py"
  if keeper_running "$_lw"; then
    log "lane_watch ($_lw) already live"
  else
    (cd "$REPLAY2/scripts" && python3 dfork_launch.py "logs/lane_watch.log" python3 "$_lw")
    log "lane_watch ($_lw) launched (dfork'd, durable opt-in)"
  fi
else
  log "lane watch: not enabled for this deployment (no lane-watch.enabled) — skipped"
fi

# 8. project clones + PAT remotes — DEPLOYMENT-CONFIGURED (era-neutral fix,
#    2026-10-10: the hardcoded TradRL/UniCom/Fleetos trio was era drift; §0:
#    the project set belongs to the deployment, not this script). One
#    owner/name per line in $DURABLE_DIR/repos.txt (# comments allowed);
#    missing/empty file = clone nothing (neutral).
if [[ -f "$DURABLE_DIR/repos.txt" ]]; then
  while read -r repo; do
    [[ -z "${repo// /}" ]] && continue
    [[ "$repo" == \#* ]] && continue
    dir="/home/z/${repo##*/}"
    if [[ ! -d "$dir/.git" ]]; then
      # 2026-10-16 flauz switch: the flauz repo is 1.3GB of history — a full
      # clone at recovery hangs the ladder for tens of minutes. Sparse
      # blob-filtered clone when the kit carries a sparse spec
      # (sparse-${name}.txt, one dir per line); plain clone otherwise (§0:
      # era-neutral — other repos keep the original behavior).
      _name="${repo##*/}"
      if [[ -f "$DURABLE_DIR/sparse-${_name}.txt" ]]; then
        git clone --quiet --filter=blob:none --sparse --depth 50 "https://github.com/${repo}.git" "$dir" \
          && (cd "$dir" && git sparse-checkout add $(tr '\n' ' ' < "$DURABLE_DIR/sparse-${_name}.txt")) \
          && log "$repo sparse-cloned @ $(cd "$dir" && git rev-parse --short HEAD)" \
          || log "WARN: $repo sparse clone failed"
      else
        git clone --quiet "https://github.com/${repo}.git" "$dir" \
          && log "$repo cloned @ $(cd "$dir" && git rev-parse --short HEAD)" \
          || log "WARN: $repo clone failed"
      fi
    else
      (cd "$dir" && git fetch --quiet origin && log "$repo refreshed (main @ $(git rev-parse --short origin/main 2>/dev/null || echo '?'))")
    fi
    # 2026-10-14 recycle #14 fix (Task 62's documented trap, now permanent):
    # credentials.env exports GITHUB_TOKEN/PAYSWAP_PAT — NOT GITHUB_PAT — so
    # the old single-variable check always evaluated empty and every
    # post-recovery push failed with "could not read Username". Same fallback
    # chain as §1b, plus the x-access-token form GitHub documents for app/PAT
    # auth over HTTPS.
    _pat8="${GITHUB_PAT:-${PAYSWAP_PAT:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}}"
    if [[ -n "$_pat8" ]] && [[ -d "$dir/.git" ]]; then
      (cd "$dir" && git remote set-url origin "https://x-access-token:${_pat8}@github.com/${repo}.git" >/dev/null 2>&1)
    fi
  done < "$DURABLE_DIR/repos.txt"
  log "PAT remotes set ($(grep -vc '^#' "$DURABLE_DIR/repos.txt" 2>/dev/null || echo 0) repos from durable repos.txt)"
else
  log "no durable repos.txt — project clones skipped (deployment not yet configured)"
fi
command -v pnpm >/dev/null 2>&1 || corepack prepare pnpm@10.33.2 --activate >/dev/null 2>&1
# 2026-10-13 recycle #11: corepack's shims land outside PATH on fresh pods
# (corepack enable needs a writable system bin). npm -g into ~/.npm-global
# (already on PATH via the export above) is the reliable fallback.
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@10.33.2 >/dev/null 2>&1
log "pnpm: $(pnpm --version 2>/dev/null || echo MISSING)"

# 8b. flauz station toolchain (2026-10-16 switch): the flauz family gates run
#     `~/toolchain/node_modules/.bin/tsc` + `bunx --bun mocha` (the families'
#     own README run commands) — the repo itself carries no root node_modules
#     install (a 1.3GB VS Code fork; the root install is not needed for the
#     build/flauz lane). Rebuild the toolchain + the node_modules symlink so
#     the scoped tsconfigs resolve "types": ["node","mocha"] after a recycle.
if [[ -f "/home/z/flauz/.git" ]]; then
  if [[ ! -x "$HOME/toolchain/node_modules/.bin/tsc" ]]; then
    mkdir -p "$HOME/toolchain"
    (cd "$HOME/toolchain" && bun add typescript@5.9 @types/node@24 @types/mocha >/dev/null 2>&1) \
      && log "flauz toolchain built (tsc + node/mocha types)" \
      || log "WARN: flauz toolchain build failed (bun add)"
  fi
  [[ -d "$HOME/toolchain/node_modules" && ! -e "/home/z/flauz/node_modules" ]] \
    && ln -sfn "$HOME/toolchain/node_modules" "/home/z/flauz/node_modules" \
    && log "flauz node_modules symlink restored (~/toolchain)"
fi

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

# 10. mini-services heal hook (2026-10-14 recycle #16 lesson: download/recovery
#     was wiped entirely and the package.json dev-command wiring rolled back
#     with the snapshot — but my-project/mini-services/ SURVIVED and the
#     platform dev.sh AUTO-STARTS every service at boot, proven by replayd
#     coming up unattended at recycles #15/#16). Materialize the heal service
#     from the repo master so the NEXT recycle self-heals with zero Lead
#     intervention and zero PAT. The service is idempotent, polls every 300s,
#     and stays silent while the stack is healthy.
_HEAL_DIR="/home/z/my-project/mini-services/heal"
if [[ -f "$REPLAY2/scripts/heal_service.sh" ]]; then
  mkdir -p "$_HEAL_DIR"
  if [[ ! -f "$_HEAL_DIR/heal.sh" ]]; then
    cp "$REPLAY2/scripts/heal_service.sh" "$_HEAL_DIR/heal.sh"
    chmod +x "$_HEAL_DIR/heal.sh"
    log "heal.sh installed from repo master"
  fi
  if [[ ! -f "$_HEAL_DIR/package.json" ]]; then
    printf '{\n  "name": "heal",\n  "version": "1.0.0",\n  "private": true,\n  "scripts": { "dev": "bash heal.sh" }\n}\n' > "$_HEAL_DIR/package.json"
    log "heal package.json installed (platform dev.sh auto-start)"
  fi
  # seed the embedded kit (credentials/repos/dfork) — durable vault first,
  # snapshot-vintage secrets.env as the fallback (recycle #16: only that survived)
  if [[ ! -s "$_HEAL_DIR/credentials.env" ]]; then
    if [[ -s "$DURABLE_DIR/credentials.env" ]]; then
      cp "$DURABLE_DIR/credentials.env" "$_HEAL_DIR/credentials.env"
    elif [[ -s /home/z/my-project/recovery/secrets.env ]]; then
      cp /home/z/my-project/recovery/secrets.env "$_HEAL_DIR/credentials.env"
    fi
    [[ -f "$_HEAL_DIR/credentials.env" ]] && chmod 600 "$_HEAL_DIR/credentials.env" && log "heal kit credentials seeded"
  fi
  [[ -s "$DURABLE_DIR/repos.txt" && ! -s "$_HEAL_DIR/repos.txt" ]] && cp "$DURABLE_DIR/repos.txt" "$_HEAL_DIR/repos.txt"
  [[ -f "$REPLAY2/scripts/dfork_launch.py" && ! -f "$_HEAL_DIR/dfork_launch.py" ]] && cp "$REPLAY2/scripts/dfork_launch.py" "$_HEAL_DIR/dfork_launch.py"
  # start if not running (dfork'd — survives the session reaper; the pgrep
  # pattern also matches when tl_recover itself was invoked BY heal.sh — the
  # correct no-op, never a double start)
  if ! pgrep -f "mini-services/heal/heal\.sh" >/dev/null 2>&1; then
    (cd "$REPLAY2/scripts" && python3 dfork_launch.py "$_HEAL_DIR/heal.log" bash "$_HEAL_DIR/heal.sh")
    log "heal service launched (dfork'd)"
  else
    log "heal service already running"
  fi
else
  log "WARN: scripts/heal_service.sh missing — heal hook not installed"
fi
unset _HEAL_DIR

log "=== TL recover done ==="
exit 0
