#!/usr/bin/env python3
"""probe_agent_paths.py — try agent-relevant URLs in a disposable tab, report
which (if any) show the authenticated Agent shell (sidebar Agent nav)."""
import json, sys, time, urllib.request
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from dispatch_worker import JS_AGENT_PRESENT

CANDIDATES = [
    "https://chat.z.ai/agent",
    "https://chat.z.ai/agents",
    "https://chat.z.ai/web-dev",
    "https://chat.z.ai/",
]

def agent_nav(c):
    r = c.call("Runtime.evaluate",
               {"expression": JS_AGENT_PRESENT, "returnByValue": True}, timeout=30)
    return r.get("result", {}).get("value")

for url in CANDIDATES:
    try:
        tab = channel.new_tab(url)
        if not tab:
            print(url, "-> no tab")
            continue
        time.sleep(5)
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        v = "init"
        for _ in range(6):
            v = agent_nav(c)
            if v == "found":
                break
            time.sleep(2)
        # also read final url + any login redirect
        r2 = c.call("Runtime.evaluate",
                    {"expression": "location.href + ' | ' + document.title", "returnByValue": True},
                    timeout=30)
        print("%s -> agentNav=%s | %s" % (url, v, r2.get("result", {}).get("value", "")))
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:9222/json/close/" + tab["id"], timeout=5)
        except Exception:
            pass
    except Exception as e:
        print(url, "-> ERROR", e)
