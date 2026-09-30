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
#   4. runs deploy.sh — Xvfb + Chrome CDP :9222 + replayd :3100 + the ring;
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
for r in frame tabs mission inbox status workers event; do
  mkdir -p "$MY/src/app/api/$r"
  cp "$ROOT/src/app/api/$r/route.ts" "$MY/src/app/api/$r/route.ts"
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

# ------------------------------------------------ 4. deploy the stack
# The platform dev server (boot hook) hot-reloads the ported files; by the
# time deploy.sh checks, :3000 already serves <title>Replay Console</title>
# so it skips spawning any separate console dev server.
say "running deploy.sh (Xvfb + Chrome + replayd + ring) ..."
bash "$ROOT/deploy.sh"

say "RESTORE COMPLETE — open the preview panel (port 3000) and log into the target site through the replay image."
