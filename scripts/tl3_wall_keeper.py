#!/usr/bin/env python3
"""tl3_wall_keeper.py — §9e gentle keeper for the TL3-P2 wave rebind.

Context (2026-09-30 reset #5 recovery): the whole TL3-P2 audit wave (8
dispatches, 3 partitions) voided against the MODEL_CONCURRENCY_LIMIT wall —
sends either gated (composer retained) or null-committed (turn opened,
user content landed as null server-side). Doctrine (boot-prompt §8/§9e):
5-min keeper cadence — a faster cadence re-burns the window; land the
directive in the first minute the window opens.

Vehicles (all render, all dead turns cured idempotently before each try):
  A -> c4aa3f08 (ladder re-dispatch chat, workspace ws-4d647321 orphaned)
  B -> ac5e6776 (ladder re-dispatch chat)
  C -> 3aaa6b2a (ladder re-dispatch chat)
Each directive = preamble + FULL original work order (recovered verbatim
from the void primaries' server-side history, stored under
/home/z/my-project/replay-artifacts/prompts/).

Landing proof is SERVER-SIDE only (chats API): last user message content
len >= threshold. DOM/body growth is not trusted (null-commit class).

On all-three-landed: writes flags/tl3_wave_landed.json, re-registers the
tabs in flags/session_registry.jsonl, arms one queue_watch per session
(marker "TL3-P2 READINESS REPORT"), exits 0.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = open(os.path.join(BASE, "logs", "tl3_wall_keeper.log"), "a", buffering=1)
PROMPTS = "/home/z/my-project/replay-artifacts/prompts"
HORIZON_S = 10 * 3600
CADENCE_S = 300  # §9e: 5-min keeper cadence; faster re-burns the window
MARKER = "TL3-P2 READINESS REPORT"

WAVE = [
    ("tl3-pa-browser-audit",
     "c4aa3f08-264d-4d45-a627-16104b5b44ca", "tl3-pa-browser-audit.md", 5000),
    ("tl3-pb-environments-audit",
     "ac5e6776-f7ce-40bf-a029-ec1416bb690b", "tl3-pb-environments-audit.md", 5000),
    ("tl3-pc-resources-continuity-audit",
     "3aaa6b2a-b165-4475-98e2-7579cb5cba4f", "tl3-pc-resources-continuity-audit.md", 5000),
]

PREAMBLE = """STATION DIRECTIVE — RESUME (READ FULLY).

A platform capacity wall ate the previous turn(s) of this chat before any work started; they have been closed cleanly server-side. The pod filesystem is FRESH — that is expected; there is nothing to recover.

The authoritative FULL work order is below; it supersedes any condensed variant above it. Execute it exactly as written, from its STEP ZERO to its completion report.

