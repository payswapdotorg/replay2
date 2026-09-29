#!/usr/bin/env python3
"""wfx2_dispatch_child.py <laneset> — the WebFlix 2.0 transition ACTOR.

Fired by wfx2_transition.py (the monitor) via dfork when a transition
condition is met. Heavy work runs HERE so the monitor never blocks
(the resident_wave_loop architecture law).

laneset:
  wave2       — the dependency gates landed (WFX2-S bible + WFX2-B boot on
                main, whoever merged them): claim WFX2-A + WFX2-U (staked
                in the ledger 02:45Z) and dispatch both under ali10.
  escalation  — the 04:15Z escalation fired (gates NOT landed, lead-STEEL
                inactive): claim the lapsed critical-path lanes WFX2-B +
                WFX2-S per the 4h-binding law + the operator standing order
                and re-dispatch them (README-contract packets — no bible
                exists on that path).

Every step is verified + recorded; verdict lands in
flags/wfx2_transition_verdict.<laneset>.json for the monitor/lead sessions.

Operator standing order (2026-09-29 02:34Z): "continuous resident watch
from here on: monitor → harvest → review → approve/require-changes →
dispatch next, until the roadmap is complete. No early returns."
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path("/home/z/replay2/scripts")
REPO = Path("/home/z/webflix-2.0")
FLAGS = SCRIPTS / "flags"
PROMPTS = SCRIPTS / "worker-prompts"
PY = "/home/z/.venv/bin/python3"
MISSION_STATE = Path("/home/z/replay2/data/mission-state.json")
VERDICT = FLAGS / "wfx2_transition_verdict.{laneset}.json"
WALL_GUARD_S = 45 * 60

# ---------------------------------------------------------------- lanes
WAVE2_LANES = [
    {
        "name": "wfx2a", "lane_id": "WFX2-A", "laneset": "wave2",
        "title": "Account surfaces — History / Playlists CRUD / Liked videos / "
                 "Watch later / notifications bell menu",
        "branch": "wfx2/account", "marker": "WFX2-A COMPLETION REPORT",
        "bundle": "wfx2-account.bundle",
        "specs_keywords": ["history", "playlist", "liked", "watch-later",
                           "watch later", "notification", "account", "you-area",
                           "you area", "saved", "your-videos"],
        "deliver": (
            "The complete account surfaces, each with its COMPLETE backend\n"
            "(Prisma models + API routes + client hooks/components + tests —\n"
            "no feature is UI-only):\n"
            "- History — the watched-videos history feed (real view records,\n"
            "  remove/clear, resume points surfacing where the watch surface\n"
            "  consumes them)\n"
            "- Playlists — full CRUD (create/rename/delete/set-visibility),\n"
            "  add/remove videos, reorder, the playlist picker on save actions\n"
            "- Liked videos — the like-truth list (real like states from the\n"
            "  watch surface's engagement seam)\n"
            "- Watch later — the save-truth list (add/remove, play-through)\n"
            "- Notifications bell menu — real notification events persisted\n"
            "  server-side, unread/read states, per-channel preference\n"
            "  granularity, mark-all-read\n"
            "All state is DATABASE truth (no mock data in code paths); counts\n"
            "and empty states render honestly."
        ),
        "owns": (
            "- The account route areas (history / playlists / liked /\n"
            "  watch-later / notifications surfaces) under `src/app/**` following\n"
            "  the boot scaffold's routing conventions\n"
            "- Their components, hooks and API routes (`src/app/api/**` per the\n"
            "  scaffold's route pattern)\n"
            "- `evidence/wfx2-a/**` (your lane evidence, yours entirely)\n"
            "- Colocated lane tests inside the paths you own"
        ),
    },
    {
        "name": "wfx2u", "lane_id": "WFX2-U", "laneset": "wave2",
        "title": "Upload + Creator Studio — upload flow (+ AI helpers) + the "
                 "full studio surfaces",
        "branch": "wfx2/upload-studio", "marker": "WFX2-U COMPLETION REPORT",
        "bundle": "wfx2-upload-studio.bundle",
        "specs_keywords": ["upload", "studio", "creator", "analytics",
                           "revenue", "moderation", "experiment", "thumbnail",
                           "ai", "content", "dashboard"],
        "deliver": (
            "The complete creator surfaces, each with its COMPLETE backend\n"
            "(Prisma models + API routes + client hooks/components + tests —\n"
            "no feature is UI-only):\n"
            "- Upload flow — video + thumbnail upload (+ the AI generator\n"
            "  helpers where the spec provides them), title/description\n"
            "  (+ AI assists), tags, visibility, member-only toggle; upload\n"
            "  progress + durable draft state\n"
            "- Creator Studio — Dashboard, Content (the video list with\n"
            "  real states: drafts/scheduled/published), Experiments\n"
            "  (A/B thumbnail tests — real experiment records + measured\n"
            "  outcomes from real impressions), Analytics (honest analytics:\n"
            "  only real recorded events; typed absence states otherwise),\n"
            "  Revenue (from real monetization truth where the spec defines\n"
            "  it; typed absences otherwise), Comments (moderation:\n"
            "  hold/review/pin/reply on the SAME comments truth the watch\n"
            "  surface renders), Moderation (the moderation queue + actions)\n"
            "All state is DATABASE truth; NO fabricated metrics — the honest-\n"
            "analytics law: every panel either proves its number from real\n"
            "recorded events or renders the typed absence state."
        ),
        "owns": (
            "- The upload route area + the studio route areas (`/upload`,\n"
            "  `/studio/**` — Dashboard/Content/Experiments/Analytics/Revenue/\n"
            "  Comments/Moderation) under `src/app/**`\n"
            "- Their components, hooks and API routes\n"
            "- `evidence/wfx2-u/**` (your lane evidence, yours entirely)\n"
            "- Colocated lane tests inside the paths you own"
        ),
    },
]

ESCALATION_LANES = [
    {
        "name": "wfx2b", "lane_id": "WFX2-B", "laneset": "escalation",
        "title": "Boot shell — scaffold + full Prisma schema + ZTube app "
                 "shell + home feed + seed + gates",
        "branch": "wfx2/boot-shell", "marker": "WFX2-B COMPLETION REPORT",
        "bundle": "wfx2-boot-shell.bundle",
        "specs_keywords": [],
        "deliver": (
            "The repo BOOT (everything later lanes build on):\n"
            "- Next.js 16 App Router + TypeScript strict scaffold (single app\n"
            "  in `src/`), Tailwind CSS 4 + shadcn/ui (New York) + lucide-react,\n"
            "  Prisma ORM + SQLite (db file in `db/`, schema in `prisma/`),\n"
            "  bun scripts (install/lint/typecheck/test/dev)\n"
            "- THE FULL Prisma schema — forward-complete for the whole\n"
            "  interface contract (users, channels, videos, comments, likes,\n"
            "  subscriptions, playlists, watch history, notifications,\n"
            "  live/premieres, memberships, uploads/studio state, analytics\n"
            "  events, experiments) — later lanes extend ADDITIVELY\n"
            "- The ZTube app shell: collapsible sidebar, topbar (search,\n"
            "  voice search, upload, trending, notifications bell, theme\n"
            "  toggle, account menu), category chips\n"
            "- The home feed: trending hero #1, Trending now rail, Continue\n"
            "  watching, Because-you-watched, Shorts shelf, Recommended grid,\n"
            "  infinite scroll, hover previews — fed by REAL database queries\n"
            "- `prisma/seed.ts` — rich honest seed data (channels, videos,\n"
            "  comments, engagement) so every surface renders truth\n"
            "- The GATES: lint/typecheck/test scripts wired and green at base\n"
            "All state is DATABASE truth; NO mock data in code paths."
        ),
        "owns": (
            "- The entire scaffold (`package.json`, `src/**`, `prisma/**`,\n"
            "  `db/`, config files) — this lane IS the boot\n"
            "- `evidence/wfx2-b/**` (your lane evidence)"
        ),
    },
    {
        "name": "wfx2s", "lane_id": "WFX2-S", "laneset": "escalation",
        "title": "The YouTube bible — docs/specs/*.md per-feature complete "
                 "functionality contract",
        "branch": "wfx2/youtube-bible", "marker": "WFX2-S COMPLETION REPORT",
        "bundle": "wfx2-youtube-bible.bundle",
        "specs_keywords": [],
        "deliver": (
            "THE FUNCTIONALITY BIBLE (the contract every later lane implements\n"
            "to). One spec file per interface-contract feature in\n"
            "`docs/specs/`, each COMPLETE:\n"
            "- feature inventory: 1 app shell, 2 home feed, 3 shorts,\n"
            "  4 trending, 5 subscriptions, 6 you-area (history/playlists/\n"
            "  liked/watch later), 7 watch page (player/engagement/comments/\n"
            "  related), 8 upload, 9 creator studio, 10 channel pages,\n"
            "  11 search, 12 explore, 13 live, 14 notifications,\n"
            "  15 memberships, 16 settings/premium/help\n"
            "Each spec carries: BEHAVIOR (the complete youtube.com behavior,\n"
            "  edge cases + states), DATA MODEL (Prisma models + fields +\n"
            "  relations), API (routes + methods + payloads + errors), and\n"
            "  ACCEPTANCE (verifiable criteria). Specs reference each other\n"
            "  by filename where surfaces compose.\n"
            "The specs are written against youtube.com's REAL behavior (the\n"
            "  clone is feature-for-feature) — precise enough that an\n"
            "  engineer who has never seen youtube.com can build the feature\n"
            "  correctly from the spec alone."
        ),
        "owns": (
            "- `docs/specs/**` (NEW — the bible, yours entirely)\n"
            "- `evidence/wfx2-s/**` (your lane evidence)"
        ),
    },
]

LANESETS = {"wave2": WAVE2_LANES, "escalation": ESCALATION_LANES}


# ---------------------------------------------------------------- helpers
def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}",
          flush=True)


def verdict(laneset: str, data: dict) -> None:
    data["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = Path(str(VERDICT).format(laneset=laneset))
    path.write_text(json.dumps(data, indent=1))
    log(f"VERDICT written: {path} — {json.dumps(data)[:400]}")


def git(*args: str, repo: Path = REPO, timeout: int = 60):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=timeout)


def main_tree_files() -> list[str]:
    r = git("ls-tree", "-r", "--name-only", "origin/main")
    return r.stdout.split() if r.returncode == 0 else []


def main_sha() -> str:
    r = git("rev-parse", "origin/main")
    return r.stdout.strip() if r.returncode == 0 else ""


def specs_for(lane: dict, tree: list[str]) -> list[str]:
    hits = []
    for f in tree:
        if not f.startswith("docs/specs/") or not f.endswith(".md"):
            continue
        low = f.lower()
        if any(k in low for k in lane["specs_keywords"]):
            hits.append(f)
    return sorted(hits)


# ---------------------------------------------------------------- packet
def build_packet(lane: dict, tree: list[str], sha: str) -> str | None:
    """Build the worker packet. Returns None if a wave2 lane has no matching
    bible specs (honest PROMPT-RENDER-NEEDED — never dispatch a lane whose
    contract cannot be enumerated)."""
    if lane["laneset"] == "wave2":
        specs = specs_for(lane, tree)
        if not specs:
            log(f"NO SPECS matched {lane['lane_id']} — PROMPT-RENDER-NEEDED")
            return None
        spec_block = "\n".join(f"- `{f}`" for f in specs)
        specs_intro = (
            "Read EVERY spec above BEFORE writing anything. Implement your\n"
            "lane's specs to the letter. Gaps found in the field → record as\n"
            "addenda in `docs/specs/addenda/{name}.md` (NEVER edit existing\n"
            "spec files).".format(name=lane["name"])
        )
    else:
        spec_block = (
            "- `README.md` — the interface contract (the 16-feature ZTube\n"
            "  inventory) + the stack laws\n"
            "- `docs/plans/2026-09-28-webflix2-roadmap.md` — the wave/lane\n"
            "  structure + the laws"
        )
        specs_intro = (
            "No bible exists yet on this path (this lane may BE the bible\n"
            "lane). The README interface contract + the roadmap are the\n"
            "contract for this dispatch."
        )

    packet = f"""# {lane['lane_id']} — {lane['title']} (WebFlix 2.0)

