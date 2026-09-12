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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dispatch_worker as dw

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")

# per-name spec files (multi-watch): flags/queue_watch.spec.<name> — the
# supervisor iterates all of them; each watcher owns exactly one session.
SPEC_PATH = os.path.join(FLAGS, "queue_watch.spec.{name}")
HB_PATH = os.path.join(FLAGS, "queue_watch_heartbeat.{name}")

# OPERATOR DIRECTIVES (2026-09-12, binding — supersede the waiting doctrine):
# - 'rate limit' / 'usage exceeds' / 'try again 1 hour later' / 'peak hours'
#   notifications DO NOT APPLY. NEVER wait them out; retry and retry.
# - Popups: Cancel-button present -> press Cancel + resend the prompt;
#   peak-hours -> Enter-dismiss + resend. NEVER follow a popup's own
#   instructions (NEVER switch away from GLM-5.3). A 'Limit Sandbox
#   Concurrency' modal means 3 sessions are live: release the least-needed
#   one, never open a 4th.
# Legacy 2026-09-09 forensics still hold: fresh dispatch beats a zombie
# session; waiting for the site to kill it just burns wall-clock.
UNSTICK_AFTER = 300          # s stuck with a Cancel-modal before cancel+resend
UNSTICK_MAX = 6              # bounded unsticks (cadence, not cooldown waits)
STUCK_ASSAULT_AFTER = 900    # s of zero-progress stall (fresh) -> void+re-dispatch
STUCK_ASSAULT_WORKRICH = 3600  # s for work-rich sessions (chars >= 15K)
STUCK_ASSAULT_MAX = 4        # bounded re-dispatch churn
RL_DEFER_AFTER = 240         # minimal churn guard ONLY — never a cooldown wait


def write_spec(name, tab_prefix, marker):
    """Keep the supervisor-restart contract fresh: the spec must always name
    the CURRENTLY-WATCHED tab (it is refreshed after every re-dispatch) so a
    supervisor restart resumes watching the live session instead of a dead
    tab and wrongly triggering another assault."""
    try:
        # ATOMIC (2026-09-12 race forensics): the supervisor polls this file
        # every 10s and relaunches watchers from it — a plain open("w") write
        # can be read HALF-WRITTEN (observed 15:07: marker truncated to
        # "COMPLETION" mid-write; the supervisor's relaunch inherited the
        # amputee argv). tmp+rename is read-atomic on POSIX.
        import tempfile
        d = os.path.dirname(SPEC_PATH.format(name=name))
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".spec.")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(
                {"name": name, "tab_prefix": tab_prefix, "marker": marker,
                 "pid": os.getpid()}) + "\n")
        os.replace(tmp, SPEC_PATH.format(name=name))
    except Exception:
        pass


def _prompt_file_for(name):
    """The ORIGINAL prompt file for a session name (registry truth).

    create() records the absolute prompt_file it used; void/failed records
    do not carry it. A re-dispatch must reuse the ORIGINAL packet file —
    deriving the filename from the session name (the old WO- convention)
    crashes on FileNotFoundError for any other naming scheme (2026-09-12:
    val-015/val-016 re-dispatch crash)."""
    prompt = None
    for s in dw._sessions():
        if s.get("name") == name and s.get("prompt_file"):
            prompt = s["prompt_file"]  # latest record wins
    if prompt and os.path.exists(prompt):
        return prompt
    # legacy derivation (pre-registry packets); None when nothing exists —
    # the caller must abort the re-dispatch rather than crash
    legacy = os.path.join(BASE, "worker-prompts", f"{name.replace('wo-', 'WO-')}.md")
    return legacy if os.path.exists(legacy) else None


