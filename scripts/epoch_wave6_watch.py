#!/usr/bin/env python3
"""epoch_wave6_watch.py — one-shot status probe for the wave-6 Epoch workers.

Per worker: tab DOM length + REAL completion-report detection (the packets
contain the literal report FORMAT, so the discriminator is a filled-in
field: a 40-hex Final head or a real PR number) + 60s-liveness delta.
Plus server-side: work branches + open PRs on payswapdotorg/Epoch.

Usage: epoch_wave6_watch.py [--delta]   (--delta: two probes 60s apart)
"""
import json
import os
import re
import sys
import time
import urllib.request
import websocket

WORKERS = [
    ("W012", "931B438C", "e5b4e2d2", "work/W012-experience-compiler"),
    ("W020", "40A3E89", "31e04e5e", "work/W020-agent-runtime-orchestration"),
    ("W028", "A9D0741A", "6d452b00", "work/W028-document-to-adapter"),
]
REPORT_RE = re.compile(r"(Final head:\s+[0-9a-f]{40}|PR:\s+#\d+|CI:\s+(success|failure))")


def tab_body(prefix):
    try:
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
        tab = [t for t in tabs if t.get("id", "").startswith(prefix)]
        if not tab:
            return None
        ws = websocket.create_connection(tab[0]["webSocketDebuggerUrl"], timeout=20)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "document.body.innerText", "returnByValue": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                ws.close()
                return m.get("result", {}).get("result", {}).get("value")
    except Exception:
        return None


def gh(path):
    tok = os.popen("grep -o 'ghp_[A-Za-z0-9]*' ~/.secrets/env.sh | head -1").read().strip()
    req = urllib.request.Request("https://api.github.com/repos/payswapdotorg/Epoch" + path,
                                 headers={"Authorization": "token " + tok,
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def probe():
    out = {}
    for wo, tabp, cid, branch in WORKERS:
        body = tab_body(tabp)
        if body is None:
            out[wo] = {"len": -1, "report": "?", "tail": "(tab gone — check server side)"}
            continue
        m = REPORT_RE.search(body[-3000:])
        out[wo] = {"len": len(body), "report": bool(m),
                   "tail": body[-160:].replace("\n", " | ")}
    return out


def server_side():
    lines = []
    try:
        prs = gh("/pulls?state=open")
        if prs:
            for p in prs:
                lines.append(f"PR #{p['number']} {p['title'][:60]} [{p['head']['ref']}]")
        else:
            lines.append("no open PRs")
    except Exception as e:
        lines.append(f"PR check err: {str(e)[:40]}")
    for _, _, _, branch in WORKERS:
        try:
            b = gh(f"/branches/{branch}")
            lines.append(f"branch {branch}: {b['commit']['sha'][:10]} ({b['commit']['commit']['message'].splitlines()[0][:50]})")
        except Exception:
            lines.append(f"branch {branch}: not pushed yet")
    return lines


def render(states, prev=None):
    for wo, tabp, cid, branch in WORKERS:
        s = states[wo]
        d = ""
        if prev and prev.get(wo) and s["len"] > 0 and prev[wo]["len"] > 0:
            d = " LIVE" if s["len"] != prev[wo]["len"] else " quiet"
        flag = " *** REPORT RENDERED ***" if s["report"] is True else ""
        print(f"[{wo}] len={s['len']}{d}{flag}")
        print(f"      {s['tail']}")


def main():
    delta = "--delta" in sys.argv
    s1 = probe()
    if delta:
        time.sleep(60)
        s2 = probe()
        render(s2, s1)
    else:
        render(s1)
    print("--- server side ---")
    for line in server_side():
        print(line)


if __name__ == "__main__":
    main()
