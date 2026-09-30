#!/usr/bin/env python3
"""p2_fix_watch.py — TL2 product-phase routed-finding watcher (campaign plane).

MISSION (FLAUZ product phase, TL2-PRODUCT-HANDOFF): TL2 is READY-TO-CLAIM.
TL4 owns the P2-FIX namespace and routes findings to owning TLs. This
watcher polls three surfaces for routed findings, classifies the owning
team, enqueues TL2 / UNCLEAR items ONCE (cross-surface dedupe by finding
id) and posts exactly ONE outbox notification per finding. It NEVER
dispatches — registry claim, WO instantiation and worker dispatch remain
station decisions (claim protocol: P2-FIX ID -> registry claim -> dedicated
branch -> targeted tests -> runtime evidence where required -> PR -> main
-> TL4 independent retest).

Surfaces (git-protocol only; the shared-IP anonymous GitHub API quota is
exhausted, the git protocol is not) — all reads go through the watcher's
own SHALLOW surface repo (scripts/flauz-surface, depth 25, single-branch
main; rebuilt lazily after a reset in ~1 min). The FULL clone at
/home/z/Flauz is a STATION ASSET only (verification, landing, worker
bases) — the watcher manages its background rebuild but never reads it:
  S1  origin/main docs/FLAUZ-PROGRAM/findings/        (new finding files)
  S2  origin/main docs/FLAUZ-PROGRAM/WORK-REGISTRY.md (P2-FIX blocks)
  S3  pull refs via `git ls-remote refs/pull/*/head`  (new PR numbers only;
      first run records a silent baseline, squash-merged history is never
      re-classified)

Routing classification (TL4 FINDING PROTOCOL):
  explicit "Domain: TLx" / "Owning TL: TLx"   -> TLx   (TL2: enqueue+notify;
                                                      other teams: silent)
  else single-team keyword vote               -> that team
  else multi-team / no signal                 -> UNCLEAR (enqueue + notify,
                                                      station judgment)

Resident duties piggybacked on every cycle:
  - flags/heartbeat touch (console agent-liveness card)
  - operator_inbox.jsonl tailing (new lines logged; a `PAT <token>` line is
    captured to /home/z/.flauz_env mode 600 and redacted from the inbox —
    the reset-wiped PAT re-supply channel)
  - self-healing background rebuild of the Flauz clone when fully absent

PATH-DEPTH LAW: this file must live at <tree>/scripts/replay-campaign/ —
ROOT resolves three levels up from this file, so the LIVE copy under
/home/z/replay2 writes flags/logs where the console renders them. The
persistent MASTER lives at my-project/scripts/replay-campaign/ (platform
snapshot tree) and is never executed directly.

State files (all under <tree>/scripts/flags/, survive daemon restarts):
  p2_fix_tl2_findings.json  the claim queue (id, domain, sources, excerpt)
  p2_fix_seen.json          dedupe set + PR baseline + acceptance-dir memory
"""
import json
import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))            # depth law
FLAGS = os.path.join(ROOT, "scripts", "flags")
LOGS = os.path.join(ROOT, "scripts", "logs")
QUEUE = os.path.join(FLAGS, "p2_fix_tl2_findings.json")
SEENF = os.path.join(FLAGS, "p2_fix_seen.json")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
INBOX = os.path.join(FLAGS, "operator_inbox.jsonl")
HEARTBEAT = os.path.join(FLAGS, "heartbeat")
ARM_MARKER = os.path.join(FLAGS, "p2_fix_arm_marker")

FLAUZ = os.environ.get("FLAUZ_DIR", "/home/z/Flauz")
FLAUZ_URL = os.environ.get("FLAUZ_URL", "https://github.com/payswapdotorg/Flauz.git")
SURFACE = os.environ.get(
    "FLAUZ_SURFACE", os.path.join(ROOT, "scripts", "flauz-surface"))
