#!/usr/bin/env python3
"""replayd.py — persistent CDP replay daemon (:3100).

Hot path for the operator console. The legacy path spawned a fresh python +
CDP websocket per event/frame (~120-400ms); this daemon holds long-lived
per-tab CDP connections so:

  * streamed drag events (dragstart/dragmove/dragend) land in ~5ms
  * frames (Page.captureScreenshot) return in ~100ms
  * the console polls frames fast enough that drags reflect in REAL TIME
    (required for slider captcha verification)

Endpoints (bound to 127.0.0.1 only; the Next.js routes proxy to it):
  GET  /healthz      -> {"ok":true, ...}
  GET  /frame        -> jpeg screenshot of the active tab
  GET  /tabs         -> {active,new,tabs:[...]}      (same shape as bridge)
  POST /tabs         -> {"id": "..."}                (set active tab)
  POST /event        -> input events; same kinds as bridge.py PLUS
                        dragstart / dragmove / dragend (streamed drags)

Per-tab connections are split into an INPUT channel and a CAPTURE channel
with separate locks, so screenshots never delay input. Dead sockets are
dropped and re-established lazily on the next request.
Supervised by supervisor.py + watcher.py (never-die mandate).
"""
import base64
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOG = os.path.join(LOGDIR, "replayd.log")
HOST = "127.0.0.1"
PORT = int(os.environ.get("REPLAYD_PORT", "3100"))

os.makedirs(FLAGS, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)

_conns = {}            # tab_id -> _TabConn
_conns_lock = threading.Lock()
_seen_lock = threading.Lock()

# ---- hidden-tab input throttling (root cause of "slow captcha drags",
#      verified 2026-09-27): Chrome defers CDP input acks ~0.5-5s for tabs
#      that are not the front tab (Input.dispatchMouseEvent measured 3.2s
#      avg on a hidden tab vs 13.7ms after Page.bringToFront). We track the
#      front tab and re-front ours before dispatching input.
_front_tab_id = ""
_front_lock = threading.Lock()

# ---- viewport cache: Page.getLayoutMetrics per dragmove goes through the
#      CAPTURE channel (shared with screenshots, ~70ms holds); a short TTL
#      cache removes that contention so dragmoves never queue behind frames.
_vp_cache = {}          # tab_id -> (ts, w, h)
_vp_lock = threading.Lock()
_VP_TTL = 2.0

# event kinds that dispatch Input.* to the renderer (hidden-tab-throttled)
_INPUT_KINDS = {"click", "dblclick", "dragstart", "dragmove", "dragend",
                "move", "key", "enter", "type", "scroll", "drag"}
_last_good_frame = b""   # stale-serving cache (lesson 102)
_last_good_ts = 0.0
_last_good_lock = threading.Lock()
_started = time.time()
_stats = {"events": 0, "frames": 0, "errors": 0}


def log(msg):
    line = time.strftime("[%H:%M:%S] ") + msg
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1024 * 1024:
            with open(LOG, "rb") as f:
                f.seek(-120 * 1024, 2)
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- tab conns

class _TabConn:
    """Two CDP connections per tab: input (Input domain) + capture
    (Page/Runtime). Separate locks => a screenshot never blocks a dragmove."""

    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.inp = channel.CDP(ws_url, timeout=10)
        self.cap = channel.CDP(ws_url, timeout=20)
        self.linp = threading.Lock()
        self.lcap = threading.Lock()

    def close(self):
        for c in (self.inp, self.cap):
            try:
                c.close()
            except Exception:
                pass

    def input(self, method, params, timeout=8):
        with self.linp:
            return self.inp.call(method, params, timeout=timeout)

    def capture(self, method, params, timeout=15):
        with self.lcap:
            return self.cap.call(method, params, timeout=timeout)

    def eval(self, expr, timeout=10):
        with self.lcap:
            return self.cap.eval(expr, timeout=timeout)


def active_tab_id():
    try:
        return open(os.path.join(FLAGS, "active_tab.txt")).read().strip()
    except Exception:
        return ""


