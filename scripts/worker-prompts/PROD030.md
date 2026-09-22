# PROD-030 — the shared-contract barrel browser-bundle fix (the PROD-026-escalated module-evaluation defect)

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-030 — fix the browser-bundle module-evaluation defect in
  the two shared-contract barrels (`@aise/adapter-contract`,
  `@aise/solution-contract` both re-export a Node-only fixtures loader whose
  module scope crashes plain-browser bundles), add the bundle gate that proves
  it stays fixed, and update the three honest-limitation notes that document
  the defect. Do not start PROD-015, HFX-101 or any other item (explicit
  non-scope: `backend/api/src/mapanything-eval/**` + `tools/mapanything-eval/**`
  — HFX-101 is IN FLIGHT there; `backend/api/src/bim-eval/**` +
  `tools/bim-eval/**` — HFX-204 owns that lane; `tools/bootstrap*`,
  `docs/EVALUATOR-GUIDE.md` beyond the three defect notes enumerated in §6,
  `docs/INSTALL.md` beyond a defect note if one exists).
- Owned surface (the ONLY files you may create/modify):
  - `packages/adapter-contract/package.json` (exports map) and
    `packages/adapter-contract/src/index.ts` (remove the loader re-export)
  - `packages/solution-contract/package.json` (exports map) and
    `packages/solution-contract/src/index.ts` (remove the loader re-exports)
  - The consumer import-site updates enumerated in §4.5 (import statements
    ONLY — no behavior changes in those files)
  - `tools/web-bundle/**` (NEW — the browser-bundle gate; see §5)
  - `docs/productization-evidence/PROD-030/**` (NEW — evidence)
  - The three `docs/EVALUATOR-GUIDE.md` defect notes (§6) and an
    `docs/INSTALL.md` defect note if present
