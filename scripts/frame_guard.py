#!/usr/bin/env python3
"""frame_guard.py — console frame freshness watch (2026-09-24).

Postmortem (01:20–05:56 UTC Sep 24): a lane tab's renderer wedged (compositor
stall — Page.captureScreenshot hung / -32603) and replayd kept "serving stale"
for 4.5h while healthz stayed green, so the operator's preview image froze
silently. This guard closes that detection gap WITHOUT touching the watch
fabric (standalone process; freeze-safe: local HTTP/CDP only, zero sends):

  every 600s:
    1. GET http://127.0.0.1:3100/frame  (timeout 10s) — 200 + jpeg magic = OK
    2. on 2 consecutive bad checks:
       a. restart replayd (kill pid on :3100; supervisor's ensure_replayd
          resurrects it — proven this morning)
       b. recheck; if still bad, Page.reload the active tab via CDP
          (page load only — no message send, no generation)
       c. recheck; if still bad, outbox alert + keep every-600s retry loop
          (tab swap / registry surgery stays a Lead action — too risky to
          automate blind)
    3. every cycle OK again -> log recovery line.

Exit: never (daemon). Logs: logs/frame_guard.log. Outbox on persistent fail.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
INTERVAL = 600
BAD_STREAK_TRIGGER = 2


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(os.path.join(LOGDIR, "frame_guard.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def outbox(text):
    try:
        rec = {"ts": int(time.time() * 1000), "from": "agent", "text": text}
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log(f"outbox err: {e}")


def frame_ok():
    """True iff replayd /frame returns 200 with JPEG magic bytes."""
    try:
        r = urllib.request.urlopen("http://127.0.0.1:3100/frame", timeout=10)
        if r.status != 200:
            return False
        head = r.read(3)
        return head[:3] == b"\xff\xd8\xff"
    except Exception:
        return False


def replayd_pid():
    try:
        out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if ":3100" in line:
                for tok in line.split():
                    if tok.startswith("pid="):
                        return int(tok[4:].split(",")[0])
    except Exception:
        pass
    return None


def restart_replayd():
    pid = replayd_pid()
    if pid:
        log(f"restarting replayd (pid {pid})")
        try:
            os.kill(pid, 15)
        except Exception as e:
            log(f"kill err: {e}")
    else:
        log("replayd pid not found on :3100 (supervisor will spawn)")


def reload_active_tab():
    """Page.reload the tab named in active_tab.txt (page load only — NO send)."""
    try:
        aid = open(os.path.join(FLAGS, "active_tab.txt")).read().strip()
        script = (
            "import asyncio,json,urllib.request,websockets\n"
            "async def t():\n"
            f"    tabs=json.load(urllib.request.urlopen('http://127.0.0.1:9222/json/list',timeout=5))\n"
            f"    tab=next(x for x in tabs if x['id'].startswith({aid[:12]!r}))\n"
            "    ws=await websockets.connect(tab['webSocketDebuggerUrl'])\n"
            "    await ws.send(json.dumps({'id':1,'method':'Page.reload','params':{'ignoreCache':True}}))\n"
            "    try:\n"
            "        await asyncio.wait_for(ws.recv(),8)\n"
            "    except Exception:\n"
            "        pass\n"
            "    await ws.close()\n"
            "asyncio.run(t())\n"
        )
        subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=30)
        log(f"Page.reload sent to active tab {aid[:12]}")
    except Exception as e:
        log(f"reload err: {e!r}")


# 2026-09-24 06:5x lesson: pick_tab matches the FULL 32-char target id in
# active_tab.txt; a short prefix silently falls back to the FIRST chat tab,
# which may be compositor-wedged. Any active-tab write MUST use the full id.
SWITCH_SCRIPT = """
import asyncio, json, sys, urllib.request, websockets

async def t():
    tabs = json.load(urllib.request.urlopen(
        "http://127.0.0.1:9222/json/list", timeout=5))
    pages = [x for x in tabs if x.get("type") == "page"
             and "chat.z.ai" in (x.get("url") or "")]
    for tab in pages:
        try:
            ws = await websockets.connect(tab["webSocketDebuggerUrl"])
            await ws.send(json.dumps(
                {"id": 1, "method": "Page.captureScreenshot",
                 "params": {"format": "jpeg", "quality": 40}}))
            r = await asyncio.wait_for(ws.recv(), 6)
            await ws.close()
            if "data" in json.loads(r).get("result", {}):
                print(tab["id"])  # FULL id of first capturable chat tab
                return
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass

asyncio.run(t())
"""


def switch_healthy_tab():
    """If the active tab itself is wedged, switch active_tab.txt (FULL id)
    to the first chat.z.ai tab that captures cleanly. Registry/marker
    surgery stays a Lead action; this only re-points the VIEW."""
    try:
        r = subprocess.run([sys.executable, "-c", SWITCH_SCRIPT],
                           capture_output=True, text=True, timeout=45)
        full_id = (r.stdout or "").strip()
        if len(full_id) == 32:
            with open(os.path.join(FLAGS, "active_tab.txt"), "w") as f:
                f.write(full_id)
            log(f"active tab switched to healthy {full_id[:12]}… (full id written)")
            return True
        log(f"no healthy chat tab found to switch to (out={full_id[:40]!r})")
        return False
    except Exception as e:
        log(f"switch err: {e!r}")
        return False


def main():
    log("frame_guard online — 600s cycle, trigger at 2 consecutive bad checks")
    bad = 0
    alerted = False
    while True:
        ok = frame_ok()
        if ok:
            if bad:
                log(f"frame RECOVERED (after {bad} bad checks)")
                if alerted:
                    outbox("[lead] Console frame stream recovered — the preview image is live again.")
                    alerted = False
            bad = 0
        else:
            bad += 1
            log(f"frame check BAD ({bad}/{BAD_STREAK_TRIGGER})")
            if bad == BAD_STREAK_TRIGGER:
                restart_replayd()
                time.sleep(20)
                if frame_ok():
                    log("replayd restart fixed the frame stream")
                    bad = 0
                    continue
                reload_active_tab()
                time.sleep(15)
                if frame_ok():
                    log("active-tab reload fixed the frame stream")
                    bad = 0
                    continue
                if switch_healthy_tab():
                    time.sleep(10)
                    if frame_ok():
                        log("healthy-tab switch fixed the frame stream")
                        bad = 0
                        continue
                if not alerted:
                    outbox("[lead] Console frame stream is STUCK (replayd restart + tab reload did not "
                           "fix it) — the operator's preview image is frozen. Needs Lead tab-swap/"
                           "registry surgery. Watches and probes are unaffected.")
                    alerted = True
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
