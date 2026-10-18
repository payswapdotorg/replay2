#!/usr/bin/env python3
"""Definitive mer-B chat liveness test: navigate + capture the messages API call."""
import json, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

MERB_URL = "https://chat.z.ai/c/7b4c016d-4410-4a43-967d-fa597b14e615"

t = channel.new_tab(MERB_URL)
if not t:
    print("new_tab FAILED"); sys.exit(1)
print("tab created:", t.get("id", "")[:8])
cdp = channel.CDP(t["webSocketDebuggerUrl"], timeout=40)
try:
    # start network capture
    cdp.call("Network.enable", {}, timeout=10)
    # navigate (again, to be sure — new_tab may have already done it)
    try:
        cdp.call("Page.navigate", {"url": MERB_URL}, timeout=20)
    except Exception as e:
        print("navigate:", e)
    # collect events for 20s
    t0 = time.time()
    api_hits = []
    url_now = None
    while time.time() - t0 < 22:
        time.sleep(2)
        try:
            for ev in cdp.events:
                if not isinstance(ev, dict):
                    continue
                m = ev.get("method", "")
                p = ev.get("params", {}) or {}
                if m == "Network.responseReceived":
                    u = p.get("response", {}).get("url", "")
                    if "/api/" in u and ("7b4c016d" in u or "chat" in u or "message" in u):
                        api_hits.append({"url": u[:120],
                                         "status": p.get("response", {}).get("status")})
                if m == "Network.requestWillBeSent" and p.get("redirectResponse"):
                    rd = p["redirectResponse"].get("url", "")
                    if "7b4c016d" in rd or "chat.z.ai" in rd:
                        api_hits.append({"redirect_from": rd[:100],
                                         "to": p.get("documentURL", "")[:100]})
        except Exception:
            pass
        try:
            url_now = cdp.eval("location.href", timeout=8)
        except Exception:
            pass
    print("final url:", url_now)
    print(f"api hits ({len(api_hits)}):")
    seen = set()
    for h in api_hits:
        key = json.dumps(h)
        if key in seen: continue
        seen.add(key)
        print("  ", h)
finally:
    cdp.close()
