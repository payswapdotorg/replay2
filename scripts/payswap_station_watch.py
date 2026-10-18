#!/usr/bin/env python3
"""payswap_station_watch.py — unified station sentinel v4 (Task 85, 2026-10-18).

Replaces lane-watch v3 + renudge loop v2 + auto-harvest. Born from three
failure classes of the saturation era:
  1. STUCK-START: prompt lands, stop button activates, but NO content ever
     streams (site backend degraded). Old watchers saw stopBtn=True and
     classified it "GENERATING" — the lane died unwatched. LAW: stopBtn +
     body-frozen 3 consecutive cycles = stuck -> click Stop (clears the
     phantom generation; dispatch_worker send refuses busy chats) -> nudge.
  2. DEAD-LANE FALLBACK: find_tab falls back to ANY chat tab when the
     target is gone — probes read the WRONG chat. LAW: lane discovery from
     the session REGISTRY + tab pinned by tab_id; a missing tab = lane
     dead, never silently re-targeted.
  3. COMPLETION RECYCLING: completed sandboxes are recycled within minutes;
     end-loaded delivery lost two oracle-exact builds. LAW: markers checked
     every cycle; harvest_robust fires the moment they appear.

Cycles 120s. Per-lane nudge budget 24. Window 14h.

Launch: dfork_launch.py logs/station_watch.log <venv-py> payswap_station_watch.py
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
CYCLE = 120
STALL_AFTER = 1800        # 30 min without tree/worklog/body growth = stall
FROZEN_CYCLES = 3 # stopBtn + frozen body this many cycles = stuck
NUDGE_BUDGET = 24
WINDOW = 14 * 3600
MARKERS = ("COMPLETION-REPORT.md", "MANIFEST.sha256", ".bundle", ".bundle.b64")
TRACK_PREFIXES = ("payswap3-",)   # session names we watch


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def run(cmd, timeout=290):
    try:
        r = subprocess.run([sys.executable] + cmd, capture_output=True,
                           text=True, timeout=timeout, cwd=BASE)
        return (r.stdout or "").strip().splitlines()
    except subprocess.TimeoutExpired:
        return ["timeout"]


def live_lanes():
    """Registry-driven lane discovery: latest record per name; void/done
    invalidates. Returns name -> record."""
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except Exception:
        return {}
    latest = {}
    for r in recs:
        name = r.get("name") or ""
        if not name.startswith(TRACK_PREFIXES):
            continue
        act = r.get("action")
        if act in ("void", "done", "failed"):
            latest[name] = None
        elif r.get("sent") and r.get("url"):
            latest[name] = r
    return {n: r for n, r in latest.items() if r}


def tab_for(rec):
    """Pin the lane's tab by tab_id first; fall back to chat-url match ONLY
    when the record carries a /c/ url (never the generic any-tab fallback)."""
    tabs = channel.list_tabs()
    tid = rec.get("tab_id")
    if tid:
        for t in tabs:
            if t.get("id") == tid:
                return t
    url = rec.get("url") or ""
    if "/c/" in url:
        cid = url.split("/c/")[-1].split()[0]
        for t in tabs:
            if cid[:8] in (t.get("url") or ""):
                return t
    return None


def probe(tab):
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  return JSON.stringify({url: location.href, len: body.length, stopBtn, noresp});
})()""", timeout=20)
        return json.loads(raw)
    finally:
        cdp.close()


def click_stop(tab):
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        r = cdp.eval("""
(() => {
  // same selector family as the probe (aria-label OR css class) — the
  // innerText-only variant missed the real button ('gone' while stopBtn
  // probes true)
  let stop = document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  if (!stop) {
    stop = Array.from(document.querySelectorAll('button')).find(
      b => /^(Stop|Pause|Halt)$/i.test((b.innerText||'').trim()));
  }
  if (!stop) return 'gone';
  stop.click();
  return 'clicked:' + (stop.getAttribute('aria-label') || stop.className || '').slice(0, 40);
})()""", timeout=20)
        return r
    finally:
        cdp.close()


def page_eval(js, timeout=90):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def api_post(path, body):
    payload = json.dumps(body)
    return page_eval(f"(async () => {{ const r = await fetch('{path}', "
                     f"{{method:'POST',credentials:'include',"
                     f"headers:{{'Content-Type':'application/json'}},"
                     f"body:JSON.stringify({payload})}}); return await r.text(); }})()")


def discover_ws(chat_prefix):
    """chat-prefix -> workspace id via user-fc (bare-uuid law)."""
    try:
        raw = page_eval("(async () => { const r = await fetch('/api/v1/web-dev/"
                        "workspaces/user-fc', {credentials:'include'}); "
                        "return await r.text(); })()")
        data = json.loads(raw)
        v = data.get("data", data)
        items = v if isinstance(v, list) else next(
            (v[k] for k in ("workspaces", "list", "items")
             if isinstance(v.get(k), list)), [])
        for it in items:
            cid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
            if cid.startswith(chat_prefix[:8]):
                return it.get("function_name") or it.get("workspace_id") or it.get("id")
    except Exception:
        pass
    return None


def ws_tree(chat, ws_id):
    try:
        raw = api_post("/api/v1/web-dev/workspaces/files/ls-tree",
                       {"chatId": chat, "workspace_id": ws_id})
        d = json.loads(raw)
        if isinstance(d, dict):
            d = d.get("data", d)
        if isinstance(d, list):
            return [str(p) for p in d]
        if isinstance(d, dict) and isinstance(d.get("files"), list):
            return [str(p) for p in d["files"]]
    except Exception:
        pass
    return None


