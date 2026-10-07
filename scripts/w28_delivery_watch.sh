#!/usr/bin/env bash
# w28_delivery_watch.sh — TL watcher for the TradRL W-28 (lane B) delivery.
# Oracle: branch work/W28-neon-ddl-runbook-b on payswapdotorg/TradRL (git is
# the gold standard), with workspace + chat freshness ticks for diagnosis.
# Exits the moment the branch is on the remote (TL harvest can begin).
cd /home/z/replay2/scripts
CHAT=57530af9-0c99-40af-9a07-a4ef5adb2ff1
LOG=flags/w28_watch.log
declare -A SEEN
while true; do
  TS=$(date -u +%H:%M:%SZ)
  # 1. remote branch (the delivery oracle)
  BR=$(cd /home/z/TradRL && git ls-remote origin refs/heads/work/W28-neon-ddl-runbook-b 2>/dev/null | awk '{print $1}')
  if [ -n "$BR" ] && [ -z "${SEEN[branch]:-}" ]; then
    echo "$TS BRANCH-LANDED work/W28-neon-ddl-runbook-b @ ${BR:0:7}" >> $LOG
    SEEN[branch]=1
  fi
  # 2. workspace pool count
  WST=$(python3 check_workspaces.py 2>/dev/null | python3 -c "import json,sys,re; m=re.search(r'\"total\": (\d+)', sys.stdin.read()); print(m.group(1) if m else '?')" 2>/dev/null)
  # 3. chat updated_at (freshness: generation moves it)
  UA=$(python3 chats_http.py detail $CHAT 2>/dev/null | grep updated_at | awk '{print $2}')
  echo "$TS ws_total=$WST chat_updated=$UA branch=${BR:0:7}" >> flags/w28_watch.tick
  # 4. stall flag: branch absent AND chat frozen >90 min since watch start
  if [ -n "$BR" ]; then
    echo "$TS EXIT — delivery on remote, TL harvest can begin" >> $LOG
    exit 0
  fi
  sleep 120
done
