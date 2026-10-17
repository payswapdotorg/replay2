#!/usr/bin/env python3
"""os_login_watch.py v3 — poll CDP /json for openspace/google tab URL+title changes.

Evidence source for whether the operator has completed the OpenSpace login.
Survives tool-call boundaries: launch via subprocess with start_new_session=True
or `dfork_launch.py logs/os_login_watch.log python3 os_login_watch.py`.

v3 hardening (after recycle-#N ate v2): 
  - self-heal: if CDP is unreachable, keep retrying (the browser may restart)
  - durable log: writes to /home/z/replay2/logs/os_login_watch.log AND mirrors
    a copy to /home/z/my-project/data/os_login_watch.log (my-project survives)
  - login-detect: emits LOGIN_COMPLETE marker line when any tab lands on
    /orgs or any openspace URL other than /login|/forgot-password
"""
import json, time, urllib.request, os, sys

CDP = "http://127.0.0.1:9222/json"
LOGS = ["/home/z/replay2/logs/os_login_watch.log",
        "/home/z/my-project/data/os_login_watch.log"]
PRE_LOGIN = ("/login", "forgot-password", "about:blank")

os.makedirs("/home/z/replay2/logs", exist_ok=True)
os.makedirs("/home/z/my-project/data", exist_ok=True)

def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    for p in LOGS:
        try:
            with open(p, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

def tabs():
    with urllib.request.urlopen(CDP, timeout=5) as r:
        return json.loads(r.read().decode())

def interesting(t):
    u = (t.get("url") or "").lower()
    ti = (t.get("title") or "").lower()
    return ("openspace" in u or "google" in u or "accounts.google" in u or
            "openspace" in ti or "google" in ti)

state = {}  # tabid -> (url, title)
log("watcher v3 started (pid %d)" % os.getpid())
while True:
    try:
        ts = [t for t in tabs() if t.get("type") == "page" and interesting(t)]
    except Exception as e:
        log(f"CDP unreachable: {e!r} (retrying)")
        time.sleep(10)
        continue
    for t in ts:
        tid = t.get("id", "?")
        cur = (t.get("url") or "", t.get("title") or "")
        if state.get(tid) != cur:
            state[tid] = cur
            log(f"TAB {tid[:8]} -> {cur[0][:110]} | {cur[1][:60]}")
            u = cur[0].lower()
            if "openspace" in u and not any(p in u for p in PRE_LOGIN):
                log(f"LOGIN_COMPLETE signal: tab {tid[:8]} at {cur[0][:110]}")
    time.sleep(5)
