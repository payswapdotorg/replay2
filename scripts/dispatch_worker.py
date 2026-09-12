#!/usr/bin/env python3
"""dispatch_worker.py — create chat.z.ai AGENT worker sessions via the browser (replay).

OPERATOR DIRECTIVE (2026-09-08): worker sessions MUST be created in the AGENTS tab,
with model GLM-5.3 and skill Full-Stack. Sessions started in the chat tab are NULL
AND VOID — they never count as real sessions or real work.

Usage:
  dispatch_worker.py create <name> <prompt_file>   -> agents-tab session, send prompt
  dispatch_worker.py check <name>                  -> session state (text tail)
  dispatch_worker.py send <name> <msg | @file>     -> continuation message (stall recovery)
  dispatch_worker.py list                          -> registered sessions
  dispatch_worker.py void <name> <reason>          -> mark a session void + close tab
  dispatch_worker.py done <name> [note]            -> mark completed + close tab (frees the slot)
  dispatch_worker.py models                        -> inspect model selector options
  dispatch_worker.py sandboxes [url-substr]        -> inspect + release idle sandboxes

Sandbox concurrency (operator rule): when the 'Limit Sandbox Concurrency' modal
blocks, dispatch_worker releases sandboxes that have NO active job (registry
truth: live sessions + their WO keywords are kept; idle/stale holders are
released). This runs automatically inside create() (pre-send + post-send) and
on demand via the sandboxes command.

Capacity protocol (OPERATOR POLICY, 2026-09-09): NEVER wait out a capacity
popup — fight through it. create() cancels the dialog, re-picks the three
selections (agents tab, GLM-5.3, Full-Stack — a cancel can reset them) and
re-sends, round after round; a session rolled back by the site is simply
recreated from scratch (a destroyed session costs nothing, waiting costs
hours). After CAPACITY_ROUNDS in-process rounds it writes
flags/capacity_recover.json {name, prompt_file} and exits 3; the supervisor
relaunches recover_capacity.py, which re-runs this same aggressive dispatch
loop until the task actually generates. Never wait passively.

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
import re
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
    """Latest create record for `name` that has not been voided/failed since.

    A later void/failed record with the same name invalidates every earlier
    create record for it (so names can be reused after void)."""
    found = None
    create_url = None
    for s in _sessions():
        if s.get("name") != name:
            continue
        if s.get("action") in ("void", "failed", "done"):
            found = None  # invalidated / retired
        elif s.get("stage") == "capacity":
            found = None  # capacity-staged: the aggressive assault re-dispatch owns it
        elif s.get("action") == "tab-reopen":
            # §3.8 recovery: the session's live tab changed — carry it onto the
            # resolved record so _tab_for (tab_id + url fallback) finds the new tab
            if found is not None:
                found = dict(found)
                if s.get("tab_id"):
                    found["tab_id"] = s["tab_id"]
                if s.get("url"):
                    found["url"] = s["url"]
        else:
            found = dict(s)  # latest create/send record wins
            if s.get("action") is None and s.get("url"):
                create_url = s["url"]  # create records own the canonical URL
            if not found.get("url") and create_url:
                found["url"] = create_url
    if found is not None and not found.get("url") and create_url:
        found = dict(found, url=create_url)
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
  // robust 'GLM-5.3' row click (NOT 'GLM-5.3-Flash').
  // 2026-09-11: site DOM changed — menu items render name+description in one
  // node and the menu can auto-close between the open-click and the scan, so
  // this expression re-opens the menu itself on every evaluation and matches
  // both exact-text and first-line-prefix forms.
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return 'no-button';
  if (b.getAttribute('aria-expanded') !== 'true') { b.click(); }
  const cands = [];
  const consider = (e) => {
    const full = (e.innerText || '').trim();
    const first = full.split('\\n')[0].trim();
    if (full === 'GLM-5.3' || first === 'GLM-5.3') cands.push(e);
  };
  document.querySelectorAll('[role=menuitem], [role=option], [cmdk-item], [class*=popover] *, [class*=menu] *, [class*=item] *').forEach(consider);
  if (!cands.length) return 'no-option';
  // prefer the shallowest candidate (the row, not a deep span)
  cands.sort((a, z) => (a.compareDocumentPosition(z) & 2) ? -1 : 1);
  const el = cands[0];
  const row = el.closest('[role=menuitem],[role=option],button,[cmdk-item],[class*=item]') || el;
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

JS_FOCUS_COMPOSER = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'gone';
  i.focus();
  return (document.activeElement === i) ? 'ok' : 'no';
})()"""

JS_DISMISS_DIALOG = r"""(() => {
  // promotional / notification dialogs (2026-09-09 23:50 forensics: the
  // GLM-5.3-Flash launch dialog) overlay the composer, steal focus and eat
  // clicks — insertText lands 0%, Enter vanishes, sends fail with url=None.
  // Close them via their close button (aria-label or bare svg button).
  const dlg = document.querySelector('[role=dialog]');
  if (!dlg) return 'none';
  const btns = [...dlg.querySelectorAll('button')];
  const close = btns.find(b => /close/i.test(b.getAttribute('aria-label') || '')
                              || ((b.innerText||'').trim() === '' && b.querySelector('svg')));
  if (close) { close.click(); return 'closed'; }
  return 'dialog-no-close-button';
})()"""

JS_CLEAR_COMPOSER = r"""(() => {
  // React-native clear: bypass the controlled-component setter, then notify
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'no-input';
  const proto = i.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                                         : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
  return String((i.value || '').length);
})()"""

JS_INSERT_RATIO = r"""(() => {
  const i = document.querySelector('#chat-input');
  return i ? String(Math.round(100 * (i.value||'').length / __PLEN__)) : '0';
})()"""

JS_CAPACITY_STATE = r"""(() => {
  const body = document.body.innerText || '';
  const capacity = body.includes('currently at capacity') || body.includes('try again later')
                || body.includes('peak hours');
  let hasCancel = false;
  let generating = false;
  document.querySelectorAll('button').forEach(b => {
    const t = (b.innerText || '').trim();
    if (t === 'Cancel') hasCancel = true;
    if (/^(Stop|Pause|Halt)$/i.test(t)) generating = true;
  });
  return JSON.stringify({capacity: capacity, hasCancel: hasCancel, generating: generating});
})()"""

