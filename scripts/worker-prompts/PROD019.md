# PROD-019 — Android mobile adapter productization and field journey

You are a senior Android/Kotlin engineer executing ONE well-specified work item
in the AISE repository. This document is your task packet — follow it exactly.
The repository itself is your specification library; read the mandated files
below BEFORE writing anything.


## 0a. Operational notes from a previous attempt (2026-09-17, battle-tested)

A prior session executed this packet partway before an infrastructure
interruption. Its verified findings, so you do not re-derive them:

- The PROD-016 adapter contract and the FIX-001 server fix are MERGED on
  public main (7d21d47) — the base gate is exactly 3718 pass / 0 fail. The
  historical test-isolation defect on the old 1068ebb base is fixed there;
  do not chase it.
- Your sandbox ships JRE 21 only (no javac, no sudo). Fetch the portable
  JDK 21 from Adoptium (https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse —
  GitHub-backed CDN, reachable from the sandbox) into /tmp, untar, and put
  its bin/ on PATH for the Gradle probe.

## 0. Ground rules

- ONE work item: PROD-019 (the Android mobile adapter). Do not start
  PROD-017/018/020 or any other item. Do not touch web or desktop surfaces.
- Owned surface (the ONLY files you may create/modify):
  - `apps/android/**` (the Android adapter application)
  - `docs/productization-evidence/PROD-019/**` (evidence documents)
- Explicitly NOT yours: `packages/adapter-contract/**` and
  `spec/client-adapter-contract.md` (the shared contract — the PROD-016
  compatibility window FORBIDS adapter workers from changing it; CONSUME the
  committed JSON Schemas + fixtures + `CONFORMANCE_CHECKS` semantics, never
  modify the package), `apps/web/**`, `apps/desktop/**`, `backend/**`,
  `packages/shared-contracts/**`, `docs/productization-state.json`
  (Tech-Lead-owned), every other spec file, the root `bun.lock`.
- If a mandated reading contradicts this packet, STOP and report the conflict.
- Follow the existing Android architecture exactly: pure-Kotlin domain logic
  in `:core` (no Android dependencies), platform/UI glue in `:app`.
  Versions pinned in `gradle/libs.versions.toml`; no new third-party runtime
  dependencies unless strictly required (the TEST-scope json-schema-validator
  pattern is already established).
- Never weaken, skip or delete an existing test.

## 1. Setup — public main (the shared contract IS on GitHub main now)

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 7d21d47147a3df14a0e6138131de6d9add672d27   # public GitHub main (PROD-016 + PROD-021 merged)
git rev-parse HEAD   # must print 7d21d47147a3df14a0e6138131de6d9add672d27
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-019/android-adapter
bun run verify
```

Baseline expectation: **3718 pass / 0 fail, VERIFY: PASS** (the PROD-016
adapter-contract suite and the FIX-001 regression test are on main; the root
bun gate covers the TypeScript workspace; your Kotlin work is gated by
Gradle — §5).

Java/Gradle probe (do this BEFORE writing Kotlin):

```bash
cd apps/android
java -version 2>&1 | head -1        # JDK/JRE present?
./gradlew --no-daemon :core:test    # first run downloads Gradle 8.14.3 + deps
```

If your sandbox has no Java at all, report that immediately in your final
report's notes and proceed carefully: keep every new line of Kotlin within
the patterns of the existing code, gate what you can, and the Lead will run
the full Gradle gate at the integration station. Do NOT claim Gradle results
you did not produce.

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/client-adapter-contract.md` (the contract INCLUDING the PROD-016
   checkable-artifacts section, merged to main with PROD-016)
4. `spec/governance/architecture-change-record-004.md` (ACR-004: client
   adapters over a single product core — THE governing record for this item)
5. `spec/governance/architecture-change-record-005.md` and `-006.md`
6. `docs/productization-work-orders.md` §PROD-019 (your work order —
   reproduced in §3 below)
7. `packages/adapter-contract/` IN FULL — README.md (ESPECIALLY the
   non-TypeScript-consumer section: Android consumes the COMMITTED
   `schemas/*.schema.json` + `schemas/manifest.json` + fixtures +
   `CONFORMANCE_CHECKS` semantics), `src/adapter-contracts.version.ts`
   (`ADAPTER_CONTRACT_VERSION = "1.0.0"`), `src/capability.ts`
   (ClientCapabilityProfile shape), `src/negotiation.ts` (the
   permitted/degraded/unknown/blocked verdict model and domain outcomes),
   `src/reference-profiles.ts` (REFERENCE_MOBILE_FIELD_PROFILE as your
   template), `fixtures/` (the committed corpus you validate against)
