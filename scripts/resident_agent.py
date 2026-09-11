#!/usr/bin/env python3
"""resident_agent.py — the resident operator-agent's always-on presence.

AGENT_BOOT_PROMPT.md section 4 ("Resident duties") requires a presence that
survives between the operator agent's CLI turns:

  - touch flags/heartbeat so the console shows the agent alive
  - poll flags/operator_inbox.jsonl (new lines = new operator messages)
  - answer by appending {"ts": <ms>, "from": "agent", "text": ...} to
    flags/agent_outbox.jsonl
  - monitor stack health + login state; report STATE TRANSITIONS to the
    outbox (never spam: only on confirmed change)
  - write durable state: append to scripts/logs/worklog.md at every
    milestone (append-only, `---` section separators)

This is the mechanical half of the resident agent: it acknowledges, reports
and keeps the heartbeat. The intelligent half (worker dispatch via
dispatch_worker.py, prompt-building, harvesting) is driven by the operator
agent in its CLI turns — its replies land in the same outbox.

Deliberately NO CDP and NO subprocess spawns in the steady state: only
flag-file reads, localhost HTTP health checks and appends. ~10MB RSS, no
hang paths, unattractive OOM target.

Single instance (flock on flags/resident.lock). Immortal outer loop. Run
detached via scripts/launch_resident.py (Popen + start_new_session=True,
launcher exits immediately — the child reparents to init BEFORE the invoking
shell returns; a tool-shell timeout must never kill the resident).
The supervisor's ensure_resident() relaunches this process if it dies —
same immortality ring as watcher/supervisor/custodian.
"""
import fcntl
import json
import os
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOG = os.path.join(LOGDIR, "resident.log")
WORKLOG = os.path.join(LOGDIR, "worklog.md")
PIDFILE = os.path.join(BASE, "resident.pid")
LOCK = os.path.join(FLAGS, "resident.lock")

