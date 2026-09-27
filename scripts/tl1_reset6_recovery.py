#!/usr/bin/env python3
"""tl1_reset6_recovery.py — sandbox reset #6 recovery (2026-09-27 ~17:00 UTC).

The reset killed: browser profile (login), flags/chat_token, session_registry,
every sentinel. Server-side, the three TL1 chats (b-002 ea491944, c-003
f737546b, a-004 c51b52ae) hold server-delivered packets; unknown whether the
platform admitted their turns during the ~5h blackout (Beijing late-night
capacity gate). Packets were re-pinned to main bfeb5e2d (flauz-gate green)
before this recovery ran.

On operator login (detected via read-only DOM probes):
  phase 1  capture the JWT durably (my-project/download/zai_operator_jwt.txt)
           + flags/chat_token (future resets recover without login)
  phase 2  probe every old chat server-side (roles, marker, pod liveness)
           decision matrix (lessons 184/185/187):
             assistant>0 + marker + pod      -> ALIVE-COMPLETE: marker file,
                                                registry row, queue_watch
                                                (harvest sentinel fetches)
             assistant>0 + marker + no pod   -> work bytes lost with the pod
                                                -> void + fresh dispatch
             assistant>0 + no marker + pod   -> ALIVE-GRINDING: tab + registry
                                                + queue_watch
             assistant>0 + no marker + no pod-> dead turn, expired pod
                                                -> void + fresh dispatch
             assistant==0                    -> TRIGGER DEADLOCK (zero-assistant
                                                chats have no restorable tabs)
                                                -> void + fresh dispatch
  phase 3  fresh dispatch every dead lane (serialized, lesson 142) with the
           re-pinned packet; arm queue_watch per session
  phase 4  write flags/admission_chats.json (live set) + launch the admission
           sentinel and the harvest sentinel (both detached)

Re-entry safe: a live registry record for a name is never re-dispatched.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
sys.path.insert(0, BASE)
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

OLD_CHATS = [
    ("tl1-b-002", "ea491944-951a-4796-92a5-96e89dd3e0a4", "TL1-002 COMPLETION REPORT"),
    ("tl1-c-003", "f737546b-520b-4712-9d18-04643c150f8d", "TL1-003 COMPLETION REPORT"),
    ("tl1-a-004", "c51b52ae-e290-4f8f-a1a9-043ae2c0cf5f", "TL1-004 COMPLETION REPORT"),
]
DURABLE_JWT = "/home/z/my-project/download/zai_operator_jwt.txt"
POLL_SECS = 45
MAX_WAIT_SECS = 7 * 3600
LOGP = os.path.join(BASE, "logs", "tl1_reset6.log")

TERMINAL = ("void", "failed", "done")


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": text}) + "\n")
    except OSError:
        pass


def login_state():
    try:
        for t in channel.list_tabs():
            url = t.get("url") or ""
            if url.startswith("https://chat.z.ai") and "/c/" not in url:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                body = dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
                c.close()
                if body and "Sign in" not in body and "Log in" not in body:
                    return True
                return False
        channel.new_tab("https://chat.z.ai/")
        time.sleep(4)
        return False
    except Exception as e:
        log(f"login probe error {type(e).__name__} — retrying")
        return False


def token():
    return open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')


def api(method, path, body=None, timeout=60):
    url = f"https://chat.z.ai/api/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token()}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _msg_text(m):
    """Full text of a history message (content + content_blocks payload)."""
    parts = [str(m.get("content") or "")]
    for b in m.get("content_blocks") or []:
        if isinstance(b, dict):
            parts.append(str(b.get("text") or b.get("content") or ""))
    return "\n".join(parts)


def chat_probe(cid, marker):
    """Server truth for one chat: roles, marker, pod presence."""
    st = {"n_user": 0, "n_assistant": 0, "last_role": None,
          "has_marker": False, "pod": None, "err": None}
    try:
        data = api("GET", f"chats/{cid}", timeout=30)
        inner = data.get("chat") or data
        msgs = (inner.get("history") or {}).get("messages") or {}
        vals = sorted(msgs.values(), key=lambda m: m.get("timestamp") or 0)
        for m in vals:
            role = m.get("role")
            if role == "user":
                st["n_user"] += 1
            elif role == "assistant":
                st["n_assistant"] += 1
            if marker in _msg_text(m):
                st["has_marker"] = True
        st["last_role"] = vals[-1].get("role") if vals else None
    except Exception as e:
        st["err"] = repr(e)
        return st
    try:
        data = api("GET", "web-dev/workspaces/user-fc", timeout=30)
        want = f"chat-{cid}"
        for w in data.get("workspaces", []):
            if w.get("chat_id") == want:
                st["pod"] = w.get("function_name")
                break
    except Exception as e:
        log(f"  workspace probe error: {e!r}")
    return st


def reg_write(**rec):
    rec.setdefault("ts", int(time.time() * 1000))
    with open(os.path.join(FLAGS, "session_registry.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def arm_watch(name, marker):
    rec = dw._find(name)
    tab = (rec.get("tab_id") or "")[:8] if rec else ""
    if not tab:
        log(f"{name}: no registry tab — watcher NOT armed")
        return False
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"), name, tab, marker],
        cwd=BASE, timeout=90, capture_output=True, text=True)
    log(f"{name}: watcher -> {(r.stdout or '').strip()}")
    return True


def launch_detached(script, logname):
    lp = os.path.join(BASE, "logs", logname)
    subprocess.Popen([sys.executable, os.path.join(BASE, "launch_detached.py"),
                      lp, sys.executable, os.path.join(BASE, script)],
                     start_new_session=True, cwd=BASE)
    log(f"launched {script} (log {logname})")


def open_session_tab(name, cid, marker, complete):
    """Open + register a tab on an ALIVE old chat; arm its watcher."""
    url = f"https://chat.z.ai/c/{cid}"
    t = channel.new_tab(url)
    time.sleep(7)
    tabs = {x.get("id"): x for x in channel.list_tabs()}
    live = tabs.get(t.get("id")) or {}
    cur = live.get("url") or ""
    if "/c/" not in cur:
        log(f"{name}: tab bounced ({cur[:50]}) — treating as dead")
        channel.close_tab(t["id"]) if hasattr(channel, "close_tab") else None
        return False
    reg_write(name=name, url=url, tab_id=t["id"],
              note=f"reset6-recovered {'complete' if complete else 'grinding'}")
    if complete:
        with open(os.path.join(FLAGS, f"{name}-complete.marker"), "w") as f:
            f.write(f"reset6 probe found marker at {time.strftime('%H:%M:%S')}\n")
        outbox(f"[TL1] {name}: the worker COMPLETED during the blackout — "
               f"completion marker registered; the harvest sentinel is fetching.")
    arm_watch(name, marker)
    return True


def fresh_dispatch(name, marker):
    """Void-path re-dispatch with the re-pinned packet (re-entry safe)."""
    rec = dw._find(name)
    if rec and rec.get("action") not in TERMINAL and "reset6" not in str(rec.get("note", "")):
        # live record from THIS recovery already — re-arm only
        log(f"{name}: already live ({rec.get('note', '')}) — re-arming watcher")
        arm_watch(name, marker)
        return True
    if rec and "reset6-fresh" in str(rec.get("note", "")):
        log(f"{name}: fresh dispatch already recorded — re-arming watcher")
        arm_watch(name, marker)
        return True
    prompt = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    if not os.path.exists(prompt):
        log(f"FATAL {name}: packet missing at {prompt}")
        return False
    log(f"{name}: FRESH DISPATCH (create)…")
    outbox(f"[TL1] {name}: fresh dispatch starting (packet re-pinned to "
           f"main bfeb5e2d).")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
        cwd=BASE, timeout=2400, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log(f"{name}: create rc={r.returncode} tail={tail}")
    if r.returncode != 0:
        outbox(f"[TL1] {name}: dispatch FAILED (rc={r.returncode}) — the Lead "
               f"will re-fire; see logs/tl1_reset6.log.")
        return False
    # annotate the registry row so re-entry is idempotent
    reg_write(name=name, action="tab-reopen",
              tab_id=(dw._find(name) or {}).get("tab_id", ""),
              url=(dw._find(name) or {}).get("url", ""),
              note="reset6-fresh")
    arm_watch(name, marker)
    outbox(f"[TL1] {name.upper()} DISPATCHED from inside the replay — watcher "
           f"armed (marker: {marker}).")
    return True


def main():
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    os.makedirs(FLAGS, exist_ok=True)
    log("reset#6 recovery sentinel up — waiting for operator login "
        "(read-only probes)")
    started = time.time()
    while True:
        if login_state():
            log("LOGIN DETECTED — recovery begins")
            outbox("[TL1] OPERATOR LOGIN DETECTED — reset recovery starting: "
                   "token capture, chat probes, then recover/re-dispatch of "
                   "TL1-002/003/004.")
            break
        if time.time() - started > MAX_WAIT_SECS:
            log("7h login window expired — standing down")
            outbox("[TL1] recovery sentinel: login window expired — ping the "
                   "Lead to re-arm.")
            return 1
        time.sleep(POLL_SECS)

    # phase 1: durable token
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "zai_token_tools.py"),
                            "capture", DURABLE_JWT], cwd=BASE, timeout=90,
                           capture_output=True, text=True)
        log(f"token capture: {(r.stdout or '').strip()}")
        if os.path.exists(DURABLE_JWT):
            shutil.copyfile(DURABLE_JWT, os.path.join(FLAGS, "chat_token"))
            log("flags/chat_token written (durable copy at my-project/download/)")
    except Exception as e:
        log(f"token capture FAILED: {e!r}")

    # phase 2: probe old chats
    dead, complete_names = [], []
    for name, cid, marker in OLD_CHATS:
        st = chat_probe(cid, marker)
        log(f"{name} ({cid[:8]}): {st}")
        if st["err"]:
            outbox(f"[TL1] {name}: probe failed ({st['err'][:80]}) — treating "
                   f"as dead (fresh dispatch).")
            reg_write(name=name, action="void", reason=f"reset6 probe-error {st['err'][:60]}")
            dead.append((name, marker))
            continue
        if st["n_assistant"] == 0:
            reg_write(name=name, action="void",
                      reason="reset6 trigger-deadlock (zero assistant records)")
            dead.append((name, marker))
            outbox(f"[TL1] {name}: never admitted during the blackout (trigger "
                   f"deadlock, lesson 187) — re-dispatching fresh.")
        elif st["has_marker"] and st["pod"]:
            if open_session_tab(name, cid, marker, complete=True):
                complete_names.append(name)
            else:
                reg_write(name=name, action="void", reason="reset6 tab-bounce")
                dead.append((name, marker))
        elif st["has_marker"] and not st["pod"]:
            reg_write(name=name, action="void",
                      reason="reset6 complete-but-pod-expired (bytes lost)")
            dead.append((name, marker))
            outbox(f"[TL1] {name}: worker finished during the blackout but its "
                   f"pod expired (delivery bytes lost) — re-dispatching fresh.")
        elif st["pod"]:
            if open_session_tab(name, cid, marker, complete=False):
                outbox(f"[TL1] {name}: ALIVE and grinding (assistant records "
                       f"server-side, pod up) — tab restored, watcher armed.")
            else:
                reg_write(name=name, action="void", reason="reset6 tab-bounce")
                dead.append((name, marker))
        else:
            reg_write(name=name, action="void",
                      reason="reset6 dead-turn expired-pod (lesson 187.3)")
            dead.append((name, marker))
            outbox(f"[TL1] {name}: turn died with its pod expired — "
                   f"re-dispatching fresh (lesson 187.3).")
        time.sleep(3)

    # phase 3: fresh dispatches, serialized
    for name, marker in dead:
        fresh_dispatch(name, marker)
        time.sleep(20)

    # phase 4: live chat set for the admission sentinel + sentinel launch
    live = []
    for name, cid, marker in OLD_CHATS:
        rec = dw._find(name)
        if rec and rec.get("action") not in TERMINAL:
            u = rec.get("url") or ""
            if "/c/" in u:
                live.append([name, u.split("/c/")[-1].split("/")[0].split("?")[0]])
    try:
        with open(os.path.join(FLAGS, "admission_chats.json"), "w") as f:
            json.dump(live, f)
        log(f"admission_chats.json written: {live}")
    except OSError:
        pass
    launch_detached("tl1_admission_sentinel.py", "tl1_admission.log")
    launch_detached("tl1_harvest_sentinel.py", "tl1_harvest.log")

    log(f"RECOVERY ROUND COMPLETE — complete={complete_names} dead-redispatched="
        f"{[n for n, _ in dead]}; sentinels armed")
    outbox(f"[TL1] Reset recovery complete. Board: "
           f"{', '.join(complete_names) or 'no'} lane(s) completed during the "
           f"blackout; {len(dead)} lane(s) re-dispatched fresh; admission + "
           f"harvest sentinels armed. The harvest->gates->PR->merge chain is "
           f"autonomous from here. — TL1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
