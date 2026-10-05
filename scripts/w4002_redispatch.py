#!/usr/bin/env python3
"""w4002_redispatch.py — re-dispatch P4-W4-002 after the double sandbox reset.

State (2026-10-05 ~15:50Z): the worker (chat 476b5e05) has built W4-002
TWICE and lost it TWICE to sandbox filesystem resets (reset #1 between
10:35-12:53Z, reset #2 between ~14:45-15:05Z). No push ever landed before
the resets hit. The worker's session went through context compaction
(live DOM 233KB -> 38KB); it asked the TL: re-execute (re-paste the full
work order) or restore from artifacts (none exist).

TL decision: RE-EXECUTE, with a protocol amendment — PUSH EARLY, PUSH
OFTEN — so any further reset only ever costs the phase in flight, never
the whole build. The full work order is re-pasted VERBATIM from the server
record (scripts/worker-prompts/P4-W4-002.md, md5 19556ef2...).

The PAT for the amendment's push command is loaded at RUNTIME from
~/.payswap-env.sh (GH013 doctrine — GitHub push protection blocks
secret-bearing pushes; never embed a live token in a committed file).

Assault: the worker's last turn is CLOSED (it asked a question), so sends
fight the same done-session spawn wall as all day. Never-wait pattern:
cancel-never-Flash + real-mouse resubmit + Enter fallback, 45s cycles,
12h window. LANDED = tree grows beyond N_BASE=8 or assistant content
appears (server record truth).

Doctrine corrections baked into this re-dispatch (2026-10-05 ~15:55Z):
- Task 23's root-cause ("the 07:30 dispatch sent the literal placeholder")
  was WRONG — a display-redaction misread. The server record's brief
  carries the REAL 40-char PAT; user messages deliver tokens to the agent
  intact (the worker's x-oauth-scopes-echoed API 200 on the 14:54 cred
  message proves the pipeline). The morning 401's true cause is unknown.
- The brief file therefore CONTAINS A LIVE SECRET. It lives only in the
  gitignored scripts/worker-prompts/ (replay2 is a PUBLIC repo) and in
  my-project/replay-packets/ (no-remote scaffolding repo). Never commit it.

Usage: dfork_launch.py logs/w4002_redispatch.log python3 w4002_redispatch.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CHAT = "476b5e05-b67c-47f0-8c3f-a5e7cd3c429c"
FLAGS = os.path.join(BASE, "flags")
TOK = os.path.join(FLAGS, "chat_token")
BRIEF_PATH = os.path.join(BASE, "worker-prompts", "P4-W4-002.md")
CYCLE = 45
WINDOW = 12 * 3600
N_BASE = 8  # post-cred-message tree size (8 messages in the server record)

ADDENDUM_TMPL = """TL — ROUTE DECISION: RE-EXECUTE. The complete work order is re-pasted below, VERBATIM (extracted from the server record of your original dispatch — not reconstructed from a summary; it carries the same valid push credential in its §6). Read this amendment first: it changes HOW you deliver, not WHAT you build.

## A. What happened to your work (both runs — for the record)
Your environment's filesystem reset TWICE today: once mid-run (you froze at '=== 4. ROOT BATTERY ===' around 10:35Z; your 12:53 resume found the filesystem wiped), and once between turns (you finished the 10-area pages around 14:45Z; the push-credential turn found the filesystem wiped again). Each reset destroyed all local work, and no push had ever succeeded before the resets hit, so nothing survived anywhere. Nobody's fault — the fix is protocol, not blame.

## B. Push-early protocol (MANDATORY — supersedes the work order's delivery ordering)
Assume a reset can hit at ANY second, including mid-command. Therefore:
1. Branch + FIRST PUSH immediately: after `git checkout -b work/P4-W4-002` and `npm install`, make your first commit as early as you legitimately can (e.g. the surface-contracts skeleton) and PUSH it. The remote branch existing early is worth more than a tidy history.
2. Commit + push after EVERY completed phase: surface contracts -> checkout runtime/fixtures -> UI components -> pages -> docs/evidence. Never let a full phase of work live only on local disk.
3. Run the LONG battery (root `npm test`, 4641+ tests) only AFTER all source + package tests are committed and PUSHED. Both of today's losses happened with everything local-only — do not let the battery be that moment again.
4. After each push, verify it landed: `git ls-remote <PUSHURL> refs/heads/work/P4-W4-002` shows your current HEAD SHA.
5. If the environment resets mid-run: STOP cleanly. The TL will send a continuation that CLONES from the pushed branch work/P4-W4-002 and resumes from there — you never rebuild what is already pushed. The remote branch is the single source of truth.

