# TL3 Product-Readiness Audit — Worker C (Resources/Continuity)

You are Worker C of the Flauz TL3 fleet (Resources/Continuity domain). This is a self-contained work order: everything you need is in this prompt. Work autonomously to completion.

## STEP ZERO (pinned)
- Repo: https://github.com/payswapdotorg/Flauz (public; plain HTTPS clone, no auth).
- Base SHA: c27de198e14576a9e4ef84681ff061b72f452795 — clone and checkout EXACTLY this. Verify with `git rev-parse HEAD`.
- Branch (local): tl3/pc-resources-continuity-audit
- RE-ENTRY LAW: if your workspace is ever destroyed or files vanish, RE-CLONE at the pinned base, re-create your files from your context, re-run the gates, re-deliver. NEVER report results from memory alone.

## Mission
The Flauz product acceptance phase (P2-002/P2-003) is exercising the integrated product end to end, and the journey ENDS on your surface: restart -> resume task -> inspect continuity/provenance. Your job: a product-readiness AUDIT + FIX pass on extensions/flauz-resources (the whole extension) PLUS extensions/flauz-environments/src/continuityExec/ and src/continuity.ts (the continuity execution core — yours this wave; Worker B does NOT touch them) — find the real defects an acceptance journey would hit, fix them, prove each fix with tests. Quality over volume.

## Read first (in this order)
1. docs/FLAUZ-PROGRAM/TL3-PRODUCT-HANDOFF.md (your ownership boundary)
2. docs/FLAUZ-PROGRAM/ARCHITECTURE-LOCK.md (the laws)
3. extensions/flauz-resources/README.md; extensions/flauz-environments/README.md (continuity sections)
4. The source you will audit: extensions/flauz-resources/src/ (api.ts, graph.ts, provenance.ts, journalBridge.ts, continuity.ts, extension.ts, views.ts) + extensions/flauz-environments/src/continuityExec/ and src/continuity.ts

## Audit checklist (execute every item; record evidence for each)
Journey-shaped scenarios (the P2-002 resource/continuity steps + restart/recovery):
1. RESOURCEREF IDENTITY: mint refs for every kind; verify URN ids are stable, unique, and distinct from access surfaces (the law: identity != access). Two refs for the same logical resource under different access surfaces must NOT collapse into one id, and one id must never mint two access surfaces.
2. TYPED EDGES: exercise the edge vocabulary (attribution, dependency, restoration-plan edges); verify edge invariants (no dangling refs, no self-edges, cycle policy as documented).
3. PROVENANCE LEDGER (.flauz/resources.json + resources-ops.jsonl): every mutation appends exactly one canonical record (recursively-sorted-keys compact JSON, one \n per record); concurrent-append discipline (DL-77 serialized-append law) holds — no interleaved/corrupt records under concurrent ops; malformed lines fail closed, never crash the reader.
4. RESTORATION PLANNING: build a restoration plan over a small graph (browser session + environment + files); verify the plan's steps reference existing refs and the plan survives ledger reload.
5. CONTINUITY EXPORT: export a bundle (content-addressed, flauz:continuity:<16-hex> ids); verify SECRET-REDACTION — secret-shaped payloads (tokens, keys, passwords in any field) are redacted in the bundle, and the redaction is verifiable (the verify command detects a tampered/un-redacted bundle).
6. CONTINUITY VERIFY/STATUS: run verify + status on (a) a fresh bundle, (b) a tampered bundle (flip one byte in a content-addressed member) — verify must FAIL CLOSED with a typed error naming the member; status must never mutate.
7. CONTINUITY RESTORE: force-gated atomic restore — restore a bundle over live state; verify atomicity (abort mid-restore leaves pre-restore state intact); the planSwitch hand-off (continuityBundleId) carries the bundle id end to end.
8. RESTART RECOVERY (the P2-002 step-13/14 shape): full sequence — create resources + environment + browser-journal entries, export bundle, DESTROY all local state (delete .flauz state files), restart (fresh manager instances), restore from bundle, resume — verify every resource/env ref, provenance edge, and journal bridge entry is back with identity preserved and provenance INTACT (no minted-fresh-that-looks-old identities).
9. JOURNAL BRIDGE (flauz.res.syncBrowserSessions): strict READ-ONLY parse of .flauz/browser-sessions.jsonl (PIN-1, flauz.browser-session-journal/v0); ResourceRef minting from logical session ids must be deterministic (same journal -> same refs); attribution-real edges only (no synthetic attribution); malformed journal input -> typed error, no partial import.
10. COMMAND SURFACE: every flauz.res.* / continuity command checks its preconditions before mutating; verify/status/list are side-effect free.

