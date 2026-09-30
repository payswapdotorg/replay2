#!/bin/bash
# watchdog v3: re-invoke the single-shot fighter every 200s; the fighter's
# own lock prevents overlap. Nothing needs to stay resident except this
# cheap sleep-loop.
while true; do
  python3 /home/z/replay2/scripts/reap_fight.py >> /home/z/replay2/scripts/logs/reap_fight_console.log 2>&1
  echo "[$(date -u +%H:%M:%S)] fighter rc=$? — next tick in 200s" >> /home/z/replay2/scripts/logs/reap_fight_watchdog.log
  sleep 200
done