def pick_tab(tabs=None):
    tabs = tabs if tabs is not None else channel.list_tabs()
    if not tabs:
        return None
    aid = active_tab_id()
    for t in tabs:
        if t.get("id") == aid:
            return t
    # stored pointer is stale (tab closed / sandbox reset) — resolve fresh
    # and SELF-HEAL the pointer so frames, input and /healthz agree on one
    # tab instead of re-resolving (and re-writing) on every request.
    picked = None
    for t in tabs:
        if "chat.z.ai" in (t.get("url") or ""):
            picked = t
            break
    if picked is None:
        picked = tabs[0]
    try:
        open(os.path.join(FLAGS, "active_tab.txt"), "w").write(picked.get("id", ""))
    except Exception:
        pass
    return picked


def ensure_front(tid, c, force=False):
    """Bring tab to front before input dispatch. Chrome throttles CDP input
    acks on hidden tabs (0.5-5s per event); after bringToFront the same
    dispatch lands in ~14ms. force=True re-fronts even if tracked (used at
    drag start / on click — cheap insurance when an extension or worker
    dispatcher stole focus without our knowledge). Never raises."""
    global _front_tab_id
    with _front_lock:
        if not force and _front_tab_id == tid:
            return
    try:
        c.capture("Page.bringToFront", {}, timeout=3)
        with _front_lock:
            _front_tab_id = tid
    except Exception:
        pass  # wedged renderer: proceed — the input may be slow, not lost


def conn_for(tab):
    tid = tab.get("id")
    url = tab.get("webSocketDebuggerUrl")
    if not tid or not url:
        raise RuntimeError("bad-tab")
    with _conns_lock:
        c = _conns.get(tid)
        if c is not None and c.ws_url == url:
            return c
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        c = _TabConn(url)
        _conns[tid] = c
    try:
        c.capture("Page.enable", {}, timeout=10)
    except Exception:
        pass
    return c


def drop_conn(tid):
    with _conns_lock:
        c = _conns.pop(tid, None)
    if c:
        try:
            c.close()
        except Exception:
            pass


def prune_conns(tabs):
    ids = {t.get("id") for t in tabs}
    with _conns_lock:
        stale = [tid for tid in _conns if tid not in ids]
        for tid in stale:
            _conns.pop(tid)
    for tid in stale:
        drop_conn(tid)


def send_input(tid, c, method, params, timeout=8):
    try:
        return c.input(method, params, timeout)
    except Exception:
        drop_conn(tid)   # reconnect on next request
        raise


# ----------------------------------------------------------------- geometry

def viewport(c, tid=None):
    """Viewport size, TTL-cached per tab. The uncached CDP round-trip goes
    through the capture channel (shared with screenshots); during a live
    drag with frames polling at ~100ms that added up to ~70ms stalls per
    dragmove. The viewport does not change mid-drag, so a 2s cache is safe."""
    key = tid or ""
    now = time.time()
    with _vp_lock:
        hit = _vp_cache.get(key)
        if hit and now - hit[0] < _VP_TTL:
            return hit[1], hit[2]
    try:
        m = c.capture("Page.getLayoutMetrics", {}, timeout=8)
    except Exception:
        with _vp_lock:
            hit = _vp_cache.get(key)
            if hit:
                return hit[1], hit[2]   # stale beats the default guess
        return 1440.0, 756.0
    v = m.get("cssVisualViewport") or {}
    w = float(v.get("clientWidth") or 0)
    h = float(v.get("clientHeight") or 0)
    if not (w > 50 and h > 50):
        l = m.get("cssLayoutViewport") or {}
        w = float(l.get("clientWidth") or 1440)
        h = float(l.get("clientHeight") or 756)
    with _vp_lock:
        _vp_cache[key] = (now, w, h)
    return w, h


def resolve_pt(payload, c, tid=None, frac_keys=("fx", "fy"), abs_keys=("x", "y")):
    if frac_keys[0] in payload and frac_keys[1] in payload:
        w, h = viewport(c, tid)
        return float(payload[frac_keys[0]]) * w, float(payload[frac_keys[1]]) * h
    return float(payload.get(abs_keys[0], 0)), float(payload.get(abs_keys[1], 0))


# ------------------------------------------------------------------- probes

