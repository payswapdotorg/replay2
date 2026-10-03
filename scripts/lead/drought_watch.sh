#!/usr/bin/env bash
# drought_watch.sh — one-shot compact drought status (live probe set from
# the sentinel state file, lanes from the registry)
echo "=== $(date -u +%H:%M:%S) UTC ==="
tail -2 /tmp/drought_sentinel.log
cd /home/z/replay2 || exit 0
timeout 45 python3 - << 'PYEOF' 2>/dev/null
import sys, json
sys.path.insert(0, "/home/z/replay2/scripts")
from chats_http import get_token, BASE
import urllib.request

tok = get_token()
st = json.load(open("/home/z/replay2/scripts/flags/drought_fresh_probes.json"))
targets = {f"PROBE-{n}": p["cid"] for n, p in st.get("probes", {}).items()}
reg = "/home/z/replay2/scripts/flags/session_registry.jsonl"
seen = {}
for line in open(reg):
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r.get("name") and r.get("url") and not r.get("action"):
        seen[r["name"]] = r["url"].split("/c/")[-1]
for n in ("T035", "T042", "T048"):
    if n in seen:
        targets[n] = seen[n]
if not targets:
    print("(no live probes; lanes only)")
for n, cid in sorted(targets.items()):
    try:
        req = urllib.request.Request(BASE + "/api/v1/chats/" + cid, headers={"Authorization": "Bearer " + tok})
        j = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        msgs = ((j.get("chat") or j).get("history") or {}).get("messages") or {}
        m = len(msgs)
        print(f"{n}: msgs={m} {'*** ADMITTED/GENERATING ***' if m >= 2 else 'queued'}")
    except Exception as e:
        print(f"{n}: probe-err {type(e).__name__}")
PYEOF