JS_CLICK_CANCEL = r"""(() => {
  const btns = Array.from(document.querySelectorAll('button'));
  const b = btns.find(x => (x.innerText || '').trim() === 'Cancel');
  if (!b) return 'no-cancel';
  b.click();
  return 'ok';
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

JS_SANDBOX_RELEASE_TARGET = r"""(() => {
  // locate the Release button of the row whose text contains `name`, and
  // return its center coordinates (real CDP mouse events are required —
  // programmatic .click() does not work on this modal)
  const el = Array.from(document.querySelectorAll('div,section,[role=dialog]'))
    .find(e => (e.innerText||'').includes('Limit Sandbox Concurrency'));
  if (!el) return 'modal-gone';
  const btns = Array.from(el.querySelectorAll('button'))
    .filter(b => (b.innerText||'').trim() === 'Release');
  for (const b of btns) {
    const row = b.closest('tr, div');
    if (row && (row.innerText||'').includes('__TARGET__')) {
      const r = b.getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
    }
  }
  return 'no-target';
})()"""


def _active_session_keywords(extra=None):
    """Keywords identifying sessions with active jobs (registry truth).

    Registry semantics: the LATEST record per name wins (file order =
    chronological; this is how void -> re-create and tab-reopen work). A name
    is live only when its latest record is sent and carries no terminal
    action (void/failed/done). Old records — e.g. chat-tab-era sessions the
    operator ruled NULL AND VOID, superseded re-dispatches, or done sessions —
    must NOT contribute keywords, or their stale sandboxes get KEPT in the
    concurrency modal and block new jobs.

    A sandbox row is KEPT if its name matches any keyword. Keywords come from
    live sessions: 'wo-009-agents' -> ['wo-009-agents', 'WO-009']. The modal
    identifies holders by their session UUID (e.g. '2d8588a4-…') — so every
    live session's /c/<uuid> id is added as a keyword too.
    """
    last = {}
    ever_sent = set()
    for s in _sessions():
        n = s.get("name")
        if n:
            last[n] = s  # later lines supersede earlier ones
            if s.get("sent"):
                ever_sent.add(n)
    kws = []
    for n, s in last.items():
        if s.get("action") in ("void", "failed", "done"):
            continue  # retired: its sandbox is no longer an active job
        # 2026-09-10 fix (mkt-25 sandbox released mid-work twice): the latest
        # record for an ACTIVE session may be a tab-reopen (renderer recovery)
        # or a failed continuation send — neither carries sent, but the
        # session still holds live work. Liveness = latest record non-terminal
        # AND the name has EVER sent successfully.
        if n not in ever_sent:
            continue
        if n:
            kws.append(n)
            wo = n.split("-agents")[0].split("-chat")[0]
            if wo != n:
                kws.append(wo)
                kws.append(wo.upper())  # 'wo-009' -> 'WO-009'
        # 2026-09-11 fix (lesson-42 recurrence: rulings sandbox row title
        # 'RTN Plan Rulings: 5 Open Questions' matched NO keyword — the modal
        # shows the platform-transformed CHAT TITLE, not the session name or
        # UUID). Two extra derivations per live session:
        #   (a) every name word >=5 chars, lowercased ('architect-rulings-5'
        #       -> 'architect', 'rulings' — 'rulings' matches the row title)
        #   (b) the prompt file's first-line work-item prefix ('# UI-009 —
        #       ...' -> 'ui-009') for rows titled from the prompt head
        for w in re.split(r"[^A-Za-z0-9]+", n or ""):
            if len(w) >= 5:
                kws.append(w.lower())
        pf = s.get("prompt_file") or ""
        if pf and os.path.isfile(pf):
            try:
                with open(pf, "r", errors="replace") as fh:
                    first = fh.readline().strip()
                first = re.sub(r"^#+\s*", "", first)
                prefix = re.split(r"\s+[—–-]\s+", first)[0].strip()
                if prefix and len(prefix) >= 3:
                    kws.append(prefix.lower())
            except Exception:
                pass
        # the session UUID from the recorded URL (modal rows use it as name)
        u = s.get("url") or ""
        if "/c/" in u:
            uuid = u.split("/c/")[-1].split("?")[0].split("#")[0].strip("/")
            if uuid:
                kws.append(uuid)
                kws.append(uuid.split("-")[0])  # short-prefix safety
    for e in (extra or []):
        if e:
            kws.append(e)
            kws.append(e.upper())
    return kws


def _row_is_idle(row, keep_kws):
    """A sandbox row is idle (releasable) when it matches no active session
    and its recent-activity meta doesn't indicate a just-started job."""
    import re
    name = (row.get("name") or "")
    meta = (row.get("meta") or "")
    for k in keep_kws:
        if k and k.lower() in name.lower():
            return False  # one of our active jobs
    # a job that started seconds/minutes ago may be the session being
    # created right now (sandbox provisions right after the prompt send)
    ml = meta.lower()
    if "second" in ml or "just now" in ml:
        return False
    m = re.search(r"(\d+)\s*minute", ml)
    if m and int(m.group(1)) <= 10:
        return False
    return True


def _handle_sandbox_limit(c, keep_kws, max_rounds=6, log=print):
    """Release idle sandboxes when the 'Limit Sandbox Concurrency' modal blocks.

    Operator rule: release the tabs we are not using and have no active job in.
    Each release clicks the TARGET row's Release button with real CDP mouse
    events (programmatic .click() is a no-op on this modal). Returns the
    number of sandbox releases verified (row disappears from the modal).
    """
    released = 0
    # the modal only processes real pointer events on a FOCUSED (front) tab —
    # clicks dispatched while the tab is backgrounded are silently ignored
    try:
        c.call("Page.bringToFront", {}, timeout=10)
        time.sleep(0.5)
    except Exception:
        pass
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
        # locate the target row's Release button -> real mouse events
        try:
            js = JS_SANDBOX_RELEASE_TARGET.replace("__TARGET__", target.get("name", "")[:40])
            res = _eval(c, js, timeout=15)
        except Exception:
            return released
        if res in ("modal-gone", "no-target"):
            log(f"      [sandbox] target row vanished ({res}) — re-reading")
            time.sleep(2.0)
            continue
        try:
            pt = json.loads(res)
        except Exception:
            log(f"      [sandbox] could not locate Release for {target['name'][:40]}")
            return released
        c.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": pt["x"], "y": pt["y"]})
        time.sleep(0.4)
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(3.0)
        # verify: the row must be gone from the modal
        try:
            st2 = json.loads(_eval(c, JS_SANDBOX_ROWS, timeout=15) or "{}")
        except Exception:
            st2 = {}
        names2 = [r.get("name") for r in (st2.get("rows") or [])]
        if target.get("name") not in names2:
            released += 1
            log(f"      [sandbox] released idle sandbox: {target['name'][:50]} (verified gone)")
        else:
            log(f"      [sandbox] release of {target['name'][:40]} did NOT take effect — stopping")
            return released
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

