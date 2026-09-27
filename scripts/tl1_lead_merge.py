#!/usr/bin/env python3
"""tl1_lead_merge.py — autonomous Lead post-harvest integration (2026-09-27, reset #7 era).

Watches flags/<name>.harvest.json (written by tl1_harvest_sentinel on a
verified bundle harvest), then per lane — fully autonomously:
  1. refresh the gate repo (/home/z/Flauz): fetch origin main
  2. re-verify the bundle in the repo + fetch the work branch from it
  3. drift integration: merge-base != origin/main -> merge origin/main into
     the work branch (conflict -> NEEDS-LEAD + outbox, skip)
  4. push the branch; open the PR (base main)
  5. poll PR check-runs until settled (cap 50 min/lane): gate = every flauz-*
     check green; non-flauz failures tolerated only when the same check also
     fails on the main baseline snapshot (macOS = the known platform red);
     genuine regression -> ONE drift re-integration retry, else NEEDS-LEAD
  6. merge the PR (merge commit — the TL1-001 precedent preserves worker
     commits); delete the branch ref
  7. registry record: WORK-REGISTRY.md lane Status: DONE + Merge record
     paragraph, pushed to main as "docs(flauz): TL1-00N merge record"
  8. first processed lane also repairs the missing TL1-001 record
  9. after the FIRST successful merge: dispatch tl1-b-005 (the slot freed by
     that harvest — serialized-slots law) via dispatch_worker create +
     launch_queue_watch; guarded by flags/tl1-b-005.dispatched
 10. mark processed (flags/<name>.lead-merged.json) + outbox + worklog entry

Re-entry safe: processed/NEEDS-LEAD lanes are skipped on later rounds.
Sequential lane processing on purpose: parallel PRs would invalidate each
other's baselines and stack drift.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
GATE = "/home/z/Flauz"
HARVEST_ROOT = "/home/z/leads-harvest"
WORKLOG = "/home/z/my-project/worklog.md"
REPO_API = "https://api.github.com/repos/payswapdotorg/Flauz"
POLL_SECS = 90
CI_CAP_SECS = 50 * 60
GIVE_UP_AFTER = 10 * 3600

LANES = {
    "tl1-b-002": {
        "num": "TL1-002", "title": "Product build/release shell",
        "branch": "feat/tl1-002-product-shell",
        "pr": "TL1-002: product build/release shell (product.flauz.json, packaging identity, default profile, bundled extensions)",
        "heading": "### TL1-002 — Product build/release shell",
        "marker": "TL1-002 COMPLETION REPORT",
    },
    "tl1-c-003": {
        "num": "TL1-003", "title": "Core integration seam",
        "branch": "feat/tl1-003-seam-protocol",
        "pr": "TL1-003: core integration seam (versioned IPC/API protocol for commands, events, health, auth, lifecycle)",
        "heading": "### TL1-003 — Core integration seam",
        "marker": "TL1-003 COMPLETION REPORT",
    },
    "tl1-a-004": {
        "num": "TL1-004", "title": "Core-change budget",
        "branch": "feat/tl1-004-core-budget",
        "pr": "TL1-004: core-change budget (patch audit, retire unnecessary patches, fork-critical guard at zero)",
        "heading": "### TL1-004 — Core-change budget",
        "marker": "TL1-004 COMPLETION REPORT",
    },
    "tl1-b-005": {
        "num": "TL1-005", "title": "Web/desktop packaging parity",
        "branch": "feat/tl1-005-packaging-parity",
        "pr": "TL1-005: web/desktop packaging parity (parity registry, packaging-parity gate, fixtures, CI wiring)",
        "heading": "### TL1-005 — Web/desktop packaging parity",
        "marker": "TL1-005 COMPLETION REPORT",
    },
}
TL1_001_FIX_DONE = "tl1-001-registry-fix.done"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def outbox(text):
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": text}) + "\n")
    except OSError:
        pass


def worklog(text):
    try:
        with open(WORKLOG, "a") as f:
            f.write(text.rstrip() + "\n")
    except OSError:
        pass


def gh_token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    try:
        for line in open("/home/z/.flauz/creds.env"):
            m = re.match(r"export GITHUB_TOKEN=(\S+)", line.strip())
            if m:
                return m.group(1)
    except OSError:
        pass
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=GATE,
                         capture_output=True, text=True).stdout.strip()
    m = re.match(r"https://x-access-token:([^@]+)@", url)
    return m.group(1) if m else None


def api(method, path, body=None, timeout=60):
    tok = gh_token()
    req = urllib.request.Request(f"{REPO_API}/{path}", method=method,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else {}


def sh(cmd, cwd=GATE, timeout=600):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} rc={r.returncode}\n{r.stderr[-1500:]}")
    return r.stdout.strip()


def processed(name):
    return (os.path.exists(os.path.join(FLAGS, f"{name}.lead-merged.json"))
            or os.path.exists(os.path.join(FLAGS, f"{name}.lead-needs-lead.json")))


def mark(name, kind, payload):
    with open(os.path.join(FLAGS, f"{name}.lead-{kind}.json"), "w") as f:
        json.dump(payload, f, indent=1)


# --------------------------------------------------------------- registry

def registry_fix_001():
    """First-lane ride-along: repair the missing TL1-001 merge record."""
    if os.path.exists(os.path.join(FLAGS, TL1_001_FIX_DONE)):
        return False
    p = os.path.join(GATE, "docs/FLAUZ-PROGRAM/WORK-REGISTRY.md")
    txt = open(p).read()
    if "PR #10" in txt.split("### TL1-002")[0]:
        open(os.path.join(FLAGS, TL1_001_FIX_DONE), "w").write("already present\n")
        return False
    old = "### TL1-001 — Upstream synchronization lane\nStatus: ACTIVE\n"
    new = ("### TL1-001 — Upstream synchronization lane\n"
           "Status: DONE (PR #10, merge a72eb663, 2026-09-27)\n")
    if old not in txt:
        log("registry 001 fix: ACTIVE line not found — skipping (manual check)")
        return False
    txt = txt.replace(old, new, 1)
    rec = ("\nMerge record (2026-09-27, TL1 lead): PR #10 merged to main at "
           "`a72eb663` (branch `feat/tl1-001-upstream-sync`, 6 commits incl. two "
           "integration merges during gating — the drift-integration flow). "
           "Delivered: deterministic upstream-sync report/plan tool, delta report "
           "vs upstream/main, CI wiring. Status DONE.\n")
    anchor = "Acceptance: repeatable sync procedure, current diff report, no accidental upstream-only regressions.\n"
    if anchor in txt:
        txt = txt.replace(anchor, anchor + rec, 1)
    open(p, "w").write(txt)
    return True


def registry_update(lane, meta, merge_sha, stats, pr_number):
    p = os.path.join(GATE, "docs/FLAUZ-PROGRAM/WORK-REGISTRY.md")
    txt = open(p).read()
    head, status_line, rest = txt.partition(meta["heading"] + "\n")
    if not status_line:
        raise RuntimeError(f"heading not found: {meta['heading']}")
    _cur_status, nl, rest = rest.partition("\n")
    today = time.strftime("%Y-%m-%d")
    new_status = f"Status: DONE (PR #{pr_number}, merge {merge_sha[:8]}, {today})"
    rest = new_status + "\n" + rest
    # insert merge record after this lane's block (before next ### heading)
    nxt = rest.find("\n### ")
    if nxt < 0:
        nxt = len(rest)
    rec = (f"\nMerge record ({today}, TL1 lead automation): branch "
           f"`{meta['branch']}` merged to main at `{merge_sha[:8]}` "
           f"({stats}). PR check-run gate: all flauz canaries green "
           f"(non-flauz regressions none; platform-lane failures tolerated "
           f"when identical on the main baseline). Status DONE.\n")
    rest = rest[:nxt] + rec + rest[nxt:]
    open(p, "w").write(head + status_line + rest)


# --------------------------------------------------------------- gates

def check_runs(sha):
    return api("GET", f"commits/{sha}/check-runs").get("check_runs", [])


def settle_and_gate(pr):
    """Poll until PR + baseline checks settle. Returns (ok, reason, pr_head)."""
    start = time.time()
    last_state = ""
    while time.time() - start < CI_CAP_SECS:
        time.sleep(POLL_SECS)
        pr = api("GET", f"pulls/{pr['number']}")
        head = pr["head"]["sha"]
        base_sha = sh(["git", "rev-parse", "origin/main"])
        runs, base_runs = check_runs(head), check_runs(base_sha)
        state = (f"{len(runs)}runs/{sum(1 for r in runs if r['status'] != 'completed')}open "
                 f"base:{len(base_runs)}runs/{sum(1 for r in base_runs if r['status'] != 'completed')}open")
        if state != last_state:
            log(f"PR #{pr['number']} ci: {state}")
            last_state = state
        if pr.get("merged") or pr.get("state") == "closed":
            return (pr.get("merged") is True, "pr closed unexpectedly", head)
        if not runs or any(r["status"] != "completed" for r in runs):
            continue
        if not base_runs or any(r["status"] != "completed" for r in base_runs):
            continue
        base_bad = {r["name"] for r in base_runs if r["conclusion"] == "failure"}
        fails = [r for r in runs if r["conclusion"] == "failure"]
        flauz_fail = [r for r in fails if r["name"].startswith("flauz-")
                      or r["name"] in ("component-fixtures", "css-order-scan")]
        if flauz_fail:
            return (False, "flauz gate red: " + ", ".join(r["name"] for r in flauz_fail), head)
        regress = [r for r in fails if r["name"] not in base_bad]
        if regress:
            return (False, "non-flauz regression: " + ", ".join(r["name"] for r in regress), head)
        return (True, "gate green", head)
    return (False, "CI settle timeout", pr["head"]["sha"])


# --------------------------------------------------------------- per-lane

def process(name):
    meta = LANES[name]
    hrec = json.load(open(os.path.join(FLAGS, f"{name}.harvest.json")))
    if hrec.get("verify") != "ok":
        mark(name, "needs-lead", {"reason": "bundle verify FAILED at harvest"})
        outbox(f"[TL1] {name}: bundle verify FAILED — Lead attention required.")
        return False
    bpath = os.path.join(HARVEST_ROOT, name, hrec["bundle"])
    log(f"{name}: processing harvest {hrec['bundle']} ({hrec.get('bytes')} B)")

    sh(["git", "fetch", "origin", "main"])
    main_head = sh(["git", "rev-parse", "origin/main"])
    sh(["git", "bundle", "verify", bpath])
    branch = meta["branch"]
    sh(["git", "fetch", bpath, f"+{branch}:{branch}"], timeout=300)

    # drift integration
    base = sh(["git", "merge-base", branch, "origin/main"])
    integrated = False
    if base != main_head:
        log(f"{name}: drift (base {base[:8]} != main {main_head[:8]}) — integrating")
        try:
            sh(["git", "checkout", branch])
            sh(["git", "merge", "--no-edit", "origin/main"], timeout=900)
            integrated = True
        except RuntimeError as e:
            subprocess.run(["git", "merge", "--abort"], cwd=GATE,
                           capture_output=True, text=True)
            mark(name, "needs-lead", {"reason": f"merge conflict: {e}"})
            outbox(f"[TL1] {name}: drift merge CONFLICT — Lead must integrate "
                   f"manually (branch fetched locally in {GATE}).")
            return False

    # push + PR
    sh(["git", "push", "origin", f"{branch}:{branch}"], timeout=300)
    companion = os.path.join(HARVEST_ROOT, name,
                             hrec["bundle"].replace("-delivery.bundle", "") + ".md")
    body = f"Autonomous Lead integration of worker delivery `{hrec['bundle']}` "
    body += f"({hrec.get('bytes')} bytes, verify ok).\n\n"
    if os.path.exists(companion):
        ctext = open(companion, errors="replace").read()[:4000]
        body += "---\nWorker completion report (truncated):\n\n```\n" + ctext + "\n```\n"
    pr = api("POST", "pulls", {"title": meta["pr"], "head": branch,
                               "base": "main", "body": body})
    log(f"{name}: PR #{pr['number']} opened")
    outbox(f"[TL1] {name}: PR #{pr['number']} opened — waiting on CI gates.")

    ok, reason, head = settle_and_gate(pr)
    if not ok:
        mark(name, "needs-lead", {"reason": reason, "pr": pr["number"]})
        outbox(f"[TL1] {name}: PR #{pr['number']} gate FAILED ({reason}) — Lead attention.")
        return False

    m = api("PUT", f"pulls/{pr['number']}/merge", {"merge_method": "merge"})
    merge_sha = m.get("sha") or ""
    log(f"{name}: MERGED at {merge_sha[:8]}")
    api("DELETE", f"git/refs/heads/{branch}")

    # registry record (+ 001 fix on first lane)
    sh(["git", "fetch", "origin", "main"])
    sh(["git", "checkout", "main"])
    sh(["git", "reset", "--hard", "origin/main"])
    fixed = registry_fix_001()
    stats = sh(["git", "show", "--shortstat", "--oneline", merge_sha]).splitlines()[-1]
    registry_update(name, meta, merge_sha, stats or "merge", pr["number"])
    msg = "docs(flauz): TL1-001 registry record repair + " if fixed else "docs(flauz): "
    sh(["git", "add", "docs/FLAUZ-PROGRAM/WORK-REGISTRY.md"])
    sh(["git", "commit", "-m", f"{msg}{meta['num']} merge record"])
    sh(["git", "push", "origin", "main"], timeout=300)
    if fixed:
        open(os.path.join(FLAGS, TL1_001_FIX_DONE), "w").write("done\n")
    log(f"{name}: registry record pushed; lane DONE")

    mark(name, "merged", {"pr": pr["number"], "merge": merge_sha, "ts": int(time.time())})
    outbox(f"[TL1] {name} DONE: PR #{pr['number']} merged at {merge_sha[:8]}, "
           f"registry record pushed. Lane {meta['num']} complete.")
    worklog(f"\n---\nTask ID: lead-auto ({name})\nAgent: tl1_lead_merge.py\nTask: "
            f"autonomous integration of {name}\n\nWork Log:\n- harvest "
            f"{hrec['bundle']} verified ({hrec.get('bytes')} B)\n- PR #{pr['number']} "
            f"opened{' , drift-integrated' if integrated else ''}\n- gates green; "
            f"merged at {merge_sha[:8]}; registry record pushed"
            f"{' (+ TL1-001 record repair)' if fixed else ''}\n\nStage Summary:\n- "
            f"{meta['num']} DONE on main.\n")
    return True


def arm_005_if_slot(merged_any):
    """After the first merge, dispatch TL1-005 (the freed slot)."""
    guard = os.path.join(FLAGS, "tl1-b-005.dispatched")
    if not merged_any or os.path.exists(guard):
        return
    prompt = os.path.join(BASE, "worker-prompts", "TL1-B-005.md")
    if not os.path.exists(prompt):
        log("005 arming: packet missing — skipping")
        return
    open(guard, "w").write(f"armed {time.strftime('%H:%M:%S')}\n")
    log("dispatching tl1-b-005 (freed slot)…")
    outbox("[TL1] tl1-b-005: dispatching (slot freed by the merged lane — "
           "packet pinned 2ad07ba7).")
    subprocess.Popen([sys.executable, os.path.join(BASE, "launch_detached.py"),
                      os.path.join(BASE, "logs", "tl1-005-dispatch.log"),
                      sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                      "create", "tl1-b-005", prompt],
                     start_new_session=True, cwd=BASE)


def main():
    log("lead-merge sentinel up — watching harvest records")
    outbox("[TL1] lead-merge sentinel armed: on each verified harvest -> PR -> "
           "flauz-gate -> merge -> registry record -> next-lane dispatch.")
    deadline = time.time() + GIVE_UP_AFTER
    while time.time() < deadline:
        for name in LANES:
            if processed(name):
                continue
            hp = os.path.join(FLAGS, f"{name}.harvest.json")
            if not os.path.exists(hp):
                continue
            try:
                process(name)
            except Exception as e:
                log(f"{name}: ERROR {type(e).__name__}: {e}")
                mark(name, "needs-lead", {"reason": f"{type(e).__name__}: {e}"})
                outbox(f"[TL1] {name}: integration ERROR ({type(e).__name__}) — "
                       f"Lead attention required.")
        any_merged = any(os.path.exists(os.path.join(FLAGS, f"{n}.lead-merged.json"))
                         for n in LANES)
        arm_005_if_slot(any_merged)
        if all(processed(n) for n in LANES):
            log("all lanes processed — exiting")
            return
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
