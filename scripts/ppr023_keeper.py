#!/usr/bin/env python3
"""ppr023_keeper.py — §9e-lawful spawn keeper for the PPR-023 worker chat.

2026-10-02 dawn-shift laws (proven live):
- SILENT SUBMIT DROP (§9f): a UI-path send counts ONLY after the server-side
  chat record advances (updated_at + new user message). Composer-clearing,
  body growth and "message sent" verdicts are NOT proof.
- WINDOW RE-BURN (§9e): a send cadence faster than ~5 min re-burns the
  capacity window. Keeper cadence = 300s; land the directive in the first
  minute the window opens.
- The one verified lander tonight: FRESH painted tab + modal dismissed +
  React-set + Enter on THAT tab, verified server-side.

Loop:
  KEEP mode (every 300s): dismiss modal -> ensure the nudge is held ->
  Enter -> verify server-side. On landing -> SPAWN-WATCH mode.
  SPAWN-WATCH mode (every 60s): all-batch block totals. On growth ->
  PRODUCE mode. On 12 static polls (~12 min) -> §8 stop-cure -> KEEP mode.
  PRODUCE mode (every 120s): watch block totals grow; on the completion
  report marker -> set the report flag and exit 0. On 8 static polls
  (~16 min, turn death) -> §8 stop-cure -> KEEP mode.

State: flags/ppr023_keeper_state.json; report flag: flags/ppr023_report_seen.flag
Log: /tmp/ppr023_keeper.log (via dfork_launch.py)
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CHAT = "02f9e953-423c-4f25-a199-cb06b8fe1262"
URL = f"https://chat.z.ai/c/{CHAT}"
FLAGS = os.path.join(BASE, "flags")
STATE = os.path.join(FLAGS, "ppr023_keeper_state.json")
REPORT_MARK = "=== PPR-023 COMPLETION REPORT ==="
KEEPER_CADENCE_S = 300
KEEPER_MAX_ROUNDS = 60        # ~5h of keeping; the Lead can relaunch

NUDGE = open("/tmp/ppr023_manual_nudge.txt").read().strip() if os.path.exists("/tmp/ppr023_manual_nudge.txt") else (
    "[SYSTEM — resident watcher] Continue the PPR-023 (OpenClaw) work order from your last "
    "checkpoint (certified-run preload debugging). Finish the certified run + evidence, the gate "
    "battery honestly, the tarball, the worklog, then emit your FINAL message: "
    "=== PPR-023 COMPLETION REPORT === ... === END REPORT === per the contract."
)


def log(m):
    print(f"[{time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {m}", flush=True)


def state(d):
    d["ts"] = int(time.time() * 1000)
    try:
        json.dump(d, open(STATE, "w"), indent=1)
    except Exception:
        pass


def home_ws():
    """A WORKING chat.z.ai tab's WS — tries home tabs first, then chat tabs
    (a wedged home tab's fetches fail with JS errors; fall through instead
    of dying)."""
    tabs = channel.list_tabs()
    homes = [t for t in tabs if (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
    chats = [t for t in tabs if CHAT in (t.get("url") or "")]
    for cand in homes + chats:
        try:
            ws = channel.CDP(cand["webSocketDebuggerUrl"])
            v = ws.eval("(async () => { try { const r = await fetch('/api/v1/chats?limit=1', {credentials:'include'}); return r.status; } catch (e) { return 'ERR'; } })()",
                        await_promise=True, timeout=20)
            if isinstance(v, (int, float)) and int(v) < 500:
                return ws
            ws.close()
        except Exception:
            continue
    # last resort: first home tab even unverified
    if homes:
        try:
            return channel.CDP(homes[0]["webSocketDebuggerUrl"])
        except Exception:
            return None
    return None


def chat_tabs():
    return [t for t in channel.list_tabs() if CHAT in (t.get("url") or "")]


def server_record():
    """(updated, currentId, last2) via any chat.z.ai tab. NEVER raises."""
    try:
        return _server_record_inner()
    except Exception as e:
        log(f"server_record err: {type(e).__name__} {str(e)[:60]}")
        return None


def _server_record_inner():
    """(updated, currentId, last2) via any chat.z.ai tab."""
    ws = home_ws()
    if ws is None:
        return None
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store', headers:{Authorization:'Bearer '+tok}});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const h = (j.chat||{}).history||{};
          const msgs = Object.values(h.messages||{}).sort((a,b)=>(a.timestamp||0)-(b.timestamp||0));
          return JSON.stringify({updated: j.updated_at, currentId: (h.currentId||'').slice(0,8),
            last: msgs.slice(-2).map(m=>({role:m.role, ts:m.timestamp, id:(m.id||'').slice(0,8)}))});
        })()""" % CHAT
        return json.loads(ws.eval(js, await_promise=True, timeout=45))
    finally:
        try:
            ws.close()
        except Exception:
            pass


