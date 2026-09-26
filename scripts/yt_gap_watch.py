#!/usr/bin/env python3
"""
yt_gap_watch.py — the ALWAYS-ON four-gap window responder (lesson-150 design).

The mission: the four corpus-pending gaps (theme-picker rows, home resume bar,
healthy subs-feed grid, shorts action rail) need the operator's LOGGED-IN
YouTube window. This daemon makes the resident loop truly "standing ready":
no live lead session required — the moment a logged-in window exists, the
hardened gap ladder fires within ~90s, VLM-verifies the critical capture, and
notifies the operator through the outbox.

THE SIGNAL LAW (lesson-150 — the 20260926-045611 false-positive):
  - A notification-count title ("(15) YouTube") is a HINT only — it raises
    eval frequency but NEVER fires the ladder (yesterday it fired on a
    LOGGED-OUT tab with a stale title).
  - FIRE only on the STRONG signal: a successful eval showing
    #avatar-btn present AND no sign-in link.
  - A stalled/failed eval = UNKNOWN (keep retrying), never logged-out.
  - A "YouTube"-exact title on all YT tabs = logged-out hint (back off).

STATE MACHINE:
  ARMED        -> (strong signal)          -> CAPTURING (fire the ladder)
  CAPTURING    -> (ladder done/timeout)    -> NOTIFYING (VLM verify + outbox)
  NOTIFYING    -> (posted)                 -> WAIT_CLOSE
  WAIT_CLOSE   -> (no YT tabs for 3 rounds OR eval shows logged-out, checked
                   every ~6 min, failure-tolerant)              -> ARMED
  One capture per window session (no gate-fighting, the standing directive).

Output: logs/yt-gap-watch.log  ·  flags/yt-gap-*  ·  outbox notifications.
Run:  python3 launch_detached.py logs/yt-gap-watch.log python3 yt_gap_watch.py
"""
import json, os, subprocess, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "yt-gap-watch.log")
FLAGS = os .path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
LADDER = os.path.join(BASE, "yt_gap_capture.py")
CAPTURE_LOG = os.path.join(BASE, "logs", "yt-gap-capture-auto.log")
os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
os.makedirs(FLAGS, exist_ok=True)

ROUND_S = 45          # poll cadence
EVAL_TIMEOUT = 70     # patient (YouTube stalls evals under load)
CLOSE_ROUNDS = 3      # no-YT-tabs rounds before re-arming
WAIT_EVAL_EVERY = 8   # in WAIT_CLOSE, a login check every N rounds (~6 min)

LOGIN_JS = ("(() => { const s = !!document.querySelector(\"a[aria-label*='Sign in' i]\");"
            " const a = !!document.querySelector('#avatar-btn');"
            " return JSON.stringify({signin: s, avatar: a, title: document.title.slice(0,60)}); })()")

_state = {"name": "ARMED", "since": time.time(), "no_yt_rounds": 0, "rounds": 0,
          "last_capture_out": None}

def log(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] [{_state['name']}] {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def yt_tabs():
    try:
        tabs = json.load(urllib.request.urlopen("http://localhost:9222/json/list", timeout=8))
        return [t for t in tabs if t.get("type") == "page"
                and "youtube.com" in (t.get("url") or "")]
    except Exception:
        return []

def title_hint(tabs):
    """notification-count title = logged-in HINT; bare 'YouTube' = logged-out hint."""
    for t in tabs:
        title = t.get("title", "")
        if title.startswith("(") and "YouTube" in title:
            return "count"
    return "plain" if any(t.get("title") == "YouTube" for t in tabs) else "none"

def strong_login_check(tab):
    """Patient eval on the YT tab. Returns 'in' | 'out' | 'unknown'."""
    import websocket
    try:
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            ws.settimeout(EVAL_TIMEOUT)
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": LOGIN_JS,
                                           "returnByValue": True,
                                           "awaitPromise": True}}))
            deadline = time.time() + EVAL_TIMEOUT
            while time.time() < deadline:
                data = json.loads(ws.recv())
                if data.get("id") == 1:
                    v = data.get("result", {}).get("result", {}).get("value")
                    if v is None:
                        return "unknown"
                    v = json.loads(v)
                    return "in" if (v.get("avatar") and not v.get("signin")) else "out"
        finally:
            try: ws.close()
            except Exception: pass
    except Exception as e:
        log(f"login eval stalled ({type(e).__name__}: {str(e)[:80]}) — unknown, will retry")
    return "unknown"

