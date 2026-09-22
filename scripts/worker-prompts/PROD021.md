# PROD-021 — Interactive solution graph and engineering operation contract

You are a senior TypeScript engineer executing ONE well-specified work item in the
AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-021 (the interactive solution graph and engineering
  operation contract). Do not start PROD-022/023/024/025 or any other item.
  Do not build a 3D editor, an agent, or any platform UI (explicit non-scope).
- Owned surface (the ONLY files you may create/modify):
  - `packages/solution-contract/**` (NEW package — see §4)
  - `spec/solution-operation-contract.md` (NEW spec file, explicitly assigned
    to you by this packet)
  - `docs/productization-evidence/PROD-021/**` (evidence documents)
- Explicitly NOT yours: `docs/productization-state.json` (Tech-Lead-owned
  finalize), `apps/**`, `backend/**`, `packages/shared-contracts/**`,
  `packages/adapter-contract/**`, `packages/engineering-model/**` (you may
  IMPORT from them, never modify them), every other spec file.
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond what the repo already uses (zod /
  zod-to-json-schema / ajv are the established contract stack).
- Never weaken, skip or delete an existing test.

## 1. Setup — base + overlay (the shared contract is NOT on GitHub main yet)

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 1068ebbbb5eb9ba9335b8d5a77e28fb04aeb74d2   # public GitHub main
git rev-parse HEAD   # must print 1068ebbbb5eb9ba9335b8d5a77e28fb04aeb74d2

# Apply the Lead's overlay (FIX-001 server fix + the PROD-016 adapter contract
# that merged at the integration station):
curl -L -o /tmp/overlay.patch https://filebin.net/aise-overlay-1789641605/aise-overlay-v2.patch
echo "f1147c36eb17439258acb686c7459308237964b56d293b43587e91dbd5c152f0  /tmp/overlay.patch" | sha256sum -c -
# must print: /tmp/overlay.patch: OK   (STOP if it does not)
git apply --check /tmp/overlay.patch && git apply /tmp/overlay.patch
git add -A && git -c user.name="worker" -c user.email="worker@aise" commit -m "base: Lead overlay v2 (FIX-001 + PROD-016 @ aa4f899)"
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-021/solution-contract
bun run verify
```

Baseline expectation: **3574 pass / 0 fail, VERIFY: PASS**. If the baseline is
red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants; note the
   technology-substitution boundary section — the substitution contract lives
   HERE, not in a standalone file)
3. `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow — THE governing record for this
   item)
4. `spec/governance/architecture-change-record-004.md` and `-006.md` (the
   surrounding baselines: client adapters over one core; three-layer hardening
   — your contract must not foreclose either)
5. `docs/interactive-engineering-solution-workflow.md` and
   `docs/product-journey-simulation.md` (the solution workflow design and the
   journey simulation your contract must be able to express)
6. `spec/agent-ownership.md` and `spec/development-protocol.md`
7. `docs/productization-work-orders.md` §PROD-021 (your exact work order —
   reproduced in §3 below for reference)
8. `packages/shared-contracts/` and `packages/adapter-contract/` in full (the
   two established contract-package patterns you will follow — versioned
   TypeScript source of truth, generated JSON Schemas, fixtures, tests,
   schema-generation script)
9. `spec/client-adapter-contract.md` (the PROD-016 contract as the
   versioning/negotiation exemplar; your operation-capability negotiation
   follows the same honesty rules)
10. The intervention model lineage this builds on (read-only): the AISE-026
    intervention scenario/state model, the AISE-027 synchronized 3D/2D/BOQ
    intervention viewer semantics, and the AISE-028 intervention
    quantities/cost impacts — locate them via
    `spec/work-items.md` rows AISE-026/027/028 and the
    `packages/engineering-model/` surfaces they delivered

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-021 — Interactive solution graph and engineering operation contract
> **Owner:** SHARED — **Depends on:** AISE-026, AISE-027, AISE-028, PROD-016
> **Architecture:** ACR-005
> **Protected surfaces:** `packages/*` solution contracts/fixtures, relevant
> server/domain contracts, `spec/*` only as explicitly assigned.
> **Purpose:** Create the stable, domain-extensible contract for the new
> interactive engineering solution workflow without implementing a
> platform-specific editor or agent.
> **Scope:**
> - define versioned `Solution`, `SolutionVersion`, `EngineeringOperation`,
>   `ProposedState`, `OperationDependency`, `OperationTarget`,
>   `OperationEffect`, `SolutionValidationSnapshot` and solution-to-BOQ trace
>   objects;
> - define typed operation intents with explicit units, spatial targets,
>   parameters and provenance;
> - define lifecycle/version/branch semantics for draft, validated,
>   superseded and abandoned proposals;
> - define operation capability negotiation and unsupported-operation states;
> - define bidirectional solution-step ↔ generated-BOQ-line identity
>   contracts;
> - create deterministic fixtures for initial building operations.
> **Explicit non-scope:** No 3D editor, no agent implementation, no direct
> mutation of authoritative reality, no payment/cost-provider integration, and
> no support for non-building verticals in the first implementation.
> **Acceptance:**
> - same operation intent can be produced by direct manipulation or an agent;
> - every operation has deterministic identity, parameters, units, target,
>   provenance and version context;
> - proposed state remains separate from observed reality;
> - contract is extensible beyond buildings without encoding building-specific
>   authority semantics into clients;
> - BOQ trace objects are bidirectional and version-pinned.
> **Evidence:** Schemas + fixtures + serialization tests + authority/negative
> tests + operation/BOQ traceability fixtures.

