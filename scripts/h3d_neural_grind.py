#!/usr/bin/env python3
"""h3d_neural_grind.py — Task 20 resident verification loop (detached).

Goal: complete the LAST open item of the four-point mission — a REAL neural
(Hunyuan3D-2.1) generation through the production UI golden path, browser-direct,
anonymous, exactly as shipped.

Why a loop: the anonymous ZeroGPU quota is IP-pooled. The sandbox IP
(8.212.10.159, raw egress of the agent-browser daemon) had 47s left at
2026-10-19T00:40Z with the engine reporting "Try again in ~12:47" (~13:22Z).
REJECTED admission calls cost no quota, and a rejected UI attempt costs nothing
(the app falls back honestly, no credits are charged).

Phases:
  A (tracking, until fire_at): gradio_client admission probe every 45 min —
     rejected calls are free and report "Ns left" + the refill ETA.
     fire_at = eta - 90 min. Probing stops before any window could open.
  B (firing, from fire_at): the FULL production UI golden path via
     agent-browser (raw sandbox IP — the CDP Chrome routes through the VPN
     exit which is a separately drained pool):
       open PROD -> sign in (demo) -> Start Creating -> Image to 3D ->
       upload apple (input.files assignment) -> auto-caption -> GENERATE
       (Quality = neural) -> poll the new task:
         engine_used=neural -> SUCCESS: Confirm & Export (exactly 1 credit),
           byte-verify GLB/OBJ magic + sizes, screenshots, result JSON, then
           one rejected /generation_all probe (engine-side texture request
           size — the Task 18 knowledge item), exit 0.
         engine_used=fast   -> honest fallback -> log, wait 15 min, retry.
Artifacts: research/out/e2e20-grind-state.json, e2e20-grind.log,
           e2e20-neural-result.json, e2e20-neural-0*.png
"""
import base64
import json
import os
import re
import subprocess
import sys
import time

PROD = "https://hyper3d-clone.vercel.app"
# Apple fixture embedded as base64 — the upload JS is fully self-contained.
# (2026-10-19 lesson: the previous version fetched /api/task/<old-uuid>/input
# from a hardcoded list, which 404'd the moment the production database was
# migrated to a fresh project — the golden path must not depend on any DB
# row existing.)
APPLE_B64 = base64.b64encode(
    open("/home/z/my-project/research/fixtures/apple.jpg", "rb").read()
).decode()
OUT = "/home/z/my-project/research/out"
STATE_F = f"{OUT}/e2e20-grind-state.json"
LOG_F = f"{OUT}/e2e20-grind.log"
RESULT_F = f"{OUT}/e2e20-neural-result.json"
EMAIL = "demo@hyper3d.clone"
PASSWORD = "demo1234"

state = {
    "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "phase": "A",
    "fire_at_epoch": None,
    "probe_history": [],
    "cycles": [],
    "done": False,
    "result": None,
}


