#!/usr/bin/env bash
# wave_status.sh — one-glance snapshot of the live worker wave.
# Usage: bash scripts/wave_status.sh [lines-per-log]
N="${1:-4}"
echo "=== $(date -u '+%H:%M:%S') UTC ==="
echo "--- env (last 2):"; tail -2 /tmp/env_probe.log 2>/dev/null
echo "--- live watchers:"; ps aux | rg '[q]ueue_watch' | rg -o 'queue_watch.py [a-z0-9.-]+ [A-Z0-9]+' || echo 'NONE'
echo "--- watcher specs:"; ls /home/z/replay2/scripts/flags/ 2>/dev/null | rg 'queue_watch\.spec\.' || echo 'NONE'
echo "--- registry (last 3):"; tail -3 /home/z/replay2/scripts/flags/session_registry.jsonl 2>/dev/null | cut -c1-160
for f in /tmp/queue_watch_val-014-voice-4.log /tmp/queue_watch_val-016-videogen-2.log; do
  if [ -f "$f" ]; then echo "--- $(basename "$f") (last $N):"; tail -"$N" "$f"; fi
done
if [ -f /home/z/replay2/scripts/logs/create_val-014-voice-4.log ]; then
  echo "--- create_val-014-voice-4.log (last $N):"; tail -"$N" /home/z/replay2/scripts/logs/create_val-014-voice-4.log
fi
echo "--- operator_inbox:"; tail -3 /home/z/replay2/scripts/flags/operator_inbox.jsonl 2>/dev/null || echo '(no operator messages yet)'
