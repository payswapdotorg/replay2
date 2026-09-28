#!/usr/bin/env python3
"""tl2_wave3_watch.py — completion watcher + in-window harvester for the
TL2 wave-3 census-closure lanes (F1/F2/F3/F4).

Lanes are read DYNAMICALLY from flags/wave3_lanes.json (written by the
wave-3 login sentinel at dispatch time; F4 is appended when its own
dispatch fires). Per lane: fresh-tab-per-read DOM read (lesson-196: held
tabs wedge; the server tree never carries assistant content) -> on
marker>=2 with a stable tail across two polls: harvest the delivery tree
(via harvest_bearer.py prefix mode — the bundle rides inside the prefix)
DURING the active-pod window -> write the complete flag -> outbox.
When the first lane completes: dispatch F4 once (the freed slot).
When F4 completes and harvests, dispatch its record too. Exit when all
four lanes are harvested.
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
LOG = os.path.join(BASE, "logs", "tl2_wave3_watch.log")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE = os.path.join(FLAGS, "wave3_lanes.json")
PY = "/home/z/.venv/bin/python3"
CADENCE = 120
F4_DISPATCHED = os.path.join(FLAGS, "wave3-f4-dispatched.marker")

_state = {}


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


def load_lanes():
    if not os.path.exists(STATE):
        return []
    try:
        with open(STATE) as f:
            st = json.load(f)
        return st.get("lanes", [])
    except Exception:
        return []


def read_chat_dom(cid):
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
    """chat_id -> workspace id. In-page fetch first (logged-in browser),
    Bearer fallback for logout windows (lesson-198b)."""
    tok = ""
    tok_file = os.path.join(FLAGS, "chat_token")
    if os.path.exists(tok_file):
        try:
            tok = open(tok_file).read().strip()
        except OSError:
            tok = ""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/web-dev/workspaces/user-fc",
            headers={"Authorization": f"Bearer {tok}"} if tok else {})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        items = None
        for k in ("workspaces", "list", "items"):
            if isinstance(data, dict) and isinstance(data.get(k), list):
                items = data[k]
                break
        if items is None and isinstance(data, list):
            items = data
        out = {}
        for w in items or []:
            cid = str(w.get("chat_id") or "").removeprefix("chat-")
            ws = (w.get("function_name") or w.get("workspace_id")
                  or w.get("ws_id") or w.get("id"))
            if cid and ws:
                out[cid] = ws
        if out:
            return out
    except Exception:
        pass
    # fallback: in-page fetch through the live browser (cookie auth)
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
            cid = str(w.get("chat_id") or "").removeprefix("chat-")
            ws = (w.get("function_name") or w.get("workspace_id")
                  or w.get("ws_id") or w.get("id"))
            if cid and ws:
                out[cid] = ws
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


def run_harvest(name, chat_id, ws_id, prefix, dest):
    os.makedirs(dest, exist_ok=True)
    log(f"  [{name}] HARVEST start ws={ws_id}")
    r = subprocess.run([PY, os.path.join(BASE, "harvest_bearer.py"),
                        chat_id, ws_id, prefix + "/",
                        os.path.join(dest, "delivery")],
                       capture_output=True, text=True, timeout=900)
    tail = (r.stdout or "").strip().splitlines()[-1:] if r.stdout else []
    log(f"  [{name}] harvest rc={r.returncode}: {tail}")
    ok = r.returncode == 0
    if ok:
        with open(os.path.join(FLAGS, f"{name}.wave3-complete"), "w") as f:
            f.write(f"{int(time.time())} ws={ws_id}\n")
        outbox(f"[TL2 wave3] {name} COMPLETE and harvested to {dest} "
               f"(ws {str(ws_id)[:14]}). TL landing next.")
    return ok


def dispatch_f4(lanes):
    if os.path.exists(F4_DISPATCHED):
        return
    f4 = next((l for l in lanes if l["name"] == "flauz-F4-tl2"), None)
    if not f4:
        return
    log("[F4] dispatching (slot freed by a completed lane)")
    subprocess.Popen([PY, os.path.join(BASE, "launch_create.py"),
                      "flauz-F4-tl2",
                      os.path.join(BASE, "worker-prompts", "flauz-tl2-f4.md")],
                     stdout=open(os.path.join(BASE, "logs",
                                              "create_flauz-F4-tl2.log"), "a"),
                     stderr=subprocess.STDOUT,
                     start_new_session=True, cwd=BASE)
    with open(F4_DISPATCHED, "w") as f:
        f.write(f"{int(time.time())}\n")
    outbox("[TL2 wave3] a lane completed — F4 (landing-debt sweep) "
           "dispatched into the freed slot.")


def mark_f4_chat(lanes):
    """After F4's create lands, record its chat id into the state file."""
    f4 = next((l for l in lanes if l["name"] == "flauz-F4-tl2"), None)
    if not f4 or f4.get("chat"):
        return
    if not os.path.exists(F4_DISPATCHED):
        return
    reg = os.path.join(FLAGS, "session_registry.jsonl")
    if not os.path.exists(reg):
        return
    import re
    rec = None
    try:
        with open(reg) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("name") == "flauz-F4-tl2" or d.get("session") == "flauz-F4-tl2":
                    rec = d
    except Exception:
        return
    if rec and rec.get("sent") and "/c/" in (rec.get("url") or ""):
        m = re.search(r"/c/([0-9a-f-]{16,})", rec["url"])
        if m:
            f4["chat"] = m.group(1)
            f4["dispatched"] = True
            st = {"lanes": lanes}
            tmp = STATE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(st, f, indent=1)
            os.replace(tmp, STATE)
            log(f"[F4] chat recorded: {f4['chat']}")


def main():
    log("=== tl2_wave3_watch start (dynamic lanes from wave3_lanes.json)")
    while True:
        try:
            lanes = load_lanes()
            if not lanes:
                time.sleep(CADENCE)
                continue
            mark_f4_chat(lanes)
            watch = [l for l in lanes if l.get("chat") and not l.get("harvested")]
            if not watch:
                done = [l for l in lanes if l.get("harvested")]
                if len(done) >= len(lanes) and all(l.get("chat") for l in lanes):
                    log("=== all wave-3 lanes harvested; watcher exits")
                    outbox("[TL2 wave3] all four lanes (F1/F2/F3/F4) "
                           "harvested — landing continues in the TL session.")
                    return
                time.sleep(CADENCE)
                continue
            wsmap = workspaces_map()
            for lane in watch:
                name, cid = lane["name"], lane["chat"]
                marker, prefix, dest = lane["marker"], lane["prefix"], lane["dest"]
                s = _state.setdefault(name, {"chars": 0, "tail": "",
                                             "stable": 0, "phase": "WAIT"})
                body = read_chat_dom(cid)
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
                    log(f"[{name}] {s['phase']}->{phase} chars={chars} "
                        f"hits={hits} tail={tail[:70]!r}")
                    s["phase"] = phase
                s["chars"], s["tail"] = chars, tail
                if phase == "COMPLETE":
                    ws = wsmap.get(cid)
                    if ws:
                        if run_harvest(name, cid, ws, prefix, dest):
                            lane["harvested"] = True
                            st = {"lanes": lanes}
                            tmp = STATE + ".tmp"
                            with open(tmp, "w") as f:
                                json.dump(st, f, indent=1)
                            os.replace(tmp, STATE)
                            dispatch_f4(lanes)
                        else:
                            s["stable"] = 0
                    else:
                        log(f"[{name}] COMPLETE but no active workspace; retrying")
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(CADENCE)


if __name__ == "__main__":
    main()
