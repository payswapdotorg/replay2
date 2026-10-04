#!/usr/bin/env python3
"""window_watch.py — autonomous GLM-5.3 capacity-gate watcher + lane playbook executor.

§8 gentle-mode doctrine: single-send probes on a fixed cadence so the capacity
window opens onto ONE clean send. When a probe generates (not capacity-gated),
immediately execute the lane playbook.

2026-10-04 Task-73 doctrine: w143's packet is parked in a ROUTABLE chat
(f474b538 — it has an assistant stub) so it takes a BEGIN-DIRECTIVE into that
chat. w142's parked chat (e74a1f5f) is UNROUTABLE (user-only chats bounce on
cold boot AND on sidebar click — the SPA route guard requires >=1 assistant
message), so w142 takes a FRESH PACKET SEND through the agents-tab composer
(the open gate means the new chat gets its assistant turn and becomes
routable); the playbook then arms the completion oracle on the new lane.
Both packet files carry the real PAT (the platform redacts tokens only in
the API view — the model context receives them fine; proven by w140).
Then keep watching until both lanes' server-side batch stores grow.
Every action is logged to logs/window-watch.log.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "window-watch.log")
PROBE_EVERY = 300          # s between probes (gentle cadence)
MAX_MINUTES = 990          # watch through the overnight window into the 05:38-09:36Z quota reset
RENUDGE_COOLDOWN = 1800    # s between playbook re-firings (mid-generation death recovery)
W143_CHAT = "f474b538-2a8d-4a32-8456-df3b3cd5c092"
W143_BEGIN = "/home/z/my-project/replay-packets/w143-begin.md"
W142_PACKET = "/home/z/my-project/replay-packets/w142.md"
W142_MARKER = "W142 COMPLETION REPORT"


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S', time.gmtime())}Z] {msg}\n")


def _tab_on(frag):
    for t in channel.list_tabs():
        if frag in (t.get("url") or ""):
            return t
    return None


def _agents_composer():
    """A tab on chat.z.ai HOME (exact home — never a /c/ chat tab; the Task-73
    lesson: a fuzzy 'chat.z.ai/' match sent probes INTO the w143 lane chat)
    in AGENT mode with GLM-5.3 selected; returns (tab, ws) or (None, None)."""
    tab = None
    for t in channel.list_tabs():
        u = (t.get("url") or "").rstrip("/")
        if u in ("https://chat.z.ai", "http://chat.z.ai"):
            tab = t
            break
    if tab is None:
        tab = channel.new_tab("https://chat.z.ai/")
        time.sleep(8)
    ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=40)
    try:
        mode = ws.eval("(() => document.body.innerText.includes('New Task') ? 'agent' : 'chat')()", timeout=12)
        if mode != "agent":
            ws.eval("""(() => {
              const els = Array.from(document.querySelectorAll('a, button'));
              const agent = els.find(e => /^Agent$/i.test((e.innerText || '').trim()));
              if (agent) agent.click();
              return 'nav';
            })()""", timeout=12)
            time.sleep(5)
        # model: click selector, pick GLM-5.3 exact
        ws.eval("""(() => {
          const btns = Array.from(document.querySelectorAll('button'));
          const ms = btns.find(b => /GLM-5\\.[0-9]/i.test((b.innerText || '') + (b.getAttribute('aria-label') || '')) && (b.innerText || '').length < 40);
          if (ms) ms.click();
        })()""", timeout=12)
        time.sleep(1.5)
        ws.eval("""(() => {
          const opts = Array.from(document.querySelectorAll('[role=option], [role=menuitem], button, div, li'));
          const m = opts.find(o => /^GLM-5\\.3(?!-)/.test((o.innerText || '').trim()));
          if (m) m.click();
        })()""", timeout=12)
        time.sleep(1.5)
        return tab, ws
    except Exception as e:
        try:
            ws.close()
        except Exception:
            pass
        log(f"composer setup fail: {e!r}")
        return None, None


def probe_gate():
    """One gentle GLM-5.3 probe. Returns True if generation flowed."""
    tab, ws = _agents_composer()
    if ws is None:
        return False
    try:
        ws.eval("(() => { const i = document.querySelector('#chat-input, textarea'); if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=12)
        ws.call("Input.insertText", {"text": "Connectivity probe: reply with just OK"}, timeout=15)
        time.sleep(1.5)
        ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, timeout=15)
        ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, timeout=15)
        for i in range(14):
            time.sleep(5)
            try:
                t = ws.eval("(() => document.body.innerText.slice(-240))()", timeout=10)
                if "intensifying the coordination" in t or "try again later" in t:
                    return False
                busy = ws.eval("(() => { const btns = Array.from(document.querySelectorAll('button')).map(b => (b.innerText||'').trim()); return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? '1' : '0'; })()", timeout=10)
                if busy == "1":
                    return True
                if t.rstrip().endswith("OK"):
                    return True
            except Exception:
                pass
        return False
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _single_send(ws, text):
    """Gentle single send (no assault ladder). Returns True if composer cleared."""
    try:
        ws.eval("(() => { const i = document.querySelector('#chat-input, textarea'); if (!i) return 'gone'; i.focus(); return document.activeElement === i ? 'ok' : 'no'; })()", timeout=12)
        ws.call("Input.insertText", {"text": text}, timeout=30)
        time.sleep(2)
        ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, timeout=15)
        ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, timeout=15)
        time.sleep(5)
        cl = ws.eval("(document.querySelector('#chat-input, textarea')||{value:'x'}).value.length", timeout=12)
        return cl == 0
    except Exception as e:
        log(f"single_send fail: {e!r}")
        return False


def playbook():
    """The window is open: fire both lanes."""
    import dispatch_worker as dw
    import subprocess
    # 1. w143 begin-directive into the routable parked chat
    try:
        tab143 = _tab_on(W143_CHAT[:8])
        if tab143 is None:
            tab143 = channel.new_tab(f"https://chat.z.ai/c/{W143_CHAT}")
            time.sleep(10)
            dw._save({"action": "tab-reopen", "name": "w143", "tab_id": tab143["id"],
                      "url": f"https://chat.z.ai/c/{W143_CHAT}", "ts": int(time.time()),
                      "note": "window_watch playbook: tab on parked chat"})
        ws = channel.CDP(tab143["webSocketDebuggerUrl"], timeout=40)
        try:
            begin = open(W143_BEGIN).read()
            ok = _single_send(ws, begin)
            log(f"PLAYBOOK w143 begin-directive sent: {ok} (chat {W143_CHAT[:8]})")
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as e:
        log(f"PLAYBOOK w143 fail: {e!r}")
    # 2. w142 fresh packet on the general path (parked chat e74a1f5f is unroutable)
    try:
        tab, ws2 = _agents_composer()
        if ws2 is not None:
            try:
                packet = open(W142_PACKET).read()
                ok = _single_send(ws2, packet)
                u = ws2.eval("location.href", timeout=12)
                log(f"PLAYBOOK w142 packet sent: {ok} url={u[:60]}")
                if ok and "/c/" in u:
                    dw._save({"name": "w142", "tab_id": tab["id"], "url": u, "ts": int(time.time()),
                              "prompt_file": W142_PACKET, "prompt_chars": len(packet),
                              "mode": "agents-tab", "model": "GLM-5.3", "skill": "(none — general_agent path)",
                              "insert_pct": 100, "sent": True,
                              "note": "window_watch playbook fresh dispatch (general_agent path; parked chat e74a1f5f unroutable — superseded)"})
                    log(f"PLAYBOOK w142 registered: {u}")
                    # arm the completion oracle on the new lane
                    try:
                        rc = subprocess.run([sys.executable,
                                             os.path.join(BASE, "launch_queue_watch.py"),
                                             "w142", tab["id"][:8], W142_MARKER],
                                            capture_output=True, text=True, timeout=120)
                        log((rc.stdout or rc.stderr or "").strip()[:120])
                    except Exception as e:
                        log(f"oracle arm fail: {e!r}")
            finally:
                ws2.close()
    except Exception as e:
        log(f"PLAYBOOK w142 fail: {e!r}")


def main():
    log("window_watch online (gentle GLM-5.3 gate probes every 300s; playbook: w143 begin-directive into f474b538 + w142 fresh packet send with oracle auto-arm; horizon 16.5h)")
    t0 = time.time()
    last_fired = 0
    while time.time() - t0 < MAX_MINUTES * 60:
        try:
            open_gate = probe_gate()
            now = time.time()
            if open_gate and (now - last_fired) > RENUDGE_COOLDOWN:
                if last_fired == 0:
                    log("*** CAPACITY WINDOW OPEN — executing lane playbook ***")
                else:
                    log("*** window open again (re-nudge; cooldown elapsed) — re-firing playbook ***")
                playbook()
                last_fired = now
                log("playbook executed; batch growth tracked by lane_monitor; next re-nudge allowed in 30min")
            elif open_gate:
                log("window open (playbook cooling down)")
            else:
                log("gate closed (capacity message)")
        except Exception as e:
            log(f"cycle error: {e!r}")
        time.sleep(PROBE_EVERY)
    log("window_watch retiring after max watch time")


if __name__ == "__main__":
    main()
