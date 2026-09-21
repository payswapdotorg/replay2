#!/usr/bin/env python3
"""followup_dispatch.py — packet delivery into an existing LIVE session.

2026-09-21 context: post-stall recovery, the platform rejects NEW agent
sessions created with large packets (12.8K chars -> client shell only,
server never materializes the chat; differential: 46-char openers
SENT-VERIFIED fine, full agent loop replied). The working pattern:

  1. patient_dispatch a SHORT opener  -> session materializes server-side
  2. followup_dispatch the FULL packet into that live session

This tool implements step 2 with the proven patient_dispatch mechanics
(chunked insert + ratio verify + form.requestSubmit SUBMIT_JS primary),
adapting them for the /c/<id> session composer:

  - refuses if the session is mid-generation (Stop button present)
  - refuses if the tab is not on the target chat URL
  - server-side verification: batch probe the chat for the packet tail
    (the last 80 chars of the packet, whitespace-normalized) in the
    message store — DOM proofs are advisory only (Task-90 doctrine)

Usage: followup_dispatch.py <chat-id> <prompt-file.md> [--tab TABPREFIX]
Prints verdict JSON. Exit 0 = packet verified in the chat's batch store.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as DW  # noqa: E402
from batch_probe import call  # noqa: E402

EVAL_T = 30


def ev(c, js, timeout=EVAL_T):
    return DW._eval(c, js, timeout=timeout)


def reconnect(tab_id):
    for _ in range(5):
        try:
            c = DW._reconnect(tab_id)
            ev(c, "1", timeout=15)
            return c
        except Exception:
            time.sleep(4)
    raise RuntimeError("reconnect failed")


def batch_text(cid):
    """All message texts in the chat's batch store, concatenated."""
    chat = call(f"/api/v1/chats/{cid}")
    inner = chat.get("chat") or chat
    msgs = (inner.get("history") or {}).get("messages") or {}
    if isinstance(msgs, list):
        msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
    ids = [m.get("id") for m in
           sorted(msgs.values(), key=lambda m: m.get("timestamp") or 0)
           if m.get("id")]
    if not ids:
        return ""
    batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}) or {}
    out = []
    node = batch.get("data") or batch
    items = node.get("messages") if isinstance(node, dict) else None
    if isinstance(items, list):
        for m in items:
            content = m.get("content")
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict):
                        out.append(str(blk.get("text") or blk.get("content") or ""))
                    else:
                        out.append(str(blk))
            else:
                out.append(str(content or ""))
    return "\n".join(out)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    cid, prompt_file = argv[0], argv[1]
    pin = ""
    if "--tab" in argv:
        pin = argv[argv.index("--tab") + 1]
    prompt = open(prompt_file, encoding="utf-8").read()

    # 1. find the tab on this chat
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if pin:
        tabs = [t for t in tabs if (t.get("id") or "").upper().startswith(pin.upper())] or tabs
    target = None
    for t in tabs:
        if cid[:8] in (t.get("url") or ""):
            target = t
            break
    if target is None:
        print(json.dumps({"err": f"no tab on chat {cid[:8]}"}))
        return 2
    print(f"[1/5] tab {target['id'][:8]} on {cid[:8]}")

    c = reconnect(target["id"])

    # 2. refuse if mid-generation
    busy = ev(c, r"""(() => {
      const btns = Array.from(document.querySelectorAll('button'))
        .map(b => (b.innerText||'').trim());
      return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 'busy' : 'idle';
    })()""")
    if busy == "busy":
        print(json.dumps({"err": "session is generating; not interrupting"}))
        return 2
    print("[2/5] session idle")

    # 3. insert — patient chunked (patient_dispatch mechanics)
    print(f"[3/5] inserting packet ({len(prompt)} chars) ...")
    pct = 0
    for attempt in range(3):
        try:
            comp = ev(c, DW.JS_COMPOSER)
            pt = json.loads(comp)
            c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            time.sleep(1.0)
            ev(c, DW.JS_CLEAR_COMPOSER)
            time.sleep(0.5)
            foc = ev(c, DW.JS_FOCUS_COMPOSER)
            if foc != "ok":
                print(f"  focus: {foc} — retrying")
                continue
            CH = 8000
            for off in range(0, len(prompt), CH):
                c.call("Input.insertText", {"text": prompt[off:off + CH]}, timeout=90)
                time.sleep(0.6)
            time.sleep(2)
            ratio_js = f"""(() => {{
              const i = document.querySelector('#chat-input, textarea');
              return i ? String(Math.round(100 * (i.value || '').length / {len(prompt)})) : 'x';
            }})()"""
            r = ev(c, ratio_js)
            pct = int(r) if str(r).isdigit() else 0
            if 97 <= pct <= 115:
                break
            print(f"  insert attempt {attempt+1}: {pct}% — retrying")
        except Exception as e:
            print(f"  insert error: {str(e)[:60]}")
            c = reconnect(target["id"])
    if not (97 <= pct <= 115):
        print(json.dumps({"err": f"insert ratio {pct}%"}))
        return 2
    print(f"      insert verified ({pct}%)")

    # 4. send — SUBMIT_JS primary
    print("[4/5] sending (form.requestSubmit) ...")
    try:
        r = ev(c, channel.SUBMIT_JS)
        print(f"      submit-js: {r}")
    except Exception as e:
        print(json.dumps({"err": f"submit failed: {e!r}"}))
        return 2
    time.sleep(6)
    try:
        c.close()
    except Exception:
        pass

    # 5. server-side verification: packet tail in the batch store
    print("[5/5] verifying server-side (batch store) ...")
    tail = norm(prompt)[-80:]
    ok = False
    for i in range(8):
        time.sleep(10)
        try:
            blob = norm(batch_text(cid))
            if tail in blob:
                ok = True
                break
            print(f"  poll {i+1}: tail not in batch store yet "
                  f"(blob {len(blob)} chars)")
        except Exception as e:
            print(f"  poll {i+1} err: {str(e)[:60]}")
    out = {"chat_id": cid, "packet_chars": len(prompt), "verified": ok}
    print(json.dumps(out))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
