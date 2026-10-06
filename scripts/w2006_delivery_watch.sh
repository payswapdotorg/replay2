#!/usr/bin/env bash
# w2006_delivery_watch.sh — TL watcher for the W2-006 re-delivery round.
# Every 120s: (1) remote branch check (work/w2-006), (2) workspace allocation,
# (3) chat freshness. Logs transitions to flags/w2006_watch.log.
cd /home/z/replay2/scripts
CHAT=6820320a-df72-4f63-ad08-c76f65ce1972
LOG=flags/w2006_watch.log
declare -A SEEN
while true; do
  TS=$(date -u +%H:%M:%SZ)
  # 1. remote branch
  BR=$(cd /home/z/UniCom && git ls-remote origin refs/heads/work/w2-006 2>/dev/null | awk '{print $1}')
  if [ -n "$BR" ] && [ -z "${SEEN[branch]:-}" ]; then
    echo "$TS BRANCH-LANDED work/w2-006 @ ${BR:0:7}" >> $LOG
    SEEN[branch]=1
  fi
  # 2. workspace count
  WST=$(python3 check_workspaces.py 2>/dev/null | python3 -c "import json,sys,re; m=re.search(r'\"total\": (\d+)', sys.stdin.read()); print(m.group(1) if m else '?')" 2>/dev/null)
  # 3. chat updated_at
  UA=$(python3 chats_http.py detail $CHAT 2>/dev/null | grep updated_at | awk '{print $2}')
  echo "$TS ws_total=$WST chat_updated=$UA branch=${BR:0:7}" >> flags/w2006_watch.tick
  # 4. workspace appeared transition
  if [ "$WST" != "0" ] && [ -n "$WST" ] && [ "$WST" != "?" ] && [ -z "${SEEN[ws]:-}" ]; then
    echo "$TS WORKSPACE-ALLOCATED (pool $WST/3) — worker spawning" >> $LOG
    SEEN[ws]=1
  fi
  # exit when branch is on the remote
  if [ -n "$BR" ]; then
    echo "$TS EXIT — delivery on remote, TL harvest can begin" >> $LOG
    exit 0
  fi
  sleep 120
done
