#!/usr/bin/env bash
# lane_monitor.sh — patient capacity-crunch monitor (TL, Tasks 70-73)
# w143 = the routable parked chat f474b538 (packet + 854-char stub).
# w142 = dynamic: the registry's newest live row with a /c/ url (the window_watch
# playbook registers its fresh dispatch there; the unroutable parked chat
# e74a1f5f is superseded the moment the fresh lane lands).
cd /home/z/replay2/scripts || exit 1
W143_CID="f474b538-2a8d-4a32-8456-df3b3cd5c092"
LAST_W143=854
LAST_W142=-1
while true; do
  TS=$(date -u '+%H:%M:%SZ')
  P143=$(timeout 90 python3 probe_chat.py "$W143_CID" "W143 COMPLETION REPORT" 2>/dev/null | tail -1)
  B143=$(echo "$P143" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('batch',{}).get('chars'))
except Exception: print(-1)" 2>/dev/null)
  W142_CID=$(python3 -c "
import json
rows = [json.loads(l) for l in open('flags/session_registry.jsonl') if l.strip()]
live = [r for r in rows if r.get('name')=='w142' and r.get('sent') and r.get('action') is None and '/c/' in (r.get('url') or '')]
print(live[-1]['url'].split('/c/')[-1].split('/')[0] if live else '')" 2>/dev/null)
  B142="NA"
  if [ -n "$W142_CID" ]; then
    P142=$(timeout 90 python3 probe_chat.py "$W142_CID" "W142 COMPLETION REPORT" 2>/dev/null | tail -1)
    B142=$(echo "$P142" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('batch',{}).get('chars'))
except Exception: print(-1)" 2>/dev/null)
  fi
  echo "[$TS] w143($W143_CID) batch=$B143 | w142(${W142_CID:0:8}) batch=$B142" >> logs/lane-monitor.log
  if [ "$B143" != "-1" ] && [ "$B143" != "None" ] && [ "$B143" -gt "$LAST_W143" ] 2>/dev/null; then
    echo "[$TS] *** W143 GROWTH: $LAST_W143 -> $B143 ***" >> logs/lane-monitor.log
  fi
  if [ "$B142" != "-1" ] && [ "$B142" != "None" ] && [ "$B142" != "NA" ] && [ "$B142" -gt "$LAST_W142" ] 2>/dev/null; then
    echo "[$TS] *** W142 GROWTH: $LAST_W142 -> $B142 ***" >> logs/lane-monitor.log
  fi
  [ "$B143" != "-1" ] && [ "$B143" != "None" ] && LAST_W143=$B143
  { [ "$B142" != "-1" ] && [ "$B142" != "None" ] && [ "$B142" != "NA" ]; } && LAST_W142=$B142
  sleep 300
done
