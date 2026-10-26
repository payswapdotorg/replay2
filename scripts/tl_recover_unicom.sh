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
  # 2026-10-23 (product-UI review, operator directive): the platform app
  # ("UNiCOM — Multi-Store Command Center") is a valid console identity —
  # it has no /api/status route, the title alone carries the identity.
  local title
  title=$(curl -sf --max-time 5 http://127.0.0.1:3000/ 2>/dev/null | grep -o "<title>[^<]*</title>" || true)
  if [[ "$title" == *"UNiCOM"* ]]; then
    curl -sf --max-time 5 http://127.0.0.1:3100/healthz >/dev/null 2>&1 || return 1
    return 0
  fi
  curl -sf --max-time 5 http://127.0.0.1:3000/api/status >/dev/null 2>&1 || return 1
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
# 2026-10-13 recovery #12: the clone is public (no PAT needed) but the remote
# URL stays anonymous — post-recovery PUSHES fail until this is set (the
# durability law's push step silently breaks otherwise). Same pattern as the
# UniCom/TradRL/Fleetos PAT remotes below.
_PATVAL="${GITHUB_PAT:-${PAYSWAP_PAT:-}}"
if [[ -n "$_PATVAL" ]] && [[ -d "$REPLAY2/.git" ]]; then
  (cd "$REPLAY2" && git remote set-url origin "https://x-access-token:${_PATVAL}@github.com/payswapdotorg/replay2.git" >/dev/null 2>&1)
  log "replay2 PAT remote set (push-ready)"
fi

# 3. FLAGS FIRST — before ANY :3000 eviction (binding operator directive
#    2026-10-01 16:45Z: else the ring resurrects the platform scaffold app)
#    2026-10-23 (product-UI review, operator directive): preserve a DELIBERATE
#    launcher choice — only seed the default when the flag is absent.
mkdir -p "$REPLAY2/scripts/flags" "$REPLAY2/scripts/logs" "$REPLAY2/scripts/worker-prompts"
# 2026-10-24 FE era: the platform app (my-project, "UNiCOM — Commerce
# Console") is THE operator console on :3000 (the 2026-09-30 architecture;
# the 2026-10-24 frontend directive makes it real again after the recycle
# restored the pristine scaffold). Default-seed launch_console.py; the
# replay2-native console (launch_dev.py) is a side service on :3200.
# Preserve deliberate flag choices (the step-2 git clean may wipe them).
[ -f "$REPLAY2/scripts/flags/console_launcher.txt" ] \
  || printf 'launch_console.py' > "$REPLAY2/scripts/flags/console_launcher.txt"
[ -f "$REPLAY2/scripts/flags/console_port.txt" ] \
  || printf '3000' > "$REPLAY2/scripts/flags/console_port.txt"
# 2026-10-26: the replay console side-service port (watcher.py heals it;
# delete this flag to retire the side service).
[ -f "$REPLAY2/scripts/flags/console_side_port.txt" ] \
  || printf '3200' > "$REPLAY2/scripts/flags/console_side_port.txt"

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

# 4a-2. UNICOM WATCH-MACHINE STATE RESTORE (recycles #24/#25 lesson,
#     2026-10-16: the runtime-only artifacts — lane_list, the rebuilt
#     watcher scripts, the operator thread — were wipe-vulnerable and the
#     sentinel's auto-recovery went BLIND to w3-024 again; this section
#     restores all of them from the durable kit on EVERY recycle.)
# (a) lane_list — the sentinel's lane visibility (the 00:08Z root cause:
#     lane_names() fell back to legacy lanes and the recover would have
#     re-dispatched NOTHING on the next admission window)
if [[ -s "$DURABLE_DIR/lane_list.txt" ]]; then
  cp "$DURABLE_DIR/lane_list.txt" "$REPLAY2/scripts/flags/lane_list.txt"
  log "lane_list restored ($(tr '\n' ' ' < "$DURABLE_DIR/lane_list.txt"))"
else
  log "lane_list MISSING in durable kit — LOUD DEFAULT: writing w3-024"
  printf 'w3-024\n' > "$REPLAY2/scripts/flags/lane_list.txt"
fi
# (b) the rebuilt watcher scripts (vpn_heal.py + window_catcher.py were
#     runtime-only creations wiped by the re-clone; durable copies live in
#     download/recovery/scripts/)
if [[ -d "$DURABLE_DIR/scripts" ]]; then
  n_scripts=0
  for f in "$DURABLE_DIR"/scripts/*.py; do
    [[ -f "$f" ]] || continue
    cp "$f" "$REPLAY2/scripts/$(basename "$f")"
    chmod +x "$REPLAY2/scripts/$(basename "$f")"
    n_scripts=$((n_scripts+1))
  done
  [[ $n_scripts -gt 0 ]] && log "watcher scripts restored ($n_scripts)"
fi
# (c) the operator thread (agent_outbox) — IDEMPOTENT seed merge (never
#     overwrite: the runtime outbox may carry messages newer than the seed)
if [[ -f "$DURABLE_DIR/agent_outbox.seed.jsonl" ]]; then
  python3 - "$DURABLE_DIR/agent_outbox.seed.jsonl" "$REPLAY2/scripts/flags/agent_outbox.jsonl" << 'OUTBOXEOF'
import json, os, sys
seed_path, out_path = sys.argv[1], sys.argv[2]
have = set()
if os.path.exists(out_path):
    for l in open(out_path):
        try:
            have.add((json.loads(l).get("ts"), json.loads(l).get("text", "")[:80]))
        except Exception:
            pass
added = 0
with open(out_path, "a") as f:
    for l in open(seed_path):
        try:
            d = json.loads(l)
        except Exception:
            continue
        if (d.get("ts"), d.get("text", "")[:80]) not in have:
            f.write(l if l.endswith("\n") else l + "\n")
            added += 1
print(f"outbox seed: {added} messages appended")
OUTBOXEOF
  log "operator thread restored (idempotent)"
fi
# (d) the staged W3-024 dispatch packet (recycle #26 lesson, 2026-10-16:
#     the 14:11Z re-clone wiped flags/pkt_w3-024_staged.md — the sentinel's
#     D-033 resolution order found NOTHING and the auto-dispatch chain went
#     BLIND; the packet is re-derivable but every re-derivation is 30+ min
#     of TL surgery while an admission window can open+close in 90s.
#     Durable kit copy: recovery/packets/pkt_w3-024_staged.md. Restored
#     ONLY when the runtime copy is absent — never downgrades a newer
#     staged packet.)
if [[ -f "$DURABLE_DIR/packets/pkt_w3-024_staged.md" ]] && [[ ! -s "$REPLAY2/scripts/flags/pkt_w3-024_staged.md" ]]; then
  cp "$DURABLE_DIR/packets/pkt_w3-024_staged.md" "$REPLAY2/scripts/flags/pkt_w3-024_staged.md"
  chmod 600 "$REPLAY2/scripts/flags/pkt_w3-024_staged.md" 2>/dev/null
  log "W3-024 staged packet restored from durable kit ($(wc -c < "$REPLAY2/scripts/flags/pkt_w3-024_staged.md") bytes)"
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

# 4d. w2-028 lane-history materialization (recycle #14 lesson, 2026-10-14
#     ~11:51Z: the lane was dispatched 06:05Z in Task 8-8 but its registry
#     records lived only in the then-live clone — never committed here — so
#     the recycle erased the tier-a-freshness lane from the workers strip.
#     The worker itself survived server-side and DELIVERED (work/w2-028 @
#     3c468ee). Lane retired 2026-10-14 12:2xZ: TL-reviewed + merged 6c5114b
#     + closeout 16bd468 + issue #21 closed 12:19:55Z. Doctrine: EVERY
#     retired lane gets its trio in this script AT RETIREMENT TIME.)
if ! grep -q '"name": "w2-028", "action": "done"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "w2-028", "action": "create", "ts": 1791957900, "prompt_file": "/home/z/replay2/scripts/worker-prompts/w2-028.md", "tab_id": ""}
{"name": "w2-028", "action": "send", "ts": 1791957960, "url": "https://chat.z.ai/c/b95096c1-aa8b-4325-bd34-345df5cf13bb", "sent": true}
{"name": "w2-028", "action": "done", "ts": 1791980463}
LANEEOF
  log "w2-028 lane history materialized"
fi
[[ -f "$REPLAY2/scripts/flags/w2-028-complete.marker" ]] || \
  { touch "$REPLAY2/scripts/flags/w2-028-complete.marker"; log "w2-028 complete marker materialized"; }
if [[ ! -s "$REPLAY2/scripts/worker-prompts/w2-028.md" ]]; then
  cat > "$REPLAY2/scripts/worker-prompts/w2-028.md" << 'PROMPTEOF'
# W2-028 — the Tier A Freshness Verification at 8aae797 (the v2 RC inheritance currency)

> [recovery #14 provenance, 2026-10-14] The original dispatch prompt (the
> 9,229-char work-order-verbatim + operational contract, dispatched from
> inside the replay 2026-10-14T06:05Z) was lost to the pod recycle of
> 2026-10-14 ~11:51Z (worker-prompts is wipe-vulnerable). This stub
> preserves the H1 — the console's live-Workers title derivation reads
> line 1. The work order itself survives verbatim in-repo:
> payswapdotorg/UniCom docs/work-orders/W2-028.md (the completion report at
> docs/work-orders/reports/W2-028-completion-report.md). The lane is RETIRED:
> delivered (branch work/w2-028 @ 3c468ee) + TL-reviewed (every gate
> independently re-run — all matched) + merged 6c5114b (--no-ff, the TL
> battery in the message) + closeout 16bd468; issue #21 closed 12:19:55Z.
> Chat ground truth: b95096c1-aa8b-4325-bd34-345df5cf13bb, title "Tier A
> Freshness Verification W2-028", dispatched 06:05Z; the worker sandbox
> survived the pod recycle (server-side) and pushed the branch.
PROMPTEOF
  log "w2-028 prompt stub materialized"
fi

# 4e. w1-026 lane-history materialization (recycle #23 lesson, 2026-10-15:
#     the lane retired 19:27:55Z Oct 14 [merged a3e135d, TL battery 413/413 +
#     browser 8/8] but its trio was never added HERE — the recycle erased the
#     Issue #22 product-home lane from the workers strip. Doctrine: EVERY
#     retired lane gets its trio in this script AT RETIREMENT TIME.)
if ! grep -q '"name": "w1-026", "action": "done"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "w1-026", "action": "create", "ts": 1791995486, "prompt_file": "/home/z/replay2/scripts/worker-prompts/w1-026.md", "tab_id": ""}
{"name": "w1-026", "action": "send", "ts": 1791995546, "url": "https://chat.z.ai/c/b328e018-104d-4427-8fce-4fac6c047808", "sent": true}
{"name": "w1-026", "action": "done", "ts": 1792006075}
LANEEOF
  log "w1-026 lane history materialized"
fi
[[ -f "$REPLAY2/scripts/flags/w1-026-complete.marker" ]] || \
  { touch "$REPLAY2/scripts/flags/w1-026-complete.marker"; log "w1-026 complete marker materialized"; }
[[ -s "$REPLAY2/scripts/worker-prompts/w1-026.md" ]] || \
  { printf '# W1-026 — UNiCOM Product Home and Buyer/Merchant First Journeys\n\n> [recycle #23 provenance, 2026-10-15] Stub — the work order survives verbatim in-repo: payswapdotorg/UniCom docs/work-orders/W1-026.md. Lane RETIRED: merged a3e135d 19:27:55Z Oct 14 (TL: battery 413/413, browser 8/8). Session b328e018.\n' > "$REPLAY2/scripts/worker-prompts/w1-026.md"; log "w1-026 prompt stub materialized"; }

# 4f. w2-029 lane-history materialization (recycle #23 lesson, same class:
#     retired 19:56:36Z Oct 14 [merged e440cd1, TL battery 414/414 + browser
#     9/9]; trio added here per the doctrine.)
if ! grep -q '"name": "w2-029", "action": "done"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "w2-029", "action": "create", "ts": 1791995983, "prompt_file": "/home/z/replay2/scripts/worker-prompts/w2-029.md", "tab_id": ""}
{"name": "w2-029", "action": "send", "ts": 1791996043, "url": "https://chat.z.ai/c/5d0e428b-78e7-4372-a212-80afa6617ffb", "sent": true}
{"name": "w2-029", "action": "done", "ts": 1792007796}
LANEEOF
  log "w2-029 lane history materialized"
fi
[[ -f "$REPLAY2/scripts/flags/w2-029-complete.marker" ]] || \
  { touch "$REPLAY2/scripts/flags/w2-029-complete.marker"; log "w2-029 complete marker materialized"; }
[[ -s "$REPLAY2/scripts/worker-prompts/w2-029.md" ]] || \
  { printf '# W2-029 — Main-Agent, Autonomy, Decisions and Trust UX\n\n> [recycle #23 provenance, 2026-10-15] Stub — the work order survives verbatim in-repo: payswapdotorg/UniCom docs/work-orders/W2-029.md. Lane RETIRED: merged e440cd1 19:56:36Z Oct 14 (TL: battery 414/414, browser 9/9). Session 5d0e428b.\n' > "$REPLAY2/scripts/worker-prompts/w2-029.md"; log "w2-029 prompt stub materialized"; }

# 4g. w3-024 LIVE-row materialization (the lane is IN FLIGHT — round-5
#     session 82290725 (round-7, the real 13,812-char packet) dispatched 10:08:38Z Oct 15.
#     NO complete marker, NO done row. The any-row guard means a later
#     round-6+ re-dispatch (the ladder appends its own rows) suppresses this
#     materialization automatically.)
if ! grep -q '"name": "w3-024"' "$REPLAY2/scripts/flags/session_registry.jsonl" 2>/dev/null; then
  cat >> "$REPLAY2/scripts/flags/session_registry.jsonl" << 'LANEEOF'
{"name": "w3-024", "action": "create", "ts": 1792058918, "prompt_file": "/home/z/replay2/scripts/worker-prompts/w3-024.md", "tab_id": ""}
{"name": "w3-024", "action": "send", "ts": 1792058918, "url": "https://chat.z.ai/c/82290725-b4a5-4034-a708-b31dcddf37b5", "sent": true}
LANEEOF
  log "w3-024 live rows materialized"
fi
[[ -s "$REPLAY2/scripts/worker-prompts/w3-024.md" ]] || \
  { printf '# W3-024 — Default Web + Ubuntu Desktop UNiCOM Launch Experience\n\n> [recycle #23 provenance, 2026-10-15] Stub — the work order survives verbatim in-repo: payswapdotorg/UniCom docs/work-orders/W3-024.md. Lane LIVE (round-7, session 82290725 — the real packet pkt_w3-024_staged.md; round-5 a096556f + round-6 stub both voided 2026-10-15, zero work lost). Branch work/w3-024, base 82d2d68.\n' > "$REPLAY2/scripts/worker-prompts/w3-024.md"; log "w3-024 prompt stub materialized"; }

# 4h. STATION DESIGNATION enforcement (the R23 cross-station clobber class,
#     2026-10-15 09:2xZ: recycle #23's vault heal restored the ops-vault
#     HOME-STATION designation (aurum-chat) onto THIS box because the
#     designation files were absent — the console board then drift-healed to
#     the aurum mirror key and rendered AURUM content on the UniCom console.
#     Doctrine: THIS station is the UniCom TL station; the designation files
#     are PRESENT durably so the vault heal (absent/empty restore path) never
#     fires, and this step re-asserts them idempotently at every recovery.)
printf 'payswapdotorg/UniCom' > "$DURABLE_DIR/watch_repo.txt"
printf '# Station designation (durable kit — present files are never restored by the vault heal)\n# This station: the UniCom TL station. The vault home-station default (aurum-chat) is NOT this station.\npayswapdotorg/UniCom\npayswapdotorg/replay2\n' > "$DURABLE_DIR/repos.txt"
mkdir -p "$REPLAY2/scripts/flags" && printf 'payswapdotorg/UniCom' > "$REPLAY2/scripts/flags/watch_repo.txt"
if [[ -f "$HOME/.secrets/env.sh" ]] && grep -q '^REPO=payswapdotorg/aurum-chat$' "$HOME/.secrets/env.sh" 2>/dev/null; then
  sed -i 's|^REPO=payswapdotorg/aurum-chat$|REPO=payswapdotorg/UniCom|' "$HOME/.secrets/env.sh"
  log "relay REPO re-pointed aurum-chat -> UniCom (station designation)"
fi
log "station designation enforced (UniCom)"

# 4.5 platform console tree — FE era durability (2026-10-26). After a pod
# recycle the durable volume may restore my-project as the PRISTINE SCAFFOLD
# (observed live 2026-10-26: the boot found a scaffold, honored the station's
# launch_dev.py flag, and put the replay console on :3000 while the
# operator's product existed only off-box). The product tree's durable home
# is payswapdotorg/unicom-live (the off-box copy, 587d928+). When the
# my-project tree is NOT the console (marker file absent), restore it BEFORE
# the deploy so launch_console.py starts the real console. Station-durable
# files (.git .zscripts download db mini-services browser-profile .env
# dev.log) are never touched; the local worklog is backed up before the
# product worklog lands.
if [ ! -f /home/z/my-project/src/lib/product/store.ts ]; then
  log "my-project is not the console tree — restoring from unicom-live"
  _UL=/home/z/unicom-live
  if [ ! -d "$_UL/.git" ]; then
    git clone --quiet "https://x-access-token:${_PATVAL}@github.com/payswapdotorg/unicom-live.git" "$_UL" \
      && log "unicom-live cloned @ $(git -C "$_UL" rev-parse --short HEAD)" \
      || log "FATAL: unicom-live clone failed — console tree not restored"
  else
    git -C "$_UL" remote set-url origin "https://x-access-token:${_PATVAL}@github.com/payswapdotorg/unicom-live.git" >/dev/null 2>&1 || true
    git -C "$_UL" fetch --quiet origin \
      && git -C "$_UL" reset --quiet --hard origin/main \
      && log "unicom-live refreshed @ $(git -C "$_UL" rev-parse --short HEAD)" \
      || log "WARN: unicom-live refresh failed — trying existing tree"
  fi
  if [ -d "$_UL/.git" ] && [ -f "$_UL/src/lib/product/store.ts" ]; then
    if [ -f /home/z/my-project/worklog.md ]; then
      cp /home/z/my-project/worklog.md \
        "/home/z/my-project/worklog.pre-restore.$(date -u +%Y%m%dT%H%M%SZ).md"
    fi
    rsync -a --delete "$_UL/src/"     /home/z/my-project/src/
    rsync -a --delete "$_UL/public/"  /home/z/my-project/public/
    rsync -a "$_UL/agent-ctx/"    /home/z/my-project/agent-ctx/    2>/dev/null || true
    rsync -a "$_UL/tool-results/" /home/z/my-project/tool-results/ 2>/dev/null || true
    cp "$_UL/package.json" "$_UL/bun.lock" "$_UL/components.json" /home/z/my-project/ 2>/dev/null || true
    cp "$_UL/prisma/schema.prisma" /home/z/my-project/prisma/schema.prisma
    cp "$_UL/worklog.md" /home/z/my-project/worklog.md
    rm -rf /home/z/my-project/.next /home/z/my-project/db/custom.db
    (cd /home/z/my-project \
      && bun install >> "$LOG" 2>&1 \
      && bunx prisma generate >> "$LOG" 2>&1 \
      && bunx prisma db push --accept-data-loss >> "$LOG" 2>&1 \
      && log "console tree restored: deps installed + db pushed") \
      || log "WARN: console tree restore install/db step failed — check $LOG"
  fi
fi

# 5. deploy (only if unhealthy — idempotent)
if stack_healthy; then
  log "replay stack already healthy — skipping deploy"
else
  log "deploying replay stack (flags-first canonical path)…"
  # 2026-10-23: honor the launcher flag (product-UI review may hold
  # launch_console.py — the platform app is the console then)
  # 2026-10-24 FE era: pass REPLAY_PORT from the console_port flag so the
  # deploy's console section targets the right port explicitly.
  _CL=$(cat "$REPLAY2/scripts/flags/console_launcher.txt" 2>/dev/null || echo launch_console.py)
  _CP=$(cat "$REPLAY2/scripts/flags/console_port.txt" 2>/dev/null || echo 3000)
  (cd "$REPLAY2" && CONSOLE_LAUNCHER="scripts/$_CL" REPLAY_PORT="$_CP" bash deploy.sh >> "$LOG" 2>&1)
  if stack_healthy; then log "deploy OK — stack healthy"; else log "WARN: stack health check failed post-deploy — check $LOG"; fi
fi

# 6. login keeper (auto-restores ali26 from the durable token — no operator
#    login needed; snapshots the token every 20 min once logged in)
# 2026-10-13 recycle #11 (parallel station's eb46e76): system python3 on a
# fresh pod lacks websocket-client (ModuleNotFoundError kills the keepers) —
# prefer the venv python (/home/z/.venv, provisioned from pyproject.toml).
# 2026-10-14 recycle #14: the SAME class hit lane_watch_unicom (channel.py →
# websocket) — hoisted here so BOTH keepers resolve it.
_KEEPER_PY="$( [[ -x /home/z/.venv/bin/python3 ]] && echo /home/z/.venv/bin/python3 || echo python3 )"
if keeper_running login_keeper.py; then
  log "login_keeper already live"
else
  (cd "$REPLAY2/scripts" && "$_KEEPER_PY" dfork_launch.py logs/login_keeper.log "$_KEEPER_PY" login_keeper.py)
  log "login_keeper launched (dfork'd, py=$_KEEPER_PY)"
fi

# 7. lane watcher (console strip: server-side lane probes every 120s)
if keeper_running lane_watch_unicom.py; then
  log "lane_watch already live"
else
  (cd "$REPLAY2/scripts" && "$_KEEPER_PY" dfork_launch.py logs/lane_watch_unicom.log "$_KEEPER_PY" lane_watch_unicom.py)
  log "lane_watch_unicom launched (dfork'd, py=$_KEEPER_PY)"
fi

# 8. UniCom clone + PAT remote + pnpm
if [[ ! -d "$UNICOM/.git" ]]; then
  git clone --quiet "https://github.com/payswapdotorg/UniCom.git" "$UNICOM" \
    && log "UniCom cloned @ $(cd "$UNICOM" && git rev-parse --short HEAD)" \
    || log "WARN: UniCom clone failed"
else
  (cd "$UNICOM" && git fetch --quiet origin && log "UniCom refreshed (main @ $(git rev-parse --short origin/main))")
fi
_PATVAL="${GITHUB_PAT:-${PAYSWAP_PAT:-}}"
if [[ -n "$_PATVAL" ]] && [[ -d "$UNICOM/.git" ]]; then
  (cd "$UNICOM" && git remote set-url origin "https://x-access-token:${_PATVAL}@github.com/payswapdotorg/UniCom.git" >/dev/null 2>&1)
  log "UniCom PAT remote set"
fi
command -v pnpm >/dev/null 2>&1 || corepack prepare pnpm@10.33.2 --activate >/dev/null 2>&1
# 2026-10-13 recycle #11 (eb46e76): corepack shims land outside PATH on fresh
# pods — npm -g is the reliable fallback (the recorded #9 doctrine).
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@10.33.2 >/dev/null 2>&1
log "pnpm: $(pnpm --version 2>/dev/null || echo MISSING)"

log "=== TL recover done ==="
exit 0
