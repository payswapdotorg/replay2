#!/usr/bin/env python3
"""outage_monitor.py — the API-path resident monitor for the logout outage.

Every cycle (~5 min):
  1. relay_poll for every registry lane with a workspace — the completion beacon
  2. login recovery probe (a chat.z.ai tab's SPA state: token+signin-wall read)
  3. chats updated_at heartbeat per lane (turn activity server-side)
On a relay beacon: harvest via r35_harvest.py (any name) + log loudly.
On login recovery: log loudly (the lead re-arms tabs/watchers/dispatches).
Heartbeat: flags/outage_heartbeat. Log: logs/outage-monitor.log.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "outage-monitor.log")
PY = sys.executable
POLL_S = 300
CHAT_API = "https://chat.z.ai/api/v1/chats/"


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def beat():
    try:
        open(os.path.join(FLAGS, "outage_heartbeat"), "w").write(str(int(time.time() * 1000)))
    except Exception:
        pass


def token():
    try:
        return open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
    except Exception:
        return ""


def chat_updated(chat_id, tok):
    req = urllib.request.Request(CHAT_API + chat_id, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        rec = d.get("data", d) if isinstance(d, dict) else {}
        return rec.get("updated_at")
    except Exception as e:
        return f"ERR:{str(e)[:40]}"


def lane_chats():
    reg = {}
    try:
        for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("url") and "/c/" in (d.get("url") or "") and not d.get("action"):
                reg[d["name"]] = d["url"].split("/c/")[1].split("/")[0].split("?")[0]
    except FileNotFoundError:
        pass
    return reg


def relay_beacons():
    """name -> True/False relay presence (via relay_poll subprocess, robust)."""
    out = {}
    try:
        r = subprocess.run([PY, os.path.join(BASE, "relay_poll.py")],
                           capture_output=True, text=True, timeout=240)
        for line in (r.stdout or "").splitlines():
            if ": chat=" in line and " relay=" in line:
                name = line.split(":")[0].strip()
                out[name] = "relay=PRESENT" in line
    except Exception as e:
        log(f"relay_poll error: {e}")
    return out


def login_recovered():
    """Probe a chat.z.ai tab for the SPA's signed-in state."""
    try:
        r = subprocess.run(
            [PY, "-c", """
import sys
sys.path.insert(0, '%s')
import channel
t = next((t for t in channel.list_tabs() if 'chat.z.ai' in (t.get('url') or '')), None)
if not t:
    print('no-tab'); sys.exit(0)
c = channel.CDP(t['webSocketDebuggerUrl'], timeout=25)
try:
    r = c.eval(\"(() => { const b = document.body.innerText || '';
        const tok = localStorage.getItem('token');
        return 'signin=' + /sign in|log in/i.test(b) + ' path=' + location.pathname + ' toklen=' + (tok ? tok.length : 0); })()\", timeout=20)
    print(r)
finally:
    try: c.close()
    except Exception: pass
""" % BASE], capture_output=True, text=True, timeout=90)
        out = (r.stdout or "").strip()
        return ("signin=False" in out) and ("toklen=0" not in out), out
    except Exception as e:
        return False, str(e)[:60]


def daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    sys.stdout.flush(); sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1); os.dup2(logfd, 2)
    os.close(devnull); os.close(logfd)


def main():
    log(f"outage monitor up (pid={os.getpid()})")
    harvested = set()
    while True:
        beat()
        reg = lane_chats()
        tok = token()
        for name, chat in sorted(reg.items()):
            if name in harvested:
                continue
            ua = chat_updated(chat, tok)
            log(f"{name}: chat {chat[:8]} updated_at={ua}")
        beacons = relay_beacons()
        for name, present in beacons.items():
            if present and name not in harvested:
                log(f"*** RELAY BEACON: {name} — RELAY-MANIFEST.txt present! Harvest path: r35_harvest.py {name}")
                harvested.add(name)
        ok, detail = login_recovered()
        if ok:
            log(f"*** LOGIN RECOVERED ({detail}) — re-arm tabs/watchers/dispatches")
        time.sleep(POLL_S)


if __name__ == "__main__":
    if "--foreground" in sys.argv:
        main()
    else:
        daemonize()
        main()