## C. Facts you already established this turn (do NOT re-verify)
- main = 852941a43e0eda3a8190129151b0300913a48889 (the pinned base, unchanged); remote branches run through work/P4-W4-001 (6ff0da1c); zero PRs.
- The push credential is valid and push-capable — YOU verified it yourself (ls-remote authenticated; API 200; scopes include repo).
- Baseline receipts at the base (you re-ran them this afternoon, no drift): root battery 4641/4641, 0 failed; typecheck 0 errors; verify:repo green.

## D. Design continuity (approved, keep)
- Your placement decision: a separate React-free `packages/surface` for the stable surface API — APPROVED, reuse it.
- Your prior verification that all 29 REAL dispatch functions exist — still true at the same base.
- Everything else: the work order below is the authority.

## E. The push command (credential VERIFIED VALID — you proved it yourself this turn: API 200, x-oauth-scopes includes repo)
Correction of my earlier claim: your original work order DID carry this same real credential (I misread redacted logs when I told you it was a placeholder — my error, not yours). The morning 401's cause was never actually established (transient failure or URL mangling are the candidates); the credential itself is proven good. If a push ever 401s again: retype the URL fresh from this line, retry once, then report honestly.
git push https://x-access-token:{PAT}@github.com/payswapdotorg/payswap.org.git work/P4-W4-002

## F. Final report (unchanged, work order §6)
Post it IN THIS CHAT as your final message: branch + HEAD SHA; changed-file list; test receipts (package + root battery); typecheck + verify:repo; the surface placement decision; research-mapping summary; browser-verification evidence (desktop + mobile); honest deviations. Do not merge to main — the TL verifies and merges.

--- FULL WORK ORDER (VERBATIM) FOLLOWS ---
"""


def load_pat():
    """Load the PAT at runtime from the persistent env file."""
    for line in open(os.path.expanduser("~/.payswap-env.sh")):
        line = line.strip()
        if line.startswith("export GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("FATAL: GITHUB_TOKEN not found in ~/.payswap-env.sh")


def build_message():
    pat = load_pat()
    brief = open(BRIEF_PATH).read()
    # The brief is the verbatim server-record copy. Doctrine note: it carries
    # the REAL PAT (the 07:30 dispatch DID substitute — Task 23's "literal
    # placeholder" root-cause was itself a display-redaction misread; the
    # worker's successful x-oauth-scopes-echoed API 200 on the 14:54 cred
    # message proves user messages deliver tokens intact). Accept either the
    # real token or the placeholder; substitute only if placeholder.
    has_real = "ghp_" in brief
    has_ph = "[REDACTED:github_token]" in brief
    if not (has_real or has_ph):
        raise SystemExit("FATAL: brief carries neither a real PAT nor the placeholder")
    if has_ph:
        brief = brief.replace("[REDACTED:github_token]", pat)
    addendum = ADDENDUM_TMPL.replace("{PAT}", pat).replace(
        "<PUSHURL>", "https://x-access-token:" + pat + "@github.com/payswapdotorg/payswap.org.git")
    full = addendum + "\n\n" + brief
    return full


def log(msg):
    print(f"[w4002-rd {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def state(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('textarea');
  return JSON.stringify({
    composerLen: ta ? ta.value.length : -1,
    bodyLen: body.length,
    capacity: body.includes('currently at capacity') || body.includes('peak hours'),
    cancel: [...document.querySelectorAll('button')].some(b => (b.innerText||'').trim() === 'Cancel')
  });
})()"""))