8. `docs/productization-evidence/PROD-016/adapter-boundary-audit.md` — the
   §"apps/android" findings AND the §"apps/android — required adapter-local
   removals" (A-R1 … A-R4): these removals are YOUR recorded obligations
9. `docs/productization-evidence/PROD-016/compatibility-window.md` (you must
   not change the shared contract)
10. `apps/android/` IN FULL — README.md (the module architecture, commands,
    offline behavior, the capture session layer docs), settings.gradle.kts,
    gradle/libs.versions.toml, every module under `core/` and `app/` including
    their tests. This is the foundation you are promoting into the product's
    mobile adapter.

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-019 — Android mobile adapter productization and field journey
> **Owner:** MOBILE — **Depends on:** PROD-016
> **Protected surface:** `apps/android/**` and Android-specific adapter tests/docs.
> **Purpose:** Promote the existing Android capture foundation into the
> product's mobile adapter without duplicating domain authority.
> **Scope:**
> - map the Android client to the shared task/capability/result contract;
> - wire field-intent selection → capability assessment → adaptive mission →
>   guided capture → evidence submission/resume;
> - preserve the existing offline-first capture/session integrity guarantees;
> - support explicit provider/network-unavailable behavior and resumable
>   synchronization;
> - implement mobile conformance tests using PROD-016 fixtures;
> - make the mobile UI expose exact capture actions and evidence gaps instead
>   of generic capture prompts.
> **Explicit non-scope:** Do not modify `apps/web/**` or `apps/desktop/**`.
> Do not make mobile assurance decisions. Do not lower evidence requirements
> for weak devices. iOS is not required for this item; a future iOS adapter
> must consume the same contract.
> **Acceptance:**
> - Android is an adapter, not a second domain implementation;
> - representative field journey is executable with offline interruption/resume;
> - evidence reaches the same server-authoritative semantics as browser
>   operations;
> - mobile conformance passes;
> - capability degradation changes acquisition strategy/operator burden, not
>   assurance thresholds.
> **Evidence:** Android unit/instrumentation trace + adapter conformance
> report + offline/resume evidence + representative field journey recording.

## 4. Implementation shape

Follow the existing `:core` (pure Kotlin, JVM-testable) / `:app` (Android
platform) split exactly. Put ALL new contract-consumption domain logic in
`:core` so it is fully unit-testable on a plain JVM; `:app` gets the UI/state
wiring. Required work, mapped to the acceptance criteria:

1. **Adapter contract version mirror (A-R1):** an `AdapterContractVersion`
   constant mirror in `:core`, cross-checked in a test against
   `packages/adapter-contract/src/adapter-contracts.version.ts`
   (`ADAPTER_CONTRACT_VERSION = "1.0.0"`) so wire drift is a test failure.
2. **Client capability profile + negotiation consumption (A-R2):** declare
   the mobile adapter's honest `ClientCapabilityProfile` as a `:core` value
   (template: `REFERENCE_MOBILE_FIELD_PROFILE` from
   `packages/adapter-contract/src/reference-profiles.ts`, with the fixture
   `fixtures/capability/ClientCapabilityProfile.valid-mobile-field.json` as
   the committed reference). Implement a `:core` negotiation RESULT consumer
   that takes a server-provided `TaskCapabilityRequirements` set (parsed from
   the committed schemas/fixtures) plus the declared profile and derives the
   permitted interaction modes and the per-domain
   `satisfied|unsupported|unknown` + overall
   `permitted|degraded|unknown|blocked` verdict — mirroring
   `packages/adapter-contract/src/negotiation.ts` semantics faithfully (same
   domain outcomes, same verdict vocabulary). The mission UX surfaces this
   verdict and its domain reasons: an explicit BLOCKED state with the reason
   rendered verbatim, never a generic prompt.
3. **Compatibility-checker alignment (A-R3):** align or explicitly document
   the `MissionCompatibilityChecker` verdict vocabulary vs the shared
   negotiation outcomes (the checker concerns DEVICE capture domains per the
   AISE-003 capture contract; the shared negotiation concerns CLIENT platform
   capability) so the two verdict models cannot silently diverge. Either way
   the checker stays facts-not-policy.
