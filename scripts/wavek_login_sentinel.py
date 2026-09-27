#!/usr/bin/env python3
"""wavek_login_sentinel.py (v2) — reset6 epoch (2026-09-27): on operator login,
resume wave-K of the Zeck compatibility roadmap (midnight deadline), across
resets: SCAN EXISTING CHATS FIRST, then dispatch only what is missing.

v2 upgrade (14:35): between 11:03 and 14:27 an earlier sentinel may have fired
wave-K dispatches (operator login during that window is unknown — reset6 wiped
the local evidence). Workers are SERVER-SIDE; their chats survive. So the
resume order is now: list the account's recent chats with FULL ids, title-match
the wave-K work orders (PPR-018A / PPR-019 / PPR-018), probe each candidate
with the END REPORT marker, and only re-dispatch what is neither complete,
watched, nor alive.

On login (read-only /api/status poll, 30s cadence, never sends):
  1. CDP fetch the chat list (full UUIDs, titles, updated) from the tab.
  2. Categorize: f978ac52... (known PPR-018 r1); title ~PPR-018A -> ppr018a;
     ~PPR-019 -> ppr019; ~PPR-018 (not A) -> ppr018.
  3. Probe each candidate server-side (full-UUID law, END REPORT marker):
     - reportInAssistant -> COMPLETE: outbox, Lead harvests (no slot);
     - alive, no marker, fresh (<40 min) -> reopen_and_watch.py;
     - dead / not found -> assault re-dispatch (r2 prompt, base b35d7e8).
  4. check_workspaces.py; stale slots -> dash_sandbox_release.py first.
  5. Establishment assaults for every wave-K member not complete/watched.
  6. Outbox every transition; exit 0 when the wave is armed.

Launch detached: dfork_launch.py /tmp/wavek_sentinel.log <py> wavek_login_sentinel.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
sys.path.insert(0, BASE)
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PROMPTS = os.path.join(BASE, "worker-prompts")

PPR018_CHAT = "f978ac52-61ab-4159-bc10-d3150b23a1fa"
MARKER = "END REPORT"
STATUS_URL = "http://localhost:3000/api/status"
FRESH_ACTIVITY_S = 40 * 60
LOGIN_WAIT_S = 7 * 3600  # midnight deadline: 14:35 + ~7h
HEARTBEAT = os.path.join(FLAGS, "wavek_sentinel.heartbeat")

WAVE = {
    "ppr018a": {"prompt": "ppr-018a-runner-harness.md",
                "title_pats": ["ppr-018a", "018a worker", "runner harness"]},
    "ppr019": {"prompt": "ppr-019-cline-proof.md",
               "title_pats": ["ppr-019", "019 worker", "cline"]},
    "ppr018": {"prompt": "ppr018-aider-proof-r2.md",
               "title_pats": ["ppr-018", "018 worker", "implementation guide steps", "aider"]},
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post(text):
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def run(cmd, timeout=900):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def wait_for_login(max_s=LOGIN_WAIT_S):
    t0 = time.time()
    last = None
    while time.time() - t0 < max_s:
        st = login_state()
        if st != last:
            log(f"browser_login={st}")
            last = st
        if st == "logged-in":
            return True
        try:
            os.makedirs(FLAGS, exist_ok=True)
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(30)
    return False


def chat_list():
    """Full-uuid + title + updated list via the logged-in tab's credentials."""
    import channel
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        return None
    ws = channel.CDP(tabs[-1]["webSocketDebuggerUrl"])
    js = """(async () => {
      const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
      const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
      const r = await fetch('/api/v1/chats/list?page=1&size=30', {credentials: 'include', cache: 'no-store', headers: hdr});
      if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
      const j = await r.json();
      const items = (j.data && (j.data.list || j.data.chats)) || (j.list) || (Array.isArray(j) ? j : []);
      return JSON.stringify({n: items.length, chats: items.map(c => ({
        id: String(c.id || c.uuid || ''),
        title: String(c.title || ''),
        updated: c.updatedAt || c.updateTime || c.updated_at || null}))});
    })()"""
    try:
        raw = ws.eval(js, await_promise=True, timeout=30)
        d = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        return d if not d.get("err") else None
    except Exception:
        return None
    finally:
        ws.close()


def probe(uuid, marker=MARKER):
    rc, out = run([PY, os.path.join(BASE, "probe_chat.py"), uuid, marker], timeout=120)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def classify(chats):
    """Map wave member -> list of candidate full-uuids (newest first)."""
    found = {k: [] for k in WAVE}
    for c in chats or []:
        cid = c.get("id") or ""
        title = (c.get("title") or "").lower()
        if not cid:
            continue
        if cid == PPR018_CHAT:
            found["ppr018"].insert(0, cid)
            continue
        if "ppr-018a" in title or "018a" in title:
            found["ppr018a"].insert(0, cid)
        elif "ppr-019" in title or "019" in title or "cline" in title:
            found["ppr019"].insert(0, cid)
        elif "ppr-018" in title or "implementation guide steps" in title or "aider" in title:
            found["ppr018"].insert(0, cid)
    return found


def probe_age(d):
    try:
        return int(d.get("now", 0)) - int(d.get("updated", 0))
    except Exception:
        return -1