- Explicitly NOT yours: the fixtures-loader implementations themselves (their
  Node behavior is unchanged — you move WHERE they are exported from, not what
  they do), `tools/deployed/**` + `tools/deployed-check.ts` (read as pattern,
  never modify), `docs/productization-evidence/PROD-012-R/repro-harness.ts`
  (it self-detects this fix — its patch becomes a no-op "pattern no longer
  matches" branch; leave it byte-untouched), `spec/**` (FROZEN), the root
  `bun.lock` (NO dependency changes — do not touch it), root `package.json`,
  every other module.
- Governing doctrine: this is a SEAM/PACKAGING fix. Zero behavior changes.
  The loaders keep working identically for every Node consumer. No test is
  weakened, skipped or deleted. The public barrel of each package loses
  exactly the loader symbols; everything else it exports today it must still
  export tomorrow.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 6ef2c3c1b5bf82fa3dc90ca1a19e7e7dd10786ed   # public GitHub main (PROD-014 finalized)
git rev-parse HEAD   # must print 6ef2c3c1b5bf82fa3dc90ca1a19e7e7dd10786ed
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-030/browser-bundle-seam-fix
bun run verify
```

Baseline expectation: **5260 pass / 0 fail, VERIFY: PASS**. If the baseline is
red, STOP and report (do not try to fix the baseline).

## 2. Mandated reading (in order, before writing anything)

1. `docs/productization-evidence/PROD-026/end-to-end-journey.md` — search
   `pre-existing baseline finding`: the escalation record for THIS defect
   (present at the adapter-wave base; "belongs to the adapter wave's seam
   (PROD-016/017 territory)").
2. `docs/productization-evidence/PROD-012-R/repro-harness.ts` — the
   `Phase 0b` block: the exact crash mechanism, quoted from a real browser
   (`vite` externalizes `node:path` as `__vite-browser-external` = `{}`; the
   dead module-init statements throw `TypeError: (0, X.join) is not a
   function` before the app mounts; `bun run build` succeeds and
   `bun run verify` never loads the built bundle in a browser — which is how
   the defect shipped unnoticed).
3. `packages/adapter-contract/src/index.ts` (the `loadCommittedFixtures`
   re-export near the end), `packages/adapter-contract/src/fixtures-loader.ts`
   (module scope: `join(import.meta.dir, "..")` at evaluation),
   `packages/adapter-contract/package.json` (the `exports` map).
4. The same three files under `packages/solution-contract/` (the
   `loadCommittedFixtures` + `SolutionFixtureRecord`/`SolutionFixtureCorpus`
   type re-exports near the end of its index).
5. `tools/deployed/browser.ts` + the top of `tools/deployed-check.ts` — the
   Chromium launch pattern you MIRROR in the new gate (executable preflight
   that FAILS EXPLICITLY with the install command; `--no-sandbox` +
   `--disable-dev-shm-usage`; guaranteed cleanup).
6. `apps/web/package.json`, its vite config, `apps/web/src/main.tsx` and the
   shell/gate markup (`h2#gate-title` is the deployed-check shell selector) —
   what mounts first in the browser.
7. `docs/EVALUATOR-GUIDE.md` — the three defect notes you will update (§3A
   local-bundle note, §5 troubleshooting row "Local web page … is blank", §6
   "Not the local UI at this commit" bullet).

## 3. The defect (what you are fixing)

Both shared-contract barrels re-export a Node-only fixtures loader:

- `packages/adapter-contract/src/index.ts`:
  `export { loadCommittedFixtures } from "./fixtures-loader";`
- `packages/solution-contract/src/index.ts`:
  `export { loadCommittedFixtures } from "./fixtures-loader";` plus
  `export type { SolutionFixtureRecord, SolutionFixtureCorpus } from
  "./fixtures-loader";`

Each loader imports `node:fs`/`node:path` AND evaluates
`join(import.meta.dir, "..")` at MODULE SCOPE. `apps/web` imports the barrels;
vite bundles the loaders along; for the browser it externalizes the Node
builtins as `__vite-browser-external` (= `{}`), so the module-init call throws
`TypeError: (0, X.join) is not a function` before the app ever mounts — blank
page, no auth gate, no shell. This is live on the production deployment right
now (2026-09-22 deployed-check: the auth gate never becomes visible; 10
`pageerror` events with exactly that TypeError). The pre-adapter-wave
deployment predates the defect, which is why the site used to boot.

## 4. The seam fix — subpath exports (the mandated design)

1. `packages/adapter-contract/package.json` — extend the exports map:

   ```json
   "exports": {
     ".": "./src/index.ts",
     "./fixtures-loader": "./src/fixtures-loader.ts"
   }
   ```

2. `packages/adapter-contract/src/index.ts` — DELETE the
   `loadCommittedFixtures` re-export line. Nothing else changes.

3. `packages/solution-contract/package.json` — the same subpath entry
   (`"./fixtures-loader": "./src/fixtures-loader.ts"`).

4. `packages/solution-contract/src/index.ts` — DELETE both the
   `loadCommittedFixtures` re-export AND the `SolutionFixtureRecord`/
   `SolutionFixtureCorpus` type re-export from the barrel (they move to the
   subpath with the loader). Nothing else changes.

5. Migrate EVERY in-repo consumer to the deep import (import statements only;
   split mixed import statements so the remaining barrel symbols stay on the
   barrel import):

   - `packages/adapter-contract/src/conformance.test.ts` and
     `.../authority.test.ts` → relative `"./fixtures-loader"`
   - `packages/solution-contract/src/authority.test.ts` and
     `.../invariants.test.ts` → relative `"./fixtures-loader"`
   - `apps/web/src/app/task-contract.test.ts` and
     `apps/web/src/app/conformance.test.tsx` →
     `"@aise/adapter-contract/fixtures-loader"`
   - `apps/desktop/src/adapter/corpus-world.ts` (production code — Node/Electron
     main-process, safe) and `apps/desktop/src/adapter/corpus-world.test.ts`,
     `.../seam.test.ts`, `.../conformance.test.ts` →
     `"@aise/adapter-contract/fixtures-loader"`
   - `backend/api/src/reasoning/solution/compiler.test.ts` →
     `"@aise/solution-contract/fixtures-loader"`

   After migration, `grep -rn "loadCommittedFixtures" --include="*.ts"
   --include="*.tsx" .` must show NO import of it from either bare barrel
   (`"@aise/adapter-contract"` / `"@aise/solution-contract"`).

6. REJECTED alternative (document it in the evidence README, do NOT implement
   it): making the loader's module scope lazy (moving the `join` calls inside
   the function). That would stop the crash but still ships the loader graph
   and Node-builtin externalization stubs into every browser bundle — one
   future module-scope addition away from the same crash. The subpath design
   removes the loader from the browser module graph ENTIRELY: the barrel a
   browser imports can no longer reach `node:fs`.

## 5. The bundle gate — `tools/web-bundle/**` (NEW)

The gate that would have caught this defect class, wired into
`bun run verify`:

1. **Build**: spawn the apps/web production build (`bun run build` inside
   `apps/web`). The gate owns the full lifecycle (cwd, inherited env, generous
   timeout — the build takes seconds-to-tens-of-seconds; set the test timeout
   accordingly, the bun default 5s will flake).
2. **Scan** every built asset under `apps/web/dist/assets/*.js` (and the
   built `index.html`): assert the browser bundle contains NO Node-builtin
   import/externalization markers — at minimum: no `node:fs` / `node:path`
   import specifiers, no `__vite-browser-external` stub usage feeding a
   `join`-style call, and no `(0, X.join)(import.meta.dir` module-init pattern
   (the class the PROD-012-R harness documented). Choose markers that are
   robust under minification and DOCUMENT each one in the evidence; a marker
   that only matches this exact defect is acceptable — the point is this
   defect class can never ship silently again.
