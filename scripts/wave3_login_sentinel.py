#!/usr/bin/env python3
"""wave3_login_sentinel.py — dispatch the TL2 wave-3 census-closure lanes
(F1/F2/F3) when the operator's login returns after the sandbox reset.

The reset wiped the browser profile; dispatch requires the live agents-tab
surface. This sentinel polls login health (localStorage token + the
agents-tab 'New Task' marker via a live-tab probe) and on the first healthy
window: (1) caches the JWT to flags/chat_token for the Bearer harvest path,
(2) dispatches flauz-F{1,2,3}-tl2 sequentially via launch_create.py
(each create is its own detached process; the registry's sent+url record
confirms the landing; up to 3 rounds per lane), (3) records each lane's
chat id into flags/wave3_lanes.json for the completion watcher.
Read-only otherwise; 60s cadence; 12h window.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "wave3_login_sentinel.log")
PY = "/home/z/.venv/bin/python3"
REG = os.path.join(FLAGS, "session_registry.jsonl")
STATE = os.path.join(FLAGS, "wave3_lanes.json")
CADENCE = 60
MAX_WAIT = 12 * 3600
CREATE_BUDGET = 30 * 60  # per create round

LANES = [
    ("flauz-F1-tl2", "worker-prompts/flauz-tl2-f1.md",
     "flauz-delivery/tl2-f1-cancellation-concurrency",
     "FLAUZ-TL2-F1-REPORT END", "/home/z/tl2-harvest/f1"),
    ("flauz-F2-tl2", "worker-prompts/flauz-tl2-f2.md",
     "flauz-delivery/tl2-f2-bounded-retry",
     "FLAUZ-TL2-F2-REPORT END", "/home/z/tl2-harvest/f2"),
    ("flauz-F3-tl2", "worker-prompts/flauz-tl2-f3.md",
     "flauz-delivery/tl2-f3-lease-conflict",
     "FLAUZ-TL2-F3-REPORT END", "/home/z/tl2-harvest/f3"),
]
F4 = ("flauz-F4-tl2", "worker-prompts/flauz-tl2-f4.md",
      "flauz-delivery/tl2-f4-landing-debt",
      "FLAUZ-TL2-F4-REPORT END", "/home/z/tl2-harvest/f4")


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except OSError:
        pass


def write_state(update):
    """Merge update(name -> chat_id) into the shared wave3 state file."""
    st = {"lanes": []}
    if os.path.exists(STATE):
        try:
            with open(STATE) as f:
                st = json.load(f)
        except Exception:
            st = {"lanes": []}
    have = {l.get("name"): l for l in st.get("lanes", [])}
    for name, prompt, prefix, marker, dest in LANES + [F4]:
        l = have.get(name) or {"name": name, "prompt": prompt,
                               "prefix": prefix, "marker": marker,
                               "dest": dest, "chat": None,
                               "dispatched": False, "harvested": False}
        if name in update and update[name]:
            l["chat"] = update[name]
            l["dispatched"] = True
        have[name] = l
    st["lanes"] = [have[n] for n, *_ in LANES + [F4]]
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def _jwt_email(tok):
    """Decode any email-looking string from a JWT payload (guest
    discrimination — 2026-09-15 reset-2 lesson in watcher.py, re-learned
    2026-09-28): a fresh profile auto-creates a GUEST session that ALSO
    carries a >100-char token. Only a non-guest JWT email proves an
    operator login."""
    import base64 as _b64
    try:
        parts = str(tok).split(".")
        if len(parts) < 2:
            return ""
        seg = parts[1]
        seg += "=" * (-len(seg) % 4)
        payload = _b64.urlsafe_b64decode(seg.encode()).decode("utf-8", "replace")
        m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", payload)
        return m.group(0) if m else ""
    except Exception:
        return ""


def login_healthy():
    """True ONLY when a REAL (non-guest) operator session exists.

    2026-09-28 rework: the original probe opened a FRESH tab every cycle and
    required the agents surface ('New Task') in it. Two flaws surfaced after
    ~1h of silent waiting: (a) the churn steals the console's auto-focus
    while the operator is mid-login (the console follows newly opened tabs —
    a probe tab popping every 60s can interrupt their slider drag); (b) a
    guest session renders a logged-in-looking home tab in memory (display
    name + composer + 'Sign Out') while fresh tabs correctly show 'Sign in'
    — the agents surface can flicker between states that say nothing about
    the REAL session. The profile-wide JWT email is the ground truth:
    guest-*@guest.com means NOT logged in; a real email means the login
    persisted. Read it from EXISTING chat.z.ai tabs (no tab creation)."""
    try:
        tabs = channel.list_tabs()
        chat_tabs = [t for t in tabs if "chat.z.ai" in (t.get("url") or "")]
        for tab in chat_tabs[:3]:
            try:
                c = CDP(tab["webSocketDebuggerUrl"], timeout=12)
                try:
                    tok = c.eval(
                        "(localStorage.getItem('token')||'').replace(/^\"|\"$/g,'')",
                        timeout=8) or ""
                    email = _jwt_email(tok)
                    if email and "guest" not in email.lower():
                        return True
                finally:
                    c.close()
            except Exception:
                continue
        return False
    except Exception:
        return False


def cache_token():
    """Persist the JWT for the Bearer harvest path (flags/chat_token)."""
    durable = "/home/z/my-project/download/zai_operator_jwt.txt"
    try:
        r = subprocess.run([PY, os.path.join(BASE, "zai_token_tools.py"),
                            "capture"], capture_output=True, text=True,
                           timeout=90)
        log(f"token capture rc={r.returncode}: {(r.stdout or '').strip()[:120]}")
        if r.returncode == 0 and os.path.exists(durable):
            import shutil
            shutil.copyfile(durable, os.path.join(FLAGS, "chat_token"))
            os.chmod(os.path.join(FLAGS, "chat_token"), 0o600)
            return True
        return False
    except Exception as e:
        log(f"token capture error: {e}")
        return False


def latest_registry_record(name):
    """Newest registry record for a session name, or None."""
    if not os.path.exists(REG):
        return None
    rec = None
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("name") == name or d.get("session") == name:
                    rec = d
    except Exception:
        return None
    return rec


def chat_id_from_record(rec):
    if not rec:
        return None
    if rec.get("sent") and "/c/" in (rec.get("url") or ""):
        m = re.search(r"/c/([0-9a-f-]{16,})", rec["url"])
        if m:
            return m.group(1)
    if rec.get("chat_id"):
        return rec["chat_id"]
    return None


def chat_exists_server_side(chat_id):
    """Phantom guard: the chat id must appear in the account chat list."""
    tok_file = os.path.join(FLAGS, "chat_token")
    if not (chat_id and os.path.exists(tok_file)):
        return bool(chat_id)  # no token cached: trust the registry record
    try:
        import urllib.request
        tok = open(tok_file).read().strip()
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/chats/list?limit=100",
            headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        items = data if isinstance(data, list) else (
            data.get("chats") or data.get("list") or data.get("items") or [])
        for ch in items:
            cid = str(ch.get("chat_id") or ch.get("id") or "").removeprefix("chat-")
            if cid == chat_id:
                return True
        return False
    except Exception as e:
        log(f"  chat_exists check error: {e}")
        return True  # fail-open on API errors: the registry record stands


def dispatch_lane(name, prompt_rel):
    """One create round: detached create -> wait process out -> registry."""
    logp = os.path.join(BASE, "logs", f"create_{name}.log")
    r = subprocess.run([PY, os.path.join(BASE, "launch_create.py"),
                        name, os.path.join(BASE, prompt_rel)],
                       capture_output=True, text=True, timeout=120)
    m = re.search(r"pid (\d+)", r.stdout or "")
    if not m:
        log(f"[{name}] launch_create gave no pid: {(r.stdout or '')[:120]}")
        return None
    pid = int(m.group(1))
    deadline = time.time() + CREATE_BUDGET
    while time.time() < deadline:
        if not os.path.exists(f"/proc/{pid}"):
            break
        time.sleep(10)
    else:
        log(f"[{name}] create still running after budget; leaving it be")
        return None  # still grinding; caller may retry later
    rec = latest_registry_record(name)
    cid = chat_id_from_record(rec)
    if cid and chat_exists_server_side(cid):
        log(f"[{name}] LANDED chat={cid}")
        return cid
    log(f"[{name}] round did not land (rec={bool(rec)} cid={cid})")
    return None


def main():
    log("=== wave3_login_sentinel start (waiting for operator login; "
        "JWT-email guest discrimination, no tab churn)")
    started = time.time()
    last_hb = 0.0
    while time.time() - started < MAX_WAIT:
        if login_healthy():
            break
        now = time.time()
        if now - last_hb >= 600:
            log(f"waiting for operator login — elapsed "
                f"{int((now - started) // 60)}m (real account JWT not yet "
                f"present; guest session does not count)")
            last_hb = now
        time.sleep(CADENCE)
    else:
        log("12h window expired — sentinel stands down (re-arm next session)")
        return

    log("LOGIN HEALTHY — caching token + dispatching wave 3 (F1/F2/F3)")
    cache_token()
    outbox("[TL2] login detected — dispatching wave-3 census-closure lanes "
           "F1 (cancellation + concurrency), F2 (bounded provider retry), "
           "F3 (lease-conflict contract). F4 (landing debt) follows the "
           "first freed slot. Completion watcher armed.")

    update = {}
    for name, prompt, *_ in LANES:
        cid = None
        for round_no in range(3):
            cid = dispatch_lane(name, prompt)
            if cid:
                break
            log(f"[{name}] retry round {round_no + 2}/3")
            time.sleep(45)
        if cid:
            update[name] = cid
            outbox(f"[TL2] {name} dispatched — chat {cid[:8]}; generating.")
        else:
            outbox(f"[TL2] {name} did NOT land after 3 rounds — the TL "
                   "session will hand-dispatch it.")
    write_state(update)
    log(f"=== wave-3 dispatch phase done: {update}")
    outbox("[TL2] wave-3 dispatch phase complete — the completion watcher "
           "(marker + Bearer harvest + F4 chain) takes over.")


if __name__ == "__main__":
    main()
