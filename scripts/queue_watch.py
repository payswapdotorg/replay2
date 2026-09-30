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
QUEUED_STATIC_AFTER = 3600   # 2026-09-18 outage: plain "queued" zero-progress
                            # before assault (dead-with-error sessions render
                            # as plain queued; legit queues move within the hour)
RL_DEFER_AFTER = 240         # minimal churn guard ONLY — never a cooldown wait

# 2026-09-19 OUTAGE-HOLD (resident-lead directive): while
# flags/outage_hold.txt exists, ALL send paths (unstick cancel+resend,
# staleness assault, tablost/home re-dispatch) are suppressed — the watcher
# degrades to a pure read-only monitor. Rationale: the platform began
# reaping queued sessions during the 2026-09-18/19 generation outage and
# every fresh dispatch wedges identically, so churn gains nothing while
# feeding possible account-level anti-abuse blocks. The lead lifts the flag
# only when backend_probe_watch reports HEALTHY (then watchers resume the
# full ladder and fresh sessions generate immediately).
OUTAGE_HOLD_PATH = os.path.join(FLAGS, "outage_hold.txt")
_HOLD_LOG = {}

# Work-order report ID families recognized by the completion gates below.
# The gates' MECHANISM — report headline + real-hex proof, placeholder-echo-
# proof — is generic; the ID family is per-deployment DATA and lives in the
# deployment's config, never in this repo (§0). Set REPLAY_REPORT_PREFIXES
# (comma-separated, e.g. "ANCHOR,VOICE,GBIM") for this deployment's report
# shapes; legacy deployment families are recoverable from git history.
REPORT_ID_PREFIXES = [
    p.strip().upper()
    for p in os.environ.get("REPLAY_REPORT_PREFIXES", "").split(",")
    if p.strip()]
# unconfigured -> the generic ID-word pattern (ANY work-item family prefix
# before the number, e.g. "ANCHOR-002" / "VOICE-003" / "TL1-003" — the
# hex-proof mechanism stays the discriminator); configured -> exactly the
# deployment's families (explicit list, no surprises).
_IDP = "|".join(REPORT_ID_PREFIXES) if REPORT_ID_PREFIXES else r"[A-Z][A-Z0-9]*"

def hold_active(name=""):
    if not os.path.exists(OUTAGE_HOLD_PATH):
        return False
    now = time.time()
    if now - _HOLD_LOG.get(name, 0) > 1800:
        _HOLD_LOG[name] = now
        print(f"[{name}] OUTAGE-HOLD active — senders suppressed (read-only watch)", flush=True)
    return True


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
    if os.path.exists(legacy):
        return legacy
    # 2026-09-24 (reset #3): the registry was wiped by the sandbox reset and
    # the wave-5 packets use UPPERCASE names (W5-TAKE-001.md) while session
    # names are lowercase (w5-take-001) — the lowercase legacy path missed
    # and the re-dispatch aborted at the worst moment (platform recovery).
    upper = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    return upper if os.path.exists(upper) else None


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


def agent_lane(name):
    """True when the registry's latest record says this is an agents-tab
    session (dispatcher-verified at create time). LESSON 185: agent-lane
    sessions must never be Cancel-clicked (kills the session) and a VERIFIED
    send must never be void-assaulted while the conversation is alive
    server-side — the platform's generation window drains it."""
    try:
        rec = dw._find(name)
        return bool(rec and rec.get("mode") == "agents-tab")
    except Exception:
        return False


