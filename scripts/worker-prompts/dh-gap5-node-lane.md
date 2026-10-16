# WORK ORDER — DH-GAP-5: the workbench node-lane runtime binding (gap-ledger row 5)

You are a worker on the Flauz program (TL-B lane). Repo: **payswapdotorg/flauz**.
Clone it, checkout **main**, and verify your base commit is EXACTLY:

    BASE = 7478237a0e46b14fa8118343e54868edba3c6447

Work on ONE branch cut from that base: **`flauz-tlb/dh-gap5-node-lane`** (create it before any edit).

## Context (read these first, in order)

1. `docs/FLAUZ-PROGRAM/SOURCE-OF-TRUTH.md` + `ARCHITECTURE-LOCK.md` (§12.5 the domain-harness law, §12.6 the no-new-authority law)
2. `extensions/flauz-harness/src/flauzHarnessPort.ts` — THE TARGET. Read its header in full.
3. `extensions/flauz-harness/src/harnessPort.ts` (the port contract the tests cover today), `harnessState.ts`, `harnessView.ts`, `extension.ts`
4. `build/flauz/harness/acceptance/common/acceptanceContract.ts` — the frozen `HARNESS_ACCEPTANCE_GAP_LEDGER` and the CLOSED-ROW LAW (`ACCEPTANCE_CLOSED_GAP_KEYS`, currently rows 1-2 closed by PRs #205/#206)
5. `build/flauz/harness/acceptance/README.md` — the GAP-2 wave record (your closure pattern precedent)
6. The DH-010 landing record in `docs/FLAUZ-PROGRAM/WORK-REGISTRY.md` (the workbench surface family history)

## The problem (row 5 of the honest gap ledger, verbatim)

> `workbench-surface-runtime-binding` — "the flauz-harness extension's runtime binding is covered by the bundle+activation gates (the flauz-lab law), not the node lane; the UI behavior is verified here at the projection-derivation level + the extension's own node suites"

`flauzHarnessPort.ts` is the ONLY cross-lane runtime edge. Its header says **"NO TEST EVER IMPORTS THIS FILE: Node type stripping cannot resolve those .js specifiers"** — so today the binding is exercised only by the bundle + activation gates. The residue: no node-lane drill proves the REAL binding drives the REAL kits.

## Deliverable 1 — THE NODE-LANE BINDING DRILL

Author a drill that **imports the REAL `flauzHarnessPort.ts` and exercises it against the REAL Domain Harness OS kits in the node lane**:

- The drill lives in the extension's test lane (e.g. `extensions/flauz-harness/test/flauzHarnessPort.drill.ts`), runs under the repo's own TS execution lane (`NODE_OPTIONS="--import tsx" mocha --ui tdd`, the family-battery convention) — **the .js-specifier resolution solved LAWFULLY by the lane, never by editing the real kits' import specifiers and never by re-implementing the port**.
- Exercise the REAL composition route end-to-end against a temp workspace root: begin/reopen the DH-02 onboarding session (real ledger on disk), selectIndustry/composeCompany/selectWorkTypes, the draft composition through the REAL DH-03 emit, the harness + family record loads through the REAL per-family loaders, and the navigation model through the REAL DH-10 projections.
- Assert the REAL observable laws: the records/ledgers materialize on disk in the real shapes (PIN-2 mirrors; torn-ledger/envelope-mismatch refusals are typed), the honest refusals carry the underlying kit's refusal verbatim, restart-determinism (reopening the same root yields the same state), the closed-door law (the surface NEVER executes/activates — activation stays routed through the DH-01 authority).
- THE IMPORT LAW (the row's core): every symbol the drill touches comes from the REAL modules — imported, never re-implemented, never mocked. The drill may construct ONLY the injected seams the port's own constructor accepts (root dir, clock) — the same injection surface `extension.ts` uses.
- Determinism: no Math.random/Date.now in the drill's assertions path beyond the injected clock; law-comment convention for any grep hit.

## Deliverable 2 — THE ROW-5 CLOSURE (the closed-row pattern, GAP-2 precedent)

- Add `'workbench-surface-runtime-binding'` to the frozen `ACCEPTANCE_CLOSED_GAP_KEYS` list.
- Re-word the ledger row's description to its CLOSED successor state recording the truth: the node-lane drill landed (this PR), the binding now exercised in BOTH lanes (bundle+activation gates AND the node-lane drill), closed 2026-10-16.
- Propagate through the validator's coherence laws exactly as GAP-2 did: no fixture registers the closed row (fixtures' `expectedGaps` updated), the closed row rides the report VERBATIM with its closure recorded IN the row, refused as a fixture registration at the contract walk/row walk/runner's gap registration/ledger replay.
- Re-pin the affected acceptance battery assertions (disclose every re-pin in your D-register).
- Add the control-plane addenda (the same four docs GAP-1/GAP-2 updated): the WORK-REGISTRY wave record, MASTER-ROADMAP/CURRENT-STATE, FRESH-CHAT-TL-B-HANDOFF.

## Gates (run them ALL yourself; the station re-runs everything — never trust your own reported numbers alone)

1. `node_modules/.bin/tsc -p extensions/flauz-harness/tsconfig.json` → EXIT 0
2. The drill + the existing workbench-surface suite (`extensions/flauz-harness/test/*.test.ts`) → ALL PASSING under `NODE_OPTIONS="--import tsx" mocha --ui tdd`
3. The acceptance family: tsc EXIT 0 + battery (currently 161) green with the closed-row propagation
4. Sibling spot-checks: the lab battery (331) + two other families green (unchanged)
5. Determinism greps over every file you touched: law-comment-only
6. `git diff --name-only BASE..HEAD` = exactly your owned paths (the extension test lane + the acceptance family files + the four control-plane docs + READMEs). Zero deletions of landed content outside the disclosed re-pins.

## D-register

Keep a decision register: every design decision, every deviation, every re-pinned assertion, with reasons.

## Completion

Push the branch (`flauz-tlb/dh-gap5-node-lane`, single or few clean commits on the pinned base) with the provided token. The station harvests, re-runs every gate, opens the PR and merges — do NOT open a PR yourself.

End your final report with EXACTLY this marker line:

    === GAP-5 COMPLETION REPORT ===

followed by: branch name, HEAD sha, the changed-file list, your gate results, the D-register, and the honest limitations.
