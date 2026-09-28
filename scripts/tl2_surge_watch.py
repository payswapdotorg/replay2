#!/usr/bin/env python3
"""tl2_surge_watch.py — DOM-true watcher + in-window harvester for the TL2 surge lanes.

2026-09-28 LESSON (the false-outage): the server-side chat tree NEVER carries
assistant content — the freeze_probe's tree check reported DOWN for days while
generation worked and three workers DELIVERED. DOM is the only truth, and a
fresh tab load must WAIT for the SPA history render before reading.

Watched chats (one loop, 90s cadence):
  A-replica 487c77c6 (mid-run re-dispatch of the A WO, live pod)
  A/B/C-restage a0e4ed45 / ac121b3f / a48e023b (completed originals; surgical
  re-stage turns queued to re-bind their workspaces for harvest)

Per chat: navigate dump tab -> wait for load -> read innerText ->
classify (WAIT/RUNNING/CANDIDATE/COMPLETE/LOST). On COMPLETE (marker >= 2
with a stable tail across two polls) or a RESTAGED reply: harvest the
workspace IMMEDIATELY (files are only readable while the pod is active)
via harvest_robust.py, fetch the root bundle, write the complete marker,
notify via outbox.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "tl2_surge_watch.log")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PY = "/home/z/.venv/bin/python3"
CADENCE = 90

WATCHES = [
    ("A-replica", "487c77c6-d132-4b87-a701-4b7b609b8270",
     "flauz-delivery/tl2-a-orchestration", "tl2-a-orchestration.bundle",
     "FLAUZ-TL2-A-REPORT END", "/home/z/tl2-harvest/a-replica"),
    ("A-restage", "a0e4ed45-cca4-4651-ae57-8ef01d89c269",
     "flauz-delivery/tl2-a-orchestration", "tl2-a-orchestration.bundle",
     "FLAUZ-TL2-A-REPORT END", "/home/z/tl2-harvest/a-restage"),
    ("B-restage", "ac121b3f-effd-4cde-941c-ff19960bbf2a",
     "flauz-delivery/tl2-b-providers", "tl2-b-providers.bundle",
     "FLAUZ-TL2-B-REPORT END", "/home/z/tl2-harvest/b-restage"),
    ("C-restage", "a48e023b-a372-4e00-bbab-bfe495a79597",
     "flauz-delivery/tl2-c-state", "tl2-c-state.bundle",
     "FLAUZ-TL2-C-REPORT END", "/home/z/tl2-harvest/c-restage"),
]

_state = {name: {"chars": 0, "tail": "", "stable": 0, "phase": "WAIT",
                 "harvested": False, "lost": False} for name, *_ in WATCHES}


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except OSError:
        pass


DUMP_TAB_FLAG = os.path.join(FLAGS, "surge_dump_tab.txt")


def _reset_dump_tab():
    """Wedge self-heal (loop-v6 lesson): recreate the dump tab on read failure."""
    try:
        tid = open(DUMP_TAB_FLAG).read().strip()
        for t in channel.list_tabs():
            if t.get("id") == tid:
                import urllib.request
                urllib.request.urlopen(
                    f"http://127.0.0.1:9222/json/close/{t['id']}", timeout=5).read()
                break
    except OSError:
        pass
    except Exception:
        pass
    try:
        os.remove(DUMP_TAB_FLAG)
    except OSError:
        pass


def get_dump_tab():
    """DEDICATED dump tab (never reuse foreign tabs — collision lesson)."""
    try:
        tid = open(DUMP_TAB_FLAG).read().strip()
        for t in channel.list_tabs():
            if t.get("id") == tid:
                return t
    except OSError:
        pass
    t = channel.new_tab("https://chat.z.ai/")
    if t is None:
        return None
    time.sleep(3)
    try:
        with open(DUMP_TAB_FLAG, "w") as f:
            f.write(t["id"])
    except OSError:
        pass
    return t


def read_chat_dom(cid, needle):
    """FRESH tab per read (completed chats with dead workspaces WEDGE their
    tabs via the workspace-startup polling loop — a held tab goes blind in
    minutes; a fresh tab is always in its healthy window). Open -> wait for
    history render -> read -> CLOSE."""
    tab = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    if tab is None:
        return ""
    try:
        c = CDP(tab["webSocketDebuggerUrl"], timeout=40)
        best = ""
        stable = 0
        for _ in range(8):  # up to ~32s: full render + length stability
            time.sleep(4)
            body = c.eval("document.body.innerText || ''", timeout=25) or ""
            if len(body) > len(best):
                best = body
                stable = 0
            elif len(body) == len(best) and len(best) > 3000:
                stable += 1
                if stable >= 2:
                    break
            # shorter reads are transient render states — keep the longest
        c.close()  # NEVER leak CDP connections
        return best
    except Exception as e:
        log(f"  read_chat_dom({cid[:8]}) error: {e}")
        try:
            c.close()
        except Exception:
            pass
        return ""
    finally:
        try:
            import urllib.request
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
        except Exception:
            pass


def workspaces_map():
    """chat uuid -> workspace function_name via the in-page API (fresh tab —
    held tabs wedge)."""
    tab = channel.new_tab("https://chat.z.ai/")
    if tab is None:
        return {}
    try:
        time.sleep(3)
        c = CDP(tab["webSocketDebuggerUrl"], timeout=30)
        raw = c.eval("""(async () => {
          const r = await fetch('/api/v1/web-dev/workspaces/user-fc', {credentials:'include'});
          return await r.text();
        })()""", await_promise=True, timeout=30)
        c.close()
        data = json.loads(raw)
        items = None
        for k in ("workspaces", "list", "items"):
            if isinstance(data, dict) and isinstance(data.get(k), list):
                items = data[k]
                break
        if items is None and isinstance(data, list):
            items = data
        out = {}
        for w in items or []:
            cid = (w.get("chat_id") or "").removeprefix("chat-")
            if cid:
                out[cid] = w.get("function_name")
        return out
    except Exception as e:
        log(f"  workspaces_map error: {e}")
        return {}
    finally:
        try:
            import urllib.request
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
        except Exception:
            pass


def run_harvest(name, chat_id, ws_id, prefix, bundle, dest):
    os.makedirs(dest, exist_ok=True)
    log(f"  [{name}] HARVEST start ws={ws_id}")
    r1 = subprocess.run([PY, os.path.join(BASE, "harvest_robust.py"),
                         chat_id, ws_id, prefix, os.path.join(dest, "delivery")],
                        capture_output=True, text=True, timeout=900)
    log(f"  [{name}] harvest_delivery rc={r1.returncode}: " +
        (r1.stdout or "").strip().splitlines()[-1:].__repr__())
    r2 = subprocess.run([PY, os.path.join(BASE, "harvest_robust.py"),
                         chat_id, ws_id, bundle, os.path.join(dest, "root")],
                        capture_output=True, text=True, timeout=300)
    log(f"  [{name}] harvest_bundle rc={r2.returncode}: " +
        repr((r2.stdout or "").strip().splitlines()[-1:]))
    ok = r1.returncode == 0
    if ok:
        with open(os.path.join(FLAGS, f"{name}.surge-complete"), "w") as f:
            f.write(f"{int(time.time())} ws={ws_id}\n")
        outbox(f"[TL2 surge] {name} COMPLETE and harvested to {dest} "
               f"(ws {ws_id[:12]}); delivery tree + root bundle fetched. "
               f"TL review + landing next.")
    return ok


def main():
    log(f"=== tl2_surge_watch start (watches: {', '.join(w[0] for w in WATCHES)})")
    while True:
        try:
            wsmap = workspaces_map()
            for name, cid, prefix, bundle, marker, dest in WATCHES:
                s = _state[name]
                if s["harvested"] or s["lost"]:
                    continue
                body = read_chat_dom(cid, marker)
                if not body:
                    log(f"[{name}] read failed/empty")
                    continue
                chars = len(body)
                tail = body[-90:].replace("\n", " ")
                hits = body.count(marker)
                if "WORKSPACE-LOST" in body[-2000:]:
                    s["lost"] = True
                    log(f"[{name}] WORKSPACE-LOST verdict from worker")
                    outbox(f"[TL2 surge] {name}: worker reports WORKSPACE-LOST "
                           f"(sandbox recycled before harvest) — lane will be "
                           f"re-dispatched fresh.")
                    continue
                if hits >= 2 and tail == s["tail"]:
                    s["stable"] += 1
                else:
                    s["stable"] = 0
                phase = ("RUNNING" if chars != s["chars"] else
                         ("STABLE" if chars > 3000 else "WAIT"))
                if hits >= 2:
                    phase = "CANDIDATE" if s["stable"] < 2 else "COMPLETE"
                if phase != s["phase"]:
                    log(f"[{name}] {s['phase']}->{phase} chars={chars} hits={hits} "
                        f"tail={tail[:70]!r}")
                    s["phase"] = phase
                s["chars"], s["tail"] = chars, tail
                if phase == "COMPLETE":
                    ws = wsmap.get(cid)
                    if ws:
                        if run_harvest(name, cid, ws, prefix, bundle, dest):
                            s["harvested"] = True
                            log(f"[{name}] HARVESTED -> {dest}")
                        else:
                            log(f"[{name}] harvest failed; will retry next cycle")
                            s["stable"] = 0  # re-arm candidate after retry
                    else:
                        log(f"[{name}] COMPLETE but no active workspace; retrying")
            done = sum(1 for n in _state if _state[n]["harvested"])
            lost = sum(1 for n in _state if _state[n]["lost"])
            if done + lost == len(WATCHES):
                log("=== all watches resolved; watcher exits")
                outbox("[TL2 surge] all four watched chats resolved "
                       f"({done} harvested, {lost} lost); watcher exits.")
                return
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(CADENCE)


if __name__ == "__main__":
    main()