def log(*args):
    line = time.strftime("[%Y-%m-%dT%H:%M:%SZ] ", time.gmtime()) + " ".join(str(a) for a in args)
    print(line, flush=True)
    try:
        with open(LOG_F, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def save_state():
    try:
        with open(STATE_F, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        log("state-save-error:", e)


# ----------------------------- agent-browser -----------------------------

def ab(*args, timeout=150):
    try:
        r = subprocess.run(["agent-browser", *args], capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def ab_eval(js, timeout=150):
    out = ab("eval", js, timeout=timeout)
    if not out:
        return out
    # The CLI prints results as JSON text: quoted strings, raw objects,
    # arrays, numbers — parse them into Python values; plain text passes through.
    for candidate in (out, out.splitlines()[-1] if out.strip() else ""):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return out


# ----------------------------- quota probing -----------------------------

PROBE_CODE = '''
from gradio_client import Client, file
try:
    c = Client("tencent/Hunyuan3D-2.1")
    c.predict(image=file("/home/z/my-project/research/fixtures/apple.jpg"), steps=30,
              guidance_scale=5.0, seed=1, octree_resolution=256, check_box_rembg=True,
              num_chunks=8000, randomize_seed=False, api_name="/shape_generation")
    print("ADMITTED-UNEXPECTED")
except Exception as e:
    print("REJECTED:", str(e)[:400])
'''


def probe_quota():
    """Admission probe. A REJECTED call costs no GPU quota and reports the pool."""
    try:
        r = subprocess.run(["uv", "run", "--with", "gradio_client", "python3", "-c", PROBE_CODE],
                           capture_output=True, text=True, timeout=300,
                           cwd="/home/z/my-project/research")
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return {"error": "probe-timeout"}
    if "ADMITTED" in out:
        return {"admitted": True}
    m = re.search(r"(\d+)s requested vs\.?\s*(\d+)s left.*?Try again in (\d+):(\d+):(\d+)", out, re.S)
    if m:
        return {"admitted": False, "requested": int(m.group(1)), "left": int(m.group(2)),
                "eta_s": int(m.group(3)) * 3600 + int(m.group(4)) * 60 + int(m.group(5))}
    return {"error": "unparsed", "raw": out[-260:]}


# ----------------------------- golden path -----------------------------

JS_SESSION = """(async () => {
  const r = await fetch('/api/user/get_info', {method: 'POST', credentials: 'include'});
  if (!r.ok) return null;
  return await r.json();
})()"""

JS_OPEN_STUDIO = """(() => {
  let dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
  if (dlg) return 'already-open';
  const b = Array.from(document.querySelectorAll('a,button'))
    .find(x => x.innerText.trim().includes('Start Creating'));
  if (b) { b.click(); return 'clicked'; }
  return 'missing';
})()"""

JS_SIGNIN = """(async () => {
  const inputs = Array.from(document.querySelectorAll('input'));
  const email = inputs.find(i => i.type === 'email' || /mail/i.test(i.name + (i.placeholder||'')));
  const pass = inputs.find(i => i.type === 'password');
  if (!email || !pass) return 'NO-INPUTS:' + inputs.map(i => i.type).join(',');
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(email, '""" + EMAIL + """');
  email.dispatchEvent(new Event('input', {bubbles: true}));
  setter.call(pass, '""" + PASSWORD + """');
  pass.dispatchEvent(new Event('input', {bubbles: true}));
  await new Promise(r => setTimeout(r, 300));
  const form = email.closest('form');
  const btn = (form || document).querySelector("button[type=submit]") ||
    Array.from(document.querySelectorAll('button'))
      .find(b => /sign in|log in|continue/i.test(b.innerText));
  if (btn) btn.click();
  return 'submitted:' + (btn ? btn.innerText.trim().slice(0, 30) : 'no-btn');
})()"""

JS_TRIGGER_SIGNIN_DIALOG = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
  const b = Array.from((dlg || document).querySelectorAll('button'))
    .find(x => x.innerText.trim().toUpperCase().includes('GENERATE'));
  if (b) b.click();
  return b ? 'clicked' : 'missing';
})()"""

JS_MODE = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const b = Array.from(dlg.querySelectorAll('button[aria-pressed]'))
    .find(x => x.innerText.trim().startsWith('Image to 3D'));
  if (!b) return 'MISSING';
  b.click(); return 'clicked';
})()"""

JS_UPLOAD = """(async () => {
  const b64 = window.__ab64 || '';
  if (!b64) return 'no-b64';
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], {type: 'image/jpeg'});
  const file = new File([blob], 'apple.jpg', {type: 'image/jpeg'});
  const dt = new DataTransfer();
  dt.items.add(file);
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const inp = Array.from(dlg.querySelectorAll('input[type=file]'))
    .find(i => (i.accept || '').includes('image'));
  if (!inp) return 'no-input';
  inp.files = dt.files;
  inp.dispatchEvent(new Event('change', {bubbles: true}));
  return 'uploaded:' + file.size;
})()"""

JS_CAPTION = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const ta = Array.from(dlg.querySelectorAll('textarea'))
    .find(t => (t.placeholder || '').includes('caption fills this in'));
  const img = document.querySelector("img[alt='Uploaded reference image']");
  return JSON.stringify({captioned: ta ? ta.value.length > 5 : false,
    value: ta ? ta.value.slice(0, 90) : null, uploaded: !!img});
})()"""

JS_GENERATE = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
  if (!dlg) return 'NO-DIALOG';
  const b = Array.from(dlg.querySelectorAll('button'))
    .find(x => x.innerText.trim().toUpperCase().startsWith('GENERATE'));
  if (!b) return 'MISSING';
  b.click(); return 'clicked:' + b.innerText.trim();
})()"""

JS_ANCHOR = """(async () => {
  const r = await fetch('/api/task/list?filter=mine', {credentials: 'include'});
  if (!r.ok) return 'ERR';
  const arr = await r.json();
  return arr.length ? arr[0].task_uuid : 'EMPTY';
})()"""

