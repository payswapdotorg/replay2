# W306 — End-to-end latency benchmark (sporta, milestone M4)

You are a remote worker agent for the sporta monorepo. You get exactly ONE
task. This prompt is fully self-contained: nothing else from your client is
visible to you — work ONLY from this document and the repository it points
at. When you finish, you deliver by PUSHING A GIT BRANCH and printing a
completion report. Nothing else counts.

## 0. Non-negotiables (read first — violations void the session)

1. HONESTY ABOVE ALL. Never fabricate, round up, or "estimate" a measurement.
   A number you did not observe is a lie. An unmeasured stage is reported as
   UNMEASURED, never silently dropped.
2. SCOPE: you may create/modify files ONLY inside `packages/latency-benchmark/`
   plus (if strictly required) `bun.lock` workspace registration lines. Any
   other change voids the session. Do NOT touch other packages.
3. SECRETS: the push URL below embeds a GitHub token. NEVER print it, echo
   it, log it, or copy it anywhere. Use it only in the exact `git push`
   command. Never write it into any file.
4. ONE DELIVERABLE: the branch `work/s121-w306` pushed to the remote, whose
   tip contains the complete, tested, formatted package.

## 1. Setup (run exactly this)

```bash
git clone https://github.com/payswapdotorg/sporta.git sporta-w306
cd sporta-w306
git checkout c10491348d88cbdbe3d30dc99e029e72a1a5baa5   # verified main tip
git checkout -b work/s121-w306
bun install
```

If `bun install` fails on lockfile drift, run `bun install` again after
adding your package's workspace entry; never hand-edit unrelated lock lines.

## 2. The work item (verbatim from the roadmap)

> ### W306 End-to-end latency benchmark
> Owner: Platform. Dependencies: W305.
> Accept: p50/p95 stage and end-to-end latency measured on a controlled
> fixture/stream; target SLOs are documented from evidence.

## 3. The real public seams you MUST ride (never reimplement them)

Read these from the repo at your base — they are the sanctioned measurement
surface:

- `packages/webrtc-output/src/telemetry.ts` — exports
  `LiveWindowTimingRecord`, `LiveViewerArrivalRecord`, `LiveLagSummary`,
  `summarizeLag(records)`. This is the W306 latency-measurement seam the
  W305 flight explicitly carved out for you.
- `packages/webrtc-output/src/index.ts` — the public entry (also carries
  `createEndpoint`, `LoopbackLiveOutputTransport`, the phase machine, and
  the integrity/receipt types you can reuse for arrival accounting).
- The stage chain you measure ACROSS (public APIs of each, import them as
  `@sporta/...` workspace deps, exactly like the in-repo consumers do):
  - `packages/streaming-ingress` (W301) — job/heartbeat/result contract
  - `packages/processing-queues` (W302) — bounded backlog semantics
  - `packages/render-orchestration` (W304) — incremental SWM→render driving
  - `packages/webrtc-output` (W305) — live output + arrival telemetry

Rules for seam use: import through each package's `index.ts` public surface
only; never reach into `src/**` of another package; never modify another
package to "make measuring easier" — if a number is not observable through
the public seam, it is UNMEASURED and must be reported as such (that is a
finding, not a failure).

## 4. What to build: `packages/latency-benchmark`

A benchmark package with this shape (names may vary, capabilities must not):

1. **Controlled glass-to-glass fixture.** An in-process, clock-injected
   (deterministic virtual clock you own) pipeline harness that drives the
   REAL public seams W301→W304→W305 end-to-end: synthetic SWM update
   fixtures in, rendered live output receipts out. "Glass-to-glass" =
   fixture ingress timestamp → viewer-arrival receipt timestamp, through
   every real stage in between. The clock is pinned and injectable; every
   latency number derives from that clock, never from wall time.
2. **Stage-latency decomposition.** Per-stage timing records (ingress hop,
   queue dwell, orchestration dispatch, render turn, transport/arrival) with
   a NEVER-SILENT accounting model: every injected fixture must land in
   exactly one of {completed-with-full-stage-chain, accounted-early-exit
   (with the exit stage + reason), accounted-error (with the typed error)}.
   The fixture run's ledger must reconcile: inputs == outputs + accounted
   exits + accounted errors. A dropped/silent input is a defect.
