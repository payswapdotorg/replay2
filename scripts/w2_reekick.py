#!/usr/bin/env python3
"""w2_reekick.py — one-shot recovery watcher for the W2 workers.

2026-10-09 rebuild note: re-authored after sandbox reset #2 from the TL
session's final version (closed-loop supervision, marker hygiene, probe
supervision, w2c tab-ensure + fresh-dispatch fallback).

Context (2026-10-08 → 09): chat.z.ai had a site-wide generation outage
from ~02:05Z. The three W2 worker sessions dispatched at 01:33Z all
errored; w2a/w2b chats were rolled back by the site (voided in the
registry); w2c's chat record persisted. site_probe.py probes every 7 min
and writes flags/site-recovered.txt on the first REAL assistant reply.

This watcher (resident, survives the session reaper via dfork):
  1. supervise + poll every 60s for flags/site-recovered.txt;
  2. on marker: DOUBLE-VERIFY generation health on the probe tab
     (fresh "ping3" turn, 90s watch for a meaningful reply).
       - verify FAILS  => flap: clear marker, relaunch site_probe.py,
         keep watching (closed loop — no orphaned stale markers).
       - verify PASSES => proceed;
  3. ensure a tab sits on the live w2c chat; re-kick it via
     native_resubmit.py (nudge file); fresh-dispatch fallback if the
     chat was rolled after all;
  4. re-dispatch w2a fresh (dispatch_worker.py create w2a w2a.md);
  5. re-dispatch w2b fresh (dispatch_worker.py create w2b w2b.md);
  6. write flags/w2-reekick-done.json with per-step outcomes.
     Zero success => clear marker, relaunch probe, loop back to
     supervision. Partial/full success => retire (resident TL takes
     over from the summary JSON on its next watch cycle).
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
MARKER = os.path.join(FLAGS, "site-recovered.txt")
DONE = os.path.join(FLAGS, "w2-reekick-done.json")
LOG = os.path.join(FLAGS, "w2-reekick.log")
PROBE_TAB_PREFIX = "784E7732"
VERIFY_MSG = "ping3"

W2C_CHAT = "eaaa087b-8669-404c-a544-134d51ac375f"
NUDGE = os.path.join(BASE, "worker-prompts", "w2-nudge.txt")
W2A_PROMPT = os.path.join(BASE, "worker-prompts", "w2a.md")
W2B_PROMPT = os.path.join(BASE, "worker-prompts", "w2b.md")

PY = sys.executable

JUNK = ("No response", "SyntaxError", "Deep Think", "Max", "Download",
        "Publish", "Show full message", "Stop", "AutoClaw", "ZCode", "Ali22",
        "ping3", "Thinking", "Generating", "typing…", "New Chat", "Loading",
        "Meet Your AI Agents", "Code faster", "Automate more", "Share")


def log(msg):
    line = "[reekick %s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def relaunch_probe():
    try:
        subprocess.Popen(
            [PY, os.path.join(BASE, "dfork_launch.py"),
             os.path.join(BASE, "logs", "site-probe.log"),
             PY, os.path.join(BASE, "site_probe.py")],
            start_new_session=True)
        log("probe daemon relaunched (fresh horizon)")
    except Exception as e:
        log("probe relaunch FAILED: %s" % e)


def verify_health():
    """Fresh ping on the probe tab; True only on a REAL assistant reply.

    2026-10-08 13:3xZ fix: NEVER fall back to 'any chat.z.ai tab' — that
    could ping inside the w2c worker chat or the console's operator tab.
    Use the probe's tracked tab (flags/probe_tab.txt, written by
    site_probe.py); if absent, open a fresh homepage tab of our own."""
    tab = None
    try:
        want = open(os.path.join(FLAGS, "probe_tab.txt")).read().strip()
    except Exception:
        want = ""
    if want:
        for t in channel.list_tabs():
            if t.get("id") == want:
                tab = t
                break
    if not tab:
        for t in channel.list_tabs():
            if (t.get("id") or "").startswith(PROBE_TAB_PREFIX):
                tab = t
                break
    if not tab:
        try:
            tab = channel.new_tab("https://chat.z.ai/")
            time.sleep(6)
            log("verify: opened fresh verification tab %s" % tab["id"][:8])
        except Exception as e:
            log("verify: no usable tab (open failed: %s) -> DOWN" % str(e)[:60])
            return False
    if not tab:
        log("verify: no browser tab available -> treat as DOWN")
        return False
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
    try:
        try:
            c.call("Page.reload", {}, timeout=30)
        except Exception:
            pass
        time.sleep(20)
        try:
            c.eval(channel.CLEAR_JS, timeout=15)
        except Exception:
            pass
        time.sleep(0.5)
        c.eval("(() => { const i = document.querySelector('#chat-input, textarea');"
               " if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=15)
        time.sleep(0.3)
        c.call("Input.insertText", {"text": VERIFY_MSG})
        time.sleep(2)
        try:
            c.eval(channel.SUBMIT_JS, timeout=15)
        except Exception as e:
            log("verify: submit error %s" % str(e)[:80])
            return False
        for _ in range(18):  # 90s
            time.sleep(5)
            try:
                txt = c.eval("document.body.innerText", timeout=12) or ""
            except Exception:
                continue
            tail = txt[-700:]
            if VERIFY_MSG in tail and "No response" in tail:
                log("verify: outage banner still present -> DOWN")
                return False
            after = tail.split(VERIFY_MSG, 1)[-1] if VERIFY_MSG in tail else ""
            meaningful = [ln for ln in after.splitlines()
                          if ln.strip() and not any(j in ln for j in JUNK)]
            if meaningful:
                log("verify: REAL reply %r" % meaningful[:2])
                return True
        log("verify: no meaningful reply within 90s -> DOWN")
        return False
    finally:
        c.close()


def ensure_w2c_tab():
    """native_resubmit needs an open tab on the chat; open one if the
    tracked tab vanished (fresh tabs on a LIVE chat land correctly — only
    dead/rolled chats redirect to the homepage)."""
    for t in channel.list_tabs():
        if W2C_CHAT in (t.get("url") or ""):
            log("ensure_w2c_tab: tab present (%s)" % t["id"][:8])
            return True
    try:
        tab = channel.new_tab("https://chat.z.ai/c/" + W2C_CHAT)
        time.sleep(8)
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            href = c.eval("location.href", timeout=15) or ""
            if W2C_CHAT in href:
                log("ensure_w2c_tab: fresh tab landed on chat OK")
                return True
            log("ensure_w2c_tab: fresh tab REDIRECTED to %s — chat may be rolled" % href[:60])
            return False
        finally:
            c.close()
    except Exception as e:
        log("ensure_w2c_tab: open failed: %s" % e)
        return False


def run_step(name, cmd, timeout_s):
    log("step %s: %s (timeout %ss)" % (name, " ".join(cmd[:4]), timeout_s))
    try:
        r = subprocess.run(cmd, cwd=BASE, timeout=timeout_s,
                           capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        ok = r.returncode == 0
        log("step %s rc=%d tail: %s" % (name, r.returncode, out.strip()[-400:]))
        return ok, out.strip()[-1500:]
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"") + (e.stderr or b"")).decode(errors="replace")
        log("step %s TIMEOUT tail: %s" % (name, out.strip()[-300:]))
        return False, "TIMEOUT: " + out.strip()[-800:]
    except Exception as e:
        log("step %s ERROR: %s" % (name, e))
        return False, str(e)[:500]


def _probe_alive():
    """True if a site_probe.py process is running (any pid)."""
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


def _clear_marker():
    try:
        os.remove(MARKER)
    except Exception:
        pass


def _wait_for_marker():
    """Block until the recovery marker appears; keep the probe alive
    throughout (relaunch on death/exhaustion)."""
    last_probe_check = 0.0
    while not os.path.exists(MARKER):
        time.sleep(60)
        # supervisor duty: the probe must never die silently during a
        # long outage (its 120-cycle horizon can exhaust before the site
        # recovers — e.g. a daily quota window). Relaunch it; the probe
        # is idempotent and adopts its tracked tab.
        if time.time() - last_probe_check > 300:
            last_probe_check = time.time()
            if not _probe_alive():
                log("probe daemon DEAD with no marker — relaunching (outage outlasted horizon?)")
                relaunch_probe()


def main():
    log("watcher up (supervision loop)")
    while True:
        _wait_for_marker()
        log("recovery marker seen: %s" % open(MARKER).read().strip()[:100])
        time.sleep(15)  # let the site settle past the first good response

        if not verify_health():
            # flap: the marker is stale — clear it, relaunch the probe, and
            # KEEP WATCHING (previously this path exited and left nobody
            # watching a stale marker).
            log("double-verify FAILED (flap) — clearing marker, relaunching probe, continuing watch")
            _clear_marker()
            relaunch_probe()
            continue

        log("double-verify PASSED — beginning rekick sequence")

        results = {}

        # 0) make sure a tab sits on the live w2c chat (its tracked tab may
        #    have been closed/rolled during the outage)
        ensure_w2c_tab()

        # 1) w2c on its live chat (chat record persists server-side; the
        #    nudge re-drives the turn through the SPA composer)
        ok, out = run_step("w2c-nudge",
                           [PY, os.path.join(BASE, "native_resubmit.py"),
                            W2C_CHAT, NUDGE, "--label", "w2c"], 600)
        results["w2c"] = {"ok": ok, "tail": out[-600:]}

        # 1b) if the chat tab could not be established (chat rolled after all),
        #     fall back to a FRESH w2c dispatch with the full original prompt
        if not results["w2c"]["ok"] and not ensure_w2c_tab():
            log("w2c chat unrecoverable — falling back to fresh dispatch")
            ok, out = run_step("w2c-create",
                               [PY, os.path.join(BASE, "dispatch_worker.py"),
                                "void", "w2c", "chat rolled during outage"], 300)
            ok, out = run_step("w2c-create",
                               [PY, os.path.join(BASE, "dispatch_worker.py"),
                                "create", "w2c",
                                os.path.join(BASE, "worker-prompts", "w2c.md")], 1800)
            results["w2c"] = {"ok": ok, "tail": out[-600:], "fallback": "fresh-dispatch"}

        # 2) w2a fresh dispatch
        ok, out = run_step("w2a-create",
                           [PY, os.path.join(BASE, "dispatch_worker.py"),
                            "create", "w2a", W2A_PROMPT], 1800)
        results["w2a"] = {"ok": ok, "tail": out[-600:]}

        # 3) w2b fresh dispatch
        ok, out = run_step("w2b-create",
                           [PY, os.path.join(BASE, "dispatch_worker.py"),
                            "create", "w2b", W2B_PROMPT], 1800)
        results["w2b"] = {"ok": ok, "tail": out[-600:]}

        summary = {"ts": int(time.time()), "results": results,
                   "any_ok": any(v["ok"] for v in results.values())}
        with open(DONE, "w") as f:
            json.dump(summary, f, indent=2)
        log("reekick sequence complete: any_ok=%s" % summary["any_ok"])

        if summary["any_ok"]:
            # partial/full success — the resident TL takes over from the
            # summary JSON on its next watch cycle; the watcher retires.
            return
        # zero success: the site flapped down mid-sequence — clear the
        # stale marker, relaunch the probe, and loop back to supervision
        # (previously this exited and orphaned the marker).
        log("zero steps succeeded — clearing marker, relaunching probe, resuming watch")
        _clear_marker()
        relaunch_probe()


if __name__ == "__main__":
    main()
