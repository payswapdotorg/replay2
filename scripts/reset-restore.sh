#!/usr/bin/env bash
# reset-restore.sh — ONE-COMMAND recovery after a sandbox reset.
#
# The sandbox periodically wipes /home/z/my-project (the platform app) while
# keeping /home/z/.venv, /home/z/.cache (Playwright Chromium), .bun and
# .npm-global. Everything the replay console needs is either in THIS repo
# (committed) or re-derivable. This script rebuilds the whole deployment:
#
#   1. ports the console UI + API routes into the platform app (/ route)
#   2. sets the platform layout title to "Replay Console" (the identity the
#      supervisor's console_body_ok() and deploy.sh's console_ok() check)
#   3. teaches eslint to ignore the nested replay2/ repo
#   4. materializes the lead-watch daemon (tracked source → scripts/local/)
#   5. runs deploy.sh — Xvfb + Chrome CDP :9222 + replayd :3100 + the ring;
#      the console gate sees the platform app already serving the identity,
#      so NO separate console dev server is ever spawned (port war dead)
#
# Prerequisites (NOT in this repo — it is PUBLIC, never commit secrets):
#   - credentials persisted by the TL to /home/z/.payswap-env (from the
#     operator's standing instruction; only needed for git push/dispatch,
#     not for this script)
#
# Usage (after a reset, from anywhere):
#   git clone https://x-access-token:$PAT@github.com/payswapdotorg/replay2.git \
#       /home/z/my-project/replay2
#   bash /home/z/my-project/replay2/scripts/reset-restore.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"     # replay2 repo root
MY=/home/z/my-project                        # platform app

say() { echo "[restore $(date +%H:%M:%S)] $*"; }

# ------------------------------------------------ 0. sanity
[ -d "$MY/src/app" ] || { say "FATAL: $MY is not the platform app"; exit 1; }
for f in src/app/page.tsx src/components/replay-console.tsx \
         src/components/mission-control.tsx src/lib/replay.ts src/lib/mission.ts; do
  [ -f "$ROOT/$f" ] || { say "FATAL: $ROOT/$f missing (wrong repo?)"; exit 1; }
done

# ------------------------------------------------ 1. port the console
say "porting console UI + API routes into $MY ..."
cp "$ROOT/src/app/page.tsx"                       "$MY/src/app/page.tsx"
cp "$ROOT/src/components/replay-console.tsx"      "$MY/src/components/replay-console.tsx"
cp "$ROOT/src/components/mission-control.tsx"     "$MY/src/components/mission-control.tsx"
cp "$ROOT/src/lib/replay.ts"                      "$MY/src/lib/replay.ts"
cp "$ROOT/src/lib/mission.ts"                     "$MY/src/lib/mission.ts"
# 2026-10-03: the AgentChat evolution (PR #1) — page.tsx imports these; a copy
# list without them 500s the dev server on a fresh my-project (Task-65 lesson).
if [ -f "$ROOT/src/components/AgentChat.tsx" ]; then
  cp "$ROOT/src/components/AgentChat.tsx"         "$MY/src/components/AgentChat.tsx"
  cp "$ROOT/src/components/Markdown.tsx"          "$MY/src/components/Markdown.tsx"
  cp "$ROOT/src/lib/chatStore.ts"                 "$MY/src/lib/chatStore.ts"
  for r in agent/chat agent/capabilities; do
    mkdir -p "$MY/src/app/api/$r"
    cp "$ROOT/src/app/api/$r/route.ts"            "$MY/src/app/api/$r/route.ts"
  done
fi
for r in frame tabs mission inbox status workers event; do
  mkdir -p "$MY/src/app/api/$r"
  cp "$ROOT/src/app/api/$r/route.ts" "$MY/src/app/api/$r/route.ts"
done
# 2026-10-04: the Engineering-Lab console evolution (B1/B2/B3 waves, Tasks
# 25-28) — page.tsx is a 3-view switcher (replay/mission/lab) importing the
# lab tree; a copy list without it 500s the dev server on a fresh
# my-project. Synced from the surviving my-project at the Phase C opening.
if [ -d "$ROOT/src/lib/lab" ]; then
  mkdir -p "$MY/src/lib/lab" "$MY/src/components/lab" "$MY/src/app/api/lab"
  cp -r "$ROOT/src/lib/lab/." "$MY/src/lib/lab/"
  cp -r "$ROOT/src/components/lab/." "$MY/src/components/lab/"
  cp -r "$ROOT/src/app/api/lab/." "$MY/src/app/api/lab/"
  say "lab console tree ported ($(find "$MY/src/lib/lab" "$MY/src/components/lab" -type f | wc -l) files)"
