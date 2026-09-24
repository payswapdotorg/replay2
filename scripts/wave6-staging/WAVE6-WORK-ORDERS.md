# Wave 6 Work Orders — F11: Web Client (production-gate client #3)

> **Status: DRAFT (pre-dispatch)** — base pin and dispatch status line are
> finalized by the Tech Lead AFTER TAKE-001 merges. At dispatch this header
> becomes: `Status: DISPATCHED <date> (WEB-001 Worker A — base = main @
> <FULL-SHA>)` and the packet prompt pins the same SHA.
>
> **Lead final-pin checklist (all must pass before dispatch):**
> 1. TAKE-001 merged through its PR; main advanced past `b346895`.
> 2. Verify TAKE-001's landed surface (takeover/approval/handoff records,
>    cancellation propagation) against §6 below — extend if the landed
>    record families differ.
> 3. Commit this doc to `docs/research/WAVE6-WORK-ORDERS.md` on main.
> 4. Pin the dispatch prompt to the resulting main SHA (full hex).
> 5. WEB-002 is NOT dispatched until WEB-001 is merged and gated (serial
>    sub-waves; the web tree is single-owner at any time).
>
> Shared-contract authority:
> [F2-CONTRACT-KERNEL.md](F2-CONTRACT-KERNEL.md) (frozen) + the Wave-2/3/4/5
> addenda in [WAVE2-WORK-ORDERS.md](WAVE2-WORK-ORDERS.md),
> [WAVE3-WORK-ORDERS.md](WAVE3-WORK-ORDERS.md),
> [WAVE4-WORK-ORDERS.md](WAVE4-WORK-ORDERS.md),
> [WAVE5-WORK-ORDERS.md](WAVE5-WORK-ORDERS.md) (all frozen) + the
> **Wave-6 kernel addendum below** + the MERGED contract crates (flauz-world /
> flauz-exec / flauz-context / flauz-cap / flauz-orch / flauz-prov /
> flauz-lab / flauz-collab / flauz-lease / the TAKE-001 takeover fabric).
> Every work order follows [WORK-ORDER-TEMPLATE.md](../WORK-ORDER-TEMPLATE.md).
> Non-empty `Contract deviations` in a worker report blocks closure. Workers
> deliver via `git bundle` on a single clean commit branch; the Lead gates,
> fixes, merges.
>
> **The phase this wave serves** (ACTIVE-EXECUTION-STATE.md immediate order
> item 4 — "Finish Web client"; ROADMAP F11 + the 2026-09-23 sequencing
> amendment: the FIRST production gate requires Linux desktop + Windows
> desktop + **Web client**; macOS/Mobile are deliberately deferred). The web
> client is therefore a production-gate client, not a convenience surface:
> its journeys carry the same acceptance law as the desktop's.

## Wave-6 kernel addendum (frozen by the Tech Lead before dispatch)

1. **The app-server JSON-RPC protocol is the ONLY capability contract.** The
   web client shows exactly what the existing app-server protocol surface
   provides. The gateway (see §2) adds ZERO product logic. A capability
   missing from the protocol is a protocol work order (deviation-gated,
   additive seam only) — never a gateway-side or frontend-side fabrication.
2. **One new Rust crate: `flauz-web-gateway`.** A transparent transport
   bridge: WebSocket frames ↔ app-server JSON-RPC messages, plus static-file
   hosting for the web frontend, plus the documented auth/session handshake
   pass-through. It supervises one app-server per authenticated session with
   the same supervision semantics as the desktop client's backend binding.
   No other crate in `crates/` may be modified by Wave-6 work orders except
   through the additive protocol seam (deviation-gated, Lead-gated case by
   case).
3. **The frontend is TypeScript + React in `web/`, outside the Rust
   workspace.** The Rust workspace's cargo gates must not depend on node
   tooling, and the web build must not gate cargo. The frozen frontend
   contract is the exported app-server schema (the experimental schema
   export, `CODEX_APP_SERVER_SCHEMA_EXPERIMENTAL=1`) — the frontend consumes
   generated types from that export; hand-written duplicates of protocol
   types are forbidden (drift = contract violation).
