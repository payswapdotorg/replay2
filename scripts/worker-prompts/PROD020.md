# PROD-020 — Desktop adapter productization

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly.
The repository itself is your specification library; read the mandated files
below BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-020 (the desktop adapter). Do not start
  PROD-017/018/019 or any other item. Do not touch web or Android surfaces.
- Owned surface (the ONLY files you may create/modify):
  - `apps/desktop/**` (NEW — you create this directory; it does not exist)
  - `docs/productization-evidence/PROD-020/**` (evidence documents)
- Explicitly NOT yours: `packages/adapter-contract/**` and
  `spec/client-adapter-contract.md` (the shared contract — the PROD-016
  compatibility window FORBIDS adapter workers from changing it; IMPORT from
  `@aise/adapter-contract`, never modify it), `apps/web/**`,
  `apps/android/**`, `backend/**`, `packages/shared-contracts/**`,
  `docs/productization-state.json` (Tech-Lead-owned), every other spec file,
  the root `bun.lock` (see §6 — the Lead regenerates the canonical lockfile).
  EXCEPTION: `apps/web/**` is not yours to MODIFY, but you may reference and
  load it (the work order explicitly permits a thin installed shell over the
  existing web application — you may add a BUILD/TARGET configuration inside
  `apps/desktop/` that points at the web app's dev/build output; you may not
  edit the web app's own files).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- Keep the root install light: `apps/desktop` must be a real bun workspace
  package whose TESTS run under the root `bun run verify`. The desktop
  platform binary (Electron or your chosen shell) must be a devDependency of
  `apps/desktop` only — never a root dependency.
- Never weaken, skip or delete an existing test.

## 1. Setup — public main (the shared contract IS on GitHub main now)

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 0bbcb1fb11765ea5fcd9db7198210b7dd5975363   # public GitHub main (PROD-016 + 017 + 019 + 021 merged)
git rev-parse HEAD   # must print 0bbcb1fb11765ea5fcd9db7198210b7dd5975363
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-020/desktop-adapter
bun run verify
```

Baseline expectation: **3808 pass / 0 fail, VERIFY: PASS** (the PROD-016 + PROD-017
adapter-contract suite and the FIX-001 regression test are on main). If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/client-adapter-contract.md` (the contract INCLUDING the PROD-016
   checkable-artifacts section, merged to main with PROD-016 — its 12-item client
   conformance suite applies to your adapter)
4. `spec/governance/architecture-change-record-004.md` (ACR-004: client
   adapters over a single product core — THE governing record for this item)
5. `spec/governance/architecture-change-record-005.md` and `-006.md`
6. `docs/productization-work-orders.md` §PROD-020 (your work order —
   reproduced in §3 below)
7. `packages/adapter-contract/` IN FULL — README.md (layout, versioning,
   no-client-authority), `src/index.ts` (the public API you consume),
   `src/conformance.ts` (runConformance / CONFORMANCE_CHECKS /
   AUTHORITATIVE_FIELDS / createLosslessBinding),
   `src/reference-profiles.ts` (REFERENCE_DESKTOP_RICH_SHELL_PROFILE and the
   reference task-requirement sets), `src/fixtures-loader.ts`
   (loadCommittedFixtures), `fixtures/` layout, `schemas/manifest.json`
8. `docs/productization-evidence/PROD-016/adapter-boundary-audit.md` — the
   §"apps/desktop" ruling: PROD-020 must consume `@aise/adapter-contract`
   from its FIRST commit (declare a desktop-appropriate
   `ClientCapabilityProfile` with the reference `desktop-rich-shell` profile
   as template, decode the twelve semantic objects through the package, pass
   `runConformance` before adding any platform affordance)
9. `docs/productization-evidence/PROD-016/compatibility-window.md` (you must
   not change the shared contract)
10. `apps/web/` structurally (package.json, vite.config.ts, src/ layout) —
    the product shell your desktop adapter wraps; and
    `packages/shared-contracts/` + `packages/adapter-contract/` for the
    established workspace-package conventions (tsconfig, scripts, README
    discipline)

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-020 — Desktop adapter productization
> **Owner:** DESKTOP — **Depends on:** PROD-016
> **Protected surface:** `apps/desktop/**` and desktop-specific adapter tests/docs.
> **Purpose:** Create a real desktop adapter over the shared AISE product
> contracts. The implementation may be a thin installed shell over the
> existing web application, provided it exposes desktop-appropriate
> capabilities without creating a domain fork.
> **Scope:**
> - create `apps/desktop/` with a reproducible desktop build/run workflow;
> - choose the lightest maintainable desktop technology compatible with the
>   repository and target operating-system support;
> - consume the same task/capability/result contract as browser/mobile;
> - optimize for high-density review, large files, keyboard shortcuts and
>   optional local integration affordances;
> - add desktop conformance tests using PROD-016 fixtures;
> - ensure the desktop adapter can open a project and exercise
>   representative review/intervention workflows.
> **Explicit non-scope:** Do not fork domain services,
> Reality/Evidence/Assurance/Verification logic, or the shared contract. Do
> not make local filesystem state authoritative. Do not block the
> web/mobile product on platform-specific features.
> **Acceptance:**
> - `apps/desktop` is a real runnable product surface, not documentation or
>   a placeholder;
> - desktop actions resolve to shared server/domain actions;
> - representative desktop project/review journey passes;
> - desktop conformance passes on at least one documented supported desktop
>   environment;
> - platform-specific convenience features remain optional and
>   non-authoritative.
> **Evidence:** Build/run transcript + desktop smoke trace + adapter
> conformance report + supported-platform declaration.

## 4. Implementation shape

Create `apps/desktop/` as a real bun workspace package. Required work,
mapped to the acceptance criteria:

1. **Technology choice (lightest maintainable):** an Electron-based thin
   shell is the suggested baseline (installs purely from npm as a
   devDependency — no system toolchain), but the choice is yours within the
   work order's constraint. Whatever you choose: the PLATFORM layer (the
   shell entry, window management, menus, local-integration affordances)
   must be thin and clearly separated from the ADAPTER LOGIC layer, and the
   adapter logic must be 100% unit-testable under plain `bun test` WITHOUT
   launching the platform binary.
