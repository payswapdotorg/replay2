#!/usr/bin/env python3
"""dispatch_worker.py — create chat.z.ai AGENT worker sessions via the browser (replay).

OPERATOR DIRECTIVE (2026-09-08): worker sessions MUST be created in the AGENTS tab,
with model GLM-5.3 and skill Full-Stack. Sessions started in the chat tab are NULL
AND VOID — they never count as real sessions or real work.

Usage:
  dispatch_worker.py create <name> <prompt_file>   -> agents-tab session, send prompt
  dispatch_worker.py check <name>                  -> session state (text tail)
  dispatch_worker.py list                          -> registered sessions
  dispatch_worker.py void <name> <reason>          -> mark a session void + close tab
  dispatch_worker.py models                        -> inspect model selector options
  dispatch_worker.py sandboxes [url-substr]        -> inspect + release idle sandboxes

Sandbox concurrency (operator rule): when the 'Limit Sandbox Concurrency' modal
blocks, dispatch_worker releases sandboxes that have NO active job (registry
truth: live sessions + their WO keywords are kept; idle/stale holders are
released). This runs automatically inside create() (pre-send + post-send) and
on demand via the sandboxes command.

create flow (each step verified, hard-fails if any selection does not stick):
  1. new browser tab -> https://chat.z.ai/
  2. click the sidebar "Agent" nav  -> verify agent mode ("New Task" marker)
  3. open model selector -> click "GLM-5.3" (exact, NOT -Flash) -> verify selector
  4. click the "Full-Stack" skill chip -> verify it activates in the composer bar
  5. focus composer (#chat-input) -> insert full prompt -> verify >=97% landed
  6. send (Enter; send-button fallback) -> verify composer cleared
  7. record the session in flags/session_registry.jsonl

Sessions registry: scripts/flags/session_registry.jsonl
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags/session_registry.jsonl")

CHAT_URL = "https://chat.z.ai/"
WANT_MODEL = "GLM-5.3"
WANT_SKILL = "Full-Stack"


# ---------------------------------------------------------------- registry --

def _sessions():
    try:
        return [json.loads(l) for l in open(REG).read().split("\n") if l.strip()]
    except Exception:
        return []


def _save(s):
    with open(REG, "a") as f:
        f.write(json.dumps(s) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _find(name):
    found = None
    for s in _sessions():
        if s.get("name") == name and s.get("action") not in ("void", "failed", "tab-reopen"):
            found = s  # latest create record wins
    return found


def _tab_for(s):
    tabs = channel.list_tabs()
    for t in tabs:
        if t["id"] == s.get("tab_id"):
            return t
    for t in tabs:
        if s.get("url") and s["url"].split("chat.z.ai")[-1][:30] in (t.get("url") or ""):
            return t
    return None


# ------------------------------------------------------------ dom helpers --

JS_AGENT_PRESENT = r"""(() => {
  const all = document.querySelectorAll('div,span,button,li,a,p');
  for (const el of all) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join(' ');
    if (own === 'Agent') return 'found';
  }
  return 'not-found';
})()"""

JS_AGENT_NAV = r"""(() => {
  // sidebar nav item whose own text is exactly 'Agent'
  const all = document.querySelectorAll('div,span,button,li,a,p');
  for (const el of all) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join(' ');
    if (own === 'Agent') {
      const target = el.closest('a,button,[role=button]') || el;
      target.click();
      return 'ok';
    }
  }
  return 'not-found';
})()"""

JS_AGENT_MODE_ON = r"""(() => {
  // agent mode replaces "New Chat" with "New Task" in the sidebar
  const all = document.querySelectorAll('div,span,button,li,a,p');
  for (const el of all) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join(' ');
    if (own === 'New Task') return 'true';
  }
  return 'false';
})()"""

JS_MODEL_TEXT = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  return b ? ((b.innerText || '').trim().split('\n')[0] || '?') : 'no-button';
})()"""

