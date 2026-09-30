#!/usr/bin/env bash
# redeploy_replay.sh — TL2 product-phase reset recovery (one command, idempotent).
#
# Heals the post-reset state: no replay2 clone, no Flauz clone, no daemons,
# my-project boot hook squatting :3000, GitHub PAT wiped (debt notice only —
# re-supply channel: console input line "PAT <token>", captured by the
# watcher to /home/z/.flauz_env).
#
# RETIRED vs the TL2-H1 era: the login-gated tl2_h1 dispatch daemon is GONE
# (TL2-H1 landed via PR #49; re-arming it would re-dispatch completed work).
# The product-phase watcher (p2_fix_watch.py) is the standing daemon now.
#
# Paths: masters live in my-project/scripts/replay-campaign/ (platform
# snapshot tree); live copies deploy under replay2/scripts/replay-campaign/
# (depth law: the watcher resolves ROOT three levels up so flags/logs land
# in the replay2 tree where the console renders them).
set -euo pipefail

REPLAY=/home/z/replay2
MASTER=/home/z/my-project/scripts/replay-campaign
FLAUZ=/home/z/Flauz
PY=python3

say() { echo "[redeploy $(date +%H:%M:%S)] $*"; }

# 0. credential auto-restore (RESET-PROOF UPGRADE, 2026-09-30: the operator
#    declared the PAT/Composio keys single-supply; resets wipe ~/.flauz_env
#    + ~/.secrets; the durable master copy lives in my-project/download/
#    (the documented reset-surviving capture location, cf. zai_operator_jwt.txt).
#    Restores both locations + the bashrc hook whenever a reset wipes them.)
DURABLE_CREDS="/home/z/my-project/download/flauz_station_env.sh"
if [ ! -f /home/z/.flauz_env ] && [ -f "$DURABLE_CREDS" ]; then
  say "station env wiped by reset — restoring from durable master (download/)"
  umask 177
  cp -f "$DURABLE_CREDS" /home/z/.flauz_env && chmod 600 /home/z/.flauz_env
  mkdir -p /home/z/.secrets && chmod 700 /home/z/.secrets
  sed -n 's/^export REPO=/export REPO=/p' /home/z/.flauz_env > /dev/null
  printf '# operator credentials (canonical; mode 600; outside all repos)\n' > /home/z/.secrets/env.sh
  rg '^export (REPO|OPERATOR_PAT)=' /home/z/.flauz_env >> /home/z/.secrets/env.sh
  chmod 600 /home/z/.secrets/env.sh
fi
if ! rg -q 'flauz_env' /home/z/.bashrc 2>/dev/null; then
  printf '\n# Flauz station credentials (survive shell restarts)\n[ -f /home/z/.flauz_env ] && set -a && . /home/z/.flauz_env && set +a\n' >> /home/z/.bashrc
  say "bashrc credential hook re-wired"
fi
[ -f /home/z/.flauz_env ] && say "station env present ($(grep -c '^export' /home/z/.flauz_env) vars)" || say "WARN: no station env (PAT re-supply needed: console line 'PAT <token>')"

# 1. replay stack — NEW ARCHITECTURE (upstream 283a22d, 2026-09-30): the
#    console lives INSIDE the platform app (/home/z/my-project). The OLD
#    flow (evict the my-project squatter + spawn a separate console dev
#    server) is RETIRED — deploy.sh now treats my-project as console
#    family and dies silently under the old eviction paradigm. The new
#    entry point is reset-restore.sh: it ports the console UI + API routes
#    into the platform app, sets the Replay Console identity, then
#    deploy.sh sees the identity already served and starts only
#    Xvfb/Chrome/replayd/ring (the :3000 port war is over).
if [ ! -d "$REPLAY/.git" ]; then
  say "cloning replay2 from canonical GitHub..."
  git clone https://github.com/payswapdotorg/replay2.git "$REPLAY"
fi
bash "$REPLAY/scripts/reset-restore.sh"

# 2. resident wiring
mkdir -p "$REPLAY/scripts/flags" "$REPLAY/scripts/logs" \
         "$REPLAY/scripts/replay-campaign" "$MASTER"
if [ ! -f "$REPLAY/scripts/env.sh" ]; then
  printf 'export REPO=payswapdotorg/Flauz\n' > "$REPLAY/scripts/env.sh"
  say "env.sh wired (REPO=payswapdotorg/Flauz)"
fi
touch "$REPLAY/scripts/flags/heartbeat"

# 3. live copies of the campaign layer (masters win; queue/state flags persist)
for f in p2_fix_watch.py p2fix-wo-template.md flauz_full_clone.sh; do
  if [ -f "$MASTER/$f" ]; then
    cp -f "$MASTER/$f" "$REPLAY/scripts/replay-campaign/$f"
  fi
done
[ -f "$REPLAY/scripts/replay-campaign/p2_fix_watch.py" ] \
  && chmod +x "$REPLAY/scripts/replay-campaign/p2_fix_watch.py"

# 4. product-phase watcher: clean restart (state files survive)
pkill -f "replay-campaign/p2_fix_watch.py" 2>/dev/null || true
sleep 1
"$PY" "$REPLAY/scripts/dfork_launch.py" \
      "$REPLAY/scripts/logs/p2_fix_watch.log" \
      "$PY" "$REPLAY/scripts/replay-campaign/p2_fix_watch.py"
say "p2_fix_watch dispatched (log: replay2/scripts/logs/p2_fix_watch.log)"

# 5. Flauz station clone rebuild (direct full clone; the 2026-09-29 "OOM
#    wall" was a misdiagnosis — every death was self-inflicted interference,
#    a clean run completes in ~3 min. flauz_full_clone.sh stays as the
#    documented blobless fallback; the watcher self-heals this too)
#    RESET-#4 LESSON: the URL MUST carry the ".git" suffix — the watcher's
#    live-clone guard pattern is "git clone .*Flauz\.git /home/z/Flauz$";
#    a suffix-less spawn is invisible to it, so the watcher purged the
#    dir under the live clone and double-cloned (both raced; the watcher's
#    clone won by luck). Pattern consistency is the law for every spawner.
if [ ! -d "$FLAUZ/.git" ] && ! pgrep -f "flauz_full_clone|git clone .*payswapdotorg/Flauz" >/dev/null 2>&1; then
  say "Flauz clone missing — background full clone started"
  nohup git clone https://github.com/payswapdotorg/Flauz.git "$FLAUZ" \
        > "$REPLAY/scripts/logs/flauz_clone.log" 2>&1 &
fi

# 6. outbox redeploy notice (idempotent per 30 min)
MARK="$REPLAY/scripts/flags/p2_fix_redeploy_marker"
if [ ! -f "$MARK" ] || [ $(( $(date +%s) - $(stat -c %Y "$MARK") )) -gt 1800 ]; then
  "$PY" - "$REPLAY/scripts/flags/agent_outbox.jsonl" <<'EOF'
import json, sys, time
line = json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text":
  "Replay redeployed after sandbox reset (product phase). Stack: Chrome CDP "
  ":9222, replayd :3100, console :3000. Browser starts logged-out(guest) — "
  "sign in via the replay image (your credentials, per boot law). TL2 "
  "READY-TO-CLAIM watcher armed (findings dir + WORK-REGISTRY P2-FIX + pull "
  "refs). GitHub PAT was wiped by the reset — re-supply via this console "
  "input with a line 'PAT <token>' to unblock landing PRs."}) + "\n"
open(sys.argv[1], "a").write(line)
EOF
  touch "$MARK"
fi

say "done. Operator entry: preview panel -> :3000 (Replay Console)."
