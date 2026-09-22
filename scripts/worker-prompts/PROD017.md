# PROD-017 — Browser adapter and task-first product UX

You are a senior TypeScript engineer executing ONE well-specified work item in the
AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-017 (the browser adapter). Do not start PROD-018/019/020
  or any other item. Do not touch Android or desktop surfaces.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/**` (the browser adapter application)
  - `docs/productization-evidence/PROD-017/**` (evidence documents)
- Explicitly NOT yours: `packages/adapter-contract/**` and
  `spec/client-adapter-contract.md` (the shared contract — the PROD-016
  compatibility window FORBIDS adapter workers from changing it; IMPORT from
  `@aise/adapter-contract`, never modify it), `apps/android/**`,
  `apps/desktop/**`, `backend/**`, `packages/shared-contracts/**`,
  `docs/productization-state.json` (Tech-Lead-owned), every other spec file,
  the root `bun.lock` (see §6 — the Lead regenerates the canonical lockfile).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- No new runtime dependencies beyond what the repo already uses. The web app
  gains ONE dependency: `@aise/adapter-contract` (workspace package).
- Never weaken, skip or delete an existing test.

## 1. Setup — public main (the shared contract IS on GitHub main now)

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 7d21d47147a3df14a0e6138131de6d9add672d27   # public GitHub main (PROD-016 + PROD-021 merged)
git rev-parse HEAD   # must print 7d21d47147a3df14a0e6138131de6d9add672d27
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-017/browser-adapter
bun run verify
```

Baseline expectation: **3718 pass / 0 fail, VERIFY: PASS** (the PROD-016
adapter-contract suite and the FIX-001 regression test are on main). If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/client-adapter-contract.md` (the contract INCLUDING the PROD-016
   checkable-artifacts section, merged to main with PROD-016)
4. `spec/governance/architecture-change-record-004.md` (ACR-004: client
   adapters over a single product core — THE governing record for this item)
5. `spec/governance/architecture-change-record-005.md` and `-006.md`
6. `docs/productization-work-orders.md` §PROD-017 (your work order —
   reproduced in §3 below)
7. `packages/adapter-contract/` IN FULL — README.md (layout, versioning,
   no-client-authority), `src/index.ts` (the public API you consume),
   `src/conformance.ts` (runConformance / CONFORMANCE_CHECKS /
   AUTHORITATIVE_FIELDS / createLosslessBinding),
   `src/reference-profiles.ts` (REFERENCE_BROWSER_PROFILE and the reference
   task-requirement sets), `src/fixtures-loader.ts` (loadCommittedFixtures),
   `fixtures/` layout, `schemas/manifest.json`
8. `docs/productization-evidence/PROD-016/adapter-boundary-audit.md` — the
   §"apps/web" findings AND the §"apps/web — required adapter-local removals"
   (W-R1 … W-R5): these removals are YOUR recorded obligations
9. `docs/productization-evidence/PROD-016/compatibility-window.md` (you must
   not change the shared contract)
10. `apps/web/` IN FULL — package.json, vite.config.ts, tsconfig.json, and
    every module under `src/` (app/, shell/, viewer/, workspace/, boqlens/ and
    any other directory), including their tests. This is the product shell you
    are promoting into the task-first browser adapter.

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-017 — Browser adapter and task-first product UX
> **Owner:** WEB — **Depends on:** PROD-010, PROD-016
> **Protected surface:** `apps/web/**` and browser-specific adapter tests/docs.
> **Purpose:** Turn the current web product shell into the primary task-first
> browser adapter over the shared AISE domain/API contracts.
> **Scope:**
> - implement task-first landing, project opening/creation and Next Best Action
>   flows;
> - make the golden journey executable from the browser without source-code/API
>   knowledge;
> - make loading, empty, error, unavailable-provider and permission states
>   explicit;
> - preserve direct auditability from consequential claims/quantities to
>   source/evidence/version context;
> - implement browser conformance tests using the PROD-016 fixtures;
> - keep browser-specific presentation state non-authoritative.
> **Explicit non-scope:** Do not change Android or desktop surfaces. Do not
> change Reality/Evidence/Assurance/Verification semantics. Do not redesign
> the shared contract.
> **Acceptance:**
> - browser completes the primary product journey through real application
>   entrypoints;
> - every primary screen exposes the next useful action or an explicit blocked
>   reason;
> - observed/proposed, provenance, uncertainty and authorization semantics
>   remain visible and intact;
> - browser adapter conformance passes.
> **Evidence:** Browser task trace + automated browser/adapter tests +
> provenance spot checks + screenshots/recording as repository evidence.

## 4. Implementation shape

Follow the repo's own conventions (study how `apps/web` modules are structured:
model/ports/actions/render separation, committed fixtures, one test file per
module). Required work, mapped to the acceptance criteria:

1. **Contract consumption at the seam (the W-R1/W-R2 removals):** decode the
   server's semantic objects through `@aise/adapter-contract`
   (decodeX/decodeXStrict — ProjectContext, RealitySummary, BOQContext,
   EvidenceSummary, EngineeringCaseSummary, InterventionScenarioSummary,
   OutcomeSummary, NextBestAction, AuthorizationContext, OperationResult) at
   the `app/api.ts` seam, replacing the hand-maintained structural-mirror
   validators. Keep the detailed pane/view projections (viewer, workspace,
   boqlens render models) local — they are legitimate presentation.
2. **Task-first landing and Next Best Action flows:** the app's entry
   experience is task-first (open/create project → the golden journey's steps
   as NextBestAction-driven flow), not module-first. Every primary screen
   exposes the next useful action or an explicit blocked reason (render
   AuthorizationContext denials and negotiation-blocked states verbatim).
3. **Explicit states everywhere:** loading, empty, error,
   unavailable-provider and permission states are first-class renders — never
   blank, never generic.
4. **TaskIntent authoring (W-R3):** `create-forms.ts`, `outcome-forms.ts`,
   `evidence-picker.ts` emit typed `TaskIntent` wire objects.
5. **Browser capability profile + conformance (W-R4):** declare the browser
   `ClientCapabilityProfile` (use `REFERENCE_BROWSER_PROFILE` as the factual
   template) and run `runConformance(binding, loadCommittedFixtures())`
   (C0–C9) in the browser adapter test suite, extended with the
   platform-specific client conformance suite required by
   `spec/client-adapter-contract.md`.
6. **Presentation stays non-authoritative:** boqlens derivations/health
   rollups remain presentation-only aggregations (W-R5 standing constraint —
   do not regress it).
7. **Golden journey executable through real entrypoints:** an automated
   task trace that drives the real application entrypoints (router + api +
   shell modules — follow the existing test patterns of `app/router.test.ts`
   and the shell fixtures pattern) end-to-end: project context load →
   journey steps → evidence/case/BOQ surfaces → an operation result, with
   provenance spot checks asserting that consequential quantities trace to
   their source/evidence/version context.

Add `@aise/adapter-contract` (`workspace:*`) to `apps/web/package.json`
dependencies. Do NOT stage `bun.lock` in your delivery (§6).

Evidence documents under `docs/productization-evidence/PROD-017/`:
- `browser-task-trace.md` — the golden-journey task trace (step-by-step, with
  the semantic objects observed at each step and provenance spot checks);
- `conformance-report.md` — the browser binding, the C0–C9 results, and the
  platform-specific suite inventory;
- `screenshots/` or `render-trace/` — visual or DOM/text render evidence of
  the primary screens and their explicit states. If a literal screenshot is
  not producible in your sandbox, commit DOM/text render traces and document
  that limitation honestly — do not fabricate images.

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3718 + N) pass / 0 fail** where N = your new tests (state N in
the report), typecheck + lint clean, boundary scan clean (apps may import
packages; apps/web must NOT import backend sources or other apps), final line
`VERIFY: PASS`.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-017: browser adapter and task-first product UX"
git diff $BASE..HEAD --stat
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's
harvest API cannot see. After committing, copy EVERY new/changed file (the
complete diff vs the base commit `$BASE` from §1) into the PROJECT
directory (the one containing package.json / src/ — the workspace root),
preserving repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery: remove `delivery/bun.lock` if staged.
The Lead regenerates the canonical lockfile at the integration station (your
`apps/web/package.json` dependency declaration is what matters). Note in your
report that you excluded it.

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-017 COMPLETION REPORT
base: public main @ 7d21d47147a3df14a0e6138131de6d9add672d27 (PROD-016 + PROD-021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3718 + N pass / 0 fail)
contract consumption: <which decodeX seams replaced which mirrors (W-R1/W-R2)>
task-first + NBA: <one-line proof of landing/journey/NBA flows + explicit states>
TaskIntent authoring: <one-line proof (W-R3)>
browser profile + conformance: <profile summary + C0–C9 result (W-R4)>
presentation non-authoritative: <one-line proof (W-R5)>
golden journey: <one-line proof of the task trace through real entrypoints + provenance spot checks>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```
