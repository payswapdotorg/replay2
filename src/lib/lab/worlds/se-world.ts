/**
 * Engineering Lab — world engine for `se.repo-maintenance`
 * (mission step 3, the FIRST software-engineering task world).
 *
 * DETERMINISM LAWS: pure functions only. Instance generation is a function of
 * (scenario, count, seed) — byte-identical on every call, in every process.
 * All randomness flows through the seeded RNG; there is no clock access and
 * no unseeded randomness anywhere in this file.
 *
 * Conventions B2/B3 rely on:
 * - `instance.seed` is the per-instance sub-seed (hashSeed(scenario.id, seed,
 *   index)) so any single instance can be regenerated or re-executed alone.
 * - `instance.acceptance` strings are the canonical verification strings:
 *   execution adapters are expected to emit `outcome.verification` entries
 *   whose `check` field is taken verbatim from this list (see
 *   src/lib/lab/execution/fixture-adapter.ts).
 */

import { seWorld } from "../catalog/se-world";
import { findTaskType } from "../catalog/task-types";
import type { TaskInstance, TaskOutcome, TaskScenario, WorldEngine } from "../contracts";
import { clamp01, createRng, hashSeed, type Rng } from "../rng";

// ---------------------------------------------------------------------------
// Brief fragment banks (keyed by taskTypeId, with a generic fallback).
// Each brief = opener + 1-2 evidence fragments + constraint + deliverable
// (+ optional context note) => 4-6 sentences, chosen deterministically.
// ---------------------------------------------------------------------------

interface BriefBank {
  openers: string[];
  evidence: string[];
  constraint: string[];
  deliverable: string[];
  contextNote: string[];
}

const BUGFIX_BANK: BriefBank = {
  openers: [
    "CI fails on `payments/service.ts` L142 with a TypeError after the retry refactor.",
    "Users report 500s from `orders/router.ts` when the discount code field is left empty.",
    "The nightly ingest job on `ingest/cron.ts` deadlocks whenever two runs overlap.",
    "Payments webhook handling in `webhooks/stripe.ts` double-charges on duplicate delivery.",
    "The orders export endpoint returns stale rows after the cache change landed.",
    "`payments/gateway.ts` retries forever when the PSP returns HTTP 429.",
  ],
  evidence: [
    "The stack trace points at the gateway call, but the exception is swallowed and re-thrown one layer up.",
    "Reproduction requires the `payments.v2` feature flag to be enabled.",
    "The failure started at commit {sha} and is reproducible on main.",
    "Logs show the request retried three times before the crash, with no backoff between attempts.",
    "The suite passes locally but fails on the CI runner roughly one run in three.",
    "Error grouping shows 47 events under the same fingerprint in the last 24 hours.",
  ],
  constraint: [
    "A regression test must cover the failing path before the fix lands.",
    "The fix must not widen the public API of the touched module.",
    "Keep the change minimal; a follow-up refactor is already scheduled.",
    "The data contract with the PSP must stay byte-compatible.",
    "The failing path is on the money-movement critical path — zero tolerance for silent failures.",
  ],
  deliverable: [
    "Deliver the localized fix plus a regression test, and post a short root-cause note.",
    "Expected output: a single focused diff, updated tests, and a green CI run.",
    "Hand back a patch, the reproduction steps, and the root cause in one paragraph.",
  ],
  contextNote: [
    "The repo is mid-migration from REST handlers to typed routers; some paths appear in both styles.",
    "Two maintainers are on holiday; assume high review latency.",
    "The service deploys hourly; long-lived branches will conflict.",
  ],
};

