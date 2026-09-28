# R35b — the 32-spec journey re-encode: the J01–J39 stale-grammar specs brought to the current product grammar (each spec keeps its fails-on-regression honesty)

You are a senior TypeScript engineer executing ONE well-specified work item in the
WebFlix repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: R35b — re-encode the 32 STALE-GRAMMAR journey specs recorded by
  the R34-C production regression sweep so they assert the CURRENT product
  grammar (the R24→R30 operator-directed evolution), without weakening a single
  journey's check strength. Do not start any other item.
- Owned surface (the ONLY files you may create/modify):
  - `journeys/web/j*.ts` — ONLY the 32 specs listed in §3 (the green set
    J03/J13/J18/J19 and J40/J41/J43 are NOT yours; never touch them)
  - `journeys/web/index.ts` — ONLY if a re-encode changes a journey's honest
    reach or limitation note (narrate every such edit in the report)
  - `docs/validation/webflix-golden-journeys.md` — ONE dated additive section
    recording the re-encode (never reword existing content)
  - `evidence/r35b/**` — your lane evidence (new directory, yours entirely)
  - Explicitly NOT yours: `apps/**`, `packages/**`, `scripts/**`,
    `journeys/desktop/**`, `journeys/lib/**`, `journeys/runner.ts`, every other
    path. If you believe a product bug is the real cause of a spec failure,
    STOP that spec's re-encode, record it in the report as a named
    defect-candidate (file + line + the observed vs expected), and continue
    with the rest — never fix product code on this lane.