_PROBE_JS = """(function(){
  var X=%f, Y=%f;
  function clickable(el){var n=el;for(var i=0;i<6&&n;i++){var t=(n.tagName||'').toUpperCase();
    if(t==='A'||t==='BUTTON'||t==='TEXTAREA'||t==='SELECT'||n.getAttribute('role')==='button'||n.onclick||
       (t==='INPUT'))return n;
    n=n.parentElement;}return null;}
  function describe(el){if(!el)return null;var t=((el.innerText||el.value||el.placeholder||el.getAttribute('aria-label')||'')+'').trim().slice(0,60);
    return {tag:(el.tagName||'').toLowerCase(),id:el.id||'',cls:(''+(el.className||'')).slice(0,50),text:t};}
  function tryPt(x,y){var els=document.elementsFromPoint?document.elementsFromPoint(x,y):[document.elementFromPoint(x,y)];
    for(var i=0;i<els.length;i++){var c=clickable(els[i]);if(c)return describe(c);}return null;}
  var off=[[0,0]];
  var ds=[4,8,12,16,20,24];
  for(var j=0;j<ds.length;j++){var d=ds[j];off.push([d,0],[-d,0],[0,d],[0,-d],[d,d],[-d,d],[d,-d],[-d,-d]);}
  for(var k=0;k<off.length;k++){var r=tryPt(X+off[k][0],Y+off[k][1]);if(r){r.dx=off[k][0];r.dy=off[k][1];return r;}}
  var top=document.elementFromPoint(X,Y);
  var d2=describe(top);if(d2){d2.dx=0;d2.dy=0;return d2;}
  return {tag:'none',text:'',dx:0,dy:0};
})()"""

_DOMCLICK_JS = """(function(){
  var X=%f, Y=%f;
  function clickable(el){var n=el;for(var i=0;i<6&&n;i++){var t=(n.tagName||'').toUpperCase();
    if(t==='A'||t==='BUTTON'||t==='TEXTAREA'||t==='SELECT'||n.getAttribute('role')==='button'||n.onclick||
       (t==='INPUT'))return n;
    n=n.parentElement;}return null;}
  function findAt(x,y){var els=document.elementsFromPoint?document.elementsFromPoint(x,y):[document.elementFromPoint(x,y)];
    for(var i=0;i<els.length;i++){var c=clickable(els[i]);if(c)return c;}return document.elementFromPoint(x,y);}
  var off=[[0,0]];
  var ds=[4,8,12,16,20,24];
  for(var j=0;j<ds.length;j++){var d=ds[j];off.push([d,0],[-d,0],[0,d],[0,-d],[d,d],[-d,d],[d,-d],[-d,-d]);}
  var el=null,dx=0,dy=0;
  for(var k=0;k<off.length&&!el;k++){el=findAt(X+off[k][0],Y+off[k][1]);dx=off[k][0];dy=off[k][1];}
  if(!el)return {ok:false,target:{tag:'none',text:''}};
  var t=((el.innerText||el.value||el.getAttribute('aria-label')||'')+'').trim().slice(0,60);
  var desc={tag:(el.tagName||'').toLowerCase(),text:t,dx:dx,dy:dy};
  try{if(/^(input|textarea|select)$/i.test(el.tagName)){el.focus();if(el.setSelectionRange)el.setSelectionRange(el.value.length,el.value.length);}}catch(e){}
  try{el.click();}catch(e){return {ok:false,target:desc,err:''+e};}
  return {ok:true,target:desc};
})()"""

_FOCUS_JS = """(function(){
  var a=document.activeElement;
  if(a&&/^(input|textarea|select)$/i.test(a.tagName||'')&&!a.disabled&&!a.readOnly)return 'already-focused';
  function vis(el){try{var r=el.getBoundingClientRect();if(r.width<2||r.height<2)return false;
    var s=getComputedStyle(el);return s.visibility!=='hidden'&&s.display!=='none';}catch(e){return false;}}
  var sel='input[type=text],input[type=email],input[type=password],input[type=tel],input[type=number],input:not([type]),textarea';
  var els=[].slice.call(document.querySelectorAll(sel)).filter(function(el){return vis(el)&&!el.disabled&&!el.readOnly;});
  if(!els.length)return 'none-found';
  var el=els[0];
  el.focus();
  try{if(el.setSelectionRange)el.setSelectionRange((el.value||'').length,(el.value||'').length);}catch(e){}
  return 'focused:'+((el.placeholder||el.name||el.id||el.type||'field')+'').slice(0,40);
})()"""


