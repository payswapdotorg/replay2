# FLAUZ WORKER ORDER — A-PROD-006-W8 (sustained-production-cycle-5 / production-real revolution 2: the flauz-harness production-integration incident + the v0.2.1 release cycle)

> Issued by the TL-A station (Flauz A-PROD). Repo of record: github.com/payswapdotorg/Flauz (PUBLIC — clone it PAT-less: `git clone https://github.com/payswapdotorg/Flauz.git`). The repo is the ONLY source of truth. Read `docs/FLAUZ-PROGRAM/FLAUZ-START-HERE.md` first, then this order.

## §0 Stop clauses (read first)

- If any instruction here conflicts with `docs/FLAUZ-PROGRAM/` governance (ARCHITECTURE-LOCK, MASTER-ROADMAP, WORK-REGISTRY), STOP and report the conflict — do not improvise.
- **Boundary loss-stop:** you own the PRODUCTION-INTEGRATION RESIDUE partition only: `build/flauz/packaging-parity.json`, `build/flauz/security/flauz-sbom.json`, `build/flauz/security/bundle-manifest.json`, `product.flauz.json` (version field only), `docs/FLAUZ-PROGRAM/WORK-REGISTRY.md` (your landing-record section only), plus additive test/ledger rows under `build/flauz/production/` if your regression pin needs them. The DH implementation families (`build/flauz/harness/**`, `extensions/flauz-harness/**`) are TL-B-owned and READ-ONLY: if a complete fix would require editing them, implement your half and report the residue.
- Credential-free delivery: no secrets, no tokens, no network credentials in any artifact. You deliver through the chat workspace files only (§5).
- If you cannot reproduce the finding at the pinned base, STOP and report.
- Determinism law (production/ops family): no clock, no random, no env in shipped code under `build/flauz/production/`.

## §1 The finding (verbatim, machine-detected by the TL-A station at main `7478237a0e46b14fa8118343e54868edba3c6447` — 2026-10-16; first detected 2026-10-15 at `c56460755b59e425a23992039c818cd60ac070a7`, re-verified byte-identical at the post-GAP-wave frontier)

