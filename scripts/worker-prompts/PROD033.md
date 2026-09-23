# PROD-033 — the production journey proof, Gates A–I evidence, and narrative reconciliation

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-033 (issue #9 Worker C). Independently prove production
  readiness: the journey harnesses W (web) / M (mobile) / X (combined
  field-to-office), the Gates A–I evidence assembly, the narrative
  reconciliation, and the environment fingerprint. Do not start PROD-015,
  HFX-302, HFX-401 or any other item.
- Owned surface (the ONLY files you may create/modify):
  - `tools/journey/**` (NEW — the W/M/X journey harness; see §4)
  - `tools/deployed/**` (EXTEND — journey legs that belong on the
    deployed-check foundation; see §4.4)
  - `docs/productization-evidence/PROD-033/**` (NEW — the evidence package)
  - `docs/PRODUCTION-READINESS-GATE.md` (ADD the gate→evidence index; the
    gate DEFINITIONS stay byte-identical)
  - `docs/DEPLOYMENT.md` (ADD the final-SHA deployment + replay runbook
    section; the existing sections stay intact)
  - `spec/technology-substitution-contract.md` (NEW FILE — materialize the
    referenced-but-missing contract from frozen sources; see §6)
  - `docs/TECH-LEAD-HANDOFF.md` + `docs/productization-roadmap.md`
    (narrative reconciliation to the final frontier; see §6)
- Explicitly NOT yours: `tools/geometry-eval/**` and
  `backend/api/src/geometry-eval/**` (HFX-302 — a CONCURRENT worker lane;
  never create, modify or read-plan around them), `tools/verify.ts` (the
  Lead's gate — your harness runs STANDALONE, never wired into
  `bun run verify`), `docs/productization-state.json` (the Lead's machine
  record), `apps/**`, `packages/**`, `backend/**`, `tools/build.ts`,
  `tools/start.ts`, `tools/smoke.ts`, `tools/bootstrap.ts` (read-only —
  consume their behavior, extend nothing in them), `tools/deployed-check.ts`
  (read-only — your entry point lives in `tools/journey/` and may IMPORT from
  `tools/deployed/`), every other module, `spec/**` EXCEPT the one missing
  file above, the root `bun.lock` (NO dependency changes — zero new
  dependencies; the harness uses only what the repo already dev-depends on),
  root `package.json`.
- EVIDENCE DOCTRINE (binding): every journey step record carries PASS/FAIL
  plus an evidence class from EXACTLY {deterministic, synthetic, emulated,
  physical}. NEVER upgrade a class. A claim without a committed artifact
  behind it (a test name, a harness output file, or a committed transcript)
  is not evidence. "It looked right" is not evidence. The final deployed-SHA
  proof belongs to the Lead's finalization (PROD-015) — where your evidence
  is at a different SHA than any deployment, your record says so VERBATIM.
- LIVE-BROWSER HONESTY: the W harness is BUILT for a real headless Chromium
  (the `tools/deployed-check.ts` doctrine). If Chromium is unavailable in
  your sandbox, the harness still ships complete, and your recorded run
  falls back to the deterministic legs — the record states EXACTLY which
  legs ran live and which fell back, in the per-step Class column. NEVER
  fabricate a live run. NEVER fake console-error counts.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout d11d03e44dbebb2b2cea069bffa7c7fb57ab6d2c   # public GitHub main (the Tech Lead pins this at dispatch)
git rev-parse HEAD   # must print d11d03e44dbebb2b2cea069bffa7c7fb57ab6d2c
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-033/journey-proof
bun run verify
```

Baseline expectation: **5677 pass / 0 fail, VERIFY: PASS** (the Tech Lead's
verified number at this SHA). If the baseline is red, STOP and report.

## 2. Mandated reading (in order, before writing anything)

1. `docs/PRODUCTION-READINESS-GATE.md` — the nine gates, the declaration
   rule, and the TWO Gate F journeys (your acceptance vocabulary; every
   verdict you record uses THIS document's words).
2. `docs/productization-state.json` — the machine record: the finalized
   inventory, the deployment facts, and the honest law that recorded facts
   are not proof until revalidated.
3. `tools/deployed-check.ts` + `tools/deployed/**` — the seven-check
   real-Chromium harness (sequential per-context checks, one bounded retry
   per CHECK, explicit-Chromium-missing failure, always-cleanup) — the
   engineering pattern your W legs EXTEND.
4. `tools/smoke.ts` — the measurement-causality doctrine (the port-dark
   identity proof; your local-serve journey runs adopt it).
5. `docs/productization-evidence/PROD-026/end-to-end-journey.md` — the
   twelve-step composed golden journey: the behavior contract for
   journey-2's legs.
6. `docs/productization-evidence/PROD-034/browser-journey.md` — the
   deterministic discoverability recording, ESPECIALLY its final section
   "What a real browser walk would add" — that section is precisely what
   your W journey's live legs deliver.
7. `docs/productization-evidence/PROD-032/README.md` +
   `apps/android/scripts/e2b-station/README.md` — the E2B station, the
   gradle trio, the 16-step field journey with its honest classification,
   and `BLOCKED_NO_KVM` (your M journey's foundation and its honesty law).
8. `docs/productization-evidence/PROD-031/**` — the browser execution path
   evidence (journey-2's live solution legs at the HTTP routes).
9. `docs/DEPLOYMENT.md` — the deployed shape, the file-naming rules, the
   rewrites table (your runbook section extends this document).
10. `spec/governance/architecture-change-record-004.md`,
    `spec/governance/architecture-change-record-005.md`,
    `spec/governance/architecture-change-record-006.md`, and
    `spec/architecture-lock.md` — the frozen invariants your substitution
    contract MATERIALIZES (never re-invents).
11. `docs/layered-competitive-stress-test-2026-09-16.md` — the 500-project
    architecture stress context behind Gate I.
12. `docs/EVALUATOR-GUIDE.md` — the fresh-evaluator path (Gate A's audience).

## 3. The four deliverables

1. **The journey harness** `tools/journey/` (§4) — one runner, three
   journeys (W/M/X), per-step records with evidence classes, exit 0/1.
2. **The Gates A–I evidence assembly**
   `docs/productization-evidence/PROD-033/gates.md` (§5) — verdict + evidence
   pointer + honest gap per gate.
3. **The narrative reconciliation** (§6) — materialize the missing
   `spec/technology-substitution-contract.md`; reconcile the handoff and the
   roadmap to the final frontier.
4. **The environment fingerprint + the final-SHA runbook** (§7) — the
   committed fingerprint record and the Lead's deployment/replay runbook
   section in `docs/DEPLOYMENT.md`.

## 4. The journey harness (`tools/journey/`)

One CLI, three journeys, one record format:

```bash
bun tools/journey/run.ts --list                 # enumerate journeys + steps
bun tools/journey/run.ts w  [--base-url URL]    # the web journeys (Gate F)
bun tools/journey/run.ts m                      # the mobile field journey
bun tools/journey/run.ts x  [--base-url URL]    # the combined journey
bun tools/journey/run.ts all [--base-url URL]   # everything, in order
```

- Exit 0 = every step PASS (with its recorded class); any FAIL step or any
  harness crash = exit 1 with the failing step named.
- `--base-url` defaults to the LOCAL production-like serve (§4.1); the Lead
  will pass the deployed URL at finalization — the harness treats both
  identically (same-origin fetch, no privileged access).
- Each run appends a timestamped record under
  `docs/productization-evidence/PROD-033/runs/` (committed): journey id, base
  URL, the repo SHA (from `git rev-parse HEAD` at run time), per-step
  table, and the per-leg class.

### 4.1 The W journey (web) — BOTH Gate F journeys, for real

Journey W1 (the golden product journey):

```text
HOME → DEMO PROJECT → BOQ → EVIDENCE → CASE → INTERVENTION → OUTCOME
```

Journey W2 (the interactive solution journey):

```text
CURRENT BUILDING → PROBLEM → INTERACTIVE SOLUTION → VALIDATE →
SOLUTION BOQ → BOQ LINE → SOLUTION STEP
```

- The default base: build and serve the product locally in the production
  shape — `bun run build` then `bun run start` (it requires
  `AISE_DATA_DIR`; use a scratch dir, and follow `tools/smoke.ts`'s
  causality doctrine: prove the port was dark before, and dark after).
- Walk EVERY leg with a real headless Chromium when available (the
  `tools/deployed-check.ts` pattern: sequential checks, isolated context
  per leg where session semantics require it, one bounded retry per check,
  console-error capture, always-cleanup). For each leg record: the route
  loads; the core controls are present; no blocking console errors; the API
  calls return expected status classes; a representative upload/import path
  works (W1); navigation state stays coherent; desktop AND mobile viewport
  smoke (the existing responsive checks show the pattern); direct
  manipulation creates typed operations (W2); an agent command creates a
  semantically equivalent operation (W2); validation results are visible
  and tied to a solution version (W2); generated BOQ lines navigate to
  contributing steps/geometry (W2).
- W1's live legs must cover at minimum what PROD-034's recording listed as
  "what a real browser walk would add": the live task-flow GET populating
  the mission/envelope/integration panels, the live `/readyz` probe
  populating the provider note, and a real capture upload round-trip.
- W2's live legs drive the PROD-031 browser execution path: the solution
  workspace executing through the HTTP routes in the plain browser
  (direct-manipulation intent submit, agent turn, validation, BOQ
  generation, the line↔step round-trip).
- Where Chromium is unavailable, the leg falls back to its deterministic
  proof (the committed tests that already prove the leg — cite them) and
  the record's Class column says `deterministic (fallback: no Chromium)`
  — honest, never silent.

### 4.2 The M journey (mobile/Android) — the field journey, honestly

- The M record is built on the PROD-032 E2B station field journey: the 16
  steps, their existing honest classification (5 REAL including the
  backend-boot and wire-envelope steps; the emulator lane BLOCKED_NO_KVM).
- If an E2B sandbox is available to you (an `E2B_API_KEY` in your
  environment), you MAY run `apps/android/scripts/e2b-station/` scripts
  fresh at your SHA and record the fresh transcripts (classification:
  emulated, with the transcript committed under
  `docs/productization-evidence/PROD-033/runs/m-e2b/`). If NOT available,
  the M record cites the committed PROD-032 transcripts at their recorded
  SHA (classification: emulated, source: committed transcript) and says so
  VERBATIM — a fresh run you did not do is never claimed.
- The emulator limitation is recorded as its own step row with class
  `physical` FAIL→BLOCKED_NO_KVM (the honest BLOCKED state, exactly as
  PROD-032 recorded it) — never silently dropped, never upgraded.

### 4.3 The X journey (combined field-to-office)

- The composed record: the M-lane's captured evidence session (the demo
  project's authoritative reality version) feeding the W-lane's solution
  workflow — field capture lands as evidence, the case opens on it, the
  solution is authored/validated, the solution BOQ is generated and traced.
- Run deterministically against the local serve (the same backend, the
  seeded demo world from PROD-026): the composition is the proof — each
  step cites the artifact that carried it (the capture record id, the case
  id, the solution version, the BOQ line ids).
- Per-step classification (deterministic for the composition legs; the
  field-capture origin rows carry the M journey's classes forward).

### 4.4 The `tools/deployed/**` extension

- Reuse, never duplicate: session-lifecycle, responsive, accessibility and
  console-guard checks already exist there — your journey legs IMPORT them.
  You may add journey-specific legs (the upload round-trip, the solution
  legs) as new modules in `tools/deployed/` if and only if they serve BOTH
  the local and deployed base URLs; otherwise they live in
  `tools/journey/`.

## 5. The Gates A–I evidence assembly (`gates.md`)

For EACH gate A–I, one section with EXACTLY this shape:

```text
## Gate <letter> — <name>
Verdict: <PASS | PARTIAL | FAIL>
Evidence: <committed pointers: test names, harness outputs, docs>
Honest gaps: <what only the Lead's final-SHA finalization can prove, or "none">
```

- Gate A (installable): run the clean-checkout install + `bun run verify`
  yourself at your branch SHA; cite the output.
- Gate B (deployment): cite the recorded deployment facts + the runbook
  (§7); the verdict is PARTIAL by construction until the Lead deploys the
  final merged SHA — say exactly that.
- Gate C (user-friendly interface): the W journey + the committed UI test
  corpus (cite the suites).
- Gate D (engineering truthfulness): cite the corpus that proves each
  bullet (the tests exist — find them, name them).
- Gate E (operational safety): same — the tenant/auth/upload/rate-limit/
  idempotency tests, named.
- Gate F (browser proof): your W-journey runs at the local serve; the
  DEPLOYED-URL replay is the Lead's finalization leg — verdict PARTIAL with
  the exact gap named, unless your sandbox ran the full live harness
  against the deployed URL too (only if true).
- Gate G (cost/availability): cite the provider docs/cost-guard docs +
  tests.
- Gate H (interactive solution proof): the W2 journey + PROD-026/031
  evidence + the building-benchmark results (committed).
- Gate I (technology substitution): assemble the FINALIZED drills — HFX-000
  (control plane), HFX-101 (Qwen3-VL provider benchmark), HFX-201 (VLM
  eval), HFX-301 (NL/direct-manipulation equivalence), PROD-029's
  substitution-evaluation model — each with its merged SHA + evidence path.
  HFX-302 (the Layer-3 geometry/validation substitution benchmark) is a
  CONCURRENT in-flight lane: cite your gates.md row stating it is in
  flight, expected evidence path `docs/productization-evidence/HFX-302/**`.
  NEVER fabricate its results. The verdict names exactly which layers have
  completed drills and which is pending.

## 6. The narrative reconciliation

1. **Materialize `spec/technology-substitution-contract.md`** — the file is
   referenced (the readiness gate's Gate I, the ACRs) but missing. Build it
   from FROZEN sources ONLY: ACR-004/005/006, `spec/architecture-lock.md`,
   the three-laws substitution doctrine (substitution is not semantics
   change; tolerances are declared, never implicit; unsupported is
   recorded, never computed), PROD-029's comparison kinds and canonical-
   projection model, and the HFX evidence structure. The contract states:
   the swappable technology boundaries per layer (capture SDKs,
   reconstruction engines, spatial systems, LLMs, retrieval/agent
   frameworks, geometry/constraint/physics engines, operation planners,
   renderers, interaction runtimes); the conformance requirements
   (semantic-equivalence tests, negative/discrimination tests, provenance
   continuity, failure-path tests, dependent-layer regression,
   compatibility window/rollback); and the authority laws (provider types
   never canonical; the swap never lowers assurance). EVERY section cites
   its source file. You are transcribing frozen law into the missing
   contract — if you find yourself inventing policy, STOP and report.
2. **Reconcile `docs/TECH-LEAD-HANDOFF.md`** — the frontier block and the
   2026-09-23 override section updated to the machine truth: PROD-001…034
   finalized except PROD-015/PROD-033 (this item); HFX-000/101/201/204/301
   finalized, HFX-302 in flight; the deployment facts with their honesty
   law; the remaining path (PROD-033 → Lead final deployment + Gate F →
   PROD-015 declares).
3. **Reconcile `docs/productization-roadmap.md`** — same truth, same shape;
   no new promises.

## 7. The fingerprint + the runbook

- `docs/productization-evidence/PROD-033/fingerprint.md`: bun version, node
  version, OS, the `tools/env-schema.ts` required/optional surface (which
  env vars the product needs, which are optional providers), the Chromium
  executable used (or "unavailable — deterministic fallback"), every
  journey run's base URL + repo SHA, and the exact `git rev-parse HEAD`.
- `docs/DEPLOYMENT.md` gains one section: "The final-SHA deployment +
  replay runbook" — the exact ordered commands for the Lead: merge →
  `bun run build` → deploy → `AISE_DEPLOYED_URL=<url> bun tools/deployed-check.ts`
  → `bun tools/journey/run.ts all --base-url <url>` → the evidence pin.
  With the expected outputs per step (from YOUR local runs, so the Lead can
  diff).

## 8. Gates (all must pass before delivery)

```bash
bun run verify      # 5677 pass / 0 fail PLUS your additive tests (if any) —
                    # ZERO existing failures; no test weakened/skipped/deleted
bun run typecheck   # PASS
bun run lint        # PASS
bun tools/journey/run.ts --list          # W/M/X enumerate with their steps
# then run what your sandbox allows (§4): the W local-serve run, the M
# record, the X composition — and commit every run record verbatim
```

## 9. Delivery — stage INSIDE the workspace-tracked project directory

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

## 10. Completion report (post as your FINAL message)

```text
PROD-033 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Journey harness
- w journey: <steps run; live legs count / deterministic-fallback legs count; PASS count>
- m journey: <fresh E2B run at <sha> OR committed-transcript citation; the BLOCKED_NO_KVM row present>
- x journey: <steps; per-step classes; PASS count>

## Gates A–I
- A: <verdict> — <one-line why>
- B: <verdict> — <the named Lead-finalization gap>
- C: <verdict> — <one-line why>
- D: <verdict> — <one-line why>
- E: <verdict> — <one-line why>
- F: <verdict> — <the named deployed-replay gap>
- G: <verdict> — <one-line why>
- H: <verdict> — <one-line why>
- I: <verdict> — <layers with completed drills; HFX-302 cited as in-flight>

## Narrative reconciliation
- spec/technology-substitution-contract.md materialized: <YES/NO — N sections, all source-cited>
- handoff + roadmap reconciled to the final frontier: <YES/NO>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
typecheck: PASS
lint: PASS
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
```
