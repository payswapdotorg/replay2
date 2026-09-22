# PROD-012 — Deployed-browser verification, accessibility, responsive behavior and smoke tests

You are a senior QA/tooling engineer executing ONE well-specified work item in the
AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-012 (deployed-browser verification). Do not start
  PROD-014/015/018 or any other item. Do not "fix" product code you find
  deployed-side problems with — you build the VERIFICATION SUITE and REPORT
  findings; remediation is a separate governed item.
- The deployed production service is a verification TARGET, read-mostly:
  - You MAY exercise the documented demo-session lifecycle (mint → whoami →
    logout) — that is the point of this item.
  - You may NOT load-test, fuzz, brute-force, spam, or hammer it. Single
    browser context, sequential checks, human-scale pacing. This is a
    free-tier deployment shared by the whole campaign.
- Owned surface (the ONLY files you may create/modify):
  - `tools/deployed-check.ts` (NEW root runner — mirrors the tools/smoke.ts doctrine)
  - `tools/deployed/**` (NEW supporting modules)
  - `docs/productization-evidence/PROD-012/**` (evidence documents)
  - `package.json` + `bun.lock` — ONLY to add pinned entries to
    `devDependencies` (see §4). Nothing in `dependencies`. No other edits.
- Explicitly NOT yours: `docs/productization-state.json` (Tech-Lead-owned
  finalize), `apps/**`, `backend/**`, `api/**`, `packages/**`, `spec/**`
  (read them all you want; modify none).
- If a mandated reading contradicts this packet, STOP and report the conflict.
- Never weaken, skip or delete an existing test.

## 0a. Operational notes (environment reality, battle-tested)

- The worker sandbox downloads from public CDNs (Adoptium, npm) but transient
  502s happen: retry any download a few times with backoff before concluding
  the host is down.
- Playwright's browser download (`bunx playwright install chromium`, after
  `bun install`) pulls from the Playwright CDN. If it fails, retry; if it
  keeps failing, the runner must FAIL EXPLICITLY with the exact error —
  never silently skip browser checks.
- Launch Chromium with `--no-sandbox` (worker sandboxes run without the
  namespace privileges the sandboxed renderer needs).
- Known baseline quirk: the full `bun run verify` suite has, on some
  machines, up to two tests that fail in the full run but pass in isolation
  (sandbox scheduling, not code). Protocol if you see failures: re-run each
  failing file alone (`bun test <file>`). If it passes isolated, note it in
  your report (file + test name) and continue ONLY if everything else is
  green. Any other failure = STOP and report.

## 1. Setup — public GitHub main, no overlay

This item does NOT need the Lead overlay (it touches no adapter/contract
code). Base is plain public main:

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 2aabd1b3113b93bd253412077e95062ea28330ea   # public GitHub main
git rev-parse HEAD   # must print 2aabd1b3113b93bd253412077e95062ea28330ea
bun install
git checkout -b prod-012/deployed-verification
bun run verify
```

Baseline expectation: **VERIFY: PASS** (see §0a for the isolation-flake
protocol). If the baseline is otherwise red, STOP and report.

`BASE=2aabd1b3113b93bd253412077e95062ea28330ea` — your delivery diff base.

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` — what the product shell is
2. `AGENTS.md` — operating contract, authority hierarchy
3. `spec/architecture-lock.md` — immutable invariants (your suite must assert
   deployed behavior, never assume around them)
4. `spec/assurance.md` — the repo's assurance doctrine your suite extends
5. `tools/smoke.ts` — THE pattern to mirror: deterministic, real-process,
   bounded waits, causality proofs, always-cleanup, machine-readable verdict
6. `docs/productization-roadmap.md` — the PROD-012 row (verbatim in §3)
7. `docs/DEPLOYMENT.md` + `docs/free-tier-deployment.md` — what is deployed
   and the free-tier constraints your pacing must respect
8. `evidence/PROD-011B/deployed-session-walk.txt` — the deployed session
   semantics you will re-verify through a real browser (mint → whoami×N →
   logout → fail-closed 401)
9. `docs/PRODUCTION-READINESS-GATE.md` — the gate this item feeds

## 3. The work order (verbatim from docs/productization-roadmap.md)

| ID | Depends on | Scope | Acceptance |
|---|---|---|---|
| PROD-012 | PROD-011, PROD-011b | Deployed-browser verification, accessibility, responsive behavior and smoke tests | Automated browser checks pass on desktop/mobile breakpoints; no blocking console/runtime errors |

Dependencies are finalized (PROD-011, PROD-011b both merged). Production is
live at the default target URL (§4).

## 4. Implementation shape (follow the repo's own conventions)

Build ONE runner: `tools/deployed-check.ts`, executable as
`bun tools/deployed-check.ts` (do NOT modify package.json scripts — the
runner is invoked directly; only devDependencies may change, §0). Supporting
modules live under `tools/deployed/`. TypeScript throughout, the repo's
existing style (no default exports if the repo forbids them — check).

### 4.1 Doctrine (from tools/smoke.ts, non-negotiable)