You are a senior full-stack engineer executing ONE lane in WebFlix 2.0 — a
complete YouTube clone (interface baseline: ZTube; functionality cloned
feature-for-feature from youtube.com; every feature gets its complete real
behavior plus a complete backend). This document is your task packet —
follow it exactly. The repository itself is your specification library:
clone it and read the mandated files BEFORE writing anything.

    git clone https://github.com/payswapdotorg/WebFlix-2.0.git
    cd WebFlix-2.0 && git checkout -b {lane['branch']} origin/main

Your BASE is main @ {sha[:12]}.

## 0. Ground rules

- ONE lane: {lane['lane_id']} — {lane['title']}. Do NOT start any other lane
  (other lanes belong to concurrent workers; never create, modify or plan
  around their surfaces).
- ONE lane ONE branch: `{lane['branch']}` from current main.
- THE CONSUMER IS A CLEAN-ROOM LEAD: your lane is harvested as a relay
  bundle and reviewed gate-by-gate before merge — every claim in your
  report must be re-runnable from the bundle.

## 1. Stack laws (binding, from the repo README)

- Next.js 16 (App Router) + TypeScript strict — single app in `src/`
- Tailwind CSS 4 + shadcn/ui (New York) + lucide-react
- Prisma ORM + SQLite (db file in `db/`, schema in `prisma/`)
- bun (install / lint / typecheck / test / dev)
- NO mock data in code paths — the database is the truth; seed via
  `prisma/seed.ts`