JS_OPEN_MODEL_MENU = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return 'no-button';
  b.click();
  return 'ok';
})()"""

JS_CLICK_MODEL = r"""(() => {
  // exact 'GLM-5.3' row (NOT 'GLM-5.3-Flash')
  const cands = [];
  document.querySelectorAll('[role=menuitem], [role=option], [class*=popover] *, [class*=menu] *, [class*=item] *').forEach(e => {
    const t = (e.innerText || '').trim();
    if (t === 'GLM-5.3') cands.push(e);
  });
  if (!cands.length) return 'no-option';
  const label = cands[0];
  const row = label.closest('[role=menuitem],[role=option],button,[class*=item]') || label;
  row.click();
  return 'ok';
})()"""

JS_SKILL_STATE = r"""(() => {
  // returns {introChips: [...], composerChip: bool}
  const intro = [];
  document.querySelectorAll('button').forEach(b => {
    const t = (b.innerText || '').trim().split('\n')[0];
    if (['IM','Full-Stack','Writing','Data Insight'].includes(t)) {
      const cls = (b.className || '').toString();
      if (cls.includes('rounded-md')) intro.push(t);
    }
  });
  let composerChip = false;
  document.querySelectorAll('button').forEach(b => {
    const t = (b.innerText || '').trim().split('\n')[0];
    const cls = (b.className || '').toString();
    if (t === 'Full-Stack' && cls.includes('flag-parent')) composerChip = true;
  });
  return JSON.stringify({intro: intro, composerChip: composerChip});
})()"""

JS_CLICK_SKILL = r"""(() => {
  // click the intro-row Full-Stack chip
  const btns = Array.from(document.querySelectorAll('button'));
  for (const b of btns) {
    const t = (b.innerText || '').trim().split('\n')[0];
    const cls = (b.className || '').toString();
    if (t === 'Full-Stack' && cls.includes('rounded-md')) {
      b.click();
      return 'ok';
    }
  }
  return 'not-found';
})()"""

JS_COMPOSER = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return '';
  const r = i.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
})()"""

JS_SEND_BUTTON = r"""(() => {
  const b = document.querySelector('button.sendMessageButton');
  if (!b) return '';
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), disabled: b.disabled});
})()"""

# --- sandbox concurrency (operator rule: release sandboxes with no active job) ---

JS_SANDBOX_ROWS = r"""(() => {
  const el = Array.from(document.querySelectorAll('div,section,[role=dialog]'))
    .find(e => (e.innerText||'').includes('Limit Sandbox Concurrency'));
  if (!el) return JSON.stringify({present: false});
  const rows = [];
  el.querySelectorAll('button').forEach(b => {
    if ((b.innerText||'').trim() === 'Release') {
      const row = b.closest('tr, div');
      const txt = (row ? row.innerText : '') || '';
      const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
      rows.push({name: lines[0] || '?', meta: lines.slice(1, 4).join(' | ').substring(0, 120)});
    }
  });
  return JSON.stringify({present: true, rows: rows});
})()"""

JS_SANDBOX_RELEASE_FIRST = r"""(() => {
  const el = Array.from(document.querySelectorAll('div,section,[role=dialog]'))
    .find(e => (e.innerText||'').includes('Limit Sandbox Concurrency'));
  if (!el) return 'modal-gone';
  const btns = Array.from(el.querySelectorAll('button'))
    .filter(b => (b.innerText||'').trim() === 'Release');
  if (!btns.length) return 'no-buttons';
  btns[0].click();
  return 'clicked';
})()"""


def _active_session_keywords(extra=None):
    """Keywords identifying sessions with active jobs (registry truth).

    A sandbox row is KEPT if its name matches any keyword. Keywords come from
    live registry sessions: 'wo-009-agents' -> ['wo-009-agents', 'WO-009'].
    """
    kws = []
    for s in _sessions():
        if s.get("action") in ("void", "failed"):
            continue
        if not s.get("sent"):
            continue
        n = s.get("name") or ""
        if n:
            kws.append(n)
            wo = n.split("-agents")[0].split("-chat")[0]
            if wo != n:
                kws.append(wo)
                kws.append(wo.upper())  # 'wo-009' -> 'WO-009'
    for e in (extra or []):
        if e:
            kws.append(e)
            kws.append(e.upper())
    return kws


