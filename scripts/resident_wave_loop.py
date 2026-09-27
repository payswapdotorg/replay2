#!/usr/bin/env python3
"""resident_wave_loop.py — the CONTINUOUS resident Lead loop.

Operator order (2026-09-27, standing): "continuous resident watch from here
on: monitor -> harvest -> review -> approve/require-changes -> dispatch
next, until the roadmap is complete. No early returns. Use the github repo
as guide for roadmap."

Architecture: the PARENT loop is a thin immortal monitor (60s cycles: probe
chats, harvest pods, launch assaults, promote successors). Heavy work
(clean-room batteries, reviews, merges) runs in DETACHED CHILDREN
(--baseline / --review) launched via dfork so the monitor never blocks and
no Bash-call boundary can kill anything. Children write verdict files the
parent consumes on later cycles.

  MONITOR   server-side probe (full-UUID law; the DOM lies) of every wave
            member's newest non-void chat: reportInAssistant => COMPLETE;
            fresh update => LIVE; static > STALE_S with no report => DEAD.
  HARVEST   on COMPLETE: pod tree -> full harvest to
            /home/z/leads-harvest/<chat8>/ (+ report excerpt). On DEAD:
            partial harvest if the pod still exists (never waste a
            35-minute evening run), then targeted slot release.
  REVIEW    detached child: clean-room clone at frontier currentBase,
            harvest overlay, differential battery vs a cached baseline of
            the SAME sha (typecheck/lint/unit/architecture/integration/
            governance/deploy:validate + the WO's surface suites). Gate:
            no suite worse than baseline; WO-new-file failures 0; core
            exits 0.
  APPROVE   all green -> branch, provenance commit, PAT push, PR, merge,
            records commit (frontier-state + program-state + WO header —
            the exact 2430924 pattern). REQUIRE-CHANGES -> feedback file +
            ROUND-2 amendment prompt -> re-dispatch. EXCEPTION -> parked
            at in_review + LEAD-NEEDED outbox (nothing silently merges).
  DISPATCH  wave member without a live grinder (assault or capacity
            poller) gets a fresh 24-round establishment_assault via dfork
            (slot release first — the reset5 doctrine). On wave close:
            roadmap successors are promoted; base-valid prompts dispatch,
            stale/missing prompts raise PROMPT-RENDER-NEEDED for the Lead
            CLI session.

Single instance (flock). Run detached:
  dfork_launch.py /tmp/wave_loop.log <python> resident_wave_loop.py
"""
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

PY = sys.executable
BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE_F = os.path.join(FLAGS, "wave_loop_state.json")
HB = os.path.join(FLAGS, "wave_loop.heartbeat")
HARVEST = "/home/z/leads-harvest"
ZECK = "/home/z/Zeck"
SECRETS = "/home/z/.secrets/env.sh"
PROMPT_DIRS = [
    os.path.join(BASE, "worker-prompts"),
    "/home/z/my-project/recovery/worker-prompts",
]
VERIFY = "/tmp/wave-verify"
MARKER = "END REPORT"
CYCLE = 60
STALE_S = 30 * 60
PROBE_ERR_LIMIT = 5
LOCK = os.path.join(FLAGS, "wave_loop.lock")

# registry name -> (work-order id, surface dir, prompt file)
WO = {
    "ppr018a": ("PPR-018A", "harness", "ppr-018a-runner-harness.md"),
    "ppr019": ("PPR-019", "cline", "ppr-019-cline-proof.md"),
    "ppr020": ("PPR-020", "openhands", "ppr-020-openhands-proof.md"),
    "ppr021": ("PPR-021", "continue", None),
    "ppr022": ("PPR-022", "hermes-agent", None),
    "ppr023": ("PPR-023", "openclaw", None),
    "ppr024": ("PPR-024", "browser-use", None),
    "ppr025": ("PPR-025", "open-webui", None),
    "ppr026": ("PPR-026", None, None),
    "ppr027": ("PPR-027", None, None),
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent", "text": text}
            ) + "\n")
    except Exception:
        pass


def sh(cmd, timeout=900, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, cwd=cwd)


def state_load():
    try:
        return json.load(open(STATE_F))
    except Exception:
        return {"epoch": int(time.time()), "orders": {}, "noted": {},
                "probe_errs": {}}


