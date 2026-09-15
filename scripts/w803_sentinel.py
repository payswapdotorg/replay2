#!/usr/bin/env python3
"""w803_sentinel.py — session A final-stretch sentinel.

Watches for the W605 merge on origin/main; when it lands (and the operator
is logged in, and no w803 branch exists — the collision guard), dispatches
W803 as a watchable agents-tab session through the replay console
(the lesson-121 ruling). Then monitors the session for the completion
marker and the branch for landing. Separately alerts when W806 becomes
unblocked (W801-W805 all merged in main).
"""
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(HERE, "flags")
SPORTA = "/home/z/sporta"
TEMPLATE = "/home/z/my-project/worker-prompts/w803-visual-quality-gates.template.md"
RENDERED = os.path.join(HERE, "worker-prompts", "w803-visual-quality-gates.md")
BRANCH = "w803-visual-quality-gates"
NAME = "w803-visual-quality-gates"
LOG = os.path.join(HERE, "logs", "w803_sentinel.log")
MARKER = "SPORTA-COMPLETION-REPORT W803 END"
DEADLINE_H = 10


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%m-%d %H:%M:%S ") + msg + "\n")


def flag(name):
    return os.path.join(FLAGS, name)


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass
    log("OUTBOX: " + text[:160])


def hb():
    try:
        open(os.path.join(FLAGS, "heartbeat"), "w").write(str(int(time.time())))
    except Exception:
        pass


def git(args, cwd=SPORTA):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=90)


def get_pat():
    try:
        with open(os.path.expanduser("~/.secrets/env.sh")) as f:
            for line in f:
                if "PAYSWAP_PAT=" in line or "GITHUB_TOKEN=" in line:
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v.startswith(("ghp_", "github_pat_")):
                        return v
    except Exception:
        pass
    return None


def main_sha():
    r = git(["rev-parse", "origin/main"])
    return r.stdout.strip() if r.returncode == 0 else None


def merged(wid):
    """True if origin/main shows the item COMPLETE. Two signals, OR'd:
    the evidence-row commit message ('<WID> COMPLETE' — the session-B
    convention, e.g. 2ef2be9 'W804 COMPLETE' landed with NO merge commit)
    or the ledger row itself reading COMPLETE (catches any landing style)."""
    r = git(["log", "--grep", f"{wid} COMPLETE", "--oneline", "-1", "origin/main"])
    if r.stdout.strip():
        return True
    try:
        r2 = git(["show", f"origin/main:docs/status/work-item-status.md"])
        for line in r2.stdout.splitlines():
            if line.startswith(f"| {wid} "):
                return "COMPLETE" in line
    except Exception:
        pass
    return False


def branch_exists():
    r = git(["ls-remote", "origin", BRANCH])
    return bool(r.stdout.strip())


def login_ready():
    return os.path.exists(flag("LOGIN_READY"))


