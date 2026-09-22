# PROD-029 — Layer-3 hardening: operation/validation/BOQ substitution fixtures

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-029 (Layer-3 operation/validation/replay/BOQ hardening
  — the provider-neutral evaluation entry point for Layer 3, and the
  operation/validation/BOQ substitution-fixture suite: proving that
  substituting a provider at any Layer-3 seam preserves or honestly
  violates canonical semantics). Do not start PROD-027/028 or any HFX-3xx
  item (explicit non-scope: integrating any REAL provider or agent
  framework; the fixtures here are deterministic in-repo doubles).
- Owned surface (the ONLY files you may create/modify):
  - `backend/api/src/solution-eval/**` (NEW module — see §4)
  - `tools/solution-eval/**` (NEW — the reproducible benchmark runner wired
    into the root verify)
  - `docs/productization-evidence/PROD-029/**` (evidence documents)
- Explicitly NOT yours: `packages/provider-registry/**` (HFX-000's control
  plane — IMPORT, never modify), the Layer-3 canonical modules
  (`packages/solution-contract/**`, `packages/solution-engine/**`,
  `packages/solution-boq/**`, `backend/api/src/solution/**`,
  `backend/api/src/solution-boq/**`, `backend/api/src/reasoning/solution/**`
  — import and CALL, never modify), `backend/api/src/server.ts` +
  `main.ts` (Lead wires), `backend/api/src/reality-eval/**` and
  `backend/api/src/reasoning-eval/**` (PROD-027/028's parallel surfaces),
  `apps/**`, `spec/**` (FROZEN), the root `bun.lock` (Lead regenerates).
- Governing doctrine: providers are implementation candidates, NEVER
  canonical truth. A substituted provider (NL compiler, geometry engine
  adapter, validation provider, BOQ derivation provider) can never change
  operation semantics, validation verdicts or quantity semantics — if it
  produces a different canonical result, the harness must PROVE the
  difference (substitution evidence), not hide it.
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
git checkout -b prod-029/layer3-eval
bun run verify
```

Baseline expectation: **4742 pass / 0 fail, VERIFY: PASS**. If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandated reading (in order, before writing anything)

1. `spec/solution-operation-contract.md` + `spec/governance/architecture-change-record-006.md`
   — Layer-3 requirements: typed engineering operations, proposed vs
   authoritative states, validation before adoption, deterministic replay.
2. `packages/provider-registry/README.md` + `src/index.ts` — the control
   plane you CONSUME (ProviderProfile, registry, normalized I/O, closed
   failure vocabulary, BenchmarkRecord, ProvenanceManifest, testkit
   pattern).
3. `packages/solution-engine/README.md` + `packages/solution-boq/README.md`
   — the canonical Layer-3 seams you substitute AT: the engine
   (applyOperation/replay/revise/quantities), the compiler
   (backend/api/src/reasoning/solution — NL→EngineeringOperationIntent),
   the validator, the BOQ derivation.
4. `docs/productization-layer-hardening-work-orders.md` — the Layer-3 items
   (HFX-301 NL/direct-manipulation semantic equivalence, HFX-302/303
   substitution drills) are your FUTURE consumers; the D26 gate — "no
   provider-specific type reaches canonical graph contracts" — is your
   boundary mandate.
5. `tools/building-benchmark/` — the deterministic runner pattern (and its
   twelve-step journey is a ready-made substitution baseline).
6. `AGENTS.md` — repo conventions.

## 3. The work

### 3.1 The Layer-3 evaluation entry point (`backend/api/src/solution-eval/`)

A provider-neutral SUBSTITUTION-evaluation harness for Layer-3 seams:

- `model.ts`: substitution scenario types — a Layer-3 scenario declares: the
  seam under substitution (operation-compiler / engine-execution /
  validation / BOQ-derivation), the provider profile reference (the
  SUBSTITUTE — a provider-shaped alternative for that seam), the baseline
  fixture (the canonical component's committed golden behavior — e.g. the
  building-benchmark's journey steps), the substituted run (the substitute
  component executing the same scenario through the control plane's
  normalized I/O), and the comparison criteria (canonical equality of
  operation identities / states / verdicts / quantities — or the HONEST
  difference declaration).
- `harness.ts`: `evaluateSubstitution(scenario, registryLog)` — runs the
  baseline path (canonical components) and the substituted path (the
  provider double through the seam), compares CANONICAL outputs
  (operation identities, state digests, validation verdicts, BOQ lines),
  and emits a control-plane BenchmarkRecord + ProvenanceManifest. Equal →
  substitution proven; different → the difference is RECORDED as evidence
  with the right closed-vocabulary failure kind (an operation-semantic-
  failure for identity divergence; a reasoning-failure for verdict
  divergence; contract-mismatch for shape divergence). The harness must
  REFUSE provider-specific types at every canonical comparison point.
- `service.ts` + `router.ts` + `testkit.ts`: thin HTTP surface (Lead wires)
  + doubles.
- Deterministic fixture substitutes (the HFX-301/302 future consumers):
  a "fixture-compiler-provider" (NL→intent: produces the SAME intents as
  the canonical compiler for the corpus utterances + one DIVERGENT intent
  for a discriminator utterance), a "fixture-engine-provider" (operation
  execution: byte-equal state evolution + one subtly-divergent variant),
  a "fixture-validation-provider" (verdicts: agreeing verdicts + one
  disagreeing verdict), a "fixture-boq-provider" (derivation: equal lines +
  one quantity deviation). NO real models.

### 3.2 The benchmark runner (`tools/solution-eval/`)

The building-benchmark pattern: `scenario.json` (the substitution matrix:
4 seams × {equal, divergent} scenarios), committed golden
`fixtures/expected-outcomes.json`, `runner.ts` in the root verify. The
DIVERGENT scenarios are the point (day-27 doctrine): each must be CAUGHT
with the right failure kind — a harness that only proves the happy path is
a failed delivery.

### 3.3 Substitution evidence (docs)

`docs/productization-evidence/PROD-029/`:
- `evaluation-entry-point.md` — the API walkthrough (how HFX-301/302/303
  consume it).
- `substitution-matrix.md` — the full seam × scenario matrix with the
  canonical-equality verdict per cell.
- `divergence-analysis.md` — each divergent fixture: what diverged, why it
  is a provider error (not a canonical ambiguity), the failure kind
  recorded.
- `hardening-report.md` — actionable Layer-3 weaknesses the divergent
  scenarios exposed (e.g. ambiguities a substitute could exploit).
- `integration-notes.md` — Lead wiring + HFX-3xx consumption notes.

## 4. Module layout

```text
backend/api/src/solution-eval/
  model.ts harness.ts service.ts router.ts testkit.ts index.ts  (+ *.test.ts)
tools/solution-eval/
  README.md scenario.json runner.ts benchmark.test.ts fixtures/
docs/productization-evidence/PROD-029/
  evaluation-entry-point.md substitution-matrix.md divergence-analysis.md hardening-report.md integration-notes.md
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
PROD-029 COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Evaluation entry point
- substitution harness: <the API, one line>
- canonical comparison points: <the seams × compared outputs, one line>
- canonical-boundary guard: <one line>

## Substitution matrix (the D26/27 gates)
- seams covered: <list>
- equal substitutions proven: <count — canonical outputs byte-equal>
- divergent substitutions CAUGHT: <count — each with the right closed-vocabulary failure kind>
- provider-specific types reaching canonical contracts: ZERO — <one line proof>

## Divergence analysis
- <per divergent fixture: what diverged + the recorded failure kind, one line each>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
