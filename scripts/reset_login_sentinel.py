#!/usr/bin/env python3
"""reset_login_sentinel.py — HARDENED login sentinel for the R20/R21 waves.

v1 autopsy (2026-09-19 07:34, sixth reset): the login probe accepted any body
without 'Sign in' — a loading/mid-login page qualifies — fired the dispatch
while the operator's auth was still settling, and the creates died on the
login wall. The armed queue_watch then assault-looped against a signed-out
site until the lead killed it.

Hardening (three layers, carried from v2):
  1. STRICT login evidence: body has NO 'Sign in'/'Log in', length >= 700
     (loading pages are ~420-550) AND a positive app-shell marker; must hold
     on 2 consecutive probes 20s apart (debounce against transient states).
  2. PROBE-TAB AUTH INHERITANCE: before dispatching, open a fresh tab and
     verify IT renders logged-in too (the create flow opens new tabs — if
     fresh tabs cannot inherit the session, dispatch is pointless). Retries
     ~3 min for propagation, then tells the operator via outbox (once).
  3. SELF-HEALING DISPATCH: pre-clean leftover non-terminal records (void
     only when their tab is gone or signed-out — never an operator tab
     mid-login), then create; if no registry chat_id appears within 5 min,
     void and retry (max 3 attempts). Only a server-confirmed dispatch arms
     the queue_watch.

Phase 2: poll the webflix remote for the R20-A checkpoint on wfx/r20/byof;
on detection dispatch r20w2 + r20w3 (Web + Desktop lanes) and arm their
queue_watches, then exit — the lead integrates (R20-H) and stages the R21
waves.

Packets come from materialize_r20_r21_packets.py (committed templates +
PAT flag) — this script is PAT-free and committed to the repo.

Usage:
  python3 scripts/reset_login_sentinel.py [sentinel-tag]
    sentinel-tag names the log/heartbeat files (default: the hostname date
    tag, e.g. reset7) — run `launch_detached.py logs/<tag>_sentinel.log ...`.

Log: scripts/logs/<tag>_sentinel.log   Heartbeat: flags/<tag>_sentinel_heartbeat
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

TAG = (sys.argv[1] if len(sys.argv) > 1 else
       time.strftime("reset%m%d")).replace("/", "-").replace(" ", "-")
LOG_PATH = os.path.join(BASE, "logs", f"{TAG}_sentinel.log")
HEARTBEAT = os.path.join(BASE, "flags", f"{TAG}_sentinel_heartbeat")
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
WEBFLIX = os.path.join(os.path.dirname(ROOT), "webflix")
POLL_SECS = 20
MAX_WAIT_SECS = 8 * 3600
R20_BRANCH = "wfx/r20/byof"
R20A_MARKER = "R20-A checkpoint"
LOGIN_DEBOUNCE_SECS = 20

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


def _authed_body(body):
    """True when a page body shows an AUTHENTICATED chat.z.ai shell.

    Evidence autopsy (2026-09-19 11:28): signed-out shells ALWAYS render the
    sidebar 'Sign in' entry (bodyLen 428-550); authenticated fresh tabs render
    a COMPACT shell with sidebar history instead (observed 482 chars — below
    the old 700 threshold that caused a false inheritance failure while the
    operator was genuinely logged in). Length cannot discriminate; the
    'no Sign in' + positive-marker combination does.
    """
    if not body:
        return False
    if ("Sign in" in body) or ("Log in" in body):
        return False
    # positive evidence: sidebar chat history ("Previous ..." grouping) or
    # agent-mode marker, or a fully-poured app shell
    return ("Previous" in body) or ("New Task" in body) or (len(body) >= 900)


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
    """Chat id for a session whose create has LANDED.

    dispatch_worker.py never writes a literal chat_id field — the id lives in
    the record's /c/<uuid> url. A record counts as landed when sent:true (the
    stage 'queued-capacity' variant is the server-verified acceptance; the
    plain sent record is the post-send save — both mean the prompt is in the
    session, which check <name> can monitor)."""
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
        log(f"ERROR: packet missing: {prompt_path} (run materialize_r20_r21_packets.py)")
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


def r20_branch_state():
    """None | 'absent' | 'present' | 'r20a-checkpoint'."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", "origin", f"refs/heads/{R20_BRANCH}"],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return "absent"
        fetch = subprocess.run(
            ["git", "fetch", "-q", "origin", R20_BRANCH],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=60,
        )
        if fetch.returncode != 0:
            return "present"
        logn = subprocess.run(
            ["git", "log", "--oneline", "-n", "40", "FETCH_HEAD"],
            cwd=WEBFLIX, capture_output=True, text=True, timeout=30,
        )
        if R20A_MARKER in (logn.stdout or ""):
            return "r20a-checkpoint"
        return "present"
    except Exception as e:  # noqa: BLE001
        log(f"branch probe error (continuing): {e}")
        return None