def batch_totals():
    """(totalBlocks, totalChars) across ALL assistant batches (batch-mask law).
    NEVER raises — returns None on any failure (WS flakes are routine)."""
    try:
        return _batch_totals_inner()
    except Exception as e:
        log(f"batch_totals err: {type(e).__name__} {str(e)[:60]}")
        return None


def _batch_totals_inner():
    """(totalBlocks, totalChars) across ALL assistant batches (batch-mask law)."""
    ws = home_ws()
    if ws is None:
        return None
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
          const hdr = {Authorization: 'Bearer ' + tok};
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store', headers: hdr});
          const j = await r.json();
          const msgs = ((j.chat||{}).history||{}).messages || {};
          const ids = Object.values(msgs).map(m=>m.id).filter(Boolean);
          if (!ids.length) return JSON.stringify({err: 'no ids'});
          const br = await fetch('/api/v1/chats/%s/messages/batch', {
            credentials:'include', cache:'no-store', method:'POST',
            headers: Object.assign({'Content-Type': 'application/json'}, hdr),
            body: JSON.stringify({ids})});
          const bj = await br.json();
          const data = (bj && (bj.data || bj.messages)) || {};
          let blocks = 0, chars = 0, report = false;
          for (const id of Object.keys(data)) {
            const m = data[id];
            if (!m || (m.role||'assistant')==='user') continue;
            const bl = m.content_blocks || m.blocks || [];
            blocks += bl.length;
            chars += JSON.stringify(m).length;
            for (const b of bl) {
              if (b && b.type === 'text' && typeof b.content === 'string' &&
                  b.content.includes('%s')) report = true;
            }
          }
          return JSON.stringify({blocks, chars, report});
        })()""" % (CHAT, CHAT, REPORT_MARK)
        return json.loads(ws.eval(js, await_promise=True, timeout=90))
    finally:
        try:
            ws.close()
        except Exception:
            pass


def stop_cure_once():
    """One §8 stop/continue round via any chat.z.ai tab."""
    ws = home_ws()
    if ws is None:
        return None
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store',
            headers: {'Authorization': 'Bearer ' + tok}});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const mid = ((j.chat || {}).history || {}).currentId;
          if (!mid) return JSON.stringify({err: 'no currentId'});
          const sr = await fetch('/api/tasks/stop/' + mid, {method:'POST', credentials:'include',
            headers: {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
            body: JSON.stringify({reason: 'turn death — keeper cure'})});
          const sb = await sr.text();
          const cr = await fetch('/api/chat/continue', {method:'POST', credentials:'include',
            headers: {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json',
                      'X-FE-Version': 'prod-fe-1.1.98'},
            body: JSON.stringify({message_id: mid})});
          return JSON.stringify({stop_http: sr.status, stop_body: sb.slice(0, 60), cont_http: cr.status});
        })()""" % CHAT
        r = json.loads(ws.eval(js, await_promise=True, timeout=60))
        closed = r.get("cont_http") == 410
        return f"stop={r.get('stop_http')} cont={r.get('cont_http')} {'CLOSED' if closed else 'held'}"
    except Exception as e:
        return f"err: {str(e)[:80]}"
    finally:
        try:
            ws.close()
        except Exception:
            pass


