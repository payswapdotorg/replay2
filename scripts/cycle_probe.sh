#!/bin/bash
# Compact station health probe for resident watch cycles (recycle-proof: PID-agnostic)
T=$(date -u +%H:%M:%S)
GW=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3100/healthz)
CORE=$(ss -ltn 2>/dev/null | grep -c ':3110')
CDP=$(curl -s -m 5 http://127.0.0.1:9222/json/version 2>/dev/null | head -c 1)
FRAME=$(curl -s -m 5 -o /dev/null -w '%{http_code}:%{size_download}' http://127.0.0.1:3000/api/frame)
INBOX=$(curl -s -m 5 http://127.0.0.1:3000/api/inbox 2>/dev/null | head -c 60)
HB=$(find /home/z/replay2/scripts/flags -name "*_heartbeat" -mmin -10 2>/dev/null | wc -l)
LOGIN=$(grep 'login=' /home/z/replay2/scripts/watcher.log 2>/dev/null | tail -n 1 | grep -o 'login=[^ ]*')
GC=$(pgrep -fc "tab_gc.py" 2>/dev/null)
RING=$(pgrep -fc "supervisor.py|watcher.py" 2>/dev/null)
ERR=$(tail -n 200 /home/z/my-project/dev.log 2>/dev/null | grep -icE "error|fatal")
echo "[$T] gw=$GW core=$CORE cdp=$CDP frame=$FRAME ring=$RING hb=$HB/5 $LOGIN gc=$GC inbox=$INBOX err=$ERR"
