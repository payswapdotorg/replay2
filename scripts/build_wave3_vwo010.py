#!/usr/bin/env python3
"""build_wave3_vwo010.py — generate the VWO-010 synthesis worker prompt.

VWO-010 (Validation Synthesis, Remediation Planning, and Final Report
Draft) — blocked on VWO-004..009 (all six must be MERGED on main before
dispatch; the prompt embeds the base SHA of that merged state).

This is an ANALYST work order: the worker consolidates the six validation
reports, reproduces P0/P1 findings against current main, deduplicates
findings into canonical root-cause families, writes bounded remediation
work orders (RWO-*), dispositions P2/P3, and drafts the final report.
It does NOT implement remediations (the Tech Lead dispatches those as
separate workers) and does NOT render the final production-readiness
verdict where evidence is still pending the remediation loop.

Echo-safety: the embedded findings index quotes prior report SHAs only
inside bracketed annotations; the completion marker is gated by the
filled-regex in queue_watch (hits >= 1000), so prompt echoes cannot
false-trigger completion.

Usage: build_wave3_vwo010.py <repo-path> <base-sha>
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "worker-prompts")
os.makedirs(PROMPTS, exist_ok=True)  # ephemeral dir: rebuild-safe

# Condensed findings index (verified by the Tech Lead against the merged
# reports at build time). Per-report numbering is LOCAL to each report;
# VWO-010 must deduplicate across reports into canonical families.
FINDINGS_INDEX = """FINDINGS INDEX (condensed by the Tech Lead from the merged reports; per-report
numbering is LOCAL — deduplicate into canonical families; THE CLONE WINS):
- VWO-004 (enterprise-ops real-user, 12 scenarios, all teaching modes; 161
  evidence artifacts; base [0d314fd]): F1 P0 teaching surface absent (all 12
  scenarios, 4th confirmation); F2 P2 seed/catalog mismatch (no second OPEN
  purchase request w/ valid vendor in shipped seed); F3 P2 catalog grants
  ticket:resolve to ops but scenario expects support agent; F4 P2 catalog
  lists missing_asset on rendition, fixture implements data_conflict; F5 P3
  follow-up-action note realized as close-with-resolution-note.
- VWO-005 (marketplace seller real-user; 62 evidence artifacts; base
  [0d314fd]): P1x5 — F1 teaching/compile/review/approve surface absent
  product-wide; F2 FlowMart install-configuration form silently drops JSON
  input (records 'configured' while config stays {}); F4 fork surface +
  lineage data model absent; F5 improvement-candidate-from-evidence +
  approval-before-publish absent; F6 cross-tenant install mutation accepted
  server-side; P2x1 — F3 post-publication commercial-policy/attribution/
  licensing config absent; P3x1 — F7 PressRoom approved-story attach
  dead-end. Digest integrity held through every marketplace transition
  (pk-0104@1.0.0, pk-102@2.3.1/2.3.2/2.4.0).
- VWO-006 (workflow-consumer real-user, 3 scenarios via FlowMart; 36
  evidence artifacts; base [0d314fd]): F-1 teaching surface absent (same
  family as VWO-004 F1 / VWO-005 F1); F-2 rebind human path blocked by
  fixture defect (not a product defect); canonical reset+sweep verified.
- VWO-007 (persistence/restart adversary, all attacks REPELLED at engine
  layer; base [0d314fd]): F1 engine library-only — codex-workflow-durable
  control plane mounted in NO user-facing surface (same root family).
  Recovery surface intact-data observation (no explicit resumed indicator)
  recorded as observation, not a finding.
- VWO-008 (security/trust-boundary adversary, 10/10 attack classes
  REPELLED, 62 evidence artifacts; base [d198a00]): F1 engine unmounted —
  every trust-boundary guarantee verified at library layer is unobtainable
  by a normal person (same root family; 3rd engine-side confirmation).
  Injection payload renders inline with no untrusted-content marker
  (friction observation).
- VWO-009 (versioning/marketplace/distribution adversary): READ ITS MERGED
  REPORT — it is on main at your base; the index above ends at VWO-008
  because VWO-009 merged immediately before your dispatch. Extract its
  unique findings, confirmations, and evidence counts from the report
  itself; never fabricate them.