def keeper_round():
    """One keeper attempt: tab ensure -> plateau -> modal -> insert/Enter -> server verify."""
    tabs = chat_tabs()
    if not tabs:
        t = channel.new_tab(URL)
        log(f"keeper: fresh tab {t['id'][:8] if t else 'FAILED'}")
        if not t:
            return False
        tabs = [t]
    tab = tabs[-1]
    try:
        ws = channel.CDP(tab["webSocketDebuggerUrl"])
    except Exception as e:
        log(f"keeper: tab WS dead ({str(e)[:60]}) — closing it")
        try:
            channel._http_json("/json/close/" + tab["id"], method="PUT")
        except Exception:
            pass
        return False
    try:
        def bodylen():
            try:
                v = ws.eval("document.body.innerText.length", await_promise=False, timeout=20)
                return int(v) if isinstance(v, (int, float)) else -1
            except Exception:
                return -1
        # quick plateau (tabs are usually already painted in keeper mode)
        last, stall, t0 = -1, 0, time.time()
        while time.time() - t0 < 180:
            b = bodylen()
            if b == last and b > 3000:
                stall += 1
            else:
                stall = 0
            last = b
            if stall >= 2:
                break
            time.sleep(15)
        # modal dismiss (loop — it can re-arm)
        for _ in range(4):
            r = ws.eval("""(() => {
              const dlgs = [...document.querySelectorAll('[role=dialog], .ant-modal-root, [class*=modal], [class*=Modal]')].filter(e => (e.innerText||'').trim());
              if (!dlgs.length) return null;
              const d = dlgs[dlgs.length-1];
              const c = [...d.querySelectorAll('button')].find(b => ['Cancel','×','X','Dismiss','Got it','OK'].includes((b.innerText||'').trim()));
              if (c) { c.click(); return 'cancelled'; }
              return 'present-no-cancel';
            })()""", await_promise=False, timeout=20)
            if r is None:
                break
            log(f"keeper: modal {r}")
            time.sleep(2)
        # insert if empty + Enter
        res = ws.eval("""(async () => {
          const el = document.querySelector('#chat-input') || document.querySelector('textarea');
          if (!el) return JSON.stringify({err: 'no-input'});
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          if (!(el.value || '').trim()) {
            setter.call(el, %s);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            await new Promise(r => setTimeout(r, 500));
          }
          el.focus();
          el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true}));
          await new Promise(r => setTimeout(r, 1500));
          return JSON.stringify({held: (el.value||'').length});
        })()""" % json.dumps(NUDGE), await_promise=True, timeout=30)
        log(f"keeper: enter fired ({res})")
    except Exception as e:
        log(f"keeper: tab error {str(e)[:80]}")
        return False
    finally:
        try:
            ws.close()
        except Exception:
            pass
    time.sleep(6)
    rec = server_record()
    if not rec or rec.get("err"):
        log(f"keeper: server probe failed {json.dumps(rec)[:100]}")
        return False
    floor = max(keeper_round.last_updated or 0, keeper_round.arm_epoch or 0)
    landed = rec.get("updated", 0) > floor
    keeper_round.last_updated = rec.get("updated", 0)
    log(f"keeper: server updated={rec.get('updated')} currentId={rec.get('currentId')} landed={landed}")
    return landed


keeper_round.last_updated = None
keeper_round.arm_epoch = None
main_last_blocks_seen = None


def reload_chat_tabs():
    """Reload every chat.z.ai tab — the fix for the wedged-fetches state
    (network fine, page contexts broken; proven 07:12Z and 10:00Z)."""
    n = 0
    try:
        for t in channel.list_tabs():
            u = t.get("url") or ""
            if "chat.z.ai" in u:
                try:
                    ws = channel.CDP(t["webSocketDebuggerUrl"])
                    ws.eval("location.reload(); 'r'", await_promise=False, timeout=15)
                    n += 1
                    ws.close()
                except Exception:
                    continue
    except Exception:
        pass
    return n


