#!/usr/bin/env python3
"""api_gate.py v2 — watch for the degraded window to clear; ACT on clear.

The 2026-10-18 ~22:00Z window (inverted class): /api/v1/chats* returns
405/WAF-block even for the SPA's own calls (auth 200, web-dev/workspaces
200, PFS 200 — ONLY the chats family). Composer sends fail silently
(status-0 telemetry). Lane recon + dispatch are impossible while it is on.

v2 clear-action (the Task-85 r4_gate doctrine, registry-free):
  on WINDOW-CLEAR (2 consecutive unblocked probes):
    1. recon the recent-chats list -> flags/api_recon.json
    2. case-split on merchant-lane evidence (title ~ R3-W3|merchant):
       - NO candidate: AUTO-DISPATCH payswap3-r3-w3d with the rebuilt
         hardened packet (dispatch_worker.py create) + arm the station
         watch v4 (registry-driven; picks the lane up from the dispatch
         registry row) + outbox.
       - candidate(s) found: NO dispatch (TL verifies aliveness next
         turn; conservative — a live r3-w3c beats a blind duplicate).
    3. stand down (one-shot).

Launch: dfork_launch.py logs/api_gate.log <venv-py> api_gate.py
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
RECOVERED = os.path.join(FLAGS, "api_recovered.txt")
RECON = os.path.join(FLAGS, "api_recon.json")
LOGS = os.path.join(BASE, "logs")
CYCLE = 180
CAP = 12 * 3600
VENV_PY = "/home/z/.venv/bin/python3"
PKT = os.path.join(BASE, "worker-prompts", "pkt_r3-w3.md")
MERCHANT_RX = ("r3-w3", "merchant", "r3w3")

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
  try { return JSON.stringify({blocked: false, status: r.status, body: t.slice(0, 20000)}); }
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


def probe():
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        return {"blocked": True, "err": "no-tab"}
    ws = channel.CDP(tabs[-1]["webSocketDebuggerUrl"])
    try:
        raw = ws.eval(PROBE_JS, await_promise=True, timeout=45)
        return json.loads(raw if isinstance(raw, str) else json.dumps(raw))
    except Exception as e:
        return {"blocked": True, "err": str(e)[:120]}
    finally:
        ws.close()


def recon(d):
    body = d.get("body") or ""
    try:
        j = json.loads(body)
    except Exception:
        return []
    items = j.get("data", j) if isinstance(j, dict) else j
    if isinstance(items, dict):
        for k in ("chatList", "chats", "items", "list", "records"):
            if isinstance(items.get(k), list):
                items = items[k]
                break
    if not isinstance(items, list):
        return []
    rows = []
    for c in items[:40]:
        rows.append({
            "id": str(c.get("id") or c.get("chatId") or c.get("uuid") or "")[:16],
            "title": str(c.get("title") or c.get("name") or "")[:90],
            "updated": str(c.get("updatedAt") or c.get("updateTime") or c.get("updated_at") or "")[:24],
        })
    return rows


def merchant_candidates(rows):
    out = []
    for r in rows:
        t = (r.get("title") or "").lower()
        if any(k in t for k in MERCHANT_RX):
            out.append(r)
    return out


def sh(cmd, timeout=900):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=BASE)
        return (p.returncode, (p.stdout or "")[-1500:], (p.stderr or "")[-800:])
    except subprocess.TimeoutExpired:
        return (124, "timeout", "")


def dispatch_merchant4():
    """Create payswap3-r3-w3d with the rebuilt hardened packet."""
    log("dispatching payswap3-r3-w3d (merchant #4, hardened packet)")
    rc, so, se = sh([VENV_PY, "dispatch_worker.py", "create",
                     "payswap3-r3-w3d", PKT])
    log("dispatch rc=%s out tail: %s" % (rc, so[-400:]))
    return rc, so, se


def arm_station_watch():
    """Launch payswap_station_watch.py if not already running."""
    try:
        p = subprocess.run(["pgrep", "-f", "payswap_station_watch.py"],
                           capture_output=True, text=True)
        if p.stdout.strip():
            log("station watch already running (pid %s)" % p.stdout.strip().split()[0])
            return True
    except Exception:
        pass
    log("arming payswap_station_watch.py")
    try:
        subprocess.Popen([VENV_PY, "dfork_launch.py",
                          os.path.join(LOGS, "station_watch.log"),
                          VENV_PY, "payswap_station_watch.py"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, cwd=BASE)
        time.sleep(3)
        return True
    except Exception as e:
        log("watch arm failed: %r" % e)
        return False


def clear_action(rows):
    with open(RECOVERED, "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    cands = merchant_candidates(rows)
    log("WINDOW CLEARED — recon rows: %d; merchant candidates: %d" % (len(rows), len(cands)))
    for r in rows[:20]:
        log("  chat %-16s %-24s %s" % (r["id"], r["updated"], r["title"][:60]))
    for r in cands:
        log("  CANDIDATE %s %s %s" % (r["id"], r["updated"], r["title"][:60]))
    if cands:
        outbox("API WINDOW CLEARED — merchant-lane candidates found in recon "
               "(%d). NO auto-dispatch (conservative; TL verifies r3-w3c "
               "aliveness next turn). Candidates: %s" %
               (len(cands), json.dumps(cands)))
        return
    # no candidates -> auto-dispatch merchant #4
    rc, so, se = dispatch_merchant4()
    if rc == 0 and ("sent" in so.lower() or "ok" in so.lower() or "prompt" in so.lower()):
        arm_station_watch()
        outbox("API WINDOW CLEARED — no merchant candidate in recon. "
               "AUTO-DISPATCHED payswap3-r3-w3d (merchant #4, hardened "
               "packet, base c5a4dc7). Station watch v4 armed. rc=%s" % rc)
    else:
        arm_station_watch()
        outbox("API WINDOW CLEARED — no merchant candidate. Dispatch attempt "
               "rc=%s out=%s err=%s — TL retry needed." % (rc, so[-300:], se[-200:]))


def main():
    os.makedirs(FLAGS, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    if os.path.exists(RECOVERED):
        log("already recovered — standing down")
        return
    t0 = time.time()
    streak = 0
    log("armed v2 — %ds cycles; on clear: recon + case-split dispatch" % CYCLE)
    while time.time() - t0 < CAP:
        d = probe()
        if not d.get("blocked"):
            streak += 1
            log("PROBE OK (streak %d)" % streak)
            if streak >= 2:
                rows = recon(d)
                try:
                    with open(RECON, "w") as f:
                        json.dump(rows, f, indent=1)
                except Exception:
                    pass
                clear_action(rows)
                return
        else:
            streak = 0
            log("blocked (status=%s err=%s) — window still on" % (d.get("status"), d.get("err")))
        time.sleep(CYCLE)
    log("CAP reached without recovery — outbox notify")
    outbox("API GATE v2 CAP (12h) — chats API still blocked. TL attention needed.")


if __name__ == "__main__":
    main()
