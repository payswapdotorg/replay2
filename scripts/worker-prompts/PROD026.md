# PROD-026 — Interactive solution end-to-end composition and building benchmark

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-026 (end-to-end composition + building benchmark). Do not
  start PROD-027/028/029 or any other item. You CONSUME the merged surfaces of
  PROD-024 (the solution workspace), PROD-025 (solution BOQ derivation),
  PROD-022 (engine) and PROD-023 (compiler) — never re-implement any of them
  (explicit non-scope).
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/app/**` (the composition/integration layer ONLY: wiring the
    PROD-024 workspace mount point into the app shell, the golden-journey
    composition, cross-surface routing — see §4.1)
  - `docs/productization-evidence/PROD-026/**` (evidence documents)
  - `tools/building-benchmark/**` (NEW — the physically grounded building
    benchmark scenario + its deterministic checks; see §4.3)
- Explicitly NOT yours:
  - `apps/web/src/solution/**` (PROD-024's workspace — IMPORT its exported
    mount entry, never modify it; if the workspace lacks a mount seam you
    need, STOP and report the conflict)
  - `packages/solution-boq/**` and `backend/api/src/solution-boq/**`
    (PROD-025's BOQ derivation — IMPORT and CALL, never modify)
  - `packages/solution-engine/**`, `backend/api/src/solution/**`,
    `backend/api/src/reasoning/**` (PROD-022/023 — import and call only)
  - `packages/adapter-contract/**`, `packages/solution-contract/**`,
    `spec/**` (frozen contracts — import only)
  - `apps/android/**`, `apps/desktop/**`, `apps/web/src/parity/**`,
    `apps/web/src/boqlens/**`, `apps/web/src/viewer/**`,
    `apps/web/src/workspace/**`, `tools/competitive-parity/**`, the root
    `bun.lock` (the Lead regenerates it)
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond the repo's established stack.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull`, `git merge` or
  otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout __BASE_COMMIT__   # public GitHub main (adapter wave + PROD-018 + 022 + 023 + 025 + 024 merged)
git rev-parse HEAD   # must print __BASE_COMMIT__
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-026/e2e-composition
bun run verify
```

Baseline expectation: **__BASELINE__ pass / 0 fail, VERIFY: PASS** (includes
the solution-engine, reasoning-solution, solution-boq and solution-workspace
suites). If the baseline is red, STOP and report (do not try to fix the
baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants — especially the
   authoritative-reality / proposed-state seal)
3. `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow)
4. `spec/solution-operation-contract.md` (the PROD-021 contract)
5. `docs/interactive-engineering-solution-workflow.md` and
   `docs/productization-work-orders.md` §PROD-026 (your work order —
   reproduced in §3)
6. `packages/solution-engine/README.md` (deterministic engine), the
   `backend/api/src/solution/` tool endpoints, and
   `backend/api/src/reasoning/solution/` (the compiler — the SAME operation
   semantics the agent path uses)
7. `packages/solution-boq/README.md` and `backend/api/src/solution-boq/`
   (PROD-025: solution BOQ derivation + the trace objects — every BOQ line
   must carry its derivation trace)
8. `apps/web/src/solution/` (PROD-024's workspace — its exported mount entry,
   its direct-manipulation and agent interaction modes, its state stepping)
9. `docs/productization-evidence/PROD-018/**` (the composition conventions:
   cross-links, boundary labels, golden journey) and
   `docs/productization-evidence/PROD-024/**` (the workspace's own conformance
   + accessibility evidence)

## 3. Work order (reproduced verbatim from docs/productization-work-orders.md)

**Owner:** SHARED · **Depends on:** PROD-024, PROD-025, PROD-018

**Purpose** — Compose and independently verify the complete new workflow as a
first-class AISE product workflow.

**Required journey**

```text
reconstruct/open current building reality
 → select engineering problem
 → create interactive solution
 → manipulate directly and/or use agent commands
 → step through proposed layers/states
 → validate
 → generate solution BOQ
 → click BOQ line
 → jump to corresponding solution step/geometry
 → inspect and understand solution
 → save/revise solution without altering observed reality
```

**Acceptance** — The full journey works on a seeded building fixture and on at
least one representative physically grounded building scenario. All
consequential quantities have provenance, the agent and direct manipulation
produce equivalent operations, validation is deterministic, and no proposed
state leaks into authoritative reality.

**Evidence** — Complete recording + request/operation trace + deterministic
replay + physical/building benchmark + semantic agent/direct-manipulation
equivalence + provenance audit.

## 4. Build specification

### 4.1 The composition wiring (apps/web/src/app/**)

- Wire the PROD-024 workspace's exported mount entry into the app shell as a
  first-class surface: a project-scoped route (the house hash-router
  convention), a primary-nav entry, and the composition cross-links from
  PROD-018's parity layer (case → solution workspace, intervention →
  solution, BOQ lens line → solution BOQ line trace). The wiring must not
  duplicate or re-implement workspace internals — it mounts the entry and
  routes to it.
- The composed golden journey: a `composition-model` test module (the
  PROD-018 parity convention) that drives the ENTIRE §3 journey
  programmatically against the seeded fixture — every step's typed operation,
  state transition, validation snapshot, BOQ trace and cross-surface link
  asserted, with the agent-path and direct-path variants both executed and
  their operation identities compared (equivalence proof).

### 4.2 The seeded-fixture journey (deterministic, replayed)

- Use the repo's committed seeded building fixture (the engine's
  `fixtures/baseline-geometry.json` + the PROD-025 fixtures) — the journey
  must be byte-deterministic: two full runs produce identical operation ids,
  state digests, validation snapshots and BOQ traces (the PROD-022 replay
  doctrine applied end-to-end).
- Assert the authoritative-reality seal: after the full journey (including
  revise/save), the authoritative Reality Graph is byte-identical to its
  pre-journey state (mutation-protection proof at the composition level).

### 4.3 The physically grounded building benchmark (tools/building-benchmark/**)

- One representative real-world-scale scenario (e.g. a masonry retrofit with
  opening creation, lintel, plaster and finish layers — quantities a builder
  could sanity-check against trade practice): a committed scenario descriptor
  + expected-outcomes fixture + a deterministic check runner wired into the
  root `bun run verify` (the tools/ pickup convention, cf.
  tools/competitive-parity).
- The benchmark asserts: physically plausible quantities (areas, volumes,
  unit conversions via the engine's units module), provenance on every
  consequential quantity (parameter + source state + trace identity), and the
  full §3 journey on the scenario.
- An evidence doc renders the benchmark's quantities in a builder-readable
  table with the provenance chain for each line.

### 4.4 Evidence documents (docs/productization-evidence/PROD-026/**)

1. `end-to-end-journey.md` — the complete §3 journey recording: every step,
   its typed operation, its state transition, its validation snapshot, the
   BOQ line clicked, the geometry jump target (with the deterministic replay
   digests).
2. `equivalence-proof.md` — agent-path vs direct-path: the same twelve-step
   journey executed through the compiler (NL commands) and through direct
   manipulation, with identical operation identities (the sha-256 identity
   excluding provenance) and identical outcomes.
3. `provenance-audit.md` — every consequential quantity in the benchmark:
   its derivation chain (operation parameters → quantity model → BOQ line →
   trace identity), the version locks, and the honest-empty states.
4. `reality-seal.md` — the authoritative-reality byte-identity proof across
   the journey including save/revise cycles.

## 5. Quality gates (run all; paste the exact summary lines)

```bash
bun run verify        # EXPECT: (__BASELINE__ + N) pass / 0 fail, boundaries clean
bun run typecheck     # EXPECT: VERIFY: PASS
bun run lint          # EXPECT: VERIFY: PASS
```

- `verify` must be green with your new tests included (state N explicitly —
  the composition-model, benchmark and seal tests).
- Boundaries: no cross-zone imports; the composition layer imports the
  workspace/BOQ/engine surfaces through their public exports only.

## 6. Delivery

Stage your complete delivery under `delivery/` in the workspace (the house
convention — see AGENTS.md), including:

```text
delivery/DELIVERY.txt          # git diffstat vs BASE + commit sha + file list
delivery/<all changed files>   # full paths preserved
delivery/docs/productization-evidence/PROD-026/*.md
```

`DELIVERY.txt` header format (exact):

```text
commit: <your 40-hex commit sha>
base: __BASE_COMMIT__

 <diffstat>
```

## 7. Completion report (post as your FINAL message)

```text
PROD-026 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Journey verification
- fixture journey complete: YES/NO — <the twelve steps, each with its
  operation id + state digest>
- deterministic replay: <two-run digest equality proof, one line>
- reality seal: <authoritative-graph byte identity, one line>

## Equivalence
- agent vs direct: <identical operation identities — list the twelve
  operation ids once, they are shared>

## Benchmark
- scenario: <name + one-line description>
- consequential quantities: <count> — all with provenance YES/NO
- physically plausible: <the sanity-check table summary>

## Gates
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
typecheck: <PASS/FAIL>
lint: <PASS/FAIL>
boundaries: <clean / violations>

## Honesty section
- deviations from this packet: <none | list>
- known gaps / honest FAILs: <none | list — an honest FAIL is reportable
  work; a silent gap is not>
```

If you cannot complete a section, write `HONEST FAIL: <reason>` in place —
never fabricate. A truthful partial delivery with honest FAILs is acceptable
and will be gated on its real merits; a fabricated green report is not.
