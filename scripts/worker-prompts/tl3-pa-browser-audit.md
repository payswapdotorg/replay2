# TL3 Product-Readiness Audit — Worker A (Browser)

You are Worker A of the Flauz TL3 fleet (Browser domain). This is a self-contained work order: everything you need is in this prompt. Work autonomously to completion.

## STEP ZERO (pinned)
- Repo: https://github.com/payswapdotorg/Flauz (public; plain HTTPS clone, no auth).
- Base SHA: c27de198e14576a9e4ef84681ff061b72f452795 — clone and checkout EXACTLY this. Verify with `git rev-parse HEAD`.
- Branch (local): tl3/pa-browser-audit
- RE-ENTRY LAW: if your workspace is ever destroyed or files vanish, RE-CLONE at the pinned base, re-create your files from your context, re-run the gates, re-deliver. NEVER report results from memory alone.

## Mission
The Flauz product acceptance phase (P2-002/P2-003) is exercising the integrated product end to end. TL3 owns browser semantics. Your job: a product-readiness AUDIT + FIX pass on extensions/flauz-browser — find the real defects an acceptance journey would hit (and route as P2-FIX findings), fix them in TL3-owned paths, and prove each fix with tests. Quality over volume: a small set of REAL, verified fixes beats a big speculative diff.

## Read first (in this order)
1. docs/FLAUZ-PROGRAM/TL3-PRODUCT-HANDOFF.md (your ownership boundary)
2. docs/FLAUZ-PROGRAM/ARCHITECTURE-LOCK.md (the laws)
3. extensions/flauz-browser/README.md and extensions/flauz-browser/INTEGRATION-GAP.md
4. The source you will audit: extensions/flauz-browser/src/ (policy.ts, runtime/, cdp/, extension.ts, views.ts, format.ts, marks.ts)

## Audit checklist (execute every item; record evidence for each)
Journey-shaped scenarios (the P2-002 browser steps + failure/recovery):
1. SESSION LIFECYCLE: create agent session -> navigate (allowed + denied) -> capture -> evidence -> close. Verify human/agent session separation is airtight: an agent session can NEVER touch the human session's tabs, and a human tab is never adoptable without explicit policy.
2. FAIL-CLOSED POLICY: for every deny path (blocked URL, download, popup/new-target, CDP bypass attempt), verify ZERO CDP commands are sent after the deny decision (the law: deny sends zero CDP commands). Hunt for any path where a deny is decided but a command still went out.
3. DOWNLOAD DENY + NEW-TARGET GATE: simulate downloads and window.open targets in the test simulator; verify typed denial evidence rows.
4. FORCED RESET (security.enforceReset): verify the G6 forced-reset execution clears session state completely (no residue: tabs, storage refs, journal entries for the destroyed session).
5. PARTITION OWNERSHIP: verify partition-scoped tab ownership — a tab created under partition P cannot be addressed from partition Q (probe the manager from two partitions).
6. SESSION JOURNAL (PIN-1 .flauz/browser-sessions.jsonl, schema flauz.browser-session-journal/v0): verify append integrity — every state transition appends exactly one canonical record (recursively-sorted-keys compact JSON, one \n per record). Corrupt-input handling: malformed lines must be skipped/fail-closed, never crash the journal reader.
7. CAPTURE -> EVIDENCE: verify capture provenance fields (session id, partition, timestamp, uri) are complete and tamper-evident on every capture.
8. RECOVERY: verify recovery after a simulated mid-operation disconnect (transport drop during navigate/capture) — the session must recover or fail CLOSED with typed errors, never hang or half-adopt state.
9. CONTRACT SWEEP: read every exported type/command of the extension; flag any command that can mutate state WITHOUT its required policy/trust check.

## Ownership boundary (HARD LAW)
- You may ONLY modify: extensions/flauz-browser/** (src, test, fixtures, README/INTEGRATION-GAP docs).
- You must NOT touch: src/vs/** (product core), any other extension, .github/**, docs/FLAUZ-PROGRAM/**, product.flauz.json, package.json at repo root. If a defect's root cause is outside your boundary, DO NOT implement it — record a COMPATIBILITY NOTE (exact file:line, evidence, suggested fix) in your report.
- Laws that must NOT weaken: fail-closed browser policy; human/agent session isolation; deny-sends-zero-CDP-commands; capture provenance; journal canonical form.

## Method
1. Clone at the pinned base. Install: `cd extensions/flauz-browser && npm install` (or bun install).
2. BASELINE (must run before any edits): `npx tsc --noEmit` (exit 0) and `node --test "test/*.test.ts"` — record exact pass/fail/skip counts verbatim. If a gate is red at base, record it as a PRE-EXISTING finding and continue.
3. Audit: work the checklist. Prefer adding a focused probe test over ad-hoc scripts when unsure of behavior (probe tests also become your regression tests if a defect confirms).
4. Fix every confirmed defect in your owned paths. One logical commit per defect (or a single squashed commit if the fixes form one logical unit). Every fix gets a regression test that fails at base and passes at the fix.
5. Re-run BOTH gates at the fixed tree. Typecheck must be exit 0; test counts must be >= baseline (your new tests added, zero pre-existing tests lost).
6. Hygiene: no secrets/credentials anywhere; no console.log left in src; match each file's existing style exactly (quotes, indentation, import style); do not reformat untouched code.

## Delivery (no push credentials in this environment — workspace delivery)
Write these files at your WORKSPACE ROOT (exact paths):
- `tl3-pa-audit/findings.md` — the audit table: one row per checklist item (item, what you ran, observed, verdict PASS/DEFECT/PRE-EXISTING, fix ref)
- `tl3-pa-audit/delivery.patch` — output of `git format-patch <base>..<branch>` (your fix commits)
- `tl3-pa-audit/baseline.txt` — verbatim baseline gate output
- `tl3-pa-audit/fixed-gates.txt` — verbatim fixed-tree gate output
Do NOT attempt `git push` (no credentials; it will fail). The station harvests your workspace files.

## Completion report (post EXACTLY this format in your final chat message; first line verbatim)
TL3-P2 READINESS REPORT
Worker: A (Browser) — base c27de198e1
BASELINE: typecheck <exit>, tests <pass>/<fail>/<skip>
FINDINGS: <n> confirmed defects / <m> fixed / <k> pre-existing / <c> compatibility notes
FIXES: one line each — <defect> -> <fix> -> <regression test name>
GATES AT FIX: typecheck exit 0; tests <pass>/<fail>/<skip> (delta vs baseline explained)
DELIVERY: tl3-pa-audit/{findings.md,delivery.patch,baseline.txt,fixed-gates.txt} present in workspace
COMPATIBILITY NOTES: <file:line — issue — suggested owner-side fix> (or NONE)
REMAINING RISK: <honest one-liner>
