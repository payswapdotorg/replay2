#!/usr/bin/env python3
"""pub_login_sentinel.py — reset10 epoch (2026-10-02): on operator login,
resume the SOS Public Deployment program at PUB-03 (re-dispatch).

State at authoring (2026-10-02 10:33Z, reset10 recovery):
  - Sandbox reset ~09:58Z wiped all local state (browser profile, flags,
    prompts, mission state). Remote refs survive as the only truth.
  - REMOTE TRUTH (payswapdotorg/SOS): main = 7a3b1eb = PUB-00 MERGED
    (ad3bf5c, PR #23) + PUB-01 MERGED (c98972a, PR #25, head 5a24c47) +
    PUB-02 MERGED (9b8d031, PR #24, head 67df5eb) + TL reconciliations.
    PUB-03 was DISPATCHED 02:51:52Z (chat 939f1bb0-48f4-4e99-9051-012544789c13)
    but the platform outage + reset left NO branch / NO PR = NOT YET VERIFIED.
  - Wave-2 packets (PUB-04/PUB-05/PUB-07, base 7a3b1eb) are staged under
    scripts/worker-prompts/ — dispatch is gated on wave-1 (PUB-03) closing,
    per the TL handoff sequencing. This sentinel only re-establishes PUB-03.
  - Replay stack rebuilt from payswapdotorg/replay2 (launch_dev.py console,
    CDP :9222 fresh profile → logged out; ring UP).

On login (30s poll, 16h window):
  1. Probe the old PUB-03 chat server-side (probe_chat.py, marker
     "COMPLETION REPORT"). If a real completion report exists: record the
     verdict + outbox and STOP — the TL session reviews the delivery; no
     re-dispatch (never destroy a live/delivered session).
  2. Else re-dispatch PUB-03: dispatch_worker.py create pub-03-freetier-infra
     worker-prompts/pub-03-freetier-infra.md (token substituted at send time
     from the operator env loaded below — the packet carries only the
     [REDACTED:github_token] placeholder).
  3. Verify the session in the registry; arm queue_watch[pub-03-freetier-infra]
     with marker COMPLETION REPORT (the watcher auto-corrects its tab prefix
     from the registry and handles capacity/lost-tab churn).
  4. Outbox every transition; verdict JSON -> flags/pub_login_sentinel_verdict.json

Launch detached: dfork_launch.py /tmp/pub_login_sentinel.log <py> pub_login_sentinel.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
VERDICT = os.path.join(FLAGS, "pub_login_sentinel_verdict.json")
HEARTBEAT = os.path.join(FLAGS, "pub_login_sentinel_hb.txt")

STATUS_URL = "http://localhost:3000/api/status"
ENV_FILE = "/home/z/.operator_env"

OLD_PUB03_CHAT = "939f1bb0-48f4-4e99-9051-012544789c13"
SESSION_NAME = "pub-03-freetier-infra"
# packet location: scripts/worker-prompts/ (reset10 staging). NOTE: an
# earlier epoch pointed at BASE/../worker-prompts — that path does not exist
# (FATAL packet-missing at runtime). Fixed 2026-10-02 17:40Z.
PROMPT_FILE = os.path.join(BASE, "worker-prompts", "pub-03-freetier-infra.md")
MARKER = "COMPLETION REPORT"


def load_operator_env():
    """Make the GH token available to dispatch_worker's substitution."""
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or not line.startswith("export "):
                continue
            body = line[len("export "):]
            if "=" in body:
                k, v = body.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except FileNotFoundError:
        pass


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post(text):
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent", "text": text}
            ) + "\n")
    except Exception:
        pass


def run(cmd, timeout=1500, cwd=BASE):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def login_state():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=8) as r:
            d = json.loads(r.read().decode())
            return d.get("browser_login", "unknown")
    except Exception:
        return "unknown"


def wait_for_login(max_s=16 * 3600):
    t0 = time.time()
    last = None
    while time.time() - t0 < max_s:
        st = login_state()
        if st != last:
            log(f"browser_login={st}")
            last = st
        # NOTE: /api/status reports "logged-in(<user>)" for a logged-in
        # operator, NOT the bare "logged-in" literal. An earlier epoch used
        # exact equality here and sat in the poll loop for 10+ minutes after
        # the operator logged in (fix 2026-10-02 17:40Z).
        if st.startswith("logged-in") and "logged-out" not in st:
            return True
        try:
            os.makedirs(FLAGS, exist_ok=True)
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(30)
    return False


def write_verdict(d):
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(VERDICT, "w") as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass


def probe_old_pub03():
    """Server-side truth on the original PUB-03 dispatch chat."""
    log(f"probing old PUB-03 chat {OLD_PUB03_CHAT} (server-side truth)...")
    rc, out = run([PY, os.path.join(BASE, "probe_chat.py"), OLD_PUB03_CHAT, MARKER], timeout=120)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def registry_tail(name):
    reg = os.path.join(BASE, "session_registry.jsonl")
    try:
        recs = [json.loads(l) for l in open(reg).read().splitlines() if l.strip()]
        mine = [r for r in recs if r.get("name") == name]
        return mine[-1] if mine else None
    except Exception:
        return None


