#!/usr/bin/env python3
"""site_probe.py — resident generation-outage probe.

Site state 2026-10-08 ~02:10Z: completions POST returns an HTML error page
("No response, Please try again later." + SyntaxError '<!doctype') for ALL
generation attempts (agent + regular chat mode). Chats/login/list APIs are
healthy. Suspected backend outage or drained daily quota.

2026-10-09 rebuild note: re-authored after sandbox reset #2 from the TL
session's final version (all fixes of the 2026-10-08 hardening round kept:
tracked probe tab, fresh-tab lifecycle, wedged-tab self-replacement, no
arbitrary-tab fallback, PURE-DETECTOR role).

This daemon probes gently (§8 doctrine: don't burn the fresh window):
  cycle: reload probe tab -> ping -> watch 75s for a REAL assistant reply
  (text beyond the prompt echo). Reply => write flags/site-recovered.txt
  (with timestamp) and exit 0. Otherwise sleep PROBE_INTERVAL and repeat.

2026-10-09 08:0xZ: the wave-specific rekick watchers are RETIRED (wave-
lifecycle law: retire wave automation at wave completion — the W2 spurious
re-dispatch incident taught this). The marker is now INERT telemetry: no
active consumer. w3_redispatch.py (agent-mode canary redispatcher) is the
sole live wave-3 automation and supervises this probe's relaunch; it does
its OWN fresh-tab truth-check and never trusts this marker alone.
"""
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
PROBE_TAB_PREFIX = "784E7732"
PROBE_TAB_FILE = os.path.join(FLAGS, "probe_tab.txt")
PROBE_MSG = "ping2"
PROBE_INTERVAL = int(os.environ.get("PROBE_INTERVAL", "420"))
MAX_CYCLES = int(os.environ.get("PROBE_CYCLES", "40"))


def _tracked_tab_id():
    try:
        return open(PROBE_TAB_FILE).read().strip()
    except Exception:
        return ""


def _track_tab(tab_id):
    with open(PROBE_TAB_FILE, "w") as f:
        f.write(tab_id)


def fresh_probe_tab():
    """Open a NEW homepage tab and track it as probe-owned.

    2026-10-08 13:3xZ fix: the original prefix-matched tab accumulated 30+
    ping turns and its post-reload render started exceeding CDP timeouts —
    cycle() then raised BEFORE the ping was sent, producing false
    still-down verdicts that could mask a real recovery. A fresh tab keeps
    render cost flat. The old any-home-tab fallback was REMOVED: it could
    have adopted the console's operator tab (collision with replayd)."""
    tab = channel.new_tab("https://chat.z.ai/")
    _track_tab(tab["id"])
    time.sleep(6)
    print("[probe] fresh probe tab %s opened" % tab["id"][:8], flush=True)
    return tab


def find_probe_tab():
    want = _tracked_tab_id()
    if want:
        for t in channel.list_tabs():
            if t.get("id") == want:
                return t
    # legacy adoption (pre-state-file world): prefix-matched tab only
    for t in channel.list_tabs():
        if (t.get("id") or "").startswith(PROBE_TAB_PREFIX):
            _track_tab(t["id"])
            return t
    return None


