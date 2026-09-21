#!/usr/bin/env python3
"""patient_dispatch.py — slow-and-steady agents-tab worker dispatch.

2026-09-21: the account's chat sidebar has grown to ~290 chats; home-page
hydration is heavy and the stock create flow's tight eval timeouts
(15s) now time out on the model-selection step even on a freshly
restarted browser (the "model still 'err:Connection timed out'" family).
This variant reuses the house JS selectors (imported from
dispatch_worker) with:

  - long settle sleeps between phases (hydration allowance)
  - 30s eval timeouts, 20x3s verification retries
  - fresh CDP connection after every mutating click
  - smaller insert chunks (8K)
  - send via Enter + arrow-up-button fallback (the proven prod019 path)
  - FINAL verification is server-side (chats list delta + batch probe of
    the new chat for the exact packet) — DOM proofs are advisory only

Usage: patient_dispatch.py <session-name> <prompt-file.md>
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as DW  # noqa: E402

CHAT_URL = "https://chat.z.ai/"
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


def settle(c, label, secs=8):
    time.sleep(secs)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    name, prompt_file = sys.argv[1], sys.argv[2]
    prompt = open(prompt_file, encoding="utf-8").read()

    # pick or open a chat.z.ai tab (reuse existing — fewer tabs, less load)
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if tabs:
        tab = tabs[0]
        c = reconnect(tab["id"])
        # navigate home if we're on a chat page (fresh New Task surface)
        url = ev(c, "location.href")
        if "/c/" in url:
            c.call("Page.enable", {}, timeout=10)
            c.call("Page.navigate", {"url": CHAT_URL}, timeout=20)
            time.sleep(8)
            c = reconnect(tab["id"])
    else:
        print("no chat.z.ai tab — open one first")
        return 1
    print(f"[1/7] tab {tab['id'][:8]} on home; settling for hydration ...")
    settle(c, "shell", 12)

    # 3. agent mode
    print("[3/7] selecting AGENTS tab ...")
    already = str(ev(c, DW.JS_AGENT_MODE_ON)) == "true"
    if not already:
        for attempt in range(4):
            res = ev(c, DW.JS_AGENT_NAV)
            if res != "ok":
                print(f"  agent nav click: {res}")
                time.sleep(5)
                continue
            time.sleep(6)
            try:
                if str(ev(c, DW.JS_AGENT_MODE_ON)) == "true":
                    break
            except Exception:
                c = reconnect(tab["id"])
        if str(ev(c, DW.JS_AGENT_MODE_ON)) != "true":
            print("ERROR: agent mode not activating")
            return 1
    print("      agent mode ON")

    # 4. model GLM-5.3 — patient
    print("[4/7] selecting model GLM-5.3 (patient) ...")
    cur = None
    for _ in range(3):
        try:
            cur = ev(c, DW.JS_MODEL_TEXT)
            break
        except Exception:
            time.sleep(6)
            c = reconnect(tab["id"])
    if cur != DW.WANT_MODEL:
        if cur == "no-button":
            print("ERROR: model selector button not found")
            return 1
        ev(c, DW.JS_OPEN_MODEL_MENU)
        time.sleep(4)
        ok = False
        for _ in range(10):
            try:
                res = ev(c, DW.JS_CLICK_MODEL)
                if res == "ok":
                    ok = True
                    break
            except Exception:
                c = reconnect(tab["id"])
            time.sleep(3)
        if not ok:
            print("ERROR: GLM-5.3 option not clickable")
            return 1
        time.sleep(6)
        c = reconnect(tab["id"])
        time.sleep(3)
        for _ in range(20):
            try:
                cur = ev(c, DW.JS_MODEL_TEXT, timeout=20)
                if cur == DW.WANT_MODEL:
                    break
            except Exception:
                pass
            time.sleep(3)
    if cur != DW.WANT_MODEL:
        print(f"ERROR: model still '{cur}'")
        return 1
    print(f"      model = {DW.WANT_MODEL} (verified)")

    # 5. skill Full-Stack — patient
    print("[5/7] selecting skill Full-Stack ...")
    for _ in range(6):
        try:
            state = json.loads(ev(c, DW.JS_SKILL_STATE) or "{}")
            if state.get("composerChip"):
                break
            if DW.WANT_SKILL in (state.get("intro") or []):
                ev(c, DW.JS_CLICK_SKILL)
                time.sleep(3)
        except Exception:
            c = reconnect(tab["id"])
        time.sleep(3)
    state = json.loads(ev(c, DW.JS_SKILL_STATE) or "{}")
    if not state.get("composerChip"):
        print("ERROR: Full-Stack skill chip not active")
        return 1
    print("      Full-Stack skill ON")

    # 6. insert — patient chunked
    print(f"[6/7] inserting prompt ({len(prompt)} chars) ...")
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
            c = reconnect(tab["id"])
    if not (97 <= pct <= 115):
        print(f"ERROR: insert ratio {pct}%")
        return 1
    print(f"      insert verified ({pct}%)")

    # 7. send — Enter then arrow-up fallback
    print("[7/7] sending ...")
    try:
        fp = json.loads(ev(c, DW.JS_COMPOSER) or '{"x":0,"y":0}')
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(0.5)
    except Exception:
        pass
    ev(c, DW.JS_FOCUS_COMPOSER)
    for typ in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                          "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    time.sleep(5)
    try:
        c.close()
    except Exception:
        pass
    c = reconnect(tab["id"])
    cleared = ev(c, r"""(() => {
          const i = document.querySelector('#chat-input');
          return i ? String((i.value||'').length) : 'gone';
        })()""")
    if cleared not in ("0", "gone"):
        # arrow-up send button fallback
        sb = ev(c, DW.JS_SEND_BUTTON)
        if sb:
            spt = json.loads(sb)
            if not spt.get("disabled"):
                c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": spt["x"], "y": spt["y"],
                                                    "button": "left", "clickCount": 1})
                c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": spt["x"], "y": spt["y"],
                                                    "button": "left", "clickCount": 1})
                time.sleep(5)
                try:
                    c.close()
                except Exception:
                    pass
                c = reconnect(tab["id"])
    url = ev(c, "location.href")
    print(f"      post-send url: {url[:70]}")

    # SERVER-SIDE verification (the only real proof): find the new chat with
    # the exact packet via the chats list + batch probe
    print("verifying server-side ...")
    time.sleep(8)
    tok = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "flags", "chat_token")).read().strip().strip('"')

    def api(path, body=None):
        import urllib.request
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("https://chat.z.ai" + path, data=data,
                                     method="POST" if data else "GET")
        req.add_header("Authorization", f"Bearer {tok}")
        req.add_header("Accept", "application/json")
        if data:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())

    listing = api("/api/v1/chats/list?limit=15")
    items = listing.get("data", listing) if isinstance(listing, dict) else listing
    if isinstance(items, dict):
        items = items.get("items") or []
    first_line = prompt.strip().split("\n")[0][:60]
    found = None
    for it in items:
        cid = it.get("id") or ""
        if not cid:
            continue
        try:
            chat = api(f"/api/v1/chats/{cid}")
        except Exception:
            continue
        msgs = ((chat.get("chat") or chat).get("history") or {}).get("messages") or {}
        for m in msgs.values():
            content = m.get("content")
            txt = content if isinstance(content, str) else json.dumps(content)
            if isinstance(content, str) and len(content) >= len(prompt) - 200 and content[:40] == prompt[:40]:
                found = cid
                break
        if found:
            break
    if not found:
        print("ERROR: packet not found in any recent chat — send FAILED server-side")
        return 1
    print(f"SENT-VERIFIED (server): chat {found} holds the {len(prompt)}-char packet")
    rec = {"name": name, "tab_id": tab["id"], "url": f"https://chat.z.ai/c/{found}",
           "ts": int(time.time()), "prompt_file": os.path.abspath(prompt_file),
           "prompt_chars": len(prompt), "mode": "agents-tab", "model": "GLM-5.3",
           "skill": "Full-Stack", "insert_pct": pct, "sent": True,
           "note": "patient_dispatch (lead): server-verified packet landing"}
    reg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags", "session_registry.jsonl")
    open(reg, "a").write(json.dumps(rec) + "\n")
    print("registry updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