3. **Real Chromium mount check** (mirror `tools/deployed/browser.ts` exactly
   in spirit): preflight the executable (FAIL EXPLICITLY with the
   `bunx playwright install chromium` command if missing — browser checks are
   never silently skipped), launch ONE Chromium with `--no-sandbox` +
   `--disable-dev-shm-usage`, serve `apps/web/dist` (a minimal static file
   server on an ephemeral port is fine; no backend needed for the mount
   assertion), load `/`, and assert (a) the app MOUNTS — the shell root
   element is non-empty / the auth-gate heading (`h2#gate-title`) becomes
   visible — and (b) ZERO `pageerror` events. Close the browser no matter
   what.
4. **Suite wiring**: a `check.test.ts` (or equivalent) under
   `tools/web-bundle/` that runs the gate, registered so `bun run verify`
   executes it — mirror how the existing `tools/*/` suites (e.g.
   `tools/reality-eval/benchmark.test.ts`) are picked up. NO root config
   changes if the existing glob already covers it — prove by running
   `bun run verify` before/after your change and comparing the discovered
   suite count.
5. **Barrel-safety tests** (co-located in each package): import the barrel
   namespace and assert `loadCommittedFixtures` is NOT exported from it; deep
   import the subpath and assert it loads a non-empty committed corpus (the
   round-trip proof the loader still works where it belongs).
6. **Negative control** (mandatory, FIRST, on the pristine base BEFORE any
   fix): run the gate against the unmodified base checkout — it MUST FAIL
   with the defect signature (scan marker hit and/or Chromium mount failure
   with the `(0, X.join)` pageerror). Capture that output verbatim for the
   evidence. Then apply the fix and run it again — PASS. A gate that cannot
   fail on the defect it exists to catch is not a gate.

## 6. Docs — the three honest-limitation notes

In `docs/EVALUATOR-GUIDE.md` (and `docs/INSTALL.md` only if it carries the
same note):

1. §3A (the local-bundle "renders a blank page" note) — update to state the
   defect is FIXED by PROD-030 (the seam fix + the bundle gate), keeping a
   one-line honest history pointer to
   `docs/productization-evidence/PROD-030/`.
2. §5 troubleshooting row ("Local web page at http://localhost:4173/ is
   blank") — update the same way.
3. §6 "Not the local UI at this commit" bullet — update: the local visual
   surface is now demonstrable (the bundle gate proves the mount in a real
   Chromium on every verify run).

Do not rewrite any other guide content. The notes must stay honest — if your
gate shows ANY remaining local-render limitation, say so instead of claiming
more than the proof.

## 7. Evidence — `docs/productization-evidence/PROD-030/**`

- `README.md` — the defect story (the PROD-026 escalation record, the
  PROD-012-R Phase-0b documentation, the 2026-09-22 deployed-check failure
  signature: gate never visible + 10 pageerrors), the fix (subpath exports +
  barrel removal + the consumer migration list), the REJECTED lazy-init
  alternative with the reasoning, and the compatibility note (workspace-
  internal packages; the loader moved from the barrel to a documented
  subpath; all in-repo consumers migrated in this item).
- `browser-proof.md` — the negative-control output (gate FAILS at base, the
  defect signature) AND the passing run after the fix (exact command, commit
  SHA, output).
- `bundle-audit.md` — the scan markers (each documented), the assets scanned,
  and the absence proof after the fix.

## 8. Gates (all must pass before delivery)

```bash
bun run verify        # 5260 + N pass / 0 fail — N = your new tests; VERIFY: PASS
bun run typecheck     # PASS
bun run lint          # PASS
```

N is your new-test count; report the exact number. The bundle gate and the
barrel-safety tests must be part of the verify run (not a side script only),
and the negative control must be recorded in the evidence.

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
PROD-030 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Exit gate (the barrel seam fix + the bundle gate)
- barrels no longer export the Node-only loader (both packages): <YES/NO — the barrel-safety test names>
- every in-repo consumer migrated to the subpath (no bare-barrel loadCommittedFixtures imports remain): <YES/NO>
- bundle scan: no Node-builtin externalization markers in the built web assets: <YES/NO — the marker list>
- real Chromium: app mounts + zero pageerror on the built bundle: <YES/NO — the assertion>
- negative control: the gate FAILS on the pristine base with the defect signature: <YES/NO — the signature line>
- EVALUATOR-GUIDE defect notes updated honestly: <YES/NO>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