def resolve_member(name, cands):
    """Returns 'complete' | 'watched' | 'missing'. Probes newest first."""
    for cid in cands[:3]:
        log(f"[{name}] probing candidate {cid[:8]} ...")
        d = probe(cid)
        if d is None or not d.get("alive"):
            log(f"[{name}] {cid[:8]} not alive")
            continue
        msgs = int(d.get("msgs", -1))
        age = probe_age(d)
        if d.get("reportInAssistant"):
            log(f"[{name}] {cid[:8]} COMPLETE (END REPORT present)")
            post(f"wave-K: {name} chat {cid[:8]} carries the END REPORT — COMPLETE. Lead harvest next (pod tree -> tarball -> battery -> merge).")
            return "complete"
        if msgs >= 2 and 0 <= age < FRESH_ACTIVITY_S:
            log(f"[{name}] {cid[:8]} alive (msgs={msgs}, age={age}s) -> watch")
            rc, out = run([PY, os.path.join(BASE, "reopen_and_watch.py"), cid, name, MARKER], timeout=300)
            log(f"reopen_and_watch rc={rc}: {(out or '').strip()[-160:]}")
            if rc == 0:
                post(f"wave-K: {name} chat {cid[:8]} alive server-side — tab re-opened, queue_watch[{name}] armed.")
                return "watched"
        else:
            log(f"[{name}] {cid[:8]} dead turn (msgs={msgs}, age={age}s)")
    return "missing"


def release_workspace_slots():
    log("checking workspace slots (reset doctrine)...")
    rc, out = run([PY, os.path.join(BASE, "check_workspaces.py")], timeout=180)
    tail = "\n".join((out or "").strip().splitlines()[-6:])
    log(f"check_workspaces rc={rc}:\n{tail}")
    if "Expired" in (out or ""):
        log("stale workspace rows detected -> dash_sandbox_release")
        rc2, out2 = run([PY, os.path.join(BASE, "dash_sandbox_release.py")], timeout=300)
        log(f"dash_sandbox_release rc={rc2}: {(out2 or '').strip()[-200:]}")
        post("wave-K: stale workspace rows released via dash_sandbox_release (doctrine — slots freed before assault).")


def assault(name, rounds=16):
    pf = os.path.join(PROMPTS, WAVE[name]["prompt"])
    log(f"assault[{name}] launching: {WAVE[name]['prompt']}")
    post(f"wave-K: dispatching {name} ({WAVE[name]['prompt']}) via establishment assault — the real work-order send, from inside the replay.")
    rc, out = run([PY, os.path.join(BASE, "establishment_assault.py"),
                   name, pf, MARKER, "360", str(rounds)], timeout=6 * 3600)
    tail = "\n".join((out or "").strip().splitlines()[-3:])
    log(f"assault[{name}] rc={rc}:\n{tail}")
    return rc


def main():
    log("wave-K login sentinel v2 start (reset6 epoch)")
    post("wave-K sentinel v2 armed (post-reset6): waiting for operator login through the replay image. On login: SCAN existing chats first (wave-K dispatches from the 11:03-14:27 window may be live server-side), then dispatch only what is missing (PPR-018A / PPR-019 / PPR-018). Midnight plan.")
    if not wait_for_login():
        post("wave-K sentinel: login window elapsed without login — exiting (re-arm on next session).")
        return 4
    log("LOGIN DETECTED — resuming wave-K (scan-first)")
    post("LOGIN DETECTED — wave-K scan-first resumption starting.")
    try:
        os.makedirs(FLAGS, exist_ok=True)
        open(os.path.join(FLAGS, "LOGIN_READY"), "w").write(str(int(time.time() * 1000)))
    except Exception:
        pass
    time.sleep(15)  # let the SPA settle post-login

    d = chat_list()
    if not d:
        log("chat list unavailable — falling back to the known PPR-018 uuid only")
        cands = {k: [] for k in WAVE}
        cands["ppr018"].append(PPR018_CHAT)
    else:
        log(f"chat list: {d.get('n')} chats")
        for c in d.get("chats", [])[:12]:
            log(f"  {c.get('id', '')[:12]}  {(c.get('title') or '')[:46]}")
        cands = classify(d.get("chats"))
        if PPR018_CHAT not in cands["ppr018"]:
            cands["ppr018"].append(PPR018_CHAT)

    status = {}
    for name in ("ppr018a", "ppr019", "ppr018"):
        c = cands.get(name) or []
        if c:
            status[name] = resolve_member(name, c)
        else:
            status[name] = "missing"
        log(f"{name}: {status[name]}")

    release_workspace_slots()

    results = {}
    for name in ("ppr018a", "ppr019", "ppr018"):
        if status[name] in ("complete", "watched"):
            continue
        results[name] = assault(name)

    ok = [k for k, v in results.items() if v == 0]
    bad = [k for k, v in results.items() if v != 0]
    parts = [f"{k}={status.get(k)}" for k in WAVE]
    summary = (f"wave-K resume pass complete: {', '.join(parts)}. "
               f"Fresh dispatches established={ok or 'none'}"
               f"{'; exhausted=' + ','.join(bad) if bad else ''}. "
               f"Watch ring armed per established session (END REPORT gate). "
               f"Midnight path: harvest+integrate each completion; PPR-020 when the wave closes.")
    log(summary)
    post(summary)
    return 0 if (ok or all(s in ("complete", "watched") for s in status.values())) else 3


if __name__ == "__main__":
    sys.exit(main())
