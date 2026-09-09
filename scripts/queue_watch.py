#!/usr/bin/env python3
"""queue_watch.py <name> <tab-prefix> <marker> — resident watch for a queued/running worker session.

State machine (two-state capacity protocol + operator assault policy):
- ACCEPTED (URL /c/<id>, prompt in transcript) + capacity popup: NEVER touch
  the dialog — the task is queued server-side; the popup is cosmetic.
- Tab LOST or URL rolled home (the site destroys queued sessions during
  peaks): re-dispatch via dispatch_worker.create (full assault loop).
- Generating: watch for completion (marker count >= 2: prompt echo + answer).
- Complete: write flags/<name>-complete.marker and exit 0.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/my-project/scripts")
import channel
import dispatch_worker as dw

BASE = "/home/z/my-project/scripts"
FLAGS = os.path.join(BASE, "flags")

# per-name spec files (multi-watch): flags/queue_watch.spec.<name> — the
# supervisor iterates all of them; each watcher owns exactly one session.
SPEC_PATH = os.path.join(FLAGS, "queue_watch.spec.{name}")
HB_PATH = os.path.join(FLAGS, "queue_watch_heartbeat.{name}")

# staleness-assault policy (2026-09-09 forensics): a session stuck in
# queued-capacity NEVER self-recovered (2/2 data points: 49cda388 destroyed
# by the site after ~1h; fe7a9812 sat 2h10m then needed destruction anyway,
# and the fresh re-dispatch immediately got clean capacity). Waiting for the
# site to kill the session just burns wall-clock — assault it ourselves.
STUCK_ASSAULT_AFTER = 5400   # s of queued-capacity with zero progress
STUCK_ASSAULT_MAX = 3        # then keep waiting (peaks do end eventually)


def write_spec(name, tab_prefix, marker):
    """Keep the supervisor-restart contract fresh: the spec must always name
    the CURRENTLY-WATCHED tab (it is refreshed after every re-dispatch) so a
    supervisor restart resumes watching the live session instead of a dead
    tab and wrongly triggering another assault."""
    try:
        open(SPEC_PATH.format(name=name), "w").write(json.dumps(
            {"name": name, "tab_prefix": tab_prefix, "marker": marker,
             "pid": os.getpid()}) + "\n")
    except Exception:
        pass


def heartbeat(name):
    try:
        with open(HB_PATH.format(name=name), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def state(tab_prefix):
    try:
        tab = None
        for t in channel.list_tabs():
            if t["id"].startswith(tab_prefix):
                tab = t
                break
        if not tab:
            return "tablost", 0, 0, ""
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            url = dw._eval(c, "location.href", timeout=15)
            body = dw._eval(c, "document.body.innerText || ''", timeout=25) or ""
            c.close()
        except Exception as e:
            return f"busy:{type(e).__name__}", 0, 0, ""
    except Exception as e:
        return f"busy:{type(e).__name__}", 0, 0, ""
    marker_arg = sys.argv[3] if len(sys.argv) > 3 else "COMPLETION REPORT"
    hits = body.count(marker_arg)
    # 2026-09-09 (WO-010 forensics): GLM workers in this environment answer
    # in Chinese ~half the time — a genuine report headline may be
    # "=== WO-010 完成报告 ===" instead of the English literal. Accept the
    # bilingual headline so a real report is never missed.
    if "COMPLETION REPORT" in marker_arg:
        hits += body.count(marker_arg.replace("COMPLETION REPORT", "完成报告"))
    # TRUE completion: the marker is followed by a FILLED report — a real hex
    # SHA on the base-SHA line (the prompt template only has a placeholder).
    # Prompt echoes (even duplicated by an operator-procedure resend) never
    # satisfy this; a genuine answer always does. Field labels may be English
    # or Chinese (base branch / 基础分支), colon may be ASCII or fullwidth.
    filled = bool(re.search(
        r"=== WO-\d+ (?:COMPLETION REPORT|完成报告) ==="
        r"[\s\S]{0,600}?(?:base branch|基础分支)\s*\+\s*(?:base SHA|基础\s*SHA)\s*[:：]\s*main\s*@\s*[0-9a-f]{7,40}",
        body))
    gen = bool(re.search(r"\b(Stop|Pause|Halt)\b", body[-1500:]))
    cap = "currently at capacity" in body or "peak hours" in body
    if "/c/" not in url:
        return "home", len(body), (1000 if filled else hits), url
    if gen:
        return "generating", len(body), (1000 if filled else hits), url
    return ("queued-capacity" if cap else "queued"), len(body), (1000 if filled else hits), url


def run_with_hb(name, cmd):
    """Run a re-dispatch subprocess while KEEPING THE HEARTBEAT FRESH.

    2026-09-09 fix (wave-4 forensics): a capacity-peak re-dispatch (create's
    assault loop with backoffs) can run 10-20 minutes; the old blocking
    subprocess.call never ticked the heartbeat, so the supervisor killed the
    watcher MID-ASSAULT as 'hung' (603s stale) — the orphaned create() then
    finished its job against a watcher that had already been replaced.
    Ticking every 15s during the wait makes a legitimately-busy watcher
    indistinguishable from a healthy one (hangs still die via the 600s rule
    because a true hang stops calling this loop entirely).
    """
    p = subprocess.Popen(cmd, stdout=None, stderr=subprocess.STDOUT)
    while p.poll() is None:
        heartbeat(name)
        time.sleep(15)
    return p.returncode


def main():
    name, tab_prefix = sys.argv[1], sys.argv[2]
    marker = sys.argv[3] if len(sys.argv) > 3 else "COMPLETION REPORT"
    # supervisor contract: while this spec exists, the supervisor resurrects
    # this watcher; we remove it when the session completes
    write_spec(name, tab_prefix, marker)
    rounds_since_progress = 0
    last_len = 0
    stuck_since = 0          # first-sighting ts of zero-progress queued-capacity
    stuck_assaults = 0       # bounded staleness re-dispatches
    while True:
        try:
            st, ln, hits, url = state(tab_prefix)
            stamp = time.strftime("%H:%M:%S")
            print(f"[{name}] {stamp} {st} chars={ln} hits={hits} url={url[:60]}", flush=True)
            heartbeat(name)
            mk = os.path.join(FLAGS, f"{name}-complete.marker")
            if hits >= 2:
                open(mk, "w").write(f"{time.time()} {url}\n")
                print(f"[{name}] COMPLETE — marker written", flush=True)
                try:
                    os.remove(SPEC_PATH.format(name=name))
                    os.remove(HB_PATH.format(name=name))
                except Exception:
                    pass
                return 0
            if st == "tablost" or st == "home":
                print(f"[{name}] {stamp} session destroyed ({st}) — re-dispatching (assault)", flush=True)
                # the dead session's registry record would make create() bail
                # with "already exists" — void it first
                run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "void", name,
                                 f"session destroyed while queued ({st}); queue_watch assault re-dispatch"])
                run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "create", name,
                                 os.path.join(BASE, "worker-prompts", f"{name.replace('wo-', 'WO-')}.md")])
                # refresh tab prefix from the registry's latest record
                rec = dw._find(name)
                if rec:
                    tab_prefix = (rec.get("tab_id") or "")[:8]
                    print(f"[{name}] {stamp} new session tab={tab_prefix}", flush=True)
                    write_spec(name, tab_prefix, marker)  # keep supervisor contract fresh
            # progress bookkeeping + staleness-assault policy
            if ln != last_len:
                rounds_since_progress = 0
                last_len = ln
            else:
                rounds_since_progress += 1
            if st == "queued-capacity":
                if rounds_since_progress == 0:
                    stuck_since = 0            # body still changing — not stuck
                elif rounds_since_progress >= 2 and not stuck_since:
                    stuck_since = time.time()
                    print(f"{stamp} stuck-clock started (queued-capacity, no progress)", flush=True)
            else:
                stuck_since = 0                # generating/queued/home all reset the clock
            if (st == "queued-capacity" and stuck_since
                    and time.time() - stuck_since > STUCK_ASSAULT_AFTER
                    and stuck_assaults < STUCK_ASSAULT_MAX):
                stuck_assaults += 1
                stuck_since = 0
                print(f"[{name}] {stamp} STUCK {STUCK_ASSAULT_AFTER}s in queued-capacity — "
                      f"assault #{stuck_assaults}/{STUCK_ASSAULT_MAX} (fresh dispatch beats a zombie session)",
                      flush=True)
                run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "void", name,
                                 f"stuck in queued-capacity {STUCK_ASSAULT_AFTER}s with zero progress; "
                                 f"staleness assault #{stuck_assaults}"])
                run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "create", name,
                                 os.path.join(BASE, "worker-prompts", f"{name.replace('wo-', 'WO-')}.md")])
                rec = dw._find(name)
                if rec:
                    tab_prefix = (rec.get("tab_id") or "")[:8]
                    print(f"[{name}] {stamp} new session tab={tab_prefix}", flush=True)
                    write_spec(name, tab_prefix, marker)
                last_len = 0
                rounds_since_progress = 0
        except Exception as e:
            print(f"[{name}] {time.strftime('%H:%M:%S')} loop-error {type(e).__name__} — continuing", flush=True)
        heartbeat(name)  # also tick after loop errors (busy states are not hangs)
        time.sleep(120)


if __name__ == "__main__":
    sys.exit(main())