- COMPLETE BACKEND LAW: every feature = Prisma model(s) + API route(s) +
  client hook/component + tests. No feature is UI-only.
- Honest data: counts/states always reflect the database; typed empty
  states otherwise. NEVER fabricate a metric.

## 2. Your contract — read first

{spec_block}

{specs_intro}

## 3. Deliverables

{lane['deliver']}

## 4. Allowed paths

{lane['owns']}

- SHARED FILES (`prisma/schema.prisma`, `prisma/seed.ts`, shared UI
  primitives, `src/lib/**` utilities, shared route layouts): ADDITIVE
  edits only — never modify, rename or weaken an existing model, type,
  route or test. Every shared-file edit is an ESCALATION, recorded in
  your RELAY-MANIFEST.
- NO new dependencies — `package.json` / `bun.lock` stay untouched; build
  with what the repo already has.

## 5. Merge protocol (the relay bundle)

At completion, at the WORKSPACE STORAGE ROOT, produce:

- `{lane['bundle']}` — created with
  `git bundle create {lane['bundle']} origin/main..{lane['branch']}`
- `evidence/{lane['name']}/**` — your lane evidence: spec-compliance notes
  per deliverable, honesty proofs for every count/metric, gate outputs
- `RELAY-MANIFEST.txt` — the manifest: your branch + base sha + the
  sha256 of EVERY relayed file (bundle + evidence) + escalations
  (shared-file edits, one line each) + divergences (anything the packet
  asked for that you could not deliver, and why — honest records only)

