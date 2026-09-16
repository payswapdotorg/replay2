#!/bin/bash
# dep011_chain.sh — run the dep-011 landing assault as soon as the dep-014
# loop (pid given) exits, then keep the dep-001 packet assault armed behind it
# if dep-011 exhausted without landing. One create-loop at a time (lock).
cd /home/z/replay2/scripts
L=logs/dep-011_land.log
echo "[chain] waiting for dep-014 loop (pid $1) to exit $(date -u +%H:%M:%S)" >> $L
while kill -0 "$1" 2>/dev/null; do sleep 30; done
echo "[chain] dep-014 loop gone; starting dep-011 assault $(date -u +%H:%M:%S)" >> $L
python3 dep_land.py dep-011 worker-prompts/dep-011.md 75 12 >> $L 2>&1
RC=$?
echo "[chain] dep-011 assault finished rc=$RC $(date -u +%H:%M:%S)" >> $L
if [ "$RC" -ne 0 ]; then
  echo "[chain] dep-011 did not land; arming dep-001 assault $(date -u +%H:%M:%S)" >> $L
  python3 dep_land.py dep-001 worker-prompts/dep-001.md 75 12 >> logs/dep-001_land.log 2>&1
  echo "[chain] dep-001 assault finished rc=$? $(date -u +%H:%M:%S)" >> logs/dep-001_land.log
fi