# RESET-#4 hardening: (\\.git)? — tolerate BOTH URL spellings. A suffix-less
# spawn (redeploy's old bug) was invisible to the guard, so the watcher
# purged the dir under the live clone and double-cloned. Pattern
# consistency is the law for every spawner; tolerance here is the backstop.
FULL_CLONE_PAT = "flauz_full_clone|git clone .*Flauz(\\.git)? %s$" % FLAUZ
SURFACE_PAT = "git clone .*flauz-surface"
PAT_FILE = os.environ.get("FLAUZ_PAT_FILE", "/home/z/.flauz_env")
POLL = int(os.environ.get("P2FIX_POLL", "60"))
PR_EVERY = int(os.environ.get("P2FIX_PR_EVERY", "5"))

REGISTRY = "docs/FLAUZ-PROGRAM/WORK-REGISTRY.md"
FINDINGS_DIR = "docs/FLAUZ-PROGRAM/findings/"
ACCEPT_DIR = "docs/FLAUZ-PROGRAM/acceptance/"

ID_RE = re.compile(r"P2-FIX-\d{3,}")
DOMAIN_RE = re.compile(
    r"(?:domain|own(?:ing|er)\s+tl)\s*[:=]\s*TL\s*([1-4])", re.I)
PAT_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,255}|gho_[A-Za-z0-9]{36})")

TEAM_KW = {
    "TL1": ("code oss", "code-oss", "upstream", "packaging", "service seam",
            "fork-critical", "fork critical", "control plane", "vscode",
            "build system", "release artifact"),
    "TL2": ("agent os", "agent-os", "flauz-agent", "flauz-models",
            "orchestration", "workflow", "a2a", "memory", "lease",
            "provider routing", "model fabric", "agent runtime",
            "durable execution", "cancellation", "retry policy",
            "approvals", "takeover", "provenance", "model capabilit",
            "tool policy", "model state"),
    "TL3": ("browser", "cdp", "chromium", "environment lifecycle", "ssh",
            "docker", "container", "resourceref", "resource graph",
            "continuity", "restoration", "e2b", "cloud execution",
            "environment resolver"),
    "TL4": ("information architecture", "accessib", "discoverab",
            "navigation", "empty state", "loading state", "onboarding flow",
            "release quality", "compatibility surface", "performance budget",
            "cross-surface consisten", "dead end", "orphan state"),
}

STATE = {"seen": {}, "prs": {}, "acc_seen": [], "baseline_done": False,
         "queue": {"findings": []}}
INBOX_POS = 0


def log(msg):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def notify(text):
    os.makedirs(FLAGS, exist_ok=True)
    line = json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                       "text": str(text)[:2000]}) + "\n"
    with open(OUTBOX, "a") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def load_state():
    global STATE, INBOX_POS
    s = {}
    try:
        with open(SEENF) as f:
            s = json.load(f)
    except Exception:
        pass
    for k in ("seen", "prs", "acc_seen", "baseline_done"):
        if k in s:
            STATE[k] = s[k]
    try:
        with open(QUEUE) as f:
            STATE["queue"] = json.load(f)
    except Exception:
        pass
    INBOX_POS = os.path.getsize(INBOX) if os.path.exists(INBOX) else 0


def persist():
    save = {"seen": STATE["seen"], "prs": STATE["prs"],
            "acc_seen": STATE["acc_seen"],
            "baseline_done": STATE["baseline_done"]}
    os.makedirs(FLAGS, exist_ok=True)
    tmp = SEENF + ".tmp"
    with open(tmp, "w") as f:
        json.dump(save, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, SEENF)
    tmp = QUEUE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(STATE["queue"], f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, QUEUE)


