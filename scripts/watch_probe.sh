#!/bin/bash
# watch_probe — the watched-repo scope probe (GENERIC — §0-clean, parameterized via local config).
# Reports the watched repo's state each cycle: main SHA movement + open issues +
# open PRs. Nonzero open-issues/PRs or a new SHA fires the station's
# monitor→harvest→review→approve/require-changes→dispatch-next loop.
# Config: scripts/local/watch_repo.txt (gitignored) = "owner/repo" (the station's
# designated roadmap source of truth). Durable copy: my-project/.secrets/watch_repo.txt
# (restored by recover.sh; the designation itself lives in the station worklog).
WATCH_CFG=/home/z/replay2/scripts/local/watch_repo.txt
T=$(date -u +%H:%M:%S)
REPO=""
[ -f "$WATCH_CFG" ] && REPO=$(head -n1 "$WATCH_CFG" | tr -d '[:space:]')
if [ -z "$REPO" ] && [ -f /home/z/my-project/.secrets/watch_repo.txt ]; then
  REPO=$(head -n1 /home/z/my-project/.secrets/watch_repo.txt | tr -d '[:space:]')
  mkdir -p /home/z/replay2/scripts/local && echo "$REPO" > "$WATCH_CFG"
fi
if [ -z "$REPO" ]; then echo "[$T] roadmap=NOCONFIG"; exit 0; fi
NAME=$(basename "$REPO")
DIR=/home/z/$NAME
if [ ! -d "$DIR/.git" ]; then echo "[$T] roadmap=$REPO NOLCLONE"; exit 0; fi
cd "$DIR" || { echo "[$T] roadmap=$REPO CDFAIL"; exit 0; }
# PAT resolution (durable, 2026-10-17 recycle-#23 lesson): primary legacy tier
# env.sh:PAYSWAP_PAT; fallback operator-secrets.env:GITHUB_PAT (the current tier —
# env.sh is snapshot-wiped on the platform-recycle class; both stay outside git).
PAT=""
[ -f /home/z/my-project/env.sh ] && PAT=$(grep '^export PAYSWAP_PAT=' /home/z/my-project/env.sh 2>/dev/null | cut -d= -f2)
[ -z "$PAT" ] && [ -f /home/z/my-project/operator-secrets.env ] && PAT=$(grep '^export GITHUB_PAT=' /home/z/my-project/operator-secrets.env 2>/dev/null | cut -d= -f2 | tr -d '"')
git fetch origin --quiet 2>/dev/null
LOCAL=$(git rev-parse --short HEAD 2>/dev/null)
REMOTE=$(git rev-parse --short origin/main 2>/dev/null)
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
OPEN=$(curl -s -m 10 -H "Authorization: token $PAT" "https://api.github.com/repos/$REPO/issues?state=open&per_page=30" 2>/dev/null | /home/z/.venv/bin/python3 -c "import json,sys
try:
 d=json.load(sys.stdin)
 print(len(d) if isinstance(d,list) else 'ERR')
except Exception: print('ERR')" 2>/dev/null)
PRS=$(curl -s -m 10 -H "Authorization: token $PAT" "https://api.github.com/repos/$REPO/pulls?state=open&per_page=30" 2>/dev/null | /home/z/.venv/bin/python3 -c "import json,sys
try:
 d=json.load(sys.stdin)
 print(len(d) if isinstance(d,list) else 'ERR')
except Exception: print('ERR')" 2>/dev/null)
echo "[$T] roadmap=$REPO main=$REMOTE local=$LOCAL behind=$BEHIND open-issues=$OPEN open-prs=$PRS"
