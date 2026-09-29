#!/usr/bin/env python3
"""login_watch_dispatch.py v2 — login detector + durable token capture +
W090C worker RESCUE daemon (rebuilt after reset #11 wiped the unpushed v2).

v1 (293d365) polled for operator login and auto-DISPATCHED W090C. That
happened (Task 41, 14:02). The worker generated but NEVER pushed
(work/w090c still at the empty starter 385341e 5.5h later — the known
died-mid-generation failure mode). v2 therefore RESCUES instead of
blind-dispatching:

  Phase 1 (login watch — unchanged from v1):
    poll CDP every 60s for an authenticated chat.z.ai tab (sidebar Agent
    nav marker), 2-poll debounce, then:
      1. flags/login_confirmed.json        (resident watcher flips LOGGED-IN)
      2. localStorage.token -> flags/chat_token (600) AND the DURABLE copy
         /home/z/my-project/download/zai_session_token.txt (my-project
         survives home-layer resets — the reset-#10 lesson)
      3. outbox note

  Phase 2 (W090C rescue — new):
    reopen the LIVE worker chat c/1c5e1f29 (session persists server-side
    across TL sandbox resets), then classify every 90s:
      DONE       body shows "W090C COMPLETION REPORT" -> flags/w090c_done.json
      PUSHED     git ls-remote work/w090c advanced past 385341e ->
                 flags/w090c_pushed.json (harvest-ready signal; keep watching
                 for the report, then exit)
      GENERATING body growing or site generating indicator -> wait
      STALLED    static body, no report -> send a continuation message
                 (max 3, spaced) via channel.send_text
      GONE       chat tab bounces to /auth or 404s while the account shell
                 is authenticated -> fallback: fresh dispatch_worker.py
                 create (registry-aware against double-dispatch)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
DONE_FLAG = os.path.join(FLAGS, "w090c_autodispatched.json")
PUSHED_FLAG = os.path.join(FLAGS, "w090c_pushed.json")
REPORTED_FLAG = os.path.join(FLAGS, "w090c_done.json")
PROMPT = "/home/z/my-project/wave8-prompts/W090C.md"
DURABLE_TOKEN = "/home/z/my-project/download/zai_session_token.txt"

WORKER_CHAT_ID = "1c5e1f29-7a33-4a79-89c7-91d81a7402db"
WORKER_CHAT_URL = "https://chat.z.ai/c/" + WORKER_CHAT_ID
STALE_W090C = "385341eb830110b06b8d2263ede528e7a27d4ffd"
COMPLETION_MARKER = "W090C COMPLETION REPORT"
FLEETOS_REMOTE = ("https://x-access-token:%s@github.com/payswapdotorg/"
                  "fleetos.git") % os.environ.get("GITHUB_PAT", "")

from dispatch_worker import JS_AGENT_PRESENT  # noqa: E402

POLL_S = 60
NEED_CONSECUTIVE = 2
CLASSIFY_S = 90
MAX_CONTINUATIONS = 3
MAX_ATTEMPTS = 20

CONTINUATION_MSG = (
    "[TL rescue] Continue the W090C work order autonomously from exactly "
    "where you left off. Do not stop early and do not re-introduce "
    "yourself: finish the remaining screens/journeys, run the three gates "
    "(check / typecheck / bun test), commit, git push origin work/w090c "
    "(the branch on origin is still at the empty starter — your push IS "
    "the deliverable), then end your final message with the exact "
    "'W090C COMPLETION REPORT' block from the work order."
)

CLASSIFY_JS = r"""(() => {
  const txt = document.body.innerText || '';
  const gen = !!(document.querySelector('img[class*=loading], [class*=generating], [role=status]'));
  let auth = false;
  const all = document.querySelectorAll('div,span,button,li,a,p');
  for (const el of all) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join(' ');
    if (own === 'Agent') { auth = true; break; }
  }
  return JSON.stringify({
    url: location.href,
    auth: auth,
    done: txt.indexOf('""" + COMPLETION_MARKER + r"""') !== -1,
    generating: gen,
    bodyLength: txt.length,
    composer: !!(document.querySelector('textarea')),
    tail: txt.slice(-300)
  });
})()"""


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)


def chat_tabs():
    try:
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
    except Exception as e:
        log("CDP /json unavailable: %s" % e)
        return []
    return [t for t in tabs if t.get("type") == "page" and "chat.z.ai" in t.get("url", "")]


def agent_nav_present(tab):
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        r = c.call("Runtime.evaluate",
                   {"expression": JS_AGENT_PRESENT, "returnByValue": True},
                   timeout=30)
        return r.get("result", {}).get("value") == "found"
    except Exception as e:
        log("agent-nav probe error: %s" % e)
        return False
    finally:
        try:
            c.close()
        except Exception:
            pass


def extract_token(tab):
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        r = c.call("Runtime.evaluate",
                   {"expression": "localStorage.getItem('token') || ''",
                    "returnByValue": True},
                   timeout=30)
        return str(r.get("result", {}).get("value") or "").strip().strip('"')
    except Exception as e:
        log("token extract error: %s" % e)
        return ""
    finally:
        try:
            c.close()
        except Exception:
            pass


def outbox(note):
    os.makedirs(FLAGS, exist_ok=True)
    rec = {"ts": int(time.time()), "from": "resident-td", "note": note}
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log("outbox write failed: %s" % e)


def registry_has_live_w090c():
    if not os.path.exists(REG):
        return False
    live = False
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("name") != "w090c":
                    continue
                if rec.get("action") == "create":
                    live = True
                elif rec.get("action") in ("void", "failed"):
                    live = False
    except Exception:
        return False
    return live


def remote_w090c_sha():
    """SHA of work/w090c on origin, or '' on error."""
    try:
        r = subprocess.run(
            ["git", "ls-remote", FLEETOS_REMOTE, "work/w090c"],
            capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").split()
        return out[0].strip() if out else ""
    except Exception:
        return ""


def worker_tab(open_if_missing=True):
    """Find the worker chat tab; open it if missing. Returns tab or None."""
    for t in chat_tabs():
        if WORKER_CHAT_ID in (t.get("url") or ""):
            return t
    if not open_if_missing:
        return None
    try:
        t = channel.new_tab(WORKER_CHAT_URL)
        log("opened worker chat tab %s" % (t.get("id"),))
        time.sleep(8)  # initial load
        return t
    except Exception as e:
        log("worker chat tab open failed: %s" % e)
        return None


def classify(tab):
    """Eval CLASSIFY_JS on the worker chat tab. Returns dict or None."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        r = c.call("Runtime.evaluate",
                   {"expression": CLASSIFY_JS, "returnByValue": True},
                   timeout=30)
        c.close()
        v = r.get("result", {}).get("value")
        return json.loads(v) if v else None
    except Exception as e:
        log("classify error: %s" % e)
        return None