def _row_is_idle(row, keep_kws):
    """A sandbox row is idle (releasable) when it matches no active session
    and its recent-activity meta doesn't indicate a just-started job."""
    name = (row.get("name") or "")
    meta = (row.get("meta") or "")
    for k in keep_kws:
        if k and k.lower() in name.lower():
            return False  # one of our active jobs
    # a job that started seconds ago may be the session being created right now
    if "second" in meta.lower() or "just now" in meta.lower():
        return False
    return True


def _handle_sandbox_limit(c, keep_kws, max_rounds=6, log=print):
    """Release idle sandboxes when the 'Limit Sandbox Concurrency' modal blocks.

    Operator rule: release the tabs we are not using and have no active job in.
    Returns the number of sandboxes released.
    """
    released = 0
    for round_ in range(max_rounds):
        try:
            st = json.loads(_eval(c, JS_SANDBOX_ROWS, timeout=15) or "{}")
        except Exception:
            return released  # page busy — nothing more we can do here
        if not st.get("present"):
            return released
        rows = st.get("rows") or []
        if not rows:
            log(f"      [sandbox] modal present, no Release buttons")
            return released
        idle = [r for r in rows if _row_is_idle(r, keep_kws)]
        if not idle:
            log(f"      [sandbox] modal present but all {len(rows)} sandbox(es) have "
                f"active jobs — NOT releasing")
            return released
        target = idle[0]
        try:
            res = _eval(c, JS_SANDBOX_RELEASE_FIRST, timeout=15)
        except Exception:
            return released
        if res == "clicked":
            released += 1
            log(f"      [sandbox] released idle sandbox: {target['name'][:50]}")
        time.sleep(2.5)
    return released


def _eval(c, js, timeout=20):
    return c.eval(js, timeout=timeout)


def _reconnect(tab_id, tries=8, sleep=1.5):
    """Re-open a CDP connection to a tab (after a send-triggered navigation)."""
    last = None
    for _ in range(tries):
        try:
            for t in channel.list_tabs():
                if t["id"] == tab_id:
                    last = channel.CDP(t["webSocketDebuggerUrl"], timeout=30)
                    # smoke test: the page responds
                    last.eval("1", timeout=15)
                    return last
        except Exception:
            pass
        time.sleep(sleep)
    if last is None:
        raise RuntimeError(f"tab {tab_id[:8]} unreachable after send")
    return last


def _wait(c, js, want, tries=20, sleep=1.0, desc=""):
    """Poll an eval js until its result == want (string compare)."""
    last = None
    for i in range(tries):
        try:
            last = _eval(c, js, timeout=15)
        except Exception as e:
            last = "err:" + str(e)[:60]
        if last == want:
            return True, last
        time.sleep(sleep)
    return False, last


# ----------------------------------------------------------------- create --

