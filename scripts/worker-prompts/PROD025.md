# PROD-025 — Validate → solution BOQ generation → bidirectional traceability

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-025 (solution BOQ generation and bidirectional
  traceability). Do not start PROD-024/026 or any other item. Do not build an
  agent, a compiler, a UI or a 3D editor (explicit non-scope).
- Owned surface (the ONLY files you may create/modify):
  - `packages/solution-boq/**` (NEW package — see §4)
  - `backend/api/src/solution-boq/**` (NEW server module — see §4.2)
  - `docs/productization-evidence/PROD-025/**` (evidence documents)
- Explicitly NOT yours: `packages/solution-contract/**` and
  `spec/solution-operation-contract.md` (the PROD-021 contract is FROZEN —
  IMPORT from `@aise/solution-contract`, never modify it; if the contract
  lacks something you need, STOP and report the conflict),
  `packages/solution-engine/**` and `backend/api/src/solution/**` (PROD-022's
  engine — import and CALL it, never modify it), `backend/api/src/boq/**`
  (the SOURCE BOQ module — read/import its models to preserve
  source-vs-generated distinction, never modify it),
  `backend/api/src/reasoning/**` (PROD-023's), `backend/api/src/server.ts`
  and `backend/api/src/main.ts` (the Tech Lead wires route factories at the
  integration station), `apps/**`, every other package/spec file, the root
  `bun.lock` (the Lead regenerates it).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- The derivation is PURE DETERMINISTIC COMPUTATION over engine outputs: no
  network, no clock reads, no randomness. Identical solution versions and
  engine outputs produce identical BOQs.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout deb46cb29948f348079c803c1e81cb5831c62c8c   # public GitHub main (adapter wave + PROD-018+021+022+023 merged)
git rev-parse HEAD   # must print deb46cb29948f348079c803c1e81cb5831c62c8c
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-025/solution-boq
bun run verify
```

Baseline expectation: **4323 pass / 0 fail, VERIFY: PASS** (includes the
PROD-022 solution-engine suite). If the baseline is red, STOP and report (do
not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow — the governing record)
4. `spec/solution-operation-contract.md` (the PROD-021 contract —
   especially the bidirectional BOQ trace identity rules and the
   solution-validation snapshot objects)
5. `docs/interactive-engineering-solution-workflow.md` (the workflow your
   derivation serves) and `docs/productization-work-orders.md` §PROD-025
   (your work order — reproduced in §3)
6. `packages/solution-contract/` in FULL — especially `src/trace.ts` (the
   `SolutionBoqLineTrace` / `OperationContribution` objects you will
   RESOLVE, not redefine), `src/validation.ts` (the
   `SolutionValidationSnapshot` your BOQ generation attaches),
   `src/solution.ts` (Solution/SolutionVersion identity), `src/operation.ts`
   (quantity dimensions), plus the trace fixtures
7. `packages/solution-engine/` in FULL (PROD-022's engine — the
   deterministic operation application, state deltas, derived quantities and
   version lineage your derivation consumes; its README documents the
   quantity models)
8. `backend/api/src/boq/` (the SOURCE BOQ module — the existing BOQ line
   model, sections, units and normalization your generated BOQ must remain
   DISTINCT from; read `model.ts`, `sections.ts`, `service.ts`)
9. `backend/api/src/execution/` (the backend module exemplar your
   `backend/api/src/solution-boq/` follows)

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-025 — Validate → solution BOQ generation → bidirectional traceability
> **Owner:** QS/CORE — **Depends on:** PROD-021, PROD-022
> **Protected surfaces:** solution BOQ derivation code, BOQ trace schemas/
> tests, solution/BOQ service tests.
> **Purpose:** Turn a validated interactive solution into an auditable BOQ
> and make the BOQ an explorable explanation of the virtual
> construction/repair process.
> **Scope:**
> - compute solution quantities from deterministic operation/state deltas;
> - group operations into meaningful building BOQ lines with units,
>   materials/activities and calculation methods;
> - attach validation snapshot and solution/version identity;
> - preserve uncertainty and unresolved assumptions;
> - implement BOQ-line → operation/geometry navigation and operation →
>   BOQ-line reverse navigation;
> - preserve the distinction between source BOQ and solution-generated BOQ.
> **Acceptance:** Clicking `Validate` on a supported solution yields a
> validation snapshot. Clicking `Generate BOQ` creates a versioned derived
> BOQ from that snapshot. Every line can navigate to the corresponding
> solution step/geometry and every operation can reveal its
> affected/generated BOQ lines.
> **Evidence:** Building fixture BOQ + calculation trace + validation
> snapshot + bidirectional navigation trace + source-vs-generated BOQ
> non-overwrite tests.

## 4. Implementation shape (follow the repo's own conventions)

### 4.1 `packages/solution-boq/` — the deterministic derivation

A NEW workspace package mirroring the `packages/*` conventions. PURE
DETERMINISTIC COMPUTATION over contract objects + engine outputs. Required
content:

1. **Quantity derivation from operation/state deltas** —
   `deriveSolutionBoq(input)`: takes a solution version's operation
   applications (the engine's applied results: effects + derived quantities
   + lineage) and computes the solution BOQ. Quantities come FROM THE
   ENGINE's outputs (never recomputed independently — the engine is the
   single quantity authority); your derivation GROUPS and LABELS them.
2. **Building BOQ lines** — group operations into meaningful lines:
   building element/activity (aligned with the contract's building-element
   taxonomy extension), unit (explicit, honoring the engine's quantity
   units), material/activity description, and the CALCULATION METHOD (the
   documented formula reference from the engine's quantity models — cite
   it, never restate it as your own authority). Line identity is
   deterministic and version-pinned (reuse the contract's identity
   derivations).
3. **Validation snapshot + version attachment** — a generated BOQ carries:
   the `SolutionValidationSnapshot` identity it was generated from, the
   solution id + version, the derivation time is ABSENT (determinism — no
   clock), and a deterministic derivation identity. Generating from the
   same snapshot twice yields the IDENTICAL BOQ (test this).
4. **Uncertainty + unresolved assumptions** — where the engine's outputs or
   the validation snapshot carry uncertainty or unresolved assumptions,
   they propagate into the BOQ lines explicitly (never silently dropped);
   a line's assumption inventory is part of its identity-stable payload.
5. **Bidirectional navigation** — resolve via the contract's
   `SolutionBoqLineTrace` objects: BOQ-line → contributing operations
   (with the operation → geometry target refs), and operation →
   generated/modified/removed BOQ lines (the `OperationContribution`
   kinds). Round-trip resolution must be proven (line → ops → lines
   recovers the same set; version-pinned).
6. **Source vs generated BOQ non-overwrite** — the generated BOQ is a NEW
   derived artifact referencing the source BOQ (if any) by identity; there
   is NO code path that writes back into the source BOQ store (sabotage
   test proving it). The distinction is typed, not just documented.

### 4.2 `backend/api/src/solution-boq/` — service + transport

A NEW backend module following the `execution/` exemplar: `model.ts`,
`service.ts` (thin orchestration over the package), `router.ts` (PURE route
factory, not mounted — the Lead wires it), `*.test.ts`. Endpoints under
`/v1/solutions/...` + `/boq` (naming yours — document in the router header):
generate-from-snapshot (deterministic), get BOQ (versioned readback),
line → operations navigation, operation → lines reverse navigation.
The `Validate` → snapshot flow belongs to the engine's validate endpoint
(PROD-022); your generate endpoint CONSUMES a snapshot identity.

### 4.3 Fixtures + evidence

- Fixtures under `packages/solution-boq/fixtures/`: building solution
  fixtures (operation sequences over the engine's fixture operations) with
  expected BOQs (lines, units, methods), calculation traces, uncertainty
  cases, version-pair cases (same solution, two versions → two BOQs with
  correct delta lineage).
- Evidence docs under `docs/productization-evidence/PROD-025/`:
  `derivation-artifacts.md` (what exists, where, commands + expected
  output), `building-fixture-boq.md` (the fixture BOQ inventory + the
  calculation trace for every line), `bidirectional-navigation.md`
  (round-trip proofs, version pinning proofs),
  `source-vs-generated.md` (the non-overwrite proof + typed distinction).

### 4.4 Monorepo wiring

Workspace membership, package.json, tsconfig following the existing
packages; root `bun run verify` picks up your tests automatically. The
package may import `@aise/solution-contract` and `@aise/solution-engine`;
it must NOT import `apps/**` or do I/O in the core.

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(4323 + N) pass / 0 fail** where N = your new tests (state
N in the report), typecheck + lint clean, boundary scan clean, final line
`VERIFY: PASS`. Your tests must be picked up by the root gate via the
workspace glob — confirm they are counted.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-025: solution BOQ generation and bidirectional traceability"
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

EXCLUDE `bun.lock` from the delivery if it appears (the Lead regenerates the
canonical lockfile). Also exclude binary/build artifacts — source only.

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-025 COMPLETION REPORT
base: public main @ deb46cb29948f348079c803c1e81cb5831c62c8c (adapter wave + PROD-018 + 021 + 022 + 023 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 4323 + N pass / 0 fail)
package layout: <top-level file list of packages/solution-boq/>
endpoints: <endpoint inventory + where the route factory lives>
acceptance:
- validate → snapshot → generate BOQ (versioned, deterministic): <one-line proof>
- every line → solution step/geometry: <one-line proof incl. round-trip test names>
- every operation → affected/generated lines: <one-line proof>
- uncertainty/assumptions preserved: <one-line proof>
- source vs generated BOQ distinction (no overwrite): <one-line proof incl. sabotage test>
- quantities from engine outputs only (no independent recomputation): <one-line proof>
calculation methods: <line → method → engine formula reference inventory>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
