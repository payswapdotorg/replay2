#!/usr/bin/env python3
"""arm_login.py v2 — drive chat.z.ai/auth to the LIVE-SLIDER state and STOP.

Lessons baked in:
- guest detection = JWT email claim starts with 'guest-' (raw token is a JWT)
- SPA buttons (Continue-with-Email, Sign in) need el.click() — CDP real-mouse
  clicks land dead-center yet do nothing on them
- button text contains newlines: normalize whitespace before exact match
- the captcha 'Click to start verification' gets a real-mouse click (Task-17
  doctrine) with JS fallback + verification
- the slider drag is the OPERATOR's move — this script never drags
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

AUTH = "https://chat.z.ai/auth"
EMAIL = os.environ.get("REPLAY_LOGIN_EMAIL", "")
PASSWORD = os.environ.get("REPLAY_LOGIN_PASSWORD", "")

def js_eval(c, expr):
    r = c.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout=30)
    return r.get("result", {}).get("value")

def real_click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.09)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)

FIND_BTN = r"""((txt) => {
  const norm = s => (s||'').replace(/\s+/g,' ').trim();
  const cands = [...document.querySelectorAll('button, div[role=button], span, div')].filter(x => norm(x.innerText) === txt && x.children.length <= 2);
  if (!cands.length) return null;
  const el = cands[cands.length-1];
  const r = el.getBoundingClientRect();
  return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height, disabled: !!el.disabled};
})(%s)"""

JS_CLICK = r"""((txt) => {
  const norm = s => (s||'').replace(/\s+/g,' ').trim();
  const b = [...document.querySelectorAll('button, div[role=button], span, div')].filter(x => norm(x.innerText) === txt && x.children.length <= 2).pop();
  if (!b) return false;
  b.click();
  return true;
})(%s)"""

FILL = r"""((sel, val) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, val);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return true;
})(%s, %s)"""

def find_btn(c, txt):
    v = js_eval(c, FIND_BTN % json.dumps(txt))
    return v if (v and not v.get("disabled")) else None

def wait_btn(c, txt, tries=20, gap=1.0):
    for _ in range(tries):
        v = find_btn(c, txt)
        if v:
            return v
        time.sleep(gap)
    return None

def click_btn(c, txt, verify_js, tries=3):
    """real-mouse click, verify, JS-click fallback."""
    for attempt in range(tries):
        v = find_btn(c, txt)
        if not v:
            return False
        if attempt == 0:
            print(f"real-click '{txt}' at", round(v["x"]), round(v["y"]))
            real_click(c, v["x"], v["y"])
        else:
            print(f"js-click fallback '{txt}' (attempt {attempt+1})")
            js_eval(c, JS_CLICK % json.dumps(txt))
        time.sleep(3)
        if js_eval(c, verify_js):
            return True
    return js_eval(c, verify_js)

def main():
    tab = channel.find_tab("chat.z.ai")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    st = js_eval(c, r"""(() => {
      const t = localStorage.getItem('token');
      let email = null;
      try { const p = JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))); email = p.email || null; } catch(e) {}
      return JSON.stringify({url: location.href, hasToken: !!t, email,
        guest: !!(email && String(email).startsWith('guest-'))});
    })()""")
    print("state:", st)
    state = json.loads(st) if st else {}
    if state.get("hasToken") and not state.get("guest"):
        print("ALREADY AUTHENTICATED — no arm needed:", state.get("email"))
        return 0

    if "/auth" not in state.get("url", ""):
        c.call("Page.navigate", {"url": AUTH}, timeout=30)
        time.sleep(6)

    HAS_EMAIL_FORM = r"""(!!document.querySelector('input[type=email]'))"""
    if not js_eval(c, HAS_EMAIL_FORM):
        ok = click_btn(c, "Continue with Email", HAS_EMAIL_FORM)
        if not ok:
            print("FATAL: email form never appeared"); return 1
    print("email form live")

    for _ in range(15):
        if js_eval(c, FILL % ('"input[type=email]"', json.dumps(EMAIL))):
            break
        time.sleep(1)
    else:
        print("FATAL: email input missing"); return 1
    time.sleep(0.8)
    for _ in range(15):
        if js_eval(c, FILL % ('"input[type=password]"', json.dumps(PASSWORD))):
            break
        time.sleep(1)
    else:
        print("FATAL: password input missing"); return 1
    print("credentials filled")

    HAS_CAPTCHA = r"""((document.body.innerText||'').includes('Click to start verification'))"""
    if not js_eval(c, HAS_CAPTCHA):
        print("FATAL: captcha start element not on form"); return 1

    # captcha FIRST (signin without captcha token = 400 per Task-16 API probe).
    # real-mouse click for the captcha start (Task-17 doctrine), JS fallback.
    ok = click_btn(c, "Click to start verification",
                   r"""(!!(document.body.innerText||'').includes('drag the slider'))""")
    if not ok:
        print("WARN: slider prompt not detected — check frame manually")

    geo = js_eval(c, r"""(() => {
      const cs = [...document.querySelectorAll('canvas')].map(cv => { const r = cv.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; });
      return JSON.stringify({canvases: cs, dragPrompt: (document.body.innerText||'').includes('drag the slider'), url: location.href});
    })()""")
    print("geometry:", (geo or "")[:300])
    g = json.loads(geo) if geo else {}
    if g.get("dragPrompt") or len(g.get("canvases", [])) >= 2:
        print("SLIDER LIVE — operator's move (one drag in the mirror)")

    try:
        req = urllib.request.Request("http://127.0.0.1:3100/tabs",
            data=json.dumps({"id": tab["id"]}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        print("mirror active-tab set:", urllib.request.urlopen(req, timeout=10).status)
    except Exception as e:
        print("mirror set failed:", e)
    return 0

if __name__ == "__main__":
    sys.exit(main())
