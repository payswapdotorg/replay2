# PROD-014 — Final evaluator documentation and one-command demo bootstrap

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-014 (install/release documentation + one-command demo
  bootstrap). Do not start PROD-015 or any HFX item (explicit non-scope: the
  production-readiness declaration, the deployed-URL re-verification, any new
  product feature).
- The EXIT CRITERION (the roadmap's wording): "Fresh evaluator follows docs
  and reaches the working product WITHOUT repository archaeology." Everything
  you build serves that sentence.
- Owned surface (the ONLY files you may create/modify):
  - `tools/bootstrap.ts` + `tools/bootstrap.test.ts` (NEW — see §3.1)
  - `docs/EVALUATOR-GUIDE.md` (NEW — the evaluator quickstart)
  - `docs/INSTALL.md` (MODIFY — pointer updates only: the demo command and
    the guide link; do not rewrite PROD-001's verified content)
  - the ROOT `package.json` — ONLY the `scripts` block, ONLY adding
    `"demo": "bun tools/bootstrap.ts"` (no dependency changes; the Lead
    checks the diff is scripts-only)
  - `docs/productization-evidence/PROD-014/**` (evidence documents)
- Explicitly NOT yours: `tools/verify.ts`, `tools/dev.ts`, `tools/build.ts`,
  `tools/start.ts`, `tools/smoke.ts`, `tools/db-migrate.ts`,
  `tools/db-seed.ts`, `tools/validate-env.ts` (CALL them — subprocess or
  import — never modify), every other file, `bun.lock` (no dependency
  changes means no lockfile change — do not touch it), `spec/**` (FROZEN),
  `apps/**`, `backend/**`, `packages/**`.
- The bootstrap is an ORCHESTRATOR over the existing tools — it must NOT
  reimplement install/build/start/smoke logic. Deterministic tests use an
  injected command runner (no real network/ports/processes in tests).
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 7b90d70bc0309bbac790af9713fad4de17c9e984   # public GitHub main (layer-hardening wave complete)
git rev-parse HEAD   # must print 7b90d70bc0309bbac790af9713fad4de17c9e984
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-014/evaluator-bootstrap
bun run verify
```

Baseline expectation: **5105 pass / 0 fail, VERIFY: PASS**. If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandated reading (in order, before writing anything)

1. `docs/productization-roadmap.md` — PROD-014's row: "Install/release
   documentation and one-command demo bootstrap ... Fresh evaluator follows
   docs and reaches the working product without repository archaeology."
2. `docs/INSTALL.md` — the authoritative install guide (PROD-001-owned,
   verified). Your guide REFERENCES it; you do not duplicate it.
3. `docs/DEPLOYMENT.md` + `docs/free-tier-deployment.md` — the deployment
   story your guide points evaluators at (the deployed URL is the Lead's
   re-verification, not yours).
4. `tools/dev.ts`, `tools/build.ts`, `tools/start.ts`, `tools/smoke.ts`,
   `tools/db-migrate.ts`, `tools/db-seed.ts`, `tools/validate-env.ts` —
   the exact CLIs you orchestrate (their argument surfaces, exit codes,
   env requirements).
5. `README.md` + `AGENTS.md` — the repo's public face and conventions.
6. `docs/interactive-engineering-solution-workflow.md` — the product
   workflow your evaluator journey walks (Reality → Understanding →
   Solution → Outcome).
7. `docs/productization-evidence/PROD-026/end-to-end-journey.md` — the
   twelve-step golden journey your guide's "what to look at" section
   references.

## 3. The work

### 3.1 The one-command demo bootstrap (`tools/bootstrap.ts`)

`bun run demo` (or `bun tools/bootstrap.ts`) — takes a fresh checkout to a
working product:

- PHASES (each printed with a clear banner, each FAILING FAST with an
  actionable message): prerequisites check (bun version, ports free) →
  `bun install` (if node_modules absent) → env validation (safe demo
  defaults; NO secrets required — the demo-open auth mode) → db migrate →
  db seed → build → start (background, with a health wait on the smoke
  endpoints) → smoke → print the evaluator entry URLs (local web app, the
  demo path, the guide link).
- IDEMPOTENT: re-running on an already-bootstrapped checkout skips
  completed phases (a light state file under a gitignored path, or phase
  probing — your call, document it).
- CLEAN FAILURE: on any phase failure, stop, print WHICH phase, the tool's
  actual output, and the troubleshooting section pointer; never leave a
  half-started server holding ports (best-effort cleanup).
- `--fresh` flag: tears down the demo state (the scratch data dir) and
  re-runs from zero — this is what your fresh-checkout evidence uses.
- NO new dependencies (node stdlib + the repo's existing tools only).

### 3.2 The evaluator guide (`docs/EVALUATOR-GUIDE.md`)

The 10-minute path from zero to product, evaluator-voiced:

1. Who this is for + what you will see (the three product promises, one
   paragraph each with a concrete "you will know it works when..." check).
2. Prerequisites (exact versions, links) + the ONE COMMAND + what the
   phase banners mean.
3. The demo walkthrough: the auth gate → demo entry → the Reality layer
   (observed scene, evidence) → Understanding (a question, the Evidence
   Envelope) → Solution (create/step/revise, the BOQ) → Outcome. Concrete
   clicks, honest about what is seeded fixture vs live capability.
4. Verifying deeper: `bun run verify`, `bun run smoke`, where the evidence
   docs live (per-wave pointers into docs/productization-evidence/).
5. Troubleshooting table (top failures → INSTALL.md section pointers).
6. What this demo is NOT (no real capture hardware, no real providers —
   deterministic fixtures; the deployed URL for the hosted experience).
7. A "docs audit" trail: every command in the guide was executed by you
   against a fresh checkout — the transcript is your evidence.

### 3.3 The docs updates (`docs/INSTALL.md`, root `package.json`)

- INSTALL.md: add the demo command + guide link at the TOP (a short
  "Just want to see it run?" box); fix any pointer your fresh-checkout
  run proved stale (each fix documented in your evidence).
- package.json: scripts-only `"demo": "bun tools/bootstrap.ts"`.

### 3.4 Evidence (`docs/productization-evidence/PROD-014/`)

- `fresh-checkout-transcript.md` — the PROOF: a scripted fresh `git clone`
  of YOUR DELIVERY COMMIT into a temp dir, `bun run demo --fresh`, the full
  phase transcript, the smoke result, the entry URLs (redacted ports/paths
  fine — no secrets). This transcript is the exit criterion's evidence.
- `evaluator-journey.md` — the walkthrough you performed in the UI (or
  headless-equivalent) following YOUR OWN guide, step by step, with what
  worked and any doc bug you fixed along the way.
- `docs-audit.md` — every doc pointer you verified; the stale ones you
  fixed; the ones outside your surface that are still stale (honest list
  for the Lead).
- `integration-notes.md` — what the Lead wires/verifies (the scripts-only
  package.json diff check, the deployed-URL re-verification context).

## 4. Quality gates (run at your delivery commit)

```bash
bun run verify        # EXPECT: (5105 + N) pass / 0 fail, boundaries clean
bun run typecheck     # PASS
bun run lint          # PASS
bun tools/bootstrap.ts --fresh   # in your clone: full pass, transcript captured
```

N is your new-test count (bootstrap.test.ts: phase ordering, idempotency
logic, failure modes, URL printing — injected runner, deterministic);
report the exact number.

## 5. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's
harvest API cannot see. After committing, copy EVERY new/changed file (the
complete diff vs the base commit `$BASE` from §1) into the PROJECT directory
(the one containing package.json / src/ — the workspace root), preserving
repo-relative paths:

```bash
cd /home/z/AISE
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery. Do NOT change anything else after the
gate run. No re-runs, no edits, no push.

## 6. Completion report (post as your FINAL message)

```text
PROD-014 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## The one command
- command: bun run demo (--fresh documented)
- phases: <the list>
- idempotency + clean-failure: <one line>

## Fresh-checkout proof (the exit criterion)
- fresh clone of the delivery commit: YES/NO
- bun run demo --fresh: <phases passed / total, time>
- smoke: PASS/FAIL
- evaluator entry URLs printed: YES/NO
- repository archaeology required: NONE — <one line on how the guide
  anticipates every step>

## Docs
- EVALUATOR-GUIDE.md sections: <list>
- INSTALL.md updates: <the box + fixed stale pointers count>
- package.json diff: scripts-only (demo line) — YES/NO
- stale docs outside surface (honest list for the Lead): <list or none>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