CAPACITY_ROUNDS = int(__import__("os").environ.get("DW_ROUNDS", "12"))  # in-process assault rounds; then flag + exit 3 (the
                      # supervisor relaunches recover_capacity.py, which re-runs
                      # the same aggressive loop — never a passive wait)


def _close_tab(tid):
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9222/json/close/" + tid, timeout=6).read()
        return True
    except Exception:
        return False


def _close_stale_tab(name):
    """Close the tab left behind by a capacity-staged/failed record for `name`.

    The aggressive re-dispatch owns the task; stale tabs must not accumulate
    (they hold sandbox slots and clutter the concurrency modal). The latest
    record for the name decides; live sessions are never touched (the
    _find() guard already returned for them).
    """
    for s in reversed(_sessions()):
        if s.get("name") != name:
            continue
        tid = s.get("tab_id")
        if tid and (s.get("stage") == "capacity" or s.get("action") == "failed"):
            if _close_tab(tid):
                print(f"      closed stale tab {tid[:8]} ({s.get('stage') or s.get('action')})")
        return


def _select_insert_send(c, tab, prompt, name, prompt_file):
    """Steps [3/7]..[7/7] on an already-navigated tab: pick the agents tab,
    model GLM-5.3 and skill Full-Stack (each hard-verified — refuses to send
    if any selection does not stick), release idle sandboxes, insert the
    full prompt (>=97% verified) and send. Returns (ok, url, pct, c) where
    the returned `c` is a FRESH connection (the send navigates the page)."""

    # 3. agent mode
    print("[3/7] selecting AGENTS tab (sidebar 'Agent') ...")
    already = str(_eval(c, JS_AGENT_MODE_ON, timeout=15)) == "true"
    if not already:
        activated = False
        for _attempt in range(3):  # click may be swallowed during hydration — retry
            res = _eval(c, JS_AGENT_NAV, timeout=15)
            if res != "ok":
                print(f"ERROR: Agent nav click failed ({res})")
                return False, None, 0, c
            ok, _ = _wait(c, JS_AGENT_MODE_ON, "true", tries=8, sleep=1.5, desc="agent-mode")
            if ok:
                activated = True
                break
        if not activated:
            print("ERROR: agent mode did not activate ('New Task' marker missing)")
            return False, None, 0, c
    print("      agent mode ON (New Task marker present)")

    # 4. model GLM-5.3
    print(f"[4/7] selecting model {WANT_MODEL} ...")
    cur = _eval(c, JS_MODEL_TEXT)
    if cur != WANT_MODEL:
        if cur == "no-button":
            print("ERROR: model selector button not found")
            return False, None, 0, c
        res = _eval(c, JS_OPEN_MODEL_MENU)
        if res != "ok":
            print(f"ERROR: could not open model menu ({res})")
            return False, None, 0, c
        time.sleep(1.5)
        ok, _ = _wait(c, JS_CLICK_MODEL, "ok", tries=6, sleep=1.5, desc="model-option")
        if not ok:
            print("ERROR: GLM-5.3 option not found in the model menu")
            return False, None, 0, c
        time.sleep(1.0)
        ok, cur = _wait(c, JS_MODEL_TEXT, WANT_MODEL, tries=10, sleep=1.0, desc="model-set")
        if not ok:
            print(f"ERROR: model still '{cur}' (wanted {WANT_MODEL})")
            return False, None, 0, c
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
            return False, None, 0, c
        time.sleep(1.5)
        state = json.loads(_eval(c, JS_SKILL_STATE, timeout=15) or '{}')
        if not state.get("composerChip"):
            print("ERROR: Full-Stack skill did not activate (composer chip missing)")
            return False, None, 0, c
        print("      Full-Stack skill ON (composer chip present)")
    else:
        print(f"ERROR: no skill chips found (state={state}); page state unexpected")
        return False, None, 0, c

    # 5b. sandbox concurrency: release idle sandboxes if the modal is up
    # (operator rule: release tabs we are not using / no active job in)
    _handle_sandbox_limit(c, _active_session_keywords(extra=[name]))

    # 6. insert prompt (idempotent: clear first, verify bounds 97..115,
    #    one clear+retry if the site doubled the text — seen live on a
    #    59K insert; a 200% send would poison the session)
    print(f"[6/7] inserting prompt ({len(prompt)} chars) ...")
    comp = _eval(c, JS_COMPOSER)
    if not comp:
        print("ERROR: composer not found (no #chat-input) — login expired?")
        _save({"name": name, "action": "failed", "stage": "composer", "tab_id": tab["id"],
               "ts": int(time.time()), "prompt_file": prompt_file})
        return False, None, 0, c
    ratio_js = JS_INSERT_RATIO.replace("__PLEN__", str(len(prompt)))
    pct = 0
    for attempt in range(3):
        pt = json.loads(comp)
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(0.5)
        # clear whatever is in the composer (React-native clear)
        _eval(c, JS_CLEAR_COMPOSER, timeout=15)
        time.sleep(0.3)
        # DOM-FOCUS (23:35 forensics): the coordinate click above can MISS
        # the textarea (dropdown overlays, layout shifts after the model/skill
        # chips) — Input.insertText then goes to <body> and the insert lands
        # 0%. focus() the element directly and hard-verify activeElement.
        foc = _eval(c, JS_FOCUS_COMPOSER, timeout=15)
        if foc != "ok":
            print(f"      [focus] composer focus returned '{foc}' — retrying click")
            pt2 = json.loads(_eval(c, JS_COMPOSER) or '{"x":0,"y":0}')
            c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt2["x"], "y": pt2["y"],
                                                "button": "left", "clickCount": 1})
            c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt2["x"], "y": pt2["y"],
                                                "button": "left", "clickCount": 1})
            time.sleep(0.4)
            _eval(c, JS_FOCUS_COMPOSER, timeout=15)
        # chunked insert: a single >100K-char Input.insertText starves the
        # CDP websocket (recv timeout under the event flood) and can block
        # the page's input handler; 16K chunks with short pauses are reliable
        CH = 16000
        for off in range(0, len(prompt), CH):
            c.call("Input.insertText", {"text": prompt[off:off + CH]}, timeout=90)
            time.sleep(0.4)
        ok, ratio = _wait(c, ratio_js, "100", tries=8, sleep=1.0, desc="insert")
        try:
            pct = int(ratio)
        except Exception:
            pct = 0
        if 97 <= pct <= 115:
            break
        print(f"      insert attempt {attempt+1}: ratio {pct}% (want 97-115) — clearing and retrying")
    if not (97 <= pct <= 115):
        print(f"ERROR: insert ratio {pct}% outside 97-115 bounds; NOT sending")
        _save({"name": name, "action": "failed", "stage": "insert", "pct": pct,
               "tab_id": tab["id"], "ts": int(time.time()), "prompt_file": prompt_file})
        return False, None, 0, c
    print(f"      insert verified ({pct}%)")

    # 7. send
    print("[7/7] sending ...")
    body_before = int(_eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
    # FOCUS-BEFORE-ENTER (23:40 forensics): after an 80K-char insert the
    # textarea grew (rect moved) and focus may sit elsewhere — an Enter to
    # <body> silently drops the send (url stays home). Re-click the LIVE
    # textarea rect and DOM-focus it right before pressing Enter.
    try:
        fp = json.loads(_eval(c, JS_COMPOSER) or '{"x":0,"y":0}')
        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fp["x"], "y": fp["y"],
                                            "button": "left", "clickCount": 1})
        time.sleep(0.3)
    except Exception:
        pass
    _eval(c, JS_FOCUS_COMPOSER, timeout=15)
    time.sleep(0.2)
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
    return ok, url, pct, c


