#!/usr/bin/env python3
"""login_probe_diag.py — verbose replication of wave3_login_sentinel.login_healthy()
to find the exact failing step. Read-only; creates one tab, closes it."""
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

def main():
    print("step1: new_tab https://chat.z.ai/")
    tab = channel.new_tab("https://chat.z.ai/")
    print(f"  tab -> {tab}")
    if tab is None:
        print("FAIL: new_tab returned None")
        return
    time.sleep(6)
    try:
        c = CDP(tab["webSocketDebuggerUrl"], timeout=20)
    except Exception as e:
        print(f"FAIL: CDP connect: {e!r}")
        _close(tab)
        return
    try:
        tok = c.eval("(localStorage.getItem('token') || '').length", timeout=8)
        print(f"step2: token length = {tok!r}")
        r = c.eval("""(() => {
          const els = Array.from(document.querySelectorAll('a, button, [role=tab], div'))
            .filter(e => (e.innerText || '').trim() === 'Agent');
          if (!els.length) return 'no-el';
          els[els.length-1].click();
          return 'clicked';
        })()""", timeout=12)
        print(f"step3: agent-click result = {r!r}")
        time.sleep(6)
        body = c.eval("document.body.innerText || ''", timeout=15) or ""
        print(f"step4: body len = {len(body)}")
        print(f"  'New Task' in body: {'New Task' in body}")
        print(f"  'Sign in' in body: {'Sign in' in body}")
        # extra diagnostics: dump interesting markers
        for marker in ["New Task", "Agents", "Agent", "Sign in", "Chat",
                       "Log in", "Create", "Task"]:
            if marker in body:
                idx = body.find(marker)
                print(f"  marker {marker!r} @ {idx}: ...{body[max(0,idx-40):idx+60]!r}...")
        url = c.eval("location.href", timeout=8)
        print(f"step5: url = {url!r}")
    except Exception as e:
        print(f"FAIL during eval: {e!r}")
    finally:
        try:
            c.close()
        except Exception:
            pass
        _close(tab)

def _close(tab):
    try:
        import urllib.request
        urllib.request.urlopen(
            f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
    except Exception as e:
        print(f"  (tab close err: {e!r})")

if __name__ == "__main__":
    main()
