#!/usr/bin/env python3
"""login_watch_now.py — CURRENT-campaign login watcher (2026-09-23 reset).

Watch-only: never sends, never dispatches. The resident Lead (who the operator
watches through the replay) does all dispatching from inside the replay.

Strict evidence discipline (carried from r22_login_sentinel v2):
  1. a chat.z.ai tab's body shows the AUTHENTICATED shell (no "Sign in"/"Log
     in" affordance + positive markers), debounced on 2 probes 20s apart;
  2. a FRESH probe tab inherits the session (the dispatch requirement);
then: write flags/login_confirmed.json + outbox note, exit 0.

Usage (detached): python3 dfork_launch.py logs/login_watch_now.log \\
                      python3 login_watch_now.py
Heartbeat: flags/login_watch_now_heartbeat (stale > 120s = watcher dead).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dispatch_worker as dw

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
HB = os.path.join(FLAGS, "login_watch_now_heartbeat")
OUT = os.path.join(FLAGS, "agent_outbox.jsonl")
CONFIRM = os.path.join(FLAGS, "login_confirmed.json")
LOG = open(os.path.join(BASE, "logs", "login_watch_now.log"), "a", buffering=1)

DEBOUNCE = 20
POLL = 30


def log(msg):
    LOG.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def beat():
    with open(HB, "w") as f:
        f.write(str(int(time.time())))


def outbox(text):
    with open(OUT, "a") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def _body_of(tab):
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            return dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return None


def _authed_body(body):
    if not body:
        return False
    if ("Sign in" in body) or ("Log in" in body):
        return False
    return ("Previous" in body) or ("New Task" in body) or (len(body) >= 900)


def logged_in_tabs():
    good = []
    try:
        for t in channel.list_tabs():
            if not (t.get("url") or "").startswith("https://chat.z.ai"):
                continue
            body = _body_of(t)
            if body and _authed_body(body):
                good.append(t["id"])
    except Exception as e:  # noqa: BLE001
        log(f"probe error (continuing): {e}")
    return good


def new_tab_authed():
    try:
        tab = channel.new_tab()
    except Exception:  # noqa: BLE001
        return False
    if not tab:
        return False
    ok = False
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            c.call("Page.navigate", {"url": "https://chat.z.ai/"}, timeout=30)
            time.sleep(8)
            body = dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
            ok = _authed_body(body)
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        log(f"probe-tab error: {e}")
    try:
        import urllib.request
        urllib.request.urlopen(
            f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=6
        ).read()
    except Exception:  # noqa: BLE001
        pass
    return ok


def main():
    log("=== login_watch_now started (watch-only, current campaign) ===")
    outbox("[lead] login watcher armed — log in through the replay image whenever you are ready.")
    while True:
        beat()
        first = logged_in_tabs()
        if first:
            time.sleep(DEBOUNCE)
            beat()
            second = logged_in_tabs()
            if second:
                log(f"strict login evidence on tabs {second}")
                if new_tab_authed():
                    log("fresh-tab session inheritance CONFIRMED")
                    rec = {
                        "ts": int(time.time() * 1000),
                        "tabs": second,
                        "inheritance": True,
                    }
                    with open(CONFIRM, "w") as f:
                        json.dump(rec, f, indent=1)
                    outbox(
                        "[lead] login confirmed (strict evidence + fresh-tab inheritance). "
                        "Recomputing frontier and dispatching workers from inside the replay."
                    )
                    log("login_confirmed.json written — exiting (Lead takes over)")
                    return 0
                log("login seen but fresh tabs NOT authed yet — continuing watch")
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
