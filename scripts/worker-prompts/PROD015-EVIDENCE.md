# PROD-015 — Final product-readiness evidence package (assembly worker)

You are a senior evidence engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly.
The repository itself is your specification library; read the mandated files
below BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-015's EVIDENCE-PACKAGE ASSEMBLY. The repository's
  implementation campaign is COMPLETE; your job is to assemble, cite or
  generate the final product-readiness evidence package — the 25-item
  Definition-of-Done manifest from `docs/productization-roadmap.md` §
  "Definition of done" — against the FINAL merged SHA. You are an evidence
  auditor and assembler: you do NOT change product code, you do NOT declare
  readiness (the declaration is the Tech Lead's, after auditing your
  package), and you do NOT weaken any gate.
- Owned surface (the ONLY files you may create/modify):
  - `docs/productization-evidence/PROD-015/**` EXCEPT the Lead-authored
    files listed below (read them, cite them, never modify them):
    - `docs/productization-evidence/PROD-015/gate-f-browser-proof.md`
    - `docs/productization-evidence/PROD-015/deployed-check-final.md`
- Explicitly NOT yours: EVERYTHING else — all of `apps/**`, `backend/**`,
  `packages/**`, `tools/**` (you may RUN `tools/deployed-check.ts`,
  `bun run verify`, `bun run smoke` etc., you may never MODIFY them),
  `docs/PRODUCTION-READINESS-GATE.md`, `docs/productization-roadmap.md`,
  `docs/productization-state.json` (the declaration edit is the Tech
  Lead's), `docs/INSTALL.md`, `docs/EVALUATOR-GUIDE.md`, `docs/DEPLOYMENT.md`,
  the root `README.md`, the root `package.json`, `bun.lock`, `spec/**`
  (FROZEN), every other directory under `docs/productization-evidence/**`
  (the merged waves' evidence — cite, never touch).
- Honesty doctrine (binding, the gate doc's own words): "No worker narrative
  alone can satisfy the gate." Your manifest must cite REAL artifacts at
  REAL commit SHAs — every citation names the file path and the commit that
  introduced it; every generated capture is the verbatim output of a named
  command. If an item's evidence is genuinely MISSING or partial, you mark
  it GAP with a precise statement of what is absent — a manifest with a
  declared GAP is MORE valuable to the gate than a fabricated PASS. Never
  invent, polish or paraphrase evidence.
- Determinism: your own captures (`verify`, `deployed-check`, `smoke`) are
  runs of committed deterministic tooling — record them verbatim with the
  exact command line and the working-tree SHA.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge upstream
  changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout __PINNED_BASE__   # public GitHub main (final merged lineage; Tech Lead pinned at dispatch)
git rev-parse HEAD   # must print __PINNED_BASE__
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-015/evidence-package
bun run verify
```

Baseline expectation: **__BASELINE__ pass / 0 fail, VERIFY: PASS** (the Tech
Lead's verified number at this SHA). If the baseline is red, STOP and report.

The deployed product: **__DEPLOYED_URL__** (redeployed by the Tech Lead at
exactly this lineage before your dispatch; smoke-checked).

## 2. Mandated reading (in order, before writing anything)

1. `docs/PRODUCTION-READINESS-GATE.md` — Gates A–I and the declaration rule.
   Your manifest maps every item to the gate(s) it evidences.
2. `docs/productization-roadmap.md` § "Definition of done" — THE 25-ITEM
   LIST (reproduced in §3 below; the roadmap is the authority if they ever
   disagree — report the disagreement in your notes, do not silently pick).
3. `docs/productization-state.json` — the full finalized lineage (every
   PROD item's merged SHA; your citations reference these).
4. `docs/EVALUATOR-GUIDE.md` + `docs/INSTALL.md` + `tools/bootstrap.ts` —
   PROD-014's deliverables (the fresh-checkout transcript, the one-command
   demo path) — items 1–2 cite these and PROD-014's evidence.
5. `docs/DEPLOYMENT.md` + `docs/free-tier-deployment.md` + `docs/COST-GUARDS.md`
   — the deployment/provider/cost evidence base (items 3–10).
6. `docs/productization-evidence/**` — EVERY subdirectory (the merged waves'
   evidence: PROD-011b/012/012-R/016–029, HFX-000/201). Items 9–21 cite
   these. Read every README in that tree before citing anything.
7. `docs/productization-evidence/PROD-015/gate-f-browser-proof.md` +
   `deployed-check-final.md` — the Tech Lead's own Gate F browser
   recordings and the final deployed-check re-verification (items 11, 18,
   19 cite these; they are Lead-authored and immutable to you).
8. `tools/deployed/README.md` (if present) or `tools/deployed-check.ts`
   header + `tools/deployed/config.ts` — how the 7-check deployed
   verification runs and what `AISE_DEPLOYED_URL` does.

## 3. The 25-item manifest (cite-or-generate, item by item)

For EACH item below your manifest row states: status CITED / GENERATED /
GAP; the artifact (path + introducing commit SHA); one-line content summary;
and the gate(s) it evidences (A–I). Reproduce this list as the manifest
table's left column, in order, using the roadmap's exact wording.

1. fresh-machine install transcript
2. local production-like start transcript
3. public HTTPS URL
4. Vercel deployment identifier
5. configured provider list and plan/tier evidence
6. database migration/bootstrap evidence
7. object upload/download evidence
8. Redis queue/cache/session evidence
9. optional Apify connector evidence or explicit disabled-state evidence
10. browser/mobile/desktop adapter conformance evidence
11. full golden user-journey browser recording
12. representative Android/mobile capture journey evidence
13. desktop adapter build and smoke evidence
14. interactive solution building journey recording
15. deterministic solution replay and validation evidence
16. generated solution BOQ with bidirectional step/line trace evidence
17. representative physical/building benchmark evidence
18. responsive/accessibility evidence
19. next-best-action/task-first UX evidence
20. competitive benchmark evidence
21. free-tier quota/cost guard evidence
22. security/tenant-isolation evidence
23. `bun run verify` result at the final merged SHA
24. exact commit SHA and environment/configuration fingerprint

(If the roadmap lists a 25th item at your base, include it; count and
numbering follow the roadmap verbatim.)

Cite-first: most items already have merged evidence — find it with
`grep -rn` over `docs/productization-evidence/**` + `docs/*.md` + the state
file's SHAs, and cite the ORIGINAL artifact (not a later mention of it).
Generate only what no artifact covers. Expected generated captures (verbatim,
command + full output):

- Item 23: `bun run verify` at your base — capture the final summary lines.
- Item 24: `git rev-parse HEAD`, `git log -1 --format='%H %s'`, the
  `bun.lock` digest (`sha256sum bun.lock`), `node --version`, `bun --version`,
  and the `.env.example` file list (names only, NEVER secret values).
- Deployed re-verification (supports items 3, 18, 22):
  `AISE_DEPLOYED_URL=__DEPLOYED_URL__ bun tools/deployed-check.ts` —
  capture the full 7-check verdict verbatim as
  `docs/productization-evidence/PROD-015/captures/deployed-check-run.md`.

## 4. The package — `docs/productization-evidence/PROD-015/**`

- `README.md` — the package index: what this is, the final SHA, the
  deployed URL, the Lead-authored files, and how to audit the manifest.
- `manifest.md` — THE 25-ROW TABLE (§3) + a coverage summary (cited /
  generated / gap counts) + the explicit statement that gap rows are
  declared honestly per the gate's "no worker narrative alone" rule.
- `captures/**` — your verbatim generated captures (§3), each with the
  exact command line, working-tree SHA, and full output.
- Do NOT duplicate evidence that exists elsewhere — cite it.

## 5. Gates (all must pass before delivery)

```bash
bun run verify        # __BASELINE__ pass / 0 fail (you add NO tests; VERIFY: PASS)
bun run typecheck     # PASS
bun run lint          # PASS
```

Your delivery adds documentation only — the verify count MUST be unchanged
from the baseline. If any verify/typecheck/lint gate is red for reasons
outside your surface, STOP and report.

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
PROD-015 EVIDENCE REPORT

BASE_SHA: <40-hex>            # must equal §1
WORKER_COMMIT: <40-hex>
FILES: <count>                # delivery file count (excluding DELIVERY.txt)
INSERTIONS: <count>

## Manifest coverage (the 25-item Definition-of-Done list)
- CITED: <count> — one line naming the strongest three citations
- GENERATED: <count> — one line each: what was captured and why no artifact covered it
- GAP: <count> — one line each: the item, what is absent, where the Lead should look
- deployed-check re-run: <the 7-check verdict line>
- bun run verify at base: <the final summary line>

verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any disagreement between this packet's list and the roadmap, or "none">
```

Do not paste evidence contents in the report — statuses, counts, paths and
the verify output only.
