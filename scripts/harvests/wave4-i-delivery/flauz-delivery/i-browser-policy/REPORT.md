# Flauz Wave 4 — Lane I delivery report: browser policy engine + partition model + blocked-at-all-layers verification

**Worker:** `flauz-I-w4` · **Branch:** `flauz/wave4/browser-policy` · **Base:** `67b0b081de0a5c786d681a383637390f16c62c6b` (`flauz/main` round 16, depth-1 clone; recorded diff base) · **Delta:** 44 files, 100% additive (`git diff --name-status` = 44 x `A`), FORK-CRITICAL ledger EMPTY (DL-12) · **Transit:** staged at `flauz-delivery/i-browser-policy/` (MANIFEST.txt sha256 per file, all 44 verified `OK`) + git bundle `/home/z/my-project/wave4-i-browser-policy.bundle` (`67b0b08..flauz/wave4/browser-policy`, 3 commits).

**Authoritative inputs honored (read first, not re-derived):** `docs/BROWSER-ARCHITECTURE.md` + `docs/PROTOTYPE-RESULTS.md` (lab branch `wave1/b-browser-ux` — the section 5 layered-gates spec + the B1c finding), `docs/SECURITY-MODEL.md` section 2.2 + section 4 (lab branch `wave2/d-license-security` — layer table L1-L7, F1-F4), `DECISION-LOG.md` DL-6/DL-12/DL-19/DL-21 (lab branch `tl/decision-log-w3`), matrix row C-28 (`wave1/c-capability-matrix`), `PERFORMANCE-PLAN.md` section 5.3 + section 8 (`wave2/e-perf-migration`). Tree citations below are repo-relative against the base sha.

---

## WHAT-BUILT

### 1. `extensions/flauz-browser/` (new extension; 17 files; zero-dep, node >= 20 stdlib only; all-TypeScript)

**`src/policy.ts` (~1090 lines) — the layered policy engine** (BROWSER-ARCHITECTURE section 5, DL-6):