INBOX = os.path.join(FLAGS, "operator_inbox.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
HB = os.path.join(FLAGS, "heartbeat")
WM = os.path.join(FLAGS, "inbox_seen_by_resident")   # our own watermark —
# distinct from inbox_seen_by_agent so resident_poll.py (CLI turns) still
# surfaces messages for the intelligent agent to answer.
LOGIN_READY = os.path.join(FLAGS, "LOGIN_READY")

CYCLE = 20            # s between cycles (heartbeat cadence)
CONFIRM = 2           # a stack transition must hold this many cycles
BOOT_DEDUPE = 600     # s — don't re-post "resident online" within this window
MAX_LOG = 2 * 1024 * 1024
KEEP_TAIL = 150 * 1024

os.makedirs(FLAGS, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)


# ------------------------------------------------------------------ plumbing
def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
            with open(LOG, "rb") as f:
                f.seek(-KEEP_TAIL, 2)
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def outbox(text):
    """Append an agent message to the console thread (boot-prompt format)."""
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": str(text)[:2000]}) + "\n")
        log(f"OUTBOX: {str(text)[:160]}")
    except Exception as e:
        log(f"outbox write failed: {e!r}")


def worklog(lines):
    """Durable state — append-only, `---` section separators."""
    try:
        with open(WORKLOG, "a", encoding="utf-8") as f:
            f.write("\n---\n" + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + "\n")
            for l in lines:
                f.write(str(l) + "\n")
    except Exception as e:
        log(f"worklog write failed: {e!r}")


def touch_hb():
    try:
        with open(HB, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def http_ok(url, timeout=4):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(64)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ state
def stack_health():
    return {
        "console:3000": http_ok("http://127.0.0.1:3000"),
        "cdp:9222": http_ok("http://127.0.0.1:9222/json/version"),
        "replayd:3100": http_ok("http://127.0.0.1:3100/healthz"),
    }


def login_state():
    """Login is detected by the watcher (CDP body probe) via LOGIN_READY."""
    return "logged-in" if os.path.exists(LOGIN_READY) else "logged-out"


def session_summary():
    """Live worker sessions from the registry (best-effort, no CDP)."""
    reg = os.path.join(FLAGS, "session_registry.jsonl")
    last = {}
    try:
        for line in open(reg, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            name = d.get("name") or d.get("session") or "?"
            ev = str(d.get("event") or d.get("stage") or "created")
            last[name] = ev
    except Exception:
        pass
    live = [n for n, ev in last.items()
            if ev not in ("done", "void", "closed", "tab-closed")]
    return live


def status_text():
    h = stack_health()
    dead = [k for k, v in h.items() if not v]
    sess = session_summary()
    return (f"stack: {'ALL UP' if not dead else 'DEAD ' + ','.join(dead)} | "
            f"login: {login_state()} | "
            f"sessions: {len(sess)}"
            + (f" ({', '.join(sess[:6])})" if sess else ""))


# ------------------------------------------------------------------ inbox
def read_inbox_lines():
    try:
        return [l for l in open(INBOX, encoding="utf-8").read().split("\n") if l.strip()]
    except Exception:
        return []


def answer(text):
    """Mechanical responder — honest, bounded, useful. The intelligent agent
    answers from its CLI turns; this keeps the thread alive in between."""
    t = (text or "").lower()
    if any(k in t for k in ("help", "what can you")):
        return ("I'm the resident monitor for this replay console. I keep the "
                "heartbeat, watch the stack and relay messages. The operator agent "
                "drives real work (worker dispatch with GLM-5.3 + Full-Stack skill, "
                "harvesting, git delivery) from the CLI chat — send task orders "
                "there. Meanwhile: log in through the replay image if you haven't; "
                "drag slider captchas slowly directly on the image.")
    if any(k in t for k in ("status", "state", "health")):
        return f"status — {status_text()}"
    if "login" in t:
        return (f"login: {login_state()}. If logged out: click Sign in inside the "
                "replay image → Continue with Email → click the field → type in the "
                "box under the image. Slider captcha: press and drag slowly on the "
                "replay image, release when aligned. Toggles: 'DOM click' if clicks "
                "land wrong. The session persists in scripts/browser-profile.")
    return (f"message received — resident monitor online. {status_text()}. "
            "For task orders (dispatch/harvest/verification) ping the operator "
            "agent in the CLI chat; I'll relay milestones here.")


def poll_inbox():
    lines = read_inbox_lines()
    try:
        prev = int(open(WM).read().strip() or "0")
    except Exception:
        prev = 0
    fresh = []
    for l in lines[prev:]:
        try:
            d = json.loads(l)
            if d.get("from") == "operator":
                fresh.append(str(d.get("text", "")))
        except Exception:
            pass
    try:
        open(WM, "w").write(str(len(lines)))
    except Exception:
        pass
    for text in fresh:
        log(f"OPERATOR: {text[:200]}")
        outbox(answer(text))
        worklog([f"operator message: {text[:300]}",
                 f"replied mechanically: {answer(text)[:120]}"])
    return fresh


# ------------------------------------------------------------------ boot
def boot_message():
    """Announce deployment once (deduped within BOOT_DEDUPE)."""
    try:
        recent = [json.loads(l) for l in
                  open(OUTBOX, encoding="utf-8").read().split("\n")
                  if l.strip()]
        last = recent[-1] if recent else {}
        if (str(last.get("text", "")).startswith("resident agent online")
                and int(last.get("ts", 0)) > (time.time() - BOOT_DEDUPE) * 1000):
            return
    except Exception:
        pass
    outbox("resident agent online — " + status_text() + ". "
           "Next operator action: LOG IN through the replay image (Sign in → "
           "email → password; drag slider captchas slowly on the image; toggle "
           "'DOM click' if a click lands wrong). Worker dispatch unlocks after "
           "login. Task orders go to the operator agent in the CLI chat.")
    worklog(["resident agent started (boot message posted)",
             status_text()])


# ------------------------------------------------------------------ main
def main():
    boot_message()
    announced = stack_health()        # last CONFIRMED state (announced)
    pending = dict(announced)         # candidate transitions
    pending_n = {}
    login_announced = login_state()

    while True:
        try:
            touch_hb()
            poll_inbox()

            # --- stack transitions (confirmed over CONFIRM cycles) ---
            h = stack_health()
            for k, v in h.items():
                if v == announced[k]:
                    pending[k] = v
                    pending_n[k] = 0
                    continue
                if pending.get(k) == v:
                    pending_n[k] = pending_n.get(k, 0) + 1
                else:
                    pending[k] = v
                    pending_n[k] = 1
                if pending_n[k] >= CONFIRM:
                    announced[k] = v
                    pending_n[k] = 0
                    if v:
                        outbox(f"{k} back UP — stack: "
                               + ",".join(k2 for k2, ok in announced.items() if ok)
                               + " up")
                    else:
                        outbox(f"ALERT: {k} DOWN (watchdog ring is healing it — "
                               "re-run ./deploy.sh only if this repeats)")
                    worklog([f"stack transition {k}: {'UP' if v else 'DOWN'}",
                             status_text()])

            # --- login transitions (watcher owns detection) ---
            ls = login_state()
            if ls != login_announced:
                login_announced = ls
                if ls == "logged-in":
                    outbox("LOGIN detected — worker dispatch is now UNLOCKED. "
                           "Send task orders to the operator agent in the CLI "
                           "chat (agents-tab sessions, GLM-5.3 + Full-Stack).")
                else:
                    outbox("login LOST — please log in again through the replay "
                           "image; the browser profile keeps prior sessions.")
                worklog([f"login transition -> {ls}", status_text()])
        except Exception as e:
            log(f"cycle error {e!r} — continuing")
        time.sleep(CYCLE)


if __name__ == "__main__":
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another resident agent already holds the lock — exiting", flush=True)
        raise SystemExit(0)
    open(PIDFILE, "w").write(str(os.getpid()))
    log(f"resident agent online (pid {os.getpid()}) — heartbeat + inbox relay")
    # IMMORTAL: even a crash in main() restarts (supervisor also guards us).
    while True:
        try:
            main()
            log("main() returned unexpectedly — restarting in 15s")
        except Exception as e:
            log(f"FATAL in main: {e!r} — restarting in 15s")
        time.sleep(15)
