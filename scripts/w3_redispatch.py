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
    """Report marker (>= 2 occurrences incl. prompt echo) or branch push.

    14:38Z duplicate-burn lesson: a single ls-remote hiccup (timeout /
    moved-repo redirect) once read a DELIVERED lane as pending and the
    monitor re-dispatched a voided duplicate 7s after TL containment.
    Retry up to 3x; only a tip that is PRESENT and still at base means
    not-delivered. Total check failure assumes DELIVERED (skipping a
    re-kick for one pass is cheap; burning a duplicate dispatch is not).
    """
    rec = live_record(name)
    if not rec:
        return False
    branch = {"w3a": "you/w3a-core", "w3b": "you/w3b-studio",
              "w3c": "you/w3c-reconstruction"}[name]
    tip = ""
    for attempt in range(3):
        try:
            r = subprocess.run(
                ["git", "ls-remote",
                 "https://github.com/payswapdotorg/LikeWise.git",
                 "refs/heads/" + branch],
                cwd=BASE, timeout=30, capture_output=True, text=True)
            out = (r.stdout or "").strip()
            if out:
                tip = out.split()[0]
                break
        except Exception:
            pass
        time.sleep(2)
    if not tip:
        log("delivered(%s): ls-remote failed 3x — assuming delivered (fail-safe)" % name)
        return True
    return not tip.startswith("cd69cf3")


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
                    # 14:3xZ flap lesson: a landed canary does NOT guarantee the
                    # window stays open — the 13:00Z and 14:35Z fan-outs both
                    # VERIFIED submits whose turns never got generation slots.
                    # (a) if the w3a lane is ALREADY delivered (branch moved),
                    # the landed canary is a duplicate turn — void it now (frees
                    # the slot for the real lanes; monitor never re-creates a
                    # delivered lane since delivered() reads the branch tip).
                    # (b) each fanned lane gets up to 3 create->verify cycles:
                    # markers within START_WAIT = turn LIVE; otherwise the
                    # window closed before the turn started — void + retry.
                    if delivered("w3a"):
                        log("canary w3a landed but lane already delivered — voiding duplicate turn")
                        void("w3a", "duplicate canary: w3a lane already delivered (branch moved)")
                    for lane in ("w3b", "w3c"):
                        # 15:2xZ live-lane guard: a re-fan (after a canary
                        # reset from monitor) must NEVER void a live WORKING
                        # lane — create() would hit "already exists" and the
                        # wedge-fix would void+re-create it, killing the turn.
                        # But a stalled record (record live, turn dead) is NOT
                        # protected — it is healed (void + fresh dispatch).
                        if live_record(lane):
                            a2, w2 = check_alive(lane)
                            if a2:
                                log("fan-out %s: live WORKING lane — skipping (protecting)" % lane)
                                continue
                            log("fan-out %s: stalled record (turn dead: %s) — recycling" % (lane, w2))
                            void(lane, "fan-out heal: stalled turn on live record")
                        landed = False
                        for attempt in range(3):
                            create(lane)
                            time.sleep(START_WAIT)
                            ok2, why2 = check_alive(lane)
                            if ok2:
                                log("fan-out %s: turn LIVE (attempt %d)" % (lane, attempt + 1))
                                landed = True
                                break
                            log("fan-out %s: turn not started (%s) — recycling (attempt %d)"
                                % (lane, why2, attempt + 1))
                            void(lane, "fan-out window closed before turn start")
                        if not landed:
                            log("fan-out %s: exhausted 3 attempts" % lane)
                    # window-aware phase selection: if ANY lane is live the
                    # monitor owns them (blind re-creates would burn prompts
                    # into a possibly-closed window); if NO lane landed, the
                    # flap closed mid-fan-out — re-arm the canary so the next
                    # window re-fans with retries (live lanes are skipped by
                    # the guard above).
                    if any(live_record(l) for l in ("w3b", "w3c")):
                        st["phase"] = "monitor"
                        st["dispatched"] = ["w3a", "w3b", "w3c"]
                    else:
                        log("fan-out exhausted with no live lane — re-arming canary for the next window")
                        st["phase"] = "canary"
                        st["dispatched"] = []
                    save_state(st)
                    time.sleep(START_WAIT)
                    continue
                if why in ("no-tab", "no-live-record"):
                    # 13:0xZ wedge class: a live record whose tab vanished
                    # ("no-tab") or a half-created record (sent=false) both
                    # block create() with "already exists" — recycle first.
                    if why == "no-tab":
                        void("w3a", "canary tab lost — recycle for fresh dispatch")
                        close_tabs_for("w3a")
                    if not create("w3a"):
                        void("w3a", "stale half-created record (never sent) — un-wedge")
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
                    # 15:2xZ window-awareness: a lane WITHOUT a live record
                    # needs a real (in-window) dispatch — the blind create
                    # here would burn a full prompt into a possibly-closed
                    # window and leave a stalled record the monitor can't
                    # remedy. Re-arm the canary phase instead: it detects
                    # the next window and re-fans with retries (live lanes
                    # are skipped by the fan-out guard).
                    log("monitor: %s lost its record — re-arming canary phase for window-aware re-dispatch" % name)
                    st["phase"] = "canary"
                    st["dispatched"] = []
                    save_state(st)
                    break
                elif not alive and why in ("no-tab",):
                    # tab closed = the SPA stream died = the turn is dead
                    # (2026-10-02 doctrine); the chat's server-side work
                    # survives — if the worker pushed, delivered() still
                    # sees the tip. Void + canary re-arm for the re-fan.
                    log("monitor: %s tab lost — voiding + re-arming canary" % name)
                    void(name, "tab lost in monitor phase")
                    st["phase"] = "canary"
                    st["dispatched"] = []
                    save_state(st)
                    break
            save_state(st)
            time.sleep(BACKOFF)
            continue

        time.sleep(BACKOFF)


if __name__ == "__main__":
    main()