# ------------------------------------------------------------------ events

def handle_event(payload):
    kind = payload.get("type")
    tab = pick_tab()
    if not tab:
        return {"ok": False, "error": "no-tab", "kind": kind}
    tid = tab["id"]
    c = conn_for(tab)

    # Anti-throttle: input to a hidden tab stalls 0.5-5s per event. Front
    # our tab before any Input.* dispatch (dragstart/click always re-front —
    # an extension or worker dispatcher may have stolen focus meanwhile).
    if kind in _INPUT_KINDS:
        ensure_front(tid, c, force=(kind in ("click", "dragstart")))

    if kind == "click":
        x, y = resolve_pt(payload, c, tid)
        target = None
        try:
            target = c.eval(_PROBE_JS % (x, y), timeout=12)
        except Exception:
            pass
        try:
            send_input(tid, c, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        except Exception:
            pass
        for typ in ("mousePressed", "mouseReleased"):
            send_input(tid, c, "Input.dispatchMouseEvent", {
                "type": typ, "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 1})
        return {"ok": True, "kind": "click", "x": round(x), "y": round(y), "target": target}

    if kind == "domclick":
        x, y = resolve_pt(payload, c, tid)
        res = c.eval(_DOMCLICK_JS % (x, y), timeout=12) or {"ok": False}
        res["kind"] = "domclick"
        res["x"] = round(x)
        res["y"] = round(y)
        return res

    if kind == "dblclick":
        x, y = resolve_pt(payload, c, tid)
        for typ in ("mousePressed", "mouseReleased", "mousePressed", "mouseReleased"):
            send_input(tid, c, "Input.dispatchMouseEvent", {
                "type": typ, "x": x, "y": y, "button": "left", "clickCount": 2, "buttons": 1})
        return {"ok": True, "kind": "dblclick", "x": round(x), "y": round(y)}

    # ---- streamed drag (THE fix for slider captchas) ----
    if kind == "dragstart":
        x, y = resolve_pt(payload, c, tid)
        # hover first (some sliders require it), then press
        send_input(tid, c, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 1})
        return {"ok": True, "kind": "dragstart", "x": round(x), "y": round(y)}

    if kind == "dragmove":
        x, y = resolve_pt(payload, c, tid)
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y, "button": "left", "buttons": 1})
        return {"ok": True, "kind": "dragmove", "x": round(x), "y": round(y)}

    if kind == "dragend":
        x, y = resolve_pt(payload, c, tid)
        # exact final position first, then release
        try:
            send_input(tid, c, "Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": x, "y": y, "button": "left", "buttons": 1})
        except Exception:
            pass
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 1})
        return {"ok": True, "kind": "dragend", "x": round(x), "y": round(y)}

    if kind == "move":
        x, y = resolve_pt(payload, c, tid)
        send_input(tid, c, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        return {"ok": True, "kind": "move"}

    if kind == "key":
        send_input(tid, c, "Input.dispatchKeyEvent", {"type": "char", "text": payload.get("text", "")})
        return {"ok": True, "kind": "key"}

    if kind == "enter":
        for typ in ("keyDown", "keyUp"):
            send_input(tid, c, "Input.dispatchKeyEvent", {
                "type": typ, "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        return {"ok": True, "kind": "enter"}

    if kind == "type":
        focus = None
        try:
            focus = c.eval(_FOCUS_JS, timeout=10)
        except Exception:
            pass
        text = payload.get("text", "")
        send_input(tid, c, "Input.insertText", {"text": text})
        return {"ok": True, "kind": "type", "chars": len(text), "focus": focus}

    if kind == "scroll":
        x, y = resolve_pt(payload, c, tid)
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y,
            "deltaX": 0, "deltaY": float(payload.get("deltaY", 120))})
        return {"ok": True, "kind": "scroll"}

    if kind == "drag":
        # legacy batch drag (kept for compatibility; FIXED fromFx/fromFy bug)
        import time as _time
        w, h = viewport(c, tid)
        if "fromFx" in payload:
            fx, fy = float(payload["fromFx"]) * w, float(payload["fromFy"]) * h
        else:
            fx, fy = float(payload.get("fromX", 0)), float(payload.get("fromY", 0))
        if "toFx" in payload:
            tx, ty = float(payload["toFx"]) * w, float(payload["toFy"]) * h
        else:
            tx, ty = float(payload.get("toX", 0)), float(payload.get("toY", 0))
        steps = max(2, int(payload.get("steps", 24)))
        import math as _math
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": fx, "y": fy, "button": "left", "clickCount": 1, "buttons": 1})
        for i in range(1, steps + 1):
            t = i / steps
            jy = 2.0 * _math.sin(i * 1.7)   # tiny jitter: less robotic
            send_input(tid, c, "Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": fx + (tx - fx) * t, "y": fy + (ty - fy) * t + jy,
                "button": "left", "buttons": 1})
            _time.sleep(0.025)
        send_input(tid, c, "Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": tx, "y": ty, "button": "left", "clickCount": 1, "buttons": 1})
        return {"ok": True, "kind": "drag", "from": [round(fx), round(fy)], "to": [round(tx), round(ty)]}

    if kind == "nav":
        c.capture("Page.navigate", {"url": payload.get("url", "https://chat.z.ai/")}, timeout=15)
        return {"ok": True, "kind": "nav"}

    if kind == "reload":
        try:
            c.capture("Page.reload", {"ignoreCache": True}, timeout=15)
        except Exception:
            try:
                c.capture("Page.navigate", {"url": c.eval("location.href") or "https://chat.z.ai/"}, timeout=15)
            except Exception:
                pass
        return {"ok": True, "kind": "reload"}

    if kind == "dialog":
        try:
            c.capture("Page.handleJavaScriptDialog", {"accept": True}, timeout=8)
        except Exception:
            pass
        return {"ok": True, "kind": "dialog"}

    if kind == "eval":
        # JS evaluation on the active tab (returnByValue). Used by the agent
        # chat backend to inspect page state; expression capped at 20k chars.
        expr = str(payload.get("expr", ""))[:20000]
        if not expr.strip():
            return {"ok": False, "error": "empty-expr", "kind": "eval"}
        try:
            res = c.eval(expr, timeout=15)
        except Exception as e:
            return {"ok": False, "error": f"eval-error: {e!r}"[:300], "kind": "eval"}
        try:
            json.dumps(res)
        except Exception:
            res = str(res)[:4000]
        return {"ok": True, "kind": "eval", "result": res}

    return {"ok": False, "error": f"unknown-type:{kind}"}


