#!/usr/bin/env python3
"""h3d_prod_neural_e2e.py — Task 20: post-refill REAL neural-run verification
on PRODUCTION (hyper3d-clone.vercel.app) through the VPN-egress Chrome
(CDP :9222, egress 198.244.234.214 — its own anonymous ZeroGPU pool, separate
from the drained raw sandbox IP).

Golden path: landing → sign in (demo) → studio → Image to 3D → upload apple →
auto-caption → GENERATE Free Preview (Quality = neural Hunyuan3D-2.1) → REAL
neural mesh (assert NO fallback) → viewer → Confirm & Export (exactly 1
credit) → byte-verified GLB + OBJ.

Artifacts: /home/z/my-project/research/out/e2e20-*.png + e2e20-result.json
"""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs, new_tab  # noqa: E402

PROD = "https://hyper3d-clone.vercel.app"
IMG = "/home/z/my-project/research/fixtures/apple.jpg"
OUT = "/home/z/my-project/research/out"
EMAIL = "demo@hyper3d.clone"
PASSWORD = "demo1234"

result = {
    "url": PROD,
    "chrome_egress": "198.244.234.214",
    "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "phases": {},
    "ok": False,
}


def shot(ws, name):
    r = ws.call("Page.captureScreenshot", {"format": "png"}, timeout=40)
    path = f"{OUT}/{name}.png"
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print(f"  [shot] {name}.png", flush=True)
    result["phases"].setdefault("shots", []).append(f"{name}.png")


def js(ws, expr, t=45):
    return ws.eval(expr, await_promise=True, timeout=t)


def get_user(ws):
    """POST /api/user/get_info (POST-only route) -> dict|None."""
    r = js(ws, """(async () => {
      const r = await fetch('/api/user/get_info', {method: 'POST', credentials: 'include'});
      if (!r.ok) return null;
      return await r.json();
    })()""")
    if isinstance(r, dict):
        return r
    if isinstance(r, str) and r.strip().startswith("{"):
        return json.loads(r)
    return None


def task_uuid_probe(obs):
    return obs.get("task_uuid")


def phase(name, data):
    result["phases"][name] = data
    print(f"[phase] {name}: {json.dumps(data, default=str)[:400]}", flush=True)


def upload_file(ws, path):
    """DOM.setFileInputFiles on the first image-accepting file input."""
    ws.call("DOM.enable", timeout=10)
    doc = ws.call("DOM.getDocument", {"depth": -1, "pierce": True}, timeout=30)
    root = doc["root"]["nodeId"]
    qr = ws.call("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file]"}, timeout=30)
    nodes = qr["nodeIds"]
    chosen = None
    for nid in nodes:
        ar = ws.call("DOM.getAttributes", {"nodeId": nid}, timeout=15)
        attrs = dict(zip(ar["attributes"][::2], ar["attributes"][1::2]))
        acc = attrs.get("accept", "")
        if "image" in acc or ".png" in acc or ".jpg" in acc or ".webp" in acc:
            chosen = nid
            break
    if chosen is None and nodes:
        chosen = nodes[0]
    if chosen is None:
        raise RuntimeError("no file input found")
    ws.call("DOM.setFileInputFiles", {"files": [path], "nodeId": chosen}, timeout=30)
    return chosen


