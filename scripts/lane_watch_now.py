#!/usr/bin/env python3
"""lane_watch_now.py — queued-capacity lane watcher (2026-09-23 endgame).

Watches the dispatched lanes (from flags/endgame_lanes.json) while they sit
in the GLM-5.3 capacity queue. Per the two-state doctrine (accepted send =
queued, never cancel), the only failure modes to catch:
  1. TAB ROLLED HOME (the site destroyed the queued session) -> outbox ALERT
     + write flags/<name>-destroyed.marker (the Lead re-dispatches);
  2. GENERATION START (chars grow beyond the prompt echo / "Ran N commands")
     -> outbox note once;
  3. COMPLETION (handed by waveB_completion_watch; here only the exit check).

Every 240s: probe each lane's registry tab (URL + body), heartbeat, log.
Exits when ALL lanes have completion markers.

Usage (detached): python3 dfork_launch.py logs/lane_watch_now.log \\
                      python3 lane_watch_now.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
HB = os.path.join(FLAGS, "lane_watch_now_heartbeat")
LOG = open(os.path.join(BASE, "logs", "lane_watch_now.log"), "a", buffering=1)

EVERY = 240


def log(m):
    LOG.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception as e:  # noqa: BLE001
        log(f"outbox fail: {e}")


def load_lanes():
    """name -> (chat-id-prefix, prompt-echo baseline)."""
    lanes = {}
    try:
        spec = json.loads(open(os.path.join(FLAGS, "endgame_lanes.json")).read())
    except Exception:  # noqa: BLE001
        return lanes
    for name, cid in spec.items():
        echo = 0
        try:
            with open(REG) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    if d.get("name") == name and d.get("prompt_chars"):
                        echo = int(d["prompt_chars"]) + 700
        except FileNotFoundError:
            pass
        lanes[name] = (cid, echo)
    return lanes


def registry_tab(name):
    tab = None
    try:
        with open(REG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if d.get("name") == name and d.get("tab_id"):
                    tab = d.get("tab_id")
    except FileNotFoundError:
        return None
    return tab


def body_of(tab):
    try:
        t = next((x for x in channel.list_tabs() if x["id"].startswith(tab[:8])), None)
        if not t:
            return None, None
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
        try:
            url = t.get("url") or ""
            body = c.eval("document.body.innerText || ''", timeout=20) or ""
            return url, body
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        log(f"{tab[:8]} probe error: {e}")
        return None, None


def main():
    log("=== lane_watch_now started (queued-capacity doctrine: never cancel) ===")
    started_note, destroyed_note = {}, {}
    while True:
        with open(HB, "w") as f:
            f.write(str(int(time.time())))
        lanes = load_lanes()
        if not lanes:
            log("no lanes configured (endgame_lanes.json empty) — idle")
            time.sleep(EVERY)
            continue
        done = 0
        for name, (cid, echo) in lanes.items():
            if os.path.exists(os.path.join(FLAGS, f"{name}-complete.marker")):
                done += 1
                continue
            if name in destroyed_note:
                continue
            tab = registry_tab(name)
            if not tab:
                log(f"{name}: no tab in registry (yet)")
                continue
            url, body = body_of(tab)
            if url is None:
                log(f"{name}: tab {tab[:8]} LOST (probe failed)")
                continue
            if "/c/" not in url:
                log(f"{name}: TAB ROLLED HOME ({url[:60]}) — DESTROYED")
                open(os.path.join(FLAGS, f"{name}-destroyed.marker"), "w").write(
                    time.strftime("%FT%TZ") + " tab rolled home: " + url[:80])
                destroyed_note[name] = True
                outbox(
                    f"[lead] ALERT: the {name} queued session was destroyed by the site "
                    "(tab rolled home during peak capacity). Re-dispatching fresh — no work lost, "
                    "the session had not started generating."
                )
                continue
            b = len(body or "")
            ran = bool(re.search(r"Ran \d+ command", body or ""))
            streaming = ran or b > echo + 800  # beyond the prompt echo = real generation
            if streaming and not started_note.get(name):
                started_note[name] = True
                log(f"{name}: GENERATION APPEARS LIVE (chars {b})")
                outbox(f"[lead] {name} is GENERATING now (chars ~{b}). I watch for the completion report.")
            log(f"{name}: queued-ok url=/c/… chars={b}")
        if lanes and done == len(lanes):
            log("all lanes complete — exiting")
            return 0
        time.sleep(EVERY)


if __name__ == "__main__":
    sys.exit(main())