def create(name, prompt_file):
    # absolute from the start: the capacity-recovery flag + registry records
    # are consumed by processes with a DIFFERENT cwd (supervisor/relaunchers) —
    # a relative path broke recovery with FileNotFoundError (2026-09-10)
    prompt_file = os.path.abspath(prompt_file)
    prompt = open(prompt_file, encoding="utf-8").read()
    if _find(name):
        print(f"session {name} already exists")
        return 1

    # the aggressive re-dispatch owns the task: close any tab left behind by
    # a capacity-staged/failed record for this name (no tab accumulation)
    _close_stale_tab(name)

    print(f"[1/7] new tab -> {CHAT_URL}")
    tab = channel.new_tab()
    if not tab:
        print("ERROR: could not create tab")
        return 1
    print(f"      tab {tab['id'][:8]}")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.navigate", {"url": CHAT_URL}, timeout=30)
        ok, url, pct = False, CHAT_URL, 0
        for assault_round in range(CAPACITY_ROUNDS + 1):
            if assault_round:
                # OPERATOR POLICY (2026-09-09): NEVER wait out a capacity
                # popup. Cancel it, re-pick the three selections (agents tab,
                # GLM-5.3, Full-Stack) and resend. A cancelled session may
                # roll back server-side (tab -> home): recreate the task from
                # scratch on the next round — a destroyed session costs
                # nothing, waiting costs hours.
                try:
                    c.close()
                except Exception:
                    pass
                try:
                    c = _reconnect(tab["id"])
                except Exception:
                    tab = channel.new_tab() or tab
                    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                c.call("Page.navigate", {"url": CHAT_URL}, timeout=30)
                print(f"[assault {assault_round}/{CAPACITY_ROUNDS}] popup cancelled — "
                      f"re-picking selections and re-sending")

            # wait for the page shell (sidebar Agent nav present)
            print("[2/7] waiting for page shell ...")
            try:
                ok_shell, last = _wait(c, JS_AGENT_PRESENT, "found", tries=25, sleep=1.5, desc="shell")
                if not ok_shell:
                    print(f"ERROR: page shell never loaded (last={last}); login may be expired")
                    _save({"name": name, "action": "failed", "stage": "shell", "tab_id": tab["id"],
                           "ts": int(time.time()), "prompt_file": prompt_file})
                    return 2
                c.call('Page.bringToFront', {})
                # dismiss any promotional/notification dialog that overlays
                # the composer (GLM-5.3-Flash launch popup etc.) — it steals
                # focus and eats the clicks/inserts that follow
                for _ in range(2):
                    dres = _eval(c, JS_DISMISS_DIALOG, timeout=10)
                    if dres == 'none':
                        break
                    time.sleep(1.2)

                ok, url, pct, c = _select_insert_send(c, tab, prompt, name, prompt_file)
                # DELAYED LANDING RE-CHECK (2026-09-12 forensics): the capacity
                # popup + optimistic-render rollback arrive SECONDS after the
                # send; an immediate check exits with a false VERIFIED before
                # the site rolls the un-accepted session back to home. Ground
                # truth after the settle window: session URL (/c/...), prompt
                # visible in the transcript — else the send did NOT stick.
                if ok:
                    time.sleep(9)
                    try:
                        url_now = _eval(c, "location.href", timeout=20) or CHAT_URL
                    except Exception:
                        url_now = url
                    if url_now not in (CHAT_URL, "about:blank"):
                        url = url_now  # landed (or queued-capacity) — keep truth
                    else:
                        body_now = _eval(c, "document.body.innerText || ''", timeout=25) or ""
                        snippet = prompt.strip().split("\n")[0][:40]
                        if not (snippet in body_now and len(body_now) > 3000):
                            print("      [landing] send did NOT stick (rolled back home) — assault round")
                            ok = False
                            url = url_now
            except Exception as e:
                # transient CDP/websocket failure (busy page, dialog churn):
                # never crash the assault — reconnect and take the next round
                print(f"      [transient] {type(e).__name__} in round {assault_round} — "
                      f"reconnect + next assault round")
                try:
                    c.close()
                except Exception:
                    pass
                try:
                    c = _reconnect(tab["id"])
                except Exception:
                    tab = channel.new_tab() or tab
                    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                time.sleep(5)
                continue

            try:
                st = json.loads(_eval(c, JS_CAPACITY_STATE, timeout=15) or "{}")
            except Exception:
                st = {}
            if st.get("generating"):
                ok = True  # generation started — the task is live
            if ok and not st.get("capacity"):
                # 7b. the agent's sandbox provisions AFTER the prompt send —
                # if the sandbox-limit modal now blocks it, release idle
                # sandboxes so the job starts
                time.sleep(4)
                released = _handle_sandbox_limit(c, _active_session_keywords(extra=[name]))
                if released:
                    print(f"      [sandbox] released {released} idle sandbox(es) so the new job can start")
                print(f"prompt sent: {'VERIFIED' if ok else 'NOT VERIFIED — retry needed'}")
                _save({"name": name, "tab_id": tab["id"], "url": url, "ts": int(time.time()),
                       "prompt_file": prompt_file, "prompt_chars": len(prompt),
                       "mode": "agents-tab", "model": WANT_MODEL, "skill": WANT_SKILL,
                       "insert_pct": pct, "sent": ok})
                return 0
            if not st.get("capacity"):
                # no capacity dialog: genuine insert/send failure — climb the
                # failure ladder (check body tail, re-send, or re-create)
                print(f"prompt sent: NOT VERIFIED — retry needed (url={url})")
                _save({"name": name, "tab_id": tab["id"], "url": url, "ts": int(time.time()),
                       "prompt_file": prompt_file, "prompt_chars": len(prompt),
                       "mode": "agents-tab", "model": WANT_MODEL, "skill": WANT_SKILL,
                       "insert_pct": pct, "sent": False})
                return 2
            if ok and "/c/" in (url or ""):
                # SERVER-SIDE EXISTENCE CHECK (2026-09-12 lessons 63/65): the
                # URL moving to /c/<uuid> used to be trusted as acceptance —
                # under the peak gate it LIES (phantom /c/ URLs with a staged
                # composer; the chat is never created server-side). Verify the
                # chat EXISTS (and carries the first message) before calling
                # it accepted.
                cid = (url or "").split("/c/")[-1].split("/")[0].split("?")[0]
                exists_server = False
                try:
                    ev = c.eval(r"""(async () => {
                      const m = location.href.match(/\/c\/([0-9a-f-]{36})/);
                      if (!m) return JSON.stringify({err: 'no-chat-url'});
                      const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
                      const r = await fetch('/api/v1/chats/' + m[1], {credentials: 'include',
                        headers: tok ? {Authorization: 'Bearer ' + tok} : {}});
                      if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
                      const j = await r.json();
                      const msgs = ((j.chat || {}).history || {}).messages || {};
                      let userLen = 0;
                      for (const mm of Object.values(msgs)) {
                        if (mm.role === 'user') {
                          const cc = Array.isArray(mm.content) ? mm.content : [mm.content];
                          userLen = Math.max(userLen, JSON.stringify(cc).length);
                        }
                      }
                      return JSON.stringify({exists: true, userLen: userLen});
                    })()""", await_promise=True, timeout=30)
                    evd = json.loads(ev or "{}")
                    if evd.get("exists") and evd.get("userLen", 0) > 100:
                        exists_server = True
                    else:
                        print(f"      [server-verify] chat NOT live server-side ({ev[:90]}) — "
                              "phantom /c/ URL; continuing assault")
                except Exception as e:
                    print(f"      [server-verify] check failed ({str(e)[:60]}) — continuing assault")
                if not exists_server:
                    ok = False
                # TWO-STATE CAPACITY PROTOCOL (queue_watch.py; live evidence
                # 2026-09-10): a send whose URL moved to /c/<uuid> (composer
                # cleared + prompt in transcript) was ACCEPTED — the task is
                # QUEUED server-side and the capacity popup is COSMETIC.
                # Cancelling destroys the queued session and re-queues at the
                # back (two hours of destroyed sessions before this fix).
                # Do NOT cancel: keep the tab open, register the session as
                # sent-queued, and monitor with `check <name>` — generation
                # starts when capacity frees.
                if exists_server:
                    print("prompt ACCEPTED — session live at " + str(url) + " (server-verified)")
                    print("      capacity popup is COSMETIC (task queued server-side) — NOT cancelling;")
                    print("      monitor generation start with: dispatch_worker.py check " + name)
                    _save({"name": name, "tab_id": tab["id"], "url": url, "ts": int(time.time()),
                           "prompt_file": prompt_file, "prompt_chars": len(prompt),
                           "mode": "agents-tab", "model": WANT_MODEL, "skill": WANT_SKILL,
                           "insert_pct": pct, "sent": True, "stage": "queued-capacity"})
                    return 0
                # phantom /c/ URL: fall through to the assault (never register
                # a session that does not exist server-side)
            # capacity dialog present and the send was NOT accepted — assault
            print(f"      [capacity] GLM-5.3 at capacity (round {assault_round}) — "
                  f"Cancel + re-pick + resend (operator policy: never wait)")
            try:
                c.call("Page.bringToFront", {}, timeout=10)
            except Exception:
                pass
            _eval(c, JS_CLICK_CANCEL, timeout=15)
            time.sleep(4)
            backoff = min(20 + 10 * assault_round, 60)
            print(f"      next assault round in {backoff}s")
            time.sleep(backoff)

        # in-process rounds exhausted — persistent hand-off: the supervisor
        # relaunches recover_capacity.py, which re-runs this same aggressive
        # loop (never passively waiting) until the task generates.
        url = _eval(c, "location.href", timeout=20) or CHAT_URL
        m = re.search(r"/c/([0-9a-f]{8})", url)
        uuid = m.group(1) if m else tab["id"]
        # per-session flag file: two exhausted sessions must never overwrite
        # each other's recovery spec (single-slot flag lost all but the last
        # writer). Name is sanitized; legacy single flag remains readable.
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        flag = os.path.join(BASE, f"flags/capacity_recover.{safe}.json")
        os.makedirs(os.path.dirname(flag), exist_ok=True)
        with open(flag, "w") as f:
            f.write(json.dumps({"name": name, "prompt_file": prompt_file, "uuid": uuid,
                                "tab_id": tab["id"], "ts": int(time.time())}))
        _save({"name": name, "tab_id": tab["id"], "url": url, "ts": int(time.time()),
               "prompt_file": prompt_file, "prompt_chars": len(prompt),
               "mode": "agents-tab", "model": WANT_MODEL, "skill": WANT_SKILL,
               "insert_pct": pct, "sent": False, "stage": "capacity"})
        print("      assault rounds exhausted — flag written; recover_capacity.py (supervisor-")
        print("      guarded) re-runs the aggressive loop. session: dispatch_worker.py check " + name)
        return 3
    finally:
        try:
            c.close()
        except Exception:
            pass


