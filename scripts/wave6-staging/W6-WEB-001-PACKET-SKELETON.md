# WEB-001 — the web foundation: gateway + shell + authenticated session connection (Flauz Wave 6, Worker A)

You are Worker A on the Flauz Wave-6 track, dispatched from inside the
replay by the Tech Lead. Waves 1–5 are CLOSED and merged on main (through
LEASE-001 PR #55 and TAKE-001's PR; the F6 depth is complete). This wave
opens the F11 production-gate client: the Web client. The main base for
this dispatch is therefore the post-TAKE-001 main:
`<PIN-FULL-SHA>`. You implement EXACTLY ONE work order: **WEB-001** (the
web foundation). Do not start any other Wave-6 item (WEB-002 is a later
dispatch) or any follow-up.

## STEP ZERO (mandatory first action — before any planning)

```
git clone https://github.com/payswapdotorg/Flauz.app flauz
cd flauz
git checkout <PIN-FULL-SHA>
git rev-parse HEAD   # MUST equal <PIN-FULL-SHA>
git checkout -b feat/web-001-foundation
```

Record the exact cloned HEAD SHA — your final report must state it.

## RE-ENTRY LAW (durable — applies whenever this packet is re-sent)

If `crates/flauz-web-gateway` AND `web/` ALREADY EXIST at your pinned base
(a predecessor session's work was merged to main before this dispatch
reached you), your job becomes VERIFY-AND-REPORT, not redo: audit the
landed gateway + shell against this packet's acceptance criteria, run every
gate verbatim, and report what you verified with exact results. Fix forward
surgically only for real defects; never rewrite history; escalate anything
you cannot resolve honestly. Never re-implement work that is already on
main.

## Canonical documents (read in-repo BEFORE implementing)

1. `AGENTS.md` (follow its formatting/lint rules)
2. `docs/FLAUZ-SOURCE-OF-TRUTH.md`
3. `docs/IMPLEMENTATION-ROADMAP.md` (F11 + the 2026-09-23 sequencing
   amendment — the web client is a production-gate client)
4. `docs/WORK-ORDER-TEMPLATE.md` (the worker rules + the closure gates)
5. `docs/PRODUCT-UX-JOURNEYS.md` (your J-01..J-05 journey definitions)
6. `docs/F2-CONTRACT-KERNEL.md` (the FROZEN contract kernel) + the frozen
   Wave-2/3/4/5 addenda in `docs/research/WAVE2-WORK-ORDERS.md` …
   `WAVE5-WORK-ORDERS.md`, and the frozen Wave-6 kernel addendum (§1–§9) in
   `docs/research/WAVE6-WORK-ORDERS.md` — your work order's contract base.
   Read §1 (protocol-only law), §2 (the one new crate), §3 (frontend
   outside the Rust workspace + schema-generated types), §4 (credential
   law), §5 (truthful connection state), §8 (journeys + evidence) with
   special care — they bind every line you write.

## Your work order (verbatim from WAVE6-WORK-ORDERS.md §WEB-001)

```
ID: WEB-001
Title: flauz-web-gateway (WebSocket↔app-server bridge + static hosting) and
       the web shell (layout, navigation, theming, keyboard, routing) with
       authenticated workspace/session connection and truthful state
Phase: F11 — Web client (Wave 6a)
Owner: dispatched worker (Wave-6 Worker A)
Dependencies: TAKE-001 merged (main past b346895); all Wave-1..5 contract
             crates read-only available
Contract(s): F2-CONTRACT-KERNEL + Wave-2..5 addenda + Wave-6 addendum
             (this file); app-server JSON-RPC surface as exported by the
             experimental schema export
Problem: the production gate requires a web client; none exists. The
         desktop client is the only UI surface today and binds users to a
         single machine.
User-visible outcome: a user opens the served web app in a browser, signs
         in, and lands in a working shell that lists/connects to their
         workspace and sessions with live, truthful state; navigation,
         theming, and keyboard paths work; disconnection and reconnection
         are named and recoverable.
Scope:
  - crates/flauz-web-gateway (NEW): axum (or workspace async stack) server;
    WebSocket endpoint bridging to a supervised app-server instance per
    authenticated session; static-file hosting for web/ build output;
    localhost-only default bind; documented non-local opt-in; graceful
    shutdown; structured logs WITHOUT credentials
  - web/ (NEW): TypeScript+React app; generated protocol types from the
    schema export; app shell (layout, nav, palette/search, theming,
    keyboard map, focus management); auth flow (login via app-server auth
    API); workspace/session list + connect; truthful connection-state
    machine (connected/authenticating/reconnecting/failed-with-reason);
    empty/error/success states for every surface; i18n-ready strings
  - evidence: web parity-lab script(s) running the J-01..J-05 journeys
    headless with captures under the evidence schema
Non-goals: remote environment control, model/provider selection,
         skill-unlock UI, collaboration/presence, artifacts/documents/
         sheets, accessibility/responsive final pass (ALL are WEB-002);
         ANY desktop change; ANY new protocol method (deviation-gated only)
Files/subsystems owned: crates/flauz-web-gateway/**, web/**,
         docs/research/evidence/web/** (new); NOTHING else
Inputs: main @ <PIN>; schema export procedure (existing repo tooling)
Outputs/artifacts: one clean commit branch `feat/web-001-foundation`,
         git bundle, completion report (11-field contract, Wave-5 shape)
Tests: gateway unit tests (bridge framing, auth handshake refusal,
         localhost-bind default, static serving); frontend component tests
         for the connection-state machine; one gateway integration test
         (spawn app-server, round-trip a JSON-RPC call over WebSocket)
GUI/lab evidence: J-01..J-05 journey captures from the headless web lab
UX journey IDs: J-01, J-02, J-03, J-04, J-05 (web variants)
Primary discovery surface: the web shell home (workspace/session)
Contextual discovery surface: connection-state banner (always visible,
         always truthful)
Search/palette discovery: command palette in the shell (fallback, never
         the sole mechanism)
Empty/success-state behavior: first-run empty workspace state; session
         connect success state with next-step affordance; every error names
         cause + recovery action
Acceptance criteria:
  1. `cargo check --workspace` and the gateway crate's tests pass with the
     documented gate flags; the web build (`web/` tooling) succeeds without
     touching cargo state
  2. The schema-exported types are the ONLY protocol types in web/ (no
     hand-written duplicates)
  3. A headless browser session completes: open app → sign in → see
     workspace/session list → connect → truthful connected state → kill the
     gateway → named disconnection state → restart → reconnect → state
     recovers (evidence captured)
  4. Non-local bind refused by default; localhost-only in evidence
  5. No credential ever appears in logs, URLs, or evidence artifacts
  6. Zero changes outside the owned paths (git diff proves it)
Rollback/recovery: revert the merge commit; no data migrations; the gateway
         is additive-only
Integration notes: the gateway reuses the desktop backend's supervision
         semantics (spawn/restart/reap of the app-server); any divergence is
         a deviation
```

## Verification gates (run verbatim; record exact results)

```
cargo test -p flauz-web-gateway --all-targets
cargo clippy -p flauz-web-gateway --all-targets -- -D warnings
cargo fmt -p flauz-web-gateway -- --check
cargo check --workspace          # the new crate must not break the workspace
cd web && <package-manager> install && <package-manager> build && <package-manager> test
```

State plainly if the sandbox lacks the Rust toolchain or Node toolchain —
static reasoning is acceptable for the missing side, the Lead independently
compiles and gates both.

## Delivery

1. ONE clean commit on `feat/web-001-foundation` at the pinned base, message:
   `feat(web): WEB-001 — flauz-web-gateway + the web shell with authenticated session connection (Wave 6)`
   Then export the delivery bundle (keep it at the repo root of the sandbox
   working tree):
   ```
   git bundle create web-001-delivery.bundle <PIN-FULL-SHA>..feat/web-001-foundation
   ```
2. DO NOT PUSH (no credentials — the Tech Lead harvests your workspace; the
   sandbox tar is the delivery channel). Keep the FULL source tree in the
   working tree; `rm -rf` cargo target dirs AND `web/node_modules` once
   verification results are recorded (keep the harvest tar lean).

## Reporting contract (all Wave-6 workers — verbatim)

The 11-field completion report (exact headers), delivered in the worker's
final message AND via the delivery bundle branch: WO ID(s); base branch +
SHA; branch/commits; changed files/surfaces; implementation summary;
tests/commands + exact results (state plainly if the sandbox lacks the
toolchain — static reasoning is acceptable, the Lead independently compiles
and gates); kernel-compliance checklist (the Wave-6 addendum's §1–§9, each
item); GUI discoverability layers covered (J-01..J-05 web variants);
acceptance-criteria evidence (map each bullet); known limitations; contract
deviations (NONE if none); follow-up work.
