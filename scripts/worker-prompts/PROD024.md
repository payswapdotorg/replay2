# PROD-024 — Interactive building solution workspace (direct manipulation + agent)

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-024 (the interactive solution workspace). Do not start
  PROD-025/026 or any other item. Do not build a new engine, a new compiler,
  a BOQ generator or a second operation semantics (explicit non-scope — you
  CONSUME the engine and compiler seams, never re-implement them).
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/solution/**` (NEW module — the interactive solution
    workspace; this path is reserved for you, see §4)
  - `docs/productization-evidence/PROD-024/**` (evidence documents)
- Explicitly NOT yours:
  - everything else under `apps/web/src/**` (App.tsx, AppShell.tsx, shell/,
    boqlens/, viewer/, workspace/, api.ts, adapter-binding.ts, …) — a
    concurrent worker owns the composition lane there (PROD-018); the Tech
    Lead wires your workspace's mount point into the app shell at the
    integration station. Your module MUST be mountable through a single
    exported entry (see §4.1) without edits outside your path.
  - `packages/solution-engine/**` and `backend/api/src/solution/**`
    (PROD-022's engine — IMPORT and CALL, never modify; if the engine lacks
    something you need, STOP and report the conflict)
  - `backend/api/src/reasoning/**` (PROD-023's compiler — same rule)
  - `backend/api/src/boq/**` (a future item's surface — read-only)
  - `packages/adapter-contract/**`, `packages/solution-contract/**` and
    `spec/**` (frozen contracts — import only)
  - `apps/android/**` and `apps/desktop/**` (sibling adapters), `tools/**`,
    the root `bun.lock` (the Lead regenerates it)
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond the repo's established stack (React 19,
  the workspace packages, the existing SVG/projection viewer patterns —
  no three.js, no WebGL mandate: the house viewer stack is SVG/projection
  based; a richer canvas layer MAY be built inside your path with zero new
  dependencies, and the accessible fallback is first-class, not an afterthought).
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull`, `git merge` or
  otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout deb46cb29948f348079c803c1e81cb5831c62c8c   # public GitHub main (adapter wave + PROD-018 + 022 + 023 merged)
git rev-parse HEAD   # must print deb46cb29948f348079c803c1e81cb5831c62c8c
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-024/solution-workspace
bun run verify
```

Baseline expectation: **4323 pass / 0 fail, VERIFY: PASS** (includes
the solution-engine suite and the reasoning-solution suite). If the baseline
is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow — the governing record)
4. `spec/solution-operation-contract.md` (the PROD-021 contract: object
   inventory, lifecycle, negotiation, trace identity — your workspace's
   every manipulation must resolve to THESE typed operations)
5. `docs/interactive-engineering-solution-workflow.md` (the workflow you
   are making interactive) and `docs/productization-work-orders.md` §PROD-024
   (your work order — reproduced in §3)
6. `packages/solution-engine/README.md` and its `src/` exports (the
   deterministic engine your workspace drives — operation application,
   state stepping, replay, quantity computation surfaces)
7. `backend/api/src/solution/` (the engine's server tool endpoints — the
   service seam your workspace calls) and `backend/api/src/reasoning/solution/`
   (the PROD-023 compiler — the SAME operation semantics the agent path uses)
8. `apps/web/src/viewer/` (svg.ts, projection.ts, render.ts — the house
   SVG/projection rendering patterns you extend inside your own path) and
   `apps/web/src/boqlens/` + `apps/web/src/workspace/` (UI conventions:
   panes, model fixtures, error surfaces)
9. `docs/productization-evidence/PROD-017/**` (browser-adapter evidence —
   the recording/conformance conventions your evidence follows) and
   `packages/adapter-contract/src/` (client adapter contract — dual-origin
   intents, PROPOSED vs OBSERVED cognitive separation, version locking)

## 3. Work order (reproduced verbatim from docs/productization-work-orders.md)

**Owner:** WEB/3D · **Depends on:** PROD-017, PROD-022, PROD-023 ·
**Protected surface:** solution-specific browser UI under `apps/web/**`; may
not alter generic adapter contract.

**Purpose** — Deliver the intuitive interactive environment in which the user
can inspect the reconstructed building, manipulate proposed work, step
layer-by-layer and see the engineering consequences.

**Scope**
- interactive 3D/2D navigation around the current/proposed building;
- direct manipulation controls mapped to typed solution operations;
- timeline/step navigation through operation states;
- isolate/inspect affected geometry and operation details;
- embedded agent interaction for the same operation system;
- clear observed vs proposed visual state distinction;
- responsive synchronization between geometry, operation list and selected
  BOQ lines once available;
- accessible non-3D fallback for core operation inspection.

**Acceptance** — A user who understands the real-world task can create or
modify a building solution without learning AISE internals; every
manipulation resolves to the same deterministic operation semantics used by
the agent; proposed reality cannot overwrite authoritative reality.

**Evidence** — Browser interactive-solution recording + operation trace +
adapter-conformance result + accessibility/fallback trace + mutation-
protection evidence.

## 4. Build specification

### 4.1 Module shape and mount contract

`apps/web/src/solution/` is a self-contained workspace module:

- export a single `SolutionWorkspace` React component (plus its prop types)
  from `apps/web/src/solution/index.ts` — the Lead mounts it at the
  integration station (a route/pane in the app shell); do NOT edit any file
  outside your path to mount it yourself;
- the component receives the case/solution context (project id, case id,
  current solution id, agent session handle) via props; no global singletons;
- keep the module's internal structure mirrors of the house patterns:
  `model.ts` (state/derivation), `operations.ts` (manipulation → typed
  operation mapping), `viewer/` (SVG/projection rendering), `panes/`
  (operation list, timeline, detail inspector), `agent/` (embedded agent
  interaction), `fallback/` (non-3D accessible inspection), `*.test.ts`
  co-located.

### 4.2 One operation semantics (the convergence law)

- EVERY user manipulation (direct manipulation control, timeline action,
  fallback-path action) MUST produce the same typed operation objects the
  agent path produces — via `@aise/solution-contract` operation/intent types
  and the engine's application/step services (`packages/solution-engine`).
  NO client-local operation semantics, NO optimistic local geometry that
  diverges from engine output. The UI renders engine-computed states only.
- The embedded agent panel (§4.4) and the direct-manipulation controls
  share one operation submission path. The trace identity (contract
  `trace.ts`) is the single join key across: manipulation, agent turn,
  operation list, timeline step and (when available) BOQ line.

### 4.3 Observed vs proposed; mutation protection

- The workspace renders OBSERVED (authoritative) state and PROPOSED state
  as visually and semantically distinct layers (the PROD-021 cognitive-
  separation doctrine; follow `packages/adapter-contract` version locking).
- PROPOSED can never overwrite OBSERVED: every mutation flows through the
  engine's negotiation/lifecycle (draft → proposed → accepted per the
  contract); the UI must make non-destructiveness inspectable (an undo/step
  back through the timeline always restores the exact prior engine state —
  deterministic replay, not a client-side snapshot hack).
- Demonstrate with tests: attempt-to-overwrite-authoritative operations are
  rejected by the engine and the UI surfaces the refusal honestly.

### 4.4 Direct manipulation, timeline, isolate/inspect

- Direct manipulation: select an object/region in the viewer → the available
  operations (from the contract's object inventory) are offered as labeled,
  real-world-worded actions (no AISE-internal jargon); executing one creates
  the typed operation, submits it through the engine service, and renders
  the resulting state.
- Timeline/step: every state the solution passes through is a steppable
  engine state (forward/back/jump); the timeline shows operation identity +
  consequence (quantities changed, objects affected) from engine output.
- Isolate/inspect: selecting an operation (list, timeline, or geometry)
  isolates the affected geometry in the viewer and opens a detail pane:
  operation record, intent provenance (direct manipulation or agent turn),
  state delta, quantities. Read-only inspection everywhere; revision creates
  a NEW operation (never edits history in place).

### 4.5 Embedded agent interaction

- An agent panel inside the workspace where the user states an intent in
  real-world language; the workspace routes it through the PROD-023
  compiler seam (the same NL → EngineeringOperationIntent path), previews
  the resulting typed operations for confirmation, then applies them through
  the same engine path as direct manipulation (§4.2).
- Refusals/clarifications from the compiler surface verbatim — the workspace
  never invents operations the compiler did not produce.

### 4.6 BOQ synchronization (guarded)

- When BOQ-line data is available in the case context (source BOQ or a
  solution-generated BOQ if present), selecting a BOQ line highlights the
  corresponding operations/geometry and vice versa, keyed by the contract's
  trace identity. Structure the seam behind a small interface so the future
  BOQ item can supply the data without workspace edits; if no BOQ data is
  present the workspace degrades gracefully (the pane simply reports none
  available — never a crash, never fabricated lines).

### 4.7 Accessible non-3D fallback (first-class)

- A complete keyboard-navigable, screen-reader-labeled operation inspection
  path (operation list + detail pane + timeline) that exercises the SAME
  semantics with zero reliance on the spatial viewer; aria roles/labels
  per the house a11y conventions; WCAG AA contrast in your styles.
- The fallback is not a stub: a user must be able to inspect and revise a
  full solution through it.

## 5. Testing and acceptance gates

- Co-located unit tests for: manipulation → operation mapping (every control
  produces exactly the typed operation the test expects), timeline stepping
  determinism (step forward/back/jump equals engine replay), observed-vs-
  proposed layering, refusal surfacing, BOQ-sync guard behavior, fallback
  completeness.
- A golden-journey test: a scripted user session (inspect → direct
  manipulation → agent turn → step back → revise → confirm) producing an
  operation trace that is byte-stable across two runs (determinism proof).
- Mutation-protection tests per §4.3.
- `bun run verify` at your base must remain green plus your new tests; run
  `bun run verify` and report the exact totals (they must be
  baseline + your new tests, 0 fail).
- Typecheck and lint clean (`bun run typecheck`, `bun run lint` — use the
  repo's actual script names from package.json).

## 6. Delivery and completion report

- Branch: `prod-024/solution-workspace`. Commit your work with a message
  beginning `PROD-024:`.
- Evidence under `docs/productization-evidence/PROD-024/`:
  - `interactive-solution-recording.md` (a described walkthrough with state
    snapshots of the golden journey — paths and outcomes, no source pastes)
  - `operation-trace.md` (the golden journey's typed operation trace with
    trace identities)
  - `mutation-protection-evidence.md`
  - `accessibility-fallback-trace.md`
- Write your delivery manifest as `DELIVERY.txt` in the repo root of your
  branch: every file you created/modified, one path per line.
- Completion report (final message): begin with the exact line
  `PROD-024 COMPLETION REPORT` and include:
  - your delivery commit sha (40 hex) and the base sha it diffs against;
  - the diffstat summary line (files changed, insertions, deletions);
  - `VERIFY: PASS|FAIL` with exact test totals (yours + baseline math);
  - the acceptance statement per §3 (each scope bullet: met / honestly
    not met and why);
  - anything the Tech Lead must wire at the integration station
    (your mount point, props contract).
- Do not paste source code in the report — paths, counts and the verify
  output only.