2. **Contract consumption from the first commit:** depend on
   `@aise/adapter-contract` (`workspace:*`). Declare the desktop
   `ClientCapabilityProfile` (template: `REFERENCE_DESKTOP_RICH_SHELL_PROFILE`
   — window management, file workflow, offline queue, keyboard shortcuts,
   table review, high-density panes). Decode the twelve semantic objects
   through the package (decodeX/decodeXStrict) at your adapter's data seam.
   Desktop actions resolve to shared server/domain actions — the shell sends
   typed `TaskIntent` wire objects and renders `OperationResult` /
   `NextBestAction` / `AuthorizationContext` verbatim, exactly like the
   browser adapter would.
3. **Conformance (before any platform affordance):** implement your adapter
   binding and run `runConformance(binding, loadCommittedFixtures())`
   (C0–C9) plus the platform-specific client conformance suite required by
   `spec/client-adapter-contract.md` — as bun tests in the root gate. This
   suite is the acceptance core: it must pass BEFORE platform features.
4. **High-density review + keyboard shortcuts:** a keyboard-shortcut
   registry (declarative, testable — shortcuts are presentation, never
   authority), a high-density review surface model (dense table/pane layout
   descriptions for review workflows over the semantic objects), and
   optional local integration affordances (open-a-local-file dialogs,
   OS notifications) behind explicit capability declarations — optional and
   non-authoritative.
5. **Representative journey:** an automated smoke trace (bun test, following
   the repo's task-trace test patterns) that opens a project (ProjectContext
   decoded), walks representative review/intervention workflows
   (EngineeringCaseSummary / InterventionScenarioSummary / BOQContext
   surfaces with provenance visible), authors a TaskIntent, and renders the
   OperationResult — through the desktop adapter's REAL entrypoints (the
   adapter layer the shell drives).
6. **Reproducible build/run workflow:** `apps/desktop/package.json` scripts
   (`dev`, `build`, `start`, `test`) + a README documenting: prerequisites,
   how to run the shell against the web app (dev server URL or built
   assets), how the conformance suite runs in the root gate, and the
   supported-platform declaration. If the platform binary cannot be
   launched in your sandbox (headless), say so honestly in the evidence and
   unit-test the shell entry's BEHAVIOR (argument handling, URL/loading
   policy, menu/shortcut wiring) without launching it — the Lead runs the
   launch smoke at the integration station.
7. **No local-fs authority:** local file state (recent projects, cached
   preferences, offline queue) is convenience only — never a source of
   record; assert this in tests.

Evidence documents under `docs/productization-evidence/PROD-020/`:
- `build-run-transcript.md` — what you built, the exact commands, what ran
  in-sandbox vs what needs a display (honest);
- `conformance-report.md` — the desktop binding, C0–C9 results, the
  platform-specific suite inventory;
- `desktop-smoke-trace.md` — the representative project/review journey trace
  with the semantic objects at each step;
- `supported-platforms.md` — the supported-platform declaration (at least
  one documented desktop environment; state exactly what you could and could
  not verify in-sandbox).

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3808 + N) pass / 0 fail** where N = your new tests (state N in
the report), typecheck + lint clean, boundary scan clean (apps/desktop may
import packages; must NOT import backend sources or other apps), final line
`VERIFY: PASS`. Your package's tests must be picked up by the root gate via
the workspace glob — confirm they are counted.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-020: desktop adapter productization"
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
`apps/desktop/package.json` declarations are what matters). Note in your
report that you excluded it. Also exclude any platform-binary artifacts
(`node_modules`, downloaded binaries, packaged output) — source only.

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-020 COMPLETION REPORT
base: public main @ 0bbcb1fb11765ea5fcd9db7198210b7dd5975363 (PROD-016 + 017 + 019 + 021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3808 + N pass / 0 fail)
technology choice: <shell technology + why it is the lightest maintainable>
contract consumption: <one-line proof of decodeX seam + TaskIntent authoring>
conformance: <C0–C9 result + platform-specific suite inventory>
journey: <one-line proof of the project/review smoke trace through real adapter entrypoints>
keyboard/review affordances: <one-line proof (registry + high-density model)>
local-fs non-authority: <one-line proof>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock + binaries excluded)
notes: <what could not run in-sandbox (display/binary), any deviation, or "none">
```
