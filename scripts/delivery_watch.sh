#!/bin/bash
# delivery_watch.sh — poll GitHub for wave delivery branches
# The PAT comes from the environment (scripts/env.sh is gitignored) — NEVER
# embed credentials in committed files (GitHub push protection will block).
[ -f "$(dirname "$0")/env.sh" ] && . "$(dirname "$0")/env.sh"
while true; do
  {
    for b in w125-company-coverage w125-company-coverage-2 w126-company-query w131-execution-contracts w132-provider-fabric w133-agent-body w134-info-strategy w135-organizational-lab w136-agent-exchange w137-execution-fabric w138-emergent-roles w139-cross-platform w140-closed-loop; do
      sha=$(git ls-remote --heads "https://${PAYSWAP_GITHUB_PAT:-$PAT}@github.com/payswapdotorg/aurum-chat.git" "work/$b" 2>/dev/null | awk '{print $1}')
      if [ -n "$sha" ]; then
        echo "[$(date -u +%H:%M:%SZ)] DELIVERY: work/$b @ ${sha:0:10}"
      fi
    done
  } >> /home/z/replay2/scripts/logs/delivery-watch.log 2>&1
  sleep 300
done
