#!/usr/bin/env python3
"""wave_dispatch_sentinel.py — capacity-gated wave dispatcher (2026-09-21).

The peak-hours gate rejects fresh agent sends with a capacity popup, and the
site's own retry shells default to GLM-5.2 (invalid per house law: workers
run GLM-5.3 + Full-Stack). Blind resubmit loops (peak_retry) therefore spawn
wrong-model shells. This sentinel pushes a wave through with CONTROLLED
churn instead:

  for each pending name (in argv order):
    rounds (bounded):
      1. probe the name's LAST registered chat: if its assistant message is
         generating/growing -> ADOPT it (a staged send came alive), done
      2. fresh patient_dispatch (GLM-5.3 + Full-Stack verified before the
         insert; PATIENT_TAB pins it away from live worker tabs)
      3. parse the post-send chat url from stdout
      4. watch that chat up to WATCH_S for an assistant turn that GROWS
         (batch_probe: CDP-free server truth; chat GET 500 = not accepted)
      5. generating -> register + flags/<name>-dispatched.marker, next name
         blocked  -> cadence sleep, next round (staged chats get adopted by
                     step 1 on later rounds if the platform ever fires them)

Usage:
  wave_dispatch_sentinel.py <name>:<prompt-file.md> [<name>:<prompt.md> ...]
                            [--every 180] [--watch 150] [--rounds 18]
Env: PATIENT_TAB (tab id prefix for patient_dispatch)

Exit 0 = every name generating; 3 = a name exhausted its rounds.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
LOG_PREFIX = time.strftime("%H:%M:%S")


def log(name, line):
    print(time.strftime("[%H:%M:%S]") + f" [{name}] {line}", flush=True)


def last_record(name):
    rec = None
    try:
        for line in open(REGISTRY):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("name") == name and d.get("action") != "void" and d.get("url"):
                rec = d
    except FileNotFoundError:
        pass
    return rec


def probe_chat(chat_id):
    """Return (ok, assistant_chars, generating, model_ok) via the batch store.

    model_ok: the chat's models list contains glm-5.3 (site-spawned retry
    shells default to glm-5.2 — those are never valid adoption targets).
    """
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(BASE, "batch_probe.py"), chat_id, "x"],
            capture_output=True, text=True, timeout=45)
        d = json.loads(out.stdout.strip().splitlines()[-1])
        models = (d.get("models") or [])
        model_ok = any("5.3" in str(m) for m in models)
        asst = [m for m in d.get("messages", []) if m.get("role") == "assistant"]
        if not asst:
            return True, 0, False, model_ok
        m = asst[-1]
        return True, int(m.get("chars") or 0), bool(m.get("generating")), model_ok
    except Exception:
        return False, 0, 0 and False or False, False


def chat_generating(chat_id, samples=2, gap=25, min_chars=2000):
    """True when the assistant turn is growing or already substantial,
    AND the chat runs the mandated glm-5.3 model."""
    ok1, c1, g1, m1 = probe_chat(chat_id)
    if not ok1 or not m1:
        return False
    if g1 or c1 >= min_chars:
        return True
    time.sleep(gap)
    ok2, c2, g2, m2 = probe_chat(chat_id)
    return bool(ok2 and m2 and (g2 or c2 > c1))


def register(name, chat_url, tab_id, prompt_file, prompt_chars):
    rec = {
        "name": name, "tab_id": tab_id, "url": chat_url,
        "ts": int(time.time()), "prompt_file": prompt_file,
        "prompt_chars": prompt_chars, "mode": "agents-tab",
        "model": "GLM-5.3", "skill": "Full-Stack",
        "insert_pct": 100, "sent": True,
        "note": "wave_dispatch_sentinel (lead): generation confirmed via batch store",
    }
    with open(REGISTRY, "a") as f:
        f.write(json.dumps(rec) + "\n")
    open(os.path.join(FLAGS, f"{name}-dispatched.marker"), "w").write(
        f"{chat_url} {int(time.time())}\n")


def tab_for_chat(chat_url):
    frag = chat_url.split("/c/")[-1][:8]
    for t in channel.list_tabs():
        if frag in (t.get("url") or ""):
            return t
    return None


def dom_state(chat_url):
    """Fast DOM signal from the tab sitting on the chat (None if no tab).
    Returns dict(stop=..., capacity=..., taLen=..., bodyLen=...)."""
    tab = tab_for_chat(chat_url)
    if not tab:
        return None
    try:
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            return json.loads(ws.eval(r"""JSON.stringify({
              stop: !!document.querySelector('[class*=stop]'),
              capacity: (document.body.innerText||'').includes('at capacity') || (document.body.innerText||'').includes('peak hours'),
              taLen: (document.querySelector('#chat-input, textarea')||{value:''}).value.length,
              bodyLen: (document.body.innerText||'').length
            })""", await_promise=False, timeout=12))
        finally:
            ws.close()
    except Exception:
        return None


def tab_hygiene():
    """2026-09-22 doctrine (the recurring tab-wedge): tabs left sitting on
    /c/<chat> pages after failed sends accumulate hung generation streams
    until the renderer dies (CDP connection timeouts). Every round starts
    from a HEALTHY pin: navigate the pinned tab to the light home page; if
    the renderer is already dead, close it and mint a fresh tab, updating
    the PATIENT_TAB pin in THIS process's environment (children inherit it
    at fork time). Returns a short status string for the log.

    2026-09-22 16:2x HARDENING (the prod031 home-page zombie): a dead
    renderer can park ON THE HOME PAGE — the URL-only 'pin already light'
    shortcut passed it while every patient_dispatch burned its full 560s
    in _reconnect retry loops (connect ok, Runtime.evaluate never
    answers). The light-pin branch now SMOKE-PROBES the renderer (eval
    '1', 8s) — a zombie is closed and replaced exactly like a chat-page
    corpse."""
    pin = (os.environ.get("PATIENT_TAB") or "").strip()
    home = "https://chat.z.ai/"
    try:
        tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    except Exception as e:
        return f"tab list failed ({str(e)[:40]})"
    tab = None
    if pin:
        tab = next((t for t in tabs if (t.get("id") or "").upper().startswith(pin.upper())), None)
    if tab is not None:
        url = tab.get("url") or ""
        dead = False
        if "chrome-error" in url or not url.startswith("https://chat.z.ai"):
            # 2026-09-23 (the 17h-outage wedge): an error page / off-domain
            # corpse is NEVER a valid pin — even one whose renderer evals
            # fine (the Task-108 VPN corpses answered evals on
            # chrome-error://chromewebdata while the lane starved).
            dead = True
        elif "/c/" not in url:
            # home page — smoke-probe the renderer TWICE (the 2026-09-23
            # lesson: a wedged renderer can answer ONE lucky probe — the
            # outage retry-storms wedge the main thread intermittently;
            # two consecutive evals with a gap discriminate reliably)
            try:
                c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=10)
                try:
                    c.eval("1", timeout=6)
                    time.sleep(1.5)
                    c.eval("1", timeout=6)
                    href = c.eval("location.href", timeout=6)
                    if "chrome-error" in str(href):
                        dead = True
                    else:
                        return "pin already light (double-probed)"
                finally:
                    c.close()
            except Exception:
                dead = True  # renderer dead/wedged — fall through to replacement
        else:
            # on a chat page: navigate home (best-effort)
            try:
                c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=12)
                try:
                    c.call("Page.navigate", {"url": home}, timeout=12)
                finally:
                    c.close()
                return "navigated pin home"
            except Exception:
                dead = True  # renderer dead — fall through to replacement
        if dead:
            # close the dead tab
            try:
                urllib.request.urlopen(
                    "http://localhost:9222/json/close/" + tab["id"], timeout=8).read()
            except Exception:
                pass
    # mint a fresh pinned tab
    try:
        r = urllib.request.urlopen(
            urllib.request.Request("http://localhost:9222/json/new", method="PUT"),
            timeout=12)
        t = json.loads(r.read().decode())
        new_id = t.get("id", "")
        time.sleep(1.5)
        for tb in channel.list_tabs():
            if tb.get("id") == new_id:
                c = channel.CDP(tb["webSocketDebuggerUrl"], timeout=15)
                try:
                    c.call("Page.navigate", {"url": home}, timeout=15)
                finally:
                    c.close()
                break
        # 2026-09-23 hardening: a minted pin must LOAD and RESPOND before it
        # is adopted — navigate alone proves nothing (the mint can land on a
        # chrome-error corpse or a wedged renderer). Settle, then probe; a
        # dead mint is closed and reported as failure (the next round's
        # hygiene mints again — never adopt an unverified pin).
        ok = False
        for _ in range(4):  # up to ~24s of settling for the SPA to come up
            time.sleep(6)
            try:
                for tb in channel.list_tabs():
                    if tb.get("id") == new_id:
                        c = channel.CDP(tb["webSocketDebuggerUrl"], timeout=10)
                        try:
                            href = c.eval("location.href", timeout=6)
                            c.eval("1", timeout=6)
                        finally:
                            c.close()
                        if href and "chat.z.ai" in str(href) and "chrome-error" not in str(href):
                            ok = True
                        break
                if ok:
                    break
            except Exception:
                continue
        if not ok:
            try:
                urllib.request.urlopen(
                    "http://localhost:9222/json/close/" + new_id, timeout=8).read()
            except Exception:
                pass
            return f"fresh pin {new_id[:8]} FAILED verification (closed; retry next round)"
        os.environ["PATIENT_TAB"] = new_id
        return f"fresh pin {new_id[:8]} (verified)"
    except Exception as e:
        return f"fresh-tab failed ({str(e)[:40]})"


def run_dispatch(name, prompt_file):
    """One patient_dispatch attempt; returns the post-send chat url or None."""
    env = dict(os.environ)
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(BASE, "patient_dispatch.py"),
             name, prompt_file],
            capture_output=True, text=True, timeout=560, env=env, cwd=BASE)
        txt = out.stdout + out.stderr
    except subprocess.TimeoutExpired:
        log(name, "patient_dispatch TIMEOUT")
        return None
    m = re.search(r"post-send url: (https://chat\.z\.ai/c/[0-9a-f-]+)", txt)
    tail = [l for l in txt.strip().splitlines() if l.strip()][-1:]
    log(name, "dispatch tail: " + (tail[0][:110] if tail else "?"))
    return m.group(1) if m else None


def main():
    args = sys.argv[1:]
    every, watch, rounds_max = 180, 150, 18
    def _opt(flag, default):
        if flag in args:
            i = args.index(flag)
            val = int(args[i + 1])
            del args[i:i + 2]
            return val
        return default
    every = _opt("--every", every)
    watch = _opt("--watch", watch)
    rounds_max = _opt("--rounds", rounds_max)
    jobs = []
    for a in args:
        if ":" in a:
            n, pf = a.split(":", 1)
            jobs.append((n, pf))
    if not jobs:
        print(__doc__)
        return 2
    log("daemon", f"wave={ [n for n, _ in jobs] } every={every}s watch={watch}s rounds={rounds_max}")
    # ROTATION MODE (2026-09-21 lesson: a name must never starve during a long
    # capacity outage — serial per-name exhaustion would skip later names once
    # earlier ones burn their rounds). One round per name per turn; a name that
    # hits generating leaves the rotation; a name that exhausts its per-name
    # budget goes to the back with its counter reset ONLY if other names still
    # progress (the daemon never exits while wave members remain). 
    state = {n: {"pf": pf, "rounds": 0, "done": False} for n, pf in jobs}
    while True:
        pending = [n for n in state if not state[n]["done"]]
        if not pending:
            break
        progressed_any = False
        for name in pending:
            s = state[name]
            prompt_file = s["pf"]
            prompt_chars = len(open(prompt_file, encoding="utf-8").read())
            s["rounds"] += 1
            rnd = s["rounds"]
            # 0. tab hygiene (2026-09-22 doctrine): every round starts from a
            #    light, responsive pinned tab — never a chat page left over
            #    from a failed send (hung streams wedge renderers).
            log(name, f"tab hygiene: {tab_hygiene()}")
            # 1. adopt a live earlier chat if it ever fires
            rec = last_record(name)
            if rec and rec.get("url"):
                cid = rec["url"].split("/c/")[-1]
                if chat_generating(cid, samples=1):
                    # 2026-09-22 lesson (prod030): the adopt path used to mark
                    # done WITHOUT register/marker — the follow-up chain
                    # (completion watch + redispatch watchers keyed on
                    # flags/<name>-dispatched.marker) never fired. Adoption
                    # must be registry + marker visible, exactly like the
                    # fresh-dispatch path.
                    register(name, rec["url"], rec.get("tab_id", "unknown-tab"),
                             prompt_file, prompt_chars)
                    log(name, f"ADOPTED earlier chat {cid[:8]} (now generating) — registered + marker written")
                    s["done"] = True
                    progressed_any = True
                    continue
            # 2. fresh dispatch
            url = run_dispatch(name, prompt_file)
            if not url:
                log(name, f"round {rnd}: no post-send url — cadence sleep")
                time.sleep(every)
                continue
            cid = url.split("/c/")[-1]
            log(name, f"round {rnd}: sent -> chat {cid[:8]}; watching {watch}s for generation")
            # 3. watch window: sample the batch store
            deadline = time.time() + watch
            gen = False
            blocked = False
            while time.time() < deadline:
                time.sleep(25)
                # fast path: DOM on the dispatch tab
                ds = dom_state(url)
                if ds and ds.get("stop"):
                    gen = True
                    break
                if ds and ds.get("capacity"):
                    blocked = True   # send rejected; window still burns for lag
                # server truth: batch store
                ok, c, g, mok = probe_chat(cid)
                if ok and mok and (g or c >= 400):
                    gen = True
                    break
                # chat GET failing or wrong model = not accepted; keep sampling
                # until the window closes (materialization lag is real)
            if blocked and not gen:
                log(name, f"round {rnd}: capacity popup on {cid[:8]} — blocked; cadence sleep {every}s")
                time.sleep(every)
                continue
            if gen:
                # confirm with a growth check
                if chat_generating(cid, samples=2, gap=20):
                    tab = tab_for_chat(url)
                    register(name, url, (tab or {}).get("id", "unknown-tab"),
                             prompt_file, prompt_chars)
                    log(name, f"GENERATING in {cid[:8]} — registered + marker written")
                    s["done"] = True
                    progressed_any = True
                    continue
                log(name, "growth unconfirmed — continuing to watch this round")
            else:
                log(name, f"round {rnd}: blocked (capacity gate) — cadence sleep {every}s")
                time.sleep(every)
            # per-name budget: surface + demote (rotation keeps it alive only
            # while others progress — the daemon cannot spin on one name alone)
            if s["rounds"] >= rounds_max and not progressed_any:
                log(name, f"budget exhausted ({rounds_max} rounds, no wave progress) — "
                          f"surfacing to lead; name stays pending for adoption")
                time.sleep(max(every, 300))
                s["rounds"] = 0  # reset: rotation continues (never starves)
    log("daemon", "whole wave generating")
    return 0


if __name__ == "__main__":
    sys.exit(main())
