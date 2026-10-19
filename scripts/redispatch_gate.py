#!/usr/bin/env python3
"""redispatch_gate.py — degraded-window watcher + VERIFIED re-dispatcher.

FORENSICS (2026-10-19 20:50Z): the FH-3 three-lane dispatch (18:55Z) was a
phantom success. The platform's degraded window made chat-creation POSTs
fail silently — the composer clears (dispatch_worker's send gate passes),
the tab never navigates to /c/<id>, no chat exists server-side — yet
create() recorded sent:true with url=home (the generating-state check
passed on the home surface; the /c/ + server-verify branch is unreachable
in that path). The station watch then nudge-looped the home tabs for 2h
(17+ nudges per lane; each spawned a garbage "New Chat" shell — 50
accumulated in the sidebar). Browser-history forensics: ZERO /c/ visits
between 18:20:07 and 19:16:11 = the dispatches never landed.

Lanes voided 20:53Z. This gate owns re-delivery:

  1. PROBE the chats list API every CYCLE seconds (in-page fetch; opens a
     probe tab if none exists). WINDOW-CLEAR = 2 consecutive clean probes.
  2. On clear: verify remote HEAD still equals the packets' BASE_SHA (else
     stand down — packets need a TL rebase).
  3. Re-dispatch each lane via dispatch_worker create.
  4. VERIFY each create EXTERNALLY: the registry's latest record for the
     name must carry sent:true AND a /c/ url (the phantom-failure detector
     create() lacks). Failed creates are voided (name freed) + retried.
  5. On full success: write flags/redispatch_complete.json + outbox, launch
     the station watch v4.4 (dfork), stand down.

CAP 12h. ROUNDS_MAX dispatch rounds (one burst per window-clear).
Launch: dfork_launch.py logs/redispatch_gate.log /home/z/.venv/bin/python3 redispatch_gate.py
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
COMPLETE = os.path.join(FLAGS, "redispatch_complete.json")
LOGS = os.path.join(BASE, "logs")

CYCLE = 180
CAP = 12 * 3600
ROUNDS_MAX = 8
CREATE_TIMEOUT = 480
BASE_SHA = "9e481f2caf9ae3134d6567cd302fda25660a971b"
VERIFY_CLONE = "/home/z/payswap3-0"
VENV_PY = "/home/z/.venv/bin/python3"

LANES = [
    ("payswap3-r4-w2b", os.path.join(BASE, "worker-prompts", "pkt_r4-w2.md")),
    ("payswap3-r4-w3b", os.path.join(BASE, "worker-prompts", "pkt_r4-w3.md")),
    ("payswap3-gov-w1r3", os.path.join(BASE, "worker-prompts", "pkt_gov-w1.md")),
]

PROBE_JS = """
(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const r = await fetch('/api/v1/chats/?page=1&type=all&channel=zai-web', {
    credentials: 'include', cache: 'no-store',
    headers: {Authorization: 'Bearer ' + tok, Accept: 'application/json'}
  });
  const ct = r.headers.get('content-type') || '';
  const t = await r.text();
  if (!r.ok || ct.includes('text/html')) return JSON.stringify({blocked: true, status: r.status});
  try { const j = JSON.parse(t); return JSON.stringify({blocked: false, status: r.status, rows: (Array.isArray(j) ? j : (j.data || j.chatList || j.chats || [])).length}); }
  catch (e) { return JSON.stringify({blocked: true, status: r.status, err: String(e)}); }
})()
"""


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def ensure_probe_tab():
    """The probe needs a chat.z.ai tab; open one if none exists."""
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if tabs:
        return tabs[-1]
    try:
        tab = channel.new_tab("https://chat.z.ai/")
        time.sleep(6)
        return tab
    except Exception as e:
        log(f"probe-tab open failed: {str(e)[:80]}")
        return None


def probe():
    tab = ensure_probe_tab()
    if tab is None:
        return {"blocked": True, "err": "no-tab"}
    try:
        ws = channel.CDP(tab["webSocketDebuggerUrl"])
        try:
            raw = ws.eval(PROBE_JS, await_promise=True, timeout=45)
            return json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        finally:
            ws.close()
    except Exception as e:
        return {"blocked": True, "err": str(e)[:120]}


def latest_record(name):
    """Last registry record for `name` (file order wins)."""
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except Exception:
        return None
    out = None
    for r in recs:
        if r.get("name") == name:
            out = r
    return out


def lane_verified(name):
    """EXTERNAL phantom-failure detector: latest record must be a sent
    create carrying a /c/ url (and not voided after)."""
    r = latest_record(name)
    if not r:
        return False
    if r.get("action") in ("void", "done", "failed"):
        return False
    return bool(r.get("sent")) and "/c/" in (r.get("url") or "")


def verify_base():
    """Remote HEAD must still equal the packets' base SHA."""
    try:
        r = subprocess.run(["git", "ls-remote", "origin", "main"],
                           capture_output=True, text=True, timeout=60,
                           cwd=VERIFY_CLONE)
        head = (r.stdout or "").split()[0] if r.stdout else ""
        return head == BASE_SHA, head
    except Exception as e:
        return False, str(e)[:80]