# ------------------------------------------------------------------- frames

# ---- escalating frame-capture recovery ladder (2026-10-03/04 freeze
#      postmortems). A wedged renderer fails every fresh conn identically
#      (cdp -32603), so "drop conn + retry next request" alone never
#      recovers — the freeze sat for 7 minutes before the ladder existed:
#        streak 1  -> fresh conn + bringToFront + immediate retry
#                     (most failures are a dropped socket on a LIVE page)
#        streak 2+ -> Page.reload under a RELOAD BUDGET (max 2/episode,
#                     >=15s apart; budget resets on success — the
#                     reload-storm bug: uncapped streak-2 reloads re-fired
#                     every 5s, pages never settled, streak wedge 15-22)
#        streak >=4 -> _switch_active_healthy(): re-point active_tab.txt at
#                     the first chat tab that captures cleanly (pick_tab
#                     only self-heals when an id VANISHES from /json/list;
#                     dead DevTools targets stay "listed")
#      On every failure the stale-serving cache (lesson 102) keeps the
#      operator's picture alive (bounded 30s) so the console overlay's age
#      readout tells the truth instead of an error gap.
_fail_streak = 0
_fail_lock = threading.Lock()
_reload_budget = {"used": 0, "last": 0.0}
_switch_last = 0.0
_switch_lock = threading.Lock()
RELOAD_MAX = 2          # reloads per failure episode
RELOAD_MIN_GAP = 15.0   # s between reloads (a reload needs time to settle)
SWITCH_COOLDOWN = 30.0  # s between healthy-tab walks


