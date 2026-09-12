#!/usr/bin/env python3
"""build_vwo011_prompt.py — generate the VWO-011 wave-4 worker prompt.

VWO-011 (Universal Computer Task Taxonomy and Coverage Benchmark) — the
wave-4 entry work order, unblocked by the VWO-010 merge (base = the merged
main head at build time). VWO-012..014 run only AFTER VWO-011.

ANALYST/AUTHOR work order: the worker authors the versioned benchmark
catalog under docs/validation/north-star/ (taxonomy, scenario IDs, scoring,
coverage matrix). It does NOT implement product code, does NOT execute the
benchmark tasks (VWO-012..016 do that), and does NOT render any verdict.

Echo-safety: prior-art SHAs appear only in bracketed annotations; the
completion marker is the angle-bracket template form (filled only by the
worker's real report); queue_watch gates on the filled-regex (hits>=1000).

Usage: build_vwo011_prompt.py <repo-path> <base-sha>
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "worker-prompts")
os.makedirs(PROMPTS, exist_ok=True)  # ephemeral dir: rebuild-safe


def build(repo_path, base_sha):
    prompt = f"""WORK ORDER: VWO-011 — Universal Computer Task Taxonomy and Coverage Benchmark
ROLE: Validation Analyst / Benchmark Author (senior). You turn the north-star
claim — automate anything a human can do on a computer — into a measurable,
repository-native coverage model. You are an AUTHOR: you create documents
under docs/validation/north-star/ and run consistency checks; you do NOT
implement product code, you do NOT execute benchmark tasks (VWO-012..016
execute them later), and you do NOT render any capability verdict.

ENVIRONMENT (sandbox — you have a shell, git, and network):
1. `git clone https://github.com/payswapdotorg/codex` (public, anonymous).
   Verify the exact base: `git rev-parse {base_sha}^{{commit}}` — main's
   head as of dispatch (waves 0-3 MERGED: VWO-001..010 all on main, the
   VWO-010 synthesis + RWO-001..012 proposals included). If that commit is
   unreachable, base on origin/main HEAD and RECORD the exact SHA you based on.
2. `cd codex && git checkout -b vwo-011/task-taxonomy-coverage-benchmark` on
   that base.
3. THE CLONE WINS over every condensed note below; if anything disagrees,
   the repository documents win and you must say so in your deviations.

BOOTSTRAP (read in the repo, in order):
1. docs/validation/VALIDATION-PROGRAM.md (program contract; §5 wave-4,
   §12 completion gate)  2. docs/validation/north-star/README.md (the
   north-star test model, coverage dimensions, evidence discipline, claim
   boundary)  3. docs/validation/work-orders/VWO-011.md (this work order —
   its Required task dimensions and Required benchmark artifacts are your
   acceptance contract)  4. docs/validation/validation-dependency-graph.json
   5. docs/validation/scenarios/SCENARIO-CATALOG.md and TEACHING-MODE-MATRIX.md
   (the existing scripted scenario inventory)  6. docs/validation/reports/
   SCENARIO-ISSUE-MATRIX.md (the VWO-010 synthesis: 34 scenario rows,
   canonical P0/P1 families A-I)  7. docs/validation/reports/REPORT-SCHEMA.md
   (report format contract; the benchmark's per-task records must align with
   its evidence fields, and the north-star README adds the extra fields).

CONTEXT (condensed by the Tech Lead from the merged state; THE CLONE WINS):
- Validated so far (waves 0-2, reports on main at your base): realistic
  human workflows across the five synthetic fixture apps (construction,
  software, rideshare, media, marketplace FlowMart) — all BROWSER-app
  surfaces; all three teaching modes exercised; adversarial classes
  REPELLED/Held: restart/persistence, security/trust-boundary,
  versioning/marketplace/entitlement. Wave-3 synthesis [2d37cc0] classified
  9 canonical P0/P1 families A-I and authored remediation work orders
  RWO-001..012 (PROPOSED; remediation workers are IN FLIGHT but NOT merged
  — do not block on them, and do not mark their findings fixed).
- NOT yet validated (the benchmark must define, not execute): native desktop
  GUI tasks; browser/web-app tasks beyond the five fixtures; terminal/CLI;
  filesystem/document manipulation; API/tool/MCP-first tasks;
  cross-application/multi-environment tasks; long-running/parallel tasks;
  held-out (unseen) human goals. Those lanes belong to VWO-012 (desktop),
  VWO-013 (browser), VWO-014 (terminal/filesystem/developer), VWO-015
  (cross-app), VWO-016 (held-out generalization).

TASK (in order; every step produces a file under docs/validation/north-star/):
1. TASK-TAXONOMY.md — the full dimension set from VWO-011's 'Required task
   dimensions' (environment modality; interaction modality; statefulness;
   application boundaries; data shape; human involvement; failure/adaptation
   requirements; and every listed bullet). For each dimension: a rigorous
   definition, its classification values, and how a concrete task is placed
   on it. State the composition rule (a task = one value per dimension).