def server_alive(name):
    """Probe the session's conversation server-side (probe_chat.py).
    Returns (alive, msgs, note, bchars, has_report). Lesson 185 corollary:
    the chat index lags after capacity events — DOM tab state
    (home/bounce) is NOT death; the server message store is the truth gate.
    2026-09-30 ZOMBIE-TURN doctrine (w13 forensics): a session can be
    alive-as-RECORD while its generation is dead — observed w13 attempt #3:
    turn opened 09:45:05, streamed ~30 min, froze mid-read; the probe read
    SERVER-SIDE ALIVE msgs=2 forever and queue_watch WAITED 2h52m on
    lesson-185 patience, never assaulting. The probe now also carries
    turn-liveness evidence — (bchars, has_report) from the batch store —
    and CALLERS track bchars across cycles: a STATIC batch with no report
    past ZOMBIE_TURN_AFTER is a dead turn (assault as designed), while a
    growing batch is live generation (patience stands).
    2026-09-27 (wave-3 crunch forensics): an http-500 on the chat read is
    UNCERTAINTY, not death — a continuation send landing during a capacity
    crunch wedges the chat RECORD (every read 500s) while the message store
    is intact and the platform can unwedge it when the window drains.
    Treating 500 as death let the assault ladder void + churn during the
    crunch (observed: T005-2/T007-2 500ing while T006-2 + old chats read
    fine — the 500 tracks the send, not the chat's existence). Probe
    errors must read as ALIVE-for-patience so the void gate stays closed
    until a definitive not-found."""
    try:
        rec = dw._find(name)
        cid = ((rec or {}).get("url") or "").split("/c/")[-1].split("/")[0].split("?")[0]
        if len(cid) < 30:
            return False, 0, "no-cid", None, False
        pr = subprocess.run(
            [sys.executable, os.path.join(BASE, "probe_chat.py"), cid, "Base SHA"],
            cwd=BASE, capture_output=True, text=True, timeout=60)
        d = json.loads(pr.stdout.strip().split("\n")[-1])
        if d.get("err"):
            # distinguish DEFINITIVE death (not-found) from UNCERTAINTY
            # (5xx read error / probe machinery failure):
            #  - http-404/403 "not found" = the chat is destroyed server-side
            #    (lesson 40 ladder) -> death verdict, assault may proceed
            #  - http-5xx = the chat record is wedged (send-during-crunch
            #    forensics above) or the API is flaking -> patience, the
            #    platform can unwedge it when the window drains
            e = str(d.get("err"))
            if "http-404" in e or "http-403" in e:
                return False, 0, f"probe-dead:{e}", None, False
            return True, 0, f"probe-uncertain:{e}", None, False
        _b = d.get("batch") or {}
        return (bool(d.get("alive")), int(d.get("msgs") or 0),
                f"title={d.get('title','')[:30]}",
                _b.get("chars"), bool(d.get("reportInAssistant")))
    except Exception as e:
        # probe machinery failure is also uncertainty — never a death verdict
        return True, 0, f"probe-exc:{type(e).__name__}", None, False


# zombie-turn doctrine (2026-09-30): patience ceiling for a server-alive
# session whose batch store is STATIC with no report. Env-overridable.
ZOMBIE_TURN_AFTER = int(os.environ.get("QW_ZOMBIE_TURN_AFTER", "7200"))
_zombie_track = {}   # name -> {"chars": int|None, "since": epoch}

# 2026-09-30 s8 CURE-FIRST doctrine (AGENT_BOOT_PROMPT section 8, PPR-022-
# proven): a zombie turn gets the stop/continue in-place cure BEFORE any
# void+re-dispatch (narrative + pod survive). Bounded attempts per watcher
# lifetime; void is the last resort.
CURE_MAX = int(os.environ.get("QW_CURE_MAX", "3"))
_cure_attempts = {}


def _zombie_verdict(name, bchars, has_report, stamp, st, thresh_note=""):
    """Track (name)'s batch-store char count across cycles.
    Returns 'wait' | 'zombie' | 'complete'.'wait' = alive-and-(growing-or-young);
    'zombie' = static past ZOMBIE_TURN_AFTER with no report; 'complete' =
    report confirmed server-side. Uncertain probes (bchars None) reset the
    clock — uncertainty never escalates to assault."""
    if has_report:
        return "complete"
    z = _zombie_track.setdefault(name, {})
    now = time.time()
    if bchars is None or bchars != z.get("chars"):
        z["chars"] = bchars
        z["since"] = now
    age = now - z.get("since", now)
    if bchars is not None and age > ZOMBIE_TURN_AFTER:
        print(f"[{name}] {stamp} tab {st} server-alive but ZOMBIE TURN — batch static "
              f"{int(age)}s (chars={bchars}), no report{thresh_note} — dead-turn verdict", flush=True)
        _zombie_track.pop(name, None)
        return "zombie"
    return "wait"