def _capture_jpeg(c):
    r = c.capture("Page.captureScreenshot", {"format": "jpeg", "quality": 72}, timeout=20)
    return base64.b64decode(r.get("data", "")) or None


def _serve_good(data):
    """Store the last-good frame and end the failure episode (streak AND
    reload budget reset on success — the anti-reload-storm law)."""
    global _last_good_frame, _last_good_ts, _fail_streak
    with _last_good_lock:
        _last_good_frame = data
        _last_good_ts = time.time()
    with _fail_lock:
        if _fail_streak:
            log(f"frame stream RECOVERED (streak {_fail_streak} ended)")  # snapshot under lock
            _fail_streak = 0
        _reload_budget["used"] = 0
    return data


def _reload_ok():
    """True iff a Page.reload may fire now: < RELOAD_MAX this episode and
    >= RELOAD_MIN_GAP since the last one. The budget is what turns the
    reload rung from a storm into a scalpel."""
    now = time.time()
    with _fail_lock:
        if _reload_budget["used"] >= RELOAD_MAX or now - _reload_budget["last"] < RELOAD_MIN_GAP:
            return False
        _reload_budget["used"] += 1
        _reload_budget["last"] = now
        return True


def _switch_active_healthy():
    """streak>=4 escalation: probe every chat tab with a REAL capture and
    re-point active_tab.txt (full id) at the first that returns image data.
    30s cooldown + non-blocking lock so concurrent /frame polls can never
    stampede the walk."""
    global _switch_last
    if not _switch_lock.acquire(blocking=False):
        return False   # another poller is already walking the tabs
    try:
        if time.time() - _switch_last < SWITCH_COOLDOWN:
            return False
        _switch_last = time.time()
        for t in channel.list_tabs():
            if "chat.z.ai" not in (t.get("url") or ""):
                continue
            c = None
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=6)
                r = c.call("Page.captureScreenshot",
                           {"format": "jpeg", "quality": 40}, timeout=6)
                if base64.b64decode(r.get("data", "")):
                    drop_conn(t["id"])   # never inherit a wedged conn entry
                    open(os.path.join(FLAGS, "active_tab.txt"), "w").write(t["id"])
                    log(f"ladder: active tab re-pointed to healthy {t['id'][:12]}…")
                    return True
            except Exception:
                continue
            finally:
                if c is not None:
                    c.close()
        log("ladder: no chat tab captures cleanly (all wedged?)")
        return False
    finally:
        _switch_lock.release()


def _recover_capture(tab, err):
    """Run the escalating ladder after a capture failure; returns a fresh
    frame if any rung recovered it (else None -> caller serves stale)."""
    with _fail_lock:
        _fail_streak += 1
        streak = _fail_streak           # race-free snapshot for the log line
    log(f"frame capture failed (streak {streak}: {err!r}) — ladder engaged")
    # rung 1: fresh conn + front + immediate retry (cheap, harmless at any
    # streak — the conn was just dropped, so this is a genuinely new socket)
    try:
        c = conn_for(tab)
        ensure_front(tab["id"], c, force=True)
        data = _capture_jpeg(c)
        if data:
            return _serve_good(data)
    except Exception as e:
        log(f"ladder rung 1 (fresh conn + front) failed: {e!r}")
    # rung 2: capped Page.reload, then retry on the settling page
    if streak >= 2 and _reload_ok():
        try:
            c = conn_for(tab)
            c.capture("Page.reload", {"ignoreCache": True}, timeout=15)
            time.sleep(1.0)              # let the reload commit before capture
            data = _capture_jpeg(c)
            if data:
                return _serve_good(data)
        except Exception as e:
            log(f"ladder rung 2 (capped reload) failed: {e!r}")
    # rung 3: healthy-tab re-point, then retry THERE
    if streak >= 4 and _switch_active_healthy():
        try:
            tab2 = pick_tab()
            if tab2 is not None and tab2.get("id") != tab.get("id"):
                data = _capture_jpeg(conn_for(tab2))
                if data:
                    return _serve_good(data)
        except Exception as e:
            log(f"ladder rung 3 (healthy-tab re-point) failed: {e!r}")
    return None


