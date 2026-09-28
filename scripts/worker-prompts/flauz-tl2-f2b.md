# FLAUZ-TL2-F2B — the environments lifecycle provider-retry + the sanctioned INV-2 journey extension (battery INV-2)

You are a senior TypeScript engineer executing ONE well-specified work item
in the Flauz repository (a Code OSS fork; the Flauz program lives in
`extensions/flauz-*`). This document is your task packet — follow it exactly.
The repository is your specification library; read the mandated files BEFORE
writing anything. You cannot see the sender's context: everything you need
is in this packet or in the repo.

## 0. Ground rules

- ONE work item: FLAUZ-TL2-F2B — land the bounded, recorded provider-retry
  contract at the ENVIRONMENTS LIFECYCLE seam and extend the battery's INV-2
  journey to measure it, flipping the battery's INV-2 row from FAIL to PASS.
  Do not start any other item.
- This lane carries the ONE sanctioned battery extension (the F3/INV-5
  precedent). The justification is on the record: the F2 lane's honest
  STOP-clause finding (ratified in the WORK-REGISTRY AO-H1 landing record,
  2026-09-28): the battery's INV-2 journey drives the frozen
  flauz-environments seam directly, and its stub fails the provider ONCE
  then returns 200-running — so any automatic retry flips the outcome to
  success and breaks inv2.no-silent-success, while no retry leaves the
  count at 1. The flip therefore requires BOTH the product contract at that
  seam (yours, §3.1) AND the journey rework (yours, §3.2). Your
  battery-suite edits are LIMITED to the INV-2 journey: every OTHER row,
  assertion, coverage table, doctored control and gate mode stays
  byte-identical. Any edit outside the INV-2 journey is forbidden.
- Owned surface (the ONLY files you may create/modify):
  - `extensions/flauz-environments/src/lifecycle/**` — the manager's
    provider-facing op path gains the bounded retry (ADDITIVE: the state
    machine, the typed outcome shapes, the fail-closed posture and every
    existing transition stay byte-compatible; no state-machine redefinition
    — the lifecycle state machine is a landed TL3 contract)
  - NEW files under `extensions/flauz-environments/src/lifecycle/` (the
    retry policy module) if you factor one
  - `extensions/flauz-environments/test/**` (new + extended tests)
  - `extensions/flauz-environments/README.md` if it documents lifecycle
    semantics (check first; only additive sections)
  - `extensions/flauz-workflow/test/agentos-battery.test.ts` — ONLY the
    INV-2 journey section (see §3.2)
  - `extensions/flauz-workflow/test/canaries/agentos-runtime.drill.ts` —
    ONLY the INV-2 leg (the same journey over the real-socket stub)
  - `flauz-delivery/tl2-f2b-env-retry/**` (your delivery — §7)
- Explicitly NOT yours: `src/vs/**` (Architecture Lock — zero changes),
  `build/flauz/scripts/agentos-battery.mjs` (the GATE — zero changes; the
  gate already emits real verdicts for INV-2), `test/fixtures/agentos-battery/**`
  (the doctored controls stay untouched), `extensions/flauz-agent/**`
  (the durable-runtime retry contract is LANDED at PR #45 — read it as your
  semantic precedent, do not modify it), `extensions/flauz-models/**`,
  `extensions/flauz-memory/**`, `extensions/flauz-execution/**`,
  `extensions/flauz-browser/**`, `extensions/flauz-resources/**`,
  `extensions/flauz-workspace/**`, `extensions/flauz-workflow/src/**`,
  `docs/FLAUZ-PROGRAM/**`, every CI workflow file.
- Hard rules: no CopilotKit/OpenMuse runtime dependency; no new npm
  dependencies (zero-dep: node:test + type stripping only); no test is
  weakened, skipped or deleted; fail-closed preserved — exhaustion is the
  existing TYPED terminal failure (never a silent success, never an
  auto-pass); the doctored controls keep firing; INV-4's approval posture
  stays PASS (a retry never auto-grants anything).
- Your base is FIXED at the commit in §1. Do NOT `git pull`, fetch or merge
  upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/flauz.git   # FULL clone, no --depth