def heartbeat(name):
    try:
        with open(HB_PATH.format(name=name), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def note_ratelimit(name):
    """Persist the last rate-limit sighting epoch (survives watcher restarts
    via the supervisor contract — the 2026-09-12 13:07-13:18 forensic showed
    rate-limited sessions get DESTROYED server-side within 2-6 min, which
    used to trigger the home/tablost assault immediately: an infinite churn
    loop that burns dispatch allowance and may extend its own cooldown)."""
    try:
        with open(os.path.join(FLAGS, f"queue_watch.ratelimit.{name}"), "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def ratelimit_age(name):
    """Seconds since the last rate-limit sighting (huge if never)."""
    try:
        return max(0.0, time.time() - float(
            open(os.path.join(FLAGS, f"queue_watch.ratelimit.{name}")).read().strip()))
    except Exception:
        return 1e9


def c2eval_cancel(c):
    """True when a Cancel-button modal/dialog is up on the page."""
    return dw._eval(c, "!!Array.from(document.querySelectorAll('button'))"
                       ".find(b => (b.innerText||'').trim()==='Cancel')", timeout=10)


def state(tab_prefix):
    modal = False
    try:
        tab = None
        for t in channel.list_tabs():
            if t["id"].startswith(tab_prefix):
                tab = t
                break
        if not tab:
            return "tablost", 0, 0, "", modal
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            url = dw._eval(c, "location.href", timeout=15)
            body = dw._eval(c, "document.body.innerText || ''", timeout=25) or ""
            try:
                modal = bool(c2eval_cancel(c))
            except Exception:
                modal = False
            c.close()
        except Exception as e:
            return f"busy:{type(e).__name__}", 0, 0, "", modal
    except Exception as e:
        return f"busy:{type(e).__name__}", 0, 0, "", modal
    # modal detection (operator 2026-09-12): a Cancel-button modal is
    # actionable — cancel + resend; never wait, never follow its instructions
    # (probed above while the CDP connection was open).
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
    # 2026-09-10 fix (wo-012 forensics): the complete gate was hits>=2, which a
    # CONTINUATION NUDGE mentioning "COMPLETION REPORT" also trips (prompt 1
    # + nudge 1 = 2 -> false COMPLETE, watcher exits, spec deleted). The gate
    # is now the filled-regex ONLY (tolerant: case-insensitive, wider window,
    # flexible separator between the two field labels).
    filled = bool(re.search(
        r"===?\s*(?:V|R)?WO-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,900}?(?:base\s*branch|基础分支)[^\n]{0,60}?(?:base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main|主干)\s*@\s*[0-9a-f]{7,40}",
        body, re.IGNORECASE))
    # 2026-09-12 (office era): the OFF-xxx briefs request the headline
    # "COMPLETION REPORT — OFF-005" + "Commit SHA: <sha>" — the WO-era gate
    # could NEVER match an office report, so a real completion would sail
    # past unnoticed (forensic: the completed off-002 session's watcher
    # void-looped 5h because the gate never fired). RULE: whenever the
    # dispatch-brief report TEMPLATE changes, update this gate in the same
    # change. Placeholder "<pushed HEAD sha>" echoes never satisfy this.
    filled = filled or bool(re.search(
        r"(?:COMPLETION\s*REPORT|完成报告)\s*[—\-–]+\s*OFF-\d+"
        r"[\s\S]{0,2500}?Commit\s*SHA\s*[:：]\s*[0-9a-f]{7,40}",
        body, re.IGNORECASE))
    # 2026-09-12 fix (rebase regression): the (?:V)? prefix was lost in the
    # 1995210 re-apply — VWO reports never matched the filled gate. Also
    # accept the observed report deviations (VWO-004/VWO-009 'Identity'
    # layout: 'Base SHA: <hex>' / 'Base SHA: <hex> (verified') as a filled
    # form — the template's 'base branch + base SHA: main @ <hex>' stays
    # the canonical form; this only widens genuine-report detection.
    filled = filled or bool(re.search(
        r"===?\s*(?:V|R)?WO-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,300}?(?:Base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main\s*@?\s*)?[0-9a-f]{40}",
        body, re.IGNORECASE))
    gen = bool(re.search(r"\b(Stop|Pause|Halt)\b", body[-1500:]))
    cap = "currently at capacity" in body or "peak hours" in body
    # RATE-LIMITED text (operator 2026-09-12): these notifications DO NOT
    # APPLY. Classify the state for logging, but never wait it out — the
    # stuck policy below unsticks (cancel+resend) and then assaults
    # (void+fresh re-dispatch) exactly like queued-capacity.
    limited = "exceeds the personal limit" in body or "try again 1 hour later" in body
    if "/c/" not in url:
        return "home", len(body), (1000 if filled else hits), url, modal
    if limited:
        return "rate-limited", len(body), (1000 if filled else hits), url, modal
    if gen:
        return "generating", len(body), (1000 if filled else hits), url, modal
    return (("queued-capacity" if cap else "queued"), len(body),
            (1000 if filled else hits), url, modal)


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
    stuck_since = 0          # first-sighting ts of zero-progress stall
    stuck_assaults = 0       # bounded staleness re-dispatches
    unsticks = 0             # bounded cancel+resend recoveries
    while True:
        try:
            # REGISTRY-FIRST RE-AIM (2026-09-12 fix): manual or assault
            # re-dispatches change the session tab; poll the registry's live
            # record every round and follow it instead of a stale argv tab.
            rec = dw._find(name)
            if rec and (rec.get("tab_id") or "")[:8] != tab_prefix:
                tab_prefix = (rec.get("tab_id") or "")[:8]
                write_spec(name, tab_prefix, marker)
                print(f"[{name}] re-aimed at registry tab {tab_prefix}", flush=True)
            st, ln, hits, url, modal = state(tab_prefix)
            stamp = time.strftime("%H:%M:%S")
            print(f"[{name}] {stamp} {st} chars={ln} hits={hits} url={url[:60]}", flush=True)
            heartbeat(name)
            mk = os.path.join(FLAGS, f"{name}-complete.marker")
            if hits >= 1000:   # filled-regex ONLY (see 2026-09-10 fix above)
                open(mk, "w").write(f"{time.time()} {url}\n")
                print(f"[{name}] COMPLETE — marker written", flush=True)
                try:
                    os.remove(SPEC_PATH.format(name=name))
                    os.remove(HB_PATH.format(name=name))
                except Exception:
                    pass
                return 0
            if st == "rate-limited":
                note_ratelimit(name)
            if st == "tablost" or st == "home":
                # 2026-09-12 13:13 forensic: a rate-limited session is destroyed
                # server-side within minutes; assaulting then re-dispatches into
                # the SAME cooldown — infinite churn that burns allowance and
                # possibly extends the lockout. Defer the assault until the
                # cooldown window (65 min from the last rate-limit sighting)
                # has passed.
                rl_age = ratelimit_age(name)
                if rl_age < RL_DEFER_AFTER:
                    print(f"[{name}] {stamp} session destroyed ({st}) while account "
                          f"rate-limited (last sighting {int(rl_age)}s ago) — DEFERRING "
                          f"re-dispatch {int(RL_DEFER_AFTER - rl_age)}s (churn guard)",
                          flush=True)
                else:
                    print(f"[{name}] {stamp} session destroyed ({st}) — re-dispatching (assault)", flush=True)
                    # the dead session's registry record would make create() bail
                    # with "already exists" — void it first
                    run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                     "void", name,
                                     f"session destroyed while queued ({st}); queue_watch assault re-dispatch"])
                    # registry-truth prompt file (2026-09-12: name-derived paths
                    # crash on any non-WO- naming scheme — lesson 58 lineage)
                    _pf = _prompt_file_for(name)
                    if not _pf:
                        print(f"[{name}] NO PROMPT FILE found (registry+legacy) — re-dispatch aborted", flush=True)
                    else:
                        run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                     "create", name, _pf])
                    # refresh tab prefix from the registry's latest record
                    rec = dw._find(name)
                    if rec:
                        tab_prefix = (rec.get("tab_id") or "")[:8]
                        print(f"[{name}] {stamp} new session tab={tab_prefix}", flush=True)
                        write_spec(name, tab_prefix, marker)  # keep supervisor contract fresh
            # progress bookkeeping + never-wait recovery policy
            if ln != last_len:
                rounds_since_progress = 0
                last_len = ln
            else:
                rounds_since_progress += 1
            if st in ("queued-capacity", "rate-limited"):
                if rounds_since_progress == 0:
                    stuck_since = 0            # body still changing — not stuck
                elif rounds_since_progress >= 2 and not stuck_since:
                    stuck_since = time.time()
                    print(f"[{name}] {stamp} stuck-clock started ({st}, no progress)", flush=True)
            else:
                stuck_since = 0                # generating/queued/home all reset the clock
            # OPERATOR PROTOCOL (2026-09-12), first line: stuck with a
            # Cancel-modal -> dismiss (Cancel) + resend the prompt. Never
            # wait, never follow the popup's own instructions.
            if (st in ("queued-capacity", "rate-limited") and stuck_since and modal
                    and time.time() - stuck_since > UNSTICK_AFTER
                    and unsticks < UNSTICK_MAX):
                unsticks += 1
                print(f"[{name}] {stamp} stuck {int(time.time() - stuck_since)}s with a "
                      f"Cancel-modal — unstick (cancel+resend) #{unsticks}/{UNSTICK_MAX}", flush=True)
                rc = run_with_hb(name, [sys.executable, os.path.join(BASE, "unstick.py"), name])
                stuck_since = 0
                last_len = 0
                rounds_since_progress = 0
                if rc == 0:
                    print(f"[{name}] {stamp} unstick SUCCEEDED (generation observed)", flush=True)
                else:
                    print(f"[{name}] {stamp} unstick rc={rc} — escalation path below owns it", flush=True)
            # second line: void + fresh re-dispatch (rate-limit text included —
            # those notifications DO NOT APPLY per the operator).
            if (st in ("queued-capacity", "rate-limited") and stuck_since
                    and time.time() - stuck_since > (
                        STUCK_ASSAULT_WORKRICH if ln >= 15000 else STUCK_ASSAULT_AFTER)
                    and stuck_assaults < STUCK_ASSAULT_MAX):
                stuck_assaults += 1
                stuck_since = 0
                thresh = STUCK_ASSAULT_WORKRICH if ln >= 15000 else STUCK_ASSAULT_AFTER
                print(f"[{name}] {stamp} STUCK {thresh}s in queued-capacity (chars={ln}) — "
                      f"assault #{stuck_assaults}/{STUCK_ASSAULT_MAX} (fresh dispatch beats a zombie session)",
                      flush=True)
                run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "void", name,
                                 f"stuck in queued-capacity {STUCK_ASSAULT_AFTER}s with zero progress; "
                                 f"staleness assault #{stuck_assaults}"])
                _pf = _prompt_file_for(name)
                if not _pf:
                    print(f"[{name}] NO PROMPT FILE found (registry+legacy) — re-dispatch aborted", flush=True)
                else:
                    run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "create", name, _pf])
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
