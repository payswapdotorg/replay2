# PROD-022 — Deterministic interactive solution engine

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-022 (the deterministic solution engine). Do not start
  PROD-023/024/025 or any other item. Do not build an agent, a compiler, a
  UI or a 3D editor (explicit non-scope).
- Owned surface (the ONLY files you may create/modify):
  - `packages/solution-engine/**` (NEW package — see §4)
  - `backend/api/src/solution/**` (NEW server module — see §4.2)
  - `docs/productization-evidence/PROD-022/**` (evidence documents)
- Explicitly NOT yours: `packages/solution-contract/**` and
  `spec/solution-operation-contract.md` (the PROD-021 contract — IMPORT from
  `@aise/solution-contract`, never modify it; if the contract lacks something
  you need, STOP and report the conflict), `backend/api/src/reasoning/**`
  (a concurrent worker owns its new subdirectories), `backend/api/src/boq/**`
  and any BOQ-line grouping/navigation (that is PROD-025's surface — you
  compute raw operation/state QUANTITIES only, never BOQ lines),
  `backend/api/src/server.ts` and `backend/api/src/main.ts` (shared mount
  points — the Tech Lead wires your route factory at the integration
  station), `apps/**`, every other package/spec file, the root `bun.lock`
  (the Lead regenerates it).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond what the repo already uses (zod and the
  established workspace stack). The engine is PURE deterministic computation:
  no network, no clock reads, no randomness without fixed seeds, no
  environment-dependent output.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Another worker is concurrently
  executing a disjoint item (reasoning-side). Do NOT `git pull`, `git merge`
  or otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 36acb217dcd5142ab920f0ad860068f457c5879e   # public GitHub main (adapter wave complete: PROD-016 + 017 + 019 + 020 + 021 merged)
