#!/usr/bin/env bash
# deploy.sh — one-command deployment of the replay console stack.
#
# Idempotent: every component is health-checked first and only started when
# dead/missing, so re-running is always safe. Fresh sandbox → full stack.
#
# Env overrides:
#   REPLAY_PORT      console port            (default 3000)
#   SKIP_BROWSER=1   don't start/verify Xvfb+Chrome (console-only redeploy)
#   SKIP_SUPERVISOR=1 don't start watcher/supervisor (e.g. parallel test next
#                    to an already-supervised deployment)
#   CHROME_BIN       explicit chrome path    (else auto-discovered)
#   REPLAY_START_URL first page loaded in the browser (default https://chat.z.ai/)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$ROOT/scripts"
PORT="${REPLAY_PORT:-3000}"
CDP_PORT="${CDP_PORT:-9222}"
REPLAYD_PORT="${REPLAYD_PORT:-3100}"
export REPLAY_PORT CDP_PORT REPLAYD_PORT
export REPLAYD_URL="http://127.0.0.1:$REPLAYD_PORT"

# Deployment secrets (COMPOSIO_API_KEY / E2B_API_KEY / ZAI_API_KEY_FALLBACK).
# Optional, gitignored, chmod 600 — sourced so the whole supervised tree
# (console dev server included) inherits them. Never commit this file.
if [ -f "$SCRIPTS/env.sh" ]; then
  . "$SCRIPTS/env.sh"
  export COMPOSIO_API_KEY E2B_API_KEY ZAI_API_KEY_FALLBACK ZAI_FALLBACK_BASE_URL 2>/dev/null || true
  echo "[deploy] secrets: scripts/env.sh sourced"
fi

say() { echo "[deploy $(date +%H:%M:%S)] $*"; }

http_ok() { curl -sf -o /dev/null --max-time 4 "$1" && return 0 || return 1; }

# Console identity check: :PORT must serve the REPLAY CONSOLE itself, not just
# any http server. After a sandbox reset the boot hook auto-starts my-project's
# `bun run dev` on :3000; accepting it blindly hands the operator a page that
# can never show the replay or the login flow (root cause of the "can't login"
# report, 2026-09-16).
# 2026-09-29 hardening: the check now matches the console's <title> tag. The
# bare string "Replay Console" also appears in my-project's retirement notice
# (which mentions this repo by name), so the loose grep produced a false
# positive and deploy.sh left the retirement page on :PORT (caught live during
# the Task-135 reset recovery). The metadata title is rendered only by the
# console itself.
console_ok() {
  curl -sf --max-time 5 "http://127.0.0.1:${1:-3000}/" 2>/dev/null \
    | grep -q "<title>Replay Console</title>"
}

# Evict non-console listeners on :PORT (keep anything running from replay2).
evict_squatters() {
  local port="${1:-3000}" evicted=""
  while read -r line; do
    case "$line" in *":$port "*) ;; *) continue ;; esac
    for tok in $(printf '%s\n' "$line" | grep -oE 'pid=[0-9]+' | cut -d= -f2); do
      local cwd="" cmd=""
      cwd=$(readlink "/proc/$tok/cwd" 2>/dev/null || true)
      cmd=$(tr '\0' ' ' < "/proc/$tok/cmdline" 2>/dev/null || true)
      case "$cwd$cmd" in *replay2*) continue ;; esac
      kill "$tok" 2>/dev/null || true
      evicted="$evicted pid $tok (${cwd:-${cmd:0:70}})"
    done
  done < <(ss -tlnp 2>/dev/null)
  if [ -n "$evicted" ]; then
    say "PORT GUARD: evicted non-console squatter(s) on :$port -$evicted"
  fi
  return 0
}

# ---------------------------------------------------------------- 1. python
# The CDP stack needs a python with the `websocket` module (websocket-client).
PY_BIN=""
for cand in "${PYTHON_BIN:-}" /home/z/.venv/bin/python3 python3 python /usr/bin/python3; do
  [ -x "$(command -v "$cand" 2>/dev/null || true)" ] || [ -x "$cand" ] || continue
  if "$cand" -c "import websocket" >/dev/null 2>&1; then
    PY_BIN="$cand"
    break
  fi
done
if [ -z "$PY_BIN" ]; then
  say "installing websocket-client for python3…"
  pip3 install --user --quiet websocket-client 2>/dev/null \
    || python3 -m pip install --user --quiet websocket-client \
    || pip3 install --quiet websocket-client \
    || true
  if python3 -c "import websocket" >/dev/null 2>&1; then
    PY_BIN="python3"
  fi
fi
if [ -z "$PY_BIN" ]; then
  echo "FATAL: no python with the 'websocket' module available." >&2
  echo "Fix: pip3 install websocket-client  (then re-run ./deploy.sh)" >&2
  exit 1
fi
echo "$PY_BIN" > "$SCRIPTS/python_bin.txt"
mkdir -p "$SCRIPTS/flags" "$SCRIPTS/logs"
say "python: $PY_BIN"

# ------------------------------------------------ 1b. §0 pre-commit guard
# Anti-contamination enforcement (operator directive 2026-10-05): install the
# tracked guard as the git pre-commit hook. Idempotent (content-compare), so
# every deploy/restore heals a fresh clone's missing hooks. .gitignore is NOT
# enforcement (git add -f walks past it — 2026-10-02 incident); this is.
if [ -d "$ROOT/.git" ] && [ -f "$SCRIPTS/guards/pre_commit.py" ]; then
  if ! cmp -s "$SCRIPTS/guards/pre_commit.py" "$ROOT/.git/hooks/pre-commit" 2>/dev/null; then
    mkdir -p "$ROOT/.git/hooks"
    cp "$SCRIPTS/guards/pre_commit.py" "$ROOT/.git/hooks/pre-commit"
    chmod +x "$ROOT/.git/hooks/pre-commit"
    say "pre-commit guard installed (§0 anti-contamination enforcement)"
  fi