4. **Auth and credential law.** The web client never embeds credentials in
   URLs, logs, or evidence artifacts (the E2B harness law, extended to the
   web). Authentication flows through the app-server's own auth APIs. The
   gateway binds localhost by default; non-local binding requires explicit
   operator configuration and refuses to start without an authenticated
   session handshake.
5. **Truthful connection state at all times.** The shell renders exactly one
   of: connected / authenticating / reconnecting / failed-with-reason —
   including the server-side session destruction cases (the replay-era
   lesson: a silently-wedged session is the worst failure mode). Every
   user-visible state must name what happened and what happens next.
6. **The conflict-honesty and takeover laws extend to the web.** Approvals,
   takeovers, escalations, and cancellations surface as NAMED records from
   the TAKE-001 fabric (who decided, what is contested, what happens next);
   the web client never auto-resolves a contested resource and never hides a
   cancelled/pending state. Cancellation propagation is visible: if an
   operation the user is watching is cancelled upstream, the UI says so with
   the propagation reason.
7. **Frozen desktop behavior.** Nothing in this wave may change desktop
   (codex-app) behavior, UI, or wiring. The desktop remains the parity
   reference; the web client is judged against it.
8. **Journeys and evidence.** J-01..J-05 minimum on web (primary visible
   path, contextual path, search/palette fallback, empty/error state,
   success/next action, keyboard path, recovery/reconnect) plus at least one
   domain-neutral non-code scenario (the shared acceptance law). Evidence is
   Playwright-driven (or equivalent headless-browser) captures stored under
   the parity-lab evidence schema: screenshots + action log + truthful-state
   assertions per journey.
9. **Scope honesty under the platform wedge.** Keep each work order small
   enough to survive a reaped session: one bounded commit-branch delivery
   per worker, the same git-bundle contract as Wave-5.

## WEB-001 — Web foundation: gateway + shell + authenticated session connection

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
Status: DRAFT (Lead pins at dispatch)
```

## WEB-002 — Web capability surfaces (dispatched only after WEB-001 merges)

```
ID: WEB-002
Title: remote environment control, model/provider selection, skill-unlock
       UI, collaboration/presence, artifacts/documents/sheets, and the
       accessibility/responsive pass on the WEB-001 foundation
Phase: F11 — Web client (Wave 6b)
Owner: dispatched worker (Wave-6 Worker B, after WEB-001 is merged+gated)
Dependencies: WEB-001 merged; TAKE-001 + LEASE-001 record families live
Contract(s): as WEB-001 + the collab/presence contract crates (flauz-collab)
Problem: the WEB-001 shell connects but shows no capabilities; the
         production gate requires the F11 capability set usable from web
User-visible outcome: a web user can select and control a remote
         environment, pick model/provider, unlock skills, see collaborators
         and presence, view artifacts/documents/sheets, with an
         accessibility/responsive pass over the whole client
Scope: web/ capability surfaces ONLY (gateway changes only via the
         deviation-gated additive seam if a protocol gap genuinely blocks
         a roadmap-mandated capability)
Non-goals: any new contract crate; desktop changes; macOS/mobile
Acceptance criteria: J-06..J-18 web variants applicable to these surfaces
         (journey evidence per the kernel addendum §8); conflict-honesty and
         takeover laws visible on every approval/cancellation surface (§6);
         responsive + keyboard + screen-reader pass evidenced
Status: DRAFT (Lead pins at dispatch; REAIMED after WEB-001's landed shape)
```

## Dispatch notes (Lead-only)

- Dispatch mode under the §16 platform wedge: ONE worker at a time
  (WEB-001 first). The packet follows the proven Wave-5 wrapper: pinned
  full SHA, STEP ZERO (clone+checkout+branch), RE-ENTRY LAW, one-commit +
  bundle contract, 11-field report, honest-absence rules.
- The completion gate marker for the queue watcher: `WEB-001 COMPLETION
  REPORT` (add the WEB- prefix alternative to the queue_watch gate regex
  before dispatch — same 4-vector test discipline as the LEASE/TAKE patch).
- Harvest chain for WEB-001: extract/reconstruct → web build + cargo gate
  (flauz-web-gateway in the workspace) → PR → merge. The gate station is
  warm; source /home/z/parity-lab/build_env.sh (recipe in replay2 repo).
