# W605 — 3D output evaluation (sporta, milestone M6 completion)

You are a remote worker agent for the sporta monorepo. You get exactly ONE
task. This prompt is fully self-contained: nothing else from your client is
visible to you — work ONLY from this document and the repository it points
at. When you finish, you deliver by PUSHING A GIT BRANCH and printing a
completion report. Nothing else counts.

## 0. Non-negotiables (read first — violations void the session)

1. HONESTY ABOVE ALL. Never claim a check passed that you did not run. The
   tech lead re-runs every battery command personally; false reports are
   detected and void the session.
2. SCOPE: you may create/modify files ONLY inside `packages/output-evaluation/`
   plus (if strictly required) `bun.lock` workspace registration lines. Any
   other change voids the session — in particular do NOT modify
   eval-harness, renderer-3d, camera-director, scene-projection, or any
   other package, even "to make measuring easier".
3. SECRETS: the push URL below embeds a GitHub token. NEVER print it, echo
   it, log it, or copy it anywhere. Use it only in the exact `git push`
   command. Never write it into any file.
4. ONE DELIVERABLE: the branch `w605-3d-output-evaluation` pushed to the
   remote, whose tip contains the complete, tested, formatted package.

## 1. Setup (run exactly this)

```bash
git clone https://github.com/payswapdotorg/sporta.git sporta-w605
cd sporta-w605
git checkout d734fb2337   # verified main tip (docs row "W704 COMPLETE — M5 GATE 7/7")
git checkout -b w605-3d-output-evaluation
bun install
```

If `bun install` fails on lockfile drift, run `bun install` again after
adding your package's workspace entry; never hand-edit unrelated lock lines.

## 2. The work item (verbatim from the roadmap)

> ### W605 3D output evaluation
> Owner: AI. Dependencies: W604.
> Accept: correctness of score, clock, player identity continuity, event
> ordering, and scene state is benchmarked.

## 3. The real public seams you MUST ride (verified live on main)

- `packages/scene-projection` (W601) — the SWM→scene projection contract;
  the eval-harness already carries a W601 case + `buildW601SceneFixture`
  (its `w601-fixture.ts`) you can study as the fixture precedent.
- `packages/renderer-3d` (W602/W603) — the deterministic 3D render path:
  `render3dMatch` (with the W603 interpolation profiles) and its per-frame
  manifests carrying the disposition vocabulary. The frame manifest + scene
  blocks are your ground-truth comparison surface.
- `packages/camera-director` (W604) — `direct()` plans with per-window
  DECISION RECORDS (`planDecisionRecords`), `checkCameraPlan` selfcheck, and
  `render3dDirectedMatch`/`REVIEW_OUTPUT_PROFILE` composing directed
  rundowns through the renderer's own `styleConfig.config.cameraSlotId`
  seam. The W604 status row calls these decision records "the W605
  evaluation surface".
- `packages/eval-harness` (W403/W801/W306) — the suite framework:
  `CaseVerdict`/`CaseOutcome`/`CaseContext` (src/cases/types.ts), the named
  case registry (w403/w503/w601/w306 case modules), `runSuite` +
  `serializeSuiteReport` + `assertSuiteReportShape`, the injected
  `SuiteClock`, `measurePackageVersions`/`ENVIRONMENT_PACKAGE_KEYS`, and the
  golden-report pattern. Study how the W306 case wraps
  `@sporta/latency-benchmark` — your integration follows that precedent.
- `packages/renderer-evaluation` — the W503-era threshold/tolerance
  precedent (`W403_TOLERANCE_DOCUMENT` in the harness shows the style).

Rules for seam use: import through each package's public `index.ts` only
(`@sporta/...` workspace deps); never reach into `src/**` of another
package; never modify another package. If something you need is not
observable through a public seam, record it as a documented limitation.

## 4. What to build: `packages/output-evaluation`

A benchmark package that measures OUTPUT CORRECTNESS of the 3D chain
(SWM → scene projection → renderer-3d → camera-directed rundown) against
the SWM ground truth, on controlled fixtures, deterministically:

1. **Correctness axes (the acceptance core — all five, each with its own
   metric definition, fixtures, and verdicts):**
   - **Score correctness** — the score carried in rendered output/manifests
     at time T equals the SWM ground-truth score at T (every scoring event
     reflected, no phantom changes between events).
   - **Clock correctness** — rendered clock at T matches the SWM clock at T
     (monotone, advances only at snapshot boundaries per the W603 contract,
     never ticks by frame time).
   - **Player identity continuity** — an entity present across consecutive
     frames keeps a stable identity; entries/absences are accounted by the
     disposition vocabulary, never silently swapped or invented.
   - **Event ordering** — events in the output respect the SWM timeline
     order (including the W603 held/discontinuity semantics and the W604
     review-window re-presentation — evaluated against the plan's declared
     windows, not raw chronology).
   - **Scene state** — projected scene state at T (positions, dispositions,
     carried verbatim claims) matches the SWM `stateAt(T)` ground truth
     through the projection contract's own conformance rules.
