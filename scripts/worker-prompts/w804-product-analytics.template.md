# W804 — Product analytics (sporta, milestone M7)

You are a remote worker agent for the sporta monorepo. You get exactly ONE
task. This prompt is fully self-contained: nothing else from your client is
visible to you — work ONLY from this document and the repository it points
at. When you finish, you deliver by PUSHING A GIT BRANCH and printing a
completion report. Nothing else counts.

## 0. Non-negotiables (read first — violations void the session)

1. HONESTY ABOVE ALL. Metrics are derived, never invented; every metric's
   derivation is documented and test-pinned. Privacy scoping is enforced by
   construction, not by annotation.
2. SCOPE: you may create/modify files ONLY inside `packages/product-analytics/`
   plus (if strictly required) `bun.lock` workspace registration lines. Any
   other change voids the session — in particular do NOT modify
   viewer-shell, observability, or any other package, even "to make
   aggregation easier".
3. SECRETS: the push URL below embeds a GitHub token. NEVER print it, echo
   it, log it, or copy it anywhere. Use it only in the exact `git push`
   command. Never write it into any file.
4. ONE DELIVERABLE: the branch `w804-product-analytics` pushed to the
   remote, whose tip contains the complete, tested, formatted package.

## 1. Setup (run exactly this)

```bash
git clone https://github.com/payswapdotorg/sporta.git sporta-w804
cd sporta-w804
git checkout d734fb2337   # verified main tip
git checkout -b w804-product-analytics
bun install
```

## 2. The work item (verbatim from the roadmap)

> ### W804 Product analytics
> Owner: Product. Dependencies: W706.
> Accept: product funnel and failure metrics are documented, privacy-scoped,
> and actionable.

## 3. The real public seams you MUST ride (verified live on main)

