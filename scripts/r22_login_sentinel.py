#!/usr/bin/env python3
"""r22_login_sentinel.py — HARDENED login sentinel for the R22 wave 1.

Same v2 hardening as reset_login_sentinel.py (strict login evidence +
debounce + probe-tab auth inheritance + self-healing dispatch — the v1
autopsy lives in that file's header). R22 differences:

  - Wave 1 = r22w1 (shared contracts lane R22-A/B/C, packet R22-W1.md,
    branch wfx/r22/shared) — dispatched ONLY after the operator's login
    is strictly confirmed AND fresh tabs inherit the session.
  - Phase 2 is NOT an auto-dispatch: the frozen R22 concurrency law
    (docs/plans/2026-09-20-webflix-major-journey-hardening-plan.md §6)
    requires LEAD RATIFICATION of A/B/C before Workers 2/3 implement
    against them. So Phase 2 only watches for the r22w1 completion
    marker / the R22-A checkpoint, notifies via outbox, and exits —
    the resident lead harvests, ratifies, and dispatches W2+W3.

Packets come from materialize_r22_packets.py (committed templates + PAT
flag). This script is PAT-free and committed to the repo.

Usage:
  python3 scripts/r22_login_sentinel.py
    (run detached via launch_detached.py logs/r22_sentinel.log ...)

Log: scripts/logs/r22_sentinel.log   Heartbeat: flags/r22_sentinel_heartbeat
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, BASE)

import channel          # noqa: E402
import dispatch_worker as dw  # noqa: E402

TAG = "r22"
LOG_PATH = os.path.join(BASE, "logs", f"{TAG}_sentinel.log")
HEARTBEAT = os.path.join(BASE, "flags", f"{TAG}_sentinel_heartbeat")
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
WEBFLIX = os.path.join(os.path.dirname(ROOT), "webflix")
POLL_SECS = 20
MAX_WAIT_SECS = 8 * 3600
LOGIN_DEBOUNCE_SECS = 20
W1_NAME = "r22w1"
W1_PROMPT = "R22-W1.md"
W1_MARKER = "R22-W1 COMPLETION REPORT"
W1_COMPLETE_FLAG = os.path.join(BASE, "flags", "r22w1-complete.marker")
R22_BRANCH = "wfx/r22/shared"
R22A_MARKER = "R22-A checkpoint"

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


def _body_of(tab):
    """Return innerText of a tab (or None on error)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            return dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return None


def _authed_body(body):
    """True when a page body shows an AUTHENTICATED chat.z.ai shell.

    (Evidence autopsy carried from v2: signed-out shells ALWAYS render the
    sidebar 'Sign in' entry; length cannot discriminate — the 'no Sign in'
    + positive-marker combination does.)"""
    if not body:
        return False
    if ("Sign in" in body) or ("Log in" in body):
        return False
    return ("Previous" in body) or ("New Task" in body) or (len(body) >= 900)


def logged_in_tabs():
    """Tabs whose strict evidence says the operator is logged in."""
    good = []
    try:
        for t in channel.list_tabs():
            if not (t.get("url") or "").startswith("https://chat.z.ai"):
                continue
            body = _body_of(t)
            if not body:
                continue
            if not _authed_body(body):
                continue
            good.append((t, body))
    except Exception as e:  # noqa: BLE001
        log(f"login probe error (continuing): {e}")
    return good


def login_confirmed():
    """Debounced strict login: positive evidence on 2 probes 20s apart."""
    first = logged_in_tabs()
    if not first:
        return None
    time.sleep(LOGIN_DEBOUNCE_SECS)
    second = logged_in_tabs()
    if not second:
        return None
    ids2 = {t["id"] for t, _ in second}
    for t, _ in first:
        if t["id"] in ids2:
            return t["id"]
    return second[0][0]["id"]


