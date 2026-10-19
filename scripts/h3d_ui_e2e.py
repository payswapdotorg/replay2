#!/usr/bin/env python3
"""h3d_ui_e2e.py — browser-level UI verification of the hyper3d-clone on :3212
using the replay Chrome (CDP :9222). Steps: open studio, sign in via dialog,
text-to-3D generate through the studio UI, watch progress, verify viewer."""
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


def js(ws, expr, timeout=45):
    return ws.eval(expr, await_promise=True, timeout=timeout)


def main():
    ws = get_ws()
    try:
        # 1. click Start Creating -> studio overlay
        r = js(ws, """(async () => {
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim() === 'Start Creating');
          if (!b) return 'BTN-NOT-FOUND';
          b.click();
          await new Promise(r => setTimeout(r, 2500));
          const dlg = document.querySelector('[role=dialog]');
          return JSON.stringify({
            hasDialog: !!dlg,
            dlgLen: dlg ? dlg.innerText.length : 0,
            head: dlg ? dlg.innerText.slice(0, 400) : null
          });
        })()""")
        print("studio open:", r)
        shot(ws, "shot-studio-open")

        # 2. sign-in: the GENERATE click when unauthenticated opens sign-in
        r = js(ws, """(async () => {
          const gen = Array.from(document.querySelectorAll('button'))
            .find(x => x.innerText.trim().toUpperCase().includes('GENERATE'));
          if (!gen) return 'GEN-NOT-FOUND';
          gen.click();
          await new Promise(r => setTimeout(r, 2000));
          const dlg = document.querySelector('[role=dialog]');
          return JSON.stringify({
            dlgNow: dlg ? dlg.innerText.slice(0, 300) : null,
            inputs: Array.from(document.querySelectorAll('input'))
              .map(i => ({type: i.type, ph: i.placeholder, name: i.name})).slice(0, 6)
          });
        })()""")
        print("signin dialog:", r)
        shot(ws, "shot-signin-dialog")

        # 3. fill credentials and submit
        r = js(ws, """(async () => {
          const inputs = Array.from(document.querySelectorAll('input'));
          const email = inputs.find(i => i.type === 'email' || /mail/i.test(i.name + i.placeholder));
          const pass = inputs.find(i => i.type === 'password');
          if (!email || !pass) return 'INPUTS-NOT-FOUND: ' + inputs.map(i=>i.type).join(',');
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(email, 'demo@hyper3d.clone');
          email.dispatchEvent(new Event('input', {bubbles: true}));
          setter.call(pass, 'demo1234');
          pass.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 400));
          const form = email.closest('form');
          const submit = form ? form.querySelector('button[type=submit], button:not([type])') : null;
          const dlg = document.querySelector('[role=dialog]');
          const btn = (dlg || document).querySelector('button[type=submit]') ||
                      Array.from((dlg || document).querySelectorAll('button'))
                        .find(b => /sign in|log in/i.test(b.innerText));
          if (!btn) return 'SUBMIT-NOT-FOUND';
          btn.click();
          await new Promise(r => setTimeout(r, 2500));
          return JSON.stringify({
            submitted: true,
            dlgGone: !document.querySelector('[role=dialog]'),
            creditPill: (document.body.innerText.match(/(\\d+)\\s*(credits?|Credits)/) || [])[0] || null,
            bodyHasDemo: document.body.innerText.includes('demo creator')
          });
        })()""")
        print("signed in:", r)
        shot(ws, "shot-signed-in")

        # 4. text-to-3D through the studio: switch to Text to 3D tab, type, generate
        r = js(ws, """(async () => {
          const tab = Array.from(document.querySelectorAll('[role=tab], button'))
            .find(x => x.innerText.trim() === 'Text to 3D');
          if (!tab) return 'TAB-NOT-FOUND';
          tab.click();
          await new Promise(r => setTimeout(r, 800));
          const ta = document.querySelector('textarea');
          if (!ta) return 'TEXTAREA-NOT-FOUND';
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, 'a medieval knight helmet with a plume');
          ta.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 600));
          const gen = Array.from(document.querySelectorAll('button'))
            .find(x => x.innerText.trim().toUpperCase().includes('GENERATE'));
          if (!gen) return 'GEN2-NOT-FOUND';
          gen.click();
          return 'GENERATE-CLICKED';
        })()""")
        print("text-to-3d:", r)

        # 5. poll studio for completion (progress pill -> done, canvas present)
        for i in range(36):
            time.sleep(5)
            r = js(ws, """(async () => {
              const t = document.body.innerText;
              const canvas = document.querySelector('canvas');
              return JSON.stringify({
                bodyLen: t.length,
                canvas: !!canvas,
                canvasCount: document.querySelectorAll('canvas').length,
                done: /Done|Preview ready|Export|Download/i.test(t.slice(-3000)),
                progress: (t.match(/[A-Za-z][^.]{10,80}\\.\\.\\./g) || []).slice(-1)[0] || null,
                tail: t.slice(-200).replace(/\\n+/g, ' | ')
              });
            })()""")
            d = json.loads(r)
            print(f"  [{i}] canvas={d['canvas']} done={d['done']} tail={d['tail'][:110]}")
            if d["done"] or d["canvas"]:
                break
        shot(ws, "shot-viewer")
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