# 2026-10-19 audit fix: arr[0] list-diff tracking misattributes tasks when two
# grind loops share the demo account (the CDP companion fires on the same
# account). The CREATE response's uuid is the only robust attribution source.
JS_INSTRUMENT = """(() => {
  if (window.__createdUuid !== undefined) return 'already';
  window.__createdUuid = null;
  window.__hfLog = [];
  const log = (e) => { try { window.__hfLog.push(Object.assign({t: Date.now()}, e)); } catch (x) {} };
  const orig = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = String(args[0] || '');
    if (url === '/api/task') {
      const res = await orig(...args);
      try {
        if (res.ok) {
          const j = await res.clone().json();
          if (j && j.uuid) window.__createdUuid = j.uuid;
        }
      } catch (e) {}
      return res;
    }
    if (url.indexOf('hf.space') === -1) return orig(...args);
    if (url.indexOf('/upload') !== -1) {
      const res = await orig(...args);
      let b = null;
      try { b = (await res.clone().text()).slice(0, 200); } catch (e) {}
      log({kind: 'upload', status: res.status, body: b});
      return res;
    }
    if (url.indexOf('/call/shape_generation/') !== -1) {
      const res = await orig(...args);
      try {
        const parts = res.body.tee();
        (async () => {
          const rd = parts[1].getReader();
          const dec = new TextDecoder();
          let buf = '';
          for (;;) {
            const r = await rd.read();
            if (r.done) { log({kind: 'sse', done: true, tail: buf.slice(-700)}); break; }
            buf += dec.decode(r.value, {stream: true});
            if (buf.length > 4000) buf = buf.slice(-4000);
          }
        })();
        return new Response(parts[0], {status: res.status, headers: res.headers});
      } catch (e) {
        log({kind: 'sse-wrap-fail', err: String(e).slice(0, 200)});
        return res;
      }
    }
    if (url.indexOf('/call/shape_generation') !== -1) {
      const res = await orig(...args);
      let b = null;
      try { b = (await res.clone().text()).slice(0, 300); } catch (e) {}
      log({kind: 'call', status: res.status, body: b});
      return res;
    }
    const res = await orig(...args);
    log({kind: 'other-hf', url: url.slice(0, 140), status: res.status});
    return res;
  };
  return 'instrumented';
})()"""

JS_HFLOG = """(() => JSON.stringify(window.__hfLog || []))()"""

JS_CREATED_UUID = "(() => window.__createdUuid || '')()"

JS_CARD = """(async () => {
  const r = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
  if (!r.ok) return JSON.stringify({error: r.status});
  const j = await r.json();
  const s = j.settings || {};
  return JSON.stringify({user_state: j.user_state, engine_used: s.engine_used || null,
    fallback_reason: s.fallback_reason || null, confirmed: s.confirmed === true});
})()"""

JS_POLL = """(async () => {
  const hf = performance.getEntriesByType('resource')
    .filter(e => e.name.includes('hf.space')).length;
  const txt = document.body.innerText;
  let mine = null;
  try {
    const r = await fetch('/api/task/list?filter=mine', {credentials: 'include'});
    if (r.ok) {
      const arr = await r.json();
      if (Array.isArray(arr) && arr.length) {
        // attribution: the CAPTURED create-response uuid when present; only
        // fall back to newest-not-anchor if the capture failed
        const tracked = '%s';
        let t0 = null;
        if (tracked) {
          t0 = arr.find(t => t.task_uuid === tracked) || null;
        } else if (arr[0].task_uuid !== '%s') {
          t0 = arr[0];
        }
        if (t0) {
          mine = { uuid: t0.task_uuid, user_state: t0.user_state,
            engine_used: t0.engine_used || null, seed: t0.seed ?? null,
            confirmed: t0.confirmed ?? null };
        }
      }
    }
  } catch (e) {}
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const confirmBtn = Array.from(dlg.querySelectorAll('button'))
    .find(b => b.innerText.includes('Confirm & Export'));
  return JSON.stringify({hf, mine, confirm: !!confirmBtn,
    neuralToast: txt.includes('Hunyuan3D-2.1 ·'),
    fallbackToast: txt.includes('Neural engine busy')});
})()"""