def create(name, prompt_file):
    prompt = open(prompt_file, encoding="utf-8").read()
    if _find(name):
        print(f"session {name} already exists")
        return 1

    print(f"[1/7] new tab -> {CHAT_URL}")
    tab = channel.new_tab()
    if not tab:
        print("ERROR: could not create tab")
        return 1
    print(f"      tab {tab['id'][:8]}")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.navigate", {"url": CHAT_URL}, timeout=30)

        # wait for the page shell (sidebar Agent nav present)
        print("[2/7] waiting for page shell ...")
        ok, last = _wait(c, JS_AGENT_PRESENT, "found", tries=25, sleep=1.5, desc="shell")
        if not ok:
            print(f"ERROR: page shell never loaded (last={last}); login may be expired")
            _save({"name": name, "action": "failed", "stage": "shell", "tab_id": tab["id"],
                   "ts": int(time.time()), "prompt_file": prompt_file})
            return 2
        c.call('Page.bringToFront', {})

        # 3. agent mode
        print("[3/7] selecting AGENTS tab (sidebar 'Agent') ...")
        already = str(_eval(c, JS_AGENT_MODE_ON, timeout=15)) == "true"
        if not already:
            activated = False
            for attempt in range(3):  # click may be swallowed during hydration — retry
                res = _eval(c, JS_AGENT_NAV, timeout=15)
                if res != "ok":
                    print(f"ERROR: Agent nav click failed ({res})")
                    return 2
                ok, _ = _wait(c, JS_AGENT_MODE_ON, "true", tries=8, sleep=1.5, desc="agent-mode")
                if ok:
                    activated = True
                    break
            if not activated:
                print("ERROR: agent mode did not activate ('New Task' marker missing)")
                return 2
        print("      agent mode ON (New Task marker present)")

        # 4. model GLM-5.3
        print(f"[4/7] selecting model {WANT_MODEL} ...")
        cur = _eval(c, JS_MODEL_TEXT)
        if cur != WANT_MODEL:
            if cur == "no-button":
                print("ERROR: model selector button not found")
                return 2
            res = _eval(c, JS_OPEN_MODEL_MENU)
            if res != "ok":
                print(f"ERROR: could not open model menu ({res})")
                return 2
            time.sleep(1.5)
            ok, _ = _wait(c, JS_CLICK_MODEL, "ok", tries=6, sleep=1.5, desc="model-option")
            if not ok:
                print("ERROR: GLM-5.3 option not found in the model menu")
                return 2
            time.sleep(1.0)
            ok, cur = _wait(c, JS_MODEL_TEXT, WANT_MODEL, tries=10, sleep=1.0, desc="model-set")
            if not ok:
                print(f"ERROR: model still '{cur}' (wanted {WANT_MODEL})")
                return 2
        print(f"      model = {WANT_MODEL} (verified)")

        # 5. skill full-stack
        print(f"[5/7] selecting skill {WANT_SKILL} ...")
        state = json.loads(_eval(c, JS_SKILL_STATE) or '{}')
        if state.get("composerChip"):
            print("      Full-Stack already active (composer chip present)")
        elif WANT_SKILL in (state.get("intro") or []):
            res = _eval(c, JS_CLICK_SKILL)
            if res != "ok":
                print(f"ERROR: Full-Stack chip click failed ({res})")
                return 2
            time.sleep(1.5)
            state = json.loads(_eval(c, JS_SKILL_STATE, timeout=15) or '{}')
            if not state.get("composerChip"):
                print("ERROR: Full-Stack skill did not activate (composer chip missing)")
                return 2
            print("      Full-Stack skill ON (composer chip present)")
        else:
            print(f"ERROR: no skill chips found (state={state}); page state unexpected")
            return 2

        # 5b. sandbox concurrency: release idle sandboxes if the modal is up
        # (operator rule: release tabs we are not using / no active job in)
        _handle_sandbox_limit(c, _active_session_keywords(extra=[name]))

        # 6. insert prompt
        print(f"[6/7] inserting prompt ({len(prompt)} chars) ...")
        comp = _eval(c, JS_COMPOSER)
        if not comp:
            print("ERROR: composer not found (no #chat-input) — login expired?")
            _save({"name": name, "action": "failed", "stage": "composer", "tab_id": tab["id"],
                   "ts": int(time.time()), "prompt_file": prompt_file})
            return 2
        pt = json.loads(comp)
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(0.5)
        c.call("Input.insertText", {"text": prompt})
        # verify the full text landed in the composer value
        ok, ratio = _wait(c, r"""(() => {
          const i = document.querySelector('#chat-input');
          return i ? String(Math.round(100 * (i.value||'').length / """ + str(len(prompt)) + r""")) : '0';
        })()""", "100", tries=8, sleep=1.0, desc="insert")
        try:
            pct = int(ratio)
        except Exception:
            pct = 0
        if pct < 97:
            print(f"ERROR: only {pct}% of the prompt landed in the composer; NOT sending")
            _save({"name": name, "action": "failed", "stage": "insert", "pct": pct,
                   "tab_id": tab["id"], "ts": int(time.time()), "prompt_file": prompt_file})
            return 2
        print(f"      insert verified ({pct}%)")

        # 7. send
        print("[7/7] sending ...")
        body_before = int(_eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
        for typ in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {
                "type": typ, "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        time.sleep(3)
        # the send may navigate to the session URL — verify on a FRESH connection
        c.close()
        c = _reconnect(tab["id"])
        cleared = _eval(c, r"""(() => {
          const i = document.querySelector('#chat-input');
          return i ? String((i.value||'').length) : 'gone';
        })()""", timeout=20)
        if cleared not in ("0", "gone"):
            # fallback: click the send button
            sb = _eval(c, JS_SEND_BUTTON)
            if sb:
                spt = json.loads(sb)
                if not spt.get("disabled"):
                    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": spt["x"],
                                                        "y": spt["y"], "button": "left", "clickCount": 1})
                    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": spt["x"],
                                                        "y": spt["y"], "button": "left", "clickCount": 1})
                    time.sleep(3)
                    c.close()
                    c = _reconnect(tab["id"])
                    cleared = _eval(c, r"""(() => {
                      const i = document.querySelector('#chat-input');
                      return i ? String((i.value||'').length) : 'gone';
                    })()""", timeout=20)
        sent = cleared in ("0", "gone")
        # proof in the body: the prompt's first line should now appear in the transcript
        snippet = prompt.strip().split("\n")[0][:60]
        body = _eval(c, "document.body.innerText || ''", timeout=25) or ""
        body_proof = snippet[:40] in body and len(body) > body_before
        url = _eval(c, "location.href", timeout=20)

        ok = sent and (body_proof or url != CHAT_URL)
        print(f"      send: composer-cleared={sent} body-proof={body_proof} url={url}")
        # 7b. the agent's sandbox provisions AFTER the prompt send — if the
        # sandbox-limit modal now blocks it, release idle sandboxes so the job starts
        if ok:
            time.sleep(4)
            released = _handle_sandbox_limit(c, _active_session_keywords(extra=[name]))
            if released:
                print(f"      [sandbox] released {released} idle sandbox(es) so the new job can start")
        print(f"prompt sent: {'VERIFIED' if ok else 'NOT VERIFIED — retry needed'}")
        _save({"name": name, "tab_id": tab["id"], "url": url, "ts": int(time.time()),
               "prompt_file": prompt_file, "prompt_chars": len(prompt),
               "mode": "agents-tab", "model": WANT_MODEL, "skill": WANT_SKILL,
               "insert_pct": pct, "sent": ok})
        return 0 if ok else 2
    finally:
        c.close()