3. **Exact percentile engine.** Order-statistics over the full measured
   sample (sorted array, exact rank selection with the documented
   interpolation rule for non-integer ranks). NO histogram approximation,
   NO reservoir sampling, NO t-digest. p50/p95/p99 minimum; the engine is
   generic over ranks. Deterministic: same samples → byte-identical stats.
4. **Deviation probes** (each must FAIL loudly when the property breaks):
   - determinism probe: run the whole fixture twice from the same pinned
     state; the two reports must be BYTE-IDENTICAL (assert on serialized
     bytes, not object equality);
   - event-influence probe: a fixture variant with a known injected
     schedule perturbation must produce measurably different percentiles
     (proves the measurements actually flow from the fixture, not from
     constants);
   - reconciliation probe: an unaccounted-input world must FAIL the ledger
     check (negative test).
5. **Byte-deterministic report + VERDICT CLI.** A report document (JSON +
   human-readable rendering) containing: environment/version block, fixture
   description, per-stage sample counts, per-stage + end-to-end percentile
   tables, the accounting ledger summary, and an `SLO-CANDIDATES` section.
   A CLI (`bun run` script or bin) that regenerates the report from the
   fixture and prints a VERDICT line. Same input → byte-identical output.
6. **SLO-CANDIDATES from measured evidence ONLY.** Every candidate line
   cites the exact measured percentile it derives from (e.g. "end-to-end
   p95 = X ms on the controlled fixture → candidate SLO p95 ≤ X"). If the
   evidence is thin, say so in the candidate line. NO aspirational numbers
   without a measurement behind them — this section is the input to W802
   (Latency SLOs), so dishonesty here poisons a downstream work item.
7. **Tests.** Unit tests for the percentile engine (exact ranks, empty
   input, single sample, even/odd counts, interpolation rule), the ledger
   reconciliation (happy + each negative knob), determinism (byte-identity),
   and the deviation probes. Run the suite; all green.
8. **README.md** for the package: what is measured, what is deliberately
   NOT measured (real network, real WebRTC ICE/STUN, real GPU timing — the
   W305 in-process binding seam makes those out of scope; say it plainly),
   how to re-run, how SLO-CANDIDATES were derived.

## 5. Honest-boundaries section (mandatory in the README)

State at minimum: virtual-clock timings are NOT wall-clock promises; the
loopback transport measures arrival through the in-process seam; unobserved
stages are listed as UNMEASURED with the seam limitation that blocks them;
sample sizes per stage; anything you did not get to.

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
git commit -m "feat(w306): latency benchmark — controlled glass-to-glass fixture over the real W301-W305 public seams, exact percentile engine, never-silent ledger, byte-deterministic report+VERDICT CLI, SLO-CANDIDATES from measured evidence"
git push https://__PAT__@github.com/payswapdotorg/sporta.git work/s121-w306
```

Use the token ONLY in that push command. Never print the URL. If the push is
rejected, re-run it; do not rewrite history.

## 8. Completion report (print this EXACTLY at the end)

```
SPORTA W306 COMPLETION REPORT
Work item: W306 End-to-end latency benchmark
Branch: work/s121-w306 @ <final-commit-sha>
Base: c10491348d88cbdbe3d30dc99e029e72a1a5baa5
Battery: typecheck 0 errors / lint clean / format clean / bun test <N>/<N> green
Package: packages/latency-benchmark (<files> files, <tests> tests)
Measured: per-stage + glass-to-glass p50/p95/p99 on the controlled fixture
          (<sample-count> samples/stage, ledger reconciled: <inputs> in,
          <completed> completed, <exits> accounted exits, <errors> accounted errors)
SLO-CANDIDATES: <count> candidates, each citing its measured percentile
Honest boundaries: virtual clock (not wall-clock promises); loopback arrival
          seam; UNMEASURED: <list or "none">
SPORTA-COMPLETION-REPORT W306 END
```

The literal final line `SPORTA-COMPLETION-REPORT W306 END` must be the last
line of your reply, verbatim, with no text after it.
