#!/usr/bin/env python3
"""composer_watch.py — gentle composer-retry + tool-block verifier.

2026-10-04 06:05Z finding: raw kicks spawn PLAIN turns (no agent runtime);
only platform-admitted composer turns carry tools (the 04:02:30 admission
proved it). This watcher: every CYCLE seconds per lane, when the lane's
newest assistant turn is NOT tool-bearing and has stalled, tries ONE
gentle composer send (channel.send_text, no assault ladder) on the lane's
tab. After a landed send it waits and checks the response's blocks for
tool_calls — the signal that full agent mode returned. Narrations are
counted but never harvested here (the TL handles narrative transport).
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import channel  # noqa: E402

LOG = os.path.join(HERE, "logs", "composer-watch.log")
CYCLE = 240  # 4 min per lane
MAX_HOURS = 16

REGISTRY = os.path.join(HERE, "flags", "session_registry.jsonl")

FALLBACK_LANES = {
    "w126": "cfdefe55-eee0-4a65-8258-9dbf8d4d355d",
    "w131": "734cbc9a-6d9d-4499-ad67-cc854246eb98",
}

MSG = ("Continue your work order with REAL tool calls (Bash/Read/Write). "
       "Proceed to the next concrete step in your sandbox and keep going "
       "until the delivery is complete, then post the real report.")


def log(m):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}Z] {m}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def resolve_lanes():
    lanes = {}
    tabs_by_url = {}
    try:
        for t in channel.list_tabs():
            tabs_by_url[t.get("url", "")] = t
    except Exception:
        pass
    try:
        for line in open(REGISTRY):
            try:
                r = json.loads(line)
            except Exception:
                continue
            name = r.get("name") or ""
            if not (name.startswith("w12") or name.startswith("w13")):
                continue
            key = name.replace("-2", "").replace("-3", "").split("-company")[0].split("-query")[0].split("-execution")[0].split("-contracts")[0].split("-fabric")[0].split("-roles")[0].split("-platform")[0].split("-loop")[0]
            if r.get("action") == "void" or r.get("event") == "void":
                lanes.pop(key, None)  # a void kills the lane family
                continue
            url = r.get("url") or ""
            if "/c/" in url:
                lanes[key] = {"cid": url.split("/c/")[-1], "url": url,
                              "tab": tabs_by_url.get(url)}
    except FileNotFoundError:
        pass
    for k, v in FALLBACK_LANES.items():
        lanes.setdefault(k, {"cid": v, "url": f"https://chat.z.ai/c/{v}", "tab": tabs_by_url.get(f"https://chat.z.ai/c/{v}")})
    return lanes


def tree_and_blocks(cid):
    """(newest_ts, last_assistant_has_tools, total) from a dedicated tab."""
    tab = channel.new_tab("https://chat.z.ai/")
    if tab is None:
        raise RuntimeError("probe tab failed")
    time.sleep(5)
    tabs = {t["id"]: t for t in channel.list_tabs()}
    t = tabs.get(tab["id"], tab)
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
          const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store', headers: hdr});
          const j = await r.json();
          const hist = (j.chat || {}).history || {};
          const mmap = hist.messages || {};
          const byTs = Object.values(mmap).sort((a,b) => (a.timestamp||0)-(b.timestamp||0));
          const ids = byTs.map(m => m.id).filter(Boolean);
          const br = await fetch('/api/v1/chats/%s/messages/batch', {
            credentials: 'include', cache: 'no-store', method: 'POST',
            headers: Object.assign({'Content-Type': 'application/json'}, hdr),
            body: JSON.stringify({ids})});
          const bj = await br.json();
          const data = (bj && (bj.data || bj.messages)) || {};
          let newest = 0, tools = false;
          const asst = byTs.filter(m => m.role === 'assistant');
          for (const m of byTs) if ((m.timestamp||0) > newest) newest = m.timestamp||0;
          for (const m of asst.slice(-3)) {
            const b = data[m.id];
            const blocks = (b && (b.content_blocks || b.blocks)) || [];
            for (const x of blocks) {
              if (String(x.type||'') === 'tool_calls') tools = true;
            }
          }
          return JSON.stringify({newest, tools, total: byTs.length});
        })()""" % (cid, cid)
        return json.loads(ws.eval(js, await_promise=True, timeout=90))
    finally:
        try:
            ws.close()
        except Exception:
            pass
        try:
            channel._http_json("/json/close/" + t["id"], method="PUT")
        except Exception:
            pass


def gentle_send(lane):
    """One composer attempt on the lane's own tab (no assault ladder)."""
    tab = lane.get("tab")
    if not tab:
        # open a tab at the chat URL and register it for next time
        t = channel.new_tab(lane["url"])
        if t is None:
            return "no-tab"
        time.sleep(8)
        tabs = {x["id"]: x for x in channel.list_tabs()}
        tab = tabs.get(t["id"], t)
        lane["tab"] = tab
    try:
        channel.send_text(MSG, tab=tab)
        return "sent"
    except Exception as e:
        return f"err:{str(e)[:80]}"


def main():
    log("composer watch started (gentle single-send retries + tool verification)")
    state = {}
    start = time.time()
    while time.time() - start < MAX_HOURS * 3600:
        try:
            lanes = resolve_lanes()
        except Exception as e:
            log(f"resolve error: {e}")
            time.sleep(60)
            continue
        for name, lane in lanes.items():
            try:
                st = tree_and_blocks(lane["cid"])
            except Exception as e:
                log(f"{name}: probe err {str(e)[:80]}")
                continue
            s = state.setdefault(name, {"last_send": 0, "tool_turns": 0})
            age = time.time() - st["newest"]
            if st["tools"]:
                if not s.get("ever_tools"):
                    s["ever_tools"] = True
                    log(f"{name}: TOOL-BEARING TURN DETECTED (agent mode) — leaving alone")
                s["tool_turns"] += 1
                continue
            if age > 360 and time.time() - s["last_send"] > CYCLE:
                r = gentle_send(lane)
                log(f"{name}: stalled {int(age)}s (total={st['total']}) -> gentle send: {r}")
                s["last_send"] = time.time()
                break  # one send per cycle
        time.sleep(90)
    log("composer watch max-hours reached")


if __name__ == "__main__":
    sys.exit(main())
