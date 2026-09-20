#!/usr/bin/env python3
"""aise_login_sentinel.py — identity-switch login sentinel for the AISE campaign.

DIFFERENCE vs r22_login_sentinel.py: the parked automation account
(ali12@payswap.org) is ALREADY logged in body-wise, so body-evidence login
detection would fire instantly and wrongly. The campaign unblock is the
OPERATOR logging in their own account through the replay console image
(ali12 is admission-parked server-side: prompts queue but never generate).
Ground truth for "operator logged in" is therefore the site JWT identity
SWITCHING away from ali12@payswap.org — read fresh from a chat.z.ai tab's
localStorage each poll (never the chats_http cache, which holds ali12's
token until deliberately refreshed).

On strict confirmation (debounced identity + fresh-tab inheritance):
  1. refresh flags/chat_token with the operator's token (forensics rail);
  2. dispatch prod021 (packet PROD021.md) — campaign next-in-line;
  3. dispatch prod012 (packet PROD012.md) — deployed-browser verification;
  4. arm one supervisor-resurrectable queue watcher per session;
  5. outbox notices at every transition; then exit (watchers + supervisor
     own the runtime; the resident lead harvests).

Re-entry law: a session whose registry record shows landed/sent with a /c/
url (and no later void/failed/done) is NEVER re-dispatched. One instance
only (lock file).

Usage:  python3 scripts/aise_login_sentinel.py
        (run detached via launch_detached.py logs/aise_sentinel.log ...)

Log: scripts/logs/aise_sentinel.log   Heartbeat: flags/aise_sentinel_heartbeat
"""
import base64
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import channel          # noqa: E402
import dispatch_worker as dw  # noqa: E402

TAG = "aise"
LOG_PATH = os.path.join(BASE, "logs", "aise_sentinel.log")
HEARTBEAT = os.path.join(BASE, "flags", "aise_sentinel_heartbeat")
LOCK = os.path.join(BASE, "flags", "aise_sentinel.lock")
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
TOKEN_CACHE = os.path.join(BASE, "flags", "chat_token")
OPERATOR_INBOX = os.path.join(BASE, "flags", "operator_inbox.jsonl")
PARKED_ACCOUNT = "ali12@payswap.org"
OPERATOR_EMAIL_FALLBACK = "ekontetevi@gmail.com"  # operator's own console post 2026-09-20 18:50

# 2026-09-20 21:20 incident: clearing the parked ali12 session made the site
# auto-mint a GUEST token (guest-...@guest.com); the old "!= ali12" trigger
# false-fired a dispatch under the guest account (create failed harmlessly
# on the auth page; sentinel killed in time). The trigger is now STRICT: the
# identity must EQUAL the operator's email (latest email-shaped operator
# message in flags/operator_inbox.jsonl, else the fallback constant). Guest,
# ali12, and any other identity never trigger.

POLL_SECS = 45
MAX_WAIT_SECS = 12 * 3600
IDENTITY_DEBOUNCE_SECS = 30
DISPATCH_ATTEMPTS = 3

QUEUE = [
    # (session name, packet file, completion marker)
    ("prod021", "PROD021.md", "PROD-021 COMPLETION REPORT"),
    ("prod012", "PROD012.md", "PROD-012 COMPLETION REPORT"),
]

LOG = open(LOG_PATH, "a", buffering=1)


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=LOG, flush=True)


def beat():
    with open(HEARTBEAT, "w") as f:
        f.write(str(time.time()))


def outbox(text):
    try:
        msg = {"ts": int(time.time() * 1000), "from": "agent", "text": text}
        with open(os.path.join(BASE, "flags", "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps(msg) + "\n")
    except OSError:
        pass


def _decode_jwt_email(tok):
    """email claim from a JWT payload, or None when undecodable."""
    try:
        parts = tok.split(".")
        if len(parts) < 2:
            return None
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad))
        email = payload.get("email")
        return str(email).strip().lower() if email else None
    except Exception:  # noqa: BLE001
        return None