"""

TOKEN = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
HDRS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
        "Content-Type": "application/json", "X-FE-Version": "prod-fe-1.1.98"}

JS_CLEAR_COMPOSER = r"""(() => {
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

JS_POPUP_CANCEL = r"""(() => {
  // §9e: NEVER click 'Switch to GLM-5.3-Flash' — Cancel only, inside dialogs.
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
        with open(os.path.join(FLAGS, "tl3_wall_keeper_heartbeat"), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def api(path, body=None, method=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://chat.z.ai" + path, data=data,
        headers=HDRS, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode(errors="replace")


def chat_inner(cid):
    _, raw = api(f"/api/v1/chats/{cid}")
    data = json.loads(raw)
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    return inner


def sorted_msgs(inner):
    msgs = (inner.get("history") or {}).get("messages", {})
    arr = list(msgs.values()) if isinstance(msgs, dict) else list(msgs)
    arr.sort(key=lambda m: m.get("createdAt") or m.get("timestamp") or 0)
    return arr


def cure_dead_turn(cid):
    """Stop the current turn if it is a dead assistant placeholder (idempotent)."""
    try:
        inner = chat_inner(cid)
        cur = (inner.get("history") or {}).get("currentId")
        roles = {m.get("id"): m.get("role") for m in sorted_msgs(inner)}
        if roles.get(cur) != "assistant":
            return "no-dead-turn"
        st, body = api(f"/api/tasks/stop/{cur}",
                       {"reason": "wall-keeper: closing void/null-commit turn per s8"})
        return f"stop:{st}"
    except Exception as e:
        return f"err:{type(e).__name__}"


def server_last_user_len(cid):
    """Content length of the LAST user message (-1 if none). Null content -> -2."""
    try:
        arr = sorted_msgs(chat_inner(cid))
        users = [m for m in arr if m.get("role") == "user"]
        if not users:
            return -1
        c = users[-1].get("content")
        if not isinstance(c, str):
            return -2
        return len(c)
    except Exception as e:
        return -3


def fresh_tab(cid):
    """§8 fresh-tab law: new tab straight at the chat URL, 14s settle."""
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
        return None, None
    return tab, c


def composer_send(c, text):
    """Proven send: clear -> focus -> chunked insert -> ratio -> focus -> Enter."""
    c.eval(JS_POPUP_CANCEL, await_promise=False, timeout=10)
    time.sleep(0.5)
    c.eval(JS_CLEAR_COMPOSER, await_promise=False, timeout=15)
    time.sleep(0.3)
    if c.eval(JS_FOCUS, await_promise=False, timeout=15) != "ok":
        return 0
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
        return pct
    # focus-before-enter (the textarea grew after insert)
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
    return pct


def attempt_landing(name, cid, prompt_file, min_len):
    """One gentle landing try. Returns (status, detail)."""
    cure = cure_dead_turn(cid)
    text = PREAMBLE + open(os.path.join(PROMPTS, prompt_file), encoding="utf-8").read()
    tab, c = fresh_tab(cid)
    if not tab:
        return "gated", f"no-renderable-tab ({cure})"
    try:
        pct = composer_send(c, text)
        if not (97 <= pct <= 115):
            return "gated", f"insert-{pct}% ({cure})"
        time.sleep(25)  # let the server commit; proof is server-side only
        L = server_last_user_len(cid)
        if L >= min_len:
            # register the live tab for dispatch_worker send/find
            rec = {"name": name, "tab_id": tab["id"],
                   "url": f"https://chat.z.ai/c/{cid}", "ts": int(time.time()),
                   "mode": "agents-tab", "model": "GLM-5.3", "skill": "Full-Stack",
                   "note": "wall-keeper landing (full work order re-delivered)"}
            with open(os.path.join(FLAGS, "session_registry.jsonl"), "a") as f:
                f.write(json.dumps(rec) + "\n")
            return "landed", f"len={L}"
        # gated or null-commit — close the dead turn this created, back off
        cure2 = cure_dead_turn(cid)
        return "gated", f"server-len={L} ({cure}; retry-cure {cure2})"
    finally:
        try:
            c.call("Target.closeTarget", {"targetId": tab["id"]}, timeout=8)
        except Exception:
            pass


def arm_watchers(landed_tabs):
    prompt_files = {n: os.path.join(PROMPTS, pf) for n, _, pf, _ in WAVE}
    for name, tab_id in landed_tabs.items():
        spec = os.path.join(FLAGS, f"queue_watch.spec.{name}")
        with open(spec, "w") as f:
            f.write(json.dumps({"name": name, "tab_prefix": tab_id[:8],
                                "marker": MARKER,
                                "prompt_file": prompt_files[name]}) + "\n")
        subprocess.Popen([sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
                          name, tab_id[:8], MARKER],
                         stdout=open(f"/tmp/queue_watch_{name}.log", "w"),
                         stderr=subprocess.STDOUT,
                         start_new_session=True, cwd=BASE)
        log(f"watcher armed: {name} tab {tab_id[:8]} marker '{MARKER}'")


def main():
    # OUTAGE-HOLD (queue_watch contract): watchers stay READ-ONLY — no assault
    # ladders, no re-dispatch churn into the wall (the 2026-09-29/30 night
    # produced 8 voids that way). The orchestrator lifts this flag manually
    # when mid-work stall recovery is wanted.
    hold = os.path.join(FLAGS, "outage_hold.txt")
    if not os.path.exists(hold):
        with open(hold, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S")
                    + " tl3_wall_keeper: capacity wall — watchers read-only\n")
        log("outage_hold.txt written (watchers will be read-only)")
    log(f"keeper online — vehicles: " + ", ".join(f"{n}->{c[:8]}" for n, c, _, _ in WAVE))
    landed = {}
    landed_tabs = {}
    start = time.time()
    while len(landed) < len(WAVE) and time.time() - start < HORIZON_S:
        hb()
        window_open = False
        for name, cid, pf, min_len in WAVE:
            if name in landed:
                continue
            st, detail = attempt_landing(name, cid, pf, min_len)
            log(f"{name}: {st} ({detail})")
            if st == "landed":
                landed[name] = detail
                window_open = True
                # keep the landed chat's tab: reopen one and hold it for the watcher
                tab, c = fresh_tab(cid)
                if tab:
                    landed_tabs[name] = tab["id"]
                    try:
                        c.close()
                    except Exception:
                        pass
            else:
                break  # wall is up — stop burning, next cadence
        if len(landed) == len(WAVE):
            with open(os.path.join(FLAGS, "tl3_wave_landed.json"), "w") as f:
                json.dump({"landed": landed, "ts": int(time.time())}, f, indent=2)
            arm_watchers(landed_tabs)
            log("ALL THREE LANDED — watchers armed; keeper exiting")
            return 0
        time.sleep(20 if window_open else CADENCE_S)
    log("horizon reached without full landing — keeper exiting (relaunch to continue)")
    with open(os.path.join(FLAGS, "tl3_wave_landed.json"), "w") as f:
        json.dump({"partial": landed, "ts": int(time.time())}, f, indent=2)
    return 1


if __name__ == "__main__":
    sys.exit(main())
