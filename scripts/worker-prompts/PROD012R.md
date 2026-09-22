# PROD-012-R — Deployed-app accessibility and responsive remediation

You are a senior TypeScript engineer executing ONE small, well-specified
remediation work item in the AISE repository. This document is your task
packet — follow it exactly.

## 0. Ground rules

- ONE work item: the PROD-012 deployed-verification remediation (the two
  honest FAILs + one moderate finding from
  `docs/productization-evidence/PROD-012/run-2026-09-20.txt`). Nothing else.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/styles/app.css` (the design-token + layout stylesheet —
    both fixes are expected to be CSS-only; see §4)
  - `apps/web/src/styles/tokens.test.ts` (NEW — the committed WCAG
    token-ratio test from §4)
  - `apps/web/src/app/AppShell.tsx` (ONLY if the header fix genuinely
    requires a markup change that CSS cannot express — justify in the report)
  - `docs/productization-evidence/PROD-012-R/**` (evidence documents)
- Explicitly NOT yours: everything else — `apps/web/src/solution/**`,
  `apps/web/src/parity/**`, `apps/web/src/app/surfaces/**`, the packages,
  backend, tools, spec, the root `bun.lock`. Other workers own those lanes.
- If the current main has already incidentally fixed a defect (PROD-017/018
  rewrote parts of the shell), REPORT that honestly with the reproduction
  numbers — do not fix what does not reproduce.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Do NOT `git pull` or merge
  upstream during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout deb46cb29948f348079c803c1e81cb5831c62c8c   # public GitHub main (adapter wave + 018 + 022 + 023 merged)
git rev-parse HEAD   # must print deb46cb29948f348079c803c1e81cb5831c62c8c
BASE=$(git rev-parse HEAD)
bun install
git checkout -b prod-012r/a11y-responsive
bun run verify
```

Baseline expectation: **4323 pass / 0 fail, VERIFY: PASS**. If the
baseline is red, STOP and report.

## 2. Mandatory reading

1. `docs/productization-evidence/PROD-012/run-2026-09-20.txt` — the
   remediation contract: the three findings, their reproduction details and
   root-cause notes.
2. `apps/web/src/styles/app.css` — the token block (`--ink-faint` at the
   top), `.app-header-inner` (~line 129, the flex row with no wrap), and the
   `.journey-hint` rules (~line 1060).
3. `apps/web/src/app/AppShell.tsx` — the header structure (brand + user
   menu + live-API chip + drawer toggle ≈ 469px at the 390px viewport).
4. `tools/deployed-check.ts` — the seven-check suite whose mobile and
   accessibility checks failed (your local verification mirrors their
   logic).

## 3. The findings to remediate (from run-2026-09-20.txt)

1. **responsive-mobile (FAIL)** — the signed-in shell horizontally overflows
   the 390px viewport (scrollWidth 469 vs innerWidth 390, budget +1). Root
   cause: `.app-header-inner` is a flex row with no wrap; brand + user menu +
   "live API" chip + drawer toggle need ~469px; main content follows the
   wider document width.
2. **accessibility (FAIL, WCAG 1.4.3 AA serious)** — `.journey-hint`
   elements render `#7a8894` (`--ink-faint`) on `#ffffff` (`--surface`) =
   3.64:1 < 4.5:1 (Dashboard journey hints; the token is also used by
   PROD-017/018 surfaces — `task-first.tsx`, `parity/components.tsx`).
3. **accessibility (moderate, non-blocking)** — nested/duplicate main
   landmarks (`index.html`'s `main#app` wraps AppShell's
   `main#main-content`).

## 4. Build specification

- **Reproduce first**: on a locally served production build
  (`bun run build` then serve the output; the repo's established static
  serve), at 390x844 headless: measure `document.scrollWidth` vs
  `window.innerWidth` on the signed-in shell (the demo session per the
  PROD-012 run), and run axe-core (the deployed-check suite's approach)
  on the Dashboard. Record the exact before numbers.
- **Fix 1 (overflow)**: make `.app-header-inner` respect the 390px viewport
  — the house style prefers: `flex-wrap: wrap` on the row, `min-width: 0`
  on the brand block, and/or a media query that condenses the header
  (hide the live-API chip label, tighten gaps) below 480px. `scrollWidth`
  must equal `innerWidth` (+1 budget) at 390x844 AND the desktop layouts
  must be visually unchanged (no regression at 1280px+: assert the header
  still renders brand + menu + chip + toggle in one row).
- **Fix 2 (contrast)**: bring every `--ink-faint` text usage to ≥ 4.5:1 on
  its actual surface (compute, do not eyeball). Prefer darkening the token
  once (e.g. a grey in the `#5f6e7a`-class — verify ≥ 4.5:1 on `--surface`
  AND on any tinted surface it appears on) over per-usage overrides; if a
  usage legitimately renders large text (≥ 24px, or ≥ 18.66px bold) the AA
  large-text 3:1 threshold applies — still prefer uniform ≥ 4.5:1 for
  robustness. State the computed ratios in the evidence doc.
- **Fix 3 (landmarks, moderate)**: if achievable without visual change:
   make the wrapper a `div` (or remove the duplicate `main`) so exactly one
  `main` landmark remains. If it requires touching files outside your
  surface, document it as a recommendation instead and mark it deferred
  with the reason.
- **Verify after**: re-run the same local reproduction harness — scrollWidth
  equality at 390x844, axe-core serious violations = 0 on the shell +
  Dashboard, one `main` landmark (or the deferred note), desktop unregressed.
- **Repo gates**: `bun run verify` (baseline + your assertions — add the
  token-ratio assertions as a small committed test, e.g. a
  `apps/web/src/styles/tokens.test.ts` computing the WCAG ratios of the
  token palette on their surfaces — the repo's established deterministic
  style), `bun run typecheck`, `bun run lint`.

## 5. Quality gates (run all; paste the exact summary lines)

```bash
bun run verify        # EXPECT: (4323 + N) pass / 0 fail
bun run typecheck     # EXPECT: VERIFY: PASS
bun run lint          # EXPECT: VERIFY: PASS
```

## 6. Delivery

Stage your complete delivery under `delivery/` in the workspace (the house
convention — see AGENTS.md):

```text
delivery/DELIVERY.txt          # git diffstat vs BASE + commit sha + file list
delivery/<all changed files>   # full paths preserved
delivery/docs/productization-evidence/PROD-012-R/remediation.md
```

`DELIVERY.txt` header format (exact):

```text
commit: <your 40-hex commit sha>
base: deb46cb29948f348079c803c1e81cb5831c62c8c

 <diffstat>
```

## 7. Completion report (post as your FINAL message)

```text
PROD-012-R COMPLETION REPORT

BASE_SHA: <40-hex>
WORKER_COMMIT: <40-hex>
FILES: <count>
INSERTIONS: <count>

## Reproduction (before)
- overflow @390x844: scrollWidth <n> vs innerWidth 390
- contrast: <token> on <surface> = <ratio>:1 (axe serious: <count> nodes)
- landmarks: <finding>

## Fixes
- overflow: <what changed, one line>
- contrast: <new token value + computed ratios on every surface it appears>
- landmarks: <fixed | deferred + reason>

## Verification (after, local production build)
- overflow @390x844: scrollWidth <n> vs innerWidth 390 — PASS/FAIL
- desktop @1280+: header one-row unregressed — PASS/FAIL
- axe-core serious violations: <count> — PASS/FAIL
- landmarks: <count> main — PASS/DEFERRED

## Gates
verify: <paste the final summary lines>
typecheck: <PASS/FAIL>
lint: <PASS/FAIL>

## Honesty section
- deviations: <none | list>
- deferred: <none | list with reasons>
```

If you cannot complete a section, write `HONEST FAIL: <reason>` — never
fabricate. Note: the DEPLOYED re-verification against
`https://aise-tan.vercel.app` is deliberately NOT yours — the Tech Lead
redeploys and re-runs `tools/deployed-check.ts` after your merge; your
evidence is the local production-build verification.
