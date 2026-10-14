#!/bin/bash
# ali4 permanence rung 2 — arm the heal watchdog at every dev boot (fire-and-forget).
# Belt-and-suspenders under the mini-services auto-start rung (the platform boots
# `bun run dev` in my-project; this hook rides it). Never blocks, never fails dev.
# Detection = the watchdog's own :3040 status endpoint (cwd-based pgrep is unreliable
# for `bun index.ts` cmdline forms; the endpoint is the source of truth).

H=/home/z/my-project/mini-services/heal
[ -f "$H/index.ts" ] || exit 0
curl -s -m 3 http://127.0.0.1:3040/ 2>/dev/null | grep -q '"ali4-heal"' && exit 0

if [ -x /home/z/replay2/scripts/dfork_launch.py ] && [ -x /home/z/.venv/bin/python3 ]; then
  /home/z/.venv/bin/python3 /home/z/replay2/scripts/dfork_launch.py "$H/watchdog.out" \
    /usr/bin/env bash -c "cd $H && exec bun index.ts" >/dev/null 2>&1 &
else
  (cd "$H" && nohup bun index.ts >> "$H/watchdog.out" 2>&1 &)
fi
exit 0
