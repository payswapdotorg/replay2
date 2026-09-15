# WORK ORDER — W803 Visual quality gates (session A dispatch)

You are a senior TypeScript engineer completing work item **W803 — Visual quality
gates** in the sporta monorepo. Owner: AI. Dependencies (both COMPLETE and
merged): W503 (`@sporta/renderer-evaluation`), W605 (`@sporta/scene-evaluation`).

**Acceptance (verbatim from docs/work-items/work-items.md):** release gates
include temporal stability, scene correctness, and human/automated quality
checks.

## Mechanics

- Repo: `https://github.com/payswapdotorg/sporta` (public to clone).
- Base: `__BASE__` (origin/main at dispatch — includes the W605 merge).
- Branch: `w803-visual-quality-gates` off that base. Push with:
  `git push https://x-access-token:__PAT__@github.com/payswapdotorg/sporta.git HEAD:w803-visual-quality-gates`
  (never write the token anywhere else, never commit it).
- Scope: ONLY the new `packages/quality-gates/` (src, test, docs, package.json,
  tsconfig.json) plus the one-line workspace addition in the root `package.json`
  work array if the convention requires it, plus `bun.lock` regenerated via
  `bun install`. ZERO touches to any other package's src/test/spec.
- Battery (all must pass, in this order): `bun install` → per-package typecheck
  (run `bun run typecheck` from the repo root if it propagates; if exit codes
  are unreliable, run `bunx tsc --noEmit` per package and `grep -c "error TS"`
  must be 0 everywhere) → `bun run lint` → `bun run format:check` → `bun test`.
- Finish with the full battery green, push the branch, and print your
  completion report. The LAST line of your final message must be exactly:
  `SPORTA-COMPLETION-REPORT W803 END`

## The delivery

Create `@sporta/quality-gates` — the release gate suite that composes the REAL
evaluations of the two completed evaluation packages into one release verdict.
You import and run their real public APIs; you re-implement NOTHING.

### 1. Gate composition (the core)

A release evaluation over the repo's real fixtures that runs, as discrete
accounted gates:

- **Temporal stability gate** — `@sporta/renderer-evaluation`'s real
  evaluation (the `evaluateRenderOutput` / `evaluateTemporalConsistency`
  family) over its real fixture clip, producing its real report; the gate
  verdict is that report's own verdict. Thresholds are REFERENCED from that
  package's pinned `thresholds.ts`/`THRESHOLDS.md` — this package defines
  ZERO new numeric thresholds for it.
- **Scene correctness gate** — `@sporta/scene-evaluation`'s real public
  evaluation over its real fixture(s), producing its real report and verdict.
  Read the merged package first: use whatever its public API actually is
  (report type, verdict field, fixture entry points). If names differ from
  any example in this document, the MERGED CODE is the truth — the
  requirement is running the real thing, not name-matching this text.
- **Human quality checks gate** — fail-closed human review. You provide:
  (a) a documented checklist (docs/REVIEW.md — what a human reviews: one
  rendered clip per renderer path visually inspected, the gate report read,
  sign-off fields); (b) a checked-in review RECORD format (JSON: reviewer,
  date, per-checklist-item result, notes — bounded); (c) the gate logic: a
  missing, malformed, or incomplete record makes the release verdict
  `PENDING-HUMAN-REVIEW` — never PASS, never silently skipped. Include one
  honestly-completed record for the fixture-based demo run, clearly marked
  as the automated-pipeline self-check record, NOT a claim that a human
  reviewed production output.
- **Accounting gate** — the never-silent ledger: total gates, per-gate
  verdicts, gates that could not run (missing input, package error) count as
  `FAIL` with the reason — a release evaluation where a gate silently
  vanishes is itself a failure.

### 2. The release report

`evaluateReleaseReadiness(...)` — pure, deterministic (same input →
byte-identical JSON report; test-pinned twice in one process AND across two
subprocess invocations with compared stdout hashes). Structure: gate rows
(name, source package, verdict, key measured values carried VERBATIM from the
source reports, accounted reason when not runnable), the human-review section,
the accounting table (counts reconcile exactly: gates = pass + fail +
not-runnable), and the overall verdict: `PASS` only when every blocking gate
passes AND the human record is complete; `PENDING-HUMAN-REVIEW` when machine
gates pass but the human record is absent/incomplete; `FAIL` otherwise.
Gate policy (which gates are blocking vs advisory) is a versioned DATA
document (docs/GATES.md) pinned to code by test both directions — no policy
in scattered ifs.

### 3. CLI + detection proofs

`bun run gate` (scripts/gate.ts): runs the release evaluation over the
fixtures, writes the deterministic report, prints the verdict and the literal
marker line `SPORTA-RELEASE-GATE <verdict>`. Tests must PROVE the gate bites
(test/): a temporal defect injected through the real injector seam → overall
FAIL; a scene defect injected the way the scene-evaluation package's own
tests inject (read them; if it has no injector, construct the minimal
malformed input its own validation rejects) → FAIL; human record removed →
PENDING-HUMAN-REVIEW; a gate made not-runnable (e.g. malformed fixture
input) → counted FAIL, never skipped; accounting totality (counts reconcile);
determinism byte-identical ×2; report cross-subprocess SHA-256 stable.

### 4. Honesty boundaries (document in docs/GATES.md §boundaries)

- Machine gates measure what W503/W605 measure — nothing more; this package
  adds no new quality metrics, only composition + policy + accounting.
- The human gate records that review HAPPENED and WHAT was checked — it
  cannot verify review QUALITY; the demo record is a pipeline self-check,
  not a human attestation.
- No new thresholds anywhere (the roadmap's rule: a number without measured
  evidence is an aspiration, not an SLO — and not a gate).
- The suite evaluates fixtures, not production traffic.

## Style (the house rules — violations are merge-blocking)

Fail-closed everywhere (unknown shapes throw typed errors with JSON paths,
never silently coerced); never-silent accounting; pure functions + injected
seams (no wall clock, no Math.random, no network); deterministic outputs;
every threshold/policy value documented and pinned to code by test; boundary
isolation test (imports only the declared @sporta/* deps + relative paths);
honest limitations documented, never invented claims. Read
`packages/camera-director/POLICY.md` and `packages/slo/` for the house idiom
of versioned policy data documents if you need a model.
