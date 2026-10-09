#!/usr/bin/env python3
"""wfx_lane_watch.py — TL2 resident lane monitor for WebFlix worker chats.

Polls each configured chat.z.ai worker session via the batch messages API
(server-side truth; no DOM dependency). Per lane:
  - every POLL seconds: fetch history + batch, measure the last assistant
    message, detect work markers and the final-report marker
  - state transitions are appended to logs/wfx-lane-watch.log
  - when a lane's report marker appears: auto-harvest the full final
    assistant message verbatim to worker-reports/<name>-report.txt and set
    flags/<name>-report-ready (TL2's watch loop picks it up for review)
  - when a lane goes silent past STALL_SILENT while NOT having delivered:
    set flags/<name>-stalled (TL2 decides kick/redispatch — this monitor
    never writes into worker chats itself)

Lane registry: flags/wfx-lanes.json  [{name, chat_id, marker, delivered}]
(re-writable by TL2 at any time; changes are picked up next cycle).
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "wfx-lane-watch.log")
LANES = os.path.join(FLAGS, "wfx-lanes.json")
OUTDIR = os.path.join(BASE, "worker-reports")
POLL = int(os.environ.get("WFX_POLL", "75"))
STALL_SILENT = int(os.environ.get("WFX_STALL_SILENT", "1500"))  # 25 min
WORK_MARKERS = ("Thought Process", "Ran ", "Wrote ", "Terminal",
                "Todo Progress", "Explored", "Read File", "Searching", "$ ")


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_lanes():
    try:
        return json.load(open(LANES))
    except Exception:
        return []


def save_lanes(lanes):
    tmp = LANES + ".tmp"
    with open(tmp, "w") as f:
        json.dump(lanes, f, indent=1)
    os.replace(tmp, LANES)


FETCH_JS = """(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
  const r = await fetch('/api/v1/chats/%s', {credentials: 'include', cache: 'no-store', headers: hdr});
  if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
  const j = await r.json();
  const msgs = ((j.chat || {}).history || {}).messages || {};
  const byTs = Object.values(msgs).sort((a,b) => (a.timestamp||0)-(b.timestamp||0));
  const ids = byTs.map(m => m.id).filter(Boolean);
  if (!ids.length) return JSON.stringify({err: 'no ids'});
  const br = await fetch('/api/v1/chats/%s/messages/batch', {
    credentials: 'include', cache: 'no-store', method: 'POST',
    headers: Object.assign({'Content-Type': 'application/json'}, hdr),
    body: JSON.stringify({ids})});
  if (!br.ok) return JSON.stringify({err: 'batch-http-' + br.status});
  const bj = await br.json();
  const data = (bj && (bj.data || bj.messages)) || {};
  let lastTs = 0, workHits = 0, reportMsg = null, nAssistant = 0, gen = null;
  for (const m of byTs) {
    const full = data[m.id];
    if (!full) continue;
    const role = full.role || m.role || 'assistant';
    if (role === 'user') continue;
    nAssistant += 1;
    const blocks = full.content_blocks || full.blocks || [];
    let joined = '', textOnly = '';
    for (const b of blocks) {
      let t = '';
      if (typeof b.content === 'string') t = b.content;
      else if (typeof b.text === 'string') t = b.text;
      joined += t;
      if (b.type === 'text') textOnly += t;
      if (b.type === 'tool_calls') gen = 'tool_calls';
    }
    for (const mk of %s) if (joined.includes(mk)) workHits += 1;
    if (textOnly.includes('%s') && textOnly.includes('%s')) reportMsg = textOnly;
    else if (textOnly.includes('%s') && !reportMsg) reportMsg = textOnly;
    if (m.timestamp > lastTs) lastTs = m.timestamp;
  }
  return JSON.stringify({n: nAssistant, lastTs, workHits, gen,
    reportLen: reportMsg ? reportMsg.length : 0, reportText: reportMsg || ''});
})()"""


def poll_lane(lane):
    tab = channel.find_tab("chat.z.ai")
    if not tab:
        return {"err": "no-tab"}
    cid = lane["chat_id"]
    ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=45)
    try:
        js = FETCH_JS % (cid, cid, json.dumps(list(WORK_MARKERS)),
                          lane["head"], lane["marker"], lane["marker"])
        raw = ws.eval(js, await_promise=True, timeout=75)
        return json.loads(raw)
    finally:
        ws.close()


def dom_probe(lane):
    """Body-length probe on the lane's own tab (live-turn signal)."""
    try:
        for t in channel.list_tabs():
            if lane["chat_id"] in (t.get("url") or ""):
                ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
                try:
                    raw = ws.eval("document.body.innerText.length", timeout=12)
                    return int(raw)
                finally:
                    ws.close()
    except Exception:
        pass
    return None


def main():
    log("lane-watch online (poll=%ss stall=%ss)" % (POLL, STALL_SILENT))
    last_sig = {}
    dom_len = {}
    while True:
        lanes = load_lanes()
        for lane in lanes:
            name = lane["name"]
            try:
                d = poll_lane(lane)
            except Exception as e:
                log("%s poll error %r" % (name, e))
                continue
            if "err" in d:
                log("%s poll api err: %s" % (name, d["err"]))
                continue
            now = time.time()
            dlen = dom_probe(lane)
            grew = dlen is not None and dlen > dom_len.get(name, 0) + 200
            if dlen is not None:
                dom_len[name] = dlen
            sig = (d["n"], d["lastTs"], d["reportLen"], dlen)
            if sig != last_sig.get(name):
                log("%s n=%d lastTs=%s work=%d gen=%s reportLen=%d domLen=%s" % (
                    name, d["n"], d["lastTs"], d["workHits"], d["gen"], d["reportLen"], dlen))
                last_sig[name] = sig
            if d["reportLen"] and not lane.get("delivered"):
                try:
                    os.makedirs(OUTDIR, exist_ok=True)
                    path = os.path.join(OUTDIR, "%s-report.txt" % name)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(d["reportText"])
                    open(os.path.join(FLAGS, "%s-report-ready" % name), "w").write(
                        "chars=%d ts=%d\n" % (d["reportLen"], now))
                    lane["delivered"] = True
                    lane["delivered_at"] = now
                    save_lanes(lanes)
                    log("%s REPORT DELIVERED (%d chars) -> %s [flag set]" % (
                        name, d["reportLen"], path))
                except Exception as e:
                    log("%s harvest error %r" % (name, e))
            elif not lane.get("delivered"):
                ts = d["lastTs"] or 0
                if ts > 1e12: ts /= 1000.0
                if ts < 1e9: ts = 0
                silent = now - (ts if ts else lane.get("started", now))
                if (STALL_SILENT and silent > STALL_SILENT and d["n"] > 0
                        and d["workHits"] == 0 and not grew):
                    stall_flag = os.path.join(FLAGS, "%s-stalled" % name)
                    if not os.path.exists(stall_flag):
                        open(stall_flag, "w").write("silent=%.0fs\n" % silent)
                        log("%s STALLED (silent %.0fs, no work markers)" % (name, silent))
        time.sleep(POLL)


if __name__ == "__main__":
    main()