def send_continuation(tab):
    """Send the rescue continuation message to the worker chat."""
    try:
        res = channel.send_text(CONTINUATION_MSG, tab=tab)
        ok = bool(res.get("ok"))
        log("continuation send ok=%s detail=%s" % (ok, res.get("detail", "")))
        return ok
    except Exception as e:
        log("continuation send error: %s" % e)
        return False


def fresh_dispatch(attempts_cap=MAX_ATTEMPTS):
    """Fallback: dispatch a brand-new W090C worker from inside the replay."""
    attempts = 0
    while attempts < attempts_cap:
        if os.path.exists(DONE_FLAG):
            log("done-flag appeared — exiting")
            return True
        attempts += 1
        log("fresh dispatch attempt %d/%d" % (attempts, attempts_cap))
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                 "create", "w090c", PROMPT],
                capture_output=True, text=True, timeout=900, cwd=BASE)
            tail = "\n".join((r.stdout or "").splitlines()[-6:])
            log("create rc=%d tail:\n%s" % (r.returncode, tail))
            if r.returncode == 0:
                with open(DONE_FLAG, "w") as f:
                    json.dump({"ts": int(time.time()), "attempts": attempts,
                               "reason": "v2-fallback-fresh-dispatch"}, f)
                outbox("W090C re-dispatched (fresh fallback) by login-watch v2 "
                       "(attempt %d). TL harvest on work/w090c push." % attempts)
                return True
        except subprocess.TimeoutExpired:
            log("create timed out (900s) — will retry")
        except Exception as e:
            log("create error: %s — will retry" % e)
        time.sleep(POLL_S)
    outbox("W090C v2 fallback dispatch exhausted %d attempts — TL manual "
           "dispatch required on next active session." % attempts_cap)
    return False


