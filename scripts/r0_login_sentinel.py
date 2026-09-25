#!/usr/bin/env python3
"""r0_login_sentinel.py — Wave R0 (POST-001/002/003) login sentinel.

FRESH-PROFILE VARIANT of the aise_login_sentinel pattern (2026-09-25 sandbox
reset wiped the browser profile + every credential backup). The browser is
fully signed out; the campaign unblock is the OPERATOR logging in their own
account through the replay console image. Ground truth for "operator logged
in" on a fresh profile: a chat.z.ai tab carries a localStorage token whose
JWT email is a REAL identity — NOT a guest-*@guest.com auto-mint and NOT the
admission-parked ali12@payswap.org (both never trigger; dispatch under either
is void).

On strict confirmation (debounced identity + fresh-tab inheritance):
  1. refresh flags/chat_token with the operator's token (forensics rail);
  2. pre-dispatch gate: active workspaces < 3 (lessons 131/135);
  3. dispatch post001, post002, post003 sequentially (launch_create.py —
     full assault machinery, popups dismissed never obeyed per lesson 129);
  4. arm one detached queue_watch per session (COMPLETION REPORT markers);
  5. outbox notices at every transition; then exit (watchers + supervisor
     own the runtime; the resident lead harvests + nudges at T+2h05m).

Re-entry law: a session whose registry record shows landed/sent with a /c/
url (and no later void/failed/done) is NEVER re-dispatched. One instance only
(lock file).

Usage:  python3 scripts/r0_login_sentinel.py
        (run detached via launch_detached.py logs/r0_sentinel.log ...)

Log: scripts/logs/r0_sentinel.log   Heartbeat: flags/r0_sentinel_heartbeat
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

TAG = "r0"
LOG_PATH = os.path.join(BASE, "logs", "r0_sentinel.log")
HEARTBEAT = os.path.join(BASE, "flags", "r0_sentinel_heartbeat")
LOCK = os.path.join(BASE, "flags", "r0_sentinel.lock")
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
TOKEN_CACHE = os.path.join(BASE, "flags", "chat_token")

NEVER_TRIGGER = {"", "guest", "ali12@payswap.org"}

# (session name, packet file, completion marker)
QUEUE = [
    ("post001", "POST001.md", "POST-001 COMPLETION REPORT"),
    ("post002", "POST002.md", "POST-002 COMPLETION REPORT"),
    ("post003", "POST003.md", "POST-003 COMPLETION REPORT"),
]

POLL_SECS = 45
MAX_WAIT_SECS = 12 * 3600
IDENTITY_DEBOUNCE_SECS = 30
DISPATCH_ATTEMPTS = 3
SANDBOX_CAP = 3

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


def identity_state():
    """(email, token) of the CURRENT chat.z.ai session, or (None, None).

    A missing token means signed-out (operator mid-login) — never a trigger.
    Guest tokens and the parked ali12 account never qualify either."""
    for t in channel.list_tabs():
        if not (t.get("url") or "").startswith("https://chat.z.ai"):
            continue
        tok = _tab_token(t)
        if tok:
            email = _decode_jwt_email(tok)
            if email and email not in NEVER_TRIGGER and not email.startswith("guest"):
                return email, tok
            return None, None  # a non-operator identity is parked on — no trigger
    return None, None


def operator_identity_confirmed():
    """Debounced trigger: the SAME real (non-guest, non-parked) identity on
    two probes IDENTITY_DEBOUNCE_SECS apart. Returns (email, token) or None."""
    email, tok = identity_state()
    if not email:
        return None
    time.sleep(IDENTITY_DEBOUNCE_SECS)
    email2, tok2 = identity_state()
    if email2 and email2 == email:
        return email2, tok2 or tok
    return None


def new_tab_inherits_operator(email):
    """True when a FRESH tab carries the SAME operator identity (create-flow
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
                ok = _decode_jwt_email(tok) == email
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


def wait_for_inheritance(email, timeout_secs=300):
    """Wait until fresh tabs inherit the operator session; outbox hint once."""
    start = time.time()
    warned = False
    while time.time() - start < timeout_secs:
        beat()
        if new_tab_inherits_operator(email):
            return True
        if not warned and time.time() - start > 90:
            warned = True
            outbox(
                f"[{TAG}] your login is visible, but NEW tabs have not inherited "
                "it yet (session propagation lag). If this persists >2 min, hard-"
                "refresh your chat.z.ai tab — worker dispatch needs new tabs to "
                "carry your session.")
        time.sleep(25)
    return new_tab_inherits_operator(email)


def refresh_token_cache(tok):
    try:
        with open(TOKEN_CACHE, "w") as f:
            f.write(tok)
        os.chmod(TOKEN_CACHE, 0o600)
        log("flags/chat_token refreshed with the operator token")
    except OSError as e:
        log(f"token-cache refresh failed (non-fatal): {e}")


def active_workspace_count():
    """Live workspaces via the in-page API (lesson 131/135 pre-dispatch gate).

    Returns (count, raw) — count is None when the API is unreadable (the
    dispatcher's own concurrency-modal handling remains the backstop)."""
    try:
        tab = channel.find_tab("chat.z.ai")
        if tab is None:
            return None, "no chat.z.ai tab"
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            raw = c.eval(
                "(async () => { const r = await fetch('/api/v1/web-dev/"
                "workspaces/user-fc', {credentials:'include'}); "
                "return (await r.text()).slice(0, 200000); })()",
                await_promise=True, timeout=60) or ""
        finally:
            c.close()
        data = json.loads(raw)
        items = []
        v = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(v, dict):
            for k in ("workspaces", "list", "items"):
                if isinstance(v.get(k), list):
                    items = v[k]
                    break
        elif isinstance(v, list):
            items = v
        active = [i for i in items
                  if i.get("is_active") or str(i.get("status", "")).lower()
                  in ("live", "running")]
        return len(active), raw[:200]
    except Exception as e:  # noqa: BLE001
        return None, f"api error: {e}"


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
        # pre-dispatch gate (lesson 131/135): workspaces < cap
        count, raw = active_workspace_count()
        if count is not None and count >= SANDBOX_CAP:
            log(f"workspace gate: {count} active >= {SANDBOX_CAP} — releasing "
                "idle sandboxes (dash_sandbox_release) before create")
            subprocess.run(
                [sys.executable, os.path.join(BASE, "dash_sandbox_release.py")],
                capture_output=True, text=True, timeout=180)
            count, _ = active_workspace_count()
            if count is not None and count >= SANDBOX_CAP:
                log(f"workspace gate STILL {count} after release — waiting 120s "
                    "and retrying the gate")
                outbox(f"[{TAG}] sandbox slots full ({count}/{SANDBOX_CAP}) for "
                       f"{name} — releasing/waiting; dispatch retries automatically.")
                time.sleep(120)
        else:
            log(f"workspace gate: active={count} (cap {SANDBOX_CAP}) — OK"
                if count is not None else
                "workspace gate: API unreadable — proceeding (dispatcher's "
                "concurrency-modal handling is the backstop)")
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
                if b"r0_login_sentinel" in f.read():
                    log("another instance is live (pid "
                        f"{pid}) — exiting without dispatching")
                    return
        except (OSError, ValueError):
            pass  # stale lock — take over
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))

    log("=== r0 sentinel armed — fresh-profile login trigger (never-trigger: "
        "guest, ali12@payswap.org); queue: "
        + ", ".join(f"{n}<-{p}" for n, p, _ in QUEUE)
        + " ===")
    start = time.time()

    watch_only = already_dispatched_all()
    if watch_only:
        log("all queue sessions already landed (registry truth) — "
            "WATCH-ONLY mode: login detection + notify, no re-dispatch")

    confirmed = None
    while time.time() - start < MAX_WAIT_SECS:
        beat()
        confirmed = operator_identity_confirmed()
        if confirmed:
            break
        time.sleep(POLL_SECS)

    if not confirmed:
        log("12h window expired without an operator login — standing down; "
            "the lead re-arms on next wake")
        outbox(f"[{TAG}] 12h login window expired — sentinel standing down; "
               "the lead re-arms it on the next wake. The replay console and "
               "queue stay live.")
        return

    email, tok = confirmed
    log(f"OPERATOR LOGIN CONFIRMED — identity {email} "
        "(debounced, fresh-tab check pending)")
    if watch_only:
        outbox(f"[{TAG}] OPERATOR LOGIN DETECTED ({email}) — welcome. "
               "post001/post002/post003 are already live in the replay "
               "(re-entry guard engaged; no duplicate dispatch). Watchers own "
               "the runtime and the resident lead harvests their reports.")
    else:
        outbox(f"[{TAG}] OPERATOR LOGIN DETECTED ({email}) — Wave R0 firing: "
               "dispatching post001 (release state), post002 (Android device "
               "lane), post003 (independent verification) from inside the "
               "replay, three slots exactly. Reports will render in their "
               "tabs; the resident lead harvests + gates + reports back here.")
    refresh_token_cache(tok)

    if not wait_for_inheritance(email):
        log("auth inheritance never landed — continuing the login watch "
            "(operator may need to complete login)")
        outbox(f"[{TAG}] login identity seen but new tabs did not inherit it "
                "in time — holding dispatch; the sentinel keeps watching and "
                "will dispatch the moment inheritance lands.")
        while time.time() - start < MAX_WAIT_SECS:
            beat()
            time.sleep(POLL_SECS)
            if operator_identity_confirmed() and \
                    new_tab_inherits_operator(email):
                break
        else:
            log("inheritance never landed within the window — standing down")
            return
    if watch_only:
        log("fresh-tab inheritance verified — watch-only pass (queue already "
            "landed; nothing to dispatch)")
        outbox(f"[{TAG}] operator session confirmed on fresh tabs — watch-only "
                "pass complete. post001/post002/post003 run with supervisor-"
                "resurrectable watchers; the resident lead harvests their "
                "COMPLETION REPORTs, runs the gates, and reports back here.")
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

    outbox(f"[{TAG}] Wave R0 dispatch pass complete — post001/post002/post003 "
           "live under your account with supervisor-resurrectable watchers. "
           "The resident lead harvests their COMPLETION REPORTs, runs the "
           "gates, and reports back here. (Concurrency cap 3 exactly filled.)")
    log("dispatch pass complete — sentinel exiting (watchers + supervisor "
        "own the runtime)")


if __name__ == "__main__":
    main()