- **Layer model + precedence:** L1 `driver` (the driver-side navigate allowlist, AUTHORITATIVE for agent-initiated navigation — its deny wins over every other layer), L2 `webRequest`, L3 `willNavigate` (user-path only — the B1c firing model), L4 `partition` containment. Combined verdict: **deny-at-any-layer wins**, first denying layer in precedence order `partition > driver > webRequest > willNavigate`. A driver ALLOW never overrides another layer's deny (the B1c insurance precondition, test-pinned).
- **CDP-bypass semantics (the B1c core):** `agent-tool` navigations (CDP `Page.navigate` via the browser tool) consult driver + webRequest — will-navigate never fires for them and is not consulted; `user` navigations consult willNavigate + webRequest. A navigation that skips will-navigate is STILL denied by driver + webRequest (fixture-matrix-proven, see below).
- **Fail-closed invariants (all test-pinned):** missing policy file -> builtin deny-all default; broken policy file -> deny-all default with the typed error carried on every verdict (`[policy file invalid: FLAUZ_POLICY_SCHEMA]`); unparseable URL -> deny at every layer; non-drivable scheme (`data:`, `chrome:`, `vscode-webview:`) -> deny at the driver layer even with allow-all host rules; `file://` outside trusted roots -> driver deny (traversal-proof boundary matching — `/tmp/trusted` does not match `/tmp/trusted-secrets`); every-gate-kill-switched path -> deny attributed to `policyFile` (reason `fail-closed: every gate layer on the path is kill-switched`).
- **Kill-switch insurance:** `enabled: false` per layer is the B1c insurance lever — each layer individually disabled leaves the others denying (proven for all three gates on BOTH initiator paths).
- **Policy source `.flauz/browser-policy.json`** (per-workspace, git-diffable — DL-9 family), schema `flauz.browser-policy/v0`: per-layer `{ enabled?, allow?, deny?, fileRoots? }` (fileRoots driver-only) + `partitions { scope?, perAgent? }`. Schema-validated with typed error classes `FLAUZ_POLICY_PARSE | FLAUZ_POLICY_VERSION | FLAUZ_POLICY_SCHEMA | FLAUZ_POLICY_PARTITION`, each carrying the offending JSON path; host patterns normalized + validated at load (accepts bare hosts, `*.example.com`, `*`, URLs (authority wins), `user@host`, `host:port`, bracketed IPv6; rejects bare IPv6, paths, spaces).
- **Host matching mirrors the tree filter exactly** (`networkFilterService.ts:26-35` + `domainMatcher.ts:257-275`): both lists empty -> deny all; denied always wins; allow-empty + deny-set -> allow anything not denied; allow-set -> must match one. Divergences documented (README): no implicit localhost exemption (the tree exempts localhost only for rewritten tunnel URLs, `browserToolHelpers.ts:239`); driver-layer scheme policy is stricter than the raw filter.
- **Partition model (L4):** `derivePartition` -> `persist:flauz-<workspace-hash>[-<agent-id>]` (or the memory-scope form without `persist:`), workspace hash = sha256(root)[0..16] (16 lowercase hex), agent ids `[A-Za-z0-9._-]{1,64}`; `validatePartitionName` shape-validates and rejects the in-tree partition families (`persist:vscode-browser`, `vscode-browser-agent-<sha256>`) as non-Flauz; `checkPartition` containment verdicts (malformed / scope-mismatch / cross-workspace-hash). Per-agent partition request while `partitions.perAgent: false` is a typed error (fail-closed on isolation misuse).
- **Audit verdicts + evidence seam:** `PolicyVerdict` = `{ decision, layer, reason, rule?, url, partition, initiator, policyVersion, policySource, ts }`; `toEvidenceRow(verdict, taskId)` maps onto the flauz-workspace `LedgerRowInput` shape (`{ kind: 'note', uri, sha256, note }`, `extensions/flauz-workspace/src/api.ts:63-69`) with sha256 over the canonical verdict core (identical canonicalization discipline, `api.ts:148-161`; `ts` dropped from the hash so identical outcomes hash identically). Proposed seam: the Agent Bridge calls `flauz.workspace.appendEvidence { taskId, row }` (`extensions/flauz-workspace/src/commands.ts:89-106`) after writing the canonical artifact under `.flauz/artifacts/<taskId>/` (DL-21 shape 5). **No flauz-workspace file was modified** — the seam is proposed and the row mapping test-pinned.
- **Post-commit reconciliation** (SECURITY-MODEL section 4 F2): `reconcileCommittedUrl` flags a violating committed URL + recommends the `about:blank` forced reset (the committed-URL residual from the Wave-1 probes).
- **Canonical serialization:** `serializePolicy` (sorted keys, 2-space, one trailing newline — DL-9 discipline) + `policyTemplate` (the deny-all starter written by `flauz.browser.setPolicy`).

**`src/extension.ts` + `src/marks.ts` — the host wiring:**

- **Activation discipline:** `onCommand:flauz.browser.setPolicy|showPolicy|verifyPolicy|checkUrl|evaluate` ONLY — no `onStartupFinished` (the cap of 2 is reserved for bridge + workspace, PERF section 2.2; activation-lint R3 verified GREEN with flauz-browser as the 4th manifest), never `*`. Perf marks `code/flauz/willActivateBrowserPolicy` / `didActivateBrowserPolicy` (timerService aggregates `code/`-prefixed only — section 6.2 discipline).
- **Policy lifecycle:** load `.flauz/browser-policy.json` from the first workspace folder (fail-closed on missing/broken), log the effective policy (the canary grep targets), FileSystemWatcher hot-reload (engine swapped on change/delete/create), graceful no-workspace degradation.
- **Command surface:** the five commands above; `flauz.browser.evaluate` is the machine surface for the Agent Bridge (`{ url, initiator?, partition?, workspaceRoot? }` -> verdict object; derives the partition from the workspace when none is given); `checkUrl` evaluates BOTH initiator classes and logs the verdict table.