def dispatch(tries=3):
    pat = get_pat()
    if not pat:
        outbox("W803 dispatch blocked: PAT missing from ~/.secrets/env.sh — cannot render packet.")
        return False
    for attempt in range(1, tries + 1):
        sha = main_sha()
        if not sha:
            time.sleep(20)
            continue
        with open(TEMPLATE) as f:
            packet = f.read()
        packet = packet.replace("__BASE__", sha).replace("__PAT__", pat)
        os.makedirs(os.path.dirname(RENDERED), exist_ok=True)
        with open(RENDERED, "w") as f:
            f.write(packet)
        os.chmod(RENDERED, 0o600)
        log(f"dispatch attempt {attempt} (base {sha[:9]})")
        r = subprocess.run(
            ["/home/z/.venv/bin/python3", os.path.join(HERE, "dispatch_worker.py"),
             "create", NAME, RENDERED],
            capture_output=True, text=True, timeout=1800)
        log(f"dispatch rc={r.returncode} tail={(r.stdout or r.stderr)[-300:]!r}")
        if r.returncode == 0:
            outbox(f"W803 DISPATCHED (attempt {attempt}) — watchable agents-tab session "
                   f"'{NAME}', base {sha[:9]}. The session appears in your Agents tab; "
                   "a watch tab is opening. I verify + merge when the branch lands.")
            try:
                reg = os.path.join(FLAGS, "session_registry.jsonl")
                tab_id = url = None
                if os.path.exists(reg):
                    last = [l for l in open(reg).read().splitlines() if l.strip()][-1:]
                    if last:
                        rec = json.loads(last[0])
                        tab_id, url = rec.get("tab_id"), rec.get("url")
                if url:
                    subprocess.run(
                        ["/home/z/.venv/bin/python3", "-c",
                         f"import sys;sys.path.insert(0,'{HERE}');"
                         f"from channel import new_tab;t=new_tab({url!r});"
                         "print('watch tab', bool(t))"],
                        capture_output=True, text=True, timeout=60)
                if tab_id:
                    subprocess.Popen(
                        ["/home/z/.venv/bin/python3",
                         os.path.join(HERE, "queue_watch.py"), NAME, tab_id, MARKER],
                        stdout=open(os.path.join(HERE, "logs", f"queue_watch.{NAME}.log"), "a"),
                        stderr=subprocess.STDOUT,
                        start_new_session=True, cwd=HERE)
                    log(f"queue_watch armed for {NAME} (tab {str(tab_id)[:8]})")
            except Exception as e:
                log(f"watch tab/queue_watch: {e!r}")
            return True
        if r.returncode == 3:
            outbox("W803 dispatch hit the capacity wall — supervisor recover_capacity "
                   "owns the assault (never waits passively).")
            return True  # supervisor owns it from here
        time.sleep(30)
    outbox("W803 dispatch FAILED after retries — TL attention needed.")
    return False


def main():
    log("w803_sentinel online (waiting on W605 merge; W806-unblock watch armed)")
    if not os.path.exists(flag("W803_SENTINEL_ARMED")):
        open(flag("W803_SENTINEL_ARMED"), "w").write(time.strftime("%H:%M:%S"))
        outbox("Final-stretch sentinel armed: the moment W605 merges into main I dispatch "
               "W803 (visual quality gates) as a watchable console session, then watch for "
               "its marker + branch. I also alert when W806 unblocks (W801-W805 all merged).")
    deadline = time.time() + DEADLINE_H * 3600
    dispatched = os.path.exists(flag("W803_DISPATCHED"))
    w806_alerted = os.path.exists(flag("W806_UNBLOCKED"))
    login_needed_noted = False
    while time.time() < deadline:
        hb()
        try:
            git(["fetch", "--quiet", "origin", "main"])
            if not dispatched and merged("W605"):
                if branch_exists():
                    open(flag("W803_STOOD_DOWN"), "w").write("branch-exists")
                    outbox("W605 merged AND a w803 branch already exists — the parallel "
                           "lane dispatched it. Standing down per the collision guard "
                           "(W305 precedent). Switching to monitor only.")
                    dispatched = True
                elif not login_ready():
                    if not login_needed_noted:
                        outbox("W605 has MERGED — W803 is dispatch-ready, but the console "
                               "is logged out. Agents-tab creation needs your login "
                               "(the W604 lesson). Log in through the replay image and "
                               "the dispatch fires automatically.")
                        login_needed_noted = True
                else:
                    if dispatch():
                        open(flag("W803_DISPATCHED"), "w").write(time.strftime("%H:%M:%S"))
                        dispatched = True
            if dispatched and not os.path.exists(flag("BRANCH_w803")):
                if branch_exists():
                    r = git(["ls-remote", "origin", BRANCH])
                    sha = r.stdout.split()[0] if r.stdout else "?"
                    open(flag("BRANCH_w803"), "w").write(sha)
                    outbox(f"W803 BRANCH LANDED: {BRANCH} @ {sha[:9]} — the worker "
                           "delivered. TL: fresh-fetch guard, full battery, review, merge.")
            if not w806_alerted and all(merged(w) for w in
                                        ("W801", "W802", "W803", "W804", "W805")):
                open(flag("W806_UNBLOCKED"), "w").write(time.strftime("%H:%M:%S"))
                w806_alerted = True
                outbox("W806 UNBLOCKED — W801 through W805 all merged. The release-"
                       "readiness TL review (my lane) can begin.")
        except Exception as e:
            log(f"loop error {e!r}")
        time.sleep(60)
    log("deadline — standing down")


if __name__ == "__main__":
    main()