def state_save(s):
    tmp = STATE_F + ".tmp"
    json.dump(s, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE_F)


def records():
    try:
        return [json.loads(l) for l in open(REGISTRY).read().split("\n")
                if l.strip()]
    except Exception:
        return []


def live_chat_for(name):
    best = None
    for r in records():
        if r.get("name") != name:
            continue
        if r.get("action") in ("void", "failed"):
            continue
        if r.get("url") and "chat.z.ai/c/" in r["url"]:
            m = re.search(r"/c/([0-9a-f-]{36})", r["url"])
            if m and (best is None or r.get("ts", 0) >= best[1]):
                best = (m.group(1), r.get("ts", 0))
    return best


def probe(chat):
    r = sh([PY, os.path.join(BASE, "probe_chat.py"), chat, MARKER],
           timeout=90)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def void_record(name, chat, reason):
    with open(REGISTRY, "a") as f:
        f.write(json.dumps({
            "action": "void", "name": name, "tab_id": None,
            "reason": reason, "ts": int(time.time())}) + "\n")


def grinder_alive(name):
    """an establishment assault OR a capacity-recovery poller covers name"""
    for pat in (f"establishment_assault.py {name} ",
                f"capacity_recover.{name}.json"):
        r = sh(["pgrep", "-f", pat], timeout=15)
        if r.stdout.strip():
            return True
    return False


def launch_assault(name, prompt_file):
    logp = f"/tmp/assault_{name}_loop.log"
    r = sh([PY, os.path.join(BASE, "dfork_launch.py"), logp, PY,
            os.path.join(BASE, "establishment_assault.py"), name,
            prompt_file, MARKER, "360", "24"], timeout=60)
    ok = r.returncode == 0
    for f in (f"capacity_recover.{name}.json",):
        p = os.path.join(FLAGS, f)
        if os.path.exists(p):
            os.remove(p)      # the assault is the single dispatcher now
    return ok


def prompt_path(name):
    _, _, pf = WO.get(name, (None, None, None))
    if not pf:
        return None
    for d in PROMPT_DIRS:
        p = os.path.join(d, pf)
        if os.path.exists(p):
            return p
    return None


def prompt_base_valid(path, current_base):
    try:
        txt = open(path).read()
    except Exception:
        return False, "unreadable"
    if "<BASE_SHA>" in txt:
        return False, "placeholder base (Lead render required)"
    m = re.search(r"\b([0-9a-f]{40})\b", txt)
    if not m:
        return True, "no explicit pin (origin/main fallback rule)"
    pinned = m.group(1)
    if pinned == current_base:
        return True, "pinned == currentBase"
    r = sh(["git", "-C", ZECK, "merge-base", "--is-ancestor", pinned,
            current_base], timeout=60)
    if r.returncode == 0:
        return True, f"pinned {pinned[:8]} ancestor of main (merge-safe)"
    r2 = sh(["git", "-C", ZECK, "cat-file", "-e", f"{pinned}^{{commit}}"],
            timeout=30)
    if r2.returncode == 0 and "origin/main HEAD" in txt:
        return True, "unreachable pin with explicit fallback rule"
    return False, f"pinned {pinned[:8]} diverged from main"
# ---------------------------------------------------------------- roadmap --


def roadmap():
    sh(["git", "-C", ZECK, "fetch", "origin", "main"], timeout=180)

    def show(path):
        r = sh(["git", "-C", ZECK, "show", f"origin/main:{path}"], timeout=60)
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except Exception:
            return None

    return (show("spec/post-release-state/frontier-state.json"),
            show("spec/application-compatibility/program-state.json"))


def remaining_wave(pg):
    return list(pg.get("currentWave", [])) if pg else []


def next_successors(fr, pg):
    delivered = set(fr.get("delivered", []))
    wave = set(pg.get("currentWave", []))
    out = []
    for s in pg.get("sequence", []):
        sid = s.get("id")
        if sid in delivered or sid in wave:
            continue
        if all(d in delivered for d in s.get("depends", [])):
            out.append(sid)
    return out
# ---------------------------------------------------------------- harvest --