def handle_frame():
    tab = pick_tab()
    if not tab:
        return _stale_frame()
    err = None
    data = None
    try:
        data = _capture_jpeg(conn_for(tab))
        if not data:
            err = RuntimeError("capture returned no image data")
    except Exception as e:
        err = e
    if err is None:
        return _serve_good(data)
    drop_conn(tab["id"])
    _stats["errors"] += 1
    data = _recover_capture(tab, err)
    if data:
        return data
    return _stale_frame()


def _stale_frame():
    with _last_good_lock:
        if _last_good_frame and (time.time() - _last_good_ts) < 30:
            return _last_good_frame
    return None


def handle_tabs():
    tabs = channel.list_tabs()
    prune_conns(tabs)
    aid = active_tab_id()
    if aid and not any(t.get("id") == aid for t in tabs):
        aid = ""
    if not aid:
        t = pick_tab(tabs)
        aid = (t or {}).get("id", "")
    seen_path = os.path.join(FLAGS, "tabs_seen.json")
    fresh = []
    with _seen_lock:
        try:
            seen = set(json.loads(open(seen_path).read()))
        except Exception:
            seen = set()
        cur = {t["id"] for t in tabs}
        fresh = [t["id"] for t in tabs
                 if t["id"] not in seen and (t.get("url") or "") not in ("", "about:blank")]
        try:
            open(seen_path, "w").write(json.dumps(sorted(cur)))
        except Exception:
            pass
    return {
        "active": aid,
        "new": fresh,
        "tabs": [{"id": t["id"], "title": (t.get("title") or "")[:70],
                  "url": (t.get("url") or "")[:140]} for t in tabs],
    }


# --------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # request noise stays out of the log; errors are logged explicitly

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _jpeg(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/healthz":
                self._json({"ok": True, "uptime": round(time.time() - _started),
                            "stats": dict(_stats), "active": active_tab_id(),
                            "conns": len(_conns)})
            elif path == "/frame":
                data = handle_frame()
                if not data:
                    _stats["errors"] += 1
                    self._json({"ok": False, "error": "no-frame"}, 500)
                else:
                    _stats["frames"] += 1
                    self._jpeg(data)
            elif path == "/tabs":
                self._json(handle_tabs())
            else:
                self._json({"ok": False, "error": "not-found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            _stats["errors"] += 1
            log(f"GET {path} error {e!r}")
            try:
                self._json({"ok": False, "error": "internal"}, 500)
            except Exception:
                pass

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n > 0 else b"{}"
            payload = json.loads(body.decode() or "{}")
        except Exception:
            self._json({"ok": False, "error": "bad-json"}, 400)
            return
        try:
            if path == "/event":
                try:
                    out = handle_event(payload)
                    _stats["events"] += 1
                    self._json(out)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as e:
                    _stats["errors"] += 1
                    log(f"event {payload.get('type')} error {e!r}")
                    try:
                        self._json({"ok": False, "kind": payload.get("type"),
                                    "error": repr(e)[:200]})
                    except Exception:
                        pass
            elif path == "/tabs":
                tid = str(payload.get("id", ""))[:64]
                if tid:
                    try:
                        open(os.path.join(FLAGS, "active_tab.txt"), "w").write(tid)
                    except Exception:
                        pass
                    # front the newly selected tab NOW: the operator just
                    # switched to it in the console — input must not hit the
                    # hidden-tab throttle path (0.5-5s/event).
                    try:
                        tab = next((t for t in channel.list_tabs()
                                    if t.get("id") == tid), None)
                        if tab:
                            ensure_front(tid, conn_for(tab), force=True)
                    except Exception:
                        pass
                    self._json({"ok": True, "id": tid})
                else:
                    self._json({"ok": False, "error": "bad id"}, 400)
            else:
                self._json({"ok": False, "error": "not-found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log(f"POST {path} error {e!r}")


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    try:
        open(os.path.join(BASE, "replayd.pid"), "w").write(str(os.getpid()))
    except Exception:
        pass
    log(f"replayd online on :{PORT} (pid {os.getpid()})")
    print(f"replayd listening on {HOST}:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