def main():
    log("station watch v4 online — registry-driven lanes; stuck-start law; "
        "marker auto-harvest")
    outbox("STATION WATCH v4 armed: unified sentinel (registry lanes + "
           "stuck-start force-unstick + marker auto-harvest). Replaces lane "
           "watch v3 / renudge v2 / auto-harvest.")
    state = {}
    deadline = time.time() + WINDOW
    while time.time() < deadline:
        lanes = live_lanes()
        for name, rec in lanes.items():
            s = state.setdefault(name, {
                "lens": [], "nudges": 0, "chat": None, "ws": None,
                "tree": 0, "wl": 0, "last_growth": time.time(),
                "stall_flagged": False, "harvested": False,
                "unstick_count": 0, "dead": False,
            })
            if s["dead"] or s["harvested"]:
                continue
            tab = tab_for(rec)
            if tab is None:
                # tab gone: if the record had a /c/ url, the chat may be
                # recycled — check the registry url directly
                url = rec.get("url") or ""
                if "/c/" in url:
                    s["dead"] = True
                    log(f"{name}: tab gone (chat {url.split('/c/')[-1][:8]}) "
                        f"— marking lane DEAD")
                    outbox(f"STATION WATCH: lane {name} tab/chat GONE "
                           f"(recycled or rolled back). TL: assess; "
                           f"redispatch may be needed.")
                continue
            try:
                st = probe(tab)
            except Exception as e:
                log(f"{name}: probe error {str(e)[:70]}")
                continue
            # chat url discovery (fresh chats start on the home surface)
            url = st.get("url") or ""
            if "/c/" in url and not s["chat"]:
                s["chat"] = url.split("/c/")[-1].split()[0]
                log(f"{name}: chat id assigned {s['chat'][:8]}")
            # liveness bookkeeping
            s["lens"].append(st.get("len") or 0)
            s["lens"] = s["lens"][-6:]
            grew = len(set(s["lens"][-3:])) > 1 or (
                len(s["lens"]) >= 2 and s["lens"][-1] != s["lens"][-2])
            # workspace tracking once the chat exists
            if s["chat"] and not s["ws"]:
                s["ws"] = discover_ws(s["chat"])
                if s["ws"]:
                    log(f"{name}: workspace {s['ws']}")
            if s["ws"]:
                paths = ws_tree(s["chat"], s["ws"])
                if paths is not None:
                    if len(paths) != s["tree"]:
                        if s["tree"]:
                            log(f"{name}: tree {s['tree']} -> {len(paths)}")
                        s["tree"] = len(paths)
                        grew = True
                    blob = "\n".join(paths)
                    marks = [m for m in MARKERS if m in blob]
                    if marks and not s["harvested"]:
                        s["harvested"] = True
                        log(f"{name}: MARKERS {marks} — AUTO-HARVEST")
                        outbox(f"AUTO-HARVEST LAUNCH: {name} carries {marks}. "
                               f"Pulling via harvest_robust NOW.")
                        lines = run([os.path.join(BASE, "harvest_robust.py"),
                                     s["chat"], s["ws"], "",
                                     f"/home/z/lanes/{name}-harvest"])
                        verdict = lines[-1] if lines else "?"
                        log(f"{name}: harvest: {verdict}")
                        outbox(f"AUTO-HARVEST DONE: {name} -> {verdict}. "
                               f"TL: MANIFEST verify + battery + merge + push.")
            if grew:
                s["last_growth"] = time.time()
                s["stall_flagged"] = False
            # the stuck-start law (2026-10-18 19:28 amendment: NEVER click
            # stop on a home-surface chat — a fresh chat exists only as its
            # pending first generation; stopping it destroys the chat and
            # the tab falls back to home. Stop-clicks are for ESTABLISHED
            # /c/ chats only; fresh chats get nudge-only recovery.)
            frozen = (len(s["lens"]) >= FROZEN_CYCLES
                      and len(set(s["lens"][-FROZEN_CYCLES:])) == 1)
            if st.get("stopBtn") and frozen and s["nudges"] < NUDGE_BUDGET:
                s["unstick_count"] += 1
                if s["chat"]:
                    log(f"{name}: STUCK-START (stopBtn + frozen {FROZEN_CYCLES} "
                        f"cycles) — force-unstick #{s['unstick_count']}")
                    r = click_stop(tab)
                    log(f"{name}: stop click: {r}")
                    time.sleep(8)
                else:
                    log(f"{name}: STUCK-START on fresh home-surface chat — "
                        f"nudge-only recovery #{s['unstick_count']} (stop would "
                        f"destroy the chat)")
                lines = run([os.path.join(BASE, "dispatch_worker.py"), "send",
                             name, "Begin the work order now (station setup "
                             "first). If already started, continue from "
                             "where you stopped."])
                s["nudges"] += 1
                v = lines[-1] if lines else "?"
                log(f"{name}: unstick nudge: {v[:90]}")
                continue
            # the no-response law
            if (st.get("noresp") and not st.get("stopBtn")
                    and s["nudges"] < NUDGE_BUDGET):
                s["nudges"] += 1
                lines = run([os.path.join(BASE, "dispatch_worker.py"), "send",
                             name, "Continue the work order from where you "
                             "stopped. (auto-nudge: generation dropped)"])
                v = lines[-1] if lines else "?"
                log(f"{name}: noresp nudge #{s['nudges']}: {v[:90]}")
            # the stall law (tree/worklog/body all frozen)
            if (not s["stall_flagged"] and s["tree"] > 0
                    and time.time() - s["last_growth"] > STALL_AFTER):
                s["stall_flagged"] = True
                log(f"{name}: STALL — no growth in {STALL_AFTER}s")
                outbox(f"STATION WATCH: lane {name} STALL "
                       f"(no growth {STALL_AFTER}s). TL: assess.")
        time.sleep(CYCLE)
    log("window expired — standing down")


if __name__ == "__main__":
    sys.exit(main() or 0)
