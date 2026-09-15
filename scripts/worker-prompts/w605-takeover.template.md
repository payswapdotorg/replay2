# WORK ORDER — W605 3D output evaluation (session A takeover flight — audit-first completion)

You are a senior TypeScript engineer completing work item **W605 — 3D output
evaluation** in the sporta monorepo. Owner: AI. Dependency W604 COMPLETE.
This is an AUDIT-FIRST COMPLETION flight: two prior flights died and their
WIP is preserved on the branch — you inherit it, audit every line, finish it.

**Acceptance (verbatim from docs/work-items/work-items.md):** correctness
of score, clock, player identity continuity, event ordering, and scene state
is benchmarked.

## Mechanics

- Repo: `https://github.com/payswapdotorg/sporta` (public to clone).
- Base: `__BASE__` (current origin/main). ALSO merge the preserved WIP
  branch `w605-3d-output-evaluation` (tip `__WIP__`) into your working
  branch first — it carries flights 1-2: `packages/scene-evaluation` with
  11 src modules (truth/expected/findings/identity/scoreClock/validate/
  errors/internal + direction/ordering/sceneState), ~1.3k lines, NO tests
  yet, no index.ts barrel. If bun.lock or config conflicts arise, take
  main's side and regenerate (`bun install`).
- Your branch: `work/sa-w605-flight4`. Push with:
  `git push https://x-access-token:__PAT__@github.com/payswapdotorg/sporta.git HEAD:work/sa-w605-flight4`
  (never write the token anywhere else, never commit it).
- Scope: ONLY `packages/scene-evaluation/` (src, test, docs, package.json,
  tsconfig.json) + workspace registration + `bun.lock`. ZERO touches to any
  other package.
- Battery (all green, in order): `bun install` → per-package typecheck
  (serial; `grep -c "error TS"` == 0 everywhere — root exit codes do not
  propagate reliably) → `bun run lint` → `bun run format:check` → `bun test`.
- The LAST line of your final message must be exactly:
  `SPORTA-COMPLETION-REPORT W605 END`

## The audit (do this FIRST, before writing anything)

Read every inherited module. For each: does it honor the acceptance surface
(score / clock / identity continuity / event ordering / scene state)? Is it
fail-closed (malformed inputs throw typed errors with JSON paths, never
silent skips)? Is its accounting never-silent? Fix what is broken — pinned
by tests. The preserved modules are the STARTING POINT: keep what is right,
repair what is not, and say so in your report.

## The completion

1. **Public API** (`src/index.ts` barrel + types): a scene-evaluation report
   type carrying, per dimension (score, clock, identity, ordering,
   scene-state, direction, source-truth), the measured values, the findings
   (the inherited `SceneEvaluationFinding` shape), and a verdict. Pure and
   deterministic (same input → byte-identical report; no wall clock, no
   randomness, no network).
2. **Fixture**: a checked-in deterministic fixture exercising the REAL
   seams — the W601 `projectScene` ground truth and the real renderer-3d
   composed output (the camera-director `compose render3dDirectedMatch` /
   `render3dMatch` surface, whichever the merged code exposes) — evaluated
   end to end.
3. **Test suite** (this is the main missing piece — flights 1-2 shipped
   none): every dimension covered; injected-defect detection proofs (a
   wrong score, a stuck clock, an identity swap, an out-of-order event, a
   scene-state mismatch, a mis-directed window each FLIP the verdict);
   never-silent accounting (every finding counted, truncation accounted);
   determinism (report byte-identical ×2 in-process AND across two
   subprocesses, SHA-256 compared); boundary isolation (imports only the
   declared @sporta/* deps + relative paths).
4. **CLI + docs**: `bun run evaluate` (scripts/) over the fixture →
   deterministic report + printed verdict; README.md with the honest
   boundary list (what is measured, what is NOT — e.g. pixel-level checks,
   real 3D engine output, live evaluation are out of scope; this is
   manifest/state-level benchmarking over the deterministic pipeline).

## Style (the house rules — violations are merge-blocking)

Fail-closed everywhere; never-silent accounting; pure functions + injected
seams; deterministic outputs; honest limitations documented; no invented
claims; no new dependencies beyond the workspace.