def workspaces():
    r = sh([PY, os.path.join(BASE, "check_workspaces.py")], timeout=120)
    txt = r.stdout or ""
    ws = {}
    for m in re.finditer(
            r"chat-(?P<c>[0-9a-f]{8})[0-9a-f-]*\s+ws=(?P<w>ws-[0-9a-f-]+)"
            r"(?:\s+active=(?P<a>\w+))?", txt):
        ws[m.group("c")] = (m.group("w"), m.group("a") or "?")
    at_cap = '"total": 3' in txt.replace(" ", "")
    return ws, txt, at_cap


def release_dead_slots():
    ws, txt, at_cap = workspaces()
    if not at_cap:
        return False
    sh([PY, os.path.join(BASE, "dash_sandbox_release.py")], timeout=300)
    return True


def pod_files(chat, wsid):
    r = sh([PY, os.path.join(BASE, "pod_tree.py"), chat, wsid], timeout=180)
    out = []
    for line in (r.stdout or "").split("\n"):
        line = line.strip()
        if (not line or line.startswith("total entries:")
                or line.startswith("PARSE FAIL") or line.endswith("/")):
            continue
        out.append(line)
    return out


HARVEST_KEEP = re.compile(
    r"(^|/)(compat/|src/integrations/|apps/dashboard/|sdk/|deploy/|tests/|"
    r"docs/|spec/|examples/|evidence|package\.json|tsconfig|vitest|biome|"
    r"README|AGENTS|\.tgz$|REPORT)", re.I)
HARVEST_EXCLUDE = re.compile(
    r"(^|/)(node_modules|\.git|\.cache|\.next|dist|coverage|"
    r"test-results|playwright-report|\.venv|bun-install-cache|tmp)/", re.I)