4. **Schema validation of server records (A-R4):** replicate the
   `SessionManifestExporter` schema-validation pattern (TEST-scope
   json-schema-validator against COMMITTED schema files) for the twelve-object
   server records the mobile adapter consumes: validate every committed
   `packages/adapter-contract/fixtures/**/valid-*.json` (and the reference
   requirement fixtures) against the corresponding committed
   `packages/adapter-contract/schemas/**/*.schema.json` from `:core` tests —
   this is the mobile conformance suite using PROD-016 fixtures. Also
   implement the C0–C9 `CONFORMANCE_CHECKS` semantics that are meaningful for
   a non-TypeScript consumer (corpus completeness, profile validity, lossless
   round-trip of the objects the adapter touches, authoritative-field
   read-only handling) as `:core` tests against the committed corpus.
5. **Field journey wiring:** field-intent selection (TaskIntent-shaped) →
   capability assessment (the negotiation consumer) → adaptive mission (the
   existing capture session runtime, mission parameters derived from the
   negotiated outcome) → guided capture (exact capture actions and evidence
   gaps exposed in the UI — the existing capture screens extended, not
   replaced) → evidence submission/resume (the existing offline manifest +
   recovery engine, now emitting submission payloads that validate against
   the contract schemas).
6. **Offline-first preserved + explicit unavailability:** the offline queue,
   session integrity, content identity and capture platform layers stay
   untouched in behavior (the audit records NO removals there). Add explicit
   provider/network-unavailable states and resumable synchronization semantics
   at the submission seam — network unavailability is a first-class UI state,
   never a silent failure.
7. **No assurance decisions on mobile:** capability degradation changes
   acquisition strategy/operator burden, never assurance thresholds — assert
   this in tests (a degraded profile cannot weaken a requirement).

Evidence documents under `docs/productization-evidence/PROD-019/`:
- `conformance-report.md` — the mobile profile declaration, the C0–C9
  coverage as implemented for the non-TypeScript consumer, schema-validation
  results over the committed corpus;
- `field-journey.md` — the representative field journey (intent → assessment
  → mission → guided capture with an offline interruption → resume →
  submission), the semantic objects at each step, and the offline/resume
  evidence (which JVM tests prove interruption/resume);
- `gradle-trace.md` — the exact Gradle commands you ran and their summary
  output (honest about what ran in your sandbox; the Lead re-runs the full
  gate at the integration station).

## 5. Gate (must pass before reporting)

Two gates:

```bash
bun run verify            # root TypeScript gate — must stay 3718 pass / 0 fail
cd apps/android
./gradlew --no-daemon :core:test    # your Kotlin domain gate — must pass
```

`bun run verify` expectation: **3718 pass / 0 fail, VERIFY: PASS** (your work
adds no TypeScript tests; do not invent fake ones — your N is in Gradle).
`:core:test` must pass with your new tests included (state the test count).
If your sandbox has the Android SDK, ALSO run `:app:test` and note the
result; if not, the Lead runs it at the integration station — say so.

Then commit locally (no push):

```bash
git add <your owned files only>
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-019: Android mobile adapter productization and field journey"
git diff $BASE..HEAD --stat
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's
harvest API cannot see. After committing, copy EVERY new/changed file (the
complete diff vs the base commit `$BASE` from §1) into the PROJECT
directory (the one containing package.json / src/ — the workspace root),
preserving repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery if staged (remove `delivery/bun.lock`).
Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-019 COMPLETION REPORT
base: public main @ 7d21d47147a3df14a0e6138131de6d9add672d27 (PROD-016 + PROD-021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new gradle tests: <count + which :core suites>
root bun gate: 3718 pass / 0 fail (unchanged — no TS tests added)
adapter mapping: <one-line proof Android is an adapter, not a domain fork (A-R1/A-R3)>
profile + negotiation: <one-line proof of the declared profile + verdict surfacing (A-R2)>
conformance: <corpus/schema validation counts + C0–C9 coverage as non-TS consumer (A-R4)>
field journey + offline: <one-line proof of the journey with interruption/resume>
unavailable-provider behavior: <one-line proof>
verify: <paste BOTH gate summaries: bun run verify final lines AND gradle :core:test result>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <java/gradle availability in your sandbox, :app:test status, any deviation, or "none">
```
