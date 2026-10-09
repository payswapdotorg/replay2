#!/usr/bin/env python3
"""Evidence-based reclaim of orphaned probe ping tabs (leak fix 12:5xZ).

The 12:1x-12:5xZ probe-relaunch leak left ping tabs open after false yields
(the operator-collision guard fired on replayd self-heal pointer artifacts).
This utility reclaims ONLY tabs with POSITIVE evidence of probe ownership:

  - tab id is NOT the current probe tab   (flags/probe_tab.txt)
  - tab id is NOT the console mirror tab  (flags/active_tab.txt)
  - tab id is NOT a live automation session tab (session_registry.jsonl:
    latest record per session name not followed by a void)
  - the tab's visible conversation tail contains probe ping content
    (a "ping2" echo AND a Pong-style reply in the last 800 chars).

Everything it does is printed (truth law). Tabs failing ANY check are left
untouched (operator-asset law). Run manually; idempotent.
"""
import json
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
PROBE_MSG = "ping2"


def _read(path):
    try:
        return open(path).read().strip()
    except Exception:
        return ""


def live_session_tabs():
    """Tab ids of the latest non-voided registry records per session name."""
    live = {}
    try:
        with open(os.path.join(FLAGS, "session_registry.jsonl")) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                name = rec.get("name")
                if not name:
                    continue
                if rec.get("action") == "void":
                    live.pop(name, None)
                elif rec.get("tab_id"):
                    live[name] = rec["tab_id"]
    except FileNotFoundError:
        pass
    return set(live.values())


def main():
    probe_tab = _read(os.path.join(FLAGS, "probe_tab.txt"))
    active_tab = _read(os.path.join(FLAGS, "active_tab.txt"))
    live_tabs = live_session_tabs()
    protected = {t for t in (probe_tab, active_tab) if t} | live_tabs
    print("[cleanup] protected: probe=%s active=%s live-sessions=%s"
          % (probe_tab[:8] or "-", active_tab[:8] or "-",
             ",".join(sorted(t[:8] for t in live_tabs)) or "-"))
    tabs = [t for t in channel.list_tabs() if t.get("type") == "page"]
    closed = 0
    for t in tabs:
        tid = t.get("id") or ""
        url = t.get("url") or ""
        if tid in protected:
            print("[cleanup] skip (protected) %s %s" % (tid[:8], url[:60]))
            continue
        if "chat.z.ai" not in url:
            print("[cleanup] skip (not chat.z.ai) %s %s" % (tid[:8], url[:40]))
            continue
        # evidence: conversation tail must show probe ping content
        try:
            ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=30)
        except Exception as e:
            print("[cleanup] skip (CDP fail) %s: %s" % (tid[:8], str(e)[:50]))
            continue
        try:
            tail = ws.eval("document.body.innerText.slice(-800)", timeout=15) or ""
        except Exception as e:
            print("[cleanup] skip (eval fail) %s: %s" % (tid[:8], str(e)[:50]))
            ws.close()
            continue
        ws.close()
        has_ping = PROBE_MSG in tail
        has_pong = ("Pong" in tail) or ("pong" in tail)
        if has_ping and has_pong:
            print("[cleanup] RECLAIM %s %s — tail evidence: %r"
                  % (tid[:8], url[:60], tail[-200:].replace("\n", " | ")))
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + tid, timeout=6).read()
                closed += 1
            except Exception as e:
                print("[cleanup] close FAILED %s: %s" % (tid[:8], str(e)[:50]))
        else:
            print("[cleanup] skip (no probe evidence) %s %s tail=%r"
                  % (tid[:8], url[:60], tail[-120:].replace("\n", " | ")))
    print("[cleanup] closed %d tab(s)" % closed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
