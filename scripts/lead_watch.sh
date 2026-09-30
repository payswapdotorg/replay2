#!/bin/bash
date -u +"%H:%M:%S UTC"
echo -n "  inbox: "; wc -l < /home/z/replay2/scripts/flags/operator_inbox.jsonl
echo -n "  egress: "; tail -1 /tmp/browser_egress.log | sed 's/2026-09-12 //'
echo -n "  replayd: "; curl -s -m 5 http://localhost:3100/healthz | head -c 42; echo
/home/z/.venv/bin/python3 /home/z/replay2/scripts/lead_watch_workers.py