cd flauz
git checkout 0d5d3903cea7a7a6467cdf055074665968cbc859   # pinned dispatch base
git rev-parse HEAD   # must print 0d5d3903cea7a7a6467cdf055074665968cbc859
git checkout -b tl2/f2b-env-retry
node --version        # v24.x (receipts run with --experimental-strip-types)
```

Baseline receipts at the base (TL2-verified at dispatch; re-run and record —
the drift is the finding signal): environments `node --test "test/*.test.ts"`
148 pass / 0 fail / 2 skip; agent 267/267; models 106; workflow 112
(includes the INV-5 journey from PR #43); execution 99; workspace 75; memory
48. The battery census at the base is exactly: PASS INV-1, INV-3, INV-4,
INV-5, INV-6, INV-7, INV-8; FAIL INV-2 (yours — the sole remaining row).
The INV-2 FAIL reason: `inv2.bounded-retry: bounded, recorded retry
behavior: the Agent OS performed 1 provider start call(s) against the
failing provider before surfacing the typed error (no automatic bounded
retry exists on the v0 slice; retries are caller-driven only)`.

## 2. Mandated reads (BEFORE writing anything)

1. `extensions/flauz-environments/src/lifecycle/manager.ts` —
   `perform(op, request)`: the op dispatch you will extend; note how
   outcomes and op rows are produced.
2. `extensions/flauz-environments/src/lifecycle/cloudHttp.ts` — the cloud
   executor: `CLOUD_PROVIDER_ERROR` mapping (non-2xx → the typed error
   effect), the start path, and which error classes exist.
3. `extensions/flauz-environments/src/lifecycle/stateMachine.ts` +
   `store.ts` + `types.ts` — the landed TL3 lifecycle contract you must NOT
   redefine; the ops journal shape the retry attempts must record into.
4. `extensions/flauz-workflow/test/agentos-battery.test.ts` — the INV-2
   journey (search `INV-2 provider-failure-retry`): `bootCloudLeg`, the
   scripted response queue (`startQueue.shift()` — empty queue answers
   200-running), every assertion (`inv2.no-silent-success`,
   `inv2.state-reflects-failure`, `inv2.failure-recorded`,
   `inv2.bounded-retry`, `inv2.retry-recovered-recorded`,
   `inv2.retry-recorded`, `inv2.task-reflects-failure-path`,
   `inv2.evidence-on-failure`), and the task-level leg.
5. `extensions/flauz-workflow/test/canaries/agentos-runtime.drill.ts` —
   the INV-2 leg: `startProviderServer`, `inv2StartCalls` (fails the FIRST
   start then recovers — you will extend the failure beyond the budget).
6. `extensions/flauz-agent/core/providerRetry.mjs` + its test
   `extensions/flauz-agent/test/providerRetry.test.ts` (LANDED, PR #45) —
   the semantic precedent for your retry policy (trigger classification,
   the bound, backoff cap, per-attempt recording, exhaustion = typed
   terminal failure, injectable wait). Mirror the SEMANTICS at the
   lifecycle seam in the repo's own TypeScript idiom.
7. `docs/FLAUZ-PROGRAM/WORK-REGISTRY.md` — the AO-H1 record (the F2
   landing + the STOP-clause finding + this lane's registration).

## 3. The semantic contract

### 3.1 The lifecycle provider-retry (product code)

The manager's provider-facing ops (at minimum `start`; survey `create`,
`stop`, `attach`, `snapshot`, `destroy` and state your scope decision in
the REPORT) gain an automatic bounded, recorded retry when the executor
surfaces a RETRYABLE typed provider error:

1. **Trigger**: only a typed retryable provider error class (at this seam:
   `CLOUD_PROVIDER_ERROR` from transient HTTP classes — 5xx and
   network-ish 429; a 404 `sandbox vanished` is NOT retryable — the drill's
   INV-8 leg depends on it staying a single-shot typed failure). Absent,
   malformed or non-retryable errors keep the existing single-shot honest
   path byte-identically. A thrown executor (lost response) is never
   retried blindly — classify honestly and state the rule.
2. **Bound**: `maxAttempts` total (default 3). Configuration is ADDITIVE
   (a new optional field on the manager/executor options; invalid config is
   a typed fail-closed error, never a silent default-masking).
3. **Backoff**: a capped, deterministic-friendly wait between attempts
   (honor a provider `Retry-After`-style hint if the executor surfaces one;
   otherwise a minimal fixed delay), with an INJECTABLE wait/clock port so
   tests and the drill stay deterministic (never real sleeps on the test
   path).
4. **Recording**: every attempt is recorded in the ops ledger (the existing
   journal): each row carries the op, the attempt ordinal, the typed
   outcome and the wait applied. The recording must be readable by the
   journey (a plain file read like `readEnvOps`).
5. **Exhaustion**: after `maxAttempts` the op resolves to the EXISTING
   typed terminal failure outcome — the state machine's failed path and
   every existing assertion shape stay intact (`inv2.no-silent-success`,
   `inv2.state-reflects-failure`, `inv2.failure-recorded` must all still
   pass with the retry engaged).
6. **Composability**: an explicit caller-driven retry after exhaustion (a
   second `perform('start', ...)`) starts a FRESH window (new attempt
   sequence) — the recovery leg depends on this.
7. **Additivity law**: with the retry feature disabled (maxAttempts = 1 or
   the default off-switch you design), behavior is byte-identical to the
   base. The state machine file itself should not need edits — if you
   believe it does, STOP and report instead (the TL3 contract boundary).

### 3.2 The sanctioned INV-2 journey extension (battery suite)

Rework the INV-2 journey so it measures the contract honestly — mirroring
the F3/INV-5 precedent (a pre-registered follow-up, never verifier
invention):

1. The stub's failure must exceed the retry budget: script the start queue
   with MORE failures than `maxAttempts` (e.g. 5 × HTTP 500 with
   maxAttempts 3) so the automatic retry engages, is recorded, and
   EXHAUSTS — `startCalls` reaches 3 (>= 2) while the outcome is still the
   typed failure (`inv2.no-silent-success` + `inv2.state-reflects-failure`
   + `inv2.failure-recorded` all still assert the honest failure).
2. `inv2.bounded-retry` flips: the count is now the engaged automatic
   retry's call count, not 1.
3. ADD the recorded-retry assertions (new checks, named honestly, e.g.
   `inv2.retry-attempts-recorded`: the ops ledger carries the attempt
   sequence with ordinals and typed outcomes; `inv2.bounded-exhaustion`:
   the count stops at exactly maxAttempts — bounded, not unbounded).
4. The recovery leg stays caller-driven: after the exhaustion, the queue
   answers 200-running and the second `perform('start')` succeeds —
   re-assert `inv2.retry-recovered-recorded` and rework
   `inv2.retry-recorded` honestly for the new op-row shape (state the exact
   expectation: with per-attempt rows, the two EXPLICIT start requests
   produce the two request-level rows plus the attempt rows — assert what
   the product actually records, do not bend the product to the old
   assertion).
5. The task-level leg (`inv2.task-reflects-failure-path`,
   `inv2.evidence-on-failure`, the `executorCalls === 1` setup assert)
   stays byte-identical — it measures the WORKFLOW envelope's
   caller-driven path, untouched by this lane.
6. The drill leg (`agentos-runtime.drill.ts` INV-2): the same
   budget-exceeding pattern over the real socket (fail the first
   `maxAttempts` starts, then recover), asserting the same journey
   honestly.

### 3.3 NOT yours (restating the boundary)

The flauz-agent durable-runtime retry is LANDED (PR #45) — read-only. The
GATE and the doctored controls are untouched. No other battery row moves:
the census diff at your head must be EXACTLY INV-2: FAIL → PASS, every
other row byte-identical.

## 4. The verification battery (run at your head)

1. `node --test` in `extensions/flauz-environments` — your new tests
   (retry engagement, the bound, per-attempt recording, exhaustion =
   the typed terminal failure, the injectable wait, non-retryable classes
   single-shot, composability, the additivity law with the feature off)
   plus ZERO regressions from the 148/0/2 baseline.
2. `node build/flauz/scripts/agentos-battery.mjs` → exit 0, census diff
   exactly INV-2 flipped to PASS (7 PASS / 1 FAIL / 0 SKIP → 8 PASS).
3. `node build/flauz/scripts/agentos-battery.mjs --json` → the INV-2 row
   quoted in the REPORT.
4. The drill: run per its README/conditions (the runtime rung; SKIP
   honestly if the endpoint is unavailable — never fake).
5. `tsc --noEmit -p extensions/flauz-environments/tsconfig.json` → exit 0;
   `-p extensions/flauz-workflow/tsconfig.json` → only the pre-existing
   Lane-K seamClient `.pid` error (reproduced identically at the base —
   state it honestly, never claim clean what is not).
6. `git diff --stat 0d5d3903...HEAD -- src/vs
   ':(exclude)src/vs/workbench/contrib/flauz'` → EMPTY (paste it).
7. `sh build/flauz/scripts/fork-critical-guard.sh --base origin/main --head HEAD`
   → exit 0.
8. Secrets scan of your diff → zero hits (paste the command + result).
9. All six sibling suites re-run (zero regressions): agent 267, models 106,
   workflow 112, execution 99, workspace 75, memory 48.

## 5. Receipts (run at your head; paste the command + summary into the REPORT)

The §4 battery IS the receipt list — every item pasted with its command and
its result line.

## 6. What this lane is NOT

- Not INV-1/3/4/5/6/7/8 (all PASS — your census diff must not touch them).
- Not a provider-adapter change: `cloudHttp.ts`'s error MAPPING stays;
  your retry lives in the manager's op path (or a factored policy module).
- Not a state-machine redefinition: the landed TL3 lifecycle contract is
  read-only in behavior (additive recording rows are fine).
- Not a weakening: exhaustion stays terminal; the doctored controls keep
  firing; no test is skipped; the additivity law (feature off =
  byte-identical) is itself a test.

## 7. Delivery protocol (credential-free bundle)

Work on branch `tl2/f2b-env-retry`; commit early and often. At completion,
stage at the sandbox workspace ROOT, with the file-writing tool:

STAGING LAW (lesson 2026-09-28 — a fully-completed lane was lost this way):
ONLY files written through the file-writing tool persist in the platform's
workspace file index. Bash-created files — the whole git clone and anything
staged inside it — are LOST the moment the sandbox recycles. The
flauz-delivery/ directory below MUST therefore be tool-written at the
workspace ROOT: the PARENT directory of your clone (the scaffold root that
already contains package.json, prisma/, src/) — never inside the clone.
bundle.git is staged the same way: write the bundle file's bytes with the
file-writing tool (tens of KB are fine). MANDATORY self-check before you
finish: confirm the workspace file tree lists
flauz-delivery/<lane-id>/MANIFEST.txt, REPORT.md, bundle.git and files/ —
if it does not, the delivery is lost and the lane is a failure even with
every receipt green.

```
flauz-delivery/tl2-f2b-env-retry/
  MANIFEST.txt     # one line per file: <repo-relative-path>  <sha256>  <bytes>
  REPORT.md        # the completion report (see §8) — LAST LINE exactly:
                   #   FLAUZ-TL2-F2B-REPORT END
  bundle.git       # git bundle create bundle.git 0d5d3903cea7a7a6467cdf055074665968cbc859..HEAD
  files/           # repo-relative mirror of EVERY file you created/modified
```

ZERO secrets anywhere in the delivery.

## 8. REPORT.md format

1. Header: lane id, base sha, head sha, branch, dates.
2. The M1 map: the manager's provider-call path + the ops-ledger mint
   points (where the retry engages, where each attempt row is written).
3. The retry semantics as implemented (§3.1 items 1-7 with file/function
   references; the configurable surface; the injectable wait; the
   additivity off-switch).
4. The journey extension (§3.2 items 1-6): the new stub script, every
   reworked/new assertion named, the exact new expected counts.
5. The gate table: every §4 receipt command + result.
6. Honest limitations.
7. Decision proposals for TL2 ratification (the orchestrator numbers them
   DL-78+ at landing).
8. The final line: `FLAUZ-TL2-F2B-REPORT END` (exact).
