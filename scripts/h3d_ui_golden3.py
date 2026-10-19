#!/usr/bin/env python3
"""h3d_ui_golden3.py — post-fix full golden path:
sign out -> Start Creating (sign-in dialog) -> sign in -> studio AUTO-OPENS
-> Text to 3D -> GENERATE -> progress -> viewer canvas -> screenshot."""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402

SHOT_DIR = "/home/z/h3d-harvest"
SEL = "div[role=dialog][aria-label='Rodin Studio workspace']"


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
        # 0. reload fresh
        ws.call("Page.reload", timeout=15)
        time.sleep(10)
        r = ws.eval("""JSON.stringify({
          title: document.title.slice(0, 40),
          studio: !!document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']"),
          signedIn: document.body.innerText.includes('demo creator')
        })""", timeout=20)
        print("fresh state:", r)

        # 1. sign out if signed in (header avatar menu -> Sign out)
        r = ws.eval("""(async () => {
          if (!document.body.innerText.includes('demo creator')) return 'already-out';
          // click the account button in the header
          const hdr = document.querySelector('header') || document.body;
          let acct = Array.from(hdr.querySelectorAll('button')).find(b => /demo|account|avatar/i.test((b.innerText || '') + b.getAttribute('aria-label') || ''));
          if (!acct) acct = Array.from(document.querySelectorAll('button')).find(b => /demo creator/i.test(b.innerText));
          if (!acct) return 'NO-ACCT-BTN';
          acct.click();
          await new Promise(r => setTimeout(r, 900));
          const so = Array.from(document.querySelectorAll('[role=menuitem], button')).find(b => /sign out/i.test(b.innerText));
          if (!so) return 'NO-SIGNOUT';
          so.click();
          await new Promise(r => setTimeout(r, 1500));
          return 'signedOut=' + !document.body.innerText.includes('demo creator');
        })()""", await_promise=True, timeout=30)
        print("sign-out:", r)

        # 2. Start Creating -> sign-in dialog with intent
        r = ws.eval("""(async () => {
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim() === 'Start Creating');
          if (!b) return 'BTN-NOT-FOUND';
          b.click();
          await new Promise(r => setTimeout(r, 1800));
          const dlg = Array.from(document.querySelectorAll('[role=dialog]')).pop();
          return JSON.stringify({
            dlg: dlg ? dlg.innerText.slice(0, 120).replace(/\\n+/g, ' | ') : null,
            hasEmail: !!document.querySelector('input[type=email]')
          });
        })()""", await_promise=True, timeout=30)
        print("start creating:", r)

        # 3. sign in -> studio should AUTO-OPEN now (the fix)
        r = ws.eval("""(async () => {
          const inputs = Array.from(document.querySelectorAll('input'));
          const email = inputs.find(i => i.type === 'email');
          const pass = inputs.find(i => i.type === 'password');
          if (!email || !pass) return 'NO-INPUTS';
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(email, 'demo@hyper3d.clone');
          email.dispatchEvent(new Event('input', {bubbles: true}));
          setter.call(pass, 'demo1234');
          pass.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 400));
          const signin = Array.from(document.querySelectorAll('button'))
            .find(b => b.innerText.trim() === 'Sign in');
          signin.click();
          for (let i = 0; i < 24; i++) {
            await new Promise(r => setTimeout(r, 500));
            if (document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']")) break;
          }
          return JSON.stringify({
            studioAutoOpened: !!document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']"),
            signedIn: document.body.innerText.includes('demo creator'),
            dlgClosed: !document.querySelector('input[type=password]')
          });
        })()""", await_promise=True, timeout=45)
        print("sign-in -> studio:", r)
        shot(ws, "shot-studio-after-signin")

        # 4. studio: Text to 3D mode, prompt, GENERATE
        r = ws.eval(f"""(async () => {{
          const root = document.querySelector("{SEL}");
          if (!root) return 'NO-STUDIO';
          const tab = Array.from(root.querySelectorAll('button')).find(b => b.innerText.trim().startsWith('Text to 3D'));
          if (!tab) return 'NO-TAB';
          tab.click();
          await new Promise(r => setTimeout(r, 700));
          const ta = root.querySelector('textarea');
          if (!ta) return 'NO-TEXTAREA';
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, 'a medieval knight helmet with a red plume');
          ta.dispatchEvent(new Event('input', {{bubbles: true}}));
          await new Promise(r => setTimeout(r, 600));
          const gen = Array.from(root.querySelectorAll('button'))
            .find(b => /^GENERATE/.test(b.innerText.trim()));
          if (!gen) return 'NO-GEN';
          const label = gen.innerText.trim().replace(/\\n+/g, ' ');
          gen.click();
          return 'CLICKED: ' + label;
        }})()""", await_promise=True, timeout=30)
        print("generate:", r)
        shot(ws, "shot-generating2")

        # 5. poll for completion inside studio
        for i in range(45):
            time.sleep(5)
            r = ws.eval(f"""(async () => {{
              const root = document.querySelector("{SEL}");
              if (!root) return JSON.stringify({{studioGone: true}});
              const t = root.innerText;
              return JSON.stringify({{
                canvases: root.querySelectorAll('canvas').length,
                progress: (t.match(/[A-Za-z][^.{{}}]{{15,90}}\\.\\.\\./g) || []).slice(-1)[0] || null,
                hasExport: /export|download|GLB|USDZ/i.test(t),
                error: /failed|error/i.test(t.slice(-400)),
                tail: t.slice(-130).replace(/\\n+/g, ' | ')
              }});
            }})""", timeout=30)
            d = json.loads(r) if isinstance(r, str) else r
            print(f"  [{i}] canvas={d.get('canvases')} export={d.get('hasExport')} err={d.get('error')} tail={str(d.get('tail'))[:95]}")
            if d.get("canvases") or d.get("hasExport") or d.get("studioGone"):
                break
        shot(ws, "shot-viewer-done")
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
