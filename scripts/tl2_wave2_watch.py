#!/usr/bin/env python3
"""tl2_wave2_watch.py — completion watcher + in-window harvester for wave 2
(A2 d5223082, S1 7a53fc90, S2 0c8db875) with S3 auto-dispatch on slot free.

Per lane: fresh-tab-per-read DOM read (lesson-196: held tabs wedge; the tree
never carries assistant content) -> on marker>=2 with a stable tail across two
polls: harvest the workspace DURING the active-pod window (delivery prefix +
root bundle) -> write the complete flag -> outbox. When a lane completes:
dispatch S3 (the last surge lane) once, via launch_create.py.
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
LOG = os.path.join(BASE, "logs", "tl2_wave2_watch.log")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PY = "/home/z/.venv/bin/python3"
CADENCE = 120

LANES = [
    ("A2", "d5223082-c51a-4aa4-b115-3e771bddeccc",
     "flauz-delivery/tl2-a2-orchestration-m4m5", "tl2-a2-orchestration-m4m5.bundle",
     "FLAUZ-TL2-A2-REPORT END", "/home/z/tl2-harvest/a2-m4m5"),
    ("S1", "7a53fc90-adf0-453b-8415-e3716926f45d",
     "flauz-delivery/tl2-s1-service-integration", "tl2-s1-service-integration.bundle",
     "FLAUZ-TL2-S1-REPORT END", "/home/z/tl2-harvest/s1-service"),
    ("S2", "0c8db875-695e-40b7-853b-8f055d5ca596",
     "flauz-delivery/tl2-s2-resource-exec", "tl2-s2-resource-exec.bundle",
     "FLAUZ-TL2-S2-REPORT END", "/home/z/tl2-harvest/s2-resource"),
]
S3_PROMPT = os.path.join(BASE, "worker-prompts", "flauz-tl2-s3.md")
S3_DISPATCHED = os.path.join(FLAGS, "s3-dispatched.marker")

_state = {name: {"chars": 0, "tail": "", "stable": 0, "phase": "WAIT",
                 "harvested": False} for name, *_ in LANES}


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


def read_chat_dom(cid, marker):
    tab = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    if tab is None:
        return ""
    try:
        c = CDP(tab["webSocketDebuggerUrl"], timeout=40)
        best = ""
        stable = 0
        for _ in range(8):
            time.sleep(4)
            body = c.eval("document.body.innerText || ''", timeout=25) or ""
            if len(body) > len(best):
                best = body
                stable = 0
            elif len(body) == len(best) and len(best) > 3000:
                stable += 1
                if stable >= 2:
                    break
        c.close()
        return best
    except Exception as e:
        log(f"  read({cid[:8]}) error: {e}")
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
    tail1 = (r1.stdout or "").strip().splitlines()[-1:] if r1.stdout else []
    log(f"  [{name}] harvest_delivery rc={r1.returncode}: {tail1}")
    r2 = subprocess.run([PY, os.path.join(BASE, "fetch_one.py"),
                         chat_id, ws_id, bundle, os.path.join(dest, "root", bundle)],
                        capture_output=True, text=True, timeout=300)
    tail2 = (r2.stdout or "").strip().splitlines()[-1:] if r2.stdout else []
    log(f"  [{name}] fetch_bundle rc={r2.returncode}: {tail2}")
    ok = r1.returncode == 0
    if ok:
        with open(os.path.join(FLAGS, f"{name}.wave2-complete"), "w") as f:
            f.write(f"{int(time.time())} ws={ws_id}\n")
        outbox(f"[TL2 wave2] {name} COMPLETE and harvested to {dest} "
               f"(ws {ws_id[:14]}); delivery tree + root bundle fetched. "
               f"TL landing next.")
    return ok


def dispatch_s3():
    if os.path.exists(S3_DISPATCHED):
        return
    log("[S3] dispatching (slot freed by a completed lane)")
    subprocess.Popen([PY, os.path.join(BASE, "launch_create.py"),
                      "flauz-S3-tl2", S3_PROMPT],
                     stdout=open(os.path.join(BASE, "logs", "s3-dispatch.out"), "a"),
                     stderr=subprocess.STDOUT,
                     start_new_session=True,
                     cwd=BASE)
    with open(S3_DISPATCHED, "w") as f:
        f.write(f"{int(time.time())}\n")
    outbox("[TL2 wave2] a lane completed — S3 (runtime verification) "
           "dispatched into the freed slot.")


def main():
    log(f"=== tl2_wave2_watch start (lanes: {', '.join(l[0] for l in LANES)})")
    while True:
        try:
            wsmap = workspaces_map()
            for name, cid, prefix, bundle, marker, dest in LANES:
                s = _state[name]
                if s["harvested"]:
                    continue
                body = read_chat_dom(cid, marker)
                if not body:
                    continue
                chars = len(body)
                tail = body[-90:].replace("\n", " ")
                hits = body.count(marker)
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
                            dispatch_s3()
                        else:
                            s["stable"] = 0
                    else:
                        log(f"[{name}] COMPLETE but no active workspace; retrying")
            if all(_state[n]["harvested"] for n, *_ in LANES):
                log("=== all wave-2 lanes harvested; watcher exits")
                outbox("[TL2 wave2] all three lanes (A2/S1/S2) harvested — "
                       "landing + S3 watch continue in the TL session.")
                return
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(CADENCE)


if __name__ == "__main__":
    main()
