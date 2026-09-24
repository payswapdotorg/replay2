# TAKE-001 — the human takeover/approval/handoff fabric + cancellation propagation, the J-17 surface (Flauz Wave 5, Worker B)

You are Worker B on the Flauz Wave-5 track, dispatched from inside the replay
by the Tech Lead. Wave 4 is CLOSED and merged (PROV-001 + LAB-001 + COL-001
landed through PRs #52/#53/#54), and since this wave opened, Wave-5 Worker A
has ALSO landed: LEASE-001 (the lease/conflict fabric — crates/flauz-lease +
the J-16 conflicts surface) merged through PR #55. The main base for this
dispatch is therefore the post-LEASE-001 main:
`b346895cad4067d72f6e70436ddc2e9c9067f7b9`. Wave 5 closes the remaining F6
depth with your work order: TAKE-001 (Worker B — the human-takeover fabric);
the LEASE-001 and TAKE-001 surfaces are disjoint. Treat crates/flauz-lease
and its codex-app conflicts surface as landed read-only code — depend on it
where the roadmap calls for it, never rewrite it. You implement EXACTLY ONE
work order: **TAKE-001**. Do not start any other Wave-5 item or any follow-up.

## STEP ZERO (mandatory first action — before any planning)

```
git clone https://github.com/payswapdotorg/Flauz.app flauz
cd flauz
git checkout b346895cad4067d72f6e70436ddc2e9c9067f7b9
git rev-parse HEAD   # MUST equal b346895cad4067d72f6e70436ddc2e9c9067f7b9
git checkout -b feat/take-001-human-loop
```

Record the exact cloned HEAD SHA — your final report must state it.

## RE-ENTRY LAW (durable — applies whenever this packet is re-sent)

If `crates/flauz-takeover` ALREADY EXISTS at your pinned base (a predecessor
session's work was merged to main before this dispatch reached you), your job
becomes VERIFY-AND-REPORT, not redo: audit the landed crate + surface against
this packet's acceptance criteria, run every gate verbatim, and report what
you verified with exact results. Fix forward surgically only for real defects;
never rewrite history; escalate anything you cannot resolve honestly. Never
re-implement work that is already on main.

## Canonical documents (read in-repo BEFORE implementing)

1. `AGENTS.md` (follow its formatting/lint rules)
2. `docs/FLAUZ-SOURCE-OF-TRUTH.md`
3. `docs/IMPLEMENTATION-ROADMAP.md`
4. `docs/WORK-ORDER-TEMPLATE.md` (the worker rules + the closure gates)
5. `docs/PRODUCT-UX-JOURNEYS.md` (your J-16/J-17 journey definitions)
6. `docs/F2-CONTRACT-KERNEL.md` (the FROZEN contract kernel) + the frozen
   Wave-2/3/4 addenda in `docs/research/WAVE2-WORK-ORDERS.md`,
   `WAVE3-WORK-ORDERS.md`, `WAVE4-WORK-ORDERS.md`, and the frozen Wave-5
   kernel addendum (§1–§7) in `docs/research/WAVE5-WORK-ORDERS.md` — your
   work order's contract base. Read §1 (frozen signatures), §3 (the takeover
   law), §4 (cancellation honesty), §6 (GUI seven-layer + d25 listener law),
   §7 (standing laws) with special care — they bind every line you write.

## Your work order (verbatim from WAVE5-WORK-ORDERS.md §TAKE-001)

```
ID: TAKE-001
Title: The human in the loop — takeover/approval/handoff records with
  attribution, approval gates with named needs and consequences,
  cancellation/dependency propagation with named terminal states, and
  the needs-you review surface (J-17)
Phase: Wave 5 (F6 depth — human takeover/approval/handoff)
Owner: Worker B (agents-tab session)
Dependencies: flauz-exec (the FROZEN harness state machine — the
  Escalated state + prepare/execute/observe/verify/persist/continue/
  recover/escalate transitions, read-only reference); flauz-orch (the
  graph's NodeFailed/RunCanceled semantics — read-only); flauz-world
  (the event stream + ActorRef); the attention/activity surfaces
  (WO-P2-008/P2-013 — additive attribution only); the shell-family UI
  patterns
Contract(s): F2-CONTRACT-KERNEL.md; Wave-2/3/4 addenda; this addendum
  §1, §3, §4, §6, §7
Problem: the harness can ESCALATE ("the human is needed") but nothing
  models what happens next: the human's work is not a first-class
  attributed turn, the handback to the agent is undefined, approval
  gates do not exist (a node that needs approval has no way to block
  with a named need), and cancellation is a run-level event with no
  dependency propagation (dependents of a cancelled node would sit
  silently Blocked forever) — the honest-failure family is incomplete.
User-visible outcome: when a run needs the human, the user sees the
  named need ("Needs you: approve the environment switch — moving to
  the remote sandbox will re-run the setup steps"), decides with the
  consequence stated, can TAKE OVER the agent's turn (their work lands
  on the same task, attributed to them; the agent's prior work
  preserved), hands back explicitly, and can cancel a node or the run
  with every dependent told the truth ("Cancelled — the research step
  it waited on was cancelled").
Scope:
  - crates/flauz-takeover/** (NEW self-contained crate, the flauz-cap
    pattern: serde/chrono-family only, inputs as data, NO
    contract-crate imports):
    - takeover.rs: TakeoverRecord (the human actor ref + what they took
      over — the node/run ref + the agent ref — + when + why) +
      HandbackRecord (the explicit return + what the human did +
      whether the agent resumes or the run completes); the takeover
      law is structural (a record without full attribution cannot be
      constructed).
    - approval.rs: ApprovalGate (the named need: what must be approved,
      the requesting node, the consequence of each side) +
      ApprovalDecision (approve/deny + the deciding human + the
      timestamp + the attributed effect); denial carries the named
      consequence (the node fails honestly with the denial as its
      reason — never a silent proceed); an approval gate is data the
      evaluator/caller consults, not a thread block.
    - cancel.rs: CancellationRecord (what was cancelled — node or run —
      + the reason + the actor) + the propagation projection (given a
      graph as data + the cancelled node → every dependent's named
      terminal state: cancelled, or blocked-resolved with the reason;
      already-attributed work kept); at most one run-level record per
      sequence (the frozen law), the node-level propagation as the
      projection's output.
    - fakes.rs + fixtures per family + conformance tests: the takeover
      round-trip (take over → work attributed to the human → handback
      → the agent resumes; the agent's artifacts preserved verbatim);
      the approval space (approve/deny × consequences, the named
      needs); the propagation matrix (cancel a leaf / a mid node / the
      root; dependents named; attributed work kept; one run record);
      determinism; canonical JSON.
  - The world-stream event vocabulary (as DATA in the crate — the
    registered new event types the caller records through the existing
    world-store seam): task.takeover_started / task.takeover_handback /
    task.approval_requested / task.approval_decided / task.cancelled /
    task.dependent_cancelled — canonical payload shapes the crate
    defines and tests.
  - crates/codex-app/src/ui/flauz_takeover.rs (NEW, the shell-family
    pattern): the needs-you review surface — the approval card (the
    named need + the consequence of each side + Approve/Decline), the
    takeover affordance ("Take over this step" — the agent's state
    preserved note + the handback path), the cancellation affordance
    (node + run, each with the consequence stated: what gets cancelled
    downstream), the honest empty state (nothing needs you), the
    wiring honesty (the live agent wiring is later — say so plainly).
  - The attention-model EXTENSION seams (additive, the COL-001
    precedent): the needs-you rows on the EXISTING attention/activity
    surfaces carry the kind (approval gate / escalation / takeover
    opportunity) — additive data + additive render lines only; NO
    second store (the seam test pins it).
  - ui.rs: ONLY the named seams — distinct from every prior wave's.
Non-goals: NO harness state-machine changes (the takeover rides the
  EXISTING Escalated + continue/recover transitions — the records are
  data the caller drives; if a genuinely-required additive transition
  surfaces, mark it a deviation with the match-sites — the Lead gates
  it), NO GraphEvent/NodeState changes, NO real concurrent-human
  sessions, NO mobile/web surfaces (the Web client is its own wave).
Files/subsystems owned: crates/flauz-takeover/**; the workspace
  Cargo.toml members line (one line; the Lead resolves the two-way
  one-liner at merge); crates/codex-app/src/ui/flauz_takeover.rs; the
  EXISTING attention modules' additive kind seams (named files in the
  report); ui.rs NAMED SEAMS ONLY
Inputs: flauz-exec's harness.rs (the frozen state machine), the
  ORCH-003 recovery surface (the Escalate-to-me precedent), the
  ORCH-004 graph semantics, the COL-001 attention-attribution seams
Outputs/artifacts: the flauz-takeover crate + the event vocabulary +
  fixtures + the needs-you surface + the attention kind seams + tests
Tests: the takeover law (attribution structural; the same-stream law —
  the human's turn is a task event, never a second store; the
  projection law — the agent's work preserved); the approval space
  (named needs, attributed decisions, denial consequence); the
  propagation matrix (every dependent named; attributed work kept; one
  run record); determinism + canonical JSON + fixtures; the credential
  scan; the UI module tests (copy rules with consequences; seven
  layers; the not-wired honesty; the chord listener SEAM-TESTED); the
  attention-extension seam test (additive-only, source-inspected)
GUI/lab evidence: Lead gate — lab scenes at the merged binary (the
  needs-you surface: the approval card with consequences, the takeover
  affordance, the cancel path with the downstream truth, the honest
  empty state)
UX journey IDs: J-17 (review activity that needs the human — the
  approve/decline/take-over flow), J-14/J-15's takeover dimension
  (the human steps in without losing the agent's work)
Primary discovery surface: the needs-you review panel + the attention
  rows' kind attribution
Contextual discovery surface: the task-surface affordance when THIS
  task needs a decision
Search/palette discovery: palette rows ("See what needs you",
  "Take over a running step")
Empty/success-state behavior: nothing needs you → the honest quiet
  state + what lands here; a gate → the card with both consequences;
  after deciding → the attributed outcome + the resume state
Keyboard path: a letter-family chord (Ctrl+Alt+Shift+Y suggested —
  verify no conflict at implementation; the palette family is at 89
  rows, ALL → 91) + scoped Escape; tab-navigable flow
Acceptance criteria:
  1. Single clean commit on feat/take-001-human-loop at the pinned
     base; owned files only.
  2. The takeover law proven: attribution structural, same-stream,
     projection-preserved; the handback explicit.
  3. The approval + cancellation spaces proven: named needs, attributed
     decisions, denial consequences, every dependent named, one run
     record — all deterministic.
  4. The surface: seven layers; user language with consequences
     (tested); the chord listener SEAM-TESTED (the d25 law); the
     attention extension additive-only + seam-tested.
  5. Non-empty Contract deviations blocks closure.
Rollback/recovery: additive crate + modules + seams; revert the commit.
Integration notes: the records are pure data (no imports); the event
  vocabulary is the wiring contract the Lead's wave-gate harness
  drives end-to-end (an approval-gated graph run → the named gate →
  the human decision on the stream → the resume/cancel with named
  dependents). The UI's live state is the module's fake-seam state
  this wave — the honest not-wired note says so plainly.
```

## Verification gates (run verbatim; record exact results)

```
cargo test -p flauz-takeover --all-targets
cargo clippy -p flauz-takeover --all-targets -- -D warnings
cargo fmt -p flauz-takeover -- --check
cargo check -p codex-app   # the ui module + ui.rs seams (if toolchain allows)
```

State plainly if the sandbox lacks the Rust toolchain — static reasoning is
acceptable, the Lead independently compiles and gates.

## Delivery

1. ONE clean commit on `feat/take-001-human-loop` at the pinned base, message:
   `feat(take): TAKE-001 — takeover/approval/handoff records, cancellation propagation, the J-17 needs-you surface (Wave 5)`
   Then export the delivery bundle (keep it at the repo root of the sandbox
   working tree):
   ```
   git bundle create take-001-delivery.bundle b346895cad4067d72f6e70436ddc2e9c9067f7b9..feat/take-001-human-loop
   ```
2. DO NOT PUSH (no credentials — the Tech Lead harvests your workspace; the
   sandbox tar is the delivery channel). Keep the FULL source tree in the
   working tree; `rm -rf` cargo target dirs once verification results are
   recorded (keep the harvest tar lean).

## Reporting contract (all Wave-5 workers — verbatim)

The 11-field completion report (exact headers), delivered in the worker's
final message AND via the delivery bundle branch: WO ID(s); base branch +
SHA; branch/commits; changed files/surfaces; implementation summary;
tests/commands + exact results (state plainly if the sandbox lacks the
Rust toolchain — static reasoning is acceptable, the Lead independently
compiles and gates); kernel-compliance checklist (this addendum's §1-§7,
each item); GUI discoverability layers covered (UI-bearing WOs);
acceptance-criteria evidence (map each bullet); known limitations;
contract deviations (NONE if none); follow-up work.

## The completion report (your FINAL message — the exact contract)

```
=== TAKE-001 COMPLETION REPORT ===
WO ID: TAKE-001
Base branch / 基础分支: main
Base SHA / 基础 SHA: main @ <the exact base SHA you checked out in STEP ZERO>
Branch / commits: feat/take-001-human-loop @ <your commit sha> (1 commit)
Changed files / surfaces: <n> files (+<adds>/−<dels>) — <one-line surface list>
Implementation summary: <what you built, per module>
Tests / commands + exact results: <each gate command + verbatim result>
Kernel-compliance checklist (§1-§7): <each section, one line each>
GUI discoverability layers covered: <the seven layers, each named>
Acceptance-criteria evidence: <map each of the 5 bullets>
Known limitations: <honest list>
Contract deviations: <NONE or the exact list — non-empty BLOCKS closure>
Follow-up work: <what the Lead should schedule next>
```

The report is the LAST message you send. After it, stop — the Tech Lead
harvests, gates, and merges. Do not answer follow-up questions inside this
session unless the Tech Lead explicitly re-engages you.
