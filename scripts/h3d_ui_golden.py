#!/usr/bin/env python3
"""h3d_ui_golden.py — full browser golden path: sign in via dialog ->
text-to-3D generate in studio -> wait for viewer -> screenshot."""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402

SHOT_DIR = "/home/z/h3d-harvest"


def get_ws():
    tabs = [t for t in list_tabs() if "3212" in (t.get("url") or "")]
    if not tabs:
        raise SystemExit("no :3212 tab")
    return CDP(tabs[0]["webSocketDebuggerUrl"])


def shot(ws, name):
    r = ws.call("Page.captureScreenshot", {"format": "jpeg", "quality": 72}, timeout=30)
    with open(f"{SHOT_DIR}/{name}.jpg", "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print(f"  [shot] {name}.jpg")


def main():
    ws = get_ws()
    try:
        # ensure studio open (from prior run it is)
        r = ws.eval("JSON.stringify({studio: document.body.innerText.includes('Image to 3D'), dlg: !!document.querySelector('[role=dialog]')})", timeout=15)
        print("state:", r)

        # 1. sign in through the dialog (inputs are inside the dialog)
        r = ws.eval("""(async () => {
          const inputs = Array.from(document.querySelectorAll('input'));
          const email = inputs.find(i => i.type === 'email');
          const pass = inputs.find(i => i.type === 'password');
          if (!email || !pass) return 'NO-INPUTS ' + inputs.map(i => i.type).join(',');
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(email, 'demo@hyper3d.clone');
          email.dispatchEvent(new Event('input', {bubbles: true}));
          setter.call(pass, 'demo1234');
          pass.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 500));
          const btns = Array.from(document.querySelectorAll('button'));
          const signin = btns.find(b => b.innerText.trim() === 'Sign in' && b.closest('[role=dialog]'));
          if (!signin) return 'NO-SIGNIN-BTN';
          signin.click();
          for (let i = 0; i < 20; i++) {
            await new Promise(r => setTimeout(r, 500));
            const t = document.body.innerText;
            if (/demo creator|credits/i.test(t) && !document.querySelector('input[type=password]')) break;
          }
          return JSON.stringify({
            signedIn: document.body.innerText.includes('demo creator'),
            creditPill: (document.body.innerText.match(/\\d+\\s*Credits?/i) || [])[0] || null,
            passGone: !document.querySelector('input[type=password]')
          });
        })()""", await_promise=True, timeout=40)
        print("sign-in:", r)
        shot(ws, "shot-signed-in-studio")

        # 2. switch to Text to 3D, type prompt, generate
        r = ws.eval("""(async () => {
          const tab = Array.from(document.querySelectorAll('[role=tab], button'))
            .find(x => x.innerText.trim() === 'Text to 3D');
          if (!tab) return 'NO-TAB';
          tab.click();
          await new Promise(r => setTimeout(r, 700));
          const ta = document.querySelector('textarea');
          if (!ta) return 'NO-TEXTAREA';
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, 'a medieval knight helmet with a red plume');
          ta.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 500));
          const gen = Array.from(document.querySelectorAll('button'))
            .filter(b => /GENERATE/i.test(b.innerText))
            .pop();
          if (!gen) return 'NO-GEN';
          gen.click();
          return 'CLICKED: ' + gen.innerText.trim().replace(/\\n+/g, ' ');
        })()""", await_promise=True, timeout=30)
        print("generate:", r)

        # 3. poll for progress + completion (canvas viewer)
        final = None
        for i in range(40):
            time.sleep(5)
            r = ws.eval("""(async () => {
              const t = document.body.innerText;
              const canvases = document.querySelectorAll('canvas');
              return JSON.stringify({
                errs: window.__errs ? window.__errs.slice(-3) : null,
                canvases: canvases.length,
                progress: (t.match(/[A-Za-z][^.]{15,90}\\.\\.\\./g) || []).slice(-1)[0] || null,
                exports: /export|download/i.test(t) && canvases.length > 0,
                creditNow: (t.match(/(\\d+)\\s*Credits?/i) || [])[1] || null,
                tail: t.slice(-160).replace(/\\n+/g, ' | ')
              });
            })()""", timeout=30)
            d = json.loads(r)
            final = d
            print(f"  [{i}] canvas={d['canvases']} progress={(d['progress'] or '')[:60]} credit={d['creditNow']} tail={d['tail'][:80]}")
            if d["canvases"] > 0 or d["exports"]:
                break
            if d["errs"]:
                print("  ERRS:", d["errs"])
        shot(ws, "shot-final")
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
