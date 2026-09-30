#!/bin/bash
# lead_status.sh — compact resident Lead status line (safe, read-only)
date -u +"%H:%M:%S UTC"
echo -n "  inbox-lines: "
wc -l < /home/z/replay2/scripts/flags/operator_inbox.jsonl
echo -n "  val014-tab: "
curl -s -m 5 http://localhost:9222/json/list | /home/z/.venv/bin/python3 -c "import json,sys; tabs=json.load(sys.stdin); t=[x for x in tabs if '6a6c6504' in (x.get('url') or '')]; print(t[0]['url'][:70] if t else 'LOST')" 2>/dev/null || echo "CDP-ERR"
echo -n "  egress: "
tail -1 /tmp/browser_egress.log
echo -n "  replayd: "
curl -s -m 5 http://localhost:3100/healthz | head -c 60
echo
echo -n "  watcher-hb: "
stat -c '%y' /home/z/replay2/scripts/flags/watcher_heartbeat 2>/dev/null | cut -c12-19
