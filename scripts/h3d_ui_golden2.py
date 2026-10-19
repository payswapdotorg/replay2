#!/usr/bin/env python3
"""h3d_ui_golden2.py — browser golden path v2: scoped to the studio root
(div[role=dialog][aria-label='Rodin Studio workspace'])."""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402

SHOT_DIR = "/home/z/h3d-harvest"
ROOT = "document.querySelector(\"div[role=dialog][aria-label='Rodin Studio workspace']\")"


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
        # 0. state: is the studio open? are we signed in?
        r = ws.eval(f"""JSON.stringify({{
          studioOpen: !!{ROOT},
          signedIn: document.body.innerText.includes('demo creator'),
          creditPill: (document.body.innerText.match(/(\\d+)\\s*\\n?credits/i) || [])[1] || null
        }})""", timeout=15)
        print("state:", r)

        # 1. open studio if needed (Start Creating)
        r = ws.eval("""(async () => {
          if (document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']")) return 'already-open';
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim() === 'Start Creating');
          if (!b) return 'BTN-NOT-FOUND';
          b.click();
          await new Promise(r => setTimeout(r, 2000));
          return 'opened=' + !!document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
        })()""", await_promise=True, timeout=30)
        print("studio:", r)
        shot(ws, "shot-studio")

        # 2. sign in if needed (studio shows its own sign-in button / GENERATE opens dialog)
        r = ws.eval("""(async () => {
          if (document.body.innerText.includes('demo creator')) return 'already-signed-in';
          const inputs = Array.from(document.querySelectorAll('input'));
          let email = inputs.find(i => i.type === 'email');
          let pass = inputs.find(i => i.type === 'password');
          if (!email) {
            const gen = Array.from(document.querySelectorAll('button'))
              .find(b => /^GENERATE/i.test(b.innerText.trim()));
            if (gen) gen.click();
            await new Promise(r => setTimeout(r, 1500));
          }
          const inputs2 = Array.from(document.querySelectorAll('input'));
          email = inputs2.find(i => i.type === 'email');
          pass = inputs2.find(i => i.type === 'password');
          if (!email || !pass) return 'NO-INPUTS';
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(email, 'demo@hyper3d.clone');
          email.dispatchEvent(new Event('input', {bubbles: true}));
          setter.call(pass, 'demo1234');
          pass.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(r => setTimeout(r, 500));
          const signin = Array.from(document.querySelectorAll('button'))
            .find(b => b.innerText.trim() === 'Sign in');
          if (!signin) return 'NO-SIGNIN-BTN';
          signin.click();
          await new Promise(r => setTimeout(r, 3000));
          return 'signedIn=' + document.body.innerText.includes('demo creator');
        })()""", await_promise=True, timeout=45)
        print("sign-in:", r)

        # 3. inside the STUDIO: click Text to 3D mode button
        r = ws.eval(f"""(async () => {{
          const root = {ROOT};
          if (!root) return 'NO-STUDIO';
          const btns = Array.from(root.querySelectorAll('button'));
          const tab = btns.find(b => b.innerText.trim() === 'Text to 3D');
          if (!tab) return 'NO-TAB: ' + btns.map(b=>b.innerText.trim().slice(0,18)).filter(Boolean).slice(0,18).join(' / ');
          tab.click();
          await new Promise(r => setTimeout(r, 700));
          return 'tab-clicked';
        }})()""", await_promise=True, timeout=30)
        print("mode:", r)

        # 4. fill prompt + click studio GENERATE (label: GENERATE 1 Credit etc.)
        r = ws.eval(f"""(async () => {{
          const root = {ROOT};
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
        shot(ws, "shot-generating")

        # 5. poll inside studio for canvas / completion
        for i in range(40):
            time.sleep(5)
            r = ws.eval(f"""(async () => {{
              const root = {ROOT};
              if (!root) return JSON.stringify({{studioGone: true}});
              const t = root.innerText;
              const canvases = root.querySelectorAll('canvas').length;
              return JSON.stringify({{
                canvases: canvases,
                progress: (t.match(/[A-Za-z][^.{{}}]{{15,90}}\\.\\.\\./g) || []).slice(-1)[0] || null,
                hasExport: /export|download|GLB|USDZ/i.test(t),
                generating: /generating|queued/i.test(t),
                tail: t.slice(-140).replace(/\\n+/g, ' | ')
              }});
            }})()""", timeout=30)
            d = json.loads(r) if isinstance(r, str) else r
            print(f"  [{i}] canvas={d.get('canvases')} export={d.get('hasExport')} tail={str(d.get('tail'))[:100]}")
            if d.get("canvases") or d.get("hasExport"):
                break
            if d.get("studioGone"):
                print("  !! studio closed unexpectedly")
                break
        shot(ws, "shot-viewer-final")
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