def new_tab_authed():
    """True when a FRESH tab inherits the login (the create-flow requirement)."""
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
            body = dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
            ok = _authed_body(body)
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        log(f"probe-tab error: {e}")
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=6).read()
    except Exception:  # noqa: BLE001
        pass
    return ok


def wait_for_auth_inheritance(timeout_secs=180):
    """Wait until fresh tabs inherit the login; outbox guidance once."""
    start = time.time()
    warn_flag = os.path.join(BASE, "flags", f"{TAG}_inheritance_warned")
    while time.time() - start < timeout_secs:
        beat()
        if new_tab_authed():
            return True
        if not os.path.exists(warn_flag) and time.time() - start > 60:
            open(warn_flag, "w").write(str(time.time()))
            outbox(f"[{TAG}] login seen on your tab, but NEW tabs are still signed out "
                   "(session propagation lag). If this persists, try a hard refresh of your "
                   "chat.z.ai tab — the dispatch needs new tabs to inherit your session.")
        time.sleep(20)
    return new_tab_authed()  # one last try


def registry_chat_id(name, timeout_secs=300):
    """Chat id for a session whose create has LANDED (from the record's /c/ url)."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        beat()
        try:
            with open(REGISTRY) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    if d.get("name") != name or not d.get("sent"):
                        continue
                    if d.get("chat_id"):
                        return d["chat_id"]
                    url = d.get("url") or ""
                    if "/c/" in url:
                        cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
                        if len(cid) >= 30:
                            return cid
        except (OSError, ValueError):
            pass
        time.sleep(10)
    return None


def _tab_signed_out_or_gone(tab_id_prefix):
    """True when the record's tab is absent or renders signed-out."""
    if not tab_id_prefix:
        return True
    try:
        for t in channel.list_tabs():
            if t["id"].startswith(tab_id_prefix):
                body = _body_of(t)
                if body and _authed_body(body):
                    return False  # a live logged-in tab — NEVER touch it
                return True
        return True  # tab gone
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
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "void", name,
             "sentinel pre-clean: stale non-terminal record (signed-out/gone tab)"],
            capture_output=True, text=True, timeout=60)
        log(f"pre-clean: voided stale record for {name} (tab {tid or 'n/a'})")
    else:
        log(f"pre-clean: record for {name} points at a logged-in tab ({tid}) — left untouched")


def dispatch_with_retry(name, prompt, marker, attempts=3):
    prompt_path = os.path.join(BASE, "worker-prompts", prompt)
    if not os.path.exists(prompt_path):
        log(f"ERROR: packet missing: {prompt_path} (run materialize_r22_packets.py)")
        outbox(f"[{TAG}] DISPATCH ABORTED for {name} — packet file missing; "
               "lead will materialize and re-arm.")
        return None
    chat_id = None
    for attempt in range(1, attempts + 1):
        beat()
        log(f"dispatch attempt {attempt}/{attempts} for {name} ({prompt})")
        pre_clean(name)
        r = subprocess.run(
            [sys.executable, os.path.join(BASE, "launch_create.py"), name, prompt_path],
            capture_output=True, text=True, timeout=900,
        )
        log(f"create[{name}] rc={r.returncode} :: {(r.stdout or '').strip()[:200]}")
        chat_id = registry_chat_id(name, timeout_secs=300)
        if chat_id:
            log(f"registry: {name} -> chat {chat_id} (server-confirmed dispatch)")
            break
        log(f"attempt {attempt}: no registry chat_id within 300s — "
            "create failed; will void leftovers and retry")
        try:
            with open(os.path.join(BASE, "logs", f"create_{name}.log"), "rb") as f:
                tail = f.read()[-400:].decode(errors="replace")
            log(f"create log tail: {tail!r}")
        except OSError:
            pass
        time.sleep(60)
    if not chat_id:
        outbox(f"[{TAG}] DISPATCH FAILED for {name} after {attempts} attempts — "
               "login went away or the site refused; lead will re-arm on next wake.")
        return None
    w = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"), name, name, marker],
        capture_output=True, text=True, timeout=60,
    )
    log(f"queue_watch[{name}] rc={w.returncode} :: {(w.stdout or '').strip()[:160]}")
    outbox(f"[{TAG}] {name} DISPATCHED from inside the replay (chat {chat_id}) — "
           f"watching for: {marker}")
    return chat_id