def repo_ready(d):
    """True when the repo at `d` can serve `git show origin/main:...` reads.

    Completion oracle for a `git clone` in progress: refs appear only at
    the very end, so a half-cloned repo (observed dead at 1.4G on
    2026-09-29 after a watcher fetch raced the clone's own downloads)
    correctly reports not-ready. refs/remotes/origin/main is checked first
    (the shallow surface repo's canonical ref), refs/heads/main as the
    fallback (a completed full clone has both)."""
    if not os.path.exists(os.path.join(d, ".git")):
        return False
    for ref in ("refs/remotes/origin/main", "refs/heads/main"):
        try:
            r = subprocess.run(["git", "-C", d, "rev-parse", "--verify",
                                "-q", ref],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _proc_alive(pattern):
    r = subprocess.run(["pgrep", "-af", pattern],
                       capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def git(*args, **kw):
    """Run git in the SURFACE repo (the watcher's shallow read repo)."""
    timeout = kw.get("timeout", 150)
    r = subprocess.run(["git", "-C", SURFACE] + list(args),
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "git failed").strip()[:250])
    return r.stdout


def classify(text):
    m = DOMAIN_RE.search(text or "")
    if m:
        return "TL%s" % m.group(1), "explicit-domain"
    low = (text or "").lower()
    hits = set()
    for team, kws in TEAM_KW.items():
        if any(k in low for k in kws):
            hits.add(team)
    if len(hits) == 1:
        return hits.pop(), "keyword"
    if not hits:
        return "UNCLEAR", "no-signal"
    return "UNCLEAR", "multi-team:" + "+".join(sorted(hits))


def queue_upsert(fid, status, source, excerpt):
    for f in STATE["queue"]["findings"]:
        if f["id"] == fid:
            f["status"] = status
            if source not in f["sources"]:
                f["sources"].append(source)
            return
    STATE["queue"]["findings"].append({
        "id": fid, "status": status, "sources": [source],
        "first_seen": int(time.time() * 1000),
        "excerpt": (excerpt or "")[:600]})


def handle(fid, dom, basis, source, excerpt):
    rec = STATE["seen"].get(fid)
    if rec is None:
        rec = {"domain": dom, "basis": basis, "sources": [source],
               "first_seen": int(time.time() * 1000), "notified_as": None}
        STATE["seen"][fid] = rec
        log("NEW %s domain=%s basis=%s source=%s" % (fid, dom, basis, source))
    else:
        if source not in rec.get("sources", []):
            rec["sources"].append(source)
        if dom != "UNCLEAR":
            rec["domain"], rec["basis"] = dom, basis
    prev = rec.get("notified_as")
    if dom == "TL2":
        if prev != "TL2":
            queue_upsert(fid, "TL2", source, excerpt)
            n = len(STATE["queue"]["findings"])
            if prev is None:
                notify("P2-FIX ROUTED TO TL2: %s (source: %s, basis: %s). "
                       "Ready-to-claim queue depth %d. Claim protocol: "
                       "registry claim -> dedicated branch -> WO "
                       "(p2fix-wo-template.md) -> dispatch from replay. "
                       "Excerpt: %s" % (fid, source, basis, n,
                                        (excerpt or "")[:200]))
            else:
                notify("ROUTING RESOLVED TO TL2: %s (was %s via earlier "
                       "surface; now %s via %s). Queue depth %d." %
                       (fid, prev, basis, source,
                        len(STATE["queue"]["findings"])))
            rec["notified_as"] = "TL2"
    elif dom == "UNCLEAR":
        if prev is None:
            queue_upsert(fid, "UNCLEAR", source, excerpt)
            notify("P2-FIX ROUTING UNCLEAR: %s (source: %s, basis: %s) — "
                   "station judgment required (multi-team or no domain "
                   "signal). Queued for review." % (fid, source, basis))
            rec["notified_as"] = "UNCLEAR"
    else:
        if prev == "TL2":
            queue_upsert(fid, "RECLASSIFIED-" + dom, source, excerpt)
            notify("ROUTING CORRECTED: %s now resolves %s (was TL2 via an "
                   "earlier surface) — TL2 queue item demoted; station to "
                   "verify against the finding text." % (fid, dom))
            rec["notified_as"] = dom
        elif prev is None:
            rec["notified_as"] = dom   # other team: recorded, never notified
    persist()


def s_registry():
    try:
        txt = git("show", "origin/main:" + REGISTRY)
    except Exception as e:
        log("registry read failed: %s" % e)
        return
    ids = {}
    for m in ID_RE.finditer(txt):
        ids.setdefault(m.group(0), txt[max(0, m.start() - 300):m.start() + 700])
    for fid, ctx in ids.items():
        rec = STATE["seen"].get(fid)
        if rec and "work-registry" in rec.get("sources", []):
            continue
        dom, basis = classify(ctx)
        handle(fid, dom, basis, "work-registry", ctx)


def s_findings():
    try:
        out = git("ls-tree", "--name-only",
                  "origin/main:" + FINDINGS_DIR.rstrip("/"))
    except Exception:
        return                       # dir absent = no findings yet (normal)
    for name in [l.strip() for l in out.splitlines() if l.strip()]:
        fidm = ID_RE.search(name)
        fid = fidm.group(0) if fidm else "FILE:" + name
        rec = STATE["seen"].get(fid)
        if rec and "findings-dir" in rec.get("sources", []):
            continue
        content = ""
        try:
            content = git("show", "origin/main:" + FINDINGS_DIR + name)
        except Exception:
            pass
        dom, basis = classify(content or name)
        handle(fid, dom, basis, "findings-dir", content or name)


def s_acceptance():
    try:
        out = git("ls-tree", "--name-only",
                  "origin/main:" + ACCEPT_DIR.rstrip("/"))
    except Exception:
        return
    names = [l.strip() for l in out.splitlines() if l.strip()]
    for n in names:
        if n not in STATE["acc_seen"]:
            log("acceptance receipt on main: %s" % n)
    STATE["acc_seen"] = names


def s_prs():
    if not STATE.get("baseline_done"):
        r = subprocess.run(["git", "ls-remote", FLAUZ_URL, "refs/pull/*/head"],
                           capture_output=True, text=True, timeout=90)
        if r.returncode != 0:
            log("pr baseline ls-remote failed: %s" % (r.stderr or "")[:150])
            return
        STATE["prs"] = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith("refs/pull/"):
                num = parts[1].split("/")[2]
                STATE["prs"]["PR-" + num] = {"sha": parts[0], "baseline": True}
        STATE["baseline_done"] = True
        log("PR baseline recorded: %d pull refs (silent, no classification)"
            % len(STATE["prs"]))
        persist()
        return
    r = subprocess.run(["git", "ls-remote", FLAUZ_URL, "refs/pull/*/head"],
                       capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        log("ls-remote failed: %s" % (r.stderr or "")[:150])
        return
    live = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith("refs/pull/"):
            live[parts[1].split("/")[2]] = parts[0]
    for num, sha in live.items():
        key = "PR-" + num
        rec = STATE["prs"].get(key)
        if rec and rec.get("sha") == sha:
            continue
        if rec is None:               # genuinely NEW pull ref since baseline
            log("new pull ref %s — inspecting" % key)
            body = ""
            try:
                git("fetch", "-q", "origin", "refs/pull/%s/head" % num,
                    timeout=150)
                body = git("log", "-1", "--format=%B", "FETCH_HEAD",
                           timeout=60)
            except Exception as e:
                log("pull ref %s inspect failed: %s" % (num, e))
            ids = sorted(set(ID_RE.findall(body or "")))
            if ids:
                dom, basis = classify(body)
                for fid in ids:
                    handle(fid, dom, basis + "+pr", "open-pr", body)
            else:
                handle(key, "UNCLEAR", "pr-without-finding-id", "open-pr",
                       (body or "")[:400])
            STATE["prs"][key] = {"sha": sha, "seen_at": int(time.time() * 1000)}
        else:
            rec["sha"] = sha          # force-push update; no re-classify
    persist()


def maybe_rebuild_clone():
    """Manage the STATION full clone (/home/z/Flauz): purge dead incomplete
    clones, start a background rebuild when absent. The watcher's surfaces
    never depend on it — they read the shallow surface repo."""
    if repo_ready(FLAUZ):
        return
    if _proc_alive(FULL_CLONE_PAT):
        return
    if os.path.exists(FLAUZ):
        log("dead incomplete Flauz clone detected — purging + rebuilding")
        try:
            subprocess.run(["rm", "-rf", FLAUZ], timeout=600)
        except Exception as e:
            log("purge failed: %s" % e)
            return
    else:
        log("Flauz clone MISSING — background rebuild started")
    os.makedirs(LOGS, exist_ok=True)
    with open(os.path.join(LOGS, "flauz_clone.log"), "ab") as lf:
        # Direct full clone — the 2026-09-29 "OOM wall" was a MISDIAGNOSIS:
        # every clone death traced to self-inflicted interference (the
        # fetch-race + the broken-pattern purge loop's rm-under-live-clone,
        # signature: 'fatal: could not open tmp_pack_* for reading'). A
        # clean run completed in 3 min. flauz_full_clone.sh (blobless
        # two-phase) stays in the campaign dir as the documented fallback
        # if genuine OOM evidence ever materializes.
        subprocess.Popen(["git", "clone", FLAUZ_URL, FLAUZ],
                         stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                         start_new_session=True)


def ensure_surface():
    """Guarantee the watcher's shallow read repo exists and is ready.

    depth 25 / single-branch main: full tree at the tip (everything the
    surfaces read), a sliver of history, ~1 min to rebuild after a reset."""
    if repo_ready(SURFACE):
        return True
    if _proc_alive(SURFACE_PAT):
        return False            # a build is already running; wait for it
    log("surface repo missing — shallow build started")
    try:
        if os.path.exists(SURFACE):
            subprocess.run(["rm", "-rf", SURFACE], timeout=300)
        os.makedirs(os.path.dirname(SURFACE), exist_ok=True)
        r = subprocess.run(
            ["git", "clone", "--depth", "25", "--single-branch",
             "--branch", "main", FLAUZ_URL, SURFACE],
            capture_output=True, text=True, timeout=280)
        if r.returncode != 0:
            log("surface build failed: %s" % (r.stderr or "")[:200])
            return False
        log("surface repo ready (shallow depth 25 @ main)")
        return True
    except Exception as e:
        log("surface build error: %s" % e)
        return False


def redact_inbox(token):
    global INBOX_POS
    try:
        with open(INBOX) as f:
            raw = f.read()
        raw = raw.replace(token, "[CAPTURED:pat]")
        with open(INBOX, "w") as f:
            f.write(raw)
        INBOX_POS = os.path.getsize(INBOX)
    except Exception:
        pass


def tail_inbox():
    global INBOX_POS
    if not os.path.exists(INBOX):
        return
    size = os.path.getsize(INBOX)
    if size < INBOX_POS:
        INBOX_POS = 0                 # truncated / rotated
    if size == INBOX_POS:
        return
    with open(INBOX) as f:
        f.seek(INBOX_POS)
        chunk = f.read()
        INBOX_POS = f.tell()
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        text = str(d.get("text", ""))
        log("OPERATOR INBOX: %s" % text[:300])
        m = PAT_RE.search(text)
        if m:
            token = m.group(1)
            try:
                with open(PAT_FILE, "w") as f:
                    f.write(token + "\n")
                os.chmod(PAT_FILE, 0o600)
                log("PAT captured to %s (%d chars, mode 600)"
                    % (PAT_FILE, len(token)))
                notify("PAT captured to %s (mode 600, outside all repos) — "
                       "landing PRs / registry claims / campaign-script "
                       "pushes are unblocked. Inbox line redacted." % PAT_FILE)
                redact_inbox(token)
            except Exception as e:
                log("PAT capture failed: %s" % e)


def arm_notice():
    fresh = False
    try:
        fresh = time.time() - os.path.getmtime(ARM_MARKER) < 21600
    except Exception:
        pass
    if fresh:
        return
    notify("TL2 product-phase watcher ARMED: polling the findings dir, "
           "WORK-REGISTRY P2-FIX blocks and pull refs every %ds. TL2 = "
           "READY-TO-CLAIM; queue empty at arm time; first sweep surfaces "
           "anything routed during the reset blackout. No dispatch happens "
           "automatically — claim + WO + dispatch stay station decisions." % POLL)
    with open(ARM_MARKER, "w") as f:
        f.write(str(int(time.time() * 1000)))


def main():
    load_state()
    log("p2_fix_watch UP (product phase) poll=%ds flauz=%s root=%s"
        % (POLL, FLAUZ, ROOT))
    arm_notice()
    cycle = 0
    while True:
        try:
            os.makedirs(FLAGS, exist_ok=True)
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
            tail_inbox()
            maybe_rebuild_clone()
            if ensure_surface():
                try:
                    git("fetch", "-q", "origin", "main", timeout=240)
                    s_registry()
                    s_findings()
                    s_acceptance()
                    if cycle % PR_EVERY == 0:
                        s_prs()
                except Exception as e:
                    log("surface error: %s" % e)
            else:
                log("surface repo not ready — surfaces idle "
                    "(build in progress?)")
        except Exception as e:
            log("cycle error: %s" % e)
        cycle += 1
        time.sleep(POLL)


if __name__ == "__main__":
    main()
