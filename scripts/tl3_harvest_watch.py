#!/usr/bin/env python3
"""tl3_harvest_watch.py — auto-harvest the TL3-P2 re-deliveries.

Watches the LAST assistant narrative of each partition chat; when its batch
payload stops growing (3 consecutive stable polls, size > 50K = real work
happened), finds the chat's live workspace, ls-trees it and fetches the
delivery files to /home/z/my-project/replay-artifacts/harvest/<name>/.
Exits when all three partitions are harvested (or 5h horizon).

Partitions:
  A: 5ba77f28 (duplicate RE-ENTRY turn already running; ws bound at harvest)
  B: 6a554aab (re-entry keeper lands the directive; fresh pod rebinds)
  C: 3aaa6b2a (same)
"""
import json
import os
import sys
import time
import urllib.request

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
OUT = "/home/z/my-project/replay-artifacts/harvest"
LOG = open(os.path.join(BASE, "logs", "tl3_harvest_watch.log"), "a", buffering=1)
HORIZON_S = 5 * 3600
POLL_S = 120
STABLE_N = 3
MIN_SIZE = 50000

PARTITIONS = [
    ("tl3-pa", "c4aa3f08-264d-4d45-a627-16104b5b44ca"),
    ("tl3-pb", "6a554aab-53b2-4d1e-addb-8a32b5ee2ed5"),
    ("tl3-pc", "3aaa6b2a-b165-4475-98e2-7579cb5cba4f"),
]

WANT_EXACT = ["findings.md", "delivery.patch", "baseline.txt", "fixed-gates.txt",
              "fix-report.md", "DELIVERY.txt", "delivery.txt"]

TOKEN = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
HDRS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
        "Content-Type": "application/json"}


def log(msg):
    LOG.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")


def api(path, body=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://chat.z.ai" + path, data=data, headers=HDRS,
        method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(errors="replace"))


def last_assistant_size(cid):
    """Batch payload size of the newest assistant message (0 if none)."""
    data = api(f"/api/v1/chats/{cid}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = (inner.get("history") or {}).get("messages", {})
    arr = list(msgs.values()) if isinstance(msgs, dict) else list(msgs)
    arr.sort(key=lambda m: m.get("createdAt") or m.get("timestamp") or 0)
    asst = [m for m in arr if m.get("role") == "assistant"]
    if not asst:
        return 0, None
    last = asst[-1]
    ids = [m["id"] for m in arr if m.get("id")]
    bj = api(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids})
    payloads = (bj.get("data") or bj.get("messages") or {}) if isinstance(bj, dict) else {}
    m = payloads.get(last["id"])
    if not m:
        return 0, None
    return len(json.dumps(m)), last["id"]


def workspace_for(cid):
    wj = api("/api/v1/web-dev/workspaces/user-fc")
    for w in (wj.get("workspaces") or []):
        if (w.get("chat_id") or "").replace("chat-", "") == cid:
            return w.get("function_name")
    return None


def fetch_files(cid, wsid, outdir):
    tree = api("/api/v1/web-dev/workspaces/files/ls-tree",
               {"chatId": cid, "workspace_id": wsid})
    if isinstance(tree, dict):
        tree = tree.get("data") or tree.get("files") or []
    want = [f for f in tree if f in WANT_EXACT or f.startswith("delivery/")]
    got = []
    os.makedirs(outdir, exist_ok=True)
    for fp in want:
        dest = os.path.join(outdir, fp.replace("/", "__"))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            got.append(fp)
            continue
        try:
            req = urllib.request.Request(
                "https://chat.z.ai/api/v1/web-dev/workspaces/files/content",
                data=json.dumps({"chatId": cid, "workspace_id": wsid,
                                 "rev": "latest", "filepath": fp}).encode(),
                headers=HDRS, method="POST")
            with urllib.request.urlopen(req, timeout=110) as r:
                raw = r.read()
            if len(raw) > 0:
                open(dest, "wb").write(raw)
                got.append(fp)
                log(f"    fetched {fp} ({len(raw)} bytes)")
        except Exception as e:
            log(f"    fetch fail {fp}: {str(e)[:80]}")
    return got


def main():
    log("harvest watch online: " + ", ".join(f"{n}->{c[:8]}" for n, c in PARTITIONS))
    state = {n: {"size": 0, "stable": 0, "harvested": False} for n, c in PARTITIONS}
    start = time.time()
    while time.time() - start < HORIZON_S:
        try:
            with open(os.path.join(FLAGS, "tl3_harvest_watch_heartbeat"), "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        for name, cid in PARTITIONS:
            st = state[name]
            if st["harvested"]:
                continue
            try:
                size, mid = last_assistant_size(cid)
            except Exception as e:
                log(f"{name}: poll error {type(e).__name__} {str(e)[:60]}")
                continue
            if size > st["size"]:
                st["size"] = size
                st["stable"] = 0
                log(f"{name}: narrative growing {size} (mid {str(mid)[:8]})")
                continue
            if size < MIN_SIZE:
                continue
            st["stable"] += 1
            log(f"{name}: stable x{st['stable']} at {size}")
            if st["stable"] < STABLE_N:
                continue
            # stable: attempt harvest
            wsid = workspace_for(cid)
            log(f"{name}: stable — harvesting (ws={wsid})")
            if not wsid:
                log(f"{name}: no live workspace yet")
                continue
            got = fetch_files(cid, wsid, os.path.join(OUT, name))
            if len(got) >= 2 or ("delivery.patch" in got and "findings.md" in got):
                st["harvested"] = True
                log(f"{name}: HARVESTED {got}")
            else:
                log(f"{name}: harvest thin ({got}) — keep watching")
                st["stable"] = 0
        if all(s["harvested"] for s in state.values()):
            with open(os.path.join(FLAGS, "tl3_harvest_complete.json"), "w") as f:
                json.dump({"ts": int(time.time()), "state": state}, f, indent=2)
            log("ALL THREE PARTITIONS HARVESTED — exiting")
            return 0
        time.sleep(POLL_S)
    log("horizon reached — partial: "
        + json.dumps({n: s["harvested"] for n, s in state.items()}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