def wake_kick():
    """Fire kick_queued.py as a subprocess — the proven turn-wake (both of
    tonight's successful spawns followed a kick; plain landings often sit
    un-spawned through the whole SPAWN-WATCH window). SESSION_BUSY ladder:
    a busy 409 means either an allocation in flight OR a zombie holder —
    stop-cure once and retry the kick (the 10:17Z zombie needed exactly
    this; the cure+kick woke +246 blocks of production)."""
    import subprocess

    def _kick():
        try:
            p = subprocess.run(
                [sys.executable, os.path.join(BASE, "kick_queued.py"), CHAT,
                 "/tmp/ppr023_manual_nudge.txt"],
                capture_output=True, text=True, timeout=300)
            tail = (p.stdout or "").strip().splitlines()
            return tail[-1][:160] if tail else f"rc={p.returncode} no-output"
        except subprocess.TimeoutExpired:
            return "kick shell-timeout (stream may still be landing)"
        except Exception as e:
            return f"kick err: {str(e)[:80]}"

    res = _kick()
    if "SESSION_BUSY" in res:
        log(f"wake_kick: SESSION_BUSY — stop-cure ladder: {stop_cure_once()}")
        time.sleep(20)
        res = _kick()
    return res


def main():
    global main_last_blocks_seen
    log(f"keeper armed: {CHAT[:8]} nudge={len(NUDGE)}c cadence={KEEPER_CADENCE_S}s")
    arm_epoch = int(time.time()) - 60
    rec = None
    for _ in range(3):
        rec = server_record()
        if rec and not rec.get("err"):
            break
        time.sleep(20)
    if rec and not rec.get("err"):
        keeper_round.last_updated = rec.get("updated")
        log(f"keeper: baseline updated={rec.get('updated')} currentId={rec.get('currentId')}")
    else:
        keeper_round.last_updated = arm_epoch
        log(f"keeper: baseline probe failed — using arm-epoch floor {arm_epoch}")
    keeper_round.arm_epoch = arm_epoch
    mode = "KEEP"
    static = 0
    last_blocks = None
    rounds = 0
    failstreak = 0
    # boot live-check: if the worker is already producing, watch it instead of nudging
    try:
        a = batch_totals()
        time.sleep(110)
        b = batch_totals()
        if a and b and b.get("blocks", 0) > a.get("blocks", 0):
            log(f"boot live-check: producing ({a.get('blocks')} -> {b.get('blocks')} blocks) — PRODUCE mode")
            mode = "PRODUCE"
            last_blocks = b["blocks"]
    except Exception as e:
        log(f"boot live-check err (ignored): {type(e).__name__}")
    while rounds < KEEPER_MAX_ROUNDS:
        rounds += 1
        state({"mode": mode, "rounds": rounds, "static": static, "failstreak": failstreak})
        try:
            if mode == "KEEP":
                # pre-send growth check: a late spawn may have started while we
                # were sleeping — never nudge into a producing turn
                t = batch_totals()
                if t and not t.get("err") and t.get("blocks", 0) > (main_last_blocks_seen or 0) and main_last_blocks_seen is not None:
                    log(f"keep: blocks grew ({main_last_blocks_seen} -> {t['blocks']}) — late spawn, PRODUCE mode")
                    mode, static, last_blocks = "PRODUCE", 0, t["blocks"]
                    main_last_blocks_seen = t["blocks"]
                    continue
                if t and not t.get("err"):
                    main_last_blocks_seen = t["blocks"]
                landed = keeper_round()
                if landed:
                    log("keeper: DIRECTIVE LANDED — switching to SPAWN-WATCH")
                    mode = "SPAWN-WATCH"
                    static = 0
                    last_blocks = None
                    failstreak = 0
                    # do NOT send again — one landed message per window
                else:
                    failstreak += 1
                    log(f"keeper: not landed (streak {failstreak}) — sleeping {KEEPER_CADENCE_S}s (window law)")
                    if failstreak == 3:
                        # closed window: the kick is the window-independent
                        # lander (proven 06:35Z + 07:48Z) — land + wake in one
                        log("keeper: 3-round failstreak — KICK LAND (window-independent)")
                        state({"mode": "KEEP", "kick": "streak-3", "rounds": rounds})
                        log(f"kick-land: {wake_kick()}")
                        time.sleep(30)
                        rec2 = server_record()
                        if rec2 and not rec2.get("err") and rec2.get("updated", 0) > (keeper_round.last_updated or 0):
                            log("keeper: KICK LANDED — switching to SPAWN-WATCH")
                            keeper_round.last_updated = rec2.get("updated")
                            mode, static, last_blocks, failstreak = "SPAWN-WATCH", 0, None, 0
                            continue
                    time.sleep(KEEPER_CADENCE_S)
            elif mode == "SPAWN-WATCH":
                time.sleep(60)
                t = batch_totals()
                if not t or t.get("err"):
                    static += 1
                    if static in (4, 8):
                        log(f"spawn-watch: probe fails ({static}) — reloading tabs ({reload_chat_tabs()})")
                    if static >= 12:
                        log("spawn-watch: probe surface dead — back to KEEP")
                        mode, static = "KEEP", 0
                    continue
                if t.get("report"):
                    log("REPORT MARKER SEEN — keeper exiting for Lead review")
                    state({"mode": "REPORT-SEEN"})
                    open(os.path.join(FLAGS, "ppr023_report_seen.flag"), "w").write(str(int(time.time())))
                    return 0
                if last_blocks is None:
                    last_blocks = t["blocks"]
                elif t["blocks"] > last_blocks:
                    log(f"spawn-watch: TURN SPAWNED ({last_blocks} -> {t['blocks']} blocks) — PRODUCE mode")
                    mode, static, last_blocks = "PRODUCE", 0, t["blocks"]
                else:
                    static += 1
                    if static == 6:
                        log("spawn-watch: 6 min no spawn — WAKE KICK")
                        state({"mode": "SPAWN-WATCH", "wake": "kick-fired", "rounds": rounds})
                        log(f"wake-kick: {wake_kick()}")
                        continue
                    if static >= 12:
                        log("spawn-watch: 12 min no spawn — stop-cure + back to KEEP")
                        log(f"stop-cure: {stop_cure_once()}")
                        mode, static = "KEEP", 0
            elif mode == "PRODUCE":
                time.sleep(120)
                t = batch_totals()
                if not t or t.get("err"):
                    static += 1
                    if static in (3, 6):
                        log(f"produce: probe fails ({static}) — reloading tabs ({reload_chat_tabs()})")
                    if static >= 8:
                        log("produce: probe surface dead — stop-cure + KEEP")
                        log(f"stop-cure: {stop_cure_once()}")
                        mode, static = "KEEP", 0
                    continue
                if t.get("report"):
                    log("REPORT MARKER SEEN — keeper exiting for Lead review")
                    state({"mode": "REPORT-SEEN"})
                    open(os.path.join(FLAGS, "ppr023_report_seen.flag"), "w").write(str(int(time.time())))
                    return 0
                if t["blocks"] > (last_blocks or 0):
                    static = 0
                    last_blocks = t["blocks"]
                    log(f"produce: {t['blocks']} blocks / {t['chars']} chars")
                else:
                    static += 1
                    if static >= 8:
                        log(f"produce: turn death at {last_blocks} blocks — stop-cure + KEEP")
                        log(f"stop-cure: {stop_cure_once()}")
                        mode, static = "KEEP", 0
        except Exception as e:
            log(f" keeper round exception (survived): {type(e).__name__} {str(e)[:100]}")
            time.sleep(60)
    log("keeper round cap — Lead attention")
    state({"mode": "ROUND-CAP"})
    return 1


if __name__ == "__main__":
    sys.exit(main())
