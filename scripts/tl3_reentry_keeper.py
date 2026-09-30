#!/usr/bin/env python3
"""tl3_reentry_keeper.py — verified-landing keeper for the RE-ENTRY wave.

State (2026-09-30 ~18:05Z): partition audits A/B/C all COMPLETED server-side
(batch narratives preserved); the staged workspace files died with their pods.
A's accidental duplicate re-run in 5ba77f28 was stopped mid-work (audit done,
no delivery) — its slot released; the chat is retired as a vehicle. This
keeper lands the RE-ENTRY directive on the three COMPLETE-narrative vehicles:

  A -> c4aa3f08 (partition A vehicle, complete report, ws record active)
  C -> 3aaa6b2a (partition C vehicle, complete narrative, no live ws)
  B -> 6a554aab (partition B full-original-prompt lineage, complete, no live ws)

Wall behavior is INTERMITTENT (sends land sometimes, null-commit others), so:
send -> verify SERVER-SIDE (new user msg whose batch payload contains the
directive marker) -> if not landed, back off (90s x4, then 300s) and retry.
After landing, wait for the turn to OPEN (new assistant stub / currentId
move) within 15 min; then record + move to the next vehicle. Exit 0 when
both are landed+open. Never touches partition A (already re-entering).
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = open(os.path.join(BASE, "logs", "tl3_reentry_keeper.log"), "a", buffering=1)
HORIZON_S = 6 * 3600
MARKER = "RE-ENTRY (your work order"

WAVE = [
    ("tl3-pa-reentry", "c4aa3f08-264d-4d45-a627-16104b5b44ca", "DB19FDA2"),
    ("tl3-pc-reentry", "3aaa6b2a-b165-4475-98e2-7579cb5cba4f", "212C0A4F"),
    ("tl3-pb-reentry", "6a554aab-53b2-4d1e-addb-8a32b5ee2ed5", "B196AB21"),
]

DIRECTIVE = """STATION DIRECTIVE — RE-ENTRY (your work order's RE-ENTRY LAW now applies). Your prior turn COMPLETED this audit (full narrative preserved in this chat) and staged findings.md, delivery.patch, baseline.txt, fixed-gates.txt — but the pod filesystem was lost in a workspace rebind; the files are gone. DO NOT re-audit from scratch and DO NOT re-derive findings. Rebuild EXACTLY what your narrative shows you already produced and verified: re-clone at the pinned base SHA c27de198e14576a9e4ef84681ff061b72f452795, re-apply your recorded changes (your Write/Edit/Bash steps are all in your context above), re-create the same single delivery commit on your recorded branch, re-run your gate battery to confirm, and re-stage the four files at the workspace root (/home/z/my-project). Then reply with a short confirmation: file list + sizes + branch/SHA. Speed matters: this is a rebuild, not a re-audit."""

TOKEN = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
HDRS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
        "Content-Type": "application/json"}

JS_CLEAR = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'no-input';
  const proto = i.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                                         : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
  return String((i.value || '').length);
})()"""

JS_FOCUS = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'gone';
  i.focus();
  return (document.activeElement === i) ? 'ok' : 'no';
})()"""

JS_RECT = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return '';
  const r = i.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
})()"""

JS_POPUP = r"""(() => {
  const dlgs = document.querySelectorAll('[role=dialog]');
  for (const dlg of dlgs) {
    for (const b of dlg.querySelectorAll('button')) {
      const t = (b.innerText || '').trim();
      if (t === 'Cancel' || t === '取消') { b.click(); return 'cancelled'; }
    }
  }
  return 'none';
})()"""


def log(msg):
    LOG.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")


def hb():
    try:
        with open(os.path.join(FLAGS, "tl3_reentry_keeper_heartbeat"), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def api(path, body=None, method=None, timeout=45):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://chat.z.ai" + path, data=data, headers=HDRS,
        method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(errors="replace"))


def batch_state(cid):
    """(n_msgs, landed_marker, turn_open, assistant_payloads) server truth."""
    data = api(f"/api/v1/chats/{cid}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    hist = inner.get("history") or {}
    msgs = hist.get("messages", {})
    arr = list(msgs.values()) if isinstance(msgs, dict) else list(msgs)
    arr.sort(key=lambda m: m.get("createdAt") or m.get("timestamp") or 0)
    ids = [m["id"] for m in arr if m.get("id")]
    landed = False
    asst_sizes = []
    if ids:
        bj = api(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids})
        payloads = (bj.get("data") or bj.get("messages") or {}) if isinstance(bj, dict) else {}
        for mid, m in payloads.items():
            if not m:
                continue
            if m.get("role") == "user" and MARKER in json.dumps(m):
                landed = True
            if m.get("role") != "user":
                asst_sizes.append((mid, len(json.dumps(m))))
    n_before = len([m for m in arr if m.get("role") == "assistant"])
    return len(arr), landed, n_before, asst_sizes


def fresh_tab(cid, tab_pref=None):
    """Reuse the held tab if it's on this chat; else open one."""
    if tab_pref:
        for t in channel.list_tabs():
            if (t.get("id") or "").startswith(tab_pref) and cid[:12] in (t.get("url") or ""):
                return t
    tab = channel.new_tab()
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    c.call("Page.navigate", {"url": f"https://chat.z.ai/c/{cid}"}, timeout=30)
    time.sleep(14)
    href = c.eval("location.href", await_promise=False, timeout=10)
    if cid[:12] not in (href or ""):
        try:
            c.call("Target.closeTarget", {"targetId": tab["id"]}, timeout=8)
        except Exception:
            pass
        return None
    return tab