The DH wave 9 landing (DH-010, PR #201 `032e7b0369`, merged 2026-10-15) introduced `extensions/flauz-harness` (the flauz-harness workbench surface, 19 files, vscode-dts, `main: ./dist/extension.js`, no browser entry, engines vscode ^1.140.0, 7 contributed commands, activation onView:onCommand:flauz.harness.*) WITHOUT updating the three production-integration surfaces that every new extension must regenerate:

```text
$ node build/flauz/scripts/packaging-parity.mjs --root . --registry build/flauz/packaging-parity.json
FAIL  PP2 coverage: extension flauz-harness (extensions/flauz-harness/package.json) has no parity rows - an unclassified surface is a violation
packaging-parity: drift/violations found  (verdict: DRIFT, manifests: 22, rows: 71, fail: 1)
```

- `build/flauz/packaging-parity.json`: 22 extension manifests live, 21 extension surfaces registered — flauz-harness has NO parity row (PP2 FAIL, machine-detected).
- `build/flauz/security/flauz-sbom.json`: `grep -c flauz-harness` = 0 (flauz-lab IS present at `pkg:generic/flauz/flauz-lab@0.1.0`) — the SBOM component set is stale at v0.2.0.
- `build/flauz/security/bundle-manifest.json`: `grep -c flauz-harness` = 0 — the bundle manifest does not enumerate the new extension's files.

This is a REAL production-integration incident of exactly the class the A-PROD-006 reliability loop exists to catch (usage → evidence → incident → fix → regression → release → post-release verify): a sibling-lane landing (TL-B's DH wave) advanced main without the TL-A-owned packaging/security surface regeneration, and the LIVE production identity (v0.2.0 at https://flauz-web.vercel.app) does not carry the harness surface at all.

## §2 Fixed facts

- **Pinned base:** `7478237a0e46b14fa8118343e54868edba3c6447` (flauz main at claim time — verify with `git rev-parse HEAD` after clone; if remote main has moved, STILL cut your branch from THIS SHA). Branch: `flauz-aprod/aprod-006-w8`, cut FROM THIS SHA ONLY; rebase is forbidden.
- **Work-order id:** A-PROD-006-W8 — every artifact, branch, marker and report line carries it.
- **minimal-diff law:** the smallest diff that satisfies §3. Drive-by refactors, formatting sweeps and unrelated fixes are defects.
- **GATE-FROZEN law:** `build/flauz/scripts/packaging-parity.mjs`, `compat-battery.mjs`, `agentos-battery.mjs`, the doctored controls and the verifiers stay BYTE-IDENTICAL to the pinned base (sha256 of each in your report). The instruments are frozen — the fix must pass them, never edit them.
- **Hygiene:** additive-only inside your partition; no schema primitive lists; imports respect extension boundaries; match each edited file's existing indentation style exactly; regenerate — never hand-fabricate — machine-generated artifacts (SBOM, bundle manifest) using the repo's own generators if they exist (search `build/flauz/scripts/` and the security-gate tooling for the generator that produced them; if only a manual schema exists, follow it exactly and disclose).
- **Known non-goals (do NOT touch):** the compat-battery `FLAUZ_BUILTIN_EXTENSIONS` six-extension list is a documented pre-existing TL3-005 merge gap — out of scope. DH-012/DH-013 are TL-B's. The INF-009 live-provider canary stays env-gated SKIP.

## §3 The work (the sustained-operation cycle, in order)

1. **Incident record.** Add the incident row through the frozen incident lifecycle vocabulary (the A-PROD-006-W1 incident/problem registry family — find the registry surface under `build/flauz/` or `extensions/flauz-incidents/` and follow its exact record shape; if the registry is a docs-side ledger, add the row there following the established format): id `INC-W8-PARITY-GAP` (or the next sequential id if the registry numbers them), class production-integration, finding = §1 verbatim, surfaces = the three stale files, owning lane TL-A, status open→fixed within this order.
2. **Parity row.** Add the `extensions/flauz-harness` row(s) to `build/flauz/packaging-parity.json` with the HONEST class (expected `web-blocked` — node main, no browser entry, vscode-dts; verify by reading the extension's manifest + imports and mirror the evidence-shape of the flauz-lab row: manifest-key citations, node: import citations where true, recoveryPath). The gate must read: `packaging-parity: CLEAN` with rows 71→72+ and ZERO FAIL/DRIFT lines.
3. **SBOM regen.** Regenerate `build/flauz/security/flauz-sbom.json` to include the `flauz-harness` component (`pkg:generic/flauz/flauz-harness@<its package.json version>`) following the existing component shape exactly (the flauz-lab row is the template). Byte-deterministic: same generator inputs → same output. The security-runtime-gate's SBOM check must stay green at the new version (§3.5).
4. **Bundle manifest regen.** Regenerate `build/flauz/security/bundle-manifest.json` to enumerate the extension's committed files (follow the existing per-file row shape; the flauz-lab rows are the template). If the manifest is produced by a script (search for it), run it; disclose which path you took.
5. **Release identity.** Advance `product.flauz.json` `version` `0.2.0` → `0.2.1`. This is the cycle's release identity. Regenerate any version-pinned artifacts that cite the version (SBOM metadata, the deploy healthz/status expectations under `build/flauz/production/deploy/` IF they pin the version literally — check and update faithfully).
6. **Regression pin.** Add ONE targeted regression test (or extend the existing parity/registry battery where the PP2 law is already tested — follow the established test file shape) that fails on the pinned base (the unclassified-surface violation present) and passes on your fix (flauz-harness classified + counted). Name it with the work-order id.
7. **The release battery at your branch head.** Run and receipt EXACTLY this set (report actual numbers, never copy old ones): `verify-fixtures` (AS EXPECTED, 0 deviations) · security-gate GREEN · security-runtime-gate GREEN (SBOM byte-exact at 0.2.1) · premium-ux CLEAN · compat-battery (report count; expect the historical green set) · packaging-parity CLEAN (the repaired count) · fork-critical guard EMPTY vs origin/upstream/main · activation lint GREEN · the production/ops battery 137/137 · scoped `tsc --noEmit` EXIT 0 for the production families you touched (the scoped tsconfig pattern under `build/flauz/production/`). If a gate is ENV-GATED SKIP in this repo (e.g. live-provider canary), report it as SKIP with the env var name — never fake it.
8. **The sustained-cycle ledger.** Append the W8 cycle row to the production ops ledger (the W7 sustained-operation ledger surface under `build/flauz/production/` — find the established ledger file from the W7 record and follow its row shape): cycle 5, revolution production-real #2 (station-side), the incident id from §3.1, the release identity 0.2.1, the battery verdict set from §3.7.
9. **Registry record.** Append your `#### TL-A worker delivery record — A-PROD-006-W8` section to `docs/FLAUZ-PROGRAM/WORK-REGISTRY.md` (the established worker-record shape: what was delivered, the receipts, the honest disclosures — including anything you could NOT verify in-sandbox). The station will re-verify every receipt and write the final landing record around yours.

## §4 Evidence levels (never promote)

```text
fixture < battery < runtime < live-provider < production-real
```

- Your in-sandbox gate/battery runs are LOCAL-REAL at best. Claim exactly what you ran (command + exit code + count). PRODUCTION-REAL is claimed ONLY by the station at the LIVE URL — you never claim it.
- The SBOM/bundle regens are machine artifacts: their evidence is the byte-diff + the generator provenance you disclose.

## §5 Deliverables & staging (credential-free)

1. ONE commit on the branch `flauz-aprod/aprod-006-w8` (single commit, pinned base parent).
2. `git bundle create <scratch>/aprod-006-w8.bundle flauz-aprod/aprod-006-w8` — a bundle whose only ref is your branch (the station fetches + verifies + pushes it).
3. `MANIFEST` file: every changed file path + `sha256` + the tree self-check line (`TREE-SELF-CHECK <sha256 of git write-tree>`), plus the frozen-instrument sha256 table (§2 GATE-FROZEN files).
4. Upload BOTH files (`aprod-006-w8.bundle`, `MANIFEST`) to THIS chat's workspace (the file-upload surface of this conversation) at the path `flauz-delivery/aprod-006-w8-sustained-cycle/`.
5. Completion report in your FINAL chat message, bounded by EXACT markers (see §6). The report carries: the receipts table (§3.7 with commands + exit codes), the incident id, the honest-disclosure list, and the MANIFEST sha256 table inline.

## §6 Completion report format (EXACT markers — the station's parser is regex-based)

Your final message MUST contain, verbatim:

```text
FLAUZ-APROD-006-W8-REPORT BEGIN
WORK-ORDER: A-PROD-006-W8
BRANCH: flauz-aprod/aprod-006-w8
BASE: 7478237a0e46b14fa8118343e54868edba3c6447
HEAD: <your 40-char commit sha>
BUNDLE: flauz-delivery/aprod-006-w8-sustained-cycle/aprod-006-w8.bundle
INCIDENT: <the incident id recorded>
VERSION: 0.2.1
PARITY: CLEAN <N rows>
SBOM: <component count> components, flauz-harness present
FIXTURES: <N>/<N> AS EXPECTED, 0 deviations
SECURITY-GATE: GREEN
SECURITY-RUNTIME-GATE: GREEN (SBOM byte-exact at 0.2.1)
PREMIUM-UX: CLEAN
COMPAT: <N>/<N>
FORK-CRITICAL: EMPTY
ACTIVATION: GREEN
OPS-BATTERY: 137/137
TSC-SCOPED: EXIT 0
REGRESSION: <test name> fails-on-base, passes-on-fix
DISCLOSURES: <list or NONE>
FLAUZ-APROD-006-W8-REPORT END
```

Report truthfully: a SKIP stays SKIP, a red gate stays red with its output tail. The station re-verification is independent and exhaustive — every number you claim will be re-run at your pushed tree, and any mismatch voids the delivery.

## §7 What the station does after your report (context — not your work)

The TL-A station independently re-verifies every receipt at your bundle-reconstructed tree (six gates + scoped tsc + the census), drives the incident to closed in the registry, pushes the branch, lands the PR, redeploys the LIVE production surface (Vercel + Neon, station-held credentials) at 0.2.1, runs the LIVE battery + E2E boot + observability census, and writes the final landing record + the sustained-operation ledger update. Your delivery is the in-sandbox half of the cycle.

— TL-A station, 2026-10-16. The repo is the only source of truth; this order cites it exactly.