**`test/` — 5 suites, 96 node --test cases, all green** (plus a fidelity-mapped vscode mock harness, the lane-F `importWithVscodeMock` redirect pattern): `policy.test.ts` (schema/error classes/defaults/matcher/serialization/evidence — fixture-driven over all 23 good+bad files), `precedence.test.ts` (deny-at-any-layer, driver authority, B1c firing model, kill-switch insurance x6, fail-closed x4, scheme policy, file roots, reconciliation), `partition.test.ts` (derivation/validation/containment — fixture-driven), `cdpBypass.test.ts` (the 14-case CDP-bypass matrix + the B1c headline + the insurance invariant across both paths), `extension.test.ts` (activation/log lines/commands/watcher under the mock). tsc --noEmit clean (typescript 5.9.3, strict).

### 2. `test/fixtures/browser-policy/` (25 files)

- `good/` (4): minimal, full (every rule class exercised), killswitch-driver, deny-only.
- `bad/` (19): one file per violated rule class — bad JSON, root array, version missing/unsupported/type, unknown top-level key, driver type, layer unknown key, enabled type, allow type, bad allow/deny pattern, fileRoots type/dotdot/on-webRequest, partitions type/scope/perAgent/unknown. Every rule class violated at least once (test-asserted completeness + directory-listing completeness).
- `cdp-bypass-cases.json`: 7 policies x 14 cases pinning decision+layer for CDP/user navigations under the base, each-single-layer-kill-switch, all-gates-off, deny-wins-over-allow-all variants.
- `partition-cases.json`: derivations, perAgent misuse, bad agent ids, 15 valid/invalid name shapes (incl. the in-tree families as negatives), containment expectations.

### 3. `build/flauz/canaries/B-POLICY.md` — the blocked-at-all-layers canary spec

Scripted canary for the policy-gated browser pane in the default profile: setup (build recipe as C-20 + bundle-extensions + a policy-carrying workspace fixture + canary-profile `chat.agent.networkFilter: true`), 10 steps, 10 assertions — **A1-A3 boot-level automated** (engine verdict on the fixture policy via the real `src/policy.ts` import; clean boot + `bundle-extensions.mjs --verify`; networkFilter + browserView compile greps), **A4-A10 driver-level WAITING-ON-LANE F/driver** (driver block before CDP, `ERR_BLOCKED_BY_CLIENT` with driver kill-switched, will-navigate never firing for CDP navs, the full kill-switch matrix, partition name shape, ledger rows). Tree citations throughout (L1 `navigateBrowserTool.ts:62-116`/`:100-103`, L2 `browserSession.ts:310-330`/`:311`, L3 `browserView.ts:328-344`, L4 `browserSession.ts:134-180`, settings `chat.shared.contribution.ts:1548-1590`). Drift trip-wires + the honest note that lazy activation makes plain-boot log lines impossible by design (the log greps belong to the driver steps).

### 4. `.github/workflows/flauz-browser.yml` — the CI workflow (2 jobs)

- `b-policy-unit` (zero-token, timeout 15m): checkout + spec-present + lane-presence glob probe + the `node --test` suites + `tsc --noEmit` via an isolated global typescript install (never a repo install — sandbox discipline carried into CI).
- `b-policy-canary` (timeout 60m): mirrors `flauz-canaries.yml` (ubuntu-latest, pinned action SHAs, xvfb boot recipe, `ELECTRON_SKIP_BINARY_DOWNLOAD`, artifact upload); runs the B-POLICY boot-level assertion set including the exact A1 engine step (verified green in-sandbox — receipt 4 below). The auto-provided `GITHUB_TOKEN` appears ONLY as an install-step env (the DL-20/DL-28 adjudicated narrow exception — identical shape to `flauz-canaries.yml`/`flauz-hygiene.yml`); the unit job carries no token at all.
- Gated on the DL-25 path set + `workflow_dispatch`; `permissions: contents: read`; concurrency group per ref.

### 5. `extensions/flauz-browser/INTEGRATION-GAP.md` — the tree-cited wiring analysis