## Ownership boundary (HARD LAW)
- You may ONLY modify: extensions/flauz-resources/** AND extensions/flauz-environments/src/continuityExec/** + extensions/flauz-environments/src/continuity.ts (+ their tests/fixtures). Worker B owns the REST of flauz-environments this wave — do not modify lifecycle/, providers/, resolver/, api.ts, registry.ts, extension.ts of flauz-environments.
- You must NOT touch: src/vs/**, other extensions, .github/**, docs/FLAUZ-PROGRAM/**, product.flauz.json. Root causes outside your boundary -> COMPATIBILITY NOTE (file:line, evidence, suggested fix), never an implementation.
- Laws that must NOT weaken: identity distinct from access surface; provenance preserved through every path; secret-redaction in continuity bundles; fail-closed on corrupt input; read-only bridge parse.

## Method
1. Clone at the pinned base. Install: `cd extensions/flauz-resources && npm install` AND `cd extensions/flauz-environments && npm install` (or bun install).
2. BASELINE (before any edits): for BOTH extensions run `npx tsc --noEmit` (exit 0) and `node --test "test/*.test.ts"` — record exact pass/fail/skip counts verbatim. Red at base = record as PRE-EXISTING finding, continue.
3. Audit the checklist; prefer focused probe tests over ad-hoc scripts (probes become regression tests when a defect confirms).
4. Fix every confirmed defect in your owned paths; one logical commit per defect; every fix gets a regression test that fails at base and passes at the fix.
5. Re-run ALL FOUR gates at the fixed tree (both extensions): typecheck exit 0 each; tests >= baseline counts (new tests added, none lost).
6. Hygiene: no secrets anywhere (redaction TEST fixtures use obvious fake shapes clearly marked as fixtures); match each file's existing style exactly; do not reformat untouched code; no console.log left in src.

## Delivery (no push credentials in this environment — workspace delivery)
Write these files at your WORKSPACE ROOT (exact paths):
- `tl3-pc-audit/findings.md` — audit table: one row per checklist item (item, what you ran, observed, verdict PASS/DEFECT/PRE-EXISTING, fix ref)
- `tl3-pc-audit/delivery.patch` — `git format-patch <base>..<branch>` output
- `tl3-pc-audit/baseline.txt` — verbatim baseline gate outputs (both extensions)
- `tl3-pc-audit/fixed-gates.txt` — verbatim fixed-tree gate outputs (both extensions)
Do NOT attempt `git push` (no credentials; it will fail). The station harvests your workspace files.

## Completion report (post EXACTLY this format in your final chat message; first line verbatim)
TL3-P2 READINESS REPORT
Worker: C (Resources/Continuity) — base c27de198e1
BASELINE: resources typecheck <exit> tests <p>/<f>/<s>; environments typecheck <exit> tests <p>/<f>/<s>
FINDINGS: <n> confirmed defects / <m> fixed / <k> pre-existing / <c> compatibility notes
FIXES: one line each — <defect> -> <fix> -> <regression test name>
GATES AT FIX: all four gates + deltas explained
DELIVERY: tl3-pc-audit/{findings.md,delivery.patch,baseline.txt,fixed-gates.txt} present in workspace
COMPATIBILITY NOTES: <file:line — issue — suggested owner-side fix> (or NONE)
REMAINING RISK: <honest one-liner>