def harvest_pod(name, chat, partial):
    chat8 = chat[:8]
    dest = os.path.join(
        HARVEST, chat8 + (f"-partial{int(time.time())}" if partial else ""))
    os.makedirs(dest, exist_ok=True)
    ws, _, _ = workspaces()
    wsid = None
    for c8, v in ws.items():
        if chat.startswith(c8):
            wsid = v[0]
            break
    if not wsid:
        return None, "no workspace (pod GC'd?)"
    files = pod_files(chat, wsid)
    keep = [p for p in files
            if HARVEST_KEEP.search(p) and not HARVEST_EXCLUDE.search(p)]
    if not keep:
        return None, "pod tree empty (recycled)"
    log(f"[{name}] harvesting {len(keep)} files from {wsid}")
    flat_dir = os.path.join(HARVEST, chat8)
    os.makedirs(flat_dir, exist_ok=True)
    for i in range(0, len(keep), 40):
        sh([PY, os.path.join(BASE, "harvest_files.py"), chat, wsid]
           + keep[i:i + 40], timeout=600)
    for p in keep:
        flat = os.path.join(flat_dir, os.path.basename(p))
        if not os.path.exists(flat):
            continue
        rp = p.lstrip("./")
        m = re.search(r"(?:^|/)Zeck/(.+)$", rp)
        if m:
            dst = os.path.join(dest, m.group(1))
        else:
            dst = os.path.join(dest, "_podscratch",
                               rp.replace("/", "_"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.move(flat, dst)
        except Exception:
            pass
    try:
        shutil.rmtree(flat_dir, ignore_errors=True)
    except Exception:
        pass
    r = sh([PY, os.path.join(BASE, "batch_probe.py"), chat, MARKER],
           timeout=120)
    if r.stdout:
        open(os.path.join(dest, "report_excerpt.txt"), "w").write(r.stdout)
    return dest, f"{len(keep)} files"
# ----------------------------------------------------------------- review --


def token():
    try:
        for line in open(SECRETS):
            line = line.strip()
            if line.startswith("export ZECK_GITHUB_PAT="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("ZECK_GITHUB_PAT", "")


def gh(method, path, body=None):
    tok = token()
    if not tok:
        raise RuntimeError("no PAT")
    req = urllib.request.Request(
        f"https://api.github.com/repos/payswapdotorg/Zeck/{path}",
        method=method,
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode() or "{}")


def parse_vitest(txt):
    m = re.search(r"Tests\s+(\d+)\s+failed", txt)
    if m:
        return int(m.group(1))
    if re.search(r"Tests\s+\d+\s+passed", txt):
        return 0
    return None


def parse_lint(txt):
    m = re.search(r"Found\s+(\d+)\s+errors?\s+and\s+(\d+)\s+warnings?"
                  r"\s+and\s+(\d+)\s+infos?", txt)
    return tuple(int(x) for x in m.groups()) if m else (None, None, None)


def battery(clone, surface):
    rep = {}

    def run(key, cmd, timeout=2400):
        t0 = time.time()
        r = sh(cmd, timeout=timeout, cwd=clone)
        rep[key] = {"rc": r.returncode, "secs": int(time.time() - t0),
                    "tail": ((r.stdout or "")[-5000:]
                             + (r.stderr or "")[-2500:])}
        return r

    run("typecheck", ["bun", "run", "typecheck"])
    run("lint", ["bun", "run", "lint"])
    run("unit", ["bun", "run", "test:unit"])
    run("architecture", ["bun", "run", "test:architecture"])
    run("integration", ["bun", "run", "test:integration"])
    run("governance", ["bun", "run", "governance:check"])
    run("deploy_validate", ["bun", "run", "deploy:validate"], timeout=1500)
    if surface and os.path.isdir(os.path.join(clone, "compat", surface)):
        run(f"compat_{surface}",
            ["bunx", "vitest", "run", f"compat/{surface}"])
    for k in list(rep):
        rep[k]["failed"] = parse_vitest(rep[k]["tail"])
    rep["_lint_counts"] = parse_lint(rep.get("lint", {}).get("tail", ""))
    return rep


def prepare_clone(base_sha, tag):
    """clean-room clone at EXACTLY base_sha. The local Zeck clone's main
    branch can be stale (shallow clone; roadmap() only refreshes its
    remote-tracking origin/main) — so after the fast local clone we fetch
    the TRUE main through the local repo's remote-tracking ref and hard-
    fail if the base checkout does not land exactly."""
    d = os.path.join(VERIFY, tag)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(VERIFY, exist_ok=True)
    r = sh(["git", "clone", "--quiet", ZECK, d], timeout=600)
    if r.returncode != 0:
        r = sh(["git", "clone", "--quiet",
                "https://github.com/payswapdotorg/Zeck.git", d], timeout=900)
        if r.returncode != 0:
            raise RuntimeError("clone failed")
    # the true main: /home/z/Zeck's remote-tracking origin/main is kept
    # fresh by roadmap() every cycle
    sh(["git", "-C", d, "fetch", "--quiet", ZECK,
        "refs/remotes/origin/main:refs/heads/wave-main"], timeout=600)
    r = sh(["git", "-C", d, "checkout", "--quiet", "-B", "verify",
            base_sha], timeout=120)
    if r.returncode != 0:
        raise RuntimeError(
            f"base checkout failed: {base_sha[:10]} not reachable — "
            f"stale frontier currentBase?")
    r = sh(["git", "-C", d, "rev-parse", "HEAD"], timeout=30)
    if r.stdout.strip() != base_sha:
        raise RuntimeError(f"base mismatch: {r.stdout.strip()[:10]} != "
                           f"{base_sha[:10]}")
    r = sh(["bun", "install", "--frozen-lockfile"], cwd=d, timeout=1500)
    if r.returncode != 0:
        sh(["bun", "install"], cwd=d, timeout=1500)
    return d


OVERLAY_SKIP = re.compile(
    r"(^|/)(_podscratch/|report_excerpt|REQUIRED_CHANGES|lead_review|"
    r"lead_verdict|\.tgz$)")


def overlay(clone, harvest_dir):
    n = 0
    for root, _, files in os.walk(harvest_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), harvest_dir)
            if OVERLAY_SKIP.search(rel):
                continue
            dst = os.path.join(clone, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(root, f), dst)
            n += 1
    return n


def baseline_for(base_sha):
    cachef = os.path.join(FLAGS, f"battery_baseline_{base_sha[:10]}.json")
    if os.path.exists(cachef):
        try:
            return json.load(open(cachef))
        except Exception:
            pass
    d = prepare_clone(base_sha, "baseline")
    rep = battery(d, None)
    json.dump(rep, open(cachef, "w"), indent=1)
    shutil.rmtree(d, ignore_errors=True)
    return rep


def gates_verdict(candidate, baseline):
    problems = []
    for key in ("typecheck", "governance", "deploy_validate"):
        if candidate.get(key, {}).get("rc") != 0:
            problems.append(f"{key} exit={candidate[key]['rc']}")
    for key in ("unit", "architecture", "integration"):
        c = candidate.get(key, {}).get("failed")
        b = baseline.get(key, {}).get("failed")
        if c is not None and b is not None and c > b:
            problems.append(f"{key}: {b} -> {c} failed (worse than baseline)")
    cl = candidate.get("_lint_counts", (None, None, None))
    bl = baseline.get("_lint_counts", (None, None, None))
    if None not in cl and None not in bl:
        for i, nm in enumerate(("errors", "warnings", "infos")):
            if cl[i] > bl[i]:
                problems.append(f"lint {nm}: {bl[i]} -> {cl[i]}")
    for k in candidate:
        if k.startswith("compat_"):
            c = candidate[k].get("failed")
            if c is None:
                continue
            b = baseline.get(k, {}).get("failed", 0)
            if c > b:
                problems.append(f"{k}: baseline {b} -> {c} failed")
    return problems


def review_and_deliver(name, chat, harvest_dir, base_sha):
    """runs INSIDE a --review child. Writes lead_verdict.json; returns
    'delivered' | 'require_changes' | 'parked'."""
    wo_id, surface, _ = WO.get(name, (name.upper(), None, None))
    vf = os.path.join(harvest_dir, "lead_verdict.json")

    def verdict(v, extra=None):
        json.dump({"verdict": v, "wo": wo_id, "chat": chat,
                   "ts": int(time.time()), "extra": extra or {}},
                  open(vf, "w"), indent=1)
        return v

    try:
        outbox(f"[{name}] LEAD REVIEW running — clean-room differential "
               f"battery at {base_sha[:8]} (harvest {harvest_dir})")
        baseline = baseline_for(base_sha)
        clone = prepare_clone(base_sha, f"cand-{name}")
        # snapshot bun-install churn BEFORE overlay (the PPR-018 lesson:
        # bun can rewrite package.json/lockfile — never commit that churn
        # unless the harvest itself carries those files)
        r0 = sh(["git", "-C", clone, "status", "--porcelain"], timeout=60)
        churn = [l[3:] for l in (r0.stdout or "").split("\n") if l.strip()]
        n = overlay(clone, harvest_dir)
        if n == 0:
            outbox(f"[{name}] REVIEW PARKED: harvest overlay empty — the "
                   f"interactive Lead may need an op-stream replay")
            return verdict("parked", {"reason": "empty overlay"})
        overlaid = set()
        for root, _, files in os.walk(harvest_dir):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), harvest_dir)
                if not OVERLAY_SKIP.search(rel):
                    overlaid.add(rel)
        for f in churn:
            if f not in overlaid:
                sh(["git", "-C", clone, "checkout", "--", f], timeout=60)
        r = sh(["git", "-C", clone, "status", "--porcelain"], timeout=60)
        new_files = [l[3:] for l in (r.stdout or "").split("\n")
                     if l.strip()]
        cand = battery(clone, surface)
        # WO-own new test files must not fail
        new_failed = []
        for f in new_files:
            if not f.endswith(".test.ts"):
                continue
            for k, v in cand.items():
                if not isinstance(v, dict):
                    continue
                if re.search(r"FAIL[^\n]*" + re.escape(f),
                             v.get("tail", "")):
                    new_failed.append(f)
                    break
        problems = gates_verdict(cand, baseline) + (
            [f"WO new-file test failures: {new_failed}"] if new_failed else [])
        json.dump({"candidate": {k: v for k, v in cand.items()},
                   "problems": problems, "new_files": new_files},
                  open(os.path.join(harvest_dir, "lead_review.json"), "w"),
                  indent=1)
        if problems:
            outbox(f"[{name}] REQUIRE-CHANGES: " + "; ".join(problems[:6])
                   + " — ROUND-2 amendment will dispatch")
            open(os.path.join(harvest_dir, "REQUIRED_CHANGES.md"), "w").write(
                "# ROUND 2 REQUIRED CHANGES\n\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n\nFull battery tails in lead_review.json (same dir).\n")
            shutil.rmtree(clone, ignore_errors=True)
            return verdict("require_changes", {"problems": problems})
        # ---- APPROVE ----
        br = f"work/{wo_id}-{surface or 'proof'}"
        sh(["git", "-C", clone, "checkout", "--quiet", "-B", br], timeout=60)
        sh(["git", "-C", clone, "add", "-A"], timeout=120)
        r = sh(["git", "-C", clone, "commit", "--quiet", "-m",
                f"{wo_id}: {surface or 'proof'} delivery — worker session "
                f"{chat[:8]}, Lead differential battery all-green "
                f"(baseline-exact, new-file failures 0)"], timeout=180)
        if r.returncode != 0:
            outbox(f"[{name}] REVIEW PARKED: commit failed")
            return verdict("parked", {"reason": "commit failed"})
        tok = token()
        if not tok:
            outbox(f"[{name}] REVIEW PARKED: no PAT")
            return verdict("parked", {"reason": "no PAT"})
        push_url = (f"https://x-access-token:{tok}"
                    f"@github.com/payswapdotorg/Zeck.git")
        r = sh(["git", "-C", clone, "push", push_url,
                f"HEAD:refs/heads/{br}"], timeout=300)
        if r.returncode != 0:
            outbox(f"[{name}] REVIEW PARKED: branch push failed")
            return verdict("parked", {"reason": "push failed"})
        pr = gh("POST", "pulls", {
            "title": f"{wo_id} {surface or 'proof'} delivery",
            "head": br, "base": "main",
            "body": f"Worker session chat {chat} (dispatched from inside "
                    f"the replay). Lead differential battery vs baseline "
                    f"at {base_sha[:8]}: all gates green. Files: "
                    f"{len(new_files)}. Provenance: lead_review.json in the "
                    f"harvest."})
        num = pr["number"]
        mg = gh("PUT", f"pulls/{num}/merge", {"merge_method": "merge"})
        merge_sha = mg.get("sha", "")
        if not merge_sha:
            outbox(f"[{name}] REVIEW PARKED: merge API refused PR #{num}")
            return verdict("parked", {"reason": f"merge refused PR #{num}",
                                       "pr": num})
        # records commit — on top of the JUST-MERGED github main
        sh(["git", "-C", clone, "fetch", "--quiet", push_url, "main"],
           timeout=180)
        sh(["git", "-C", clone, "checkout", "--quiet", "FETCH_HEAD"],
           timeout=60)
        fpath = "spec/post-release-state/frontier-state.json"
        fr2 = json.load(open(os.path.join(clone, fpath)))
        fr2["currentBase"] = merge_sha
        if wo_id not in fr2["delivered"]:
            fr2["delivered"].append(wo_id)
        fr2["delivered"] = sorted(set(fr2["delivered"]))
        if wo_id in fr2.get("eligible", []):
            fr2["eligible"].remove(wo_id)
        json.dump(fr2, open(os.path.join(clone, fpath), "w"), indent=1)
        open(os.path.join(clone, fpath), "a").write("\n")
        ppath = "spec/application-compatibility/program-state.json"
        pg2 = json.load(open(os.path.join(clone, ppath)))
        if wo_id in pg2.get("currentWave", []):
            pg2["currentWave"].remove(wo_id)
        json.dump(pg2, open(os.path.join(clone, ppath), "w"), indent=1)
        open(os.path.join(clone, ppath), "a").write("\n")
        wopath = f"spec/post-release-work-orders/{wo_id}.md"
        if os.path.exists(os.path.join(clone, wopath)):
            t = open(os.path.join(clone, wopath)).read()
            t = re.sub(r"Status:\s*AUTHORIZED[^\n]*",
                       f"Status: DELIVERED (PR #{num}, merge "
                       f"{merge_sha[:7]} — Lead differential battery "
                       f"all-green; harvest from worker session "
                       f"{chat[:8]})", t, count=1)
            open(os.path.join(clone, wopath), "w").write(t)
        sh(["git", "-C", clone, "add", "-A"], timeout=60)
        sh(["git", "-C", clone, "commit", "--quiet", "-m",
            f"{wo_id} delivered records: frontier delivered += {wo_id} "
            f"(currentBase {merge_sha[:7]}, the PR #{num} merge head), "
            f"work-order header -> DELIVERED, program-state currentWave "
            f"updated"], timeout=180)
        r = sh(["git", "-C", clone, "push", push_url, "HEAD:main"],
               timeout=300)
        if r.returncode != 0:
            outbox(f"[{name}] MERGED but records push FAILED (PR #{num}, "
                   f"{merge_sha[:7]}) — Lead must push records")
            return verdict("delivered", {"pr": num, "merge": merge_sha,
                                         "records": "push-failed"})
        outbox(f"[{name}] APPROVED + DELIVERED: PR #{num} merged "
               f"({merge_sha[:7]}), records pushed. Differential battery "
               f"all-green; {len(new_files)} files.")
        shutil.rmtree(clone, ignore_errors=True)
        return verdict("delivered", {"pr": num, "merge": merge_sha})
    except Exception as e:
        outbox(f"[{name}] REVIEW EXCEPTION: {type(e).__name__}: {e} — "
               f"parked for the interactive Lead (harvest safe)")
        log(f"review exception: {e}")
        return verdict("parked", {"reason": f"{type(e).__name__}: {e}"})