def dispatch_lane(name, pkt):
    """One create attempt. Returns True when the registry record verifies."""
    r = latest_record(name)
    if r and r.get("action") is None and r.get("sent") and "/c/" in (r.get("url") or ""):
        return True  # already established (e.g. supervisor raced us)
    if r and r.get("action") is None:
        # stale non-terminal record (failed create, no void) — void to free the name
        subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                        "void", name, "gate: pre-dispatch cleanup of stale record"],
                       capture_output=True, text=True, timeout=120, cwd=BASE)
    log(f"{name}: dispatching ({os.path.basename(pkt)})")
    try:
        p = subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                            "create", name, pkt],
                           capture_output=True, text=True, timeout=CREATE_TIMEOUT,
                           cwd=BASE)
        tail = (p.stdout or "").strip().splitlines()[-3:]
        for line in tail:
            log(f"  {name}: {line[:110]}")
    except subprocess.TimeoutExpired:
        log(f"  {name}: create TIMED OUT ({CREATE_TIMEOUT}s)")
    # clear any capacity-recovery flag the create may have written (the
    # gate owns retries; the supervisor ring is not running)
    for suf in (name, name.replace("payswap3-", "")):
        fp = os.path.join(FLAGS, f"capacity_recover.{suf}.json")
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
    ok = lane_verified(name)
    if not ok:
        subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                        "void", name, "gate: create did not verify (no /c/ record)"],
                       capture_output=True, text=True, timeout=120, cwd=BASE)
        log(f"  {name}: NOT VERIFIED (no /c/ record) — voided for retry")
    return ok


def launch_watch():
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "dfork_launch.py"),
                            os.path.join(LOGS, "station_watch.log"),
                            VENV_PY, os.path.join(BASE, "payswap_station_watch.py")],
                           capture_output=True, text=True, timeout=60, cwd=BASE)
        log(f"station watch v4.4 launched (rc={r.returncode})")
    except Exception as e:
        log(f"watch launch FAILED: {str(e)[:80]} — TL must launch manually")


def main():
    log("redispatch gate online — probing for window clear; lanes: "
        + ", ".join(n for n, _ in LANES))
    outbox("REDISPATCH GATE armed: watching for the degraded window to "
           "clear, then verified re-dispatch of r4-w2 + r4-w3 + gov-w1r2 "
           "(base 9e481f2).")
    streak = 0
    deadline = time.time() + CAP
    rounds = 0
    verified = set()
    while time.time() < deadline and len(verified) < len(LANES):
        d = probe()
        if d.get("blocked"):
            if streak:
                log(f"window BLOCKED again (status={d.get('status')} "
                    f"err={d.get('err', '')[:40]}) — streak reset")
            else:
                log(f"window still BLOCKED (status={d.get('status')} "
                    f"err={d.get('err', '')[:40]})")
            streak = 0
        else:
            streak += 1
            log(f"probe clean (status={d.get('status')}, rows={d.get('rows')}) "
                f"— streak {streak}/2")
        if streak >= 2:
            streak = 0
            rounds += 1
            log(f"WINDOW CLEAR — dispatch round {rounds}/{ROUNDS_MAX}")
            ok_base, head = verify_base()
            if not ok_base:
                log(f"BASE DRIFT: remote main = {head} != {BASE_SHA} — "
                    "STANDING DOWN (TL must rebase packets)")
                outbox(f"REDISPATCH GATE stood down: remote main moved to "
                       f"{head} (packets built on {BASE_SHA[:8]}). TL: rebase "
                       f"pkt_r4-w2/w3/gov-w1r2 then re-arm the gate.")
                return 4
            for name, pkt in LANES:
                if name in verified:
                    continue
                if dispatch_lane(name, pkt):
                    verified.add(name)
                    rec = latest_record(name) or {}
                    log(f"{name}: VERIFIED at {rec.get('url', '?')[:60]}")
                    outbox(f"REDISPATCH VERIFIED: {name} established at "
                           f"{(rec.get('url') or '?')[:70]}")
            if len(verified) == len(LANES):
                with open(COMPLETE, "w") as f:
                    json.dump({"ts": int(time.time()), "lanes": sorted(verified),
                               "base": BASE_SHA}, f)
                outbox("REDISPATCH COMPLETE: all three lanes established "
                       "(/c/-verified). Station watch v4.4 takes over.")
                launch_watch()
                log("ALL LANES VERIFIED — gate standing down")
                return 0
            if rounds >= ROUNDS_MAX:
                log("rounds exhausted — standing down")
                outbox(f"REDISPATCH GATE: rounds exhausted; verified "
                       f"{len(verified)}/{len(LANES)} "
                       f"({', '.join(sorted(verified)) or 'none'}). TL: assess "
                       f"remaining lanes manually.")
                return 3
            # partial failure: the window may have flapped mid-burst —
            # fall through to the probe loop (streak rebuilds from zero)
        time.sleep(CYCLE)
    log("cap reached — standing down")
    outbox("REDISPATCH GATE: 12h cap reached. TL: assess window state.")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
