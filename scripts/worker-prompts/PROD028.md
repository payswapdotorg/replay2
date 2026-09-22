# PROD-028 — Layer-2 hardening: Evidence Envelope/reasoning evaluation entry point

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-028 (Layer-2 Evidence Envelope/reasoning/tool-policy
  hardening — the provider-neutral evaluation entry point for Layer 2, the
  Evidence Envelope benchmark fixture map, and the
  multimodal/document/retrieval evaluation lanes). Do not start
  PROD-027/029 or any HFX-2xx item (explicit non-scope: integrating any
  REAL provider — Qwen3-VL/PaddleOCR/SigLIP are FUTURE consumers; the
  fixtures here are deterministic in-repo doubles).
- Owned surface (the ONLY files you may create/modify):
  - `backend/api/src/reasoning-eval/**` (NEW module — see §4)
  - `tools/reasoning-eval/**` (NEW — the reproducible benchmark runner wired
    into the root verify)
  - `docs/productization-evidence/PROD-028/**` (evidence documents)
- Explicitly NOT yours: `packages/provider-registry/**` (HFX-000's control
  plane — IMPORT `@aise/provider-registry`, never modify it), the existing
  Layer-2 modules (`backend/api/src/reasoning/**`, `evidence/**`,
  `semantics/**`, `benchmarks/**` — read/import, never modify),
  `backend/api/src/server.ts` + `main.ts` (Lead wires),
  `backend/api/src/reality-eval/**` and `backend/api/src/solution-eval/**`
  (PROD-027/029's parallel surfaces), every other package, `apps/**`,
  `spec/**` (FROZEN), the root `bun.lock` (Lead regenerates).
- Governing doctrine: providers are implementation candidates, NEVER
  canonical truth. Agents/providers may propose, retrieve, explain — they
  can NEVER become readiness, verification, geometry or evidence
  authorities (ACR-006). No provider-specific type crosses the canonical
  boundary; native payloads stay opaque.
- PURE DETERMINISTIC COMPUTATION: no network, no clock reads, no randomness.
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
git checkout -b prod-028/layer2-eval
bun run verify
```

Baseline expectation: **4742 pass / 0 fail, VERIFY: PASS**. If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandated reading (in order, before writing anything)

1. `spec/governance/architecture-change-record-006.md` — Layer-2
   requirements: the Evidence Envelope (every consequential reasoning result
   carries intent, authorized context, evidence IDs, facts, assumptions,
   unknowns, uncertainty, deterministic checks, result status, invalidation
   conditions, agent/provider identity), agents as bounded proposers.
2. `packages/provider-registry/README.md` + `src/index.ts` — the control
   plane you CONSUME (ProviderProfile, registry, normalized I/O, closed
   failure vocabulary, BenchmarkRecord, ProvenanceManifest, testkit
   pattern).
3. `docs/productization-layer-hardening-work-orders.md` — Layer-2 items
   (HFX-201 Qwen3-VL, HFX-202 PaddleOCR/PP-DocLayout, HFX-203 SigLIP/
   STELLAR, HFX-204 IFC-Bench/BIM-Edit) are your FUTURE consumers: design
   their entry points, do not implement them. The HF-2 exit gate — "the
   benchmark suite can distinguish perception, retrieval, reasoning,
   unsupported-data and operation-semantic failures" — is YOUR failure-
   discrimination mandate.
4. `backend/api/src/reasoning/solution/` (PROD-023's compiler — the
   refusal/clarification taxonomy is a Layer-2 artifact worth referencing)
   and `backend/api/src/evidence/` (the canonical Evidence Graph types).
5. `backend/api/src/benchmarks/model.ts` — the existing benchmark engine.
6. `tools/building-benchmark/` — the deterministic runner pattern.
7. `AGENTS.md` — repo conventions.

## 3. The work

### 3.1 The Layer-2 evaluation entry point (`backend/api/src/reasoning-eval/`)

A provider-neutral evaluation HARNESS for Layer-2 reasoning capabilities,
with the Evidence Envelope as the evaluation TARGET:

- `model.ts`: evaluation scenario types — a Layer-2 scenario declares: the
  lane (multimodal-reasoning / document-understanding / retrieval), the
  provider profile reference, the input fixture (normalized ProviderInput
  carrying an evidence-question bundle), the expected Evidence-Envelope-
  shaped outcome (observed facts, inferred assumptions, unknowns,
  deterministic checks invoked, result claim + status, invalidation
  conditions — declared against the CANONICAL envelope semantics, never the
  provider's), and evaluation criteria.
- `harness.ts`: `evaluateScenario(scenario, registryLog)` — normalizes the
  provider's declared result, maps it ONTO the canonical Evidence Envelope
  shape, and emits a control-plane BenchmarkRecord + ProvenanceManifest.
  The harness must verify the envelope's integrity rules (every claim
  carries evidence IDs; assumptions are explicit; unknowns are explicit;
  agent/provider identity recorded) and record violations as the CLOSED
  failure vocabulary — NOT new vocabulary.
- Failure-discrimination lanes (the HF-2 exit gate): the harness must be
  able to DISTINGUISH `perception-failure` vs `retrieval-failure` vs
  `reasoning-failure` vs `unsupported-data` vs `operation-semantic-failure`
  — each lane's fixtures produce at least one scenario exhibiting each
  applicable failure kind, and the harness's classification is asserted
  (a provider answering from wrong evidence is a retrieval failure, not a
  reasoning failure; a provider refusing out-of-scope data is
  unsupported-data, not a perception failure).
- `service.ts` + `router.ts` + `testkit.ts`: thin HTTP surface (Lead wires)
  + deterministic doubles.
- Deterministic fixture providers: a "fixture-vlm-provider" (multimodal
  lane: correct answers / hallucinated-but-plausible answers / refusals),
  a "fixture-doc-provider" (document lane: correct extraction / missed
  fields / wrong-section attributions), a "fixture-retrieval-provider"
  (retrieval lane: correct hits / near-miss hits / empty results). NO real
  models.

### 3.2 The benchmark runner (`tools/reasoning-eval/`)

The building-benchmark pattern: `scenario.json`, committed golden
`fixtures/expected-outcomes.json`, `runner.ts` in the root verify. Include
NEGATIVE/discrimination scenarios: a provider that hallucinates plausible
answers MUST be caught (envelope integrity violation + the right failure
kind); a provider that answers from the wrong evidence MUST be classified
as retrieval-failure. Assert classifications, not just scores.

### 3.3 The Evidence Envelope fixture map (evidence)

`docs/productization-evidence/PROD-028/`:
- `evaluation-entry-point.md` — the API walkthrough (how HFX-201/202/203/204
  consume it).
- `envelope-fixture-map.md` — which canonical envelope fields are
  evaluable today per lane; the honest gap list.
- `failure-discrimination.md` — the five-way discrimination proof (scenario
  → observed failure kind → why not the neighboring kinds).
- `hardening-report.md` — actionable envelope/reasoning weaknesses the
  negative scenarios exposed.
- `integration-notes.md` — Lead wiring + HFX-2xx consumption notes.

## 4. Module layout

```text
backend/api/src/reasoning-eval/
  model.ts harness.ts service.ts router.ts testkit.ts index.ts  (+ *.test.ts)
tools/reasoning-eval/
  README.md scenario.json runner.ts benchmark.test.ts fixtures/
docs/productization-evidence/PROD-028/
  evaluation-entry-point.md envelope-fixture-map.md failure-discrimination.md hardening-report.md integration-notes.md
```

Do NOT edit `backend/api/package.json` or `bun.lock`.

## 5. Quality gates (run at your delivery commit)

```bash
bun run verify        # EXPECT: (4742 + N) pass / 0 fail, boundaries clean
bun run typecheck     # PASS
bun run lint          # PASS
```

N is your new-test count; report the exact number.

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
PROD-028 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Evaluation entry point
- provider-neutral entry: <the harness API, one line>
- envelope integrity verification: <the rules the harness enforces, one line>
- canonical-boundary guard: <one line>

## Failure discrimination (the HF-2 exit gate)
- five-way discrimination: <per failure kind: scenario → classification, one line each>
- hallucination caught: YES/NO — <one line>
- wrong-evidence classified as retrieval: YES/NO — <one line>

## Fixture map
- evaluable envelope fields per lane: <list>
- honest gap list: <fields/lanes lacking provider-neutral entry points>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
