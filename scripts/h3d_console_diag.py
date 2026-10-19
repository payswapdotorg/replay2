#!/usr/bin/env python3
"""h3d_console_diag.py — reload :3212, attach console listener, reproduce the
GENERATE-click client crash, dump console errors."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402


def get_ws():
    tabs = [t for t in list_tabs() if "3212" in (t.get("url") or "")]
    if not tabs:
        raise SystemExit("no :3212 tab")
    return CDP(tabs[0]["webSocketDebuggerUrl"])


def main():
    ws = get_ws()
    try:
        # enable console capture
        ws.call("Runtime.enable", timeout=10)
        # install error trap + reload
        ws.eval("window.__errs = []; window.addEventListener('error', e => window.__errs.push(String(e.message))); "
                "window.addEventListener('unhandledrejection', e => window.__errs.push('REJ ' + String(e.reason)));",
                timeout=10)
        ws.call("Page.reload", timeout=15)
        time.sleep(12)
        ws.eval("window.__errs = []; window.addEventListener('error', e => window.__errs.push(String(e.message))); "
                "window.addEventListener('unhandledrejection', e => window.__errs.push('REJ ' + String(e.reason)));",
                timeout=10)
        print("reloaded, trap armed")

        # step 1: open studio
        r = ws.eval("""(async () => {
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim() === 'Start Creating');
          if (!b) return 'BTN-NOT-FOUND';
          b.click();
          await new Promise(r => setTimeout(r, 2000));
          return 'studio-open dlg=' + !!document.querySelector('[role=dialog]');
        })()""", await_promise=True, timeout=30)
        print("open studio:", r)

        # step 2: if sign-in dialog shows, close it first (Close button)
        r = ws.eval("""(async () => {
          const dlg = document.querySelector('[role=dialog]');
          if (!dlg) return 'no-dialog';
          const close = Array.from(dlg.querySelectorAll('button')).find(b => /close/i.test(b.innerText));
          if (close) { close.click(); await new Promise(r => setTimeout(r, 800)); }
          return 'dialog-closed=' + !document.querySelector('[role=dialog]');
        })()""", await_promise=True, timeout=30)
        print("close dialog:", r)

        # step 3: inspect studio state now
        r = ws.eval("""JSON.stringify({
          errs: window.__errs,
          tabs: Array.from(document.querySelectorAll('[role=tab]')).map(t => t.innerText.trim()),
          buttons: Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t && t.length < 30).slice(0, 20),
          textarea: !!document.querySelector('textarea'),
          signInHint: document.body.innerText.includes('demo@hyper3d.clone')
        })""", timeout=30)
        print("studio state:", r[:900])
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
