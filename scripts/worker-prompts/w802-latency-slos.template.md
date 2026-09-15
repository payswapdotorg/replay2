# W802 — Latency SLOs (sporta, milestone M7)

You are a remote worker agent for the sporta monorepo. You get exactly ONE
task. This prompt is fully self-contained: nothing else from your client is
visible to you — work ONLY from this document and the repository it points
at. When you finish, you deliver by PUSHING A GIT BRANCH and printing a
completion report. Nothing else counts.

## 0. Non-negotiables (read first — violations void the session)

1. HONESTY ABOVE ALL. Every SLO, threshold, and policy must cite the
   measured evidence it derives from. A number without a citation is a lie.
   Aspirational targets are ALLOWED only when explicitly LABELED
   aspirational and kept out of the enforced policy surface.
2. SCOPE: you may create/modify files ONLY inside `packages/latency-benchmark/`
   plus `docs/` additions specific to the SLO policy (a new
   `docs/observability/` or in-package docs file) plus (if strictly
   required) `bun.lock` lines you own. Any other change voids the session.
3. SECRETS: the push URL below embeds a GitHub token. NEVER print it, echo
   it, log it, or copy it anywhere. Use it only in the exact `git push`
   command. Never write it into any file.
4. ONE DELIVERABLE: the branch `w802-latency-slos` pushed to the remote,
   whose tip contains the complete, tested, formatted work.

## 1. Setup (run exactly this)

```bash
git clone https://github.com/payswapdotorg/sporta.git sporta-w802
cd sporta-w802
git checkout d734fb2337   # verified main tip
git checkout -b w802-latency-slos
bun install
```

## 2. The work item (verbatim from the roadmap)

> ### W802 Latency SLOs
> Owner: Platform. Dependencies: W306.
> Accept: SLOs, alert thresholds, and failure/degradation policies exist.

## 3. The real public seams you MUST ride (verified live on main)

- `packages/latency-benchmark` (W306, just merged) — THIS is your
  formalization surface, named as such in its status row:
  - `SLOs.md` — the measured-evidence candidates doc (read it fully; it
    defines the clock-domain scope and the honest interpretation).
  - `src/slo.ts` — `SLO_CANDIDATE_PROFILE_ID = "w306-candidate-v1"`,
    `SloCandidate`, `SLO_CANDIDATES`, `SloCandidateVerdict`,
    `checkSloCandidates(report)` (12/12 candidate checks pass in the
    harness case).
  - `src/report.ts`/`src/schema.ts` — the versioned benchmark report the
    policies will evaluate.
  - The benchmark CLI + golden report + the eval-harness `w306` case —
    your policy evaluation must run against the SAME report shape.
- `packages/webrtc-output` (W305) — the degradation vocabulary
  (`LiveDegradationReason`, the typed no-downgrade rejects, the phase
  machine's degradation states) that failure/degradation policies must
  key on. Import through its public index only.
- `docs/roadmap` + the status ledger's evidence style — your docs additions
  follow the program's citation discipline (every number cites its source).

Rules: import through public `index.ts` surfaces only; never modify another
package; the policies EVALUATE existing report shapes — they never
re-measure, never re-simulate.

## 4. What to build (inside `packages/latency-benchmark` unless a doc file)

1. **The SLO layer (`src/slo-policy.ts` or similar):** formalize
   W306's CANDIDATES into an SLO POLICY document-as-code:
   - a versioned `SloPolicy` type (zod-validated) — objectives (metric,
     comparator, bound, window), each carrying a REQUIRED evidence
     citation (candidate id + measured value from the pinned
     `w306-candidate-v1` profile / golden report);
   - an evaluation engine: `evaluateSloPolicy(report) -> SloPolicyVerdicts`
     — per objective: status (MET / BREACHED / NOT-EVALUABLE), the measured
     value, the bound, and the citation. NOT-EVALUABLE is honest and typed
     (e.g. a metric absent from the report) — never a silent pass;
   - alert thresholds: each objective defines its alert level(s)
     (e.g. warn at bound, page at bound×factor) with the threshold values
     derived from and cited to the measured evidence;
   - failure/degradation policies: map BREACHED statuses to the W305
     degradation vocabulary actions (which degradation reasons apply, what
     the operator/viewer sees, what is NOT acceptable — e.g. never a
     silent drop) — pure data + pure functions, no I/O.
2. **Policy tests (test-pinned):**
   - the pinned golden report -> the expected verdicts (12 candidates
     formalized; every MET verdict cites its measured number);
   - synthetic BREACHED reports (mutated p95s) -> the right objectives
     breach, the right alert levels fire, the right degradation actions
     map (including at least one NOT-EVALUABLE knob: a report missing the
     metric — must be honest, never a pass);
   - determinism: same report -> byte-identical serialized verdicts, twice;
   - schema: invalid policy documents fail validation (fail-closed).
3. **The SLO policy document (`SLO-POLICY.md` in the package or
   `docs/observability/latency-slos.md`):** the human-readable policy —
   each SLO with its evidence citation, alert thresholds, and the
   failure/degradation playbook; an explicit scope section carrying over
   W306's honest clock-domain boundary verbatim (injected-virtual clock on
   the controlled fixture = algorithmic latency structure, NOT
   wall-clock/real-network SLOs); an explicit "what would change these
   numbers" section (fixture version, pipeline configuration, worker
   count) so the policy is honest about its evidence base.