const FEATURE_BANK: BriefBank = {
  openers: [
    "Add idempotency keys to the checkout endpoint in `orders/router.ts`.",
    "Implement webhook signature verification for `webhooks/stripe.ts` per the provider spec.",
    "Expose the new `GET /payments/:id/ledger` endpoint from `payments/service.ts`.",
    "Add a dead-letter queue path for ingest rows that fail validation three times.",
    "Introduce a per-tenant rate limit on the public API surface.",
    "Support dry-run mode for the migration runner in `ingest/cron.ts`.",
  ],
  evidence: [
    "The design doc names three acceptance behaviors; two are mandatory and one is stretch.",
    "An RFC exists, but its API example is out of date with the current router signature.",
    "The CLI contract is frozen; flags may be added but not renamed.",
    "Contract tests exist for the sibling endpoint and should be mirrored.",
    "The change must remain behind the `payments.v2` flag until ops signs off.",
  ],
  constraint: [
    "Tests are mandatory: happy path, one rejection case, and one idempotency case.",
    "Follow the existing service/module layout; no new top-level directories.",
    "Keep the diff reviewable: target under 400 changed lines.",
    "The feature must be reversible — feature-flagged or trivially revertible.",
    "No new runtime dependencies without written justification.",
  ],
  deliverable: [
    "Deliver the implementation, the tests, and a one-paragraph rollout note.",
    "Expected output: working code behind the flag, updated contract tests, and a changelog entry.",
    "Hand back the diff, the test plan, and any spec corrections you discover.",
  ],
  contextNote: [
    "The SDK team consumes this API; breaking changes need a deprecation shim.",
    "The service is mid-migration; prefer wiring through the typed router.",
    "Last quarter's load tests showed the checkout path is CPU-bound; watch the hot loop.",
  ],
};

const INVESTIGATION_BANK: BriefBank = {
  openers: [
    "`tests/payments/service.test.ts` 'refunds a partial capture' fails roughly once per ten CI runs.",
    "The ingest e2e flow times out on the second parallel shard only.",
    "`tests/orders/router.test.ts` intermittently asserts on a stale discount fixture.",
    "The checkout e2e suite flakes between 03:00 and 04:00 UTC.",
    "`tests/ingest/cron.test.ts` deadlocks in about 5% of CI runs.",
    "A random subset of payments tests fails after cold cache restores.",
  ],
  evidence: [
    "Failure mode is an assertion on a timestamp that is sometimes equal, sometimes one tick late.",
    "The retry helper introduces sleeps that make the assertion racy.",
    "Logs are truncated at 10k lines; the decisive frames are usually missing.",
    "The flake correlates with CI runner swaps, not with commit content.",
    "Local re-runs over 200 iterations failed to reproduce.",
    "The suite shares one test database between shards.",
  ],
  constraint: [
    "Establish a deterministic reproduction or a statistically sound characterization first.",
    "The fix must keep test runtime under the current budget (no added sleeps above 50ms).",
    "Do not mark tests skipped; quarantine is acceptable only with a tracking note.",
    "Propose the stabilization, but land only what you can prove.",
    "Report the flake rate before and after, with the runs to back it.",
  ],
  deliverable: [
    "Deliver the root cause, the reproduction (or characterization), and the stabilization patch.",
    "Expected output: an analysis note, the racy path identified by file and line, and a minimal fix.",
    "Hand back the evidence chain: runs, timings, and the diff.",
  ],
  contextNote: [
    "The nightly pipeline is allow-fail for this suite; your job is to end that.",
    "Two other teams pin this suite green in their dashboards.",
  ],
};

const GENERIC_BANK: BriefBank = {
  openers: [
    "A change request is open against the synthetic service repo.",
    "CI flagged a new failure class on the main branch.",
    "A recurring maintenance item in the service repo needs attention.",
  ],
  evidence: [
    "The relevant surface spans a few files in payments/ and orders/.",
    "The behavior is reproducible from the recorded seed.",
    "Recent commits touched the same path.",
  ],
  constraint: [
    "Keep the change scoped and reviewable.",
    "Do not break the existing test suite.",
  ],
  deliverable: [
    "Deliver the change plus the evidence that it holds.",
    "Expected output: a focused diff and a green run.",
  ],
  contextNote: [
    "The repo layout follows the standard module conventions.",
  ],
};