# ------------------------------------------------------------------ check --

def check(name):
    s = _find(name)
    if not s:
        print(f"no session named {name}")
        return 1
    tab = _tab_for(s)
    if not tab:
        print(f"session tab LOST (was {s.get('tab_id','')[:8]}); url: {s.get('url')}")
        return 2
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
    try:
        body = c.eval("document.body.innerText || ''", timeout=20) or ""
        streaming = any(m in body for m in ("Thinking", "Generating", "typing…"))
        # the prompt itself instructs the marker, so the report has landed only
        # when it appears again in the assistant output (>= 2 occurrences)
        marker_count = body.count("COMPLETION REPORT") + body.count("FINAL REPORT")
        has_report = marker_count >= 2 or ("PATCH END" in body and marker_count >= 1)
        lines = [l for l in body.split("\n") if l.strip()]
        print(f"session {name} | mode={s.get('mode','?')} model={s.get('model','?')} skill={s.get('skill','?')}")
        print(f"url {c.eval('location.href', timeout=15)}")
        print(f"chars: {len(body)} | streaming-marker: {streaming} | report-marker: {has_report}")
        print("---- last 15 lines ----")
        for l in lines[-15:]:
            print("  " + l[:120])
        return 0
    finally:
        c.close()


# ------------------------------------------------------------------- void --

def void(name, reason):
    s = None
    for rec in _sessions():
        if rec.get("name") == name:
            s = rec  # last record wins
    if not s:
        print(f"no session named {name}")
        return 1
    # close the tab if it still exists
    closed = False
    tabs = channel.list_tabs()
    for t in tabs:
        if t["id"] == s.get("tab_id"):
            try:
                import urllib.request
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + t["id"], timeout=6).read()
                closed = True
            except Exception:
                pass
    _save({"action": "void", "name": name, "tab_id": s.get("tab_id"),
           "reason": reason, "ts": int(time.time())})
    print(f"session {name} marked VOID (tab closed={closed}): {reason}")
    return 0