- `packages/viewer-shell` (W706's telemetry lives here) — the event
  vocabulary and sinks, exported from its public index:
  - `telemetry-events.ts`: `TELEMETRY_SCHEMA_VERSION`,
    `TELEMETRY_VIEWER_STATUSES`, `TELEMETRY_OPERATIONS`/`isViewerOperation`,
    `TELEMETRY_TIMED_OPERATIONS`, `REMEDIATION_HINTS` (keyed by
    `ViewerFailureClass`), `USER_FEEDBACK_KINDS`, and the event interfaces
    (`TelemetryEventCommon`, `StateTransitionEvent`, `OperationTimingEvent`,
    `ErrorOccurredEvent`, …).
  - `telemetry-sink.ts`/`telemetry-file-sink.ts`/`telemetry-http-sink.ts`:
    the sink contracts (`TelemetrySink`, `createJsonlTelemetryFileSink`).
  - `errors.ts`: `ViewerFailureClass`, `ErrorView`.
  Your analytics CONSUMES these event shapes verbatim — never redefine,
   never extend the vocabulary from your package (if a needed event kind
   truly does not exist, that is a documented limitation, not a license to
   fork the schema).
- `packages/observability` (W007) — the existing observability vocabulary;
  study its style for scope/privacy discipline. Import through its public
  index only if you use it.

Rules: import through public `index.ts` surfaces only; never modify another
package; the analytics are PURE functions over recorded event streams — no
I/O, no network, no daemons.

## 4. What to build: `packages/product-analytics`

1. **The product funnel layer:** a deterministic, versioned funnel model
   over the W706 event vocabulary — funnel stages derived from the
   `TELEMETRY_VIEWER_STATUSES`/state-transition events (e.g. session-opened
   → output-selected → playback-started → playback-sustained →
   feedback-sent, respecting the ACTUAL status vocabulary the telemetry
   defines — name the stages from the real statuses, do not invent states):
   - stage classification: every consumed event lands in exactly one of
     {advanced-a-stage, matched-current-stage, out-of-funnel(with reason),
     malformed(typed)} — never-silent accounting, reconciliation asserted;
   - funnel derivation: per-session stage progression + cohort aggregation
     (counts, conversion between adjacent stages, drop-off with the
     last-known status), over session-scoped ids ONLY.
2. **The failure-metrics layer:** deterministic classification and
   aggregation of error/feedback events through `ViewerFailureClass` and
   `USER_FEEDBACK_KINDS`:
   - failure counts by class over time buckets (deterministic bucketing —
     injectable clock, no wall-clock reads);
   - operation timing statistics (the `TELEMETRY_TIMED_OPERATIONS`) using
     exact order statistics (sorted samples, documented rank rule — the
     W306 percentile precedent; NO histograms/reservoirs);
   - failure-to-remediation mapping surfaced via `REMEDIATION_HINTS` —
     each top failure class carries its actionable hint in the report.
3. **Privacy scoping ENFORCED BY CONSTRUCTION:**
   - a schema-level allowlist: the analytics layer accepts ONLY the fields
     it needs (session-scoped opaque ids, status/operation/failure enums,
     timestamps, timing values); any PII-shaped field (free text, emails,
     ip-like strings) present in an input record REJECTS that record with
     a typed privacy violation (fail-closed, test-pinned) — the pipeline
     cannot accidentally ingest what it refuses to model;
   - the privacy contract documented field-by-field in the README (what is
     collected, why, retention posture: derived aggregates only, raw event
     streams are the caller's responsibility).
4. **Actionability:** every metric in the report carries an ACTIONABLE
   annotation derived from data (e.g. top drop-off stage, top failure class
   + its remediation hint, worst timed operation) — no vague dashboards;
   the report states WHICH levers exist (status vocabulary, failure
   classes, remediation hints) and cites the counts behind each callout.
5. **Versioned, machine-readable report + CLI:** zod-validated report
   document (schema-tagged), human summary rendering, CLI regeneration
   with a VERDICT line; same input → byte-identical output (assert twice).
6. **Tests:** funnel classification (happy + out-of-funnel + malformed
   knobs), reconciliation, failure classification/bucketing, percentile
   exactness, privacy rejection knobs (each PII shape fails), determinism
   byte-identity, schema round-trip.
7. **README.md:** the metric catalog (each metric: definition, inputs,
   derivation, action), the privacy contract, the vocabulary boundaries,
   how to re-run; honest limitations section (see §5).

## 5. Honest-boundaries section (mandatory in the README)

State at minimum: analytics are OFFLINE derivations over recorded event
streams — this package is NOT a collection agent (W706's sinks collect;
this derives); no cross-session user tracking exists or is modeled
(session-scoped ids by construction); the funnel models the W706 status
vocabulary's expressiveness only; timing percentiles characterize recorded
samples, not live SLAs (W802 owns SLO policy); sample sizes per metric.

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
git commit -m "feat(w804): product-analytics — funnel + failure metrics over the W706 telemetry vocabulary (never-silent stage accounting, exact timed-operation percentiles, privacy fail-closed by construction, actionable versioned reports + CLI)"
git push https://__PAT__@github.com/payswapdotorg/sporta.git w804-product-analytics
```

Use the token ONLY in that push command. Never print the URL.

## 8. Completion report (print this EXACTLY at the end)

```
SPORTA W804 COMPLETION REPORT
Work item: W804 Product analytics
Branch: w804-product-analytics @ <final-commit-sha>
Base: d734fb2337
Battery: typecheck 0 errors / lint clean / format clean / bun test <N>/<N> green
Package: packages/product-analytics (<files> files, <tests> tests)
Funnel: <stages> stages named from the real W706 status vocabulary;
        accounting reconciled (<events> in = <advanced>+<matched>+<out>+<malformed>)
Failure metrics: <classes> ViewerFailureClasses + <feedback> feedback kinds,
        bucketed + remediation-hinted; exact percentiles for timed operations
Privacy: allowlist-enforced, PII-shaped fields fail closed (test-pinned)
Determinism: byte-identical x2; schema round-trip green
Honest boundaries: offline derivation not collection; session-scoped only;
        W706 vocabulary expressiveness; percentiles are not live SLAs
SPORTA-COMPLETION-REPORT W804 END
```

The literal final line `SPORTA-COMPLETION-REPORT W804 END` must be the last
line of your reply, verbatim, with no text after it.