def fire_ladder():
    log("FIRING the four-gap ladder (detached)")
    p = subprocess.run([sys.executable, LADDER], capture_output=True, text=True,
                       timeout=600)
    with open(CAPTURE_LOG, "a") as f:
        f.write(p.stdout + p.stderr)
    out_dir, verdict = None, {}
    for line in p.stdout.splitlines():
        if line.startswith("[") and " OUT: " in line:
            out_dir = line.split(" OUT: ", 1)[1].strip()
    last = os.path.join(BASE, "flags", "yt-gap-last-capture")
    if os.path.exists(last):
        try:
            parts = open(last).read().strip().splitlines()
            out_dir = out_dir or parts[0]
            verdict = json.loads(parts[1])
        except Exception:
            pass
    log(f"ladder done rc={p.returncode} out={out_dir} verdict={verdict}")
    return out_dir, verdict

def vlm_check(path, prompt):
    try:
        r = subprocess.run(["z-ai", "vision", "-p", prompt, "-i", path,
                            "-o", path + ".vlm.json"],
                           capture_output=True, text=True, timeout=120)
        if os.path.exists(path + ".vlm.json"):
            c = json.load(open(path + ".vlm.json"))["choices"][0]["message"]["content"]
            return c[:600]
    except Exception as e:
        return f"vlm-error: {str(e)[:120]}"
    return "vlm-no-output"

def notify(text):
    entry = {"ts": int(time.time() * 1000), "from": "agent", "text": text}
    with open(OUTBOX, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    log("outbox posted")

def do_capture_cycle():
    out_dir, verdict = fire_ladder()
    picker_verdict = "not-captured"
    if out_dir:
        shot = os.path.join(out_dir, "g1-2-theme-picker.jpg")
        if os.path.exists(shot):
            picker_verdict = vlm_check(
                shot, "Is a YouTube Appearance/theme-picker submenu open in this "
                      "screenshot? If yes, list its exact rows in order with their "
                      "selected state. If no, say NO PICKER and describe what is shown.")
        else:
            shot2 = os.path.join(out_dir, "g1-2-theme-picker-NOT-OPEN.jpg")
            if os.path.exists(shot2):
                picker_verdict = "NOT-OPEN: " + vlm_check(
                    shot2, "Is any YouTube menu or submenu open here? Describe the "
                           "masthead state (avatar present?) and what is on screen.")
    notify(
        "YT GAP WINDOW CAPTURED (auto-responder): the logged-in YouTube window was "
        f"detected and the four-gap ladder fired. Results: {json.dumps(verdict)}. "
        f"The theme-picker verdict: {str(picker_verdict)[:500]}. Captures: {out_dir}. "
        "The lead session should now review the captures, build the gap corpus "
        "(CORPUS grammar per surface, never from memory), and dispatch the gap wave. "
        "If surfaces came back degraded/gate-closed, they stay corpus-pending — "
        "honest records, no fighting.")
    _state["last_capture_out"] = out_dir

def main():
    log(f"yt_gap_watch START — four-gap responder armed (strict signal law, lesson-150)")
    while True:
        _state["rounds"] += 1
        tabs = yt_tabs()
        hint = title_hint(tabs)

        if _state["name"] == "ARMED":
            _state["no_yt_rounds"] = 0
            if not tabs:
                time.sleep(ROUND_S); continue
            do_eval = (hint == "count") or (_state["rounds"] % 2 == 0)
            if do_eval:
                verdict = strong_login_check(tabs[0])
                if verdict == "in":
                    log(f"STRONG SIGNAL — logged-in window (hint={hint})")
                    _state["name"] = "CAPTURING"; _state["since"] = time.time()
                    try:
                        do_capture_cycle()
                    except Exception as e:
                        log(f"capture cycle error: {e}")
                        notify("YT GAP RESPONDER: the capture cycle errored "
                               f"({str(e)[:200]}) — the window may still be open; "
                               "re-trigger manually via yt_gap_capture.py if needed.")
                    _state["name"] = "WAIT_CLOSE"; _state["since"] = time.time()
                    continue
                elif verdict == "out":
                    log(f"eval: logged-out (hint={hint}) — standing by")
                else:
                    log(f"eval unknown (hint={hint}) — will retry")
            else:
                log(f"tabs={len(tabs)} hint={hint} — watching")
            time.sleep(ROUND_S)

        elif _state["name"] == "WAIT_CLOSE":
            if not tabs:
                _state["no_yt_rounds"] += 1
                if _state["no_yt_rounds"] >= CLOSE_ROUNDS:
                    log("window closed — re-arming")
                    _state["name"] = "ARMED"; _state["no_yt_rounds"] = 0
            else:
                _state["no_yt_rounds"] = 0
                if _state["rounds"] % WAIT_EVAL_EVERY == 0:
                    verdict = strong_login_check(tabs[0])
                    if verdict == "out":
                        log("eval shows logged-out — re-arming (same tab may re-login)")
                        _state["name"] = "ARMED"
                    else:
                        log(f"wait_close eval: {verdict} — window still open, standing by")
            time.sleep(ROUND_S)

        else:  # CAPTURING / NOTIFYING are handled synchronously; safety net
            _state["name"] = "WAIT_CLOSE"
            time.sleep(ROUND_S)

if __name__ == "__main__":
    main()