git rev-parse HEAD   # must print 36acb217dcd5142ab920f0ad860068f457c5879e
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-022/solution-engine
bun run verify
```

Baseline expectation: **3983 pass / 0 fail, VERIFY: PASS** (includes the
PROD-021 solution-contract suite and the PROD-017 apps/web suite). If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow — the governing record)
4. `spec/solution-operation-contract.md` (the PROD-021 contract your engine
   EXECUTES — object inventory, lifecycle, negotiation, trace identity)
5. `docs/interactive-engineering-solution-workflow.md` (the workflow your
   engine serves) and `docs/productization-work-orders.md` §PROD-022 (your
   work order — reproduced in §3)
6. `packages/solution-contract/` in FULL: `src/` (especially `intent.ts`,
   `operation.ts`, `state.ts`, `solution.ts`, `lifecycle.ts`,
   `negotiation.ts`, `validation.ts`, `identity.ts`, `invariants.ts`,
   `trace.ts`), `README.md`, and `fixtures/` (the deterministic
   building-operation corpus your engine must be able to apply)
7. `backend/api/src/execution/` as the exemplar backend module (router as
   pure transport adapter over a deterministic service — your
   `backend/api/src/solution/` module follows this pattern; also read its
   tests to see how route factories are tested without a live server)
8. `packages/adapter-contract/README.md` §negotiation (the honesty rules your
   engine's outcome states follow)

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-022 — Deterministic interactive solution engine
> **Owner:** CORE — **Depends on:** PROD-021
> **Protected surfaces:** `packages/*solution-engine*`, server solution
> execution/validation code, deterministic geometry tests.
> **Purpose:** Implement the server/domain engine that applies typed
> engineering operations to a proposed solution and produces reproducible
> proposed states.
> **Scope:**
> - implement operation application and state-delta computation;
> - implement deterministic geometry/topology/quantity calculations for the
>   initial building operation subset;
> - support undo/revision via new solution versions rather than destructive
>   mutation;
> - produce explicit unsupported/invalid/needs-input states;
> - expose deterministic tool endpoints for validate, step, inspect and
>   derived quantities;
> - preserve provenance and version lineage for every state transition.
> **Acceptance:**
> - identical inputs/operation sequences reproduce identical proposed states
>   and quantities;
> - authoritative Reality Graph is never mutated;
> - invalid or ambiguous operations fail closed;
> - operation effects and quantities are traceable to their parameters and
>   source state;
> - deterministic tests and negative/discrimination tests pass.
> **Evidence:** Engine fixtures + deterministic replay + mutation protection +
> negative/discrimination suite + building operation quantity tests.

## 4. Implementation shape (follow the repo's own conventions)

### 4.1 `packages/solution-engine/` — the deterministic core

A NEW workspace package mirroring the existing `packages/*` conventions
(versioned source of truth, tests under `src/*.test.ts`, README, package.json
scripts `test` + `gen:schemas` IF you ship schemas — schemas are NOT required
here; the wire objects already live in solution-contract). The package is
PURE DETERMINISTIC COMPUTATION over contract objects. Required content:

1. **Operation application + state-delta computation** —
   `applyOperation(input)` takes a `ProposedState` (or a solution-version
   baseline) plus a decoded `EngineeringOperationIntent` (use the contract's
   strict decoders) and returns a typed `OperationApplicationResult`:
   either `applied` (new version-pinned `ProposedState`, an explicit
   `OperationEffect`-shaped delta, derived quantities, and full lineage:
   parent version, applied intent id, deterministic transition identity) or
   one of the fail-closed outcomes `invalid` / `unsupported` /
   `needs-input` — each carrying machine-readable reasons. Gate execution
   through the contract's `negotiateOperationCapability` (capability profile
   → executable/unsupported/blocked with honest reasons); never invent a
   second negotiation semantics.
2. **Deterministic geometry/topology/quantity calculators** — for the
   initial building operation subset defined by the contract fixtures
   (excavation, backfill, block-wall, plaster, demolition and the other valid
   operation fixtures in `packages/solution-contract/fixtures/operation/`):
   compute lengths/areas/volumes/counts with EXPLICIT units (honor the
   intent's parameter units; convert deterministically, never silently),
   emitting quantities tagged with the contract's `QuantityDimension`
   vocabulary. Where an operation needs a quantity model the engineering
   model does not yet define, choose the simplest defensible deterministic
   formula, DOCUMENT it in the package README, and make it swappable behind
   an interface — but never nondeterministic.
3. **Undo/revision via new versions** — the engine NEVER mutates a state in
   place: every application/revision/undo produces a NEW `SolutionVersion`
   with parent linkage (append-only lineage); "undo" = a new version whose
   effect reverts the named prior transition, recorded as its own
   provenance-carrying transition. Destructive mutation of any historical
   version is structurally impossible (no API surface offers it).
4. **Mutation protection** — the engine consumes authoritative reality refs
   READ-ONLY (baseline resolution is an injected read-only resolver, cf. the
   intervention service's `BaselineResolver` pattern); it exposes NO write
   path to authoritative state. Prove this with a sabotage-style test: a
   hostile caller cannot reach any mutation surface (compile-time API
   inventory + runtime attempt).
5. **Deterministic replay** — `replay(baseline, intents[])` reproduces the
   exact same state chain, effects and quantities for the same input
   sequence: bit-identical canonical serialization (reuse the contract's
   codec/identity derivations, e.g. deterministic ids via the contract's
   identity helpers — do not invent id formats that disagree with
   `identity.ts`). Include an explicit replay-discrimination test: two runs
   with permuted irrelevant metadata (author name, timestamps in provenance
   metadata that do not participate in identity) still produce identical
   ENGINE-IDENTITIES while preserving their distinct provenance.
6. **Traceability** — every effect and quantity carries the intent id,
   parameter values + units, and source-state version it was computed from
   (the parameters the contract's trace objects need; PROD-025 will build BOQ
   lines on exactly this — do not build BOQ lines yourself).

### 4.2 `backend/api/src/solution/` — deterministic tool endpoints

A NEW backend module following the `execution/` exemplar: `model.ts` (request
/response shapes), `service.ts` (deterministic orchestration over the engine
package — thin), `router.ts` (a PURE route factory, transport adapter ONLY),
plus `*.test.ts` testing the route factory and service directly (no live
server boot, no server.ts edit). Endpoints (paths under `/v1/solutions/...`,
naming yours to define — document them in the router header comment):
`validate` (run the contract's validation checks over a state, returning a
`SolutionValidationSnapshot`-shaped result), `step` (apply one intent →
result + new version), `inspect` (state/version/lineage readback), and
`quantities` (derived quantities for a state/version). All handlers are
deterministic and fail closed with typed errors. The Tech Lead mounts the
factory in `server.ts` at the integration station — do NOT edit shared
server files; instead note the intended mount point in your evidence doc.

### 4.3 Fixtures + evidence

- Engine fixtures under `packages/solution-engine/fixtures/`: baseline
  building states + intent sequences (reuse/extend the contract's fixture
  corpus by REFERENCE where possible; your own fixtures hold expected
  states/quantities), valid + typed-invalid sequences, ambiguity cases.
- Negative/discrimination suite: invalid targets, missing parameters,
  unsupported operation types for the capability profile, unit
  mismatches, dimensionally inconsistent parameters — all fail closed with
  the right reason code.
- Evidence docs under `docs/productization-evidence/PROD-022/`:
  `engine-artifacts.md` (what exists, where, exact commands + expected
  output summary), `determinism.md` (replay proofs, identity stability,
  the quantity formulas + their documentation pointers),
  `mutation-protection.md` (the no-write-path proof + sabotage test
  summary), `quantity-tests.md` (building-operation quantity inventory:
  operation → formula → fixture → expected value).

### 4.4 Monorepo wiring

Workspace membership, package.json, tsconfig following the existing packages;
root `bun run verify` must pick up your tests automatically (confirm via the
gate in §5). The engine package may import `@aise/solution-contract` and
other `packages/*`; it must NOT import `apps/**`, `backend/**` or node
I/O in the core.

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3983 + N) pass / 0 fail** where N = your new tests (state N in
the report), typecheck + lint clean, boundary scan clean (packages may not
import apps/backend; backend/api/src/solution may import packages), final
line `VERIFY: PASS`. Your tests must be picked up by the root gate via the
workspace glob — confirm they are counted.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-022: deterministic interactive solution engine"
git diff $BASE..HEAD --stat
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's harvest
API cannot see. After committing, copy EVERY new/changed file (the complete
diff vs the base commit `$BASE` from §1) into the PROJECT directory
(the one containing package.json / src/ — the workspace root), preserving
repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery: remove `delivery/bun.lock` if staged.
The Lead regenerates the canonical lockfile at the integration station (your
`packages/solution-engine/package.json` declarations are what matters). Note
in your report that you excluded it. Also exclude any binary/build artifacts
(`node_modules`, dist output) — source only.

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-022 COMPLETION REPORT
base: public main @ 36acb217dcd5142ab920f0ad860068f457c5879e (adapter wave complete: PROD-016 + 017 + 019 + 020 + 021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3983 + N pass / 0 fail)
engine package layout: <top-level file list of packages/solution-engine/>
tool endpoints: <endpoint inventory (paths) + where the route factory lives>
acceptance:
- identical inputs reproduce identical states/quantities: <one-line proof incl. the replay test names>
- authoritative Reality Graph never mutated: <one-line proof incl. sabotage test>
- invalid/ambiguous operations fail closed: <one-line proof incl. reason-code inventory>
- effects/quantities traceable to parameters + source state: <one-line proof>
- negative/discrimination suite: <one-line summary>
quantity models: <operation → formula summary + where documented>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
