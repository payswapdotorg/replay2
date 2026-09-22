# PROD-031 — the solution workspace's browser execution path (the HTTP engine wiring)

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-031 — make the INTERACTIVE SOLUTION WORKSPACE execute in
  a plain browser at the deployed URL, through the backend's live HTTP routes,
  so Gate F's second journey (CURRENT BUILDING → PROBLEM → INTERACTIVE
  SOLUTION → VALIDATE → SOLUTION BOQ → BOQ LINE → SOLUTION STEP) runs for real
  against the deployment. Today the workspace renders the honest
  engine-unavailable panel in a plain browser: the mounted body's module graph
  statically imports `node:crypto`-dependent engine values, the dynamic import
  rejects, and the surface degrades (the documented PROD-026 lazy-mount law).
  The seams for the browser path ALL EXIST (the HTTP service binding, the HTTP
  agent port, the mounted backend routes) — this item wires them and makes the
  module cut browser-safe. Do not start PROD-015, HFX-204 or any other item
  (explicit non-scope: `packages/adapter-contract/**` — PROD-030's surface if
  it is still unmerged at your base; `backend/api/src/mapanything-eval/**` +
  `tools/mapanything-eval/**` — HFX-101 territory; `backend/api/src/bim-eval/**`
  — HFX-204 territory; `tools/bootstrap*`, `docs/EVALUATOR-GUIDE.md` beyond the
  one note enumerated in §7; the readiness declaration — the Tech Lead's).
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/solution/**` (the workspace module: operations.ts, boq.ts,
    service.ts, agent/port.ts, model.ts, SolutionWorkspace.tsx and siblings —
    the browser-safe cut + the binding selection)
  - `apps/web/src/app/surfaces/Solution.tsx` + `apps/web/src/app/solution-mount.tsx`
    + `apps/web/src/app/solution-journey.ts` + `apps/web/src/app/solution-composition*`
    (the mount/binding selection + the composed journey's browser path)
  - `backend/api/src/solution/**` (ONLY if you must add the baseline
    materialization route — §4.4; additive, route-factory discipline)
  - `packages/solution-contract/package.json` + a NEW browser-safe subpath
    module under `packages/solution-contract/src/` (§4.3 — additive ONLY; the
    barrel and every existing module stay byte-identical)
  - `packages/solution-boq/package.json` + the same additive-subpath treatment
    IF the browser path needs its pure resolvers (same rules)
  - `tools/web-bundle/**` (EXTEND the PROD-030 gate: the solution-chunk
    assertion, §5)
  - `docs/productization-evidence/PROD-031/**` (NEW — evidence)
  - The one `docs/EVALUATOR-GUIDE.md` note (§7)
- Explicitly NOT yours: `packages/solution-contract/src/index.ts` and every
  EXISTING module under that package (additive subpath only — the barrel's
  exports are FROZEN to you), `packages/solution-engine/**` (read-only — the
  engine is consumed through ports), `backend/api/src/server.ts` (if your
  baseline route needs mounting, STOP and report — the Lead mounts routes),
  `backend/api/src/reasoning/**` (the compiler — consumed through the port),
  `apps/web/src/app/surfaces/**` except Solution.tsx, `spec/**` (FROZEN), the
  root `bun.lock` (NO dependency changes), root `package.json`, every other
  module, `docs/productization-evidence/**` except PROD-031.
- Governing doctrine: ZERO changes to operation semantics. The engine's
  `applyOperation`/`reviseVersion`/`deriveStateQuantities`/`validateSolution`
  `Version`/`materializeBaselineState` and the BOQ derivation remain THE ONLY
  implementations — this item changes WHERE they execute for a browser client
  (the backend process through the mounted routes), never WHAT they compute.
  The local engine binding remains the default where the module graph
  evaluates (Node contexts, the deterministic gate); the HTTP binding is
  selected when it cannot. No test is weakened, skipped or deleted.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout __PINNED_BASE__   # public GitHub main (the Tech Lead pins this at dispatch)
git rev-parse HEAD   # must print __PINNED_BASE__
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-031/solution-browser-execution
bun run verify
```

Baseline expectation: **__BASELINE__ pass / 0 fail, VERIFY: PASS** (the Tech
Lead's verified number at this SHA). If the baseline is red, STOP and report.

## 2. Mandated reading (in order, before writing anything)

1. `apps/web/src/app/surfaces/Solution.tsx` — the lazy mount law: the ONE
   cached dynamic import (`solutionEngineResource`), the rejection catch, the
   honest engine-unavailable panel. THIS is the selection point you rewire.
2. `apps/web/src/solution/service.ts` — the service seam: the port interface,
   `createLocalSolutionService` (the engine binding — Node contexts) and
   `createHttpSolutionService` (the same-origin HTTP binding over
   `POST /v1/solutions/step|validate|inspect|quantities` + the revision leg,
   fetch INJECTED). The comment names THIS item: "for the Lead's production
   wiring".
3. `apps/web/src/solution/agent/port.ts` — the agent seam:
   `createHttpSolutionAgentPort` over `POST /v1/solution-agent/compile|turn`
   (fetch injected), the scripted double, and the mirror discipline.
4. `backend/api/src/solution/router.ts` — the route inventory + the PURE
   route-factory discipline + the HTTP status mapping (evaluation refusals
   are 200-data; transport/method/decode errors are 4xx/405).
5. `backend/api/src/solution-boq/index.ts` + `router.ts` (PROD-025) — the
   `/v1/solutions/boq` surface (generate/readback/line-operations/
   operation-lines) — the BOQ derivation server-side.
6. `backend/api/src/reasoning/solution/router.ts` (PROD-023) — the agent
   compile/turn routes.
7. `apps/web/src/solution/operations.ts` — the workspace controllers
   (`openWorkspace`, `buildDirectManipulationIntent` + `submitIntent`,
   `applyAgentDecision`, `stepTimeline`, `validateCurrentVersion`,
   `reviseOperation`) and the DIRECT engine value-imports you must sever:
   `materializeBaselineState` (line ~377 — the solution-creation baseline
   overlay), `resolveBoqForOperation` via boq.ts.
8. `apps/web/src/solution/boq.ts` — the BOQ seam: the direct contract
   value-imports (`resolveLinesForOperation`, `resolveOperationsForLine`).
9. `apps/web/src/app/solution-journey.ts` — the composed journey runner +
   `deriveSolutionBoq` (the direct solution-boq value-import).
10. `docs/productization-evidence/PROD-026/end-to-end-journey.md` — the
    twelve-step golden journey (the behavior contract your browser path must
    reproduce; steps 3-12 are the journey-2 legs).
11. `tools/web-bundle/**` — the PROD-030 bundle gate you EXTEND (§5).
12. `packages/solution-contract/src/identity.ts` — WHY the barrel is
    browser-unsafe (module-scope `createHash` from `node:crypto`) and which
    functions are crypto-FREE (verify, never assume — §4.3).

## 3. The defect (what you are fixing)

The workspace's browser-safety is currently ALL-OR-NOTHING: the entire mounted
body (workspace + composed journey) evaluates or the surface degrades to the
static panel. The mounted graph statically imports engine/contract/boq VALUES
(`materializeBaselineState`, `resolveLinesForOperation`,
`resolveOperationsForLine`, `createOperationIntent`,
`REFERENCE_BUILDING_OPERATION_PROFILE`, `deriveSolutionBoq`, the local service
constructor) whose packages transitively import `node:crypto` at module scope
— a plain-browser bundle externalizes it and the dynamic import rejects.
The consequence at the deployed URL: journey 2 CANNOT run — no direct
manipulation, no agent commands, no validation display, no BOQ trace — while
every required backend route is LIVE and session-authenticated behind the
demo path. The module's own docs name the intended fix: the HTTP bindings
exist "for the Lead's production wiring", "with zero workspace edits" at the
agent seam.

## 4. The wiring (the mandated design)

1. **The service-selection mount** (`surfaces/Solution.tsx` +
   `solution-mount.tsx`): keep the ONE cached dynamic import of the local
   engine mount as the FIRST choice. On rejection, attempt a SECOND cached
   dynamic import of a NEW browser mount entry (§4.2). Only if BOTH fail does
   the existing honest engine-unavailable panel render (unchanged semantics,
   one more rung on the ladder). No synchronous fallback, no silent catch:
   each rung logs its outcome to the console guard's non-blocking channel.

2. **The browser mount entry** (NEW, e.g. `apps/web/src/app/solution-browser-mount.tsx`):
   the composed body with EVERY engine/contract/boq value supplied through
   the HTTP bindings — `createHttpSolutionService` (the existing port) for
   step/validate/inspect/quantities/revision, the BOQ seam over
   `POST /v1/solutions/boq` (generate/readback/line-operations/operation-lines
   — a NEW thin HTTP adapter in the boq seam's discipline if none exists),
   and `createHttpSolutionAgentPort` for the agent leg. The fetch used is the
   browser global (same-origin — the PROD-001 contract); the demo session's
   cookies ride it. If the backend is unreachable (no session / network
   error), the browser mount surfaces the honest not-connected state — never
   fabricated engine output.

3. **The browser-safe resolvers** (additive subpath, the PROD-030 pattern):
   verify (by reading + a co-located test that imports ONLY the subpath in a
   crypto-free assertion) which contract/boq functions the browser graph
   still needs DIRECTLY (`resolveLinesForOperation`,
   `resolveOperationsForLine`, `REFERENCE_BUILDING_OPERATION_PROFILE`, and
   any pure constants) are crypto-FREE — then export them from a NEW
   `packages/solution-contract/src/browser.ts` (added to the package's
   exports map as `"./browser"`) that imports ONLY crypto-free modules. The
   existing barrel stays byte-identical. Any function that transitively
   needs `createHash` is NOT browser-safe — it moves behind the HTTP
   service/port instead (§4.2). The same additive treatment for
   `packages/solution-boq` IF (and only if) a pure resolver is needed
   browser-side; `deriveSolutionBoq` itself is a derivation — prefer the
   backend route over any browser re-implementation.

4. **The baseline materialization**: `materializeBaselineState` (operations.ts
   ~line 377) hashes the observed scene — crypto-dependent, NOT
   browser-safe. Route it through the service port: add
   `POST /v1/solutions/baseline` to `backend/api/src/solution/router.ts`
   (additive — body `{ observedScene, materializedAt, capabilityProfile? }`
   or the engine's own input shape; response the engine's baseline
   `ProposedState`; the same strict-decode + fail-closed discipline + HTTP
   status mapping as the existing routes) and extend the service port with
   the corresponding method (the local binding calls the engine directly;
   the HTTP binding posts the route). If — and only if — mounting the route
   requires editing `backend/api/src/server.ts`, STOP and report instead
   (the Lead mounts routes at the integration station).

5. **The agent leg**: the browser mount binds
   `createHttpSolutionAgentPort` (already shipped, fetch injected). The
   scripted double stays a test-only export (never the browser default).
   Confirmed agent proposals flow through the SAME submission path as
   direct manipulation (the existing §4.2 one-operation-semantics law —
   unchanged).

6. **The composed journey record** (`solution-journey.ts`): the recorded
   demo journey currently derives through the engine/boq packages directly.
   In the browser mount, the journey record the surface renders comes from
   the HTTP bindings (the backend executes the same deterministic steps) —
   OR, if the record is derivable from committed fixture data without
   crypto, from the browser-safe subpath. Choose the design that keeps ONE
   record (no second serialization); document the choice in the evidence.

## 5. The bundle gate extension — `tools/web-bundle/**`

Extend the PROD-030 gate (do not weaken it):

1. The existing shell/mount assertions stay.
2. NEW: the built solution chunk (or the whole assets tree if chunks are
   unnamed) contains NO Node-builtin markers (the same marker list) —
   proving the browser mount's graph is crypto-free.
3. NEW: a real-Chromium mount check of the SOLUTION surface against a local
   static serve of `apps/web/dist` WITH a session-authenticated local
   backend (the `bun run demo` stack or the smallest honest equivalent —
   the check may SKIP the interaction legs if the backend is not feasible
   in the gate, but the MOUNT assertion (the workspace chrome renders, not
   the engine-unavailable panel, when the backend is reachable) MUST run).
   Mirror the deployed-check browser discipline (preflight, --no-sandbox,
   guaranteed cleanup).
4. The NEGATIVE CONTROL doctrine carries over: at your pristine base (before
   your fix), the solution-surface mount check must FAIL-or-degrade exactly
   as documented (the engine-unavailable panel); after the fix it mounts.
   Capture both runs in the evidence.

## 6. The workspace browser test (real behavior, not smoke)

A Chromium-driven test (the tools/deployed pattern; the root playwright
devDependency) that walks journey 2's legs against the local production
build + local backend: open the demo project's solution surface → the
workspace mounts → ONE direct-manipulation operation (the committed
demolition fixture) → the agent leg ONE command (the committed
"Rebuild the damaged wall with blocks." script → clarification → answer →
confirm) → validation visible over v1 → the generated BOQ renders → ONE
BOQ line click → the line→step trace renders (the deep-link query) → the
observed scene UNCHANGED (the read-only anchors). Assert the typed outcomes
(the committed identities from PROD-026's record where deterministic).
Wire it into `bun run verify` (the tools/web-bundle or a sibling suite) so
the browser journey is a GATE, not a demo. If the sandbox cannot run
Chromium, STOP and report (never silently skip a browser check).

## 7. Docs + evidence

- `docs/EVALUATOR-GUIDE.md` — ONE note update: the interactive solution
  surface now executes at the deployed URL through the backend engine
  binding (the honest history pointer to the PROD-031 evidence); keep the
  local-bundle note's truthfulness in sync if PROD-030 changed it.
- `docs/productization-evidence/PROD-031/README.md` — the design (the
  selection ladder, the port map, the subpath cut with the crypto-freeness
  proof, the baseline route), the negative control captures, and the
  browser-journey capture (§6) with the exact commands + SHAs.
- `docs/productization-evidence/PROD-031/browser-journey.md` — the recorded
  journey-2 run (the twelve-step table format of PROD-026's recording, the
  real-browser column).

## 8. Gates (all must pass before delivery)

```bash
bun run verify        # __BASELINE__ + N pass / 0 fail — N = your new tests; VERIFY: PASS
bun run typecheck     # PASS
bun run lint          # PASS
```

N is your new-test count; report the exact number. The existing suites
(the PROD-024/025/026 workspace/BOQ/composition tests, the PROD-023 compiler
tests, the PROD-030 web-bundle gate) must all still pass UNCHANGED.

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
PROD-031 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Exit gate (the browser execution path)
- the workspace mounts in a real plain browser (the selection ladder's second rung): <YES/NO — the browser test name>
- direct manipulation and agent commands resolve to typed operations through the SAME submission path: <YES/NO — the test names>
- validation + the generated solution BOQ render and the line↔step trace round-trips: <YES/NO — the test names>
- the browser mount's bundle graph is crypto-free (no Node-builtin markers in the solution chunk): <YES/NO — the gate assertion>
- the local engine binding remains the default where the module graph evaluates; the honest degraded panel remains the final rung: <YES/NO>
- zero operation-semantics changes (the engine/BOQ/compiler modules untouched or additive-only): <YES/NO — the diffstat shape>
- the baseline materialization route (if added) follows the route-factory discipline: <YES/NO — or "not needed: <why>">

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
