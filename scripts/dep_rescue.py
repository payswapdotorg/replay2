#!/usr/bin/env python3
"""dep_rescue.py — TTL-wall + stalled-generation auto-recovery sentinel for DEP Wave A.

Doctrine (2026-09-15 Task 48):
- Workers implement inside ONE long uncommitted turn; committed content stays ~0
  until turn end. If the sandbox pod hits its ~2h22m TTL mid-turn, the turn hangs
  open and ALL work in it is lost.
- Recovery: detect (transcript frozen >= FROZEN_MIN) AND (pod expired/gone),
  then nudge the chat via the house send machinery (dispatch_worker.py send).
  A send after pod loss triggers a fresh generation that provisions a NEW pod
  with a full TTL window (proven by the Task 47 resume -> ws-cc1c7e45 flow).

Safety rails:
- NEVER nudge a healthy streaming worker (double condition: frozen + expired pod).
- Max NUDGES_MAX nudges per chat, spaced NUDGE_SPACING_S.
- Skip chats that already have a dep_watch completion marker.
- Memory-light: one CDP socket at a time, all closed after each probe.

Exit: 0 when all watched chats are complete or runtime budget exhausted.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "dep_rescue.log")
RUN_MAX_S = 6 * 3600          # 6h runtime budget
FROZEN_MIN = 20 * 60           # transcript unchanged this long = frozen
GRACE_S = 120                  # wait after expiry detected before nudging
NUDGE_SPACING_S = 12 * 60      # min spacing between nudges per chat
NUDGES_MAX = 3
VERIFY_WITHIN_S = 10 * 60      # transcript must grow within this after nudge
VERIFY_GROWTH = 300            # ... by at least this many chars

CHATS = {
    "dep-001": "4e2f61fd-5c76-4fce-b32b-110133cb8c0b",
    "dep-010": "5c355d3c-1aaa-40f0-826c-27207e0c81c4",
    "dep-020": "003f515c-c3e7-468b-8665-7e1463d7df2d",
}

NUDGE_TEXT = (
    "Continue your DEP work order now, exactly per the worker guide above in this "
    "chat. Your previous sandbox pod expired mid-work; this message provisions a "
    "fresh one. If /home/z/Zeck is missing or stale: re-clone "
    "https://github.com/payswapdotorg/Zeck.git and reset to base "
    "6fbe6cb4c3c15115f72b297700e09485f9bda050. Then implement your assigned "
    "surface, run the FULL verification battery, and deliver the completion "
    "report + tarball exactly per the delivery contract. Begin immediately."
)


def log(*args):
    line = time.strftime("[%H:%M:%S]") + " " + " ".join(str(a) for a in args)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def complete(name):
    return os.path.exists(os.path.join(FLAGS, f"{name}-complete.marker"))


def transcript_len(cid):
    """Live DOM text length of the chat's tab; None if tab missing."""
    for t in channel.list_tabs():
        if cid in (t.get("url") or ""):
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                try:
                    return int(c.eval("document.body.innerText.length",
                                      await_promise=False, timeout=15))
                finally:
                    c.close()
            except Exception as e:
                log(f"  {cid[:8]} transcript probe ERR: {str(e)[:60]}")
                return None
    return None


def pod_status(cid):
    """'Running' | 'gone' | 'unknown' via in-page workspaces API."""
    js = """
    (async () => {
      try {
        const r = await fetch('/api/v1/web-dev/workspaces/status', {
          method: 'POST', credentials: 'include',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({chat_id: '%s'})
        });
        const t = await r.text();
        return r.status + ' | ' + t.slice(0, 200);
      } catch (e) { return 'ERR | ' + String(e).slice(0, 80); }
    })()
    """ % cid
    for t in channel.list_tabs():
        if "chat.z.ai" in (t.get("url") or ""):
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
                try:
                    raw = c.eval(js, await_promise=True, timeout=30)
                finally:
                    c.close()
                s = str(raw)
                if s.startswith("200") and '"Running"' in s:
                    return "Running"
                if s.startswith("200") and ('"status":""' in s or '"pod":null' in s
                                            or '"pod":{}' in s):
                    return "gone"
                if s.startswith("4") or s.startswith("5"):
                    return "gone"
                return "unknown:" + s[:60]
            except Exception as e:
                log(f"  {cid[:8]} pod probe ERR: {str(e)[:60]}")
                return "unknown"
    return "unknown"


def house_send(name, text):
    """Send via the house machinery (capacity assault + verification)."""
    cmd = [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "send", name, text]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=420, cwd=BASE)
        out = (p.stdout or "") + (p.stderr or "")
        log(f"  house send rc={p.returncode} out={out[-400:]}")
        return p.returncode == 0
    except Exception as e:
        log(f"  house send EXC {str(e)[:100]}")
        return False


def main():
    st = {n: {"len": None, "since": time.time(), "nudges": 0, "last_nudge": 0,
              "expired_since": None, "verifying_until": 0}
          for n in CHATS}
    t0 = time.time()
    log(f"rescue sentinel up; chats={list(CHATS)}")
    while time.time() - t0 < RUN_MAX_S:
        live = [n for n in CHATS if not complete(n)]
        if not live:
            log("all chats complete — exiting")
            return 0
        for name in live:
            cid = CHATS[name]
            s = st[name]
            n = transcript_len(cid)
            ps = pod_status(cid)
            now = time.time()
            if n is not None and n != s["len"]:
                s["len"] = n
                s["since"] = now          # streaming: refresh frozen clock
            frozen_s = now - s["since"]
            if ps == "Running":
                s["expired_since"] = None
            elif s["expired_since"] is None:
                s["expired_since"] = now
                log(f"{name}: pod NOT Running ({ps}) — expiry clock started")
            log(f"{name}: len={n} frozen={int(frozen_s)}s pod={ps} nudges={s['nudges']}")
            # nudge condition: frozen long enough AND pod gone AND spacing OK
            if (frozen_s >= FROZEN_MIN and s["expired_since"] is not None
                    and now - s["expired_since"] >= GRACE_S
                    and s["nudges"] < NUDGES_MAX
                    and now - s["last_nudge"] >= NUDGE_SPACING_S
                    and now > s["verifying_until"]):
                log(f"{name}: STALL+EXPIRY confirmed — nudging (#{s['nudges']+1})")
                if house_send(name, NUDGE_TEXT):
                    s["nudges"] += 1
                    s["last_nudge"] = now
                    s["verifying_until"] = now + VERIFY_WITHIN_S
                    s["since"] = now       # restart frozen clock for verification
                    s["len_at_nudge"] = n or s["len"] or 0
                    log(f"{name}: nudge sent (baseline len {s['len_at_nudge']}); "
                        f"verifying growth for {VERIFY_WITHIN_S}s")
                else:
                    log(f"{name}: house send FAILED — will retry next cycle")
            elif s["verifying_until"] and now < s["verifying_until"]:
                base = s.get("len_at_nudge") or 0
                if n is not None and n >= base + VERIFY_GROWTH:
                    log(f"{name}: VERIFIED generation running (len {n} >= {base}+{VERIFY_GROWTH})")
                    s["verifying_until"] = 0
            elif s["verifying_until"] and now >= s["verifying_until"] and s["verifying_until"]:
                # verification window expired without growth
                log(f"{name}: verification window EXPIRED without growth — "
                    f"nudge #{s['nudges']} failed")
                s["verifying_until"] = 0
        time.sleep(90)
    log("runtime budget exhausted — exiting")
    return 4


if __name__ == "__main__":
    sys.exit(main())
