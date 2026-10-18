#!/usr/bin/env python3
"""api_gate.py — watch for the degraded window to clear (chats API recovery).

The 2026-10-18 ~22:00Z window: /api/v1/chats/?page=1&type=all&channel=zai-web
returns 405/WAF-block even for the SPA's own calls (auth 200s fine). Until it
recovers, lane recon is impossible (r3-w3c's chat id is registry-lost) and
fresh dispatches cannot establish.

This gate probes the endpoint from inside the page every CYCLE seconds. On
REAL JSON (200 + parseable), it: writes flags/api_recovered.txt, notifies the
outbox, and dumps the recent-chats recon (id/title/updated) to
flags/api_recon.json + the log — then stands down (one-shot).

Launch: dfork_launch.py logs/api_gate.log <venv-py> api_gate.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
RECOVERED = os.path.join(FLAGS, "api_recovered.txt")
RECON = os.path.join(FLAGS, "api_recon.json")
CYCLE = 180
CAP = 12 * 3600

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
            "title": str(c.get("title") or c.get("name") or "")[:70],
            "updated": str(c.get("updatedAt") or c.get("updateTime") or c.get("updated_at") or "")[:24],
        })
    return rows


def main():
    os.makedirs(FLAGS, exist_ok=True)
    if os.path.exists(RECOVERED):
        log("already recovered — standing down")
        return
    t0 = time.time()
    streak = 0
    log("armed — %ds cycles, watching /api/v1/chats/ for the window to clear" % CYCLE)
    while time.time() - t0 < CAP:
        d = probe()
        if not d.get("blocked"):
            streak += 1
            log("PROBE OK (streak %d)" % streak)
            if streak >= 2:
                rows = recon(d)
                with open(RECON, "w") as f:
                    json.dump(rows, f, indent=1)
                with open(RECOVERED, "w") as f:
                    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                log("WINDOW CLEARED — recon rows: %d (saved %s)" % (len(rows), RECON))
                for r in rows[:20]:
                    log("  chat %-16s %-24s %s" % (r["id"], r["updated"], r["title"]))
                outbox("API WINDOW CLEARED — chats API recovered. Recon saved: %d rows "
                       "(flags/api_recon.json). TL: identify r3-w3c, assess lane, "
                       "harvest or redispatch merchant #4; then R4 lanes." % len(rows))
                return
        else:
            streak = 0
            log("blocked (status=%s err=%s) — window still on" % (d.get("status"), d.get("err")))
        time.sleep(CYCLE)
    log("CAP reached without recovery — outbox notify")
    outbox("API GATE CAP (12h) — chats API still blocked. TL attention needed.")


if __name__ == "__main__":
    main()
