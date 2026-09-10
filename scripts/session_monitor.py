#!/usr/bin/env python3
"""Detached session-state monitor: appends one status line per poll to
/tmp/orbb_sessions.log so the lead can sleep between checks instead of
running full CDP reads each cycle. Passive (DOM reads only, no clicks)."""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

NAMES = ["m1-b-ui", "m1-c-observability"]


def registry_latest():
    latest = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "flags/session_registry.jsonl")) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                n = d.get("name")
                if not n:
                    continue
                if d.get("action") in ("void", "failed", "done"):
                    latest[n] = None
                elif d.get("stage") == "capacity":
                    latest[n] = None
                elif "url" in d:
                    latest[n] = d
    except FileNotFoundError:
        pass
    return latest


def read_tab(ws_url):
    try:
        c = channel.CDP(ws_url, timeout=20)
        body = c.call("Runtime.evaluate",
                      {"expression": "document.body.innerText || ''",
                       "returnByValue": True})["result"]["value"] or ""
        streaming = "Thought Process" in body[-3000:] or "Deep Think" in body[-3000:]
        final = "FINAL REPORT" in body
        err = ("personal limit" in body[-800:] or "at capacity" in body[-800:]
               or "No response" in body[-800:])
        c.ws.close()
        return len(body), streaming, final, err
    except Exception as e:
        return -1, False, False, False


def main():
    while True:
        reg = registry_latest()
        tabs = json.load(urllib.request.urlopen(
            "http://127.0.0.1:9222/json/list", timeout=10))
        parts = []
        for n in NAMES:
            s = reg.get(n)
            if not s:
                parts.append(f"{n}=unregistered")
                continue
            tab = next((t for t in tabs
                        if t.get("type") == "page"
                        and s["url"].rstrip("/") in (t.get("url") or "").rstrip("/")),
                       None)
            if not tab:
                parts.append(f"{n}=TAB-LOST")
                continue
            chars, streaming, final, err = read_tab(tab["webSocketDebuggerUrl"])
            flag = ("STREAM" if streaming else
                    "FINAL" if final and chars > 8000 else
                    "ERR" if err else "idle")
            parts.append(f"{n}={flag}:{chars}")
        with open("/tmp/orbb_sessions.log", "a") as f:
            f.write(time.strftime("%H:%M:%S") + " " + " ".join(parts) + "\n")
        time.sleep(60)


if __name__ == "__main__":
    main()