def _tab_token(tab):
    """Fresh 'token' from one tab's localStorage (None on any failure)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            raw = dw._eval(
                c, "JSON.stringify(localStorage.getItem('token') || '')",
                timeout=15) or '""'
            tok = json.loads(raw)
            return tok.strip() if isinstance(tok, str) else None
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return None


def operator_email():
    """The operator's chat.z.ai email: the LATEST email-shaped operator
    message in flags/operator_inbox.jsonl, else the fallback constant."""
    import re
    best = None
    try:
        with open(OPERATOR_INBOX) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("from") != "operator":
                    continue
                m = re.search(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                    str(d.get("text", "")))
                if m:
                    best = m.group(0).lower()  # latest wins
    except OSError:
        pass
    return best or OPERATOR_EMAIL_FALLBACK


def identity_state():
    """(email, token) of the CURRENT chat.z.ai session, or (None, None).

    Probes every chat.z.ai tab until one yields a token. A missing token
    means signed-out (operator mid-login) — never a trigger."""
    for t in channel.list_tabs():
        if not (t.get("url") or "").startswith("https://chat.z.ai"):
            continue
        tok = _tab_token(t)
        if tok:
            return _decode_jwt_email(tok), tok
    return None, None


def operator_identity_confirmed():
    """Debounced STRICT trigger: the identity EQUALS the operator's email
    (operator_email()) on two probes IDENTITY_DEBOUNCE_SECS apart. Guest
    sessions, the parked ali12 account, and anything else never trigger.
    Returns (email, token) or None."""
    want = operator_email()
    email, tok = identity_state()
    if not email or email != want:
        return None
    time.sleep(IDENTITY_DEBOUNCE_SECS)
    email2, tok2 = identity_state()
    if email2 and email2 == want:
        return email2, tok2 or tok
    return None


def new_tab_inherits_operator():
    """True when a FRESH tab carries the OPERATOR identity (create-flow
    requirement — new tabs must inherit the session before dispatch)."""
    try:
        tab = channel.new_tab()
    except Exception:  # noqa: BLE001
        return False
    if not tab:
        return False
    ok = False
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            c.call("Page.navigate", {"url": "https://chat.z.ai/"}, timeout=30)
            time.sleep(8)
            tok = None
            try:
                raw = dw._eval(
                    c, "JSON.stringify(localStorage.getItem('token') || '')",
                    timeout=15) or '""'
                tok = (json.loads(raw) or "").strip() or None
            except Exception:  # noqa: BLE001
                pass
            if tok:
                email = _decode_jwt_email(tok)
                ok = bool(email and email == operator_email())
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        log(f"probe-tab error: {e}")
    try:
        import urllib.request
        urllib.request.urlopen(
            f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=6).read()
    except Exception:  # noqa: BLE001
        pass
    return ok


def wait_for_inheritance(timeout_secs=300):
    """Wait until fresh tabs inherit the operator session; outbox hint once."""
    start = time.time()
    warned = False
    while time.time() - start < timeout_secs:
        beat()
        if new_tab_inherits_operator():
            return True
        if not warned and time.time() - start > 90:
            warned = True
            outbox(
                f"[{TAG}] your login is visible, but NEW tabs have not inherited "
                "it yet (session propagation lag). If this persists >2 min, hard-"
                "refresh your chat.z.ai tab — worker dispatch needs new tabs to "
                "carry your session.")
        time.sleep(25)
    return new_tab_inherits_operator()


def refresh_token_cache(tok):
    """Point the lesson-107 forensics rail at the operator's token."""
    try:
        with open(TOKEN_CACHE, "w") as f:
            f.write(tok)
        os.chmod(TOKEN_CACHE, 0o600)
        log("flags/chat_token refreshed with the operator token")
    except OSError as e:
        log(f"token-cache refresh failed (non-fatal): {e}")