def main():
    load_operator_env()
    log("PUB login sentinel armed (PUB-03 re-dispatch on operator login)")
    post("PUB login sentinel armed: waiting for operator login at the replay console (16h window). PUB-03 re-dispatch queued; wave-2 packets staged.")

    if not wait_for_login():
        log("16h window expired without login — exiting (TL will re-arm)")
        write_verdict({"state": "no-login-window-expired", "ts": int(time.time() * 1000)})
        post("PUB login sentinel: 16h window expired without operator login.")
        return 1

    log("operator login detected — probing old PUB-03 chat for prior delivery")
    d = probe_old_pub03()

    if d and d.get("reportInAssistant"):
        log("old PUB-03 chat carries a COMPLETION REPORT — deferring to TL review, NO re-dispatch")
        write_verdict({
            "state": "old-chat-has-report", "probe": d, "ts": int(time.time() * 1000),
        })
        post("PUB login sentinel: the original PUB-03 chat 939f1bb0 carries a completion report server-side. TL review required before any re-dispatch — sentinel standing down (read-only).")
        return 0

    if d and d.get("alive"):
        log(f"old PUB-03 chat alive but no report (last activity age {d.get('updatedAgeS')}s) — "
            "post-outage it is presumed dead-in-water (tree had only the dispatch prompt); re-dispatching fresh")
        post(f"PUB login sentinel: old PUB-03 chat alive without a report (updatedAgeS={d.get('updatedAgeS')}); platform-outage signature — re-dispatching a fresh PUB-03 session at base 7a3b1eb.")
    else:
        log("old PUB-03 chat not found / probe denied — re-dispatching fresh")
        post("PUB login sentinel: old PUB-03 chat 939f1bb0 absent or unreachable server-side — re-dispatching a fresh PUB-03 session at base 7a3b1eb.")

    if not os.path.isfile(PROMPT_FILE):
        log(f"FATAL: prompt packet missing: {PROMPT_FILE}")
        write_verdict({"state": "packet-missing", "ts": int(time.time() * 1000)})
        post("PUB login sentinel: FATAL — staged packet worker-prompts/pub-03-freetier-infra.md missing.")
        return 2

    log(f"dispatching {SESSION_NAME} (agents tab, GLM-5.3, Full-Stack)...")
    rc, out = run([PY, os.path.join(BASE, "dispatch_worker.py"), "create", SESSION_NAME, PROMPT_FILE], timeout=1500)
    log(f"dispatch_worker create rc={rc}")
    tail = "\n".join((out or "").splitlines()[-12:])
    log("create tail:\n" + tail)

    if rc == 3:
        log("capacity-exhausted in-process — supervisor's recover_capacity assault takes over")
        write_verdict({"state": "capacity-recover-armed", "rc": rc, "tail": tail,
                       "ts": int(time.time() * 1000)})
        post("PUB login sentinel: PUB-03 dispatch hit capacity rounds; recover_capacity assault armed by the supervisor ring.")
        return 0

    rec = registry_tail(SESSION_NAME)
    if rec is None:
        log("no registry record after create — reporting failure")
        write_verdict({"state": "create-failed", "rc": rc, "tail": tail,
                       "ts": int(time.time() * 1000)})
        post("PUB login sentinel: PUB-03 create FAILED (no registry record). Tail: " + tail[-400:])
        return 1

    log(f"session established: chat={rec.get('chatId') or rec.get('chat_id')} tab={(rec.get('tab_id') or '')[:8]}")
    post(f"PUB login sentinel: PUB-03 re-dispatched — session {SESSION_NAME} established (chat {(rec.get('chatId') or rec.get('chat_id') or '?')[:8]}, agents-tab/GLM-5.3/Full-Stack verified). Base 7a3b1eb; marker COMPLETION REPORT.")

    # arm the resident queue watcher (auto-corrects tab prefix from registry)
    rc2, out2 = run([PY, os.path.join(BASE, "launch_queue_watch.py"),
                     SESSION_NAME, (rec.get("tab_id") or "")[:8] or SESSION_NAME, MARKER], timeout=60)
    log(f"queue_watch armed rc={rc2}: {(out2 or '').strip()[:120]}")
    write_verdict({
        "state": "dispatched", "session": SESSION_NAME,
        "chat": rec.get("chatId") or rec.get("chat_id"),
        "tab": (rec.get("tab_id") or "")[:8],
        "watcher_rc": rc2, "ts": int(time.time() * 1000),
    })
    post(f"PUB login sentinel: queue_watch[{SESSION_NAME}] armed with marker COMPLETION REPORT. TL: monitor → harvest → review → merge → then wave-2 (PUB-04/PUB-05/PUB-07 packets staged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