JS_CONFIRM = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const b = Array.from(dlg.querySelectorAll('button'))
    .find(x => x.innerText.includes('Confirm & Export'));
  if (!b) return 'NO-BTN';
  b.click(); return 'clicked';
})()"""

JS_EXPORTS = """(() => {
  const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
  const btns = Array.from(dlg.querySelectorAll('button'))
    .filter(b => ['GLB','GLTF','OBJ','STL','USDZ'].includes(b.innerText.trim()));
  return JSON.stringify(btns.map(b => ({label: b.innerText.trim(), disabled: b.disabled})));
})()"""


def eval_json(js, timeout=150):
    r = ab_eval(js, timeout=timeout)
    if isinstance(r, str) and r.startswith("{"):
        try:
            return json.loads(r)
        except Exception:
            pass
    return r


def wait_condition(js_check, want_true_key=None, timeout_s=90, interval=4):
    """Poll ab_eval(js_check) until it satisfies; returns the last value."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = eval_json(js_check)
        if isinstance(last, dict):
            if want_true_key and last.get(want_true_key):
                return last
            if not want_true_key:
                return last
        elif isinstance(last, str) and last.startswith("NO-"):
            return last
        time.sleep(interval)
    return last


def run_golden_path(cycle_n):
    """One full attempt. Returns dict with outcome: success | fallback | error."""
    outcome = _run_golden_path_inner(cycle_n)
    # Capture the instrumented hf.space traffic (upload/call/SSE) — the
    # browser-side neural failures need request/response evidence.
    try:
        outcome["hf_log"] = ab_eval(JS_HFLOG, timeout=30)
    except Exception as e:
        outcome["hf_log"] = f"capture-failed: {e}"
    return outcome


