# PROD-027 — Layer-1 hardening: reality/capture/retrieval evaluation entry point

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-027 (Layer-1 reality/capture/retrieval/planning
  hardening — the provider-neutral evaluation entry point for Layer 1, plus
  the Layer-1 benchmark harness and fixture map). Do not start PROD-028/029
  or any HFX-1xx item (explicit non-scope: integrating any REAL provider —
  MapAnything/Video Depth Anything are FUTURE consumers; the fixtures here
  are deterministic in-repo doubles).
- Owned surface (the ONLY files you may create/modify):
  - `backend/api/src/reality-eval/**` (NEW module — see §4)
  - `tools/reality-eval/**` (NEW — the reproducible benchmark runner wired
    into the root verify, following the building-benchmark pattern)
  - `docs/productization-evidence/PROD-027/**` (evidence documents)
- Explicitly NOT yours: `packages/provider-registry/**` (HFX-000's control
  plane — IMPORT `@aise/provider-registry`, never modify it), the existing
  Layer-1 modules (`backend/api/src/reality/**`, `capture/**`,
  `reconstruction/**`, `evidence/**`, `benchmarks/**` — read/import, never
  modify), `backend/api/src/server.ts` + `main.ts` (Lead wires),
  `backend/api/src/reasoning-eval/**` and `backend/api/src/solution-eval/**`
  (PROD-028/029's parallel surfaces), every other package, `apps/**`,
  `spec/**` (FROZEN), the root `bun.lock` (Lead regenerates).
- Governing doctrine: providers are implementation candidates, NEVER
  canonical truth (HFX-000 README). No provider-specific type crosses the
  canonical boundary; native payloads stay opaque. Training/evaluation are
  separate decisions (license gate).
- PURE DETERMINISTIC COMPUTATION: no network, no clock reads, no randomness.
  Identical fixtures produce identical evaluation records, byte-for-byte.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 0a9aa811aec973f121514e291a293644ec9e1dda   # public GitHub main (through HFX-000 — provider control plane merged)
git rev-parse HEAD   # must print 0a9aa811aec973f121514e291a293644ec9e1dda
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-027/layer1-eval
bun run verify
```

Baseline expectation: **4742 pass / 0 fail, VERIFY: PASS**. If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandated reading (in order, before writing anything)

1. `spec/governance/architecture-change-record-006.md` — Layer-1 requirements
   (provider-neutral reconstruction, portable provenance, capture coverage as
   first-class state, device capability as strategy input never assurance
   downgrade).
2. `packages/provider-registry/README.md` + `src/index.ts` — the control
   plane you CONSUME: ProviderProfile schema, registry + promotion states,
   normalized I/O boundary (`ProviderInput`/`ProviderResult`,
   `normalizeResult`), the closed failure vocabulary (`FAILURE_VOCABULARY`),
   BenchmarkRecord, ProvenanceManifest, the reference-provider testkit
   pattern.
3. `docs/productization-layer-hardening-work-orders.md` — Layer-1 items
   (HFX-101 MapAnything, HFX-102 Video Depth Anything, HFX-103, HFX-104) are
   your FUTURE consumers: design their entry points, do not implement them.
4. `backend/api/src/benchmarks/index.ts` + `model.ts` — the existing
   benchmark engine (import surface).
5. `backend/api/src/reality/` + `reconstruction/` + `capture/` (index files +
   models) — the Layer-1 canonical modules you evaluate AGAINST (read-only).
6. `tools/building-benchmark/` — the house pattern for a deterministic
   root-verify benchmark runner with committed expected-outcomes fixtures.
7. `AGENTS.md` — repo conventions.

## 3. The work

### 3.1 The Layer-1 evaluation entry point (`backend/api/src/reality-eval/`)

A provider-neutral evaluation HARNESS for Layer-1 capabilities:

- `model.ts`: the evaluation scenario types — a Layer-1 evaluation scenario
  declares: the capability under test (reconstruction / depth / capture
  readiness / retrieval), the provider profile reference (a control-plane
  ProviderProfile), the input fixture (normalized ProviderInput), the
  expected canonical outcome (declared against Layer-1's OWN types — e.g.
  the reconstruction engine's output contract, never the provider's), and
  the evaluation criteria (metric thresholds + expected failure kinds from
  the closed vocabulary).
- `harness.ts`: `evaluateScenario(scenario, registryLog)` — pure function:
  normalizes the provider's declared result through the control plane's
  `normalizeResult`, compares against the expected canonical outcome using
  the existing benchmark metrics, and emits a control-plane BenchmarkRecord
  (failure observations from the CLOSED vocabulary only) + a
  ProvenanceManifest. The harness must REFUSE (typed failure) any scenario
  whose provider result carries a provider-specific type into a canonical
  comparison.
- `service.ts` + `router.ts` + `testkit.ts`: the thin HTTP surface (route
  factory mounted by the Lead) + deterministic doubles for tests.
- Deterministic fixture providers: TWO doubles mirroring the HFX-000
  reference-provider pattern — a "fixture-reconstruction-provider" (v1 good:
  passes thresholds; v2 degraded: measurable metrics below threshold +
  documented `perception-failure` + `timeout` behaviors) and a
  "fixture-depth-provider" variant with `unsupported-data` behavior on
  out-of-domain inputs. NO real models.

### 3.2 The benchmark runner (`tools/reality-eval/`)

Following the building-benchmark pattern: `scenario.json` (the committed
scenario set), `fixtures/expected-outcomes.json` (committed golden records —
BenchmarkRecords + manifests), `runner.ts` (executes every scenario through
the harness and byte-compares against the goldens), wired into the root
verify. Include NEGATIVE/discrimination scenarios (the day-27 doctrine):
a provider that silently returns plausible-but-wrong geometry MUST be caught
by the criteria (assert the harness records the failure, not just low
scores).

### 3.3 The Layer-1 fixture map (evidence)

`docs/productization-evidence/PROD-027/`:
- `evaluation-entry-point.md` — the API walkthrough (how HFX-101/102/103/104
  will register, evaluate, benchmark, prove provenance and seek promotion).
- `fixture-map.md` — the Layer-1 capture/readiness/reconstruction gap map:
  which canonical Layer-1 capabilities are evaluable today, which lack
  provider-neutral entry points (the honest gap list with pointers).
- `hardening-report.md` — actionable failures found while building the
  harness (any Layer-1 weakness the negative scenarios exposed), NOT just
  scores.
- `integration-notes.md` — what the Lead wires + what the HFX-1xx items
  consume.

## 4. Module layout

```text
backend/api/src/reality-eval/
  model.ts harness.ts service.ts router.ts testkit.ts index.ts  (+ *.test.ts)
tools/reality-eval/
  README.md scenario.json runner.ts benchmark.test.ts fixtures/
docs/productization-evidence/PROD-027/
  evaluation-entry-point.md fixture-map.md hardening-report.md integration-notes.md
```

`backend/api/package.json` may NOT need changes (reality-eval lives inside
the api workspace; the provider-registry edge already exists). Do NOT edit
`bun.lock`.

## 5. Quality gates (run at your delivery commit)

```bash
bun run verify        # EXPECT: (4742 + N) pass / 0 fail, boundaries clean
bun run typecheck     # PASS
bun run lint          # PASS
```

N is your new-test count; report the exact number. The golden records must
be reproduced by TESTS (byte-compared).

## 6. Delivery — stage INSIDE the workspace-tracked project directory

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

## 7. Completion report (post as your FINAL message)

```text
PROD-027 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Evaluation entry point
- provider-neutral entry: <the harness API, one line>
- control-plane consumption: <BenchmarkRecord + ProvenanceManifest emission, one line>
- canonical-boundary guard: <how provider-specific types are refused, one line>

## Benchmark evidence
- scenarios: <count> (positive / negative / discrimination split)
- golden records reproduced: YES/NO — byte-compared
- negative scenarios catch wrong-but-plausible results: YES/NO — <one line>

## Fixture map
- evaluable Layer-1 capabilities: <list>
- honest gap list: <capabilities lacking provider-neutral entry points>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
