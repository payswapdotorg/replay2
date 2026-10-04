#!/usr/bin/env python3
"""stop_continue.py — AGENT_BOOT_PROMPT §8 cure, automated.

A quota-killed or otherwise-wedged turn (server-alive record, dead
generation: batch store static for hours, no report) is curable IN PLACE:

  1. resolve the session's chat id from the registry
  2. POST /api/tasks/stop/<history.currentId>  -> {"status": true}
     (closes the stuck assistant turn server-side)
  3. POST /api/chat/continue {"message_id"} + X-FE-Version
     -> HTTP 410 "already completed; resume not needed" = closure verified
  4. close OLD tabs on that chat (their client state stays wedged), open a
     FRESH tab at the chat URL, wait ~14s for the shell
  5. registry tab-reopen record so _find/_tab_for resolve the new tab
  6. dw.send() the continuation directive (React-set + Enter + verify,
     with the in-session capacity assault ladder)
  7. verify server-side that a NEW assistant turn opened (msgs grew)

PROVEN lineage: PPR-022 (2026-09-30) — 11.7h wedge, stop accepted, fresh
tab send landed within 2 min, worker resumed with zero narrative loss.
Void/re-dispatch stays the LAST resort (only if this cure fails).

Usage: stop_continue.py <name> ["reason"]
Exit: 0 = turn reopened in-place; 2 = no session; 3 = stop/verify failed;
      4 = fresh-tab open failed; 5 = continuation send failed;
      6 = new turn not observed server-side.
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

DIRECTIVE = (
    "[SYSTEM — resident watcher] Your previous turn was interrupted by a "
    "platform capacity event: the stream died mid-work and the dead turn has "
    "now been closed cleanly via the platform's stop API. Your conversation "
    "context, pod, and files are intact — nothing was lost. Continue the work "
    "order from exactly where you left off: cheaply re-verify any in-flight "
    "step, do NOT redo completed work, then proceed through the remaining "
    "implementation, run the gates, push, and post the completion report "
    "exactly per the work order protocol."
)


_PREF = {"tab_id": ""}   # session's OWN chat tab (set by main from the registry)


def _api_eval(js, timeout=45):
    """Run a fetch-based API call from a chat.z.ai tab; returns parsed JSON.

    2026-10-01 fix (re-land of the YOU-5f local fix, lost to a sandbox reset
    because it was never committed): channel.CDP.eval runs with
    returnByValue=True, so object-typed JS results arrive as ALREADY-PARSED
    dicts — json.loads on them raises TypeError and killed the cure mid-run.
    Accept both shapes (dict/list pass through; JSON strings still parse).

    2026-10-04 hardening (round 2): find_tab's first pick can be a fresh
    assault chat mid-load or a wedged renderer — the eval then died on ONE
    bad tab and took the whole cure down with it. Now: prefer the session's
    OWN chat tab (_PREF), liveness-ping each candidate (6s — a wedged tab
    fails HERE, not inside the heavy eval), and WALK candidates instead of
    dying on the first."""
    tabs = [t for t in channel.list_tabs()
            if "chat.z.ai" in (t.get("url") or "")]
    pref = _PREF.get("tab_id") or ""
    if pref:
        tabs.sort(key=lambda t: 0 if t.get("id") == pref else 1)
    last = "no chat.z.ai tab"
    for tab in tabs:
        try:
            ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=10)
        except Exception as e:
            last = f"connect {tab.get('id', '')[:8]}: {e!r}"
            continue
        try:
            ws.eval("1", timeout=6)   # liveness ping before the heavy eval
            v = ws.eval(js, await_promise=True, timeout=timeout)
            if isinstance(v, (dict, list)):
                return v
            if isinstance(v, str) and v[:1] in ("{", "["):
                return json.loads(v)
            return v
        except Exception as e:
            last = f"eval {tab.get('id', '')[:8]}: {e!r}"
        finally:
            ws.close()
    raise RuntimeError(f"no live chat.z.ai tab for API eval ({last})")


def _stop_turn(cid, reason):
    """§8 steps 2+3: stop the stuck turn and verify closure. Returns mid."""
    get_js = """(async () => {
      const t = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
      const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store',
        headers: {'Authorization': 'Bearer ' + t}});
      if (!r.ok) return {err: 'http-' + r.status};
      const j = await r.json();
      return {currentId: ((j.chat || {}).history || {}).currentId,
              updated: j.updated_at, title: j.title};
    })()""" % cid
    d = _api_eval(get_js)
    if d.get("err") or not d.get("currentId"):
        print(f"  [stop] cannot resolve currentId: {json.dumps(d)[:160]}")
        return None
    mid = d["currentId"]
    print(f"  [stop] stuck turn message id: {mid} (chat updated {d.get('updated')})")

    stop_js = """(async () => {
      const t = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
      const sr = await fetch('/api/tasks/stop/%s', {method:'POST', credentials:'include',
        headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json'},
        body: JSON.stringify({reason: %s})});
      const sb = await sr.text();
      const cr = await fetch('/api/chat/continue', {method:'POST', credentials:'include',
        headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json',
                  'X-FE-Version': 'prod-fe-1.1.98'},
        body: JSON.stringify({message_id: '%s'})});
      const cb = await cr.text();
      return {stop_http: sr.status, stop_body: sb.slice(0, 120),
              cont_http: cr.status, cont_body: cb.slice(0, 160)};
    })()""" % (mid, json.dumps(reason or "wedged turn — s8 in-place cure"), mid)

    for attempt in (1, 2, 3):
        r = _api_eval(stop_js, timeout=60)
        ok_stop = r.get("stop_http") == 200 and '"status":true' in (r.get("stop_body") or "")
        closed = r.get("cont_http") == 410
        print(f"  [stop] attempt {attempt}: stop_http={r.get('stop_http')} "
              f"cont_http={r.get('cont_http')} — {'CLOSED' if closed else 'slot still held'}")
        if ok_stop and closed:
            return mid
        if not closed:
            # 200-with-busy SSE = the slot is still held — wait 2-3 min, re-stop
            time.sleep(150)
    print("  [stop] closure NOT verified after retries")
    return None


def _close_old_tabs(cid):
    """Close every tab sitting on this chat (their client state is wedged)."""
    frag = cid[:8]
    closed = 0
    for t in channel.list_tabs():
        if "chat.z.ai" in (t.get("url") or "") and f"/c/{frag}" in (t.get("url") or ""):
            try:
                channel._http_json("/json/close/" + t["id"], method="PUT")
                closed += 1
            except Exception:
                pass
    if closed:
        print(f"  [tab] closed {closed} wedged tab(s) on /c/{frag}")
    return closed


def _fresh_tab(cid):
    """Open a fresh tab on the chat URL and let the shell settle (§8: ~14s)."""
    url = f"https://chat.z.ai/c/{cid}"
    tab = channel.new_tab(url)
    if tab is None:
        print("  [tab] fresh-tab open FAILED")
        return None
    print(f"  [tab] fresh tab {tab['id'][:8]} on /c/{cid[:8]} — settling 14s")
    time.sleep(14)
    return tab


def _turn_count(cid):
    """(assistant_blocks, msgs, last_ts) from the server-side message tree."""
    js = """(async () => {
      const t = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
      const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store',
        headers: {'Authorization': 'Bearer ' + t}});
      if (!r.ok) return {err: 'http-' + r.status};
      const j = await r.json();
      const h = (j.chat || {}).history || {};
      const msgs = Object.values(h.messages || {});
      let lastTs = 0, blocks = 0;
      for (const m of msgs) { lastTs = Math.max(lastTs, m.timestamp || 0); }
      return {msgs: msgs.length, lastTs, currentId: h.currentId};
    })()""" % cid
    d = _api_eval(js)
    return d


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    reason = sys.argv[2] if len(sys.argv) > 2 else "wedged turn — s8 in-place cure"

    rec = dw._find(name)
    if not rec:
        print(f"no live session named {name} in the registry")
        return 2
    cid = ((rec.get("url") or "").split("/c/")[-1].split("/")[0].split("?")[0])
    if len(cid) < 30:
        print(f"registry record for {name} has no /c/ chat id: {rec.get('url')}")
        return 2
    print(f"s8 cure for {name}: chat /c/{cid[:8]} (tab { (rec.get('tab_id') or '')[:8] })")
    _PREF["tab_id"] = rec.get("tab_id") or ""   # _api_eval prefers the session's OWN tab

    before = _turn_count(cid)
    print(f"  [probe] before: {json.dumps(before)}")

    mid = _stop_turn(cid, reason)
    if mid is None:
        return 3

    _close_old_tabs(cid)
    tab = _fresh_tab(cid)
    if tab is None:
        return 4

    dw._save({"action": "tab-reopen", "name": name, "tab_id": tab["id"],
              "url": f"https://chat.z.ai/c/{cid}", "ts": int(time.time()),
              "note": "s8 stop/continue cure: fresh tab after turn closure"})
    _PREF["tab_id"] = tab["id"]   # the fresh tab is the session's own tab now

    print("  [send] continuation directive via dispatch_worker.send ...")
    rc = dw.send(name, DIRECTIVE)
    if rc != 0:
        print(f"  [send] FAILED rc={rc}")
        return 5
    print("  [send] continuation landed")

    # verify a NEW turn opened server-side (msgs grew / currentId advanced)
    for attempt in range(6):
        time.sleep(20)
        after = _turn_count(cid)
        grew = (after.get("msgs") or 0) > (before.get("msgs") or 0) or \
               (after.get("lastTs") or 0) > (before.get("lastTs") or 0)
        print(f"  [verify] attempt {attempt + 1}: {json.dumps(after)} — "
              f"{'NEW TURN OPEN' if grew else 'no new turn yet'}")
        if grew:
            print(f"s8 CURE COMPLETE for {name} — turn reopened in-place "
                  f"(narrative preserved); new tab {tab['id'][:8]}")
            return 0
    print("  [verify] no new assistant turn observed — cure inconclusive")
    return 6


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"stop_continue fatal: {type(e).__name__}: {str(e)[:160]}")
        sys.exit(7)
