#!/usr/bin/env python3
"""launch_spaced_patient.py — patient retry loop around launch_patient.py.

2026-09-25 (wave-6 phantom grind): the New-Task create-gate swallows sends
while other generations are active (w020f/w020g/w020i1 phantoms: chat shell
500s, packet never committed). spaced_create.py loops the OLD launch_create
path, which lacks the 2026-09-25 send hardening (Escape+DOM-click, send-
readiness gate, freshness gate). This wrapper loops the PROVEN
patient_dispatch path with lesson-142 discipline:

  - one launch_patient <base><n> per attempt, FRESH session name each time
    (registry discipline: names are never reused)
  - PACE: >= 15 min between attempts under an active peak (hot cadence
    feeds the reaping — boot lesson 142)
  - SUCCESS = LANDING + GENERATION: after a server-verified landing, ride
    the chat until an assistant turn actually generates (DOM growth on the
    chat tab); a landed-but-queued chat is reap-bait, not success
  - if the landed chat is reaped before generating, pace and retry

Usage: launch_spaced_patient.py <base-name> <prompt-file> [interval-s, def 900]
Env: SPACED_MAX (default 10 attempts), GEN_WATCH_S (default 2400)
Output: logs/spaced_<base>.log
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(BASE, "logs")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

base_name, prompt_file = sys.argv[1], os.path.abspath(sys.argv[2])
interval = int(sys.argv[3]) if len(sys.argv) > 3 else 900
MAX = int(os.environ.get("SPACED_MAX", "10"))
GEN_WATCH_S = int(os.environ.get("GEN_WATCH_S", "2400"))

os.makedirs(LOGDIR, exist_ok=True)
log_path = os.path.join(LOGDIR, f"spaced_{base_name}.log")
log = open(log_path, "a", buffering=1)


def say(msg):
    line = f"[{base_name}] {time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    log.write(line + "\n")


def registry_entry(name):
    """Latest registry record for name (dict or None)."""
    try:
        rec = None
        for raw in open(REG).read().splitlines():
            if not raw.strip():
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("name") == name:
                rec = d
        return rec
    except FileNotFoundError:
        return None


def chat_alive(cid):
    """True iff the chat detail API answers (not reaped)."""
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(BASE, "chats_http.py"), "detail", cid],
            capture_output=True, text=True, timeout=60)
        return "Traceback" not in out.stdout and "HTTPError" not in (out.stdout + out.stderr)
    except Exception:
        return False


def tab_len_for_chat(cid):
    """DOM innerText length of the tab sitting on this chat (-1 if none)."""
    js = f"""
(() => {{
  const tabs = [];
  return JSON.stringify('probe');
}})()
"""
    try:
        import urllib.request
        import websocket
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
        tab = [t for t in tabs if f"/c/{cid}" in (t.get("url") or "")]
        if not tab:
            return -1
        ws = websocket.create_connection(tab[0]["webSocketDebuggerUrl"], timeout=20)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "document.body.innerText.length",
                                       "returnByValue": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                ws.close()
                return m.get("result", {}).get("result", {}).get("value", -1)
    except Exception:
        return -1


def wait_generation(cid, timeout_s):
    """Ride the landed chat until generation (DOM growth) or timeout."""
    say(f"landed chat {cid[:8]} — riding to generation (watch {timeout_s}s)")
    deadline = time.time() + timeout_s
    last_len = tab_len_for_chat(cid)
    last_change = time.time()
    while time.time() < deadline:
        time.sleep(60)
        if not chat_alive(cid):
            say(f"chat {cid[:8]} REAPED before generation (lesson-142 reap window)")
            return "reaped"
        cur = tab_len_for_chat(cid)
        if cur > last_len + 50:
            say(f"GENERATION CONFIRMED (DOM {last_len} -> {cur})")
            return "generating"
        if cur != last_len:
            last_len = cur
            last_change = time.time()
        elif time.time() - last_change > 600:
            say(f"chat {cid[:8]} static 10min (len={cur}) — treating as queued/reap-bait")
            return "static"
    say(f"generation watch timed out for {cid[:8]}")
    return "timeout"


def wait_verdict(name, timeout=420):
    """Poll create_<name>.log until a verdict line appears or timeout."""
    cl = os.path.join(LOGDIR, f"create_{name}.log")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            tail = open(cl).read()[-400:]
        except FileNotFoundError:
            time.sleep(10)
            continue
        if "server-verified packet landing" in tail or "SENT-VERIFIED" in tail:
            return "landed"
        if "send FAILED server-side" in tail:
            return "failed"
        time.sleep(10)
    return "timeout"


say(f"spaced patient loop: prompt={os.path.basename(prompt_file)} "
    f"interval={interval}s max={MAX} (lesson-142 pacing)")
for attempt in range(1, MAX + 1):
    name = f"{base_name}{attempt}"
    say(f"attempt {attempt}/{MAX} as {name}")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_patient.py"), name, prompt_file],
        capture_output=True, text=True, timeout=120)
    out = (r.stdout or "").strip().splitlines()
    say(f"launcher: {out[-1][:100] if out else (r.stderr or '')[:100]}")
    verdict = wait_verdict(name)
    say(f"send verdict: {verdict}")
    if verdict == "landed":
        rec = registry_entry(name) or {}
        url = rec.get("url") or ""
        cid = url.split("/c/")[-1].split("/")[0].split("?")[0] if "/c/" in url else ""
        if cid:
            g = wait_generation(cid, GEN_WATCH_S)
            if g == "generating":
                say(f"SUCCESS: {name} landed AND generating (chat {cid[:8]})")
                sys.exit(0)
            # reaped / static / timeout — pace and retry
        else:
            say("WARNING: landed but registry url missing — cannot ride; retrying")
    if attempt < MAX:
        say(f"sleeping {interval}s before next attempt (lesson-142 pacing)")
        time.sleep(interval)
say(f"EXHAUSTED {MAX} attempts without landing+generation")
sys.exit(4)
