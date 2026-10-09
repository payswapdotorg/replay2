#!/usr/bin/env python3
"""w3_redispatch.py — patient W3 dispatch loop for agent-mode degradation.

2026-10-09 03:5xZ situation: chat.z.ai regular-mode generation WORKS (probe
pings get replies) but the agent-mode backend rolls or silently kills NEW
agent sessions (three consecutive W3 dispatches: turns never started; one
chat outright rolled). The global-outage probe cannot see this state.

Strategy (canary + patient loop, capacity doctrine adapted):
  - ONE canary session (w3a) at a time — don't triple-burn while the
    agent backend is degraded.
  - cycle: fresh-tab truth-check the live w3a session.
      ALIVE  (work markers rendered)  -> dispatch w3b + w3c (once),
                                         then monitor all three,
                                         retire when all delivered
                                         (report markers >= 2 or pushes).
      DEAD   (no markers after START_WAIT) -> void + close tab +
                                         re-dispatch w3a fresh.
  - between cycles: BACKOFF (default 600s). Never wait passively forever:
    every cycle retries. All state in flags/w3-redispatch-state.json so
    the resident TL can audit/repair at any time.
  - also supervises site_probe.py (global outage detection stays armed).
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
STATE = os.path.join(FLAGS, "w3-redispatch-state.json")
LOG = os.path.join(BASE, "logs", "w3-redispatch.log")
START_WAIT = int(os.environ.get("W3_START_WAIT", "150"))
BACKOFF = int(os.environ.get("W3_BACKOFF", "600"))
PY = sys.executable

WORK_MARKERS = ("Thought Process", "Ran ", "Wrote ", "Terminal",
                "Todo Progress", "Explored", "Read File")


def log(msg):
    # 2026-10-09 08:0xZ fix: this used to print() AND append to LOG — but the
    # daemon's stdout is already redirected to the same log file by
    # dfork_launch.py, so every line appeared twice. File-append only now
    # (works identically whether or not stdout is redirected).
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        print(line, flush=True)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"phase": "canary", "dispatched": [], "cycles": 0}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE)


def live_record(name):
    rec = None
    try:
        for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
            if line.strip():
                r = json.loads(line)
                if r.get("name") == name:
                    if r.get("action") in ("void", "failed", "done"):
                        rec = None  # invalidated
                    elif r.get("sent") and r.get("action") is None:
                        rec = r
    except FileNotFoundError:
        pass
    return rec


def run_step(name, cmd, timeout_s):
    log("step %s (timeout %ss)" % (name, timeout_s))
    try:
        r = subprocess.run(cmd, cwd=BASE, timeout=timeout_s,
                           capture_output=True, text=True)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        ok = r.returncode == 0
        log("step %s rc=%d tail: %s" % (name, r.returncode, out[-200:]))
        return ok
    except subprocess.TimeoutExpired:
        log("step %s TIMEOUT" % name)
        return False
    except Exception as e:
        log("step %s ERROR %s" % (name, e))
        return False


def create(name):
    return run_step("create-" + name,
                    [PY, os.path.join(BASE, "dispatch_worker.py"),
                     "create", name,
                     os.path.join(BASE, "worker-prompts", name + ".md")], 1500)


def void(name, reason):
    return run_step("void-" + name,
                    [PY, os.path.join(BASE, "dispatch_worker.py"),
                     "void", name, reason], 120)


def check_alive(name):
    """Fresh-tab truth-check: work markers rendered = turn actually running."""
    rec = live_record(name)
    if not rec:
        return False, "no-live-record"
    chat = rec["url"].split("/")[-1]
    tab = None
    for t in channel.list_tabs():
        if chat in (t.get("url") or ""):
            tab = t
            break
    if not tab:
        return False, "no-tab"
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            body = c.eval("document.body.innerText || ''", timeout=20) or ""
        finally:
            c.close()
        if any(m in body for m in WORK_MARKERS):
            return True, "work-markers"
        if "No response" in body[-3000:]:
            return False, "error-banner"
        return False, "no-markers"
    except Exception as e:
        return False, "eval-fail:" + str(e)[:40]


def delivered(name):
    """Report marker (>= 2 occurrences incl. prompt echo) or branch push."""
    rec = live_record(name)
    if not rec:
        return False
    chat = rec["url"].split("/")[-1]
    # branch push check (the GOLD signal)
    branch = {"w3a": "you/w3a-core", "w3b": "you/w3b-studio",
              "w3c": "you/w3c-reconstruction"}[name]
    try:
        r = subprocess.run(["git", "ls-remote", "https://github.com/payswapdotorg/LikeWise.git",
                            "refs/heads/" + branch], cwd=BASE, timeout=30,
                           capture_output=True, text=True)
        tip = (r.stdout or "").strip().split()[0] if (r.stdout or "").strip() else ""
        if tip and not tip.startswith("cd69cf3"):
            return True
    except Exception:
        pass
    return False


def close_tabs_for(name):
    rec = live_record(name)
    if not rec:
        return
    chat = rec["url"].split("/")[-1]
    import urllib.request
    for t in channel.list_tabs():
        if chat in (t.get("url") or ""):
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + t["id"], timeout=6).read()
            except Exception:
                pass


def probe_alive():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().replace(b"\x00", b" ").decode(errors="replace")
            if "site_probe.py" in cmd:
                return True
        except Exception:
            continue
    return False


def relaunch_probe():
    try:
        subprocess.Popen(
            [PY, os.path.join(BASE, "dfork_launch.py"),
             os.path.join(BASE, "logs", "site-probe.log"),
             PY, os.path.join(BASE, "site_probe.py")],
            start_new_session=True)
        log("probe daemon relaunched")
    except Exception as e:
        log("probe relaunch FAILED: %s" % e)


def main():
    st = load_state()
    log("w3_redispatch up (phase=%s, dispatched=%s)" % (st["phase"], st.get("dispatched")))
    while True:
        st["cycles"] = st.get("cycles", 0) + 1
        # probe supervision (global outage detection stays armed)
        if not probe_alive():
            relaunch_probe()

        if st["phase"] == "canary":
            rec = live_record("w3a")
            if rec:
                alive, why = check_alive("w3a")
                log("canary w3a: %s (%s)" % ("ALIVE" if alive else "dead", why))
                if alive:
                    log("canary ALIVE — dispatching w3b + w3c")
                    create("w3b")
                    create("w3c")
                    st["phase"] = "monitor"
                    st["dispatched"] = ["w3a", "w3b", "w3c"]
                    save_state(st)
                    time.sleep(START_WAIT)
                    continue
                if why in ("no-tab", "no-live-record"):
                    create("w3a")
                    save_state(st)
                    time.sleep(START_WAIT)
                    continue
                # dead turn on live chat: void + fresh
                void("w3a", "canary turn dead (%s) — agent backend degraded" % why)
                close_tabs_for("w3a")
                create("w3a")
                save_state(st)
                time.sleep(START_WAIT)
                continue
            else:
                log("canary: no live w3a record — fresh dispatch")
                create("w3a")
                save_state(st)
                time.sleep(START_WAIT)
                continue

        if st["phase"] == "monitor":
            pending = []
            for name in ("w3a", "w3b", "w3c"):
                if not delivered(name):
                    pending.append(name)
            log("monitor: pending=%s" % pending)
            if not pending:
                log("ALL THREE W3 LANES DELIVERED — redispatcher retiring")
                save_state(st)
                return
            # re-kick any lane whose turn died but whose chat persists
            for name in pending:
                alive, why = check_alive(name)
                if why == "no-live-record":
                    log("monitor: %s lost its record — re-dispatching" % name)
                    create(name)
                elif not alive and why in ("no-tab",):
                    log("monitor: %s tab lost — re-dispatching" % name)
                    void(name, "tab lost in monitor phase")
                    create(name)
            save_state(st)
            time.sleep(BACKOFF)
            continue

        time.sleep(BACKOFF)


if __name__ == "__main__":
    main()