(See INTEGRATION-GAP section below.)

---

## VERIFICATION-RECEIPTS

All commands run in the worker sandbox (2 cores / 4GB; no repo build — sandbox discipline: fixtures + node --test + zero-dep scripts only; the CI runners execute the real boots via the added workflow).

| # | Receipt | Command + result |
|---|---|---|
| R1 | Full test suite | `cd extensions/flauz-browser && node --test "test/*.test.ts"` -> **tests 96 / pass 96 / fail 0** (duration ~0.75s; re-run after every fix incl. the final hygiene pass) |
| R2 | Typecheck | `tsc --noEmit` (typescript 5.9.3, strict, noUnusedLocals/Parameters) -> **0 errors** |
| R3 | YAML structural validation | python3 yaml.safe_load + assertions on triggers/DL-25 path gates/permissions/runs-on/timeouts/token shape -> `flauz-browser.yml: 2 jobs ... GREEN`; the 4 sibling flauz workflows still parse (sanity) |
| R4 | B-POLICY A1 (the exact CI canary step) | `node --input-type=module` importing the real `src/policy.ts`, evaluating the fixture policy against `https://evil.org/pay` -> **`deny driver agent-tool`** -> A1 GREEN |
| R5 | Additive-delta guard | `git diff --name-status 67b0b08..HEAD` -> **44 x `A`** (100% additive; zero modified/deleted); forbidden-path diff (`src/vs`, `build/lib`, non-flauz extensions, non-flauz workflows) -> **0 files** (FORK-CRITICAL ledger EMPTY, DL-12) |
| R6 | Activation lint (repo's own gate) | `node build/flauz/scripts/activation-lint.mjs --root .` -> **ACTIVATION LINT GREEN** (4 manifests incl. flauz-browser; R3 startup cap = 2: flauz-agent + flauz-workspace only; the R7 WARN is the documented pre-existing flauz-defaults gap, not this lane) |
| R7 | Harness self-test (no interference) | `sh build/flauz/scripts/verify-fixtures.sh` -> **ALL 28 CASES AS EXPECTED (0 deviations)** |
| R8 | Hygiene self-audit (work order section 4) | python3 byte-level audit: MS 4-line headers byte-exact on all 13 `.ts`/`.mts` files; tabs-only indentation CLEAN (1654 space-indented lines converted in the hygiene commit; sanctioned ` *` continuations preserved); `.json` tab-indented + parseable (`bad/` fixtures parse-exempt by design); no new `.js`/`.mjs` (=> `.eslint-allowed-javascript-files` untouched); `.ts` ASCII: all own files (unicode test input escaped; the vendored `vscode-dts/vscode.d.ts` is byte-verbatim upstream per its PROVENANCE contract — non-ASCII inventory identical to lane F's shipped copy); `.md`/`.yml` prose carries em-dashes only, matching the uniform precedent of every shipped flauz md + workflow (which additionally carry `§`/`⚠`) |
| R9 | Manifest verification | `sha256sum -c MANIFEST.txt` in the staged delivery -> **44/44 OK** |

---

## INTEGRATION-GAP (the src/vs wiring analysis — full version in `extensions/flauz-browser/INTEGRATION-GAP.md`)

**What extension-land owns (shipped):** the engine, the per-workspace policy source, the partition naming contract + containment verdicts, the audit verdict objects, the evidence-row seam, the post-commit reconciliation verdicts, and a host-matcher that byte-mirrors the tree filter's algorithm so verdicts agree wherever both run.

**The in-tree gate inventory (verified at this HEAD):** L1 driver `navigateBrowserTool.ts:62-116` (`:100-103` throws pre-navigation; helper `browserToolHelpers.ts:226-242`) — the primary enforcement point; L2 webRequest `browserSession.ts:310-330` (`:311` Agent-scope-only `onBeforeRequest`; propagation `browserViewMainService.ts:81-83` -> `browserSession.ts:119-129`); L3 will-navigate `browserView.ts:328-344` — UX-only by design (B1c); L4 partitions `browserSession.ts:134-180` (global/workspace/ephemeral/agent families); L5 permissions `browserSessionPermissions.ts:121-` (`:183-` handler); L6 file trust `browserSession.ts:341-347`; L7 TLS `browserSessionTrust.ts:46-`. Settings surface: `chat.agent.networkFilter` et al. at `chat.shared.contribution.ts:1548-1590` (default false, APPLICATION scope, restricted, enterprise policy `ChatAgentNetworkFilter`).

**The gaps (only product-side changes can wire):**

- **G1** per-workspace policy vs APPLICATION-scoped settings (no workspace-granular network policy surface exists in-tree — the gap this lane fills extension-side).
- **G2** the driver layer consults `IAgentNetworkFilterService` directly (instantiated `app.ts:1252`; consumed across main + browserView + shared-process services) — an extension cannot inject a per-workspace provider. Proposed hook (DECISION-LOG proposal DL-31): a provider interface in `platform/networkFilter/common/` consulted before the settings fallthrough; FORK-CRITICAL-class, demotion alternative = P0.
- **G3** webRequest default-off (`chat.shared.contribution.ts:1551`) — the Flauz default-on-for-agent-scope posture (SECURITY-MODEL F3) is zero-fork reachable via a `flauz-defaults` `contributes.configurationDefaults` (the C-20 affinity-pin pattern); lossy (application scope).
- **G4** will-navigate as a security gate — NOT wireable, intentionally so; the engine models it correctly (documented to prevent a future lane from "fixing" it wrong).
- **G5** partition naming control — the proposed `vscode.proposed.browser.d.ts` (`:24` `startCDPSession`, `:90` `openBrowserTab`; options `:50-62` view-only) exposes no session/partition surface, so `persist:flauz-*` names can only be minted product-side; until then the engine's partition verdicts are the audit/containment surface + the naming contract (DL-29).
- **G6** post-commit forced reset — would live in the main-process navigation-event path; the engine computes the verdict + reset target, the enforcement is product-side.

**Ranked postures:** **P0** extension-driven tabs (proposed API, zero fork; the extension gates its own `Page.navigate` — the driver allowlist becomes genuinely authoritative for the Flauz agent path) > **P1** config-only default-on L2 (zero fork, flauz-defaults) > **P2** minimal src/vs provider hook (FORK-CRITICAL ledger entry; DL-31 proposal). P0 needs only the DL-19-style product grant `"flauz.flauz-browser": ["browser"]` in `product.flauz.json#extensionEnabledApiProposals` when the lane lands — deliberately NOT added by this lane (the proposal grant without the consuming code would be dead config; noted for the TL).

---

## DECISION-LOG-PROPOSALS (DL-29+ candidates for TL adjudication)

- **DL-29 — Partition naming contract.** Adopt `persist:flauz-<workspace-hash>[-<agent-id>]` (and the memory-scope form) as the normative Flauz partition name shape: workspace hash = sha256(workspace root)[0..16] lowercase hex; agent ids `[A-Za-z0-9._-]{1,64}`; `scope: persist|memory` policy-controlled; per-agent suffix only when `partitions.perAgent: true` (misuse = typed error). Rationale: proven-live partition mechanics (Wave-1 proto #1) + the in-tree agent-session precedent (`vscode-browser-agent-<sha256(identity)>`, `browserSession.ts:165-180`) + SECURITY-MODEL F4 (per-agent jars). Class: STRUCTURAL (naming contract).
- **DL-30 — Policy-file schema versioning.** `flauz.browser-policy/v0` carries `schemaVersion: 0`; the engine REJECTS any other version at load (`FLAUZ_POLICY_VERSION`, fail-closed to the deny-all default). Breaking changes bump the version and migrate explicitly (never silently reinterpret); additive optional keys may land within v0 per upstream settings precedent. Class: STRUCTURAL (artifact format, DL-20 family).
- **DL-31 — Integration-gap posture.** Adopt the ranked postures: P0 (extension-driven tabs via the proposed browser API + product grant per DL-19) and P1 (flauz-defaults `chat.agent.networkFilter: true` default-on for agent scope, SECURITY-MODEL F3) as the zero-fork path; P2 (the `platform/networkFilter` provider hook closing G2/G5/G6 per-workspace) remains FORK-CRITICAL-ledger-gated with P0+P1 as the demotion alternative. Class: CONFIG (posture) + the P2 entry would be STRUCTURAL if ever taken.
- **(record) B-POLICY canary + flauz-browser.yml** join the DL-25 path-gated CI family; the canary's driver-level assertions are WAITING-ON-LANE F/driver (the session-driver dependency already recorded for C-23/C-24/C-28). The activation-log grep targets (`flauz.browser: effective policy ...`) are pinned by the extension tests.

---

## GAPS-AND-SKIPS

1. **Real IDE boots / real CDP sessions / real Electron partitions: OUT OF SCOPE in the sandbox** (work order section 2) — verified against fixtures + `node --test` + the byte-level tree citations; the CI runners execute the real boots via `.github/workflows/flauz-browser.yml` (boot-level A1-A3) and the driver-level A4-A10 land with the lane-F session driver. The A1 engine step was executed in-sandbox exactly as CI will run it (receipt R4).
2. **The A4-A10 canary assertions require the lane-F session driver** (a scripted chat participant driving the browser tools) — specified, not automated; same WAITING-ON-LANE posture as C-23/C-24/C-28 (their specs' driver steps are equally pending). The same B1c matrix is executable WITHOUT a browser in the unit job (and is, 96 cases).
3. **No product.flauz.json edit:** the DL-19 grant `"flauz.flauz-browser": ["browser"]` is deliberately not added — flauz-browser v0 uses NO proposed APIs (command surface only); the grant belongs to the P0 posture when the extension starts driving tabs (adding it now would be unexercised config; flagged for the TL in the DL-30/DL-31 proposals).
4. **Activation-lint R7 WARN observed** (flauz.flauz-agent not affinity-pinned) — pre-existing, owned by the future flauz-defaults lane (PERF section 7 R1); not this lane's delta.
5. **Vendored `vscode-dts/vscode.d.ts` is non-ASCII** (11 chars inside upstream doc comments) — byte-verbatim upstream copy per its PROVENANCE line ("Do not edit"), inventory identical to lane F's shipped copy; treated as an upstream artifact, not lane source. `.md`/`.yml` em-dashes match the uniform precedent of every shipped flauz md + workflow (which also carry `§`/`⚠`).
6. **PERFORMANCE-PLAN section 8 q4 (browser-tool 4-process path cold/warm):** not measured here (needs the real tool path; C-28's driver steps own it). This lane's contribution is the measurement-closure hook — the canary's policy-carrying boot is the same profile the C-28 timing capture will ride.
7. **Sandbox lint tooling:** the repo's eslint gate needs the full `npm install` (forbidden here); hygiene was verified with the byte-level audit (receipt R8) covering every binding rule (headers, tabs, ASCII, json-indent, no-new-js, additive paths). `bun run lint`-equivalent (eslint.config.js incl. `local/code-no-new-javascript-files`) runs on CI via flauz-hygiene.yml, which this lane's delta cannot regress (no new js/mjs; no edits outside flauz paths).

Staging note (for the TL): the delivery root is `/home/z/my-project/flauz-delivery/i-browser-policy/` — `MANIFEST.txt` (44 sha256 lines, all verified), `REPORT.md` (this file), `extensions/flauz-browser/**` (17 files), `test/fixtures/browser-policy/**` (25), `build/flauz/canaries/B-POLICY.md`, `.github/workflows/flauz-browser.yml`. Git bundle: `/home/z/my-project/wave4-i-browser-policy.bundle` = `67b0b081de0a5c786d681a383637390f16c62c6b..flauz/wave4/browser-policy` (3 commits: milestone 1 engine+tests; milestones 2+3 gap/canary/workflow; hygiene pass). Pushes from this sandbox are blocked (expected); the TL harvests the staged files + bundle.
