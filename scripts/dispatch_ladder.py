#!/usr/bin/env python3
"""dispatch_ladder.py — saturation-window respawn ladder for one work order
(Task 84, 2026-10-18).

The 16:30Z+ saturation window ROLLS BACK fresh agent chats (two r4-w1
attempts destroyed server-side; established chats like mer-B survive).
Each attempt is cheap ("a destroyed session costs nothing, waiting costs
hours"). Ladder law:
  - create fresh (suffix rotates b,c,d,...)
  - monitor up to 6 cycles (30 min): streaming -> SUCCESS (stand down);
    landing -> void + next attempt; 'No response' -> light nudge
  - 8 attempts max, then stand down and notify

Launch: dfork_launch.py logs/dispatch_ladder.log <venv-py> dispatch_ladder.py
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
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
CYCLE = 300
MAX_ATTEMPTS = 8
POLLS_PER_ATTEMPT = 6
PROMPT = os.path.join(BASE, "worker-prompts", "pkt_r4-w1.md")
SUFFIXES = "bcdefghijk"


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def run(cmd, timeout=290):
    r = subprocess.run([sys.executable] + cmd, capture_output=True,
                       text=True, timeout=timeout, cwd=BASE)
    return (r.stdout or "").strip().splitlines()


def chat_state(cid_prefix):
    tab = channel.find_tab(cid_prefix)
    if tab is None:
        return {"tab": False}
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const streaming = ['Thinking', 'Generating', 'typing…', 'Thought Process'].some(m => body.includes(m));
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  const landing = body.includes('Need a assistant') || body.includes('Create anything you can imagine');
  return JSON.stringify({tab: true, streaming, stopBtn, noresp, landing, len: body.length});
})()
""", timeout=20)
        return json.loads(raw)
    except Exception as e:
        return {"tab": True, "err": str(e)[:80]}
    finally:
        cdp.close()


def adopt_live():
    """Adopt a LIVE r4-w1 session from the registry (a prior ladder run may
    have created one before dying — spawning a duplicate wastes a slot and
    creates the duplicate-worker class). Returns (name, chat) or None."""
    reg = os.path.join(FLAGS, "session_registry.jsonl")
    try:
        recs = [json.loads(l) for l in open(reg) if l.strip()]
    except Exception:
        return None
    # latest CREATE per name, invalidated by later void/done on that name
    latest = {}
    for r in recs:
        name = r.get("name") or ""
        if not name.startswith("payswap3-r4-w1"):
            continue
        act = r.get("action")
        if act in ("void", "done", "failed"):
            latest[name] = None
        elif act is None and r.get("sent") and r.get("url") and "/c/" in r["url"]:
            latest[name] = r
    for name, r in latest.items():
        if r is None:
            continue
        chat = r["url"].split("/c/")[-1].split()[0]
        log(f"adopting live session {name} ({chat[:8]})")
        return name, chat
    return None


def main():
    log(f"dispatch ladder online — {PROMPT}, {MAX_ATTEMPTS} attempts cap")
    outbox("R4-W1 dispatch ladder armed (saturation window; rolled-back "
           "chats respawn with the next suffix until one generates).")
    adopted = adopt_live()
    if adopted:
        name, cur_chat = adopted
        with open(os.path.join(FLAGS, "r4w1_current.json"), "w") as f:
            json.dump({"name": name, "chat": cur_chat,
                       "ts": int(time.time() * 1000)}, f)
        # monitor the adopted chat first; respawn only if it rolls back
        if monitor(name, cur_chat):
            return 0
    for attempt in range(MAX_ATTEMPTS):
        suffix = SUFFIXES[attempt] if attempt < len(SUFFIXES) else "z"
        name = f"payswap3-r4-w1{suffix}"
        log(f"attempt {attempt + 1}/{MAX_ATTEMPTS}: create {name}")
        cur_chat = None
        try:
            lines = run([os.path.join(BASE, "dispatch_worker.py"),
                         "create", name, PROMPT])
        except subprocess.TimeoutExpired:
            log("  create timed out (browser contention) — retry next cycle")
            time.sleep(CYCLE)
            continue
        for ln in lines:
            if "chat.z.ai/c/" in ln and "/c/" in ln:
                cur_chat = ln.split("/c/")[-1].split()[0]
        # 2026-10-18 fix: the create() stdout no longer prints the chat URL
        # (verdict line only) — read it from the session registry instead
        # (the create path appends a record carrying url + sent). Without
        # this, cur_chat stays None: the ladder never monitors the chat it
        # just created and burns suffixes blind.
        if not cur_chat:
            try:
                reg = os.path.join(FLAGS, "session_registry.jsonl")
                recs = [json.loads(l) for l in open(reg) if l.strip()]
                for r in reversed(recs):
                    if (r.get("name") == name and r.get("url")
                            and "/c/" in r["url"] and r.get("sent")):
                        cur_chat = r["url"].split("/c/")[-1].split()[0]
                        break
            except Exception:
                pass
        verdict = lines[-1] if lines else "no output"
        log(f"  chat={cur_chat or '?'} verdict: {verdict[:110]}")
        if cur_chat:
            # publish the current chat so auto_harvest can follow the ladder
            try:
                with open(os.path.join(FLAGS, "r4w1_current.json"), "w") as f:
                    json.dump({"name": name, "chat": cur_chat,
                               "ts": int(time.time() * 1000)}, f)
            except Exception:
                pass
        if not cur_chat:
            time.sleep(CYCLE)
            continue
        if monitor(name, cur_chat):
            return 0
    log("attempt cap reached — standing down")
    outbox("R4-W1 LADDER EXHAUSTED: saturation window destroyed every fresh "
           "chat. TL: re-arm when the window clears.")
    return 1


def monitor(name, cur_chat):
    """Poll one session up to POLLS_PER_ATTEMPT cycles. True = GENERATING."""
    for poll in range(POLLS_PER_ATTEMPT):
        time.sleep(CYCLE)
        st = chat_state(cur_chat[:8])
        if st.get("err"):
            log(f"  {name}: probe issue {st.get('err')}")
            continue
        if not st.get("tab"):
            log(f"  {name}: tab gone — treat as rollback")
            return False
        if st.get("streaming") or st.get("stopBtn"):
            log(f"  {name}: GENERATING — LADDER SUCCESS")
            outbox(f"R4-W1 LADDER SUCCESS: {name} ({cur_chat}) is "
                   f"GENERATING. TL: let it run; auto-harvest is armed.")
            return True
        if st.get("landing"):
            log(f"  {name}: ROLLED BACK — void + respawn")
            try:
                run([os.path.join(BASE, "dispatch_worker.py"), "void",
                     name, "saturation rollback (ladder respawn)"])
            except subprocess.TimeoutExpired:
                pass
            return False
        if st.get("noresp"):
            log(f"  {name}: queued — light nudge")
            try:
                run([os.path.join(BASE, "dispatch_worker.py"), "send",
                     name, "Begin the R4-W1 work order now (station "
                           "setup first). If already started, continue."])
            except subprocess.TimeoutExpired:
                pass
    return False


if __name__ == "__main__":
    sys.exit(main())