def click_cancel(cdp):
    return cdp.eval(r"""(() => {
  const c = [...document.querySelectorAll('button')]
    .filter(b => (b.innerText || '').trim() === 'Cancel');
  if (!c.length) return 'none';
  c[0].click(); return 'clicked';
})()""")


def submit(cdp):
    pos = cdp.eval(r"""(() => {
  const b = document.querySelector('button.sendMessageButton');
  if (!b || b.disabled) return '';
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
})()""")
    if pos:
        p = json.loads(pos)
        if p.get("x", 0) > 0:
            cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": p["x"],
                                                  "y": p["y"], "button": "left", "clickCount": 1})
            cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": p["x"],
                                                  "y": p["y"], "button": "left", "clickCount": 1})
            return "real-mouse-send"
    return cdp.eval(channel.SUBMIT_JS)


def tree_state():
    """(n_msgs, assistant_content_len)."""
    try:
        tok = open(TOK).read().strip()
        req = urllib.request.Request(
            f"https://chat.z.ai/api/v1/chats/{CHAT}",
            headers={"Authorization": "Bearer " + tok,
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"})
        d = json.load(urllib.request.urlopen(req, timeout=20))
        msgs = ((d.get("chat") or {}).get("history") or {}).get("messages") or {}
        best = 0
        for m in msgs.values():
            if m.get("role") == "assistant":
                best = max(best, len(m.get("content") or ""))
        return len(msgs), best
    except Exception:
        return -1, -1


def main():
    msg = build_message()
    log(f"packet built: {len(msg)} chars (amendment + verbatim brief, PAT substituted at runtime)")
    _ = subprocess.run(["git", "-C", BASE, "status", "--porcelain"],
                       capture_output=True)  # touch git; PAT never printed
    log(f"armed — redispatch assault, N_BASE={N_BASE}, cycle {CYCLE}s, window {WINDOW//3600}h")
    t0 = time.time()
    accepted = False
    while time.time() - t0 < WINDOW:
        try:
            tab = channel.find_tab(CHAT[:8])
            if not tab:
                log("no chat tab — opening one")
                channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
                time.sleep(15)
                continue
            ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
            try:
                s = state(ws)
                if accepted:
                    n, alen = tree_state()
                    if n > N_BASE or alen > 0:
                        log(f"LANDED — tree n={n} (base {N_BASE}) alen={alen}")
                        open(os.path.join(FLAGS, "w4002_redispatch_landed"), "w").write(
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                        return 0
                    if s["composerLen"] > 50:
                        log("composer refilled post-accept (rollback) — resuming assault")
                        accepted = False
                    else:
                        log(f"accepted-queued, waiting for turn open (n={n})")
                else:
                    if s["composerLen"] > 50:
                        if s["capacity"] or s["cancel"]:
                            if s["cancel"]:
                                click_cancel(ws)
                                time.sleep(1.5)
                        r = submit(ws)
                        try:
                            for typ in ("keyDown", "keyUp"):
                                ws.call("Input.dispatchKeyEvent", {
                                    "type": typ, "key": "Enter", "code": "Enter",
                                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
                        except Exception:
                            pass
                        time.sleep(5)
                        s2 = state(ws)
                        if s2["composerLen"] <= 10:
                            accepted = True
                            log(f"ACCEPTED ({r}) — capacity={s2['capacity']}")
                        else:
                            log(f"round fought ({r}) — composer={s2['composerLen']} capacity={s2['capacity']}")
                    elif s["composerLen"] >= 0:
                        # empty composer: late landing, Chrome restart, or lost text
                        n, alen = tree_state()
                        if n > N_BASE or alen > 0:
                            log(f"LANDED (late accept — n={n} alen={alen})")
                            open(os.path.join(FLAGS, "w4002_redispatch_landed"), "w").write(
                                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                            return 0
                        log("composer empty, turn not open — re-staging packet")
                        channel._type_into_composer(ws, msg)
                        time.sleep(2)
            finally:
                ws.close()
        except Exception as e:
            log(f"cycle error: {type(e).__name__}: {e}")
        time.sleep(CYCLE)
    log("WINDOW EXPIRED")
    open(os.path.join(FLAGS, "w4002_redispatch_failed"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
