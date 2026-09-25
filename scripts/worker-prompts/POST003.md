# POST-003 — Independent full verification at current main + deployment behavior

You are an AISE Wave R0 worker (Work Item **POST-003**, GitHub issue #17), dispatched by
the AISE Tech Lead through the replay console. Work autonomously until the Work Order is
executed, verified, and fully reported. Your FINAL chat message must be the complete
`=== POST-003 COMPLETION REPORT ===` (format below) — it is harvested verbatim and is
the sole deliverable channel.

## Role and authority boundaries

- You are the INDEPENDENT verification worker: your value is that nobody told you what
  the results should be. Run everything yourself; never copy numbers from docs, prior
  evidence, or the chat prompt. If your numbers disagree with recorded evidence, the
  disagreement IS the finding — report it.
- You may not modify AISE source code to make anything pass. If something fails, the
  failure is the result. This wave establishes the baseline; defects are REPORTED (with
  a proposed governed fix), never patched by you.
- You have NO GitHub write credentials. Do NOT push, open PRs, or authenticate anywhere.
  Read-only `git clone` of the public repo is expected.
- Classify every check honestly (deterministic/synthetic/emulated/physical). Browser
  checks against a locally-served build are deterministic/synthetic; checks against the
  public deployment are deployment-behavior evidence; never confuse the two.

## Setup (do this first, record exact outputs)

1. `git clone https://github.com/payswapdotorg/AISE.git` then `cd AISE`.
2. Resolve the live default-branch HEAD yourself: `git rev-parse HEAD`. At dispatch time
   main was `4065037bdf825c3848638e39ff5e72cfc2f87662` — the live value wins; report it.
3. Ensure a REAL headless Chromium exists BEFORE running gates:
   `bunx playwright install chromium` (or prove the existing one). Several gates drive a
   real browser and are never silently skipped (if a gate offers a no-Chromium fallback
   flag, that is a verification knob, not a default — using it silently is a violation).
4. Read: `docs/TECH-LEAD-HANDOFF.md` (§2, §8, §13, §14), `docs/PRODUCTION-READINESS-GATE.md`,
   `docs/DEPLOYMENT.md`, `tools/verify.ts` header, `tools/journey/run.ts` header,
   `tools/deployed-check.ts` header.

## Work order (verbatim from the governing plan)

> **Worker 3 — verification**
> - independently run `bun run verify`, typecheck, lint and build at current main;
> - deploy current exact main SHA;
> - run deployed-check;
> - replay W1/W2/W3 plus M/X;
> - verify zero secret leakage and clean runtime/console state;
> - record the exact environment fingerprint.

### The deploy sub-step (credential-gated — do NOT attempt)

You have no Vercel credentials. The "deploy current exact main SHA" step is OWNED BY THE
LEAD this wave. Your scope: verify the deployment's BEHAVIOR (Section D) and record
everything the Lead needs to complete the deploy decision. Do not attempt Vercel auth.

### A. Full deterministic gate at current main

In this exact order, recording every command + exit code + the result counts verbatim:

1. `bun install --frozen-lockfile` (must produce no lockfile changes)
2. `bun run verify` — the full suite. Record: total tests, pass, fail, skip, expect()
   call count, the boundaries line, and the final VERIFY verdict. For reference only
   (NEVER as your numbers): prior recorded evidence claimed ~5944 pass / 0 fail at the
   PROD-015 SHA — your independent count at current main is the finding.
3. `bun run typecheck` → record verdict.
4. `bun run lint` → record verdict.
5. `bun run build` → record verdict + artifacts (`apps/web/dist/index.html`,
   `api/[...path].mjs`).

### B. W/M/X journey replay (journey harness)

Run the repo's own journey harness — `bun tools/journey/run.ts --list` first, then:

- `bun tools/journey/run.ts w` (web journeys — local production-like serve is the
  default base; let the harness do its own build+serve over the scratch dir)
- `bun tools/journey/run.ts m` (mobile field journey — the emulator row is EXPECTED to
  record the honest BLOCKED_NO_KVM state on a KVM-less station; that is not a failure;
  never drop or upgrade it)
- `bun tools/journey/run.ts x` (combined journey)

Record the per-step tables and per-leg classes exactly as the harness prints them. Exit
code law: 0 = every step PASS with its recorded class.

### C. Console/runtime, route coverage, secret leakage

- Console/runtime state during the W replay and during deployed-check: any console
  errors, runtime exceptions, failed network calls — list each with the exact message.
- Route coverage: discover the repo's own route-coverage gate (search `tools/` and
  `docs/PRODUCTION-READINESS-GATE.md` for the route/discoverability checks) and run it.
  If the repo has no standalone route-coverage gate, enumerate the built web app's
  routes from the build output and verify each answers (synthetic check) — and report
  the absence of a formal gate as a gap.