def rescue_loop():
    """Phase 2: watch/rescue the live W090C worker chat until done."""
    log("rescue loop armed on %s (classify every %ss)" % (WORKER_CHAT_URL, CLASSIFY_S))
    prev_len = -1
    static_rounds = 0
    continuations = 0
    pushed_seen = False
    gone_rounds = 0
    while True:
        # --- push detection (harvest-ready signal, independent of chat) ---
        sha = remote_w090c_sha()
        if sha and sha != STALE_W090C and not pushed_seen:
            pushed_seen = True
            with open(PUSHED_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "sha": sha}, f)
            outbox("W090C PUSHED: origin work/w090c advanced to %s — "
                   "harvest-ready (TL: clone, re-run gates locally, review, "
                   "merge --no-ff)." % sha[:8])
            log("WORKER PUSHED work/w090c @ %s" % sha[:8])

        # --- chat state classification ---
        tab = worker_tab()
        st = classify(tab) if tab else None
        if st is None:
            log("classify unavailable this round")
            time.sleep(CLASSIFY_S)
            continue

        url = st.get("url", "")
        if st.get("done"):
            with open(REPORTED_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "url": url,
                           "pushed_sha": sha}, f)
            outbox("W090C COMPLETION REPORT detected in the worker chat. "
                   "TL: harvest now (branch sha %s)." % (sha or "unknown")[:8])
            log("WORKER DONE — completion report present. Exiting.")
            return 0

        if "/auth" in url or (not st.get("auth") and "chat.z.ai" not in url):
            gone_rounds += 1
            log("worker chat appears GONE/bounced (url=%s) round %d" % (url, gone_rounds))
            if gone_rounds >= 3:
                log("chat gone 3 rounds — fresh-dispatch fallback")
                outbox("W090C worker chat unreachable after login — falling "
                       "back to a fresh dispatch (registry-aware).")
                if registry_has_live_w090c():
                    log("registry holds live w090c create record — still "
                        "dispatching a fresh one; old session presumed dead")
                ok = fresh_dispatch()
                return 0 if ok else 1
        else:
            gone_rounds = 0

        grew = st.get("bodyLength", 0) > prev_len + 40 if prev_len >= 0 else True
        if st.get("generating") or grew:
            static_rounds = 0
            log("GENERATING (len=%s gen=%s grew=%s)"
                % (st.get("bodyLength"), st.get("generating"), grew))
        else:
            static_rounds += 1
            log("static round %d (len=%s)" % (static_rounds, st.get("bodyLength")))
            if static_rounds >= 2 and continuations < MAX_CONTINUATIONS:
                log("STALLED — sending continuation %d/%d"
                    % (continuations + 1, MAX_CONTINUATIONS))
                if send_continuation(tab):
                    continuations += 1
                    static_rounds = 0
                    outbox("W090C worker stalled — TL rescue continuation "
                           "sent (%d/%d)." % (continuations, MAX_CONTINUATIONS))
        prev_len = st.get("bodyLength", 0)
        time.sleep(CLASSIFY_S)


def main():
    os.makedirs(FLAGS, exist_ok=True)
    if os.path.exists(REPORTED_FLAG):
        log("w090c already reported done — exiting")
        return 0
    log("login-watch v2 armed: poll %ss for authenticated tab; then rescue "
        "the live W090C chat %s" % (POLL_S, WORKER_CHAT_ID))
    consecutive = 0
    auth_tabs = []
    while True:
        auth_tabs = [t for t in chat_tabs() if agent_nav_present(t)]
        if auth_tabs:
            consecutive += 1
            log("authenticated shell visible (%d/%d)" % (consecutive, NEED_CONSECUTIVE))
        else:
            if consecutive:
                log("authenticated state lost — resetting debounce")
            consecutive = 0
        if consecutive >= NEED_CONSECUTIVE:
            break
        time.sleep(POLL_S)

    tab = auth_tabs[0]
    log("OPERATOR LOGIN CONFIRMED on tab %s (%s)" % (tab.get("id"), tab.get("url")))

    # 1. login flag (flips the resident watcher to LOGGED-IN)
    os.makedirs(FLAGS, exist_ok=True)
    with open(os.path.join(FLAGS, "login_confirmed.json"), "w") as f:
        json.dump({"method": "operator-login-detected", "ts": int(time.time()),
                   "tab": tab.get("id"), "url": tab.get("url")}, f)
    # 2. durable token capture (BOTH locations — the reset-#10 lesson)
    tok = extract_token(tab)
    if tok:
        with open(os.path.join(FLAGS, "chat_token"), "w") as f:
            f.write(tok)
        os.chmod(os.path.join(FLAGS, "chat_token"), 0o600)
        try:
            os.makedirs(os.path.dirname(DURABLE_TOKEN), exist_ok=True)
            with open(DURABLE_TOKEN, "w") as f:
                f.write(tok)
            os.chmod(DURABLE_TOKEN, 0o600)
        except Exception as e:
            log("durable token write failed: %s" % e)
        log("chat_token captured (%d chars) + durable copy" % len(tok))
    # 3. outbox note
    outbox("Operator login detected on the replay image (login-watch v2). "
           "Engaging W090C rescue immediately: reopen worker chat, classify, "
           "continue-if-stalled, watch for the completion report + push.")

    # 4. rescue loop (not blind dispatch — the worker is already live)
    return rescue_loop()


if __name__ == "__main__":
    raise SystemExit(main())