fi

# ---------------------------------------------------------------- 2. console deps
if [ ! -d "$ROOT/node_modules" ]; then
  say "installing console dependencies (bun install)…"
  (cd "$ROOT" && bun install)
else
  say "console dependencies present"
fi

# ---------------------------------------------------------------- 3. browser
if [ "${SKIP_BROWSER:-0}" = "1" ]; then
  say "SKIP_BROWSER=1 — skipping Xvfb/Chrome"
else
  if http_ok "http://127.0.0.1:$CDP_PORT/json/version"; then
    say "Chrome CDP :$CDP_PORT already up"
  else
    say "starting Xvfb + Chrome (CDP :$CDP_PORT)…"
    (cd "$ROOT" && "$PY_BIN" scripts/launch_stack.py)
  fi
fi

# ---------------------------------------------------------------- 4. replayd
if http_ok "http://127.0.0.1:$REPLAYD_PORT/healthz"; then
  say "replayd :$REPLAYD_PORT already up"
else
  say "starting replayd :$REPLAYD_PORT…"
  (cd "$ROOT" && REPLAYD_PORT="$REPLAYD_PORT" "$PY_BIN" scripts/launch_replayd.py)
  for i in $(seq 1 20); do
    http_ok "http://127.0.0.1:$REPLAYD_PORT/healthz" && break
    sleep 1
  done
fi
http_ok "http://127.0.0.1:$REPLAYD_PORT/healthz" || say "WARN: replayd not healthy yet (watcher will keep trying)"

# ---------------------------------------------------------------- 5. console
if console_ok "$PORT"; then
  say "console :$PORT already up (identity verified)"
else
  if http_ok "http://127.0.0.1:$PORT"; then
    say ":$PORT is up but NOT the replay console — evicting squatter…"
    evict_squatters "$PORT"
    for i in $(seq 1 15); do
      http_ok "http://127.0.0.1:$PORT" || break
      sleep 1
    done
  fi
  say "starting console dev server :$PORT…"
  # CONSOLE_LAUNCHER: per-deployment console choice (shared-repo contract).
  # Default scripts/launch_console.py = platform app (my-project) — correct
  # wherever my-project has been built out as the console (2026-09-30
  # architecture). Deployments where the platform app is the pristine
  # scaffold (no console UI inside) set CONSOLE_LAUNCHER=scripts/launch_dev.py
  # — the replay2 Next app that serves <title>Replay Console</title>. The
  # ring's console_body_ok marker check is satisfied by either server, so
  # the supervisor/watcher resurrection paths need no changes.
  (REPLAY_PORT="$PORT" "$PY_BIN" "${CONSOLE_LAUNCHER:-scripts/launch_console.py}")
fi
CONSOLE_OK=0
for i in $(seq 1 60); do
  if console_ok "$PORT"; then CONSOLE_OK=1; break; fi
  sleep 2
done
if [ "$CONSOLE_OK" = "1" ]; then
  say "console :$PORT is live (Replay Console identity verified)"
else
  say "WARN: console :$PORT not serving the Replay Console yet — check scripts/dev.log"
fi

# ---------------------------------------------------------------- 6. watchdogs
if [ "${SKIP_SUPERVISOR:-0}" = "1" ]; then
  say "SKIP_SUPERVISOR=1 — not starting watcher/supervisor"
else
  if pgrep -f "$SCRIPTS/supervisor.py" >/dev/null; then
    say "supervisor already running"
  else
    say "starting supervisor (mutual watchdog with watcher)…"
    setsid nohup "$PY_BIN" "$SCRIPTS/supervisor.py" \
      >> "$SCRIPTS/logs/supervisor.log" 2>&1 < /dev/null &
  fi
fi

# ---------------------------------------------------------------- 7. summary
echo
say "================ REPLAY STACK SUMMARY ================"
http_ok "http://127.0.0.1:$CDP_PORT/json/version" && echo "  Chrome CDP    :$CDP_PORT  UP"  || echo "  Chrome CDP    :$CDP_PORT  down"
http_ok "http://127.0.0.1:$REPLAYD_PORT/healthz" && echo "  replayd       :$REPLAYD_PORT  UP" || echo "  replayd       :$REPLAYD_PORT  down"
http_ok "http://127.0.0.1:$PORT"             && echo "  console       :$PORT  UP" || echo "  console       :$PORT  down"
[ "${SKIP_SUPERVISOR:-0}" = "1" ] || pgrep -f "$SCRIPTS/supervisor.py" >/dev/null \
  && echo "  supervisor    ----   UP" || echo "  supervisor    ----   down"
echo "  logs          $SCRIPTS/logs/, $SCRIPTS/*.log"
echo "===================================================================="
echo
echo "NEXT: open the console (preview panel / port $PORT) and LOG IN to the"
echo "target site through the replay image — the session persists in the"
echo "DURABLE browser profile (default /home/z/my-project/browser-profile; env"
echo "REPLAY_PROFILE_DIR overrides; legacy scripts/browser-profile auto-migrates)"
echo "so logins now survive sandbox resets too."
echo "Drag slider captchas directly on the replay image: press, drag slowly,"
echo "release. If a click lands wrong, toggle 'DOM click' mode."