def wave1_landed():
    """True when a previous run already landed the r22w1 session (re-entry
    guard — re-dispatching would void a LIVE session). Append-order truth:
    a later void/failed/done record invalidates."""
    landed = False
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
                if d.get("name") != W1_NAME:
                    continue
                if d.get("action") in ("void", "failed", "done"):
                    landed = False
                elif d.get("sent") and "/c/" in (d.get("url") or ""):
                    landed = True
    except OSError:
        pass
    return landed


def r22a_checkpoint_landed():
    """True when the remote wfx/r22/shared log carries the R22-A checkpoint."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", "origin", f"refs/heads/{R22_BRANCH}"],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return False
        fetch = subprocess.run(
            ["git", "fetch", "-q", "origin", R22_BRANCH],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=60,
        )
        if fetch.returncode != 0:
            return False
        logn = subprocess.run(
            ["git", "log", "--oneline", "-n", "40", "FETCH_HEAD"],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=30,
        )
        return R22A_MARKER in (logn.stdout or "")
    except Exception as e:  # noqa: BLE001
        log(f"branch probe error (continuing): {e}")
        return False


def main():
    log(f"=== {TAG} sentinel armed (v2 hardening: strict evidence + debounce + "
        "probe-tab inheritance + self-healing dispatch; wave 2 gated on LEAD "
        "ratification per the R22 concurrency law) ===")
    start = time.time()

    if wave1_landed():
        log("wave 1 already landed (r22w1 session live from a prior run) — "
            "skipping login wait, entering Phase 2 (notify-only watch)")
    else:
        wave1 = None
        while time.time() - start < MAX_WAIT_SECS:
            beat()
            tab_id = login_confirmed()
            if tab_id:
                log(f"operator login CONFIRMED (tab {tab_id[:8]}, strict+debounced)")
                if not wait_for_auth_inheritance():
                    log("auth inheritance never landed — continuing to watch login "
                        "(operator may need to complete login)")
                    continue
                log("fresh-tab auth inheritance verified — dispatching R22 wave 1 (shared lane)")
                wave1 = dispatch_with_retry(W1_NAME, W1_PROMPT, W1_MARKER)
                break
            time.sleep(POLL_SECS)
        if not wave1:
            log("8h login window expired — sentinel standing down (lead re-arms on next wake)")
            outbox(f"[{TAG}] 8h login window expired without a usable session — "
                   "standing down; the lead re-arms on next wake.")
            return

    # Phase 2 (notify-only): watch for W1 completion / the R22-A checkpoint,
    # then hand off to the resident lead (ratification is the lead's job).
    log("Phase 2: watching for r22w1 completion / R22-A checkpoint (notify-only)")
    deadline = time.time() + 10 * 3600
    notified_checkpoint = False
    while time.time() < deadline:
        beat()
        if os.path.exists(W1_COMPLETE_FLAG):
            log("r22w1-complete marker present — lead harvest in progress; sentinel exiting")
            outbox(f"[{TAG}] r22w1 COMPLETION detected — the resident lead harvests, "
                   "ratifies A/B/C (R22-K), then dispatches W2+W3 per the concurrency law.")
            return
        if not notified_checkpoint and r22a_checkpoint_landed():
            notified_checkpoint = True
            log("R22-A checkpoint detected on wfx/r22/shared — lead notified (no auto wave-2)")
            outbox(f"[{TAG}] R22-A checkpoint detected on {R22_BRANCH} — the resident "
                   "lead begins ratification; W2/W3 dispatch follows lead verification.")
        time.sleep(60)
    log("Phase 2 watch window expired — sentinel exiting; lead resumes manually")


if __name__ == "__main__":
    main()