# ----------------------------------------------------------------- models --

def models():
    tab = channel.find_tab("chat.z.ai")
    if not tab:
        print("no chat.z.ai tab")
        return 1
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
    try:
        _eval(c, JS_OPEN_MODEL_MENU)
        time.sleep(1.5)
        opts = _eval(c, r"""(() => {
          const items = Array.from(document.querySelectorAll('[role=menuitem], [role=option], [class*=popover] *, [class*=dropdown] *, [class*=menu] *'));
          const texts = items.map(e => (e.innerText||'').trim().split('\n')[0]).filter(t => t && t.length > 2 && t.length < 60);
          return JSON.stringify([...new Set(texts)].slice(0, 20));
        })()""")
        print("MODEL OPTIONS:", opts)
        print("CURRENT:", _eval(c, JS_MODEL_TEXT))
        # close the menu again (Esc)
        c.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape",
                                          "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        c.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape",
                                          "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        return 0
    finally:
        c.close()


# ------------------------------------------------------------- sandboxes --

def sandboxes(session_substr=None):
    """Inspect + release idle agent sandboxes (operator rule: release tabs
    with no active job). Opens the newest live session page (or the one given)
    — the 'Limit Sandbox Concurrency' modal appears there when over the cap."""
    s = None
    if session_substr:
        for rec in _sessions():
            if session_substr in (rec.get("url") or ""):
                s = rec
    if s is None:  # newest live session
        live = [r for r in _sessions() if r.get("sent") and r.get("action") is None]
        s = live[-1] if live else None
    if s is None or not s.get("url"):
        print("no live session to open (the modal only appears on session pages)")
        return 1
    tab = _tab_for(s)
    if not tab:
        tab = channel.new_tab()
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            c.call("Page.navigate", {"url": s["url"]}, timeout=30)
            time.sleep(8)
        finally:
            c.close()
        tab = _tab_for(s) or channel.find_tab(s["url"].split("chat.z.ai")[-1][:30])
        if not tab:
            print("could not open session page")
            return 1
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        try:
            st = json.loads(_eval(c, JS_SANDBOX_ROWS, timeout=15) or "{}")
        except Exception as e:
            print(f"page busy ({e!r}); retry later")
            return 2
        if not st.get("present"):
            print("sandbox limit OK (no modal — under the cap)")
            return 0
        rows = st.get("rows") or []
        print(f"sandbox modal present with {len(rows)} holder(s):")
        keep_kws = _active_session_keywords()
        for r in rows:
            status = "KEEP (active job)" if not _row_is_idle(r, keep_kws) else "IDLE (releasable)"
            print(f"  [{status}] {r.get('name','?')[:60]} | {r.get('meta','')[:60]}")
        released = _handle_sandbox_limit(c, keep_kws)
        print(f"released {released} idle sandbox(es)")
        return 0
    finally:
        c.close()


# ------------------------------------------------------------------- main --

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "create":
        return create(sys.argv[2], sys.argv[3])
    if cmd == "check":
        return check(sys.argv[2])
    if cmd == "list":
        for s in _sessions():
            if s.get("action") == "void":
                print(f"{s['name']:12} VOIDED ({s.get('reason','')[:40]})")
                continue
            print(f"{s['name']:12} tab={s.get('tab_id','')[:8]} mode={s.get('mode','chat')} "
                  f"model={s.get('model','?')} skill={s.get('skill','?')} sent={s.get('sent')}")
        return 0
    if cmd == "void":
        if len(sys.argv) < 4:
            print("usage: void <name> <reason>")
            return 1
        return void(sys.argv[2], " ".join(sys.argv[3:]))
    if cmd == "models":
        return models()
    if cmd == "sandboxes":
        return sandboxes(sys.argv[2] if len(sys.argv) > 2 else None)
    print("unknown command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