2. **Ground-truth fixtures** — a small set of deterministic SWM fixtures
   (you may derive from the W601 fixture precedent + the renderer-3d test
   fixtures' shapes) including: a clean-match case, a
   discontinuity/heavy-corrections case, a review-window directed case
   (W604), and at least one adversarial fixture per axis (a mutated output
   that MUST fail that axis — the discrimination proof: a benchmark that
   cannot fail is not a benchmark).
3. **Exact, honest metrics** — per-axis pass/fail with named violation ids
   (which frame, which entity, which expected-vs-actual), counts and worst
   cases; NO approximate scoring, NO partial credit unless the axis's
   definition explicitly defines it (then document it). Never-silent
   accounting: every evaluated frame/window lands in exactly one of
   {evaluated, skipped(with reason — e.g. outside fixture window), error
   (typed)}.
4. **Determinism** — the full evaluation run twice from the same pinned
   state produces BYTE-IDENTICAL reports (assert on serialized bytes).
   Event-influence probe: a fixture variant with a known ground-truth
   perturbation must change the verdict/metrics (proves the benchmark
   actually reads its inputs).
5. **Versioned, machine-readable report + CLI** — zod-validated report
   document (schema-tagged like the harness's REPORT_SCHEMA_TAG pattern),
   a human summary rendering, and a CLI that regenerates the report and
   prints a VERDICT line. Same input → byte-identical output.
6. **Tests** — unit tests per axis (happy + adversarial), the determinism
   byte-identity, the deviation probes, the accounting reconciliation
   (each negative knob fails its axis), and the report schema round-trip.
7. **README.md** — what is measured, the five axis definitions verbatim,
   what is deliberately NOT measured (human-perceived visual quality — that
   is W803's territory; broadcast-pixel comparison — explicitly out of
   scope per the program's synthetic-asset posture; real-GPU timing),
   fixture inventory, how to re-run.

## 5. Honest-boundaries section (mandatory in the README)

State at minimum: correctness is evaluated against the SWM's OWN claims
(the SWM is ground truth by program definition — if the SWM is wrong the
benchmark cannot know); identity continuity is evaluated within the
disposition vocabulary's expressiveness; the review-window axis evaluates
the W604 plan's declared semantics (re-presentation), not cinematic
quality; everything runs on the injected-clock domain; sample sizes per
axis per fixture.

## 6. Battery (all five, in order, all must pass)

```bash
bun install
bun run --filter '@sporta/*' typecheck   # if the parallel root run OOMs, run
                                         # per-package serially; grep the FULL
                                         # output for "error TS" — count MUST be 0
bun run lint
bun run format:check                     # prettier; run `bun run format` if it fails
bun test                                 # full workspace suite, all green
```

Battery discipline: check each command's exit code DIRECTLY (the root
typecheck script does not propagate per-package failures — grep for
`error TS` yourself). Re-run format after any final edit.

## 7. Delivery

```bash
git add -A
git commit -m "feat(w605): output-evaluation — five-axis 3D-output correctness benchmark (score/clock/identity-continuity/event-ordering/scene-state) over the real W601-W604 public seams, adversarial fixtures per axis, never-silent accounting, byte-deterministic versioned reports + CLI"
git push https://__PAT__@github.com/payswapdotorg/sporta.git w605-3d-output-evaluation
```

Use the token ONLY in that push command. Never print the URL. If the push
is rejected, re-run it; do not rewrite history.

## 8. Completion report (print this EXACTLY at the end)

```
SPORTA W605 COMPLETION REPORT
Work item: W605 3D output evaluation
Branch: w605-3d-output-evaluation @ <final-commit-sha>
Base: d734fb2337
Battery: typecheck 0 errors / lint clean / format clean / bun test <N>/<N> green
Package: packages/output-evaluation (<files> files, <tests> tests)
Axes: score / clock / identity-continuity / event-ordering / scene-state —
      each defined, fixtured, adversarially discriminated
Accounting: <frames> frames + <windows> windows evaluated, <skipped> skipped
      (reasoned), <errors> typed errors — ledger reconciled
Determinism: byte-identical x2; deviation probes change verdicts
Honest boundaries: SWM-is-ground-truth scope; disposition-vocabulary
      expressiveness; review-window semantics per W604 plan; injected clock
SPORTA-COMPLETION-REPORT W605 END
```

The literal final line `SPORTA-COMPLETION-REPORT W605 END` must be the last
line of your reply, verbatim, with no text after it.
