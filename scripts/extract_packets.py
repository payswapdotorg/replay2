#!/usr/bin/env python3
"""extract_packets.py — recover lane dispatch packets from chat msg-1.

The wave-28 packet files were lost in the sandbox resets, but every packet's
full text lives server-side as message #1 of its dispatched chat. This tool
fetches msg-1 for each lane, scrubs the OLD (dead) operator PAT — replaced
with the [REDACTED:github_token] placeholder — and stages a re-dispatchable
packet file (mode 600) under scripts/flags/.

At send time dispatch_worker._subst_pat injects the CURRENT PAT from env
(GITHUB_OPERATOR_PAT / OPERATOR_PAT / GITHUB_TOKEN / PAYSWAP_PAT).
"""
import json
import os
import re
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")

LANES = {
    "T032": "fc56c555-3365-4702-ba45-a5f1f2d0851e",
    "T034": "350c9a75-5136-4ea2-bb5c-9069bbfac9e5",
    "T048": "bb59b0ce-2b94-4a4a-901c-35bbe1dba1ac",
}

PAT_RE = re.compile(r"ghp_[A-Za-z0-9]{20,}")


def page_eval(js, timeout=60):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def fetch_msg1(cid):
    js = f"""
    (async () => {{
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t}}}});
      const t2 = await r.text();
      return t2.slice(0, 400000);
    }})()
    """
    raw = page_eval(js)
    d = json.loads(raw)
    hist = (d.get("chat") or {}).get("history") or {}
    msgs = list((hist.get("messages") or {}).values())
    if not msgs:
        raise SystemExit(f"{cid}: no messages")
    # msg-1 = earliest user message (the dispatch packet)
    users = [m for m in msgs if m.get("role") == "user"]
    users.sort(key=lambda m: m.get("timestamp") or 0)
    m = users[0]
    c = m.get("content")
    if isinstance(c, list):
        c = "".join(str(p.get("text", "")) for p in c if isinstance(p, dict))
    if not isinstance(c, str) or len(c) < 100:
        raise SystemExit(f"{cid}: msg-1 not a usable text (len={len(c) if isinstance(c,str) else '?'})")
    return c


def main():
    ok = True
    for name, cid in LANES.items():
        try:
            text = fetch_msg1(cid)
        except SystemExit as e:
            print(f"{name}: EXTRACT FAIL — {e}")
            ok = False
            continue
        pats = PAT_RE.findall(text)
        if pats:
            # all embedded tokens should be the same old PAT; scrub them all
            for p in set(pats):
                text = text.replace(p, "[REDACTED:github_token]")
            note = f"scrubbed {len(pats)} token occurrence(s)"
        else:
            note = "no token found (packet carried placeholder already?)"
        path = os.path.join(FLAGS, f"pkt_{name}_redispatch.md")
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o600)
        print(f"{name}: {len(text)} chars -> {os.path.basename(path)} ({note})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
