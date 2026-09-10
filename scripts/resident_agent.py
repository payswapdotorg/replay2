#!/usr/bin/env python3
"""resident_agent.py — resident operator-agent daemon (mechanical duties).

Implements the resident duties from AGENT_BOOT_PROMPT.md §4:
  - touch flags/heartbeat every cycle (console shows the agent as alive)
  - poll flags/operator_inbox.jsonl for NEW operator messages; acknowledge
    each exactly once via flags/agent_outbox.jsonl with a stack health
    snapshot (clearly labelled as an auto-ACK; the main agent session does
    the actual work)
  - watch flags/session_registry.jsonl; surface worker REPORT-READY and
    state-change events into the outbox + logs/resident_agent.log
  - stack health monitor (console :3000 / CDP :9222 / replayd :3100 /
    watcher / supervisor); incidents are logged and announced once —
    the supervisor/watchdog pair performs the actual healing
  - append milestones to /worklog.md (durable state survives resets)

Immortal: every exception is caught and the loop continues; the supervisor
(ensure_resident_agent) relaunches this process if it ever dies.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402  (CDP helper, same dir)

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOG = os.path.join(LOGDIR, "resident_agent.log")
INBOX = os.path.join(FLAGS, "operator_inbox.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
REG = os.path.join(FLAGS, "session_registry.jsonl")
WM = os.path.join(FLAGS, "inbox_seen_by_agent")
STATE = os.path.join(FLAGS, "resident_agent_state.json")
HB = os.path.join(FLAGS, "heartbeat")
WORKLOG = os.path.join(ROOT, "worklog.md")

CYCLE = 10          # s — heartbeat + inbox cadence
SLOW_EVERY = 6      # health + registry every N cycles (~60s)

os.makedirs(FLAGS, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1024 * 1024:
            with open(LOG, "rb") as f:
                f.seek(-100 * 1024, 2)
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def outbox(text):
    """Append a message from the agent to the console thread."""
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": str(text)[:2000]}) + "\n")
    except Exception:
        pass


def worklog(msg):
    try:
        with open(WORKLOG, "a", encoding="utf-8") as f:
            f.write(f"- {time.strftime('%Y-%m-%d %H:%M:%S')} [resident_agent] {msg}\n")
    except Exception:
        pass


def load_state(default):
    try:
        return json.loads(open(STATE).read())
    except Exception:
        return default


def save_state(st):
    try:
        with open(STATE, "w") as f:
            f.write(json.dumps(st))
    except Exception:
        pass


def http_ok(url, timeout=4):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(64)
        return True
    except Exception:
        return False


def proc_alive(pattern):
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        return bool(r.stdout.strip())
    except Exception:
        return False


def stack_health():
    return {
        "console:3000": http_ok("http://127.0.0.1:3000"),
        "cdp:9222": http_ok("http://127.0.0.1:9222/json/version"),
        "replayd:3100": http_ok("http://127.0.0.1:3100/healthz"),
        "watcher": proc_alive("scripts/watcher.py"),
        "supervisor": proc_alive("scripts/supervisor.py"),
    }


def fmt_health(h):
    dead = [k for k, v in h.items() if not v]
    return "ALL UP" if not dead else f"DOWN: {', '.join(dead)} (supervisor auto-heals)"


def read_inbox_lines():
    try:
        return [l for l in open(INBOX, encoding="utf-8").read().split("\n") if l.strip()]
    except Exception:
        return []


def poll_inbox(st):
    """New operator messages -> auto-ACK once, with a health snapshot."""
    lines = read_inbox_lines()
    prev = st.get("inbox_seen", 0)
    if len(lines) <= prev:
        st["inbox_seen"] = len(lines)
        return
    new = []
    for l in lines[prev:]:
        try:
            d = json.loads(l)
            if d.get("from") == "operator":
                new.append(str(d.get("text", ""))[:500])
        except Exception:
            pass
    st["inbox_seen"] = len(lines)
    for m in new:
        log(f"OPERATOR MESSAGE: {m}")
        h = stack_health()
        outbox(
            f"ACK (auto): message received — \"{m[:160]}\". "
            f"Stack: {fmt_health(h)}. The main agent session polls this inbox "
            f"and will act on your request; urgent/manual items (login, "
            f"captcha) show up directly in the replay image."
        )
        worklog(f"operator message acked: {m[:120]}")
    # keep the shared watermark (resident_poll.py uses the same file) in sync
    try:
        open(WM, "w").write(str(len(lines)))
    except Exception:
        pass


def registry_sessions():
    """Latest record per session name from the JSONL registry."""
    latest = {}
    order = []
    try:
        for l in open(REG, encoding="utf-8").read().split("\n"):
            if not l.strip():
                continue
            try:
                d = json.loads(l)
            except Exception:
                continue
            n = d.get("name")
            if not n:
                continue
            if n not in latest:
                order.append(n)
            latest[n] = d
    except Exception:
        pass
    return [(n, latest[n]) for n in order]


def session_live_state(rec):
    """CDP probe of a session tab: (chars, streaming, report)."""
    tab_id = rec.get("tab_id", "")
    if not tab_id:
        return None
    try:
        tab = next((t for t in channel.list_tabs() if t.get("id") == tab_id), None)
        if not tab:
            return {"state": "TAB-LOST"}
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=12)
        try:
            body = cdp.eval("document.body.innerText || ''", timeout=12) or ""
        finally:
            cdp.close()
        return {
            "state": "live",
            "chars": len(body),
            "streaming": any(m in body for m in ("Thinking", "Generating", "typing…")),
            "report": "COMPLETION REPORT" in body,
        }
    except Exception as e:
        return {"state": f"ERR:{e!r}"}


def poll_sessions(st):
    """Surface worker completion / state events once each."""
    announced = st.setdefault("announced", {})
    for name, rec in registry_sessions():
        if rec.get("event") in ("done", "void"):
            key = f"{name}:{rec.get('event')}"
            if not announced.get(key):
                announced[key] = 1
                outbox(f"worker {name}: session {rec.get('event')} — {str(rec.get('note', ''))[:120]}")
                worklog(f"session {name} {rec.get('event')}")
            continue
        if "agent" not in str(rec.get("mode", "")).lower():
            continue  # only agent-mode sessions are real (boot prompt §2)
        ls = session_live_state(rec)
        if not ls or ls.get("state") != "live":
            continue
        if ls.get("report") and not ls.get("streaming"):
            key = f"{name}:report"
            if not announced.get(key):
                announced[key] = 1
                outbox(
                    f"worker {name}: COMPLETION REPORT ready "
                    f"(transcript {ls.get('chars', 0)} chars). Harvest with: "
                    f"python3 scripts/harvest_report.py {name}"
                )
                worklog(f"worker {name} report ready ({ls.get('chars')} chars)")
        elif ls.get("streaming") and not announced.get(f"{name}:started"):
            announced[f"{name}:started"] = 1
            log(f"worker {name} streaming ({ls.get('chars')} chars)")


def poll_health(st):
    h = stack_health()
    dead = [k for k, v in h.items() if not v]
    if dead:
        key = "health:" + ",".join(dead)
        if st.setdefault("incidents", {}).get(key) != int(time.time() // 600):
            st["incidents"][key] = int(time.time() // 600)
            log(f"stack incident: {dead} (supervisor auto-heals)")
            worklog(f"stack incident (auto-healing): {dead}")
    return h


JS_MODAL_STATE = r"""(() => {
  const body = document.body.innerText || '';
  const capacity = body.includes('currently at capacity') || body.includes('try again later')
                || body.includes('peak hours');
  let hasCancel = false;
  let generating = false;
  document.querySelectorAll('button').forEach(b => {
    const t = (b.innerText || '').trim();
    if (t === 'Cancel') hasCancel = true;
    if (/^(Stop|Pause|Halt)$/i.test(t)) generating = true;
  });
  // transcript length is returned for frozen-stall detection in the daemon:
  // streaming workers grow the transcript (never frozen), stalled ones don't
  return JSON.stringify({capacity: capacity, hasCancel: hasCancel, generating: generating, len: body.length});
})()"""

JS_MODAL_CANCEL = r"""(() => {
  const b = Array.from(document.querySelectorAll('button'))
    .find(x => (x.innerText || '').trim() === 'Cancel');
  if (!b) return 'no-cancel';
  b.click();
  return 'ok';
})()"""

NUDGE_INTERVAL = 300  # s — min spacing between full nudges per session
NUDGE_MSG = ("Continue: implement per the brief above. Deliver via git push, "
             "then report with the COMPLETION REPORT marker. Dismiss capacity "
             "popups and retry.")


def nudge_stalled_sessions(st):
    """Paced in-session recovery for capacity-blocked worker sessions.

    Operator policy: never wait out a capacity peak. For every live session:
    capacity modal -> click Cancel (renderer hygiene); no modal + turn ended
    (no streaming indicator AND transcript frozen across cycles) -> spawn a
    detached `send` nudge (the proven composer dance) at most once per
    NUDGE_INTERVAL per session. Streaming workers are NEVER touched.
    """
    now = time.time()
    nudged = st.setdefault("nudge_ts", {})
    lens = st.setdefault("nudge_len", {})
    for name, rec in registry_sessions():
        if rec.get("action") in ("void", "failed", "done"):
            continue
        if not rec.get("sent"):
            continue
        tab_id = rec.get("tab_id", "")
        if not tab_id:
            continue
        try:
            tab = next((t for t in channel.list_tabs() if t.get("id") == tab_id), None)
        except Exception:
            continue
        if not tab:
            continue
        try:
            cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=12)
            try:
                raw = cdp.eval(JS_MODAL_STATE, timeout=12) or "{}"
            finally:
                cdp.close()
            state = json.loads(raw)
        except Exception:
            continue
        if state.get("generating"):
            lens[name] = state.get("len", 0)
            continue
        if state.get("capacity") and state.get("hasCancel"):
            try:
                cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=12)
                try:
                    cdp.eval(JS_MODAL_CANCEL, timeout=12)
                finally:
                    cdp.close()
                log(f"nudger: capacity modal cancelled on {name}")
            except Exception:
                pass
            continue
        # no modal, not streaming: turn ended. Nudge only if the transcript
        # is frozen (unchanged across slow cycles) and pacing allows.
        cur = state.get("len", 0)
        prev = lens.get(name)
        frozen = prev is not None and prev == cur and cur > 0
        lens[name] = cur
        if not frozen:
            continue
        if now - nudged.get(name, 0) < NUDGE_INTERVAL:
            continue
        nudged[name] = now
        log(f"nudger: dispatching send nudge to {name} (turn stalled, transcript frozen at {cur})")
        out = open(os.path.join(LOGDIR, "nudge.log"), "a")
        subprocess.Popen(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
             "send", name, NUDGE_MSG],
            stdout=out, stderr=out, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        out.close()
    save_state(st)


def main():
    open(os.path.join(FLAGS, "resident_agent.pid"), "w").write(str(os.getpid()))
    st = load_state({"inbox_seen": 0, "announced": {}, "incidents": {}})
    log(f"resident agent online (pid {os.getpid()})")
    # announce online at most once per hour (restarts stay quiet)
    if time.time() - st.get("online_announced_ts", 0) > 3600:
        st["online_announced_ts"] = time.time()
        save_state(st)
        outbox(
            "Resident agent online. Replay stack deployed: Chrome CDP :9222, "
            "replayd :3100, console :3000, watcher+supervisor watchdogs UP. "
            "Next step for the operator: log in to the target site through the "
            "replay image (Sign in → email → password; slider captchas: press "
            "and drag slowly on the image)."
        )
    worklog("resident agent daemon online — duties: heartbeat / inbox / sessions / health")
    cycle = 0
    while True:
        try:
            with open(HB, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        try:
            poll_inbox(st)
        except Exception as e:
            log(f"inbox poll error {e!r}")
        if cycle % SLOW_EVERY == 0:
            try:
                poll_health(st)
            except Exception as e:
                log(f"health poll error {e!r}")
            try:
                poll_sessions(st)
            except Exception as e:
                log(f"session poll error {e!r}")
            try:
                nudge_stalled_sessions(st)
            except Exception as e:
                log(f"nudge poll error {e!r}")
            save_state(st)
        cycle += 1
        time.sleep(CYCLE)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            try:
                log(f"FATAL in main: {e!r} — restarting in 15s")
            except Exception:
                pass
            time.sleep(15)