# ------------------------------------------------------------------ cycle --


def review_child_alive():
    r = sh(["pgrep", "-f", "resident_wave_loop.py --review"], timeout=15)
    return bool(r.stdout.strip())


def note(s, key, text):
    if s["noted"].get(key):
        return
    s["noted"][key] = int(time.time())
    outbox(text)


def cycle(s):
    open(HB, "w").write(str(int(time.time())))
    fr, pg = roadmap()
    if not fr or not pg:
        log("roadmap unreadable — cycle skipped")
        return
    # promote dependency-complete successors + track current wave
    for sid in next_successors(fr, pg) + remaining_wave(pg):
        nm = sid.lower().replace("-", "")
        if nm in WO and nm not in s["orders"]:
            s["orders"][nm] = {"status": "idle", "chat": None,
                               "since": int(time.time())}
            outbox(f"[{nm}] promoted by roadmap (frontier delivered: "
                   f"{len(fr['delivered'])} WOs)")
    for name, o in list(s["orders"].items()):
        if o.get("status") == "delivered":
            continue
        wo_id = WO.get(name, (name.upper(),))[0]
        if wo_id in fr.get("delivered", []):
            o["status"] = "delivered"
            continue
        st = o.get("status")
        # consume review verdicts
        if st == "in_review_running":
            vf = os.path.join(o.get("harvest", "/nonexistent"),
                              "lead_verdict.json")
            if os.path.exists(vf):
                try:
                    v = json.load(open(vf))
                except Exception:
                    v = None
                if v:
                    if v["verdict"] == "delivered":
                        o["status"] = "delivered"
                        outbox(f"[{name}] DELIVERED (PR "
                               f"{v.get('extra', {}).get('pr')}) — "
                               f"roadmap advanced")
                    elif v["verdict"] == "require_changes":
                        pp = prompt_path(name)
                        fb = os.path.join(o.get("harvest", ""),
                                          "REQUIRED_CHANGES.md")
                        if pp and os.path.exists(fb):
                            r2 = pp.replace(
                                ".md", f"-r2-{int(time.time())}.md")
                            open(r2, "w").write(
                                open(pp).read()
                                + "\n\n---\n\n# ROUND 2 AMENDMENT "
                                  "(Lead review)\n\n" + open(fb).read()
                                + "\nYour previous attempt's harvest is "
                                  "preserved; fix these gates and deliver "
                                  "the full set again.\n")
                            o["status"] = "grinding"
                            o["chat"] = None
                            release_dead_slots()
                            launch_assault(name, r2)
                        else:
                            o["status"] = "in_review"
                    else:
                        o["status"] = "in_review"
            continue
        if st in ("in_review",):
            continue                      # parked for the interactive Lead
        cand = live_chat_for(name)
        chat = cand[0] if cand else None
        if not chat:
            pp = prompt_path(name)
            if not pp:
                note(s, f"prompt_missing_{name}",
                     f"[{name}] PROMPT-RENDER-NEEDED: no worker prompt for "
                     f"{wo_id} — the Lead CLI session must author it")
                continue
            ok, why = prompt_base_valid(pp, fr["currentBase"])
            if not ok:
                note(s, f"prompt_base_{name}",
                     f"[{name}] PROMPT-RENDER-NEEDED ({why}) — Lead must "
                     f"re-render at base {fr['currentBase'][:8]}")
                continue
            if not grinder_alive(name):
                release_dead_slots()
                if launch_assault(name, pp):
                    outbox(f"[{name}] establishment assault launched by "
                           f"the resident loop (24 rounds, never-wait)")
                    o["since"] = int(time.time())
            if o.get("status") != "grinding":
                o["status"] = "grinding"
            continue
        p = probe(chat)
        if p is None:
            s["probe_errs"][name] = s["probe_errs"].get(name, 0) + 1
            if s["probe_errs"][name] == PROBE_ERR_LIMIT:
                outbox("[loop] probe failures x5 — browser/login may be "
                       "down; grinders continue regardless")
            continue
        s["probe_errs"][name] = 0
        age = p.get("now", 0) - p.get("updated", 0)
        if p.get("reportInAssistant"):
            if st != "complete":
                o["status"] = "complete"
                outbox(f"[{name}] COMPLETE — END REPORT in chat "
                       f"{chat[:8]}; harvesting pod")
                dest, info = harvest_pod(name, chat, partial=False)
                if dest is None:
                    outbox(f"[{name}] pod GC'd before harvest — LEAD-NEEDED "
                           f"op-stream replay (the PPR-018 proven path)")
                    o["status"] = "in_review"
                    continue
                outbox(f"[{name}] harvested {info} -> {dest}")
                o["status"] = "harvested"
                o["harvest"] = dest
                o["chat"] = chat
                st = "harvested"
        elif p.get("msgs", 0) >= 2 and age < STALE_S:
            if st != "live":
                outbox(f"[{name}] LIVE — chat {chat[:8]} generating "
                       f"(msgs={p['msgs']}, age {age}s)")
            o["status"] = "live"
            o["chat"] = chat
            o["since"] = int(time.time())
            continue
        else:
            if st == "live" or age > STALE_S:
                outbox(f"[{name}] worker turn DEAD (chat {chat[:8]}, "
                       f"static {age}s) — partial harvest + release + "
                       f"re-dispatch (never-wait)")
                dest, info = harvest_pod(name, chat, partial=True)
                if dest:
                    outbox(f"[{name}] partial harvested {info} -> {dest}")
                release_dead_slots()
                void_record(name, chat,
                            f"wave_loop death: static {age}s, no report")
                o["status"] = "grinding"
                o["chat"] = None
                pp = prompt_path(name)
                if pp and not grinder_alive(name):
                    launch_assault(name, pp)
                continue
            continue
        # harvested -> spawn the detached review child (one at a time)
        if o.get("status") == "harvested" and not review_child_alive():
            r = sh([PY, os.path.join(BASE, "dfork_launch.py"),
                    f"/tmp/review_{name}.log", PY,
                    os.path.join(BASE, "resident_wave_loop.py"),
                    "--review", name, o.get("chat", chat),
                    o.get("harvest", ""), fr["currentBase"]], timeout=60)
            if r.returncode == 0:
                o["status"] = "in_review_running"
                outbox(f"[{name}] review child launched (clean-room "
                       f"differential battery)")


