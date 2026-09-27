#!/usr/bin/env python3
"""tl1_admission_sentinel.py — autonomous capacity-gate recovery (2026-09-27).

Context: the platform's agents-mode generation gate (evening-peak load
shedding). Three TL1 chats hold server-delivered packets but were never
admitted (user-last, zero assistant records). The outage hold protects the
queue positions (no assault churn); plain-chat generation works, so the
gate is agents-specific and will lift with off-peak capacity.

This sentinel:
  1. Polls each chat's history server-side every POLL_SECS (read-only).
  2. Every PROBE_EVERY_SECS, sends ONE lightweight begin-nudge via
     stage_send.py to the next chat that has NO assistant record
     (round-robin). A dropped send is harmless (the capacity gate's silent
     drop); a landed send is exactly the begin-directive we want.
     A landed nudge is detected server-side (user message count grows) —
     if generation then opens (assistant record appears), that chat is
     ADMITTED.
  3. On ANY admission: remove flags/outage_hold.txt (restores the watchers'
     full protection), outbox notice.
  4. Exits when every live chat has an assistant record (all turns open —
     the queue_watch watchers own everything from there).

Registry truth for tab ids (they roll on assault); chat ids fixed.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
sys.path.insert(0, BASE)

POLL_SECS = 120
PROBE_EVERY_SECS = 900        # one probe per 15 min
GIVE_UP_AFTER = 16 * 3600
HOLD = os.path.join(FLAGS, "outage_hold.txt")
LOGP = os.path.join(BASE, "logs", "tl1_admission.log")

CHATS = [
    ("tl1-b-002", "ea491944-951a-4796-92a5-96e89dd3e0a4"),
    ("tl1-c-003", "f737546b-520b-4712-9d18-04643c150f8d"),
    ("tl1-a-004", "c51b52ae-e290-4f8f-a1a9-043ae2c0cf5f"),
]

NUDGE = ("Begin the work order now — proceed with your packet from STEP ZERO. "
         "If you already began, continue exactly where you are. "
         "(Operational directive from the Tech Lead; duplicate-safe.)\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": text}) + "\n")
    except OSError:
        pass


def token():
    return open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')


def chat_state(cid):
    """(n_user_msgs, last_role) via the history endpoint (server truth)."""
    try:
        req = urllib.request.Request(f"https://chat.z.ai/api/v1/chats/{cid}",
                                     headers={"Authorization": f"Bearer {token()}"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
        inner = data.get("chat") or data
        msgs = (inner.get("history") or {}).get("messages") or {}
        vals = sorted(msgs.values(), key=lambda m: m.get("timestamp") or 0)
        if not vals:
            return (0, None)
        return (sum(1 for m in vals if m.get("role") == "user"),
                vals[-1].get("role"))
    except Exception:
        return (None, None)   # probe failure — treat as unknown


def registry_tab(name):
    last = None
    try:
        for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
            rec = json.loads(line)
            if rec.get("name") == name:
                last = rec
    except OSError:
        return None
    return (last.get("tab_id") or "")[:8] if last else None


def send_nudge(name, chat):
    tab = registry_tab(name)
    if not tab:
        log(f"{name}: no registry tab — probe skipped")
        return False
    mf = os.path.join(FLAGS, f"admission-nudge-{name}.txt")
    with open(mf, "w") as f:
        f.write(NUDGE)
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "stage_send.py"), tab, mf, chat[:8]],
        cwd=BASE, timeout=300, capture_output=True, text=True)
    out = (r.stdout or "").strip()
    ok = "SENT" in out and "NOT SENT" not in out
    log(f"{name}: probe nudge -> {'SENT' if ok else 'dropped'} ({out[-90:]})")
    return ok


def main():
    started = time.time()
    last_probe = 0
    probe_i = 0
    admitted = {name: False for name, _ in CHATS}
    hold_removed = False
    log(f"admission sentinel up — {len(CHATS)} chats, probes every "
        f"{PROBE_EVERY_SECS // 60} min")
    outbox("[TL1] admission sentinel armed — the agents capacity gate is "
           "probed round-robin; on the first admission the hold lifts and "
           "each session receives its begin-directive. — TL1")
    while True:
        all_admitted = True
        for name, cid in CHATS:
            if admitted[name]:
                continue
            n_user, last_role = chat_state(cid)
            if last_role is None and n_user is None:
                log(f"{name}: probe failed — retry next cycle")
                all_admitted = False
                continue
            if last_role == "assistant":
                admitted[name] = True
                log(f"{name}: ADMITTED (assistant record server-side)")
                outbox(f"[TL1] {name} ADMITTED — generation open.")
                continue
            all_admitted = False
        # gate-open side effects (once)
        if any(admitted.values()) and not hold_removed:
            try:
                os.remove(HOLD)
                log("outage hold REMOVED — full watcher protection restored")
                outbox("[TL1] capacity gate OPEN — outage hold lifted; "
                       "watchers back to full protection.")
            except FileNotFoundError:
                pass
            hold_removed = True
        if all_admitted:
            log("ALL SESSIONS ADMITTED — exiting (watchers own the rest)")
            outbox("[TL1] all three sessions admitted and generating — the "
                   "normal harvest->gates->PR->merge cycle resumes per session.")
            return 0
        # probe cadence: only while some session is still gated
        now = time.time()
        if now - last_probe > PROBE_EVERY_SECS and not all(admitted.values()):
            pend = [(n, c) for n, c in CHATS if not admitted[n]]
            name, cid = pend[probe_i % len(pend)]
            probe_i += 1
            try:
                send_nudge(name, cid)
            except Exception as e:
                log(f"{name}: probe exception {e!r}")
            last_probe = now
        if time.time() - started > GIVE_UP_AFTER:
            log("gave up after 16h — standing down (Lead re-arms manually)")
            outbox("[TL1] admission sentinel: 16h window expired without "
                   "admission — Lead attention required.")
            return 1
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    sys.exit(main())