def cycle(ws):
    # hard reload clears the error-state wedge (submit-mute cure)
    try:
        ws.call("Page.reload", {}, timeout=30)
    except Exception:
        pass
    time.sleep(22)
    # clear + focus + insert + submit
    try:
        ws.eval(channel.CLEAR_JS, timeout=15)
    except Exception:
        pass
    time.sleep(0.5)
    ws.eval("(() => { const i = document.querySelector('#chat-input, textarea');"
            " if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=15)
    time.sleep(0.3)
    ws.call("Input.insertText", {"text": PROBE_MSG})
    time.sleep(2)
    try:
        ws.eval(channel.SUBMIT_JS, timeout=15)
    except Exception as e:
        print("[probe] submit err: %s" % str(e)[:60], flush=True)
        return False
    # watch 75s for assistant text beyond the prompt echo
    for i in range(15):
        time.sleep(5)
        try:
            txt = ws.eval("document.body.innerText", timeout=12) or ""
        except Exception:
            continue
        tail = txt[-500:]
        if PROBE_MSG in tail and "No response" in tail:
            return False  # same outage banner
        # a real reply: text after the prompt line that is neither the
        # error banner nor composer chrome
        after = tail.split(PROBE_MSG, 1)[-1] if PROBE_MSG in tail else ""
        junk = ("No response", "SyntaxError", "Deep Think", "Max", "Download",
                "Publish", "Show full message", "Stop", "AutoClaw", "ZCode", "Ali22")
        meaningful = [ln for ln in after.splitlines()
                      if ln.strip() and not any(j in ln for j in junk)]
        if meaningful:
            print("[probe] reply lines: %r" % meaningful[:3], flush=True)
            return True
    return False


def _close_tab(tab):
    try:
        import urllib.request
        urllib.request.urlopen(
            "http://127.0.0.1:9222/json/close/" + tab["id"], timeout=6).read()
        return True
    except Exception:
        return False


def _operator_active_tab():
    """The tab replayd's console currently mirrors (the operator's tab).

    2026-10-09 03:1xZ collision fix: with an ACTIVE operator driving the
    browser through the replay console, any probe tab can be taken over
    (the probe once ended up tracked on the operator's live tab and would
    have pinged into their chat). The probe must NEVER ping the operator's
    active tab — detect and yield."""
    try:
        import json as _json
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:3100/healthz", timeout=5) as r:
            d = _json.loads(r.read().decode())
        return (d.get("active") or "")
    except Exception:
        return ""


def main():
    # 2026-10-09 08:1xZ stale-marker law: a fresh probe generation clears any
    # pre-existing marker at startup. The marker's lifetime is therefore
    # bounded by one probe generation (recovery -> probe exit -> relaunch).
    # Rationale: no live consumer deletes it (forensics 08:0xZ), so a marker
    # could otherwise linger indefinitely and falsely arm a FUTURE
    # wave-watcher generated from the reekick template (which polls for
    # this file). Startup-clearing makes a visible marker always mean
    # "recovered within the current probe generation" — combined with the
    # watcher's 90s double-verify, the spurious-fire surface is ~zero.
    try:
        os.remove(os.path.join(FLAGS, "site-recovered.txt"))
        print("[probe] stale marker cleared at startup", flush=True)
    except FileNotFoundError:
        pass

    # 2026-10-09 02:0xZ semantics fix: marker = RECOVERY (DOWN -> UP
    # transition) only. A deployment that starts while the site is already
    # up never writes a marker (the TL already handled that state; firing
    # would double-dispatch workers). seen_down gates the marker.
    seen_down = False
    for n in range(MAX_CYCLES):
        tab = find_probe_tab()
        if tab is None:
            tab = fresh_probe_tab()
        # operator-collision guard: never ping the console's active tab
        active = _operator_active_tab()
        if active and tab["id"] == active:
            print("[probe] tracked tab IS the operator's active console tab — yielding (fresh tab)", flush=True)
            tab = fresh_probe_tab()
        try:
            ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=45)
        except Exception as e:
            print("[probe] CDP fail: %s" % str(e)[:60], flush=True)
            _close_tab(tab)
            time.sleep(60)
            continue
        cycle_err = None
        try:
            ok = cycle(ws)
        except Exception as e:
            print("[probe] cycle error: %s" % str(e)[:80], flush=True)
            ok = False
            cycle_err = str(e)[:80]
        finally:
            ws.close()
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print("[probe] %s cycle %d -> %s" % (stamp, n, "RECOVERED" if ok else "still-down"), flush=True)
        if ok:
            if not seen_down:
                # site healthy (or healthy since deploy) — keep watching;
                # a marker is only meaningful as a RECOVERY signal.
                time.sleep(PROBE_INTERVAL)
                continue
            with open(os.path.join(FLAGS, "site-recovered.txt"), "w") as f:
                f.write(stamp + "\n")
            print("[probe] RECOVERED at %s — marker written (inert telemetry; no live watcher consumes it; w3_redispatch owns agent-mode recovery + probe relaunch)" % stamp, flush=True)
            # 2026-10-08 10:4xZ de-conflict: the probe is a PURE detector now.
            # The watcher double-verifies health and runs the single
            # authoritative rekick sequence.
            return 0
        seen_down = True
        if cycle_err:
            # a wedged/slow tab must not poison later cycles: replace it
            print("[probe] cycle errored pre-verdict — replacing probe tab", flush=True)
            _close_tab(tab)
            fresh_probe_tab()
        time.sleep(PROBE_INTERVAL)
    print("[probe] exhausted cycles", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
