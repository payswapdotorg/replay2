#!/bin/bash
# lead_monitor.sh — one compact orchestrator status line per call
R=/home/z/replay2
ST=$(curl -s --max-time 8 http://localhost:3000/api/status 2>/dev/null | python3 -c "
import json,sys
try:
  d=json.load(sys.stdin); print(d.get('browser_login','?'))
except: print('status-ERR')")
FR=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://localhost:3000/api/frame 2>/dev/null)
DW=$(pgrep -f dispatch_wave3.py >/dev/null && echo armed || echo DOWN)
RING=""
for p in watcher.py stall_recovery.py custodian.py frame_guard.py replayd.py; do
  pgrep -f "$p" >/dev/null && RING="$RING+"
done
CH=$(pgrep -f "remote-debugging-port=9222" >/dev/null && echo up || echo DOWN)
NEWMSG=$(wc -l < $R/scripts/flags/operator_inbox.jsonl 2>/dev/null || echo 0)
echo "login=$ST | frame=$FR | dispatch=$DW | ring=${#RING}/5 | chrome=$CH | op_msgs=$NEWMSG | $(date -u +%H:%M:%S)"