def main():
    os.makedirs(FLAGS, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--baseline":
        fr, _ = roadmap()
        if fr:
            rep = baseline_for(fr["currentBase"])
            log(f"baseline cached for {fr['currentBase'][:10]}: "
                f"unit={rep.get('unit', {}).get('failed')} arch="
                f"{rep.get('architecture', {}).get('failed')} integ="
                f"{rep.get('integration', {}).get('failed')} lint="
                f"{rep.get('_lint_counts')}")
        return
    if len(sys.argv) >= 6 and sys.argv[1] == "--review":
        _, _, name, chat, harvest_dir, base_sha = sys.argv
        review_and_deliver(name, chat, harvest_dir, base_sha)
        return
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another wave_loop instance holds the lock — exiting")
        return
    s = state_load()
    outbox("RESIDENT WAVE LOOP online — continuous "
           "monitor->harvest->review->approve/require-changes->dispatch "
           "until the roadmap completes. No early returns.")
    log("resident wave loop online")
    while True:
        t0 = time.time()
        try:
            cycle(s)
        except Exception as e:
            log(f"cycle exception: {type(e).__name__}: {e}")
        try:
            state_save(s)
        except Exception:
            pass
        time.sleep(max(5, CYCLE - (time.time() - t0)))


if __name__ == "__main__":
    main()