# ------------------------------------------------------------------ done --

def done(name, note=""):
    """Mark a session DONE (completed + harvested) and close its tab.

    A done session is retired: it no longer counts as an active job for
    sandbox keep/release decisions, and its name is freed for reuse.
    The session's chat transcript stays on chat.z.ai (the work record).
    """
    s = None
    for rec in _sessions():
        if rec.get("name") == name:
            s = rec  # last record wins
    if not s:
        print(f"no session named {name}")
        return 1
    closed = False
    for t in channel.list_tabs():
        if t["id"] == s.get("tab_id"):
            try:
                import urllib.request
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + t["id"], timeout=6).read()
                closed = True
            except Exception:
                pass
    _save({"action": "done", "name": name, "tab_id": s.get("tab_id"),
           "note": note, "ts": int(time.time())})
    print(f"session {name} marked DONE (tab closed={closed}): {note}")
    return 0


# ------------------------------------------------------------------ send --

def send(name, message):
    """Send a continuation/follow-up message into an existing session.

    Failure-ladder step 3: a turn stalled mid-work (or the composer kept the
    text after a failed send) — the recovery is a browser-driven re-send in
    the SAME session. Uses the proven create() method: click composer ->
    React-native clear -> insertText -> focus-the-textarea -> Enter.

    2026-09-09 fix (WO-010 stall forensics): the old code clicked the
    composer at coordinates measured BEFORE the insert — a 1k-char message
    grows the textarea ~60px, so the click landed below it and Enter went
    to <body> (message never sent). The fix re-queries the textarea rect
    AFTER insert, clicks its center, hard-verifies activeElement === the
    textarea, and only then presses Enter. Capacity popups are assaulted
    in-session (Cancel + refocus + Enter) per the operator policy: never
    wait, never destroy a session that holds work.
    """
    s = _find(name)
    if not s:
        print(f"no session named {name}")
        return 1
    tab = _tab_for(s)
    if not tab:
        print(f"session tab LOST (was {s.get('tab_id','')[:8]}); url: {s.get('url')}")
        return 2
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        # JUNK-SESSION GUARD (2026-09-12 vwo-011 forensic): a 'message sent:
        # VERIFIED' into a tab that has rolled HOME creates a junk chat and
        # fools the body-growth proof (942 -> 1431 was the home page, not the
        # session). Verify the tab is on THIS session's chat URL before
        # touching the composer; a destroyed session is the watcher
        # assault's job, not the send path's.
        want = (s.get("url") or "").rstrip("/").split("/c/")[-1]
        cur = _eval(c, "location.href", timeout=15) or ""
        if "/c/" not in cur or (want and want not in cur):
            print(f"tab is NOT on {name}'s session (at {cur[:70]}) — destroyed; "
                  "refusing to send into a blank/home chat")
            return 3
        # refuse to interrupt an actively-generating turn
        busy = _eval(c, r"""(() => {
          const btns = Array.from(document.querySelectorAll('button'))
            .map(b => (b.innerText||'').trim());
          return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 'busy' : 'idle';
        })()""", timeout=15)
        if busy == "busy":
            print("session is generating right now; not interrupting")
            return 0
        # dismiss promotional/notification dialogs first (they overlay the
        # composer, steal focus and eat clicks — GLM-5.3-Flash popup etc.)
        for _ in range(2):
            dres = _eval(c, JS_DISMISS_DIALOG, timeout=10)
            if dres == "none":
                break
            print(f"      [dialog] dismissed promotional dialog ({dres})")
            time.sleep(1.2)
        # a capacity modal may already be up (e.g. from a previous failed
        # send): it BLOCKS the composer — insert would land nowhere (ratio 0).
        # Cancel it first so the page below becomes interactive again.
        try:
            st0 = json.loads(_eval(c, JS_CAPACITY_STATE, timeout=15) or "{}")
        except Exception:
            st0 = {}
        if st0.get("capacity") or st0.get("hasCancel"):
            # OPERATOR DIRECTIVE (2026-09-12, supersedes the 22:29 rate-limit
            # guard): rate-limit notifications DO NOT APPLY — never wait out
            # a cooldown. Cancel the modal and attempt the send (the
            # cancel+retry protocol); a rejected send reports itself and the
            # queue_watch unstick/assault ladder owns the retry cadence.
            limited = _eval(c, r"""(() => {
              // 2026-09-10 fix: the limit text ALSO survives as stale
              // TRANSCRIPT text after the cooldown lapses (inline in a
              // message element, never removed) — only a LIVE modal blocks
              // sending. Live = fixed-position overlay carrying the text.
              for (const el of document.querySelectorAll('div,section')) {
                const st = getComputedStyle(el);
                if (st.position === 'fixed' && parseInt(st.zIndex || '0') >= 500) {
                  const lt = (el.innerText || '');
                  if (lt.includes('exceeds the personal limit') ||
                      lt.includes('try again 1 hour later')) return 'yes';
                }
              }
              return 'no';
            })()""", timeout=15)
            # (live-modal probe above kept for logging only)
            _eval(c, JS_CLICK_CANCEL, timeout=15)
            print("      [capacity] pre-existing popup cancelled before composer use")
            time.sleep(3)
        # STAGED-REJECTED SHORTCUT (wave-4 forensics): after a capacity
        # rejection the composer often still holds the FULL message (the UI
        # staged it into the transcript but never sent). If so, skip the
        # clear+insert entirely — re-inserting an 80K prompt through a modal
        # transition is exactly when insertText lands nowhere (ratio 0).
        staged_len = _eval(c, r"""(() => {
          const i = document.querySelector('#chat-input, textarea');
          return i ? String((i.value||'').length) : 'gone';
        })()""", timeout=15)
        try:
            staged = int(staged_len) >= int(len(message) * 0.97)
        except Exception:
            staged = False
        if staged:
            print(f"      [staged] composer already holds the full message ({staged_len} chars) — send-only path")
            pct = 100
        else:
            comp = _eval(c, JS_COMPOSER)
            if not comp:
                print("ERROR: composer not found — login expired?")
                return 2
            pt = json.loads(comp)
            c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                                "button": "left", "clickCount": 1})
            time.sleep(0.5)
            # FOCUS-BEFORE-INSERT (wave-4 forensics): Input.insertText goes to
            # the FOCUSED element; after a modal Cancel the focus sits on
            # <body> and the insert vanishes (ratio 0%). Focus the textarea
            # and hard-verify BEFORE inserting.
            focused0 = _eval(c, r"""(() => {
              const i = document.querySelector('#chat-input, textarea');
              return (i && document.activeElement === i) ? 'yes' : 'no';
            })()""", timeout=15)
            if focused0 != "yes":
                _eval(c, r"""(() => {
                  const i = document.querySelector('#chat-input, textarea');
                  if (i) { i.focus(); return 'ok'; } return 'gone';
                })()""", timeout=15)
                time.sleep(0.4)
            _eval(c, JS_CLEAR_COMPOSER, timeout=15)
            time.sleep(0.3)
            _eval(c, r"""(() => {
              const i = document.querySelector('#chat-input, textarea');
              if (i) { i.focus(); return 'ok'; } return 'gone';
            })()""", timeout=15)
            time.sleep(0.2)
            c.call("Input.insertText", {"text": message})
            ratio_js = JS_INSERT_RATIO.replace("__PLEN__", str(len(message)))
            ok, ratio = _wait(c, ratio_js, "100", tries=8, sleep=1.0, desc="insert")
            try:
                pct = int(ratio)
            except Exception:
                pct = 0
            if not (97 <= pct <= 115):
                print(f"ERROR: insert ratio {pct}%; message not sent")
                return 2
        body_before = int(_eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
        ok = False
        reason = ""
        for attempt in range(CAPACITY_ROUNDS + 1):
            # FOCUS FIX: re-query the textarea rect AFTER the insert (it grew)
            # and hard-verify focus before pressing Enter — an Enter dispatched
            # to <body> silently drops the message (WO-010 forensics).
            fp = _eval(c, JS_COMPOSER)  # #chat-input/textarea rect, live
            if not fp:
                print("ERROR: textarea vanished — login expired or page navigated")
                return 2
            f = json.loads(fp)
            c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": f["x"], "y": f["y"],
                                                 "button": "left", "clickCount": 1})
            c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": f["x"], "y": f["y"],
                                                 "button": "left", "clickCount": 1})
            time.sleep(0.5)
            focused = _eval(c, r"""(() => {
              const i = document.querySelector('#chat-input, textarea');
              return (i && document.activeElement === i) ? 'yes' : 'no';
            })()""", timeout=15)
            if focused != "yes":
                # last resort: DOM focus() then re-verify
                _eval(c, r"""(() => {
                  const i = document.querySelector('#chat-input, textarea');
                  if (i) { i.focus(); return 'ok'; } return 'gone';
                })()""", timeout=15)
                time.sleep(0.4)
            # the text may have been consumed by an earlier round — restore it
            clen = _eval(c, r"""(() => {
              const i = document.querySelector('#chat-input, textarea');
              return i ? String((i.value||'').length) : 'gone';
            })()""", timeout=15)
            if clen == "0":
                c.call("Input.insertText", {"text": message})
                time.sleep(0.5)
            for typ in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {
                    "type": typ, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            time.sleep(5)
            # outcome triage
            try:
                st = json.loads(_eval(c, JS_CAPACITY_STATE, timeout=15) or "{}")
            except Exception:
                st = {}
            if st.get("generating"):
                ok, reason = True, "generating"
                break
            cleared = _eval(c, r"""(() => {
              const i = document.querySelector('#chat-input, textarea');
              return i ? String((i.value||'').length) : 'gone';
            })()""", timeout=20)
            body_now = int(_eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
            if cleared in ("0", "gone") and body_now > body_before:
                ok, reason = True, "composer-cleared+grew"
                break
            if st.get("capacity") or st.get("hasCancel"):
                # RATE-LIMIT BAIL (22:29 forensics): grinding rounds while the
                # personal-limit dialog is up re-arms the cooldown — abort
                # instead of assaulting; the caller waits out the window.
                try:
                    limited_now = _eval(c, r"""(() => {
                              // 2026-09-10 fix: the limit text ALSO survives as stale
                      // TRANSCRIPT text after the cooldown lapses (inline in a
                      // message element, never removed) — only a LIVE modal blocks
                      // sending. Live = fixed-position overlay carrying the text.
                      for (const el of document.querySelectorAll('div,section')) {
                        const st = getComputedStyle(el);
                        if (st.position === 'fixed' && parseInt(st.zIndex || '0') >= 500) {
                          const lt = (el.innerText || '');
                          if (lt.includes('exceeds the personal limit') ||
                              lt.includes('try again 1 hour later')) return 'yes';
                        }
                      }
                      return 'no';
            })()""", timeout=15)
                except Exception:
                    limited_now = "no"
                if limited_now == "yes":
                    reason = "rate-limited (account cooldown) — aborting assault"
                    print(f"      [rate-limited] {reason}")
                    break
                # capacity popup rejected the send — gentle in-session assault
                # (never destroys the session: it holds 45+ min of live work)
                _eval(c, JS_CLICK_CANCEL, timeout=15)
                backoff = min(20 + 10 * attempt, 60)
                print(f"      [capacity] round {attempt}: popup cancelled — "
                      f"refocus + re-Enter in {backoff}s (in-session, work preserved)")
                time.sleep(backoff)
                continue
            # no popup, not generating, composer still holds text — try the
            # send-button fallbacks once, then next attempt round
            sb = _eval(c, JS_SEND_BUTTON)
            spt = None
            if sb:
                spt = json.loads(sb)
            if (not spt or spt.get("disabled")):
                try:
                    alt = _eval(c, r"""(() => {
                      const i = document.querySelector('#chat-input, textarea');
                      const form = i ? i.closest('form') : null;
                      if (!form) return '';
                      const btns = Array.from(form.querySelectorAll('button'))
                        .filter(b => !b.disabled && b.getBoundingClientRect().width > 0);
                      if (!btns.length) return '';
                      const b = btns[btns.length - 1];
                      const r = b.getBoundingClientRect();
                      return JSON.stringify({x: Math.round(r.x + r.width/2),
                                             y: Math.round(r.y + r.height/2)});
                    })()""", timeout=15)
                    if alt:
                        spt = json.loads(alt)
                except Exception:
                    spt = None
            if spt and not spt.get("disabled"):
                c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": spt["x"],
                                                    "y": spt["y"], "button": "left", "clickCount": 1})
                c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": spt["x"],
                                                    "y": spt["y"], "button": "left", "clickCount": 1})
                time.sleep(5)
            if attempt >= CAPACITY_ROUNDS:
                reason = f"not-sent after {attempt+1} attempts (cleared={cleared})"
        body_after = int(_eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
        # SERVER-SIDE COMMIT VERIFICATION (2026-09-12 lessons 63/65): the
        # composer-cleared+grew proof LIES under peak-capacity pressure —
        # Enters commit NULL message pairs (client stages the text optimistically,
        # server stores null content) and phantom /c/ URLs. Only the chats API
        # is truth. A send is VERIFIED only when the chat's LAST message is a
        # user message carrying real content (or an assistant turn already
        # generating on top of it).
        if ok:
            try:
                time.sleep(2)
                verify_js = r"""(async () => {
                  const m = location.href.match(/\/c\/([0-9a-f-]{36})/);
                  if (!m) return JSON.stringify({err: 'no-chat-url'});
                  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
                  const r = await fetch('/api/v1/chats/' + m[1], {credentials: 'include',
                    headers: tok ? {Authorization: 'Bearer ' + tok} : {}});
                  if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
                  const j = await r.json();
                  const msgs = ((j.chat || {}).history || {}).messages || {};
                  const byTs = Object.values(msgs).sort((a,b)=>(a.timestamp||0)-(b.timestamp||0));
                  const last = byTs[byTs.length-1] || null;
                  const prev = byTs[byTs.length-2] || null;
                  const cc = last ? (Array.isArray(last.content) ? last.content : [last.content]) : [];
                  const txt = JSON.stringify(cc);
                  const pc = prev ? JSON.stringify(Array.isArray(prev.content) ? prev.content : [prev.content]) : '';
                  // success: last=user-with-content, OR last=assistant (turn started)
                  // on top of a prev=user-with-content (the send landed, model responding)
                  const landed = (last && last.role === 'user' && txt.length > 10) ||
                                 (last && last.role === 'assistant' && prev && prev.role === 'user' && pc.length > 10);
                  return JSON.stringify({role: last ? last.role : null, len: txt.length,
                    nullish: txt.length <= 10, landed: !!landed});
                })()"""
                vr = json.loads(c.eval(verify_js, await_promise=True, timeout=30) or "{}")
                if vr.get("err"):
                    reason = "server-verify: " + vr["err"]
                    ok = False
                elif not vr.get("landed"):
                    reason = "server-null-commit (len=%s role=%s)" % (vr.get("len"), vr.get("role"))
                    ok = False
                # landed=True: last=user-with-content, or assistant turn already
                # consuming a content-bearing user message — server truth
            except Exception as e:
                reason = "server-verify-exc: " + str(e)[:70]
                ok = False
        print(f"message sent: {'VERIFIED' if ok else 'NOT VERIFIED'} ({reason}; "
              f"body {body_before}->{body_after})")
        _save({"action": "send", "name": name, "tab_id": tab["id"], "ts": int(time.time()),
               "msg_chars": len(message), "sent": ok, "kind": "continuation",
               "note": reason})
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

def _dispatch_lock():
    """Serialize ALL browser-driving commands (create/send/void).

    2026-09-09 23:23 forensics: two queue_watchers fired their tablost
    re-dispatches on the same 2-min cycle tick — the two concurrent create()
    flows fought over the same Chrome (interleaved model-selection clicks,
    racing inserts) and BOTH came back 'prompt sent: NOT VERIFIED'. The
    browser is a single shared resource: one dispatch at a time, others
    block here (flock released on process exit).
    """
    import fcntl
    lk = open(os.path.join(BASE, "flags", "dispatch.lock"), "w")
    fcntl.flock(lk, fcntl.LOCK_EX)
    return lk


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd in ("create", "send", "void"):
        _dispatch_lock()
    if cmd == "create":
        return create(sys.argv[2], sys.argv[3])
    if cmd == "check":
        return check(sys.argv[2])
    if cmd == "send":
        if len(sys.argv) < 4:
            print("usage: send <name> <message | @prompt-file>")
            return 1
        arg = sys.argv[3]
        import os.path as _p
        if arg.startswith("@") and _p.isfile(arg[1:]):
            msg = open(arg[1:], encoding="utf-8").read()
        else:
            msg = arg
        return send(sys.argv[2], msg)
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
    if cmd == "done":
        if len(sys.argv) < 3:
            print("usage: done <name> [note]")
            return 1
        return done(sys.argv[2], " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "completed")
    if cmd == "models":
        return models()
    if cmd == "sandboxes":
        return sandboxes(sys.argv[2] if len(sys.argv) > 2 else None)
    print("unknown command")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # crash exit code must differ from rc=1 ('session already live'):
        # recover_capacity treats 1 as recovered-elsewhere and would abort
        # the assault on a websocket timeout (2026-09-10 false positive).
        import traceback
        traceback.print_exc()
        sys.exit(4)