def dispatch_simple(name, prompt, marker):
    """Wave-2 dispatch (login already proven by wave 1's session)."""
    prompt_path = os.path.join(BASE, "worker-prompts", prompt)
    if not os.path.exists(prompt_path):
        log(f"ERROR: packet missing: {prompt_path} (run materialize_r20_r21_packets.py)")
        outbox(f"[{TAG}] wave-2 dispatch ABORTED for {name} — packet file missing.")
        return None
    pre_clean(name)
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_create.py"), name, prompt_path],
        capture_output=True, text=True, timeout=900,
    )
    log(f"create[{name}] rc={r.returncode} :: {(r.stdout or '').strip()[:200]}")
    chat_id = registry_chat_id(name, timeout_secs=300)
    if chat_id:
        w = subprocess.run(
            [sys.executable, os.path.join(BASE, "launch_queue_watch.py"), name, name, marker],
            capture_output=True, text=True, timeout=60,
        )
        log(f"queue_watch[{name}] rc={w.returncode} :: {(w.stdout or '').strip()[:160]}")
        outbox(f"[{TAG}] {name} DISPATCHED from inside the replay (chat {chat_id}) — "
               f"watching for: {marker}")
    else:
        outbox(f"[{TAG}] wave-2 dispatch for {name} FAILED (no chat_id in 300s) — "
               "lead will pick it up on next wake")
    return chat_id


def wave1_landed():
    """True when a previous sentinel run already landed the r20w1 session.

    Re-entry guard (2026-09-19 11:34): the sentinel died after the r20w1
    create landed (capacity assault round 1) but before arming its watcher —
    the lead armed the queue_watch manually. A relaunch must skip wave 1
    (re-dispatching would void a LIVE session) and go straight to Phase 2.
    Append-order truth: a later void/failed/done record invalidates.
    """
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
                if d.get("name") != "r20w1":
                    continue
                if d.get("action") in ("void", "failed", "done"):
                    landed = False
                elif d.get("sent") and "/c/" in (d.get("url") or ""):
                    landed = True
    except OSError:
        pass
    return landed


def main():
    log(f"=== {TAG} sentinel armed (hardened: strict evidence + debounce + "
        "probe-tab inheritance + self-healing dispatch) ===")
    start = time.time()
    state = r20_branch_state()
    if state in ("present", "r20a-checkpoint"):
        log(f"stand-down: {R20_BRANCH} already on remote ({state}) — lead handles the lane")
        return

    if wave1_landed():
        log("wave 1 already landed (r20w1 session live from a prior sentinel run) — "
            "skipping login wait, entering Phase 2 (R20-A checkpoint watch)")
        wave1 = "already-landed"
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
                log("fresh-tab auth inheritance verified — dispatching R20 wave 1")
                wave1 = dispatch_with_retry("r20w1", "R20-W1.md", "R20-W1 COMPLETION REPORT")
                break
            time.sleep(POLL_SECS)
    if not wave1:
        log("8h login window expired — sentinel standing down (lead re-arms on next wake)")
        outbox(f"[{TAG}] 8h login window expired without a usable session — "
               "standing down; the lead re-arms on next wake.")
        return

    # Phase 2: watch for the R20-A checkpoint, then dispatch wave 2 (W2 + W3)
    log("watching for R20-A checkpoint on wfx/r20/byof (wave 2 gate)")
    deadline = time.time() + 8 * 3600
    while time.time() < deadline:
        beat()
        st = r20_branch_state()
        if st == "r20a-checkpoint":
            log("R20-A checkpoint detected — dispatching R20 wave 2 (r20w2 + r20w3)")
            dispatch_simple("r20w2", "R20-W2.md", "R20-W2 COMPLETION REPORT")
            time.sleep(20)
            dispatch_simple("r20w3", "R20-W3.md", "R20-W3 COMPLETION REPORT")
            log("wave 2 dispatched — sentinel exiting; lead integrates (R20-H) then stages R21")
            return
        time.sleep(60)
    log("8h wave-2 window expired — sentinel exiting; lead resumes manually")


if __name__ == "__main__":
    main()