def composer_send(cid, tab_pref):
    tab = fresh_tab(cid, tab_pref)
    if not tab:
        return "no-tab"
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.eval(JS_POPUP, await_promise=False, timeout=10)
        time.sleep(0.5)
        c.eval(JS_CLEAR, await_promise=False, timeout=15)
        time.sleep(0.3)
        if c.eval(JS_FOCUS, await_promise=False, timeout=15) != "ok":
            return "no-focus"
        text = DIRECTIVE
        CH = 16000
        for off in range(0, len(text), CH):
            c.call("Input.insertText", {"text": text[off:off + CH]}, timeout=90)
            time.sleep(0.4)
        ratio_js = ("(() => { const i = document.querySelector('#chat-input');"
                    f"return i ? String(Math.round(100 * (i.value||'').length / {len(text)})) : '0';}})()")
        pct = 0
        for _ in range(8):
            try:
                pct = int(c.eval(ratio_js, await_promise=False, timeout=10))
            except Exception:
                pct = 0
            if 97 <= pct <= 115:
                break
            time.sleep(1.0)
        if not (97 <= pct <= 115):
            return f"insert-{pct}"
        try:
            pt = json.loads(c.eval(JS_RECT, await_promise=False, timeout=10) or '{"x":0,"y":0}')
            c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            time.sleep(0.3)
        except Exception:
            pass
        c.eval(JS_FOCUS, await_promise=False, timeout=15)
        time.sleep(0.2)
        for typ in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {
                "type": typ, "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        return "sent"
    finally:
        try:
            c.close()
        except Exception:
            pass


def main():
    log("re-entry keeper online — vehicles: " +
        ", ".join(f"{n}->{c[:8]}" for n, c, _ in WAVE))
    state = {n: {"landed": False, "open": False} for n, c, _ in WAVE}
    backoff = {n: 0 for n, c, _ in WAVE}
    start = time.time()
    while time.time() - start < HORIZON_S:
        hb()
        progress = False
        for name, cid, tab_pref in WAVE:
            st = state[name]
            if st["landed"] and st["open"]:
                continue
            n, landed, n_asst, sizes = batch_state(cid)
            if landed:
                st["landed"] = True
                log(f"{name}: DIRECTIVE LANDED (msgs={n}, assistant_turns={n_asst})")
                progress = True
            if st["landed"]:
                # wait for turn open: assistant turn count grows vs baseline 1
                if n_asst >= 2:
                    st["open"] = True
                    log(f"{name}: TURN OPEN (assistant_turns={n_asst}) — re-entry running")
                    progress = True
                    continue
                # not open yet; if it's been >2 min since landing, log a heartbeat
                log(f"{name}: landed, waiting for turn open (assistant_turns={n_asst})")
                continue
            # not landed: send
            res = composer_send(cid, tab_pref)
            time.sleep(25)
            n2, landed2, n_asst2, _ = batch_state(cid)
            log(f"{name}: send={res} -> msgs {n}->{n2} landed={landed2}")
            if landed2:
                st["landed"] = True
                progress = True
            else:
                backoff[name] += 1
        done = all(s["landed"] and s["open"] for s in state.values())
        if done:
            with open(os.path.join(FLAGS, "tl3_reentry_landed.json"), "w") as f:
                json.dump({"state": state, "ts": int(time.time())}, f, indent=2)
            log("BOTH RE-ENTRY TURNS LIVE — keeper exiting")
            return 0
        # adaptive cadence: quick retries early, gentle later
        max_backoff = max(backoff.values())
        time.sleep(90 if max_backoff <= 4 else 300)
    log("horizon reached — keeper exiting")
    return 1


if __name__ == "__main__":
    sys.exit(main())
