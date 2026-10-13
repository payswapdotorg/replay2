#!/usr/bin/env python3
"""homepage_tab_gc.py — frozen-homepage tab GC (2026-10-13, the pcl-002 capacity fight).

The assault loop (dispatch_worker create ladder) materializes a chat.z.ai
homepage tab per failed round; when a round's send dies at capacity the tab
is left behind and its renderer FREEZES (4GB box, no swap — the freeze
class discovered in replay-#11: a frozen renderer never answers CDP eval).
phantom_tab_gc.py deliberately never touches these (its law is TRUE-phantom
CHAT tabs: absent server-side + no registry row — homepage tabs have no
chat id at all, so the class is invisible to it). Ten frozen homepages
later the box re-enters the memory starvation that killed the frame core
during the w9c fight (9c9605e).

This GC closes ONLY chat.z.ai homepage tabs (url with no /c/ path) whose
renderer is CONFIRMED FROZEN (a 3s location.href ping times out). An ALIVE
homepage is the assault's current working tab — never touched. /c/ chat
tabs are NEVER touched (the phantom_tab_gc doctrine governs those).
Rounds every 90s; stateless; logs to flags/ via the standard log().
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
LOG = os.path.join(FLAGS, "homepage_tab_gc.log")
INTERVAL = 90
CDP = "http://127.0.0.1:" + os.environ.get("CDP_PORT", "9222")


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def tab_frozen(tab):
    """True if the tab's renderer is frozen (ping times out)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=3)
        try:
            c.eval("location.href", timeout=3)
            return False
        finally:
            c.close()
    except Exception:
        return True


def close_tab(tid):
    try:
        urllib.request.urlopen(
            urllib.request.Request(CDP + "/json/close/" + tid, method="PUT"),
            timeout=8)
        return True
    except Exception:
        return False


def main():
    log("homepage_tab_gc armed (90s rounds, frozen-homepage-only law)")
    while True:
        try:
            tabs = [t for t in channel.list_tabs()
                    if t.get("type") == "page" and "chat.z.ai" in (t.get("url") or "")]
            homes = [t for t in tabs if "/c/" not in (t.get("url") or "")]
            closed = 0
            for t in homes:
                if tab_frozen(t) and close_tab(t["id"]):
                    closed += 1
                    log(f"closed frozen homepage tab {t['id'][:8]}")
            if closed:
                log(f"round: closed {closed} frozen homepage tab(s), {len(homes)} homepage(s) seen")
            try:
                open(os.path.join(FLAGS, "homepage_tab_gc_heartbeat"), "w").write(
                    time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
        except Exception as e:
            log(f"round error: {str(e)[:80]}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
