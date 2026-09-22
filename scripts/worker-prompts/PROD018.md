# PROD-018 — Competitive-parity and differentiation hardening (composition)

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-018 (competitive-parity composition). Do not start
  PROD-022/023/024/025 or any other item (they are other workers' concurrent
  or future lanes).
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/**` EXCEPT `apps/web/src/solution/**` (that path is
    RESERVED for the future PROD-024 interactive-solution workspace — do not
    create or occupy it; your composition work lives in the existing app
    surfaces plus your own new subdirectories with parity/composition-scoped
    names)
  - `tools/competitive-parity/**` (NEW — the simulation re-run harness and
    cross-adapter semantic-equivalence checks)
  - `docs/productization-evidence/PROD-018/**` (evidence documents,
    including the competitive-simulation re-run record)
- Explicitly NOT yours: `apps/web/src/solution/**` (reserved, see above),
  `apps/android/**` and `apps/desktop/**` (the sibling adapters — read,
  import their committed conformance artifacts and profiles, never modify
  them), `packages/**` (import only), `backend/**`, `spec/**`,
  `docs/competitor-simulation-2026-09-16.md` (the ORIGINAL simulation is a
  frozen input — your re-run record goes under your evidence directory;
  never rewrite history), `docs/productization-state.json`, the root
  `bun.lock` (the Lead regenerates it).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond the repo's established stack. No second
  authority: composition must route through existing contracts/services; no
  feature may introduce provider lock-in.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 36acb217dcd5142ab920f0ad860068f457c5879e   # public GitHub main (adapter wave complete: PROD-016+017+019+020+021 merged)
git rev-parse HEAD   # must print 36acb217dcd5142ab920f0ad860068f457c5879e
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-018/competitive-parity
bun run verify
```

Baseline expectation: **3983 pass / 0 fail, VERIFY: PASS** (includes the
PROD-017 web adapter suite and the PROD-020 desktop adapter suite). If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants — the no-second-
   authority rule your composition must preserve)
3. `spec/governance/architecture-change-record-004.md` (client adapters over
   one core) and `spec/client-adapter-contract.md` (what all three adapters
   conform to)
4. `docs/competitor-simulation-2026-09-16.md` IN FULL (the frozen
   competitive simulation — the journeys and gaps your re-run measures
   against) and `docs/layered-competitive-stress-test-2026-09-16.md` (the
   layered stress test framing)
5. `docs/productization-work-orders.md` §PROD-018 (your work order —
   reproduced in §3)
6. `docs/interactive-engineering-solution-workflow.md` (the journey your
   composition serves)
7. `apps/web/src/` in full — especially `app/task-first.tsx`,
   `app/task-flow.ts`, `app/router.ts`, `app/surfaces/`, `boqlens/`,
   `workspace/`, `viewer/`, `shell/` (the composition host you build on)
8. The sibling adapters' committed artifacts (read-only):
   `apps/desktop/src/adapter/profile.ts` + `conformance.test.ts`,
   the Android adapter's conformance artifacts under `apps/android/**`
   (locate its profile/fixtures the same way), and
   `packages/adapter-contract/` (the shared conformance fixture corpus and
   the C0-C9 checks)
9. `docs/productization-evidence/PROD-017/`, `PROD-019/`, `PROD-020/`
   (what each adapter proved — your equivalence checks compose THESE
   results)

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-018 — Competitive-parity and differentiation hardening
> **Owner:** SHARED — **Depends on:** PROD-012, PROD-017, PROD-019, PROD-020
> **Purpose:** Close product gaps revealed by the 2026 competitor simulation
> without cloning incumbents or weakening AISE's architectural boundary.
> **Required capability set:**
> 1. Smartphone/field capture is low-friction, resumable and offline-capable.
> 2. Reality is spatially contextualized to the project.
> 3. Quantities are editable/reviewable and source-linked.
> 4. Drawings/documents are revision-aware and interoperable with incumbents.
> 5. Issues carry rich visual/spatial context and actionable next steps.
> 6. AI actions are bounded and inspectable, not chat-only.
> 7. Plan-vs-reality and before/after are easy to access.
> 8. Intervention simulation connects geometry, cost and execution.
> 9. Post-work evidence and outcome comparison are a first-class workflow.
> 10. Uncertainty, provenance and human verification remain visible at
>    consequential boundaries.
> **Acceptance:**
> - competitive simulation in `docs/competitor-simulation-2026-09-16.md` is
>   re-run against the composed product;
> - every required capability is either implemented or has an explicit
>   governed exception with rationale;
> - AISE's evidence → understanding → intervention → execution → outcome
>   continuity remains visible;
> - no feature introduces a second authority or provider lock-in;
> - browser/mobile/desktop continue to produce semantically equivalent
>   engineering results.
> **Evidence:** Competitive journey matrix + capability traceability + final
> golden journey replay + cross-adapter semantic equivalence checks.

## 4. Implementation shape (follow the repo's own conventions)

This is a COMPOSITION item: the platform capabilities largely exist (backend
modules, adapters, contracts); your job is to (a) compose them into the
parity-grade product journey in the web app, (b) re-run the competitive
simulation against that composed product, and (c) prove cross-adapter
semantic equivalence. Where a capability is genuinely missing, you do NOT
build a new platform: you mark it as a GOVERNED EXCEPTION with rationale and
the owning work item (see §4.3).

### 4.1 Composition UX (`apps/web/src/**`, existing surfaces + your new
composition-scoped subdirectories)

Wire the journeys the competitor simulation showed users expect (all routed
through EXISTING contracts/services — no new authority):

1. **Cross-links**: capture → issue → BOQ navigation (an issue opens its
   evidence and its affected BOQ lines; a BOQ line opens its evidence and
   issues; a capture opens the issues+quantities derived from it).
2. **Action-label / terminology normalization**: the four canonical actions
   — Capture, Investigate, Build solution, Review outcome — consistently
   label entry points, navigation and next-step suggestions across the app
   (unify the current mixed vocabulary; keep AISE's differentiated language
   where it exists deliberately).
3. **Plan-vs-reality and before/after**: easy-access navigation between the
   plan (reconstructed/as-designed) view and reality (captured) view per
   project surface, and before/after comparison for executed work.
4. **Outcome discovery**: post-work evidence and outcome comparison as a
   first-class surface (find outcomes by case/intervention/evidence).
5. **BOQ Lens → action bridges**: the existing boqlens surface gains action
   bridges — from a quantity line to its evidence, case and next actions.
6. **Task-first composition + evidence-gap next actions**: the task-first
   shell (PROD-017) gains composed journeys that chain adapter tasks with
   honest next-action suggestions when evidence is missing (explicit
   blocked/gap states — extend the adapter contract's honest-states
   doctrine to the composition layer).
7. **Uncertainty/provenance visibility**: at consequential boundaries
   (quantities, validations, outcomes) the UI surfaces uncertainty and
   provenance labels from the existing contracts — never invents them.

Each composition surface ships with journey-level tests (the repo's
`*.test.tsx` / `*.test.ts` patterns) exercising the REAL task-flow and
adapter seams (no mocked-away core).

### 4.2 Cross-adapter semantic equivalence (`tools/competitive-parity/**`)

A NEW harness (bun-runnable, wired into the root verify via its own tests)
that proves browser/mobile/desktop produce semantically equivalent
engineering results:

- load the committed adapter-contract fixture corpus + each adapter's
  committed conformance binding artifacts (profiles, conformance results,
  evidence docs — all in-repo, no live devices needed);
- for representative fixture flows, assert the three adapters' decodable
  outputs (task intents, presented fields, honest states, negotiation
  results) are semantically equivalent per the shared contract's equality
  semantics (canonical forms, not incidental formatting);
- emit a machine-readable equivalence report (committed as a fixture of the
  harness) + a human-readable summary in your evidence docs.

### 4.3 Capability traceability matrix (the acceptance core)

Under `docs/productization-evidence/PROD-018/`:

- `competitive-simulation-rerun.md` — the 2026-09-16 simulation re-run
  against the composed product: each simulated competitor journey mapped to
  the AISE journey that serves it (with the concrete UI route + flow), the
  gaps that remain, and the differentiation AISE keeps (never clone
  incumbents).
- `capability-matrix.md` — the ten required capabilities, each with:
  IMPLEMENTED (where: surface + test proving it) or GOVERNED EXCEPTION
  (rationale + owning work item/roadmap position — honest, never silent).
- `golden-journey.md` — the final golden journey replay record: one
  end-to-end pass through evidence → understanding → intervention →
  execution → outcome continuity in the composed app (the replay harness +
  its committed trace).
- `equivalence-summary.md` — the cross-adapter semantic equivalence
  results from §4.2.

### 4.4 Monorepo wiring

The harness and its tests run under the root `bun run verify` (tools/ test
pattern — follow how existing tools' tests are picked up; confirm they are
counted in the gate). No changes to shared configs beyond what your owned
paths need.

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3983 + N) pass / 0 fail** where N = your new tests (state N in
the report), typecheck + lint clean, boundary scan clean (apps may import
packages; apps/web must not import backend sources or other apps' sources —
the equivalence harness consumes the sibling adapters' COMMITTED ARTIFACTS,
not their code), final line `VERIFY: PASS`.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-018: competitive-parity and differentiation hardening"
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
PROD-018 COMPLETION REPORT
base: public main @ 36acb217dcd5142ab920f0ad860068f457c5879e (adapter wave complete: PROD-016+017+019+020+021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3983 + N pass / 0 fail)
composition inventory: <new/changed apps/web surfaces (paths) + the cross-links/labels/bridges shipped>
equivalence harness: <tools/competitive-parity layout + the equivalence report location>
capability matrix: <10 capabilities: X implemented / Y governed exceptions (one line each)>
acceptance:
- competitive simulation re-run against the composed product: <one-line proof>
- every capability implemented or governed exception: <one-line proof>
- evidence → understanding → intervention → execution → outcome continuity visible: <one-line proof incl. golden journey test names>
- no second authority / no provider lock-in: <one-line proof>
- browser/mobile/desktop semantically equivalent: <one-line proof incl. harness test names>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
