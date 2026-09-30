#!/usr/bin/env python3
"""lane_status.py — deep status for the wave-22 lanes: server-side chat record
(message counts, updated_at) + tab state (capacity modal?)."""
import json, sys, time, urllib.request
sys.path.insert(0, "/home/z/replay2/scripts")

TOKEN = open("/home/z/replay2/scripts/flags/chat_token").read().strip()
LANES = {"T024": "1f67d986-3159-430e-9c94-1a636ef1859a",
         "T030": "ee463202-5f10-425e-9c18-56693c42a7bf",
         "T040": "66a92d9d-7e12-43ba-a0d9-c3bdbb97752d"}

def api(path):
    req = urllib.request.Request("https://chat.z.ai" + path)
    req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

for name, cid in LANES.items():
    try:
        d = api("/api/v1/chats/" + cid)
        msgs = d.get("messages", [])
        roles = [m.get("role") for m in msgs]
        print("%s: http-200 | msgs=%d roles=%s | updated=%s | title=%r"
              % (name, len(msgs), roles[:6], d.get("updatedAt", d.get("updated_at", "?")), (d.get("title") or "")[:40]))
    except urllib.error.HTTPError as e:
        print("%s: HTTP %d" % (name, e.code))
    except Exception as e:
        print("%s: ERR %s" % (name, e))
    time.sleep(0.4)