def main():
    # ---------- 0. tab ----------
    tab = None
    for t in list_tabs():
        if "hyper3d-clone.vercel.app" in (t.get("url") or ""):
            tab = t
            break
    if tab is None:
        tab = new_tab(PROD)
    if tab is None:
        raise SystemExit("could not open production tab")
    ws = CDP(tab["webSocketDebuggerUrl"], timeout=20)
    # fresh deterministic state (prior runs may have left dialogs/studio open)
    ws.call("Page.reload", timeout=15)
    for _ in range(25):
        try:
            if js(ws, "document.readyState", t=8) == "complete":
                break
        except Exception:
            pass
        time.sleep(1)
    time.sleep(3)

    # ---------- 1b. instrument fetch: log hf.space traffic + confirm/export API
    # responses + CAPTURE the create-task response uuid (the 2026-10-19 audit
    # showed arr[0] list-diff tracking misattributes tasks when two grind
    # loops share the demo account — the create response is the only robust
    # attribution source). ----------
    js(ws, """(() => {
      if (window.__hfLog) return 'already';
      window.__hfLog = [];
      window.__createdUuid = null;
      const orig = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const url = String(args[0] || '');
        const isHf = url.includes('hf.space');
        const isCreate = url === '/api/task';
        const isApi = /\\/api\\/task\\/.*(confirm|fallback|mesh|export)/.test(url);
        if (!isHf && !isApi && !isCreate) return orig(...args);
        const entry = {url: url.slice(0, 160), t: Date.now(), status: null, body: null, chunks: []};
        window.__hfLog.push(entry);
        try {
          const res = await orig(...args);
          entry.status = res.status;
          if (isCreate && res.ok) {
            try { const j = await res.clone().json(); if (j && j.uuid) window.__createdUuid = j.uuid; } catch (e) {}
          }
          if (isHf && res.body && (res.headers.get('content-type') || '').includes('event-stream')) {
            // tee the SSE stream: one branch feeds the page, one feeds our log
            const [a, b] = res.body.tee();
            const dec = new TextDecoder();
            const rd = b.getReader();
            (async () => {
              try {
                for (;;) {
                  const {done, value} = await rd.read();
                  if (done) break;
                  const txt = dec.decode(value, {stream: true});
                  if (entry.chunks.length < 40) entry.chunks.push(txt.slice(0, 800));
                }
              } catch (e) {}
            })();
            return new Response(a, {status: res.status, statusText: res.statusText, headers: res.headers});
          }
          if (isApi || isCreate || (isHf && !res.ok)) {
            try { entry.body = (await res.clone().text()).slice(0, 600); } catch (e) {}
          }
          return res;
        } catch (e) {
          entry.status = 'fetch-error';
          entry.body = String(e).slice(0, 300);
          throw e;
        }
      };
      return 'instrumented';
    })()""")
    landing = js(ws, """JSON.stringify({
      title: document.title.slice(0, 60),
      startCreating: !!Array.from(document.querySelectorAll('a,button'))
        .find(x => x.innerText.trim().includes('Start Creating')),
      body: document.body.innerText.slice(0, 120)
    })""")
    phase("landing", json.loads(landing))
    shot(ws, "e2e20-01-landing")

    # ---------- 2. sign in (idempotent: cookie may already be set) ----------
    user = get_user(ws)
    if user:
        phase("signin", {"already": True, "user": user.get("username"), "balance": user.get("balance")})
        js(ws, """(() => {
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim().includes('Start Creating'));
          if (b) b.click(); return b ? 'clicked' : 'missing';
        })()""")
        time.sleep(3)
    else:
        js(ws, """(() => {
          const b = Array.from(document.querySelectorAll('a,button'))
            .find(x => x.innerText.trim().includes('Start Creating'));
          if (b) b.click(); return b ? 'clicked' : 'missing';
        })()""")
        time.sleep(3)
        # GENERATE while unauthenticated -> sign-in dialog
        js(ws, """(() => {
          const b = Array.from(document.querySelectorAll('button'))
            .find(x => x.innerText.trim().toUpperCase().includes('GENERATE'));
          if (b) b.click(); return b ? 'clicked' : 'missing';
        })()""")
        time.sleep(2.5)
        r = js(ws, """(async () => {
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
    })()""")
        time.sleep(6)
        user = get_user(ws)
        phase("signin", {"submit": r, "user": (user or {}).get("username"),
                          "balance": (user or {}).get("balance"), "ok": bool(user)})
        if not user:
            shot(ws, "e2e20-02-signin-FAILED")
            raise SystemExit("sign-in failed")
    shot(ws, "e2e20-02-signed-in")

    # ---------- 3. Image to 3D mode (sidebar button[aria-pressed], not landing tabs) ----------
    r = js(ws, """(() => {
      const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
      const b = Array.from(dlg.querySelectorAll('button[aria-pressed]'))
        .find(x => x.innerText.trim().startsWith('Image to 3D'));
      if (!b) return 'MISSING';
      b.click(); return 'clicked';
    })()""")
    time.sleep(1.5)
    mode_state = js(ws, """(() => {
      const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
      const b = Array.from(dlg.querySelectorAll('button[aria-pressed]'))
        .find(x => x.innerText.trim().startsWith('Image to 3D'));
      const fileInputs = Array.from(document.querySelectorAll('input[type=file]')).length;
      return JSON.stringify({
        pressed: b ? b.getAttribute('aria-pressed') : null,
        hint: b ? b.innerText.slice(0, 60) : null,
        dropzone: document.body.innerText.includes('Drop an image'),
        fileInputs
      });
    })()""")
    phase("mode", {"image_tab": r, "state": json.loads(mode_state or "{}")})

    # ---------- 4. upload + caption ----------
    try:
        nid = upload_file(ws, IMG)
        phase("upload", {"nodeId": nid, "file": IMG})
    except Exception as e:
        phase("upload", {"error": str(e)})
        raise
    cap = None
    deadline = time.time() + 45
    while time.time() < deadline:
        cap = js(ws, """(() => {
          const ta = Array.from(document.querySelectorAll('textarea'))
            .find(t => (t.placeholder || '').includes('caption fills this in'));
          const img = document.querySelector("img[alt='Uploaded reference image']");
          return JSON.stringify({
            captioned: ta ? ta.value.length > 5 : false,
            value: ta ? ta.value.slice(0, 140) : null,
            uploaded: !!img
          });
        })()""")
        d = json.loads(cap)
        if d.get("captioned"):
            break
        time.sleep(3)
    phase("caption", json.loads(cap or "{}"))
    shot(ws, "e2e20-03-uploaded-captioned")

    # ---------- 5. pre-generate state: tier + balance ----------
    pre_user = get_user(ws)
    pre = js(ws, """(() => {
      const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
      if (!dlg) return JSON.stringify({error: 'no-studio-dialog'});
      const gen = Array.from(dlg.querySelectorAll('button'))
        .find(x => x.innerText.trim().toUpperCase().startsWith('GENERATE'));
      const radios = Array.from(dlg.querySelectorAll("[role=radiogroup][aria-label='Engine tier'] button[role=radio]"))
        .map(b => ({label: b.innerText.trim().split('\\n')[0], checked: b.getAttribute('aria-checked')}));
      return JSON.stringify({generateLabel: gen ? gen.innerText.trim() : null,
        generateDisabled: gen ? gen.disabled : null, tierRadios: radios});
    })()""")
    pre_d = json.loads(pre or "{}")
    pre_d["balance"] = (pre_user or {}).get("balance")
    phase("pre_generate", pre_d)
    if not pre_d.get("generateLabel"):
        raise SystemExit("studio GENERATE button not found")

    # ---------- 6. GENERATE (Quality = neural) — studio-scoped ----------
    t_start = time.time()
    gen_click = js(ws, """(() => {
      const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']");
      if (!dlg) return 'NO-DIALOG';
      const b = Array.from(dlg.querySelectorAll('button'))
        .find(x => x.innerText.trim().toUpperCase().startsWith('GENERATE'));
      if (!b) return 'MISSING';
      b.click(); return 'clicked:' + b.innerText.trim();
    })()""")
    phase("generate_click", {"result": gen_click, "at": round(time.time() - t_start, 1)})
    print("[gen] clicked", gen_click, "— polling neural pipeline…", flush=True)

    # anchor: newest task BEFORE generate (fallback attribution only —
    # primary attribution is the CAPTURED create-response uuid)
    pre_task = js(ws, """(async () => {
      const r = await fetch('/api/task/list?filter=mine', {credentials: 'include'});
      if (!r.ok) return 'ERR';
      const arr = await r.json();
      return arr.length ? JSON.stringify({uuid: arr[0].task_uuid, time: arr[0].time}) : 'EMPTY';
    })()""")
    pre_task_uuid = None
    if pre_task and pre_task.startswith("{"):
        pre_task_uuid = json.loads(pre_task).get("uuid")

    # capture the create-response uuid (robust attribution — see audit)
    tracked_uuid = None
    for _ in range(15):
        cap = js(ws, "(() => window.__createdUuid || '')()", t=10)
        if cap:
            tracked_uuid = cap
            break
        time.sleep(2)
    phase("task_attribution", {"captured_create_uuid": tracked_uuid,
                              "anchor_newest_before": pre_task_uuid,
                              "attribution": "create-response" if tracked_uuid else "anchor-diff-fallback"})

    observations = {"hf_space_reqs": [], "engine_used": None, "fallback_reason": None,
                    "seed": None, "user_state": None, "task_uuid": None, "neural_toast_at": None,
                    "fallback_toast_at": None, "confirm_btn_at": None}
    poll_deadline = time.time() + 360
    last_dump = ""
    while time.time() < poll_deadline:
        try:
            st = js(ws, """(async () => {
              const hf = performance.getEntriesByType('resource')
                .filter(e => e.name.includes('hf.space')).length;
              const txt = document.body.innerText;
              let mine = null;
              try {
                const r = await fetch('/api/task/list?filter=mine', {credentials: 'include'});
                if (r.ok) {
                  const arr = await r.json();
                  if (Array.isArray(arr) && arr.length) {
                    // track by the CAPTURED create uuid when present; only
                    // fall back to newest-not-anchor when capture failed
                    const t0 = '%s'
                      ? arr.find(t => t.task_uuid === '%s')
                      : (arr[0].task_uuid !== '%s' ? arr[0] : null);
                    if (t0) {
                      mine = { uuid: t0.task_uuid, user_state: t0.user_state,
                        engine_used: t0.engine_used || null, seed: t0.seed ?? null,
                        confirmed: t0.confirmed ?? null, time: t0.time };
                    }
                  }
                }
              } catch (e) {}
              const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
              const confirmBtn = Array.from(dlg.querySelectorAll('button'))
                .find(b => b.innerText.includes('Confirm & Export'));
              return JSON.stringify({
                hf, mine, confirm: !!confirmBtn,
                neuralToast: txt.includes('Hunyuan3D-2.1 ·'),
                fallbackToast: txt.includes('Neural engine busy'),
                elapsed: Math.round((Date.now() - %d) / 1000)
              });
            })()""" % (str(tracked_uuid or ""), str(tracked_uuid or ""), str(pre_task_uuid), int(t_start * 1000)), t=30)
        except Exception as e:
            print(f"  [poll-error] {e}", flush=True)
            time.sleep(5)
            continue
        d = json.loads(st)
        observations["hf_space_reqs"].append(d.get("hf"))
        if d.get("mine"):
            m = d["mine"]
            observations["task_uuid"] = m["uuid"]
            observations["user_state"] = m["user_state"]
            if m["engine_used"]:
                observations["engine_used"] = m["engine_used"]
            if m["seed"] is not None:
                observations["seed"] = m["seed"]
        if d.get("neuralToast") and not observations["neural_toast_at"]:
            observations["neural_toast_at"] = round(time.time() - t_start, 1)
        if d.get("fallbackToast") and not observations["fallback_toast_at"]:
            observations["fallback_toast_at"] = round(time.time() - t_start, 1)
        if d.get("confirm") and not observations["confirm_btn_at"]:
            observations["confirm_btn_at"] = round(time.time() - t_start, 1)
        dump = json.dumps(d, default=str)
        if dump != last_dump:
            print(f"  [{d.get('elapsed')}s] {dump[:280]}", flush=True)
            last_dump = dump
        m = d.get("mine")
        done = m and m.get("user_state") in ("DonePreview", "done") and \
            (d.get("confirm") or m.get("engine_used"))
        if done or (d.get("neuralToast") and d.get("confirm")):
            break
        time.sleep(4)

    observations["total_s"] = round(time.time() - t_start, 1)
    phase("generation", observations)
    shot(ws, "e2e20-04-task-result")

    # VERDICT from the tracked task's CARD (server truth), not the poll's
    # last engine_used snapshot: a just-created neural task reports
    # engine_used=neural before its pipeline resolves — the false-positive
    # mechanism of 2026-10-19 02:45Z.
    verdict_card = None
    verdict_uuid = observations.get("task_uuid") or tracked_uuid
    if verdict_uuid:
        vc = js(ws, """(async () => {
          const r = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const j = await r.json();
          const s = j.settings || {};
          return JSON.stringify({user_state: j.user_state,
            engine_used: s.engine_used || null,
            fallback_reason: s.fallback_reason || null,
            confirmed: s.confirmed === true});
        })()""" % verdict_uuid, t=30)
        try:
            verdict_card = json.loads(vc)
        except Exception:
            verdict_card = {"raw": str(vc)[:200]}
    phase("verdict_card", verdict_card)
    neural_ok = bool(verdict_card and
                     verdict_card.get("user_state") in ("DonePreview", "done") and
                     verdict_card.get("engine_used") == "neural" and
                     not verdict_card.get("fallback_reason"))
    result["neural"] = neural_ok
    result["verdict_source"] = "card:%s" % verdict_uuid

    # ---------- 7. viewer + poster shot ----------
    time.sleep(2)
    shot(ws, "e2e20-05-viewer")

    # ---------- 8. Confirm & Export (studio-scoped, patient) ----------
    confirm_res = js(ws, """(async () => {
          const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
          const b = Array.from(dlg.querySelectorAll('button'))
            .find(x => x.innerText.includes('Confirm & Export'));
          if (!b) return 'NO-BTN';
          b.click();
          return 'clicked';
        })()""")
    # poll for the confirmed state: exports enabled + card confirmed + balance drop
    exp = None
    confirmed_card = None
    for _ in range(22):
        exp = js(ws, """(() => {
          const dlg = document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']") || document;
          const btns = Array.from(dlg.querySelectorAll('button'))
            .filter(b => ['GLB','GLTF','OBJ','STL','USDZ'].includes(b.innerText.trim()));
          return JSON.stringify(btns.map(b => ({label: b.innerText.trim(), disabled: b.disabled})));
        })()""")
        d = json.loads(exp or "[]")
        if d and all(not b["disabled"] for b in d) and len(d) >= 5:
            break
        time.sleep(2)
    if task_uuid_probe(observations):
        confirmed_card = js(ws, """(async () => {
          const r = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const j = await r.json();
          const s = j.settings || {};
          return JSON.stringify({user_state: j.user_state, confirmed: s.confirmed === true,
            engine_used: s.engine_used, fallback_reason: s.fallback_reason || null});
        })()""" % observations["task_uuid"], t=30)
    post_user = get_user(ws)
    phase("confirm", {"click": confirm_res, "exports": json.loads(exp or "[]"),
                      "card": json.loads(confirmed_card or "{}"),
                      "post_balance": (post_user or {}).get("balance")})
    shot(ws, "e2e20-06-confirmed-exports")

    # ---------- 9. byte-verify exports ----------
    task_uuid = observations.get("task_uuid")
    if task_uuid:
        glb = js(ws, """(async () => {
          const r = await fetch('/api/task/%s/export?format=glb', {credentials: 'include'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const buf = await r.arrayBuffer();
          const b = new Uint8Array(buf);
          let head = '';
          for (let i = 0; i < Math.min(16, b.length); i++) head += String.fromCharCode(b[i]);
          return JSON.stringify({size: buf.byteLength, magic: head.slice(0, 4),
            head: head, gltf: head.slice(0,4) === 'glTF'});
        })()""" % task_uuid, t=60)
        obj = js(ws, """(async () => {
          const r = await fetch('/api/task/%s/export?format=obj', {credentials: 'include'});
          if (!r.ok) return JSON.stringify({error: r.status});
          const t = await r.text();
          return JSON.stringify({size: t.length, head: t.slice(0, 60).replaceAll('\\n',' | ')});
        })()""" % task_uuid, t=60)
        glb_d = json.loads(glb or "{}")
        obj_d = json.loads(obj or "{}")
        phase("byte_verify", {"glb": glb_d, "obj": obj_d})
        # HONEST gate: only byte-verified when the GLB carries the glTF magic
        # AND the OBJ is a real mesh (>1KB) — the 2026-10-19 false positive
        # had this flag True over two 402s.
        result["exports_byte_verified"] = bool(
            glb_d.get("gltf") is True and isinstance(glb_d.get("size"), int) and glb_d["size"] > 1000
            and isinstance(obj_d.get("size"), int) and obj_d["size"] > 1000)

    shot(ws, "e2e20-07-final")
    # ---------- 10. dump the instrumented network log (verbatim engine errors) ----------
    hf_log = js(ws, """(() => JSON.stringify(window.__hfLog || []) )()""", t=30)
    try:
        log = json.loads(hf_log or "[]")
        phase("hf_log", log)
        with open(f"{OUT}/e2e20-hf-log.json", "w") as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        phase("hf_log", {"parse_error": str(e), "raw": (hf_log or "")[:500]})
    result["ok"] = bool(neural_ok and task_uuid)
    result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(f"{OUT}/e2e20-result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("RESULT neural:", neural_ok, "| task:", task_uuid, flush=True)
    print(json.dumps(result["phases"].get("generation", {}), indent=1, default=str), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        result["fatal"] = str(e)
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(f"{OUT}/e2e20-result.json", "w") as f:
            json.dump(result, f, indent=2, default=str)
        raise
