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


_CUR = None  # the single live CDP connection for this dispatch process


def reconnect(tab_id):
    """2026-09-22 leak fix: keep ONE live connection per dispatch process —
    the previous connection is closed before a new one is adopted (the old
    code abandoned one per call; ~20 accumulated per grinding attempt and
    wedged every other CDP client on the box).
    2026-09-23 BUDGET FIX (the 17h-outage wedge): a wedged renderer makes
    _reconnect's inner retry loop burn minutes; the OUTER retry budget is
    now 2 (was 5) so a wedged pin fails fast (< ~5 min) inside the
    sentinel's 560s child budget — the next round's tab hygiene then
    double-probes, catches the wedge and mints a fresh pin."""
    global _CUR
    for _ in range(2):
        c = None
        try:
            c = DW._reconnect(tab_id)
            ev(c, "1", timeout=15)
            old, _CUR = _CUR, c
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            return c
        except Exception:
            if c is not None:
                try:
                    c.close()
                except Exception:
                    pass
            time.sleep(2)
    raise RuntimeError("reconnect failed")


def settle(c, label, secs=8):
    time.sleep(secs)


def reset_tab(tab):
    """2026-09-24 siege patch: HARD-RELOAD the dispatch tab after a FAILED
    attempt. A tab that went through one failed send (form submit rejected /
    composer residue / error overlay) renders a degraded surface where the
    sidebar Agent nav item disappears — the next pinned reuse then fails 4x
    at 'agent nav click: not-found' (observed 18:29-19:41 on four attempts;
    verified fix: location.reload() restores the logged-in shell; a soft
    Page.navigate to the SAME url does NOT — the SPA soft-navigates)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            c.call("Page.enable", {}, timeout=10)
            c.eval("location.reload()", timeout=20)
        finally:
            c.close()
    except Exception:
        pass


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    name, prompt_file = sys.argv[1], sys.argv[2]
    prompt = open(prompt_file, encoding="utf-8").read()
    # 2026-09-24 false-positive fix (W098, twice): the server-verify matched
    # an OLD dead chat holding an IDENTICAL packet (same prompt file re-sent
    # after a void) — a failed send "verified" against 5-hour-old evidence.
    # The verify below now requires the chat's updated_at to be newer than
    # this dispatch attempt. 3-min floor covers list-write lag.
    dispatch_start = time.time() - 180

    # pick or open a chat.z.ai tab (reuse existing — fewer tabs, less load)
    # PATIENT_TAB env: pin the dispatch to a specific tab id prefix (keeps
    # other worker-chat tabs untouched — 2026-09-21 concurrent-wave usage).
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    pin = os.environ.get("PATIENT_TAB", "").strip()
    if pin:
        tabs = [t for t in tabs if (t.get("id") or "").upper().startswith(pin.upper())] or tabs
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
            reset_tab(tab)
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

    # 2026-09-25 hardening (w020b/w020c phantom creates): React-state desync —
    # the textarea can hold the inserted text while React's submit state stays
    # EMPTY (send button disabled). Clicking then creates an EMPTY chat shell
    # (reaped server-side) and the packet is lost. GATE: the send button must
    # be ENABLED before any send path fires; if disabled, refocus + full
    # re-insert (a controlled-component nudge would WIPE the text — never
    # nudge); abort cleanly rather than phantom-create.
    def _btn_state(conn):
        try:
            sb = ev(conn, DW.JS_SEND_BUTTON)
            return json.loads(sb) if sb else None
        except Exception:
            return None
    for gate in range(3):
        spt = _btn_state(c)
        if spt and not spt.get("disabled"):
            print(f"      send-gate {gate}: button enabled (React synced)")
            break
        print(f"      send-gate {gate}: button disabled/absent — refocus + full re-insert")
        try:
            ev(c, DW.JS_CLEAR_COMPOSER)
            time.sleep(0.3)
            foc = ev(c, DW.JS_FOCUS_COMPOSER)
            if foc != "ok":
                print(f"      focus: {foc}")
            time.sleep(0.4)
            for off in range(0, len(prompt), CH):
                c.call("Input.insertText", {"text": prompt[off:off + CH]}, timeout=90)
                time.sleep(0.6)
            time.sleep(1.5)
        except Exception as e:
            print(f"      re-insert error: {str(e)[:60]}")
            try:
                c.close()
            except Exception:
                pass
            c = reconnect(tab["id"])
    else:
        print("ERROR: send button never enabled (React state desync) — aborting BEFORE phantom create")
        return 1

    # 7. send — Escape-overlay-close + DOM send-button click PRIMARY
    # (2026-09-25 lesson: overlays eat Enter/coordinate clicks; the DOM
    # button.click() is the proven path), then form.requestSubmit,
    # synthetic Enter, and send-button coordinate click as fallbacks.
    print("[7/7] sending (esc-overlay + DOM btn-click primary) ...")

    def _cleared_len(conn):
        return ev(conn, r"""(() => {
          const i = document.querySelector('#chat-input');
          return i ? String((i.value||'').length) : 'gone';
        })()""")

    try:
        fp = json.loads(ev(c, DW.JS_COMPOSER) or '{"x":0,"y":0}')
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(0.5)
    except Exception:
        pass
    send_report = []
    # 2026-09-25 lesson (41e0bd1, ported from dispatch_worker.py): a leftover
    # model-menu overlay EATS Enter AND coordinate clicks (send silently
    # fails — URL stays home, composer stays filled). Escape-close any
    # overlay, then DOM-click the SEND BUTTON (button.sendMessageButton) —
    # React onClick fires regardless of overlay z-index. Proven path.
    for typ in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {"type": typ, "key": "Escape", "code": "Escape",
                                          "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
    send_report.append("esc-overlay")
    time.sleep(0.6)
    try:
        r = ev(c, DW.JS_CLICK_SEND_BUTTON)
        send_report.append(f"btn-dom:{r}")
    except Exception as e:
        send_report.append(f"btn-dom-err:{str(e)[:40]}")
    time.sleep(4)
    try:
        c.close()
    except Exception:
        pass
    c = reconnect(tab["id"])
    cleared = _cleared_len(c)
    if cleared not in ("0", "gone"):
        # fallback 0: DOM-level form.requestSubmit (the 09-21 proven path)
        try:
            r = ev(c, channel.SUBMIT_JS)
            send_report.append(f"submit-js:{r}")
        except Exception as e:
            send_report.append(f"submit-js-err:{str(e)[:40]}")
        time.sleep(5)
        try:
            c.close()
        except Exception:
            pass
        c = reconnect(tab["id"])
        cleared = _cleared_len(c)
    if cleared not in ("0", "gone"):
        # fallback 1: synthetic Enter (legacy build path)
        try:
            ev(c, DW.JS_FOCUS_COMPOSER)
            for typ in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                                  "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            send_report.append("enter-key")
            time.sleep(5)
            try:
                c.close()
            except Exception:
                pass
            c = reconnect(tab["id"])
            cleared = _cleared_len(c)
        except Exception as e:
            send_report.append(f"enter-err:{str(e)[:40]}")
    if cleared not in ("0", "gone"):
        # fallback 2: send-button coordinate click
        try:
            sb = ev(c, DW.JS_SEND_BUTTON)
            if sb:
                spt = json.loads(sb)
                if not spt.get("disabled"):
                    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": spt["x"], "y": spt["y"],
                                                        "button": "left", "clickCount": 1})
                    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": spt["x"], "y": spt["y"],
                                                        "button": "left", "clickCount": 1})
                    send_report.append("btn-click")
                    time.sleep(5)
                    try:
                        c.close()
                    except Exception:
                        pass
                    c = reconnect(tab["id"])
        except Exception as e:
            send_report.append(f"btn-err:{str(e)[:40]}")
    print("      send paths: " + "; ".join(send_report) + f" | composer={_cleared_len(c)}")
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
        # freshness gate (2026-09-24): a chat whose latest server-side write
        # predates this dispatch attempt can only hold an OLD packet — skip
        # it, else re-dispatches of the same prompt file verify against the
        # dead predecessor (observed twice on W098).
        try:
            if float(it.get("updated_at") or 0) < dispatch_start:
                continue
        except (TypeError, ValueError):
            pass
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
        reset_tab(tab)
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
