#!/usr/bin/env python3
"""passive_net_watch.py — one-shot passive network capture on the next canary tab.

Purpose (2026-10-09 09:0xZ): the W3 canary chats die silently — prompt sent,
user message rendered, assistant turn never starts, no error banner. The
redispatcher's run_step only persists the last 200 chars of dispatch_worker
output, so the api-related net trace is lost. This script attaches a PASSIVE
CDP listener (Network.enable only — no clicks, no typing, no interference)
to the NEXT w3a canary tab the automation creates and records every api-ish
request/response/failure for 100s, so the exact failing endpoint lands in a
file the TL can read.

Read-only forensics under the truth law: unverified stays labeled unverified.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

KNOWN = {"ae9d5ece"}  # chats already seen (excluded)
OUT = "/home/z/replay2/scripts/logs/canary-net-capture.json"
API_KEYS = ("/api/", "chat", "task", "completion", "agent", "model")


def main():
    print("[netwatch] waiting for next canary tab...", flush=True)
    deadline = time.time() + 240
    target = None
    while time.time() < deadline:
        for t in channel.list_tabs():
            u = t.get("url") or ""
            if "chat.z.ai/c/" in u:
                cid = u.split("/c/")[-1].split("?")[0]
                if cid[:8] not in KNOWN:
                    target = (t, cid)
                    break
        if target:
            break
        time.sleep(4)
    if not target:
        print("[netwatch] no new canary tab in window — giving up")
        return 1
    tab, cid = target
    print("[netwatch] attached to canary %s tab %s" % (cid[:8], tab["id"][:8]), flush=True)

    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    rec = {"chat": cid, "tab": tab["id"], "started": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "api_events": [], "failures": []}
    try:
        c.call("Network.enable", {}, timeout=10)
        # drain/collect: periodic trivial calls pull buffered frames into c.events
        t_end = time.time() + 100
        while time.time() < t_end:
            try:
                c.call("Runtime.evaluate", {"expression": "1", "returnByValue": True}, timeout=5)
            except Exception:
                pass  # tab may close (void) before window ends — that's data too
            time.sleep(2)
    finally:
        try:
            c.close()
        except Exception:
            pass

    for e in c.events:
        m, p = e.get("method", ""), e.get("params", {}) or {}
        if m == "Network.requestWillBeSent":
            r = p.get("request", {}) or {}
            u = str(r.get("url", ""))
            if any(k in u for k in API_KEYS):
                rec["api_events"].append(["req", str(r.get("method")), u[:160],
                                          str(p.get("type", ""))])
        elif m == "Network.responseReceived":
            r = p.get("response", {}) or {}
            u = str(r.get("url", ""))
            if any(k in u for k in API_KEYS):
                rec["api_events"].append(["rsp", str(r.get("status")), u[:160]])
        elif m == "Network.loadingFailed":
            u = str((p.get("requestId", "")))
            rec["failures"].append([u[:16], str(p.get("errorText")),
                                    str(p.get("canceled", ""))])
    rec["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(OUT, "w") as f:
        json.dump(rec, f, indent=1)
    print("[netwatch] captured %d api events, %d failures -> %s" %
          (len(rec["api_events"]), len(rec["failures"]), OUT), flush=True)
    for ev in rec["api_events"][:20]:
        print("  ", ev, flush=True)
    for fl in rec["failures"][:10]:
        print("  FAIL", fl, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
