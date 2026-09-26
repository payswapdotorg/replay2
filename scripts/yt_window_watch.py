#!/usr/bin/env python3
"""yt_window_watch.py — poll for the operator's YouTube login (the R30-B gate).

Signal layers (YouTube renderers stall CDP evals under load — be patient):
1. /json/list tab TITLE (no CDP): logged-in titles carry notification counts
   ("(94) YouTube") or change from the bare "YouTube" — weak signal alone.
2. A patient eval (90s timeout) every OTHER round: #avatar-btn present =
   LOGGED-IN; the sign-in link present = LOGGED-OUT.

On LOGGED-IN: write flags/yt-loggedin (the lead then runs the captures).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

FLAGS = "/home/z/replay2/scripts/flags"
JS = (
    "(() => { const s = !!document.querySelector(\"a[aria-label*='Sign in' i]\");"
    " const a = !!document.querySelector('#avatar-btn');"
    " return JSON.stringify({signin: s, avatar: a, title: document.title.slice(0,60)}); })()"
)


def tab_titles():
    try:
        tabs = json.load(
            urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=8))
        return [t.get("title", "") for t in tabs
                if "youtube" in (t.get("url") or "") and t.get("type") == "page"]
    except Exception:
        return []


def patient_eval():
    try:
        tabs = channel.list_tabs()
        yt = [t for t in tabs
              if "youtube" in (t.get("url") or "") and t.get("type") == "page"]
        if not yt:
            return None
        ws = channel.CDP(yt[0]["webSocketDebuggerUrl"], timeout=95)
        return json.loads(ws.eval(JS, timeout=90))
    except Exception:
        return None


def main():
    rounds = 0
    while True:
        rounds += 1
        titles = tab_titles()
        state = patient_eval() if rounds % 2 == 0 else None
        logged_in = None
        if state is not None:
            logged_in = bool(state.get("avatar")) and not bool(state.get("signin"))
        elif titles and any(t != "YouTube" and "YouTube" in t for t in titles):
            logged_in = True  # weak title signal — flag for the lead to verify
        line = (f"[{time.strftime('%H:%M:%S')}] titles={titles} "
                f"eval={state} logged_in={logged_in}")
        print(line, flush=True)
        if logged_in:
            open(f"{FLAGS}/yt-loggedin", "w").write(
                line + "\n" + json.dumps(state or {}) + "\n")
            print("YT WINDOW OPEN — flag written; the lead runs the captures.",
                  flush=True)
            return 0
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())