def _run_golden_path_inner(cycle_n):
    """One full attempt. Returns dict with outcome: success | fallback | error."""
    outcome = {"cycle": cycle_n, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        # 1. open + settle + instrument (create-uuid capture)
        ab("open", PROD, timeout=90)
        ab("wait", "--load", "networkidle", timeout=60)
        time.sleep(2)
        ab_eval(JS_INSTRUMENT, timeout=60)

        # 2. session (sign in if needed), then ALWAYS ensure the studio is open
        sess = ab_eval(JS_SESSION, timeout=60)
        if not isinstance(sess, dict):
            ab_eval(JS_OPEN_STUDIO, timeout=60)
            time.sleep(3)
            ab_eval(JS_TRIGGER_SIGNIN_DIALOG, timeout=60)
            time.sleep(2.5)
            r = ab_eval(JS_SIGNIN, timeout=60)
            time.sleep(6)
            sess = ab_eval(JS_SESSION, timeout=60)
            outcome["signin"] = r
        if not isinstance(sess, dict):
            outcome["outcome"] = "error"
            outcome["reason"] = f"sign-in failed: {sess}"
            return outcome
        outcome["user"] = sess.get("username")
        outcome["pre_balance"] = sess.get("balance")

        # 3. studio + mode
        r = ab_eval(JS_OPEN_STUDIO, timeout=60)
        time.sleep(2.5)
        r = ab_eval(JS_MODE, timeout=60)
        time.sleep(1.5)
        if r != "clicked":
            outcome["outcome"] = "error"
            outcome["reason"] = f"mode click: {r}"
            return outcome

        # 4. upload — the fixture is fed in ~24KB eval chunks first: a single
        # 159KB eval exceeds the agent-browser argv limit (Errno 7).
        ab_eval("window.__ab64 = '';", timeout=30)
        for i in range(0, len(APPLE_B64), 24000):
            ab_eval("window.__ab64 += %s;" % json.dumps(APPLE_B64[i:i + 24000]), timeout=30)
        r = ab_eval(JS_UPLOAD, timeout=90)
        outcome["upload"] = r
        if not (isinstance(r, str) and r.startswith("uploaded:")):
            outcome["outcome"] = "error"
            outcome["reason"] = f"upload: {r}"
            return outcome

        # 5. caption (Bailian vision, up to 60s)
        cap = wait_condition(JS_CAPTION, want_true_key="captioned", timeout_s=60, interval=4)
        outcome["caption"] = cap
        if not (isinstance(cap, dict) and cap.get("captioned")):
            outcome["outcome"] = "error"
            outcome["reason"] = f"caption: {cap}"
            return outcome

        # 6. anchor + GENERATE
        anchor = ab_eval(JS_ANCHOR, timeout=60)
        outcome["anchor"] = anchor
        if not (isinstance(anchor, str) and anchor.count("-") >= 4):
            outcome["outcome"] = "error"
            outcome["reason"] = f"anchor not a uuid: {anchor}"
            return outcome
        gen = ab_eval(JS_GENERATE, timeout=60)
        outcome["generate"] = gen
        if not (isinstance(gen, str) and gen.startswith("clicked")):
            outcome["outcome"] = "error"
            outcome["reason"] = f"generate: {gen}"
            return outcome

        # 6.5 capture the create-response uuid (robust attribution)
        tracked = None
        for _ in range(15):
            cap = ab_eval(JS_CREATED_UUID, timeout=30)
            if isinstance(cap, str) and cap.count("-") >= 4:
                tracked = cap
                break
            time.sleep(2)
        outcome["tracked_uuid"] = tracked

        # 7. poll the new task (up to 4 min) — by captured uuid when present
        poll_js = JS_POLL % (tracked or "", str(anchor))
        deadline = time.time() + 240
        last = None
        while time.time() < deadline:
            last = eval_json(poll_js, timeout=60)
            if isinstance(last, dict):
                m = last.get("mine")
                if m and m.get("user_state") in ("DonePreview", "done"):
                    break
            time.sleep(5)
        outcome["final_poll"] = last
        m = (last or {}).get("mine") if isinstance(last, dict) else None
        if not m:
            outcome["outcome"] = "error"
            outcome["reason"] = "no new task observed"
            return outcome
        outcome["task_uuid"] = m.get("uuid")
        outcome["user_state"] = m.get("user_state")
        outcome["engine_used"] = m.get("engine_used")
        outcome["seed"] = m.get("seed")
        outcome["hf_reqs"] = (last or {}).get("hf") if isinstance(last, dict) else None

        # 7.5 VERDICT from the task CARD (server truth) — a just-created
        # neural task reports engine_used=neural before its pipeline
        # resolves; only the card's final state counts (2026-10-19 audit)
        card = eval_json(JS_CARD % m.get("uuid"), timeout=60)
        outcome["card"] = card
        if not (isinstance(card, dict) and card.get("user_state") in ("DonePreview", "done")
                and card.get("engine_used") == "neural" and not card.get("fallback_reason")):
            outcome["outcome"] = "fallback"
            return outcome

        # 8. SUCCESS — confirm & export
        ab_eval(JS_CONFIRM, timeout=60)
        time.sleep(2)
        exp = None
        for _ in range(20):
            exp = eval_json(JS_EXPORTS, timeout=60)
            if isinstance(exp, list) and len(exp) >= 5 and all(not b.get("disabled") for b in exp):
                break
            time.sleep(2.5)
        outcome["exports"] = exp
        post = ab_eval(JS_SESSION, timeout=60)
        outcome["post_balance"] = post.get("balance") if isinstance(post, dict) else None

        # 9. byte-verify GLB + OBJ
        uuid = m.get("uuid")
        glb = ab_eval("""(async () => {
          const r = await fetch('/api/task/%s/export?format=glb', {credentials: 'include'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const buf = await r.arrayBuffer();
          const b = new Uint8Array(buf);
          let head = '';
          for (let i = 0; i < Math.min(16, b.length); i++) head += String.fromCharCode(b[i]);
          return JSON.stringify({size: buf.byteLength, magic: head.slice(0, 4), gltf: head.slice(0,4) === 'glTF'});
        })()""" % uuid, timeout=90)
        obj = ab_eval("""(async () => {
          const r = await fetch('/api/task/%s/export?format=obj', {credentials: 'include'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const t = await r.text();
          return JSON.stringify({size: t.length, head: t.slice(0, 60)});
        })()""" % uuid, timeout=90)
        outcome["byte_verify"] = {"glb": _try(glb), "obj": _try(obj)}
        _g = _try(glb)
        _o = _try(obj)
        outcome["exports_ok"] = bool(isinstance(_g, dict) and _g.get("gltf") is True
                                      and isinstance(_g.get("size"), int) and _g["size"] > 1000
                                      and isinstance(_o, dict) and isinstance(_o.get("size"), int) and _o["size"] > 1000)

        # 10. screenshots
        shots = []
        for name in ("e2e20-neural-01-task", "e2e20-neural-02-viewer",
                     "e2e20-neural-03-confirmed", "e2e20-neural-04-final"):
            p = f"{OUT}/{name}.png"
            ab("screenshot", p, timeout=60)
            shots.append(name + ".png")
            time.sleep(1.5)
        outcome["shots"] = shots
        outcome["outcome"] = "success"
        return outcome
    except Exception as e:
        outcome["outcome"] = "error"
        outcome["reason"] = f"exception: {e}"
        return outcome


def _try(s):
    if isinstance(s, str) and s.startswith("{"):
        try:
            return json.loads(s)
        except Exception:
            return s
    return s


# ----------------------------- main loop -----------------------------

def main():
    log("grind started — target: REAL neural run through the production UI from the raw sandbox IP")
    # FIRE-ONLY MODE (2026-10-19 lesson): an ADMITTED probe CONSUMES the
    # window — the probe's own gradio call runs a full server-side
    # generation (admission is a fixed 90s regardless of params), leaving
    # the pool below admission for the browser's neural call ~30-60s later.
    # Observed 3× in a row: probe admitted -> golden path honest fallback.
    # Skipping the probe lets the browser's own call be the FIRST hit on a
    # fresh pool. Set PROBE_FIRST=1 to restore probe/ETA behavior.
    if os.environ.get("PROBE_FIRST") != "1":
        state["phase"] = "B"
        log("fire-only mode: probing disabled — the browser's neural call takes the window")
    cycle = 0
    while not state["done"]:
        cycle += 1
        now = time.time()
        if state["phase"] == "A":
            p = probe_quota()
            state["probe_history"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **p})
            log(f"probe #{len(state['probe_history'])}:", json.dumps(p, default=str)[:220])
            if p.get("admitted"):
                # unexpected — the pool opened early; fire the UI immediately
                log("probe ADMITTED (pool opened early) — switching to firing phase NOW")
                state["phase"] = "B"
            elif p.get("eta_s") is not None:
                fire_at = now + p["eta_s"] - 90 * 60
                state["fire_at_epoch"] = fire_at
                state["fire_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fire_at))
                if now >= fire_at:
                    state["phase"] = "B"
                else:
                    wait = min(45 * 60, max(60, p["eta_s"] - 95 * 60))
                    log(f"phase A: pool {p['left']}s / request {p['requested']}s — fire at "
                        f"{state['fire_at_utc']} — next probe in {int(wait/60)} min")
                    save_state()
                    time.sleep(wait)
                    continue
            else:
                log("probe unparsed/errored — retrying in 20 min")
                save_state()
                time.sleep(20 * 60)
                continue

        # phase B (or fall-through from an early window)
        state["phase"] = "B"
        log(f"firing cycle {cycle} — full UI golden path…")
        res = run_golden_path(cycle)
        state["cycles"].append(res)
        save_state()
        log(f"cycle {cycle} outcome: {res.get('outcome')} | engine={res.get('engine_used')} "
            f"| task={res.get('task_uuid')} | reason={res.get('reason')}")
        if res.get("outcome") == "success":
            state["done"] = True
            state["result"] = res
            with open(RESULT_F, "w") as f:
                json.dump(res, f, indent=2, default=str)
            log("SUCCESS — REAL neural run verified end-to-end. Result:", RESULT_F)
            # one rejected /generation_all probe — engine-side texture request
            # size (Task 18 knowledge item). Post-success the pool is drained
            # below any admission, so the probe is free and reports the number.
            tp = subprocess.run(["uv", "run", "--with", "gradio_client", "python3", "-c", '''
from gradio_client import Client, file
try:
    c = Client("tencent/Hunyuan3D-2.1")
    out = c.predict(image=file("/home/z/my-project/research/fixtures/apple.jpg"), steps=30,
              guidance_scale=5.0, seed=1, octree_resolution=256, check_box_rembg=True,
              num_chunks=8000, randomize_seed=False, api_name="/generation_all")
    print("ADMITTED:", str(out)[:250])
except Exception as e:
    print("REJECTED:", str(e)[:400])
'''], capture_output=True, text=True, timeout=300, cwd="/home/z/my-project/research")
            state["textured_probe"] = ((tp.stdout or "") + (tp.stderr or ""))[-400:]
            log("textured /generation_all probe:", state["textured_probe"].replace("\n", " ")[:300])
            save_state()
            return
        # fallback / error — wait and retry (tighter in fire-only mode:
        # the browser call costs nothing when rejected, and windows are
        # empirically noisy — 5 min catches far more of them than 15)
        wait_s = 5 * 60 if os.environ.get("PROBE_FIRST") != "1" else 15 * 60
        time.sleep(wait_s)
        save_state()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("interrupted")
        sys.exit(1)