def state(tab_prefix):
    modal = False
    try:
        tab = None
        for t in channel.list_tabs():
            if t["id"].startswith(tab_prefix):
                tab = t
                break
        if not tab:
            return "tablost", 0, 0, "", modal, ""
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            url = dw._eval(c, "location.href", timeout=15)
            body = dw._eval(c, "document.body.innerText || ''", timeout=25) or ""
            # 2026-09-27 (TL1 campaign, AGENTS-mode sessions): in-place agent
            # activity (terminal runs, todo counters, file trees) renders
            # WITHOUT changing body length, and the Stop control is
            # aria-label'd (never part of innerText) — the old metrics
            # structurally misread WORKING sessions as stuck-queued and the
            # staleness assault would void live work. Two probes added:
            #   (a) fingerprint: Ran-commands counter + Todo counter + body
            #       length + Stop-control presence — any change = progress
            #   (b) stop_present: an open [aria-label=Stop] control means the
            #       agent turn is OPEN -> state is "generating" (resets the
            #       stuck clock; semantically correct for AGENTS mode)
            try:
                fp = dw._eval(c, r"""(() => {
                  const b = document.body.innerText || '';
                  const ran = (b.match(/Ran (\d+) commands?/) || ['', '0'])[1];
                  const todo = (b.match(/Todo Progress[^0-9]*(\d+)\/(\d+)/) || ['', '0', '0']);
                  const stop = document.querySelector('[aria-label=Stop]') ? '1' : '0';
                  return ran + '|' + todo[1] + '/' + todo[2] + '|' + b.length + '|' + stop;
                })()""", timeout=15) or ""
                stop_present = fp.endswith("|1")
            except Exception:
                fp = ""
                stop_present = False
            # 2026-09-27 (server-truth gate): the Stop control LIES for
            # queued-pending sessions — the client renders it optimistically
            # while the server has NO assistant record (the turn never
            # opened; observed on tl1-b/c: prompt server-side, Stop present,
            # zero assistant records for 30+ min). Only trust Stop when the
            # server confirms the turn is open: the chat's LAST history
            # message (by timestamp) must be an assistant record. If the
            # last is a user message, the session is PENDING regardless of
            # the Stop control -> downgrade to the queued path so the stuck
            # clock keeps running. Probe failure leaves stop_present as-is
            # (never downgrade on uncertainty).
            if stop_present and "/c/" in (url or ""):
                try:
                    import urllib.request as _ur
                    _cid = url.split("/c/")[-1].split("/")[0].split("?")[0].strip("/")
                    _tok = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
                    _rq = _ur.Request(f"https://chat.z.ai/api/v1/chats/{_cid}",
                                      headers={"Authorization": f"Bearer {_tok}"})
                    with _ur.urlopen(_rq, timeout=15) as _r:
                        _j = json.loads(_r.read().decode())
                    _hist = ((_j.get("chat") or _j).get("history") or {}).get("messages") or {}
                    _vals = list(_hist.values()) if isinstance(_hist, dict) else list(_hist)
                    _last = sorted(_vals, key=lambda m: m.get("timestamp") or 0)[-1] if _vals else None
                    if _last is not None and _last.get("role") != "assistant":
                        stop_present = False  # pending, not generating
                except Exception:
                    pass  # probe failed — keep the DOM verdict
            try:
                modal = bool(c2eval_cancel(c))
            except Exception:
                modal = False
            c.close()
        except Exception as e:
            return f"busy:{type(e).__name__}", 0, 0, "", modal, ""
    except Exception as e:
        return f"busy:{type(e).__name__}", 0, 0, "", modal, ""
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
    # 2026-09-12 (VAL-era wave): the VAL-NNN report
    # template ("=== VAL-016 COMPLETION REPORT ===" + "- Base: main @ <sha>")
    # never matched the WO regex — a second alternative accepts
    # it. The placeholder ("<exact SHA you based on>") is not hex, so prompt
    # echoes still never satisfy the gate.
    filled = bool(re.search(
        r"===?\s*(?:%s)-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,900}?(?:base\s*branch|基础分支)[^\n]{0,60}?(?:base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main|主干)\s*@\s*[0-9a-f]{7,40}" % _IDP,
        body, re.IGNORECASE)) or bool(re.search(
        r"===?\s*VAL-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,500}?Base\s*[:：]\s*(?:main|主干)\s*@\s*[0-9a-f]{7,40}",
        body, re.IGNORECASE))
    # 2026-09-12 fix (rebase regression): the (?:V)? prefix was lost in the
    # 1995210 re-apply — VWO reports never matched the filled gate. Also
    # accept the observed report deviations (VWO-004/VWO-009 'Identity'
    # layout: 'Base SHA: <hex>' / 'Base SHA: <hex> (verified') as a filled
    # form — the template's 'base branch + base SHA: main @ <hex>' stays
    # the canonical form; this only widens genuine-report detection.
    filled = filled or bool(re.search(
        r"===?\s*(?:%s)-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,300}?(?:Base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main\s*@?\s*)?[0-9a-f]{40}" % _IDP,
        body, re.IGNORECASE))
    # 2026-09-15 (lesson 121): the W-series worker prompts use
    # "W305 COMPLETION REPORT" + "Branch: w305-… @ <final-sha>" —
    # the template placeholder <final-sha> is not hex, so prompt echoes
    # (and worker plan echoes of the template) never satisfy this gate;
    # a genuine report always carries the pushed commit sha.
    filled = filled or bool(re.search(
        r"(?:%s)\s+W\d+\s+COMPLETION\s+REPORT"
        r"[\s\S]{0,300}?Branch\s*[:：]\s*[\w.-]+\s*@\s*[0-9a-f]{7,40}" % _IDP,
        body, re.IGNORECASE))
    # 2026-09-19 (R2x-Wx era): the wave-numbered worker packets use
    # "=== R20-W1 COMPLETION REPORT ===" + "Branch SHA pushed: <hex>". The
    # placeholder in the packet ("<the branch SHA you pushed>" / prose) is
    # never hex, so prompt echoes cannot satisfy this; a genuine report
    # always carries the pushed hex. Accept English or Chinese labels.
    filled = filled or bool(re.search(
        r"===?\s*R\d+-W\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,900}?(?:Branch\s*SHA\s*pushed|分支\s*SHA|推送的\s*分支)\s*[:：]\s*[0-9a-f]{7,40}",
        body, re.IGNORECASE))
    # Some R2x reports lead with the cloned-HEAD/base line instead ("cloned
    # HEAD SHA:" / "Base: wfx/... @ <hex>") — accept that shape too.
    filled = filled or bool(re.search(
        r"===?\s*R\d+-W\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
        r"[\s\S]{0,600}?(?:cloned\s*HEAD\s*SHA|Base)\s*[:：@]\s*[0-9a-f]{7,40}",
        body, re.IGNORECASE))
    # 2026-09-24 (Wave-5 era): the TAKE-NNN worker packets use
    # "=== TAKE-001 COMPLETION REPORT ===" (LEASE-001 same shape, LEASE
    # prefix) + "Base SHA / 基础 SHA: main @ <hex>". The packet template
    # carries a non-hex placeholder on that line, so prompt echoes (and
    # worker plan drafts echoing the template) never satisfy this gate;
    # a genuine report always carries the real checked-out base hex.
    # 2026-09-24 (Wave-6 staging): WEB- prefix added for the F11 web client
    # campaign (same report shape, same placeholder-proof rule).
    # 2026-09-25 (Wave-7 staging): FV- prefix added for the formal-
    # verification campaign (FV-001..003; same report shape, same
    # placeholder-proof rule — the packet's base-SHA line carries a real
    # hex only in a genuine report). Same-day fix: the observed Wave-6
    # report phrasing is "Base branch + SHA: main @ <hex>" (w6-web-001/
    # 002 responses) — the old `Base\s*SHA` never matched it, so those
    # completions rode the server-probe path only. Accept BOTH phrasings
    # so the DOM fast-path fires for the FV shape too (the server probe
    # stays the truth gate either way). RE-APPLIED after reset #4 (the
    # original patch was working-copy-only at the old sandbox; 12-vector
    # suite: 4 genuine shapes pass, prompt/plan/unrelated echoes fail,
    # LEASE/TAKE/WEB regressions pass).
    # 2026-09-27 (TL1 era, reset #5 re-apply): TL1- prefix added for the
    # substrate program (TL1-001..005; same report shape "TL1-00X
    # COMPLETION REPORT" + "Base SHA: main @ <hex>", same placeholder-proof
    # rule — the packet template's base-SHA line carries a non-hex
    # placeholder, so prompt/plan echoes can never satisfy the gate).
    filled = filled or bool(re.search(
        r"(?:===?|##+)?\s*(?:%s)-\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*(?:===?|#+)?"
        r"[\s\S]{0,600}?(?:Base\s*(?:branch\s*\+\s*)?SHA|基础\s*SHA)[^\n]{0,40}[:：][^\n]{0,15}?`?(?:main|主干)`?\s*@\s*`?[0-9a-f]{7,40}`?" % _IDP,
        body, re.IGNORECASE))
    # 2026-09-30 (SOS W-series campaign): W13+ worker packets use
    # "=== W13 COMPLETION REPORT ===" + "pushed: work/w13-... @ <hex>".
    # Echo-proof rule: the packet template's pushed line carries the non-hex
    # placeholder "<full 40-char SHA you pushed>", so prompt/plan echoes can
    # never satisfy the gate; a genuine report always carries the pushed hex.
    # The known base SHA on the separate base line is NOT matched (it appears
    # verbatim in the packet, so matching it would false-positive on echoes).
    # English or Chinese headline, ASCII or fullwidth colon.
    filled = filled or bool(re.search(
        r"(?:===?|##+)?\s*W\d+\s*(?:COMPLETION\s*REPORT|完成报告)\s*(?:===?|#+)?"
        r"[\s\S]{0,600}?(?:pushed|推送)[^\n]{0,60}?[:：][^\n]{0,40}?@\s*`?[0-9a-f]{7,40}`?",
        body, re.IGNORECASE))

    # 2026-09-27: an open Stop CONTROL (aria-label) outranks the innerText
    # heuristic — AGENTS-mode turns keep it present for the whole session
    gen = stop_present or bool(re.search(r"\b(Stop|Pause|Halt)\b", body[-1500:]))
    cap = "currently at capacity" in body or "peak hours" in body
    # RATE-LIMITED text (operator 2026-09-12): these notifications DO NOT
    # APPLY. Classify the state for logging, but never wait it out — the
    # stuck policy below unsticks (cancel+resend) and then assaults
    # (void+fresh re-dispatch) exactly like queued-capacity.
    limited = "exceeds the personal limit" in body or "try again 1 hour later" in body
    if "/c/" not in url:
        return "home", len(body), (1000 if filled else hits), url, modal, fp
    if limited:
        return "rate-limited", len(body), (1000 if filled else hits), url, modal, fp
    if gen:
        return "generating", len(body), (1000 if filled else hits), url, modal, fp
    return (("queued-capacity" if cap else "queued"), len(body),
            (1000 if filled else hits), url, modal, fp)


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
    last_fp = ""             # 2026-09-27: agent-activity fingerprint
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
            st, ln, hits, url, modal, fp = state(tab_prefix)
            stamp = time.strftime("%H:%M:%S")
            print(f"[{name}] {stamp} {st} chars={ln} hits={hits} fp={fp[:40]} url={url[:60]}", flush=True)
            heartbeat(name)
            mk = os.path.join(FLAGS, f"{name}-complete.marker")
            # 2026-09-19 (lesson-64 completion): the DOM filled-regex is a
            # HINT, the server batch-store probe is the GATE. Virtualized
            # rendering can push the report's hex line outside the DOM view
            # (w3 case: server-confirmed report, DOM regex never fired).
            # Probe the server whenever the marker appears ANYWHERE (the
            # packet echo counts — the probe filters truth), and declare
            # COMPLETE only on reportInAssistant. The filled fast-path
            # stays as the first branch for DOM-rendered reports.
            if hits >= 1:
                # SERVER-SIDE CONFIRMATION (lesson 64, 2026-09-12 21:19
                # re-offense): a continuation directive quoting the literal
                # headline + base SHA inoculates the DOM against the filled
                # gate (the watcher retired itself on the LEAD'S OWN
                # directive). The DOM regex alone can NEVER be trusted for
                # completion — confirm the marker lives in an ASSISTANT
                # message server-side before declaring COMPLETE.
                cid = (url or "").split("/c/")[-1].split("/")[0].split("?")[0]
                server_ok = False
                if len(cid) >= 30:
                    try:
                        _pr = subprocess.run(
                            [sys.executable, os.path.join(BASE, "probe_chat.py"), cid],
                            cwd=BASE, capture_output=True, text=True, timeout=60)
                        _pd = json.loads(_pr.stdout.strip().split("\n")[-1])
                        server_ok = bool(_pd.get("reportInAssistant"))
                    except Exception:
                        server_ok = False
                if not server_ok:
                    if hits >= 1000:
                        print(f"[{name}] filled-regex hit but SERVER probe says no "
                              "assistant report — DOM inoculation suspected; NOT complete", flush=True)
                    # else: marker echo only (packet in DOM, report not yet
                    # server-side) — silent probe, generation still in flight.
                else:
                    open(mk, "w").write(f"{time.time()} {url}\n")
                    print(f"[{name}] COMPLETE — marker written (server-confirmed)", flush=True)
                    try:
                        os.remove(SPEC_PATH.format(name=name))
                        os.remove(HB_PATH.format(name=name))
                    except Exception:
                        pass
                    return 0
            if st == "rate-limited":
                note_ratelimit(name)
            _skip_assault = False
            if st == "tablost" or st == "home":
                # LESSON 185 corollary (2026-09-27): on agent lanes the DOM
                # tab state is NOT death — the chat index lags after capacity
                # events and /c/ URLs bounce while the conversation is alive
                # server-side. Gate the assault on the server truth probe.
                if agent_lane(name):
                    alive, msgs, note, bchars, has_report = server_alive(name)
                    if alive and has_report:
                        # 2026-09-30: the tab died AFTER the report landed —
                        # server-confirmed completion, retire cleanly instead
                        # of waiting forever on lesson-185 patience.
                        open(mk, "w").write(f"{time.time()} {url}\n")
                        print(f"[{name}] {stamp} tab {st} but SERVER-SIDE REPORT CONFIRMED — "
                              "COMPLETE (marker written)", flush=True)
                        try:
                            os.remove(SPEC_PATH.format(name=name))
                            os.remove(HB_PATH.format(name=name))
                        except Exception:
                            pass
                        return 0
                    if alive:
                        _zv = _zombie_verdict(name, bchars, False, stamp, st)
                        if _zv == "wait":
                            z = _zombie_track.get(name) or {}
                            _zage = int(time.time() - z.get("since", time.time()))
                            print(f"[{name}] {stamp} tab {st} but SERVER-SIDE ALIVE "
                                  f"({note}, msgs={msgs}, bchars={bchars}) — lesson 185 index lag, "
                                  f"WAITING (no assault; zombie clock {_zage}s/{ZOMBIE_TURN_AFTER}s)", flush=True)
                            _skip_assault = True
                        elif _zv == "zombie" and _cure_attempts.get(name, 0) < CURE_MAX:
                            # s8 CURE-FIRST (2026-09-30): stop the dead turn +
                            # continue in-place — narrative preserved.
                            _cure_attempts[name] = _cure_attempts.get(name, 0) + 1
                            print(f"[{name}] {stamp} zombie turn — s8 stop/continue cure "
                                  f"(attempt {_cure_attempts[name]}/{CURE_MAX}, in-place)", flush=True)
                            _rc = run_with_hb(name, [sys.executable, os.path.join(BASE, "stop_continue.py"),
                                                     name, "queue_watch zombie-turn: batch static, no report"])
                            if _rc == 0:
                                print(f"[{name}] {stamp} s8 CURE LANDED — turn reopened in-place "
                                      "(narrative preserved)", flush=True)
                                _zombie_track.pop(name, None)
                                rec2 = dw._find(name)
                                if rec2 and (rec2.get("tab_id") or "")[:8] != tab_prefix:
                                    tab_prefix = (rec2.get("tab_id") or "")[:8]
                                    write_spec(name, tab_prefix, marker)
                                    print(f"[{name}] {stamp} re-aimed at cured-session tab {tab_prefix}", flush=True)
                                last_len = 0
                                last_fp = ""
                                rounds_since_progress = 0
                                _skip_assault = True
                            else:
                                print(f"[{name}] {stamp} s8 cure failed rc={_rc} — "
                                      "falling back to void+re-dispatch", flush=True)
                        # else: zombie with cure budget exhausted — fall through,
                        # the assault ladder voids + re-dispatches as designed
                    else:
                        print(f"[{name}] {stamp} tab {st} and server probe says DEAD ({note}) "
                              "— agent-lane death confirmed, assault may proceed", flush=True)
                if not _skip_assault:
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
                    elif (os.path.exists(os.path.join(FLAGS, f"capacity_recover.{name}.json"))
                          or os.path.exists(os.path.join(FLAGS, "capacity_recover.json"))):
                        # LESSON 89(b) serialization (2026-09-13): while the
                        # capacity-recover flag exists, recover_capacity.py OWNS the
                        # create fight (supervisor-guarded). A second concurrent
                        # churner here murders both (observed twice: renderer churn,
                        # socket-already-closed). queue_watch only WATCHES for the
                        # completion marker in this regime.
                        print(f"[{name}] {stamp} session destroyed ({st}) but capacity_recover flag "
                              f"present — recover_capacity.py owns the assault (serialized, lesson 89b)",
                              flush=True)
                    elif hold_active(name):
                        print(f"[{name}] {stamp} session destroyed ({st}) — OUTAGE-HOLD: re-dispatch suppressed", flush=True)
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
            # 2026-09-27: the fingerprint (Ran/Todo counters + body len +
            # Stop presence) counts as progress — in-place AGENTS-mode
            # activity never moves the body length alone
            if ln != last_len or fp != last_fp:
                rounds_since_progress = 0
                last_len = ln
                last_fp = fp
            else:
                rounds_since_progress += 1
            # 2026-09-18 outage lesson: plain "queued" MUST run the stuck-clock
            # too — generation requests failing server-side (HTML error page,
            # "No response, Please try again later.") render as plain queued
            # with NO capacity banner; the old reset-to-zero let 3 workers sit
            # dead for 5+ hours with zero auto-recovery.
            if st in ("queued-capacity", "rate-limited", "queued"):
                if rounds_since_progress == 0:
                    stuck_since = 0            # body still changing — not stuck
                elif rounds_since_progress >= 2 and not stuck_since:
                    stuck_since = time.time()
                    print(f"[{name}] {stamp} stuck-clock started ({st}, no progress)", flush=True)
            else:
                stuck_since = 0                # generating/home reset the clock
            # OPERATOR PROTOCOL (2026-09-12), first line: stuck with a
            # Cancel-modal -> dismiss (Cancel) + resend the prompt. Never
            # wait, never follow the popup's own instructions.
            if (st in ("queued-capacity", "rate-limited") and stuck_since and modal
                    and time.time() - stuck_since > UNSTICK_AFTER
                    and unsticks < UNSTICK_MAX and not hold_active(name)):
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
            # LESSON 185 (2026-09-27): for AGENT lanes the void destroys a
            # conversation that may still hold a VERIFIED, queued send — the
            # platform's generation window can drain it long after the DOM
            # goes static. Gate the void on the server truth probe: alive
            # server-side (packet present, conversation intact) = patience,
            # not churn. Dead server-side = assault as designed.
            _thresh = (QUEUED_STATIC_AFTER if st == "queued" else
                       (STUCK_ASSAULT_WORKRICH if ln >= 15000 else STUCK_ASSAULT_AFTER))
            if (st in ("queued-capacity", "rate-limited", "queued") and stuck_since
                    and time.time() - stuck_since > _thresh
                    and stuck_assaults < STUCK_ASSAULT_MAX and not hold_active(name)):
                _agent_alive = False
                if agent_lane(name):
                    _alive, _msgs, _note, _bchars, _has_report = server_alive(name)
                    if _alive and _has_report:
                        # 2026-09-30 zombie-turn doctrine: the report landed
                        # server-side but the DOM never rendered it — retire.
                        open(mk, "w").write(f"{time.time()} {url}\n")
                        print(f"[{name}] {stamp} STUCK in {st} but SERVER-SIDE REPORT CONFIRMED — "
                              "COMPLETE (marker written)", flush=True)
                        try:
                            os.remove(SPEC_PATH.format(name=name))
                            os.remove(HB_PATH.format(name=name))
                        except Exception:
                            pass
                        return 0
                    if _alive:
                        _zv = _zombie_verdict(name, _bchars, False, stamp, st,
                                              thresh_note=f", stuck {int(time.time() - stuck_since)}s")
                        if _zv == "wait":
                            _agent_alive = True
                            z = _zombie_track.get(name) or {}
                            _zage = int(time.time() - z.get("since", time.time()))
                            print(f"[{name}] {stamp} STUCK {_thresh}s in {st} but SERVER-SIDE ALIVE "
                                  f"({_note}, msgs={_msgs}, bchars={_bchars}) — lesson 185: queued send preserved, "
                                  f"extending patience (no void; zombie clock {_zage}s/{ZOMBIE_TURN_AFTER}s)", flush=True)
                            stuck_since = time.time()  # restart the clock; probe again next threshold
                        elif _zv == "zombie" and _cure_attempts.get(name, 0) < CURE_MAX:
                            # s8 CURE-FIRST (2026-09-30): un-wedge in-place
                            # before any void — narrative + pod survive.
                            _cure_attempts[name] = _cure_attempts.get(name, 0) + 1
                            print(f"[{name}] {stamp} zombie turn (stuck in {st}) — s8 stop/continue cure "
                                  f"(attempt {_cure_attempts[name]}/{CURE_MAX}, in-place)", flush=True)
                            _rc = run_with_hb(name, [sys.executable, os.path.join(BASE, "stop_continue.py"),
                                                     name, f"queue_watch zombie-turn stuck in {st}: batch static, no report"])
                            if _rc == 0:
                                print(f"[{name}] {stamp} s8 CURE LANDED — turn reopened in-place "
                                      "(narrative preserved)", flush=True)
                                _zombie_track.pop(name, None)
                                _agent_alive = True   # cured — do NOT void
                                stuck_since = 0
                                last_len = 0
                                last_fp = ""
                                rounds_since_progress = 0
                                rec2 = dw._find(name)
                                if rec2 and (rec2.get("tab_id") or "")[:8] != tab_prefix:
                                    tab_prefix = (rec2.get("tab_id") or "")[:8]
                                    write_spec(name, tab_prefix, marker)
                                    print(f"[{name}] {stamp} re-aimed at cured-session tab {tab_prefix}", flush=True)
                            else:
                                print(f"[{name}] {stamp} s8 cure failed rc={_rc} — "
                                      "falling back to void+re-dispatch", flush=True)
                        # else: zombie with cure budget exhausted — fall through,
                        # _agent_alive stays False, the stuck-assault voids +
                        # fresh-dispatches the dead turn
                if not _agent_alive:
                    stuck_assaults += 1
                    stuck_since = 0
                    print(f"[{name}] {stamp} STUCK {_thresh}s in {st} (chars={ln}) — "
                          f"assault #{stuck_assaults}/{STUCK_ASSAULT_MAX} (fresh dispatch beats a zombie session)",
                          flush=True)
                    run_with_hb(name, [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                     "void", name,
                                     f"stuck in {st} {_thresh}s with zero progress; "
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
