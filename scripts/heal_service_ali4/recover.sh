#!/bin/bash
# ali4 station auto-heal recovery — the full manual, executable unattended.
# Fired by mini-services/heal/index.ts when the replay stack is down.
# flock-serialized: concurrent runs (platform heal + agent manual recovery) queue safely.
# NEVER run on a healthy stack by hand unless you intend a full re-deploy.

LOG=/home/z/my-project/mini-services/heal/heal.log
exec 9>/home/z/my-project/mini-services/heal/recover.lock
flock -n 9 || { echo "[$(date -u +%FT%TZ)] another recover.sh holds the lock — standing by" >> "$LOG"; exit 0; }

{
echo "[$(date -u +%FT%TZ)] ===== RECOVER.SH FIRING ====="

ENV_SH=/home/z/my-project/env.sh
VENV_PY=/home/z/.venv/bin/python3

# --- Step 1: credentials (env.sh is the platform-managed survivor; Oct-08 vintage) ---
if [ ! -f "$ENV_SH" ]; then
  echo "FATAL: $ENV_SH missing — cannot restore credentials unattended"
  exit 1
fi
PAT=$(grep '^export PAYSWAP_PAT=' "$ENV_SH" | cut -d= -f2)
[ -n "$PAT" ] || { echo "FATAL: PAYSWAP_PAT empty in env.sh"; exit 1; }
printf 'protocol=https\nhost=github.com\nusername=payswapdotorg\npassword=%s\n' "$PAT" > /home/z/.git-credentials
chmod 600 /home/z/.git-credentials
git config --global credential.helper store 2>/dev/null
cp "$ENV_SH" /home/z/.payswap-env; chmod 600 /home/z/.payswap-env
mkdir -p /home/z/my-project/.secrets
cp "$ENV_SH" /home/z/my-project/.secrets/env.sh; chmod 600 /home/z/my-project/.secrets/env.sh
grep -q 'secrets/env.sh' /home/z/.bashrc 2>/dev/null || echo '[ -f /home/z/my-project/.secrets/env.sh ] && source /home/z/my-project/.secrets/env.sh' >> /home/z/.bashrc
echo "[1/6] credentials restored"

# --- Step 2: replay2 clone (PAT remote set at clone time — the recovery-#12 lesson) ---
if [ ! -d /home/z/replay2 ]; then
  git clone "https://payswapdotorg:${PAT}@github.com/payswapdotorg/replay2.git" /home/z/replay2 || { echo "FATAL: clone failed"; exit 1; }
fi
cd /home/z/replay2 || exit 1
git remote set-url origin "https://payswapdotorg:${PAT}@github.com/payswapdotorg/replay2.git"
git fetch origin main --quiet 2>/dev/null
git checkout main --quiet 2>/dev/null
git reset --hard origin/main --quiet 2>/dev/null
echo "[2/6] replay2 at $(git rev-parse --short HEAD)"

# --- Step 3: env into the clone ---
cp "$ENV_SH" scripts/env.sh; chmod 600 scripts/env.sh
echo "[3/6] env.sh -> scripts/env.sh"

# --- Step 4: full stack restore (CDP + replayd + console + supervisor ring) ---
bash scripts/reset-restore.sh
echo "[4/6] reset-restore complete"

# --- Step 5: GC daemons via canonical dfork (PPID 1, reaper-proof) ---
sleep 20
pgrep -f phantom_tab_gc.py >/dev/null 2>&1 || \
  "$VENV_PY" scripts/dfork_launch.py scripts/logs/phantom_tab_gc.out "$VENV_PY" scripts/phantom_tab_gc.py
pgrep -f homepage_tab_gc.py >/dev/null 2>&1 || \
  "$VENV_PY" scripts/dfork_launch.py scripts/logs/homepage_tab_gc.out "$VENV_PY" scripts/homepage_tab_gc.py
echo "[5/6] GC daemons armed"

# --- Step 5b: ali4 vault_guard opt-out (worklog R65 decision) ---
# replay2 >= 2fc46c9 wires ensure_vault_guard() into the supervisor. That daemon
# cures the SIBLING station's stale-Upstash-kit class — an architecture ali4 does
# not share: this station's cred source is env.sh (zero Upstash keys) and its
# off-box store is GitHub (station/ali4-worklog mirror). With no Upstash URL,
# vault_guard would sit in permanent "dead endpoint" mode and heal() would
# overwrite /home/z/.payswap-env with the ops-vault's credentials.env (dual-source
# ambiguity). Neuter it locally: kill any instance + replace with an inert stub;
# skip-worktree keeps future pulls clean. Supervised-by-5b: inert, heartbeats never.
pkill -f vault_guard.py 2>/dev/null
rm -f scripts/flags/vault_guard_heartbeat scripts/flags/vault_guard.lock
cat > scripts/vault_guard.py <<'STUB'
"""ali4 opt-out stub — this station runs the env.sh credential architecture
(no Upstash dependency; off-box store = GitHub branch mirrors). The sibling
station's ops-vault healer is not applicable here. See worklog R65. Sleeping."""
import time
while True:
    time.sleep(3600)
STUB
git update-index --skip-worktree scripts/vault_guard.py 2>/dev/null || true
echo "[5b] vault_guard neutered for ali4 (env.sh architecture)"

# --- Step 5c: watched-repo config restore (generic; the station's designated
# source-of-truth repo. §0: project designations never enter the shared repo —
# the durable copy lives in my-project/.secrets/) ---
if [ -f /home/z/my-project/.secrets/watch_repo.txt ]; then
  mkdir -p scripts/local
  cp /home/z/my-project/.secrets/watch_repo.txt scripts/local/watch_repo.txt
  echo "[5c] watched-repo config restored"
else
  echo "[5c] no watched-repo designation present"
fi

# --- Step 6: verify ---
sleep 20
GW=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3100/healthz)
FRAME=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/api/frame)
LOGIN=$(grep 'login=' scripts/watcher.log 2>/dev/null | tail -n 1 | grep -o 'login=[^ ]*')
echo "[6/6] VERIFY gw=$GW frame=$FRAME $LOGIN"
echo "[$(date -u +%FT%TZ)] ===== RECOVER.SH COMPLETE (gw=$GW frame=$FRAME) ====="
} >> "$LOG" 2>&1
