#!/usr/bin/env python3
"""tl1_harvest_sentinel.py — autonomous TL1 delivery harvest (2026-09-27).

Watches for flags/<name>-complete.marker (queue_watch writes it on a
server-confirmed completion report), then per session:
  1. resolve the chat uuid (session_registry live record) + workspace id
     (workspaces/user-fc listing, matched by chat_id)
  2. ls-tree the pod's /home/z/my-project for the packet-mandated bundle
  3. fetch the bundle (+ companion docs) via the files API (direct HTTP,
     Bearer from flags/chat_token) into /home/z/leads-harvest/<name>/
  4. git bundle verify; on success record <name>.harvest.json + outbox
     notice + RELEASE the worker's pod (slot hygiene: the verified bundle
     is local; the chat's work is done)
  5. MIG lesson (done-flag != harvest-ready): if the bundle is MISSING at
     marker time, send ONE staging nudge to the chat (stage_send.py) and
     keep polling up to NUDGES_MAX nudges / 6h, then flag for the Lead.

The Lead's post-harvest duties (replay onto a worktree, gates, PR, merge,
registry DONE, next dispatch) are NOT automated here.

Usage: tl1_harvest_sentinel.py   (run detached via launch_detached.py)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
sys.path.insert(0, BASE)

POLL_SECS = 120
GIVE_UP_AFTER = 14 * 3600          # TL1 sessions can run for hours
NUDGES_MAX = 3
OUTROOT = "/home/z/leads-harvest"

SESSIONS = {
    "tl1-a-001": ["tl1-001-delivery.bundle", "tl1-001-upstream-delta.md"],
    "tl1-b-002": ["tl1-002-delivery.bundle", "tl1-002-release-shell.md"],
    "tl1-c-003": ["tl1-003-delivery.bundle", "tl1-003-service-seam.md"],
    "tl1-a-004": ["tl1-004-delivery.bundle", "tl1-004-core-change-budget.md"],
}


def log(name, msg):
    print(f"[{name}] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except OSError:
        pass


def token():
    return open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')


def api(method, path, body=None, timeout=90):
    url = f"https://chat.z.ai/api/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token()}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def registry_chat(name):
    """Latest live record's chat uuid (the tablost assault rolls chats)."""
    last = None
    try:
        for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
            rec = json.loads(line)
            if rec.get("name") == name:
                last = rec
    except OSError:
        return None
    if not last:
        return None
    u = last.get("url") or ""
    if "/c/" not in u:
        return None
    return u.split("/c/")[-1].split("/")[0].split("?")[0].strip("/")


def workspace_for(chat):
    """workspace id for a chat (None if no pod yet)."""
    data = api("GET", "web-dev/workspaces/user-fc")
    want = f"chat-{chat}"
    for w in data.get("workspaces", []):
        if w.get("chat_id") == want:
            return w.get("function_name")
    return None


def pod_files(chat, ws):
    tree = api("POST", "web-dev/workspaces/files/ls-tree",
               {"chatId": chat, "workspace_id": ws})
    return tree if isinstance(tree, list) else []


def fetch_bytes(chat, ws, filepath):
    """Direct HTTP content fetch -> bytes (works for binary bundles)."""
    url = "https://chat.z.ai/api/v1/web-dev/workspaces/files/content"
    body = json.dumps({"chatId": chat, "workspace_id": ws, "rev": "latest",
                       "filepath": filepath}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def release_pod(chat):
    try:
        api("DELETE", f"web-dev/workspaces/{chat}", timeout=30)
        return True
    except Exception:
        return False


def nudge_staging(name, chat):
    """ONE staging nudge (MIG lesson): ask the worker to cp the bundle."""
    msgfile = os.path.join(FLAGS, f"harvest-nudge-{name}.txt")
    if not os.path.exists(msgfile):
        with open(msgfile, "w") as f:
            f.write(
                "LEAD HARVEST REQUEST (operational — do NOT redo any work): your "
                "completion report was received, but the delivery bundle was not "
                "found in /home/z/my-project by the files API. Stage it now: "
                "cp <your-bundle-path> /home/z/my-project/ and reply with the "
                "exact filename + byte size. If the bundle genuinely cannot be "
                "produced, reply exactly BUNDLE-UNAVAILABLE and the reason. "
                "This is a 1-minute operational step, not a work order.\n")
    # find the session's tab (registry tab id) and send via stage_send
    last = None
    for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
        rec = json.loads(line)
        if rec.get("name") == name:
            last = rec
    tab = (last.get("tab_id") or "")[:8] if last else ""
    if not tab:
        log(name, "nudge: no registry tab — cannot send")
        return False
    chat8 = chat[:8]
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "stage_send.py"), tab, msgfile, chat8],
        cwd=BASE, timeout=300, capture_output=True, text=True)
    ok = "SENT" in (r.stdout or "")
    log(name, f"staging nudge -> tab {tab}: {'sent' if ok else 'FAILED'} "
              f"({(r.stdout or '').strip()[-120:]})")
    return ok