2. BENCHMARK-CATALOG.md — a VERSIONED catalog (record benchmark_version:
   1.0.0 and a changelog section) of benchmark scenario IDs. ID scheme:
   NST-D### (desktop), NST-B### (browser), NST-T### (terminal/filesystem/
   developer), NST-X### (cross-application/multi-environment), NST-H###
   (held-out). For every scripted/human-authored task record: scenario ID;
   task-taxonomy dimension values; expected user goal (plain human terms);
   observable success criterion (machine-checkable or inspector-checkable,
   never model-text); required environments/capabilities/resources;
   difficulty level (definition + value); scripted vs human-authored vs
   held-out; the executing wave WO (012/013/014/015/016). Sizing: enough
   tasks per lane for that lane's WO to claim coverage (>=8 for each of
   NST-D/B/T; >=6 NST-X; NST-H defines the SELECTION PROCEDURE ONLY — the
   held-out tasks themselves must NOT be enumerated (that would defeat
   holding them out); specify who authors them, when, from what task-space
   sampling rules, and how they stay unseen until execution time).
3. SCORING.md — scoring rules: pass/fail per success criterion; partial
   credit policy; evidence required per task run (align with north-star
   README evidence discipline: exact repo SHA, scenario ID, human goal,
   teaching mode, environments, applications, capabilities/resources
   inferred, workflow/version identity, expected vs actual, computer-side
   result evidence, recovery/adaptation, human intervention, failure
   classification, product friction; NEVER model text as execution
   evidence); revalidation rule (affected lanes re-run after remediation
   merges); a no-regression rule for benchmark integrity (catalog is
   versioned; changing semantics requires a version bump).
4. COVERAGE-MATRIX.md — four SEPARATE matrices, exactly as VWO-011
   requires: ARCHITECTURE coverage (which semantic planes/crates have been
   exercised vs not — engine contracts, adapters, teaching compiler, forge,
   app plane; cite the merged reports for what ran), ENVIRONMENT coverage
   (browser fixture apps: validated; native desktop/terminal/filesystem/
   API-tool/MCP/mixed: benchmark-pending), INTERACTION coverage (GUI,
   browser, terminal, file, API/tool/MCP, human-in-the-loop: validated vs
   pending), GENERALIZATION coverage (scripted vs human-authored vs held-out
   status). Every matrix row carries: status (validated-with-evidence /
   benchmark-pending / explicitly-out-of-scope-v1), evidence pointer
   (report + scenario ID) or owning benchmark NST lane, and what remains
   untested. Include the ADD-NEW-FAMILY PROCEDURE: how a new task family is
   added to the catalog WITHOUT changing workflow semantics (version bump +
   new NST IDs + taxonomy mapping; no engine/runtime changes) — VWO-011's
   acceptance demands a reviewer can determine exactly this.
5. SELF-CHECK (run and record results): every taxonomy dimension has >=1
   catalog task or an explicit out-of-scope-v1 note with reason; every
   catalog task maps to exactly one lane + executing WO; every
   validated-with-evidence row cites a report that exists at your base;
   the forbidden list is respected (no universality claim from existing
   passes; no browser-narrowing — desktop/terminal/cross-app lanes are
   first-class; no second workflow engine or benchmark runtime is proposed;
   no finite list is presented as the definition of all computer tasks —
   state the claim boundary explicitly, citing north-star README).
6. Commit everything on your branch (single commit, message:
   'docs(validation): VWO-011 universal computer task taxonomy and coverage
   benchmark'). Keep ALL files in the sandbox working tree (the Tech Lead
   harvests your workspace; the sandbox tar is the delivery channel). Keep
   the sandbox disk lean.
7. DO NOT PUSH (no credentials; the Tech Lead independently verifies,
   pushes, and merges).

RULES (non-negotiable):
- Source-first: read the actual tree; never assume how Codex works.
- Evidence-first: every 'validated' coverage row cites a report section,
  scenario ID, or file path that exists at your base.
- No fabrication: if you cannot verify a claim, mark it unverified.
- Honest deviations: the final message lists every deviation from this
  packet.
- No contract mutation: you add NEW files under docs/validation/north-star/
  only; you do not edit any existing file (not the reports, not the
  scenario catalog, not the program docs). No credentials in any file.

FINAL MESSAGE (exact format, as your last chat message):
=== VWO-011 COMPLETION REPORT ===
- Work Order ID: VWO-011
- base branch + base SHA: main @ <exact SHA you based on>
- head SHA (your branch, after your commit):
- changed files/surfaces:
- implementation summary (taxonomy dimensions count, catalog sizes per
  lane, scoring rules, coverage-matrix row counts per matrix):
- verification commands and exact results (self-check outcomes):
- required-artifacts evidence (map each VWO-011 'Required benchmark
  artifacts' bullet to its file):
- acceptance evidence (state explicitly how a reviewer can determine
  validated vs untested vs how families are added):
- forbidden-list compliance:
- known limitations / honest deviations:
=== END VWO-011 COMPLETION REPORT ===

DELIVERY NOTE: also create a git bundle of exactly your commit:
`git bundle create /home/z/my-project/VWO-011-delivery.bundle {base_sha}..vwo-011/task-taxonomy-coverage-benchmark`
"""
    out = os.path.join(PROMPTS, "VWO-011.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"wrote {out} ({len(prompt)} chars)")
    # echo-safety self-check: marker lines must be template forms only.
    for line in prompt.splitlines():
        if "COMPLETION REPORT ===" in line and "VWO-011" in line:
            assert "<exact SHA you based on>" in prompt or "END" in line, line
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
