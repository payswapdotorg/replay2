# TL3 Product-Readiness Audit — Worker B (Environments)

You are Worker B of the Flauz TL3 fleet (Environments domain). This is a self-contained work order: everything you need is in this prompt. Work autonomously to completion.

## STEP ZERO (pinned)
- Repo: https://github.com/payswapdotorg/Flauz (public; plain HTTPS clone, no auth).
- Base SHA: c27de198e14576a9e4ef84681ff061b72f452795 — clone and checkout EXACTLY this. Verify with `git rev-parse HEAD`.
- Branch (local): tl3/pb-environments-audit
- RE-ENTRY LAW: if your workspace is ever destroyed or files vanish, RE-CLONE at the pinned base, re-create your files from your context, re-run the gates, re-deliver. NEVER report results from memory alone.

## Mission
The Flauz product acceptance phase (P2-002/P2-003) is exercising the integrated product end to end. TL3 owns environment semantics. Your job: a product-readiness AUDIT + FIX pass on extensions/flauz-environments (lifecycle, providers, resolver — NOT continuityExec, that is Worker C's lane this wave) — find the real defects an acceptance journey would hit, fix them in TL3-owned paths, and prove each fix with tests. Quality over volume.

## Read first (in this order)
1. docs/FLAUZ-PROGRAM/TL3-PRODUCT-HANDOFF.md (your ownership boundary)
2. docs/FLAUZ-PROGRAM/ARCHITECTURE-LOCK.md (the laws)
3. extensions/flauz-environments/README.md and extensions/flauz-environments/INTEGRATION-GAP.md
4. The source you will audit: extensions/flauz-environments/src/ (api.ts, registry.ts, extension.ts, lifecycle/, providers/, resolver/, views.ts, format.ts) — SKIP src/continuityExec/ and src/continuity.ts (Worker C owns those this wave; do not modify them).

## Audit checklist (execute every item; record evidence for each)
Journey-shaped scenarios (the P2-002 environment steps + failure/recovery):
1. LIFECYCLE REAL RUN: create -> start -> attach -> detach -> stop -> snapshot -> destroy with the LocalProcessExecutor (real processes). Verify state transitions are exactly the state machine's; no orphaned processes after destroy (pid-tracked SIGKILL escalation must actually fire under a stubborn child).
2. FAILURE CLASSES: exercise every typed failure class the executors declare (start failure, attach to non-running, snapshot of destroyed, CLI_NOT_AVAILABLE, timeout+kill). Each must produce its TYPED error — no raw exceptions leaking, no generic Error where a typed class exists.
3. DESTROY-DURING-OP: destroy issued while start/attach/snapshot is in flight — verify fail-closed behavior: the in-flight op aborts with a typed error, the envelope reaches a terminal state, and no partial state survives.
4. TRUST GATE: every lifecycle op on an untrusted/absent registry entry must be TRUST_REFUSED — hunt for ANY op path that skips the registry + PIN-2 state check. Environment descriptors must NEVER carry credentials.
5. PROVIDER SEAMS (rung 1, real behind contract): SshCliExecutor (system ssh, fixed-harness-over-stdin, descriptor-data auth), DockerCliExecutor (docker daemon, typed CLI_NOT_AVAILABLE when absent), CloudHttpAdapter (injectable HttpPort, apiKeyRef vault-gated). Verify with the FakeCli/mock-server suites: capability probes, typed failure taxonomy, no secret materialization anywhere.
6. RESOLVER RUNG 2: src/resolver/ — authority grammar flauz-env+<kind>+<envId> (malformed -> AUTHORITY_MALFORMED, nested a@b -> NESTED_TRANSIT), trust/policy gate (untrusted OR no PIN-2 entry -> TRUST_REFUSED; disabled OR non-running -> POSTURE_REFUSED), per-kind endpoint probes through the rung-1 seams (ssh true / docker inspect flauz-<envId> / cloud GET / PIN-2 state), RE-RESOLUTION re-checks CURRENT state (nothing cached — verify a trust flip between resolutions is honored), AHP bridge handshake (bridge port on envelope, token via SecretResolverPort only, --agent-host-port mutual exclusion -> BRIDGE_MISCONFIGURED).
7. PIN-2 ENVELOPES (.flauz/environments-lifecycle.json + environments-ops.jsonl): canonical JSONL discipline (recursively-sorted-keys, compact, one \n per record); malformed-line handling fails closed; every op appends exactly one record.
8. RESTART RECOVERY: kill the process mid-lifecycle; verify recovery reads the ledger + envelopes and reaches consistent state (no env stuck in a non-terminal state that the ledger says terminated).
9. COMMAND SURFACE: every flauz.env.* command checks trust+posture BEFORE acting; list/read commands never mutate.

## Ownership boundary (HARD LAW)
- You may ONLY modify: extensions/flauz-environments/** EXCEPT src/continuityExec/ and src/continuity.ts (Worker C's lane this wave — hands off).
- You must NOT touch: src/vs/**, other extensions, .github/**, docs/FLAUZ-PROGRAM/**, product.flauz.json. Root causes outside your boundary -> COMPATIBILITY NOTE (file:line, evidence, suggested fix), never an implementation.
- Laws that must NOT weaken: explicit environment trust (untrusted = TRUST_REFUSED); no credentials in descriptors; typed failure taxonomy; fail-closed on corrupt state; vault-only secrets.

## Method
1. Clone at the pinned base. Install: `cd extensions/flauz-environments && npm install` (or bun install).
2. BASELINE (before any edits): `npx tsc --noEmit` (exit 0) and `node --test "test/*.test.ts"` — record exact pass/fail/skip counts verbatim. Red at base = record as PRE-EXISTING finding, continue.
3. Audit the checklist; prefer focused probe tests over ad-hoc scripts (probes become regression tests when a defect confirms). The liveRemote suites are SKIP-gated by design — do not force them; verify them via the FakeCli/mock drills.
4. Fix every confirmed defect in your owned paths; one logical commit per defect; every fix gets a regression test that fails at base and passes at the fix.
5. Re-run BOTH gates at the fixed tree: typecheck exit 0; tests >= baseline counts (new tests added, none lost).
6. Hygiene: no secrets anywhere; match each file's existing style exactly; do not reformat untouched code; no console.log left in src.

## Delivery (no push credentials in this environment — workspace delivery)
Write these files at your WORKSPACE ROOT (exact paths):
- `tl3-pb-audit/findings.md` — audit table: one row per checklist item (item, what you ran, observed, verdict PASS/DEFECT/PRE-EXISTING, fix ref)
- `tl3-pb-audit/delivery.patch` — `git format-patch <base>..<branch>` output
- `tl3-pb-audit/baseline.txt` — verbatim baseline gate output
- `tl3-pb-audit/fixed-gates.txt` — verbatim fixed-tree gate output
Do NOT attempt `git push` (no credentials; it will fail). The station harvests your workspace files.

## Completion report (post EXACTLY this format in your final chat message; first line verbatim)
TL3-P2 READINESS REPORT
Worker: B (Environments) — base c27de198e1
BASELINE: typecheck <exit>, tests <pass>/<fail>/<skip>
FINDINGS: <n> confirmed defects / <m> fixed / <k> pre-existing / <c> compatibility notes
FIXES: one line each — <defect> -> <fix> -> <regression test name>
GATES AT FIX: typecheck exit 0; tests <pass>/<fail>/<skip> (delta vs baseline explained)
DELIVERY: tl3-pb-audit/{findings.md,delivery.patch,baseline.txt,fixed-gates.txt} present in workspace
COMPATIBILITY NOTES: <file:line — issue — suggested owner-side fix> (or NONE)
REMAINING RISK: <honest one-liner>