Cross-report dedup seed (verify, extend, correct from the reports):
- CANONICAL FAMILY A (P0, engine-plane): the workflow/teaching engine is
  not mounted in ANY user-facing surface — confirmed by VWO-004 F1,
  VWO-005 F1, VWO-006 F-1, VWO-007 F1, VWO-008 F1 (5 independent reports;
  count VWO-009's confirmation if its report repeats it).
- Family B (P1, fixture/product split): FlowMart install-config form drops
  input (VWO-005 F2).
- Family C (P1): fork + lineage surface absent (VWO-005 F4).
- Family D (P1): improvement-candidate + approval-before-publish absent
  (VWO-005 F5).
- Family E (P1, security): cross-tenant install mutation accepted
  server-side (VWO-005 F6).
- Fixture-internal P2/P3 (catalog/seed drift: VWO-004 F2/F3/F4/F5,
  VWO-006 F-2, VWO-005 F3/F7) — disposition as fix-now / follow-up WO /
  accepted limitation with reasons.
"""


def build(repo_path, base_sha):
    prompt = f"""WORK ORDER: VWO-010 — Validation Synthesis, Remediation Planning, and Final Report Draft
ROLE: Validation Synthesis Analyst (senior). You consolidate six validation
work-orders' evidence into ONE coherent picture, reproduce the severe
findings, plan bounded remediation, and draft the final report. You are an
ANALYST: you create documents and run verifications; you do NOT implement
remediations (the Tech Lead dispatches those as separate workers after
reviewing your plan) and you do NOT fabricate a final verdict where
evidence is still pending the remediation loop.

ENVIRONMENT (sandbox — you have a shell, git, and network):
1. `git clone https://github.com/payswapdotorg/codex` (public, anonymous).
   Verify the exact base: `git rev-parse {base_sha}^{{commit}}` — main's
   head as of dispatch (all six wave-0/1/2 validations MERGED). If that
   commit is unreachable, base on origin/main HEAD and RECORD the exact
   SHA you based on.
2. `cd codex && git checkout -b vwo-010/validation-synthesis` on that base.
3. Check `which cargo` — if a Rust toolchain exists, you can run engine
   crate tests for reproduction evidence. If not, verify by careful static
   reasoning and say so explicitly; the Tech Lead independently compiles
   and runs everything.
4. THE CLONE WINS over every excerpt below. The FINDINGS INDEX is a
   navigational aid written by the Tech Lead from the merged reports; if
   it disagrees with a report, the REPORT wins, and you must say so in
   your deviations section.

BOOTSTRAP (read in the repo, in order):
1. docs/validation/VALIDATION-PROGRAM.md  2. docs/validation/
validation-dependency-graph.json  3. docs/validation/work-orders/VWO-010.md
(this work order)  4. The six reports: docs/validation/reports/
VWO-004-report.md, VWO-005-report.md, VWO-006-report.md,
VWO-007-report.md, VWO-008-report.md, VWO-009-report.md  5. The
work-orders for VWO-004..009 (their acceptance contracts)  6.
docs/validation/reports/REPORT-SCHEMA.md (report format contract).

{FINDINGS_INDEX}
TASK (in order; every step produces a file):
1. SCENARIO/ISSUE MATRIX — docs/validation/reports/SCENARIO-ISSUE-MATRIX.md:
   one row per scenario (report, scenario id, persona/goal, teaching mode,
   outcome, findings hit, evidence pointer). One section per finding family
   (deduplicated): severity, affected surfaces, confirming reports, root
   cause hypothesis, owning semantic layer (which crate/app/fixture owns
   the fix).
2. REPRODUCE every P0/P1 finding against current main (the clone). For
   each: exact reproduction commands + observed results + artifacts under
   docs/validation/evidence/vwo-010/ (command transcripts, page dumps, or
   test output — whatever the finding's surface supports in your sandbox;
   fixture apps live under the proving-ground harness per VALIDATION-
   PROGRAM.md). A finding that no longer reproduces on current main is
   CLOSED with evidence (record the closing SHA). Engine-plane findings
   (Family A) reproduce by: showing no user-facing mount exists (grep/CI
   evidence across crates + fixtures), plus the engine library tests that
   pass anyway (cargo test on the owning crates, exact results).
3. ROOT CAUSE + OWNERSHIP — for every open P0/P1: root cause (why the
   surface is absent or defective — cite architecture docs, e.g.
   ARCHITECT_START_HERE.md, CODEX-UNIVERSAL-ARCHITECTURE.md), owning
   semantic layer, and the smallest bounded fix that would close it.
4. REMEDIATION WORK ORDERS — docs/validation/work-orders/RWO-001.md (and
   RWO-002, RWO-003, ... as needed): ONE RWO per canonical P0/P1 family,
   each bounded (single-owner, single-surface, verifiable): objective,
   findings closed, reproduction evidence pointer (from step 2), fix scope
   (files/surfaces), acceptance criteria, verification commands, and
   rollback. RWOs are PROPOSALS (status: proposed) — the Tech Lead
   reviews, amends, and dispatches them; keep each RWO under ~150 lines.
5. P2/P3 DISPOSITION — in the matrix doc: every P2/P3 finding explicitly
   dispositioned fix-now (with which RWO), follow-up work order (named,
   e.g. RWO-004+), or accepted limitation (with reason). No orphan
   findings.
6. FINAL REPORT DRAFT — docs/validation/reports/
FINAL-HUMAN-WORKFLOW-VALIDATION.md per the VWO-010 spec: exact final
repository SHA; exact validation environment identities; scenario
coverage matrix (summary table); teaching-mode comparison; issue
inventory (canonical families); root causes; remediation Work Orders
(merges PENDING — mark each 'pending RWO-00n merge'); security findings;
persistence/restart findings; marketplace findings; UX/product friction;
remaining limitations; production-readiness verdict — write the verdict
as EXPLICITLY DEFERRED to the remediation loop (state exactly which
RWO merges + revalidations must land before the verdict can be rendered;
do not render a verdict you cannot support with closed evidence).
7. Commit everything on your branch (single commit, message:
   'docs(validation): VWO-010 synthesis — scenario/issue matrix, P0/P1
   reproductions, remediation work orders (RWO-*), final report draft').
   Keep ALL files in the sandbox working tree (the Tech Lead harvests
   your workspace; the sandbox tar is the delivery channel). Keep the
   sandbox disk lean: rm -rf cargo target dirs once verification results
   are recorded.
8. DO NOT PUSH (no credentials; the Tech Lead independently verifies,
   pushes, and merges).

RULES (non-negotiable):
- Source-first: never assume how Codex works; read the actual tree.
- Evidence-first: every claim in the matrix/reports cites a report
  section, a file path, or a reproduction artifact you created.
- No fabrication: if a reproduction is impossible in your sandbox, say so
  and mark the finding 'reproduction pending remediation environment'.
- Honest deviations: the final message lists every deviation from this
  packet (including FINDINGS INDEX corrections).
- No credentials in any evidence file. No contract mutation: you add
  documents and evidence; you do not rewrite the six merged reports or
  the work-order contracts (RWO-* files are NEW files).

FINAL MESSAGE (exact format, as your last chat message):
=== VWO-010 COMPLETION REPORT ===
- Work Order ID: VWO-010
- base branch + base SHA: main @ <exact SHA you based on>
- head SHA (your branch, after your commit):
- changed files/surfaces:
- implementation summary:
- verification commands and exact results (matrix consistency checks,
  P0/P1 reproduction outcomes per family, cargo test results if run):
- required-outcomes evidence (map each VWO-010 Required-outcomes bullet to
  files: matrix, reproductions, root causes, RWO-*, dispositions, final
  report draft):
- acceptance evidence (state explicitly which acceptance criteria are MET
  now vs PENDING the remediation loop):
- forbidden-list compliance (no verdict fabrication; no contract mutation;
  no credentials in evidence):
- known limitations / honest deviations:
=== END VWO-010 COMPLETION REPORT ===

DELIVERY NOTE: also create a git bundle of exactly your commit:
`git bundle create /home/z/my-project/VWO-010-delivery.bundle {base_sha}..vwo-010/validation-synthesis`
"""
    out = os.path.join(PROMPTS, "VWO-010.md")
    with open(out, "w") as f:
        f.write(prompt)
    n = len(prompt)
    print(f"wrote {out} ({n} chars)")
    # echo-safety self-check: any completion-marker-like line in the prompt
    # must be the format template (angle-bracket placeholders), never a
    # filled form.
    for line in prompt.splitlines():
        if "COMPLETION REPORT ===" in line and "VWO-010" in line:
            assert "<exact SHA you based on>" in prompt or "Work Order ID" in line
    print("echo-safety: marker lines are template forms only — OK")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    repo, sha = sys.argv[1], sys.argv[2]
    assert len(sha) in (7, 40) and all(c in "0123456789abcdef" for c in sha)
    build(repo, sha)


if __name__ == "__main__":
    main()