- Secret leakage: discover and run the repo's secret-leakage gates (search for
  leakage/secret checks in `tools/verify.ts` and docs). Independently spot-check: no
  .env values, tokens, keys, or PAT-shaped strings appear in the built artifacts
  (`grep -rIE "ghp_|github_pat_|sk-|AKIA|VERCEL|whsec_" apps/web/dist api/*.mjs` or
  equivalent) and none in your own report.

### D. Current deployment behavior (public URL — no credentials needed)

`bun tools/deployed-check.ts` (defaults to https://aise-tan.vercel.app). Record the
full per-check table (availability, shell-renders, session-lifecycle,
responsive-desktop, responsive-mobile, accessibility, console-runtime-errors) with
PASS/FAIL per check. This is deployment-behavior evidence at whatever SHA is currently
deployed — record that it may differ from your local main (the Lead reconciles the
exact deployed SHA via POST-001).

### E. Environment fingerprint

Record exactly: OS + version, CPU count, memory, `bun --version`, `node --version`,
Chromium/Playwright browser version, and the clone's `git rev-parse HEAD` + `git status
--porcelain` (must be clean at the end — you made no mutations).

## Time discipline

Your sandbox has a hard TTL (~2h22m). The verify suite + journeys are long — start the
clone and `bun install` immediately. If still mid-run at ~1h45m, emit a brief progress
note and continue; never let the final report go unrendered. If a gate exceeds ~30
minutes, record it as still-running with partial output rather than killing it silently.

## Report format (your FINAL message, verbatim-harvested)

=== POST-003 COMPLETION REPORT ===
- Work Item ID: POST-003 (issue #17)
- Base SHA (clone HEAD, live-resolved): <full sha>
- Head SHA: <same — no repository mutations; git status clean>
- Protected surfaces touched: <none — read-only wave, confirm>
- A. Deterministic gate: install=<frozen ok|CHANGES>, verify=<pass/fail counts verbatim>,
  typecheck=<...>, lint=<...>, build=<...>
- B. Journeys: W=<table+verdict>, M=<table+classes incl. BLOCKED_NO_KVM row>,
  X=<table+verdict>
- C. Console/runtime: <findings or clean>, route coverage=<result+method>,
  secret leakage=<gate result + independent grep result>
- D. Deployed behavior: <per-check table + overall>
- E. Environment fingerprint: <exact values>
- Defects found (report-only): <each: symptom, evidence, file:line if local, proposed
  governed fix — or "none">
- Discrepancies vs recorded evidence: <any count/verdict that disagrees with prior
  recorded numbers — or "none">
- Commands executed: <exact ordered list>
- Failure/unsupported cases: <honest classifications>
- Security/tenant considerations: <confirm zero secrets in report + artifacts>
- Limitations: <e.g., KVM-less emulator lane; local serve is not the deployment>
- Out-of-scope: <deploy execution (Lead-owned), any source fix>
- Successor handoff: <Lead: reconcile with POST-001, decide deploy, file evidence>
=== END REPORT ===