## 4. Implementation shape (follow the repo's own conventions)

Create a NEW package `packages/solution-contract/` mirroring the
`packages/adapter-contract/` pattern (versioned TypeScript source of truth +
generated JSON Schemas + fixtures + tests + a schema-generation script). The
package is DATA + CONTRACT LOGIC ONLY (shapes, negotiation, trace identity,
validation snapshots) — no I/O, no server behavior, no UI, no 3D. Required
content, mapped to the acceptance criteria:

1. **Versioned solution objects** — zod schemas as source of truth for
   `Solution`, `SolutionVersion`, `EngineeringOperation`, `ProposedState`,
   `OperationDependency`, `OperationTarget`, `OperationEffect`,
   `SolutionValidationSnapshot`, and the solution-to-BOQ trace objects; a
   contracts version constant + version test; generated JSON Schemas in
   `schemas/` with a manifest.
2. **Typed operation intents** — every intent carries deterministic identity,
   explicit units, spatial target, parameters and provenance; the SAME intent
   is constructible by direct manipulation or an agent (one constructor
   surface, two provenance origins — prove both in fixtures).
3. **Lifecycle/version/branch semantics** — draft, validated, superseded and
   abandoned proposal states with version-pinned transitions; branch
   semantics that keep proposed state SEPARATE from observed reality (the
   package exposes no mutation path for authoritative state — document the
   invariant in the package README).
4. **Operation capability negotiation** — a negotiation function mapping an
   operation intent + capability profile to executable / unsupported /
   blocked outcomes with honest reasons (follow the adapter-contract's
   negotiation honesty rules); unsupported-operation states are explicit,
   never silent.
5. **Bidirectional BOQ trace contracts** — solution-step ↔ BOQ-line identity
   objects that resolve in BOTH directions and are version-pinned to the
   solution version that produced them; traceability fixtures prove
   round-trip resolution.
6. **Deterministic fixtures for initial building operations** — a fixture set
   covering the initial building operations (site preparation, foundation,
   structure, enclosure, services, finishes — as the engineering model
   defines them), valid + typed-invalid per object family.
7. **Domain extensibility without client authority** — the vertical
   (building) specifics live behind a domain descriptor; nothing
   building-specific is encoded into client-facing types as authority;
   document the extension path for future verticals.
8. **Wire the package into the monorepo** — workspace membership, package.json
   scripts (`test`, `gen:schemas`), tsconfig following the existing packages;
   the root `bun run verify` must pick up the package's tests automatically
   (confirm via the gate in §5).

Author `spec/solution-operation-contract.md` as the human-readable contract:
object inventory, lifecycle state machine, negotiation rules, BOQ trace
identity rules, extensibility path, and the package as the checkable artifact
set (version, path, commands).

Evidence documents under `docs/productization-evidence/PROD-021/`:
- `contract-artifacts.md` — what exists, where, how to regenerate schemas and
  run the suites (exact commands + expected output summary);
- `operation-fixtures.md` — the deterministic building-operation fixture
  inventory (intents, units, targets, provenance, lifecycle coverage) and the
  direct-manipulation vs agent origin proof;
- `boq-trace-conformance.md` — bidirectional trace resolution proofs,
  version-pinning proofs, authority/negative test summary.

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3574 + N) pass / 0 fail** where N = your new tests (state N in the
report), typecheck + lint clean, boundary scan clean (the scanner covers
`packages/` — your package must respect the zone rules: no imports from
`apps/`, `backend/`, or root scripts), final line `VERIFY: PASS`.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-021: interactive solution graph and engineering operation contract"
git diff $BASE..HEAD --stat
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's harvest
API cannot see. After committing, copy EVERY new/changed file (the complete
diff vs the overlay base commit `$BASE` from §1) into the PROJECT directory
(the one containing package.json / src/ — the workspace root), preserving
repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "overlay-base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-021 COMPLETION REPORT
base: 1068ebbbb5eb9ba9335b8d5a77e28fb04aeb74d2 + overlay (overlay-base $BASE)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3574 + N pass / 0 fail)
contract version: <version constant you shipped>
package layout: <top-level file list of packages/solution-contract/>
acceptance:
- same intent via direct manipulation or agent: <one-line proof incl. both provenance origins>
- deterministic identity/parameters/units/target/provenance/version: <one-line proof>
- proposed state separate from observed reality: <one-line proof>
- extensible beyond buildings without client authority: <one-line proof>
- BOQ traces bidirectional + version-pinned: <one-line proof>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