The lead harvests the bundle, re-runs your gates in a clean room, merges
`--no-ff` onto main, and records the merge in the ledger. A lane without
a RELAY-MANIFEST cannot be harvested.

## 6. Gates (zero regressions)

- `bun run lint` + typecheck + the full test battery: ALL green at your
  branch head, ZERO regressions vs your base.
- Lane tests for every delivered surface (the complete-backend law).
- If a gate is genuinely environment-blocked, document it precisely in
  your evidence with the exact command + error — never fabricate a pass.

## 7. COMPLETION REPORT

End your FINAL message with a section titled EXACTLY:

    {lane['marker']}

containing: base sha, branch, files changed (count), battery numbers
(pass/fail/skip — exact), new tests (count), escalations (shared-file
edits), divergences, and the relay-bundle inventory (file list).
"""
    return packet


# ---------------------------------------------------------------- claim
def claim_ledger(lanes: list[dict], laneset: str, sha: str) -> bool:
    """Append the activation addendum + flip the claimed rows to dispatched.
    Row rewriting is LINE-BASED (anchor on the lane id cell) — never
    substring surgery (the 02:44 near-miss: a partial-row replace left the
    old tail glued onto the new row)."""
    path = REPO / "docs/plans/wave-claims.md"
    ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    lines = path.read_text().splitlines()
    for lane in lanes:
        needle = f"| {lane['lane_id']} "
        for i, line in enumerate(lines):
            # table rows start with '|'; the lane-id CELL appears anywhere in
            # the row ('| 1 | WFX2-B boot-shell | ...') — a startswith needle
            # never matched (the 02:45 dry-test catch)
            if line.startswith("|") and needle in line:
                if laneset == "wave2":
                    lines[i] = (
                        f"| 2 | {lane['lane_id']} | lead-ALI10 | {ts} | "
                        f"main @ {sha[:8]} | dispatched (worker {lane['name']}) |"
                    )
                else:
                    lines[i] = (
                        f"| 1 | {lane['lane_id']} | lead-STEEL → lead-ALI10 | "
                        f"2026-09-28 22:25 / {ts} | seed → main @ {sha[:8]} | "
                        f"RE-DISPATCHED by lead-ALI10 (lapsed claim per the "
                        f"4h law + standing order; worker {lane['name']}) |"
                    )
                break
        else:
            log(f"WARN: ledger row not found for {lane['lane_id']} "
                f"(addendum still recorded)")
    addendum = (
        f"- {ts}Z (lead-ALI10, auto per the standing order): "
        + (
            "GATES LANDED (bible + boot on main) — the staked Wave 2 claims ACTIVATE: "
            if laneset == "wave2" else
            "ESCALATION FIRED (04:15Z clause: gates not landed, lead-STEEL inactive 25min) — the lapsed critical-path claims taken over: "
        )
        + ", ".join(l["lane_id"] for l in lanes)
        + f" dispatched under ali10 (workers: {', '.join(l['name'] for l in lanes)}; base main @ {sha[:8]}). "
          "Watchers armed; completions detected server-side; harvest → clean-room review → merge per the 1.0 playbook."
    )
    text = "\n".join(lines).rstrip("\n") + "\n" + addendum + "\n"
    path.write_text(text)
    git("add", "docs/plans/wave-claims.md")
    git("commit", "-m",
        f"ledger: {laneset} transition — "
        + ("Wave 2 claims activated (gates landed)"
           if laneset == "wave2" else
           "escalation fired — lapsed critical-path lanes re-dispatched")
        + f" [{', '.join(l['lane_id'] for l in lanes)}]")
    r = git("push", "origin", "main", timeout=90)
    ok = r.returncode == 0
    log(f"ledger claim push: {'OK' if ok else 'FAILED: ' + r.stderr[:200]}")
    return ok


# ---------------------------------------------------------------- mission
def update_mission_state(lanes: list[dict], laneset: str) -> None:
    try:
        d = json.loads(MISSION_STATE.read_text())
    except Exception:
        return
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for it in d.get("items", []):
        for lane in lanes:
            if it.get("id", "").lower() == lane["lane_id"].lower():
                it["status"] = "dispatched"
                it["branch"] = lane["branch"]
                it["worker"] = f"lead-ALI10's worker (agents tab, {lane['name']})"
                it["notes"] = (
                    "DISPATCHED under ali10 per the operator standing order — "
                    + ("Wave 2 claim activated (gates landed)."
                       if laneset == "wave2" else
                       "escalation clause (lapsed claim takeover).")
                    + f" Watcher armed; marker '{lane['marker']}'."
                )
    d["updatedAt"] = ts
    d.setdefault("timeline", []).append({
        "ts": ts, "kind": "success" if laneset == "wave2" else "warn",
        "text": (
            f"{'WAVE 2 DISPATCHED' if laneset == 'wave2' else 'ESCALATION FIRED'} — "
            + ", ".join(f"{l['lane_id']} ({l['name']})" for l in lanes)
            + " under ali10 per the standing order; queue_watch armed per lane"
        ),
    })
    MISSION_STATE.write_text(json.dumps(d, indent=1))


# ---------------------------------------------------------------- dispatch
def registry_record(name: str) -> dict | None:
    reg = FLAGS / "session_registry.jsonl"
    try:
        lines = [json.loads(x) for x in reg.read_text().splitlines() if x.strip()]
    except Exception:
        return None
    recs = [r for r in lines if r.get("name") == name and r.get("url")]
    return recs[-1] if recs else None


def dispatch_lane(lane: dict, prompt_file: Path) -> dict:
    log(f"DISPATCH {lane['name']} — prompt {prompt_file}")
    r = subprocess.run(
        [PY, str(SCRIPTS / "dispatch_worker.py"), "create",
         lane["name"], str(prompt_file)],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=WALL_GUARD_S,
    )
    log(f"  create rc={r.returncode} tail: {(r.stdout or r.stderr)[-300:]}")
    if r.returncode != 0:
        return {"ok": False, "rc": r.returncode,
                "tail": (r.stdout or r.stderr)[-300:]}
    rec = registry_record(lane["name"])
    if not rec:
        return {"ok": False, "rc": -1, "tail": "no registry record after create"}
    tab_prefix = (rec.get("tab_id") or "")[:8]
    ar = subprocess.run(
        [PY, str(SCRIPTS / "launch_queue_watch.py"), lane["name"],
         tab_prefix, lane["marker"]],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=60,
    )
    log(f"  queue_watch armed: {ar.stdout.strip()[:120]}")
    return {"ok": True, "chat": rec.get("url"), "tab_prefix": tab_prefix,
            "watcher": ar.stdout.strip()[:120]}


# ---------------------------------------------------------------- main
def main() -> int:
    laneset = sys.argv[1] if len(sys.argv) > 1 else ""
    if laneset not in LANESETS:
        print(__doc__)
        return 2
    lanes = LANESETS[laneset]
    started = time.time()
    log(f"wfx2_dispatch_child[{laneset}] START")

    git("fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", timeout=90)
    sha = main_sha()
    tree = main_tree_files()

    has_bible = any(f.startswith("docs/specs/") and f.endswith(".md") for f in tree)
    has_boot = any(f == "prisma/schema.prisma" for f in tree)

    if laneset == "wave2":
        if not (has_bible and has_boot):
            log("gates MISSING at fire time — standing down (monitor re-arms)")
            verdict(laneset, {"status": "gates-missing", "sha": sha})
            return 1
    else:  # escalation
        if has_bible and has_boot:
            log("gates LANDED before escalation fire — standing down")
            verdict(laneset, {"status": "gates-preempted", "sha": sha})
            return 0

    # 1. claim in the ledger (claim-before-dispatch law)
    claim_ok = claim_ledger(lanes, laneset, sha)
    if not claim_ok:
        # claims must land before dispatch (push-order precedence);
        # a failed push = no dispatch (honest fail-stop)
        verdict(laneset, {"status": "claim-push-failed", "sha": sha})
        return 1

    # 2. build + dispatch per lane
    results = {}
    for lane in lanes:
        if time.time() - started > WALL_GUARD_S:
            log("wall guard hit — remaining lanes not dispatched")
            results[lane["lane_id"]] = {"ok": False, "rc": -2,
                                        "tail": "wall-guard"}
            break
        packet = build_packet(lane, tree, sha)
        if packet is None:
            results[lane["lane_id"]] = {"ok": False, "rc": -3,
                                        "tail": "prompt-render-needed"}
            continue
        prompt_file = PROMPTS / f"{lane['name']}-{lane['branch'].split('/')[-1]}.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(packet)
        log(f"packet built: {prompt_file} ({len(packet)} chars)")
        results[lane["lane_id"]] = dispatch_lane(lane, prompt_file)

    # 3. mission-state truth
    update_mission_state(lanes, laneset)

    dispatched = [k for k, v in results.items() if v.get("ok")]
    failed = [k for k, v in results.items() if not v.get("ok")]
    verdict(laneset, {
        "status": "dispatched" if dispatched else "all-failed",
        "sha": sha, "dispatched": dispatched, "failed": failed,
        "results": results,
    })
    log(f"wfx2_dispatch_child[{laneset}] DONE — dispatched={dispatched} "
        f"failed={failed}")
    return 0 if dispatched else 1


if __name__ == "__main__":
    sys.exit(main())
