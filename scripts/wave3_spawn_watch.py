#!/usr/bin/env python3
"""wave3_spawn_watch.py — wave-3 capacity-siege manager.

Context (2026-10-05 ~13:30Z): all three wave-3 sends landed as PHANTOMS —
the DOM verify said VERIFIED but server-side the chats don't exist
(absent from /api/v1/chats/list; detail GET 500s). GLM-5.3 is at platform
capacity (peak hours). The W1 dispatch process is in its designed assault
loop (Cancel + re-pick + resend, per-round server-verify, supervisor-
guarded via capacity_recover.json + recover_capacity.py).

This watch is the TL's gentle complement:
  - every ROUND_S, server-side list check: which wave-3 names have LIVE
    chats (in list AND a user message >100 chars in the detail tree)?
  - the FIRST name that goes live = the capacity window opened → for every
    still-phantom name: void + re-fire its dispatch (detached create).
  - rails: at most one re-fire per name per REFIRE_COOLDOWN_S; a re-fire
    only while some wave-3 name is live or the W1 assault chain is alive
    (never a blind loop into the wall); hard stop after WINDOW_S.

Doctrine: void+re-dispatch over kicks (2026-10-03 hazard law); server-side
existence is the only truth (§9f); the assault machinery owns the fighting.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(HERE, "flags")
LOG = os.path.join(HERE, "logs", "wave3_spawn_watch.log")
ROUND_S = 60
REFIRE_COOLDOWN_S = 600
WINDOW_S = 6 * 3600
NAMES = ["unicom-w1-003", "unicom-w2-003", "unicom-w3-003"]
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")

log = lambda m: print(f"[wave3 {time.strftime('%H:%M:%S')}] {m}", flush=True)


def registry_urls():
    """name → newest sent=True url (latest record wins)."""
    out = {}
    try:
        with open(REGISTRY) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("name") in NAMES and r.get("sent") and r.get("url"):
                    if r.get("action") != "void":
                        out[r["name"]] = r["url"]
    except FileNotFoundError:
        pass
    return out


def live_chats(urls):
    """{name: bool} — chat exists server-side with a real user message."""
    try:
        data = chats_http.api("/api/v1/chats/list?limit=100")
    except Exception as e:
        log(f"list probe failed ({e!r}) — treating all as unknown")
        return {}
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    ids = {it.get("id") or "" for it in items}
    out = {}
    for name, url in urls.items():
        cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
        if cid not in ids:
            out[name] = False
            continue
        try:
            d = chats_http.api(f"/api/v1/chats/{cid}")
            rec = d.get("data", d)
            inner = rec.get("chat", {}) or rec
            msgs = (inner.get("history", {}) or {}).get("messages", {})
            if isinstance(msgs, dict):
                msgs = list(msgs.values())
            userlen = max((len(m.get("content") or "")
                           for m in msgs if m.get("role") == "user"), default=0)
            out[name] = userlen > 100
        except Exception:
            out[name] = False  # in-list but detail flapping → treat as live-ish
            out[name] = cid in ids  # fall back to list membership
    return out


def void_and_refire(name, reason):
    log(f"{name}: VOID + re-dispatch ({reason})")
    subprocess.run([sys.executable, os.path.join(HERE, "dispatch_worker.py"),
                    "void", name, reason],
                   capture_output=True, timeout=180, cwd=HERE)
    subprocess.Popen(
        [sys.executable, os.path.join(HERE, "dispatch_worker.py"), "create",
         name, os.path.join(HERE, "worker-prompts", f"{name}.md")],
        stdout=open(os.path.join(HERE, "logs", f"dispatch-{name}.log"), "a"),
        stderr=subprocess.STDOUT, start_new_session=True, cwd=HERE)


def assault_alive(name):
    """the dispatch create process OR the supervisor's recover chain lives."""
    try:
        out = subprocess.run(["pgrep", "-af", f"dispatch_worker.py create {name}"],
                             capture_output=True, text=True, timeout=10)
        if out.stdout.strip():
            return True
        out = subprocess.run(["pgrep", "-af", "recover_capacity"],
                             capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:
        return False


def main():
    log(f"armed — {ROUND_S}s rounds, watching {len(NAMES)} wave-3 lanes")
    fired_at = {}
    window_end = time.time() + WINDOW_S
    while time.time() < window_end:
        urls = registry_urls()
        if not urls:
            log("no wave-3 registry records yet — waiting")
            time.sleep(ROUND_S)
            continue
        live = live_chats(urls)
        if live:
            log("state: " + ", ".join(f"{n.split('-')[1]}={'LIVE' if v else 'phantom'}"
                                      for n, v in live.items()))
        n_live = sum(1 for v in live.values() if v)
        window_open = n_live > 0  # someone landed → the capacity window opened
        w1_assault = assault_alive("unicom-w1-003")
        for name in NAMES:
            if name not in live or live[name]:
                continue  # unknown or already live
            cooled = time.time() - fired_at.get(name, 0) >= REFIRE_COOLDOWN_S
            if window_open and cooled:
                void_and_refire(name, "phantom /c/ URL — window opened, refiring (wave3 watch)")
                fired_at[name] = time.time()
        # canary revival: nobody has landed and W1's assault chain died
        # (create exits + supervisor's recover_capacity also gone) → void the
        # stale record (a failed/unsent create record blocks fresh creates —
        # "already exists") and re-fire the assault; NEVER fire w2/w3 into a
        # closed window
        if not window_open and not w1_assault and not live.get("unicom-w1-003") \
                and time.time() - fired_at.get("unicom-w1-003", 0) >= REFIRE_COOLDOWN_S:
            log("unicom-w1-003: assault chain dead + still phantom — canary revival (void + re-fire)")
            void_and_refire("unicom-w1-003", "assault chain dead + phantom — canary revival (wave3 watch)")
            fired_at["unicom-w1-003"] = time.time()
        if live and all(live.get(n) for n in NAMES):
            log("ALL WAVE-3 LANES LIVE server-side — watch complete")
            open(os.path.join(FLAGS, "wave3_spawn_watch_done"), "w").write(
                str(int(time.time())))
            return 0
        time.sleep(ROUND_S)
    log("window expired")
    return 1


if __name__ == "__main__":
    sys.exit(main())