def harvest(name):
    """Full harvest for one completed session. Returns True when done."""
    chat = registry_chat(name)
    if not chat:
        log(name, "no live registry record — skipping this round")
        return False
    ws = workspace_for(chat)
    if not ws:
        log(name, f"chat {chat[:8]} has no pod — nothing to harvest yet")
        return False
    bundle_name = SESSIONS[name][0]
    try:
        tree = pod_files(chat, ws)
    except Exception as e:
        log(name, f"ls-tree failed ({e!r}) — retry next round")
        return False
    if bundle_name not in tree:
        log(name, f"marker fired but bundle {bundle_name} NOT staged "
                  f"({len(tree)} entries) — the MIG gap")
        state = _state(name)
        if state["nudges"] < NUDGES_MAX and time.time() - state["last_nudge"] > 900:
            if nudge_staging(name, chat):
                _state(name, nudges=state["nudges"] + 1, last_nudge=time.time())
                outbox(f"[TL1] {name}: completion report received but bundle not "
                       f"staged — staging nudge #{state['nudges'] + 1} sent.")
        return False
    # fetch bundle + companions
    outdir = os.path.join(OUTROOT, name)
    os.makedirs(outdir, exist_ok=True)
    fetched = []
    for fn in SESSIONS[name]:
        if fn in tree:
            dest = os.path.join(outdir, fn)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                fetched.append(fn)
                continue
            try:
                raw = fetch_bytes(chat, ws, fn)
                with open(dest, "wb") as f:
                    f.write(raw)
                fetched.append(fn)
                log(name, f"fetched {fn} ({len(raw)} bytes)")
            except Exception as e:
                log(name, f"fetch {fn} FAILED ({e!r})")
        else:
            log(name, f"companion {fn} not staged (skipped — bundle is the deliverable)")
    bpath = os.path.join(outdir, bundle_name)
    if not os.path.exists(bpath) or os.path.getsize(bpath) == 0:
        log(name, "bundle fetch incomplete — retry next round")
        return False
    # verify
    # verify INSIDE a repo that contains the prerequisite commits (the
    # Lead's Flauz clone at the pinned base) — `git bundle verify` checks
    # prerequisite existence in the surrounding repo; the harvest outdir is
    # not a repository (the 2026-09-27 false VERIFY-FAILED)
    GATE_REPO = "/home/z/Flauz"
    v = subprocess.run(["git", "bundle", "verify", os.path.abspath(bpath)],
                       capture_output=True, text=True, cwd=GATE_REPO)
    ok = v.returncode == 0
    head = None
    if ok:
        ls = subprocess.run(["git", "bundle", "list-heads", bpath], capture_output=True, text=True)
        head = (ls.stdout or "").split("\n")[0].strip()
    rec = {"name": name, "chat": chat, "workspace": ws, "ts": int(time.time()),
           "bundle": bundle_name, "bytes": os.path.getsize(bpath),
           "verify": "ok" if ok else "FAILED", "head": head,
           "files": fetched}
    with open(os.path.join(FLAGS, f"{name}.harvest.json"), "w") as f:
        json.dump(rec, f, indent=1)
    log(name, f"HARVEST {'COMPLETE' if ok else 'VERIFY-FAILED'}: {rec['bytes']} bytes, head {head}")
    outbox(f"[TL1] {name} HARVEST {'COMPLETE' if ok else 'VERIFY-FAILED'} — bundle "
           f"{rec['bytes']} bytes at leads-harvest/{name}/ ({head or 'no-head'}). "
           + ("Pod released; Lead gates next." if ok else "Lead attention required."))
    if ok:
        release_pod(chat)
        log(name, f"pod {ws[:14]} released (slot hygiene)")
    return ok


def _state(name, **updates):
    """Tiny per-session nudge state file."""
    p = os.path.join(FLAGS, f"{name}.harvest-state.json")
    st = {"nudges": 0, "last_nudge": 0}
    try:
        st.update(json.load(open(p)))
    except Exception:
        pass
    if updates:
        st.update(updates)
        json.dump(st, open(p, "w"))
    return st


def main():
    done = {}
    started = time.time()
    log("sentinel", f"up — watching {len(SESSIONS)} sessions for completion markers")
    outbox("[TL1] harvest sentinel armed — on each completion marker: bundle "
           "check -> fetch -> verify -> pod release -> Lead gates notice.")
    while True:
        for name in SESSIONS:
            if done.get(name):
                continue
            marker = os.path.join(FLAGS, f"{name}-complete.marker")
            if not os.path.exists(marker):
                continue
            if harvest(name):
                done[name] = True
                log("sentinel", f"{name} harvested ({len(done)}/{len(SESSIONS)})")
        if len(done) == len(SESSIONS):
            log("sentinel", "ALL SESSIONS HARVESTED — exiting")
            outbox("[TL1] harvest sentinel: all sessions harvested — Lead gates + PRs next.")
            return 0
        if time.time() - started > GIVE_UP_AFTER:
            log("sentinel", "gave up after 14h — standing down (unharvested: "
                f"{[n for n in SESSIONS if not done.get(n)]})")
            outbox("[TL1] harvest sentinel: 14h window expired — Lead must handle "
                   f"the remaining sessions manually.")
            return 1
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    sys.exit(main())