const BRIEF_BANKS: Record<string, BriefBank> = {
  "impl.bugfix": BUGFIX_BANK,
  "impl.feature": FEATURE_BANK,
  "invest.flake": INVESTIGATION_BANK,
};

// ---------------------------------------------------------------------------
// Synthetic repo layout (shared by every scenario in this world).
// ---------------------------------------------------------------------------

const REPO_PATHS: string[] = [
  "src/payments/service.ts",
  "src/payments/gateway.ts",
  "src/payments/retry.ts",
  "src/payments/ledger.ts",
  "src/orders/router.ts",
  "src/orders/processor.ts",
  "src/orders/discount.ts",
  "src/ingest/cron.ts",
  "src/ingest/queue.ts",
  "src/webhooks/stripe.ts",
  "src/lib/config.ts",
  "src/lib/logger.ts",
  "src/lib/backoff.ts",
  "src/db/schema.ts",
  "src/db/migrations/0042_add_retry_state.ts",
  "tests/payments/service.test.ts",
  "tests/payments/gateway.test.ts",
  "tests/orders/router.test.ts",
  "tests/ingest/cron.test.ts",
  "tests/e2e/checkout.flow.ts",
  "tests/helpers/fixtures.ts",
  "package.json",
  "tsconfig.json",
  "docs/runbook.md",
];

// ---------------------------------------------------------------------------
// Acceptance criteria banks (canonical verification strings; keyed by
// taskTypeId with a generic fallback).
// ---------------------------------------------------------------------------

const ACCEPTANCE_BANKS: Record<string, string[]> = {
  "impl.bugfix": [
    "Regression test covering the failing path passes",
    "Full suite for the touched module is green",
    "No public API change in the diff",
    "Root-cause note attached to the fix",
    "No new lint warnings introduced",
  ],
  "impl.feature": [
    "Happy-path test passes",
    "Rejection case covered by a test",
    "Contract test for the new surface passes",
    "Feature is gated by the agreed flag",
    "No new runtime dependencies added",
  ],
  "maint.refactor": [
    "Public behavior unchanged (diff inspection clean)",
    "Full module suite green",
    "No new lint warnings introduced",
  ],
  "review.pr": [
    "Review verdict recorded with rationale",
    "Blocking issues enumerated or none found",
  ],
  "invest.flake": [
    "Deterministic reproduction (or characterization) documented",
    "Touched suite green across 10 consecutive runs",
    "No skipped tests without a tracking note",
    "Racy path identified by file and line",
    "Flake-rate evidence attached",
  ],
  "maint.migration": [
    "Migration applies and rolls back cleanly",
    "Full module suite green",
    "No new lint warnings introduced",
  ],
};

const GENERIC_ACCEPTANCE: string[] = [
  "Change satisfies the brief",
  "Tests covering the touched path pass",
];

// ---------------------------------------------------------------------------
// Deterministic helpers.
// ---------------------------------------------------------------------------

/** Deterministically select `count` distinct items (partial Fisher-Yates). */
function pickDistinct<T>(rng: Rng, items: readonly T[], count: number): T[] {
  if (count >= items.length) {
    return [...items];
  }
  const pool = [...items];
  for (let i = 0; i < count; i++) {
    const j = i + rng.int(pool.length - i);
    const tmp = pool[i];
    pool[i] = pool[j];
    pool[j] = tmp;
  }
  return pool.slice(0, count);
}

/** Build the instance brief from 4-6 deterministic template fragments. */
function buildBrief(rng: Rng, bank: BriefBank, repoSha: string): string {
  const sentences: string[] = [rng.pick(bank.openers)];
  const evidenceCount = rng.bernoulli(0.55) ? 2 : 1;
  sentences.push(...pickDistinct(rng, bank.evidence, evidenceCount));
  sentences.push(rng.pick(bank.constraint));
  sentences.push(rng.pick(bank.deliverable));
  if (rng.bernoulli(0.4)) {
    sentences.push(rng.pick(bank.contextNote));
  }
  return sentences.map((s) => s.replaceAll("{sha}", repoSha)).join(" ");
}