def registry_chat_id(name, timeout_secs=300):
    """Chat id for a session whose create LANDED (registry /c/ url)."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        beat()
        try:
            with open(REGISTRY) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("name") != name or not d.get("sent"):
                        continue
                    if d.get("chat_id"):
                        return d["chat_id"]
                    url = d.get("url") or ""
                    if "/c/" in url:
                        cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
                        if len(cid) >= 30:
                            return cid
        except OSError:
            pass
        time.sleep(10)
    return None


def landed(name):
    """Re-entry guard: append-order registry truth (later terminal record
    invalidates an earlier landed one)."""
    hit = False
    try:
        with open(REGISTRY) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("name") != name:
                    continue
                if d.get("action") in ("void", "failed", "done"):
                    hit = False
                elif d.get("sent") and "/c/" in (d.get("url") or ""):
                    hit = True
    except OSError:
        pass
    return hit


def _tab_signed_out_or_gone(tab_id_prefix):
    if not tab_id_prefix:
        return True
    try:
        for t in channel.list_tabs():
            if t["id"].startswith(tab_id_prefix):
                try:
                    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                    try:
                        body = dw._eval(
                            c, "document.body.innerText || ''", timeout=20) or ""
                    finally:
                        c.close()
                except Exception:  # noqa: BLE001
                    return True
                if body and "Sign in" not in body and "Log in" not in body:
                    return False  # a live logged-in tab — NEVER touch it
                return True
        return True
    except Exception:  # noqa: BLE001
        return True


def pre_clean(name):
    """Void leftover non-terminal records whose tabs are dead/signed-out."""
    try:
        rec = dw._find(name)
    except Exception:  # noqa: BLE001
        rec = None
    if not rec:
        return
    tid = (rec.get("tab_id") or "")[:8]
    if _tab_signed_out_or_gone(tid):
        subprocess.run(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "void",
             name, "sentinel pre-clean: stale non-terminal record "
             "(signed-out/gone tab)"],
            capture_output=True, text=True, timeout=60)
        log(f"pre-clean: voided stale record for {name} (tab {tid or 'n/a'})")
    else:
        log(f"pre-clean: record for {name} points at a live tab ({tid}) — untouched")


def dispatch_with_retry(name, prompt, marker, attempts=DISPATCH_ATTEMPTS):
    prompt_path = os.path.join(BASE, "worker-prompts", prompt)
    if not os.path.exists(prompt_path):
        log(f"ERROR: packet missing: {prompt_path}")
        outbox(f"[{TAG}] DISPATCH ABORTED for {name} — packet {prompt} missing; "
               "the lead re-arms after re-materializing it.")
        return None
    chat_id = None
    for attempt in range(1, attempts + 1):
        beat()
        log(f"dispatch attempt {attempt}/{attempts} for {name} ({prompt})")
        pre_clean(name)
        r = subprocess.run(
            [sys.executable, os.path.join(BASE, "launch_create.py"),
             name, prompt_path],
            capture_output=True, text=True, timeout=900)
        log(f"create[{name}] rc={r.returncode} :: "
            f"{(r.stdout or '').strip()[:200]}")
        chat_id = registry_chat_id(name, timeout_secs=300)
        if chat_id:
            log(f"registry: {name} -> chat {chat_id} (server-confirmed)")
            break
        log(f"attempt {attempt}: no registry chat_id within 300s — "
            "create failed; voiding leftovers and retrying")
        try:
            with open(os.path.join(BASE, "logs", f"create_{name}.log"), "rb") as f:
                tail = f.read()[-400:].decode(errors="replace")
            log(f"create log tail: {tail!r}")
        except OSError:
            pass
        time.sleep(60)
    if not chat_id:
        outbox(f"[{TAG}] DISPATCH FAILED for {name} after {attempts} attempts — "
               "the lead re-arms on next wake.")
        return None
    w = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
         name, name, marker],
        capture_output=True, text=True, timeout=60)
    log(f"queue_watch[{name}] rc={w.returncode} :: "
        f"{(w.stdout or '').strip()[:160]}")
    outbox(f"[{TAG}] {name} DISPATCHED from inside the replay (chat {chat_id}) — "
           f"watching for: {marker}")
    return chat_id


def already_dispatched_all():
    return all(landed(n) for n, _, _ in QUEUE)


def main():
    # one-instance lock
    if os.path.exists(LOCK):
        try:
            pid = int(open(LOCK).read().strip())
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"aise_login_sentinel" in f.read():
                    log("another instance is live (pid "
                        f"{pid}) — exiting without dispatching")
                    return
        except (OSError, ValueError):
            pass  # stale lock — take over
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))

    log(f"=== {TAG} sentinel armed — identity-switch trigger (parked: "
        f"{PARKED_ACCOUNT}); queue: "
        + ", ".join(f"{n}<-{p}" for n, p, _ in QUEUE)
        + " ===")
    start = time.time()

    watch_only = already_dispatched_all()
    if watch_only:
        log("both queue sessions already landed (registry truth) — "
            "WATCH-ONLY mode: login detection + notify, no re-dispatch")

    confirmed = None
    while time.time() - start < MAX_WAIT_SECS:
        beat()
        confirmed = operator_identity_confirmed()
        if confirmed:
            break
        time.sleep(POLL_SECS)

    if not confirmed:
        log("12h window expired without an operator identity switch — "
            "standing down; the lead re-arms on next wake")
        outbox(f"[{TAG}] 12h login window expired — sentinel standing down; "
               "the lead re-arms it on the next wake. The replay console and "
               "queue stay live.")
        return

    email, tok = confirmed
    log(f"OPERATOR LOGIN CONFIRMED — identity switched to {email} "
        "(debounced, fresh-tab check pending)")
    if watch_only:
        outbox(f"[{TAG}] OPERATOR LOGIN DETECTED ({email}) — welcome. "
               "prod021 + prod012 are already live in the replay (re-entry "
               "guard engaged; no duplicate dispatch). Watchers own the "
               "runtime and the resident lead harvests their reports. The "
               "adapter-wave re-land (prod017/019/020 packets on disk) stays "
               "your call — say the word and they follow.")
    else:
        outbox(f"[{TAG}] OPERATOR LOGIN DETECTED ({email}) — resuming the campaign: "
               "dispatching prod021 (next-in-line) then prod012 (deployed-browser "
               "verification) from inside the replay. The adapter-wave re-land "
               "(prod017/019/020 packets on disk) stays your call — say the word "
               "and they follow.")
    refresh_token_cache(tok)

    if not wait_for_inheritance():
        log("auth inheritance never landed — continuing the login watch "
            "(operator may need to complete login)")
        outbox(f"[{TAG}] login identity seen but new tabs did not inherit it "
               "in time — holding dispatch; the sentinel keeps watching and "
               "will dispatch the moment inheritance lands.")
        while time.time() - start < MAX_WAIT_SECS:
            beat()
            time.sleep(POLL_SECS)
            if operator_identity_confirmed() and new_tab_inherits_operator():
                break
        else:
            log("inheritance never landed within the window — standing down")
            return
    if watch_only:
        log("fresh-tab inheritance verified — watch-only pass (queue already "
            "landed; nothing to dispatch)")
        outbox(f"[{TAG}] operator session confirmed on fresh tabs — watch-only "
               "pass complete. prod021 + prod012 run with supervisor-"
               "resurrectable watchers; the resident lead harvests their "
               "COMPLETION REPORTs, runs the gates, and reports back here. "
               "(Concurrency cap 3 observed; one slot held free.)")
        log("watch-only pass complete — sentinel exiting (watchers + "
            "supervisor own the runtime)")
        return

    log("fresh-tab inheritance verified — dispatching the armed queue")

    for name, prompt, marker in QUEUE:
        if landed(name):
            log(f"{name} already landed (re-entry guard) — skipping")
            continue
        dispatch_with_retry(name, prompt, marker)
        time.sleep(30)  # settle between creates

    outbox(f"[{TAG}] queue dispatch pass complete — prod021 + prod012 are "
           "live under your account with supervisor-resurrectable watchers. "
           "The resident lead harvests their COMPLETION REPORTs, runs the "
           "gates, and reports back here. (Concurrency cap 3 observed; one "
           "slot held free.)")
    log("dispatch pass complete — sentinel exiting (watchers + supervisor "
        "own the runtime)")


if __name__ == "__main__":
    main()