- THE RE-ENCODE LAW (this lane's whole point): a re-encoded spec must (a) still
  assert the SAME user-visible intent the original spec tracked, (b) bind to the
  CURRENT grammar element (cite the element in a one-line spec comment at each
  changed assertion), and (c) still FAIL if that contract regresses. Relaxing an
  assertion merely to make it pass, deleting assertions, or wrapping failures in
  try/catch are all fabrication — forbidden. Where the honest reach of a journey
  genuinely changed (a surface the grammar no longer exposes), encode the
  honest typed state and record it in the limitation note — never a fake pass.
- The six production-only bindings (J04, J14, J15, J16, J33, J38): their local
  fixtures-boot passes are NOT to be broken — the re-encode makes their
  catalog/config bindings NEUTRAL (assert the DOM grammar and structural
  truths, not fixture counts like "1 / 3" or dev-route presences) so the spec
  holds on both the fixtures boot and the service-mode production surface. The
  R23 production sweep (evidence/r23/production-sweep.md) is the production
  truth of record for these six.
- No new RUNTIME dependencies; no changes to any product code; never weaken,
  skip or delete an existing test outside your owned surface.
- Your base is FIXED at the commit in §1. Do NOT `git pull`, `git merge` or
  otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/WebFlix.git
cd WebFlix
git checkout acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419   # main (R35-A)
git rev-parse HEAD          # must print acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419
bun install
git checkout -b wfx/r35b/journeys
bun run ci
```

Baseline expectation (the battery of record at main): **5265 pass / 1 fail / 0
skip** — the 1 fail is the pre-existing platform failure of record; your
regression floor is "no NEW failures and pass count ≥ 5265". Record the exact
totals from your own baseline run in `evidence/r35b/guards.md`. If the baseline
is red beyond the 1 pre-existing fail, STOP and report.

## 2. Mandatory reading (in-repo, in this order)

1. `evidence/r34c/README.md` — the sweep of record; the 4 PASS / 34 FAIL
   decomposition (32 STALE-GRAMMAR + 2 ENVIRONMENTAL) and the deliverable map.
2. `evidence/r34c/adjudication-table.md` — EVERY journey's first-failing
   assertion + classification. This is your work list: the 32 STALE-GRAMMAR
   rows (J01 J02 J04 J05 J06 J07 J08 J09 J10 J12 J14 J15 J16 J17 J20 J21 J22
   J23 J24 J25 J26 J27 J28 J29 J30 J31 J32 J33 J34 J36 J37 J38).
3. `evidence/r34c/acceptance-summary.md` — what each finding needs.
4. `journeys/README.md` — the harness laws: journeys are checks not theater;
   the layering law (journeys import nothing from @wfx packages); the
   browser-validation protocol (open → networkidle → snapshot -i, fresh
   snapshot after every DOM-changing interaction); determinism; honest
   listing; evidence committed.
5. `docs/plans/2026-09-28-youtube-parity-survey.md` §1 — the current product
   surface (the grammar's source of truth post-R35).
6. `git log --oneline -40` + `docs/work-items/` — the R24→R35 wave history
   (predominantly R28-B's home/item/player restructure and R29-B's
   shell/masthead rail grammar) — the grammar deltas your re-encodes track.

## 3. The work — five milestones

### M1 — The grammar survey (before any edit)

For each of the 32 specs: run it alone on the fixtures boot
(`bun journeys/runner.ts --only <Jid>` or the harness's equivalent), capture
the first-failing assertion, and map it to the grammar change that made it
stale (R28-B restructure / R29-B shell rail / fixtures-catalog binding /
config binding). Write the survey table to `evidence/r35b/plan.md`:
`| Jid | first-failing assertion | grammar delta | re-encode approach |`.

### M2 — The 26 grammar-drift re-encodes

Update each grammar-drift spec to the current grammar. Every changed assertion
carries a one-line comment citing the grammar element it now binds (e.g.
`// binds R29-B masthead rail: [data-testid="masthead-rail"]`). The journey's
user-visible intent is preserved assertion-for-assertion where the surface
still exists.

### M3 — The 6 production-only neutral re-encodes

J04 (page-size), J14 (source-card), J15/J16 (note wording), J33 (dev-route),
J38 (torrent-catalog): make the bindings catalog/config-neutral — assert the
DOM grammar and structural truths (the pill grammar, the grouping law, the
typed-absence states) rather than fixture counts or dev-only routes. Each of
the six cites the R23 production-sweep line that is its production truth.

### M4 — The full-suite green gate

`bun run journeys:web` — every encoded journey green on the fixtures boot (the
re-encoded 32 + the untouched green set + J40/J41/J43). `bun run ci` at or
above the floor (no new failures; typecheck, contract-check, lane-check all
green). Capture the full run manifests + battery output under
`evidence/r35b/run/` and `evidence/r35b/battery-test-summary.txt`.

### M5 — The regression proof + relay

Re-verify honesty: for 3 representative re-encoded specs (one R28-B class, one
R29-B class, one production-only class), temporarily revert ONLY your spec
change on a scratch checkout and show the pre-existing spec now passes while
your re-encoded spec would fail on a simulated regression — i.e. document (in
`evidence/r35b/honesty-proof.md`) that each re-encoded spec still has teeth
(the exact mutation you applied and the failing assertion it produced). Then
restore your lane and build the relay delivery (§5).

## 4. Verification — the honest gate

- `bun run ci` green at or above the recorded floor (5265 / 1 pre-existing /
  0; exact totals recorded).
- `bun run journeys:web` full pass on the fixtures boot; manifests committed
  under `evidence/r35b/run/`.
- No product code touched (`git diff main --stat` = journeys/web/** +
  docs/validation/** + evidence/r35b/** only).
- The honesty proof (M5) present for the 3 representative classes.
- `git status` clean; everything committed on `wfx/r35b/journeys`.

## 5. Commit and relay the delivery

```bash
git add -A
git commit -m "test(journeys): the R35b 32-spec re-encode — the stale-grammar J01-J38 specs brought to the R24-R35 product grammar, honesty-preserving (R35b)"
git bundle create webflix-r35b-journeys.bundle main..wfx/r35b/journeys
sha256sum webflix-r35b-journeys.bundle evidence/r35b/* 2>/dev/null | sort -k2 > RELAY-MANIFEST.txt
```

Then WRITE the relay files into your workspace storage root with your
file-tools (the exact three artifacts, at the storage root unless noted):

1. `RELAY-MANIFEST.txt` (the sha256 list; the final line must be
   `R35B lane head <your full commit sha>`)
2. `webflix-r35b-journeys.bundle` (the git bundle of main..wfx/r35b/journeys)
3. `evidence/r35b/**` (the full evidence tree — plan, run manifests, battery
   summary, honesty proof, guards)

Then report in the chat (no source code, no tokens, exact shape):

```
=== R35B COMPLETION REPORT ===
branch: wfx/r35b/journeys
base: acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419
specs re-encoded: <count grammar-drift> grammar-drift + <count production-only> production-neutral (of the 32)
green set preserved: J03 J13 J18 J19 J40 J41 J43 untouched and green
journeys:web: <exact pass/fail/skip totals on the fixtures boot>
battery: <exact totals vs the 5265/1/0 floor>
honesty proof: <the 3 representative classes + their failing-assertion evidence>
defect-candidates: <any named product defects found, or "none">
relay: RELAY-MANIFEST.txt + webflix-r35b-journeys.bundle + evidence/r35b/** written via file-tools
lane head: <full commit sha>
=== R35B COMPLETION REPORT @ <the full commit sha> END ===
```

The LAST line above (with the literal full commit sha) is the completion
marker — the Tech Lead gates on it. Do not paste source code, tokens or any
credential material in the report — paths, counts and outcomes only.

CRITICAL ANTI-FABRICATION RULE: if at any point you cannot execute a step
(no working terminal, no file-tools, no network), say so EXACTLY and stop —
report `Status: BLOCKED` with the specific blocker. NEVER invent test counts,
commit SHAs, file paths or outcomes. A fabricated report is worse than a
blocked one.