// ---------------------------------------------------------------------------
// The world engine.
// ---------------------------------------------------------------------------

export const seWorldEngine: WorldEngine = {
  worldId: seWorld.id, // "se.repo-maintenance"

  generateInstances(scenario: TaskScenario, count: number, seed: number): TaskInstance[] {
    // Scenario-level RNG: fixes a repo revision stamp shared by this batch.
    const scenarioRng = createRng(hashSeed(scenario.id, seed));
    const repoSha = Math.floor(scenarioRng.next() * 0x10000000)
      .toString(16)
      .padStart(7, "0");

    const taskType = findTaskType(scenario.taskTypeId);
    const briefBank = BRIEF_BANKS[scenario.taskTypeId] ?? GENERIC_BANK;
    const obstaclePool =
      taskType?.typicalObstacles.length && taskType.typicalObstacles.length > 0
        ? taskType.typicalObstacles
        : scenario.perturbations;
    const acceptancePool = ACCEPTANCE_BANKS[scenario.taskTypeId] ?? GENERIC_ACCEPTANCE;

    const instances: TaskInstance[] = [];
    for (let i = 0; i < count; i++) {
      // Per-instance sub-RNG: instance i is independent of count and order.
      const instanceSeed = hashSeed(scenario.id, seed, i);
      const rng = createRng(instanceSeed);

      const brief = buildBrief(rng, briefBank, repoSha);

      // 3-6 context files with 40-900 lines and 0.3-1.0 relevance.
      const fileCount = 3 + rng.int(4); // 3..6
      const files = pickDistinct(rng, REPO_PATHS, fileCount).map((path) => ({
        path,
        lines: 40 + rng.int(861), // 40..900
        relevance: Number(rng.range(0.3, 1.0).toFixed(3)),
      }));

      // 1-3 obstacles from the task type's typicalObstacles, severity 0.2-0.9.
      const obstacleCount = 1 + rng.int(3); // 1..3
      const obstacles = pickDistinct(rng, obstaclePool, obstacleCount).map((kind) => ({
        kind,
        severity: Number(rng.range(0.2, 0.9).toFixed(3)),
      }));

      // 2-4 acceptance criteria.
      const acceptanceCount = Math.min(2 + rng.int(3), acceptancePool.length); // 2..4
      const acceptance = pickDistinct(rng, acceptancePool, acceptanceCount);

      // difficulty = clamp01(base + 0.18 * avgObstacleSeverity + jitter)
      const avgSeverity =
        obstacles.reduce((sum, o) => sum + o.severity, 0) / Math.max(1, obstacles.length);
      const difficulty = clamp01(
        scenario.difficultyBase + 0.18 * avgSeverity + rng.range(-0.05, 0.05),
      );

      instances.push({
        id: `${scenario.id}#${i}`,
        scenarioId: scenario.id,
        index: i,
        seed: instanceSeed,
        brief,
        contextFiles: files,
        obstacles,
        acceptance,
        difficulty: Number(difficulty.toFixed(4)),
      });
    }
    return instances;
  },

  checkAcceptance(outcome: TaskOutcome, instance: TaskInstance): boolean {
    // The world accepts an outcome only when:
    //  1. the executor reports success,
    //  2. verification actually ran (an empty check list proves nothing),
    //  3. every emitted check passed, and
    //  4. every acceptance criterion is covered by a passing check.
    // Convention: a check "maps to" an acceptance criterion when its `check`
    // string equals the criterion string (adapters emit them verbatim).
    if (!outcome.success) {
      return false;
    }
    const checks = outcome.verification;
    if (checks.length === 0) {
      return false;
    }
    if (!checks.every((c) => c.passed)) {
      return false;
    }
    const passedChecks = new Set(checks.filter((c) => c.passed).map((c) => c.check));
    return instance.acceptance.every((criterion) => passedChecks.has(criterion));
  },
};
