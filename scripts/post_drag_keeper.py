#!/usr/bin/env python3
"""post_drag_keeper.py — after the operator's drag: click Sign in, verify,
re-arm if the captcha resets. Runs alongside login_keeper (which snapshots
the durable token the moment it lands). 24h window, 5s poll."""
import json, os, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = "/home/z/replay2/scripts/logs/post_drag_keeper.log"
DEADLINE = time.time() + 24 * 3600

def log(m):
    line = f"[post_drag {time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)

def js_eval(c, expr):
    r = c.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout=30)
    return r.get("result", {}).get("value")

PROBE = r"""(() => {
  const t = localStorage.getItem('token');
  let email = null;
  try { const p = JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))); email = p.email || null; } catch(e) {}
  const norm = s => (s||'').replace(/\s+/g,' ').trim();
  const text = document.body.innerText || '';
  return JSON.stringify({url: location.href, email,
    authed: !!(email && !String(email).startsWith('guest-')),
    drag: text.includes('drag the slider'),
    start: text.includes('Click to start verification'),
    signin: [...document.querySelectorAll('button')].some(b => norm(b.innerText) === 'Sign in')});
})()"""

CLICK = r"""((txt) => {
  const norm = s => (s||'').replace(/\s+/g,' ').trim();
  const b = [...document.querySelectorAll('button, div[role=button], span, div')].filter(x => norm(x.innerText) === txt && x.children.length <= 2).pop();
  if (!b) return false;
  b.click();
  return true;
})(%s)"""

def main():
    armed = False
    signins = 0
    while time.time() < DEADLINE:
        try:
            tab = channel.find_tab("chat.z.ai")
            if not tab:
                time.sleep(5); continue
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
            v = js_eval(c, PROBE)
            s = json.loads(v) if v else {}
            if s.get("authed"):
                log(f"AUTHENTICATED as {s.get('email')} — done (login_keeper snapshots)")
                open(os.path.join(BASE, "../flags/post_drag_done"), "w").write(str(int(time.time())))
                return 0
            if s.get("drag"):
                if not armed:
                    armed = True
                    log("captcha LIVE — waiting for the operator's drag")
            elif armed and s.get("signin"):
                signins += 1
                log(f"captcha cleared — clicking Sign in (attempt {signins})")
                js_eval(c, CLICK % json.dumps("Sign in"))
                time.sleep(6)
                v2 = js_eval(c, PROBE)
                s2 = json.loads(v2) if v2 else {}
                if s2.get("authed"):
                    log(f"AUTHENTICATED as {s2.get('email')} — done")
                    open(os.path.join(BASE, "../flags/post_drag_done"), "w").write(str(int(time.time())))
                    return 0
                if s2.get("drag"):
                    log("captcha re-armed by site — operator's next drag")
                elif s2.get("start"):
                    log("captcha reset — re-arming slider for the operator")
                    js_eval(c, CLICK % json.dumps("Click to start verification"))
                    time.sleep(4)
                else:
                    log(f"post-signin state: url={s2.get('url','?')} — keeping watch")
            c.ws.close()
        except Exception as e:
            log(f"cycle error (non-fatal): {e!r}")
        time.sleep(5)
    log("24h window expired")
    return 1

if __name__ == "__main__":
    sys.exit(main())