fi
# 2026-10-05 (reset-3 lesson): the agent tree + prisma lab models + deps.
# src/agent was tracked here but never ported (Task-17 manual gap); the lab
# Prisma models lived only in the wiped my-project; ws/@e2b deps were never
# synced. Port all three so a fresh my-project boots the full agent console.
if [ -d "$ROOT/src/agent" ]; then
    mkdir -p "$MY/src/agent"
    cp -r "$ROOT/src/agent/." "$MY/src/agent/"
    say "agent tree ported ($(find "$MY/src/agent" -type f | wc -l) files)"
fi
[ -f "$ROOT/src/lib/db.ts" ] && cp "$ROOT/src/lib/db.ts" "$MY/src/lib/db.ts"
if [ -f "$ROOT/prisma/schema.prisma" ] && ! grep -q "model LabRun" "$MY/prisma/schema.prisma" 2>/dev/null; then
    mkdir -p "$MY/prisma"
    cp "$ROOT/prisma/schema.prisma" "$MY/prisma/schema.prisma"
    (cd "$MY" && bun run db:push >/dev/null 2>&1) \
        && say "prisma lab schema synced (db:push ok)" \
        || say "WARN: db:push failed — run 'bun run db:push' manually"
fi
if [ -f "$MY/src/agent/e2b.ts" ] && ! grep -q '"@e2b/code-interpreter"' "$MY/package.json" 2>/dev/null; then
    (cd "$MY" && bun add ws @e2b/code-interpreter @e2b/desktop >/dev/null 2>&1) \
        && say "agent deps installed (ws, @e2b/code-interpreter, @e2b/desktop)" \
        || say "WARN: bun add agent deps failed"
fi
# login-ambush materialization (same pattern as mos_lead_watch): arm_login
# drives the form to the live slider; post_drag_keeper clicks Sign in after
# the operator's drag; login_keeper (tracked above) snapshots the token.
mkdir -p "$ROOT/scripts/local"
for daemon in arm_login post_drag_keeper; do
    if [ -f "$ROOT/scripts/$daemon.py" ] && [ ! -f "$ROOT/scripts/local/$daemon.py" ]; then
        cp "$ROOT/scripts/$daemon.py" "$ROOT/scripts/local/$daemon.py"
        say "$daemon materialized into scripts/local/"
    fi
done
mkdir -p "$MY/data"
say "console files ported (mission state: $([ -f "$MY/data/mission-state.json" ] && echo kept || echo 'not present — neutral No-mission state') )"

# ------------------------------------------------ 2. layout identity
python3 - "$MY/src/app/layout.tsx" <<'PYEOF'
import re, sys
p = sys.argv[1]
s = open(p).read()
if '<title>Replay Console</title>' in s:
    print("  layout already carries the console identity")
else:
    s2 = re.sub(r'title:\s*"[^"]*"(\s*,\s*\n\s*description:\s*)"[^"]*"',
                r'title: "Replay Console"\1"Remote browser control console — live click / drag / typing replay, worker dispatch, and mission control."', s, count=1)
    if s2 == s:
        # generic fallback: swap the metadata title regardless of description shape
        s2 = re.sub(r'(title:\s*)"[^"]*"', r'\1"Replay Console"', s, count=1)
    open(p, "w").write(s2)
    print("  layout title set to 'Replay Console'")
PYEOF

# ------------------------------------------------ 3. eslint ignores
python3 - "$MY/eslint.config.mjs" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()
if "replay2/**" in s:
    print("  eslint already ignores replay2/**")
else:
    s = s.replace(
        'ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts", "examples/**", "skills"]',
        'ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts", "examples/**", "skills", "replay2/**", "mini-services/**", "data/**"]')
    open(p, "w").write(s)
    print("  eslint now ignores replay2/** (+ build artifacts)")
PYEOF

# ------------------------------------------------ 4. lead-watch daemon
# The resident lane watch (mos_lead_watch) is deployment-local by governance
# (scripts/local/ is gitignored), but its source is tracked here so a reset
# never loses the daemon: materialize the local instance from the tracked
# file. The 2026-10-03 fix (lanes reload EVERY cycle + per-lane status files
# for the console workers strip) must survive resets.
if [ -f "$ROOT/scripts/mos_lead_watch.py" ]; then
    mkdir -p "$ROOT/scripts/local"
    if [ ! -f "$ROOT/scripts/local/mos_lead_watch.py" ]; then
        cp "$ROOT/scripts/mos_lead_watch.py" "$ROOT/scripts/local/mos_lead_watch.py"
        say "lead-watch daemon materialized into scripts/local/ (tracked source)"
    else
        say "lead-watch daemon already present in scripts/local/"
    fi
fi

# ------------------------------------------------ 5. deploy the stack
# The platform dev server (boot hook) hot-reloads the ported files; by the
# time deploy.sh checks, :3000 already serves <title>Replay Console</title>
# so it skips spawning any separate console dev server.
say "running deploy.sh (Xvfb + Chrome + replayd + ring) ..."
bash "$ROOT/deploy.sh"

say "RESTORE COMPLETE — open the preview panel (port 3000) and log into the target site through the replay image."
