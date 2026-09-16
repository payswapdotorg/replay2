#!/bin/bash
# dep_reland_chain.sh — re-land dep-001 then dep-014 sequentially (one
# create-loop at a time via the dispatch lock; the second starts when the
# first LANDS, leaving the capacity gate to pace actual generations).
cd /home/z/replay2/scripts
echo "[chain] dep-001 assault start $(date -u +%H:%M:%S)" >> logs/dep-001_land.log
python3 dep_land.py dep-001 worker-prompts/dep-001.md 75 12 >> logs/dep-001_land.log 2>&1
RC1=$?
echo "[chain] dep-001 assault rc=$RC1 $(date -u +%H:%M:%S)" >> logs/dep-001_land.log
echo "[chain] dep-014 assault start $(date -u +%H:%M:%S)" >> logs/dep-014_land.log
python3 dep_land.py dep-014 worker-prompts/dep-014.md 75 12 >> logs/dep-014_land.log 2>&1
RC2=$?
echo "[chain] dep-014 assault rc=$RC2 $(date -u +%H:%M:%S)" >> logs/dep-014_land.log
