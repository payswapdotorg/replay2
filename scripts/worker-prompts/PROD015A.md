# PROD-015a — Product-readiness evidence package assembly (NOT the declaration)

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules — READ THIS SECTION TWICE

- ONE work item: PROD-015a (the evidence-package ASSEMBLY for the final
  production-readiness gate). You are assembling, citing and generating
  EVIDENCE — you are NOT declaring readiness and you are NOT judging the
  gates. **The declaration is reserved to the Tech Lead** ("No worker narrative
  alone can satisfy the gate" — docs/productization-roadmap.md). Your manifest
  reports WHAT THE EVIDENCE SHOWS, per item, with file citations — the PASS
  verdicts you record are the EVIDENCE's verdicts (test outputs, check runs),
  never your own opinion.
- Explicit non-scope: `docs/productization-state.json` (NEVER touch — the Lead
  declares), the root `README.md` (the Lead publishes), `docs/PRODUCTION-READINESS-GATE.md`
  (read-only authority), any HFX item, any product feature, `spec/**` (FROZEN).
- Owned surface (the ONLY files you may create/modify):
  - `docs/productization-evidence/PROD-015/**` (the evidence package — NEW)
  - `docs/productization-evidence/README.md` (MODIFY only if absent — an index
    of the evidence folders; do not rewrite per-item evidence)
- The deployed URL for the deployed-check re-run: the Lead has ALREADY
  redeployed `<DEPLOYED_URL>` at commit `<FINAL_SHA>` before your dispatch
  (verify this first — see §3 step 0; if the deployment does not match, STOP
  and report, do not assemble stale evidence).
- Deterministic-only for anything you RUN locally: no network beyond the
  deployed URL checks and the git clone, no clock reads in code you write, no
  randomness. The deployed-check suite exercises the real deployed target.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout <FINAL_SHA>   # the Lead pins this at dispatch (post-PROD-014 main)
git rev-parse HEAD         # must print <FINAL_SHA>
BASE=$(git rev-parse HEAD)
bun install
git checkout -b prod-015a/evidence-package
bun run verify             # baseline: the Lead reports the exact expected count
```

## 2. Mandated reading (in order, before writing anything)

1. `docs/productization-roadmap.md` — the "Definition of done" section (search
   `PROD-015 is the only authority`): the binding evidence-package item list
   (your §3 checklist, verbatim).
2. `docs/PRODUCTION-READINESS-GATE.md` — Gates A–I (the declaration's
   requirements; your evidence maps onto them).
3. `docs/productization-evidence/**` — EVERY existing evidence folder (PROD-010
   through PROD-029 + PROD-012-R + HFX-000): know what is already proven and
   where it lives. This is your citation corpus.
4. `docs/DEPLOYMENT.md` + `docs/free-tier-deployment.md` + `tools/deploy-vercel.md`
   — the deployed shape, the provider table (plans/tiers/allowances), the
   deploy runbook.
5. `docs/COST-GUARDS.md` — the quota/spend-guard evidence base.
6. `tools/deployed-check.ts` + `tools/deployed/` — the seven-check deployed
   verification suite you will RE-RUN (§3 item 10).
7. `docs/EVALUATOR-GUIDE.md` + `docs/INSTALL.md` — PROD-014's evaluator path
   (the fresh-install evidence items cite its transcript).
8. `docs/productization-state.json` (READ-ONLY) — the machine truth: which
   items are finalized, the deployment section (publicUrl, deployment id,
   deployedApplicationCommit — updated by the Lead at redeploy).

## 3. The work — the evidence package (docs/productization-evidence/PROD-015/)

For EVERY item on the roadmap's Definition-of-Done list (below, verbatim), the
manifest gets one row with: the item, the STATUS of its evidence (exists /
generated-by-you / Lead-artifact-pending), the exact file citation(s) with
their owning work item, and — where the item is a transcript — the captured
output. The items:

1. fresh-machine install transcript → cite PROD-014's fresh-checkout
   transcript; if it does not cover a step, generate the missing transcript
   deterministically (a fresh `git clone` of YOUR delivery commit →
   `bun install --frozen-lockfile` → capture).
2. local production-like start transcript → run the documented one-command
   demo path (`bun run demo --fresh` per EVALUATOR-GUIDE.md) at your base;
   capture the full transcript (install → migrate → seed → build → start →
   smoke) into `local-demo-transcript.txt`.
3. public HTTPS URL → record `<DEPLOYED_URL>` + the smoke outputs (§3 step 0).
4. Vercel deployment identifier → from `docs/productization-state.json`'s
   deployment section (the Lead's redeploy record) + `bunx vercel ls` output
   if credentials are configured (they are NOT in your sandbox — cite the
   state record; do not fabricate).
5. configured provider list and plan/tier evidence → the provider table from
   `docs/free-tier-deployment.md` + what the deployment ACTUALLY uses (the
   zero-external-server demo shape per DEPLOYMENT.md §2-3 — document it
   HONESTLY: Vercel Hobby + Upstash Redis free pair + application-owned auth;
   Neon/R2 documented as the reference shape with the demo deployment's
   honest current state).
6. database migration/bootstrap evidence → from the local demo transcript
   (item 2) — the migrate + seed phases.
7. object upload/download evidence → what the deployed shape supports TODAY:
   cite the artifacts module's local artifact path + the honest demo-deployment
   state; if a real upload/download round-trip is exercisable via the local
   demo, capture it; otherwise record the documented equivalent explicitly.
8. Redis queue/cache/session evidence → the deployed `/readyz` cost.ledger
   check (the deployed-check availability item proves it) + PROD-011b's
   session-stability walk evidence.
9. optional Apify connector evidence or explicit disabled-state evidence →
   cite the documented optional/disabled state (COST-GUARDS.md + the env
   schema's optional connectors).
10. browser/mobile/desktop adapter conformance evidence → cite PROD-017
    (browser), PROD-019 (Android), PROD-020 (desktop) evidence + RE-RUN the
    deployed-check suite: `AISE_DEPLOYED_URL=<DEPLOYED_URL> bun tools/deployed-check.ts`
    — capture the FULL output to `deployed-check-rerun.txt`. EXPECTATION: the
    two historical FAILs (mobile overflow; .journey-hint contrast) now PASS
    (the PROD-012-R fixes are deployed at <FINAL_SHA>). If any check FAILS,
    capture it faithfully — it goes to the Lead, not to a silent pass.
11. full golden user-journey browser recording → Lead artifact (Gate F) —
    mark `Lead-artifact-pending: docs/productization-evidence/PROD-015/gate-f/`
    (the Lead commits both journeys' records there).
12. representative Android/mobile capture journey evidence → cite PROD-019's
    field-journey.md.
13. desktop adapter build and smoke evidence → cite PROD-020's
    desktop-smoke-trace.md.
14. interactive solution building journey recording → Lead artifact (Gate F,
    journey 2) — same pending marker.
15. deterministic solution replay and validation evidence → cite PROD-022
    (determinism.md) + PROD-026 evidence.
16. generated solution BOQ with bidirectional step/line trace evidence →
    cite PROD-025 + PROD-026 (boq-trace-conformance.md).
17. representative physical/building benchmark evidence → cite
    tools/building-benchmark/ (the committed scenario + test) + PROD-026.
18. responsive/accessibility evidence → your deployed-check re-run (item 10)
    + the PROD-012-R remediation record.
19. next-best-action/task-first UX evidence → cite PROD-016/PROD-021/PROD-024
    evidence per the post-simulation plan's journey model.
20. competitive benchmark evidence → cite PROD-018
    (competitive-simulation-rerun.md + capability-matrix.md).
21. free-tier quota/cost guard evidence → cite COST-GUARDS.md + the provider
    table + any quota-exhaustion behavior tests in the corpus (find them).
22. security/tenant-isolation evidence → cite the tenant/project
    authorization tests (find them in the verify corpus — e.g. via
    `bun run verify` output grouping) + PROD-012's session-lifecycle
    fail-closed check.
23. `bun run verify` result at the final merged SHA → YOUR OWN gate run at
    <FINAL_SHA> (the §7 gates) — the exact counts, pasted.
24. exact commit SHA and environment/configuration fingerprint →
    <FINAL_SHA> + the fingerprint table (node/bun versions, the env-schema's
    required-vs-optional vars for the demo shape, the deployment's
    configured env per DEPLOYMENT.md §3 — NAMES only, never values).

Deliverables:
- `README.md` — the manifest: the 24-row table (item → status → citations),
  the overall evidence picture, the explicit "Lead-pending" list (Gate F
  artifacts + the declaration), and the honest gaps (if any item's evidence
  is genuinely absent from the corpus, SAY SO — a gap reported is honest; a
  gap papered over is a gate violation).
- `local-demo-transcript.txt` — item 2's captured transcript.
- `deployed-check-rerun.txt` — item 10's captured full output.
- `fingerprint.md` — item 24.
- `provider-evidence.md` — items 5/7/8/9 consolidated (the honest deployed
  shape + the reference shape + citations).

## 4. Honesty rules (Gate D applies to the evidence itself)

- Every citation must name a real file at a real path — no invented paths.
- Every captured transcript is the REAL output — no edits, no trimming beyond
  explicit `[... N lines ...]` markers that preserve the meaning.
- The deployed-check re-run result is reported EXACTLY as it ran.
- Gaps are reported as gaps. The manifest's value is its trustworthiness.

## 5. Gates (all must pass before delivery)

```bash
bun run verify        # the Lead-reported baseline count, 0 fail — VERIFY: PASS
bun run typecheck     # PASS
bun run lint          # PASS
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's
harvest API cannot see. After committing, copy EVERY new/changed file (the
complete diff vs the base commit `$BASE` from §1) into the PROJECT directory
(the one containing package.json / src/ — the workspace root), preserving
repo-relative paths:

```bash
cd /home/z/AISE
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery. Do NOT change anything else after the
gate run. No re-runs, no edits, no push.

## 7. Completion report (post as your FINAL message)

```text
PROD015A COMPLETION REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Evidence manifest summary
- items with existing evidence cited: <count>/24
- items you generated transcripts for: <the list>
- Lead-pending items (Gate F + declaration): <the list>
- HONEST GAPS: <the list, or "none">

## Deployed-check re-run vs <DEPLOYED_URL>
- overall: <DEPLOYED: PASS/FAIL>
- the two historical FAILs (mobile overflow, journey-hint contrast): <PASS/FAIL each — the PROD-012-R re-verification>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