- Deterministic verdict: print `DEPLOYED: PASS` or `DEPLOYED: FAIL` and exit
  0/1 accordingly. Every check prints a one-line result with proof excerpts.
- Bounded waits everywhere (explicit ms budgets, never unbounded sleeps).
- Causality proof: prove you measured THE target (assert the response
  `<title>`/headers identity at start; if a check hits anything else, fail).
- ALWAYS clean up: close the browser, delete nothing server-side beyond your
  own minted demo sessions (logout does this).
- One bounded retry per CHECK (not per assertion) for transient network
  flakes; a check that fails twice fails. Print which checks retried.

### 4.2 Target

- URL from env `AISE_DEPLOYED_URL`, default `https://aise-tan.vercel.app`.
  Print the resolved target at start.

### 4.3 Required checks (each a named, separately-reported step)

1. **availability** — via the browser context's request API:
   `GET /` → 200 + expected `<title>`; `GET /healthz` → 200 `{ok:true,...}`;
   `GET /readyz` → 200 `{ok:true,...}` (capture the `ledger` field — it must
   be `"redis"` when the deployed env carries the Redis pair; if it is not,
   report the value and FAIL — that is a deployed-configuration regression).
2. **shell-renders** — load `/` in a real page: the app root mounts (non-
   trivial DOM under the root element), the document is not blank, primary
   shell text/landmarks present (read README/the shell's own markup; assert
   at least the document title and one product shell landmark).
3. **session-lifecycle** — through the REAL page origin with
   `credentials: "include"` (HttpOnly cookie semantics, mirroring the
   PROD-011B walk):
   - `POST /v1/auth/demo` → 2xx; capture the session cookie evidence
     (response body/session id).
   - `GET /v1/auth/whoami` → 200 authenticated (same browser context).
   - `DELETE /v1/auth/sessions/current` → 2xx.
   - `GET /v1/auth/whoami` → **401** (fail-closed). Assert the status code
     exactly; a 200 here is a critical failure.
4. **responsive-desktop** — viewport 1440×900: no horizontal overflow
   (`document.scrollingElement.scrollWidth <= window.innerWidth + 1`), shell
   landmark visible.
5. **responsive-mobile** — viewport 390×844: same assertions.
6. **accessibility** — axe-core (`@axe-core/playwright`) at BOTH viewports:
   zero `critical` and zero `serious` violations. Report the violation counts
   by impact level (passes with `moderate`/`minor` > 0 are OK — report them,
   do not fail).
7. **console-runtime-errors** — during ALL page interactions above, collect:
   `pageerror` events, `console.error` calls, and failed requests for
   document/script/style/font/xhr/fetch (HTTP status ≥ 400 or network error).
   Blocking = any pageerror, any console.error, any failed
   document/script/style load. XHR/fetch 4xx that the app HANDLES (e.g. the
   intentional 401 in check 3) are not blocking — the suite must exclude
   expected-by-design responses. Fail with excerpts (first 3 of each class).

### 4.4 Authorized devDependencies (pinned exact, dev-only)

- `playwright` (pin the exact version you tested)
- `@axe-core/playwright` (pin)

`bun add -d --exact playwright@<ver> @axe-core/playwright@<ver>`, then
`bunx playwright install chromium` (setup step; the runner's preflight
prints an actionable error if the browser is missing).

### 4.5 Evidence

Write `docs/productization-evidence/PROD-012/run-<UTC-date>.txt`: the full
runner output of a passing run (the report's §7 references it).

## 5. Gate (must pass before reporting)

```bash
bun run verify                                   # full battery, VERIFY: PASS
bun tools/deployed-check.ts                      # DEPLOYED: PASS against production
```

Both must pass in the same working tree. Do NOT change anything after the
gate run.

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's
harvest API cannot see. After committing, copy EVERY new/changed file (the
complete diff vs base `2aabd1b3113b93bd253412077e95062ea28330ea`) into the
PROJECT directory (the one containing package.json / src/ — the workspace
root), preserving repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only 2aabd1b3113b93bd253412077e95062ea28330ea..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo; git diff 2aabd1b3113b93bd253412077e95062ea28330ea..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-012 COMPLETION REPORT
base: 2aabd1b3113b93bd253412077e95062ea28330ea
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
target: <the deployed URL the suite verified>
checks implemented: <named list from §4.3>
results:
- availability: <PASS/FAIL + healthz/readyz ledger value>
- shell-renders: <PASS/FAIL + landmark asserted>
- session-lifecycle: <PASS/FAIL + whoami-after-logout status code>
- responsive-desktop: <PASS/FAIL + overflow measurement>
- responsive-mobile: <PASS/FAIL + overflow measurement>
- accessibility: <PASS/FAIL + violations by impact at each viewport>
- console-runtime-errors: <PASS/FAIL + counts by class>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
deployed: <paste the DEPLOYED: verdict line>
evidence: docs/productization-evidence/PROD-012/run-<date>.txt
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt)
notes: <any deviation from this packet, findings worth a follow-up item, or "none">
```

Do not paste source code in the report — paths, counts and the verdict lines
only.