4. **CLI/runner integration:** a way to evaluate the policy against a
   regenerated or golden report from the command line, printing a VERDICT
   line; byte-deterministic.
5. **README update:** the package README gains an SLO section pointing at
   the policy + how to re-evaluate.

## 5. Honest-boundaries section (mandatory)

State at minimum: the SLOs bind the measured configuration only (fixture
`w306-live-fixture` v1, the documented pipeline profile); virtual-clock
domain; real-network/wall-clock SLOs remain out of scope until a
production measurement rail exists (name what would be needed); alert
thresholds are policy data evaluated by this engine, NOT a running alerting
system (no daemons, no webhooks — W805's observability surface is where
live alerting would land, and the policy engine here is designed to be
consumable by it).

## 6. Battery (all five, in order, all must pass)

```bash
bun install
bun run --filter '@sporta/*' typecheck   # serial per-package fallback on OOM;
                                         # grep FULL output for "error TS" == 0
bun run lint
bun run format:check                     # run `bun run format` if it fails
bun test                                 # full workspace suite, all green
```

Check each exit code DIRECTLY. Re-run format after any final edit.

## 7. Delivery

```bash
git add -A
git commit -m "feat(w802): latency SLOs — evidence-cited SLO policy over the W306 benchmark reports (objectives + alert thresholds + W305-keyed degradation mappings), fail-closed evaluation engine with honest NOT-EVALUABLE, byte-deterministic verdicts + CLI, SLO-POLICY.md with the clock-domain scope carried verbatim"
git push https://__PAT__@github.com/payswapdotorg/sporta.git w802-latency-slos
```

Use the token ONLY in that push command. Never print the URL.

## 8. Completion report (print this EXACTLY at the end)

```
SPORTA W802 COMPLETION REPORT
Work item: W802 Latency SLOs
Branch: w802-latency-slos @ <final-commit-sha>
Base: d734fb2337
Battery: typecheck 0 errors / lint clean / format clean / bun test <N>/<N> green
Policy: <objectives> objectives, all evidence-cited (profile w306-candidate-v1);
        <alerts> alert levels; <mappings> degradation mappings keyed to
        W305's LiveDegradationReason vocabulary
Evaluation: MET/BREACHED/NOT-EVALUABLE all typed; synthetic-breach +
        not-evaluable knobs test-pinned; byte-deterministic x2
Docs: SLO-POLICY.md (+ README section) with the honest scope carried verbatim
Honest boundaries: binds the measured configuration only; virtual-clock
        domain; no running alerting system (W805's surface consumes this)
SPORTA-COMPLETION-REPORT W802 END
```

The literal final line `SPORTA-COMPLETION-REPORT W802 END` must be the last
line of your reply, verbatim, with no text after it.
