/**
 * Engineering Lab catalog — the FIRST software-engineering task world
 * (mission step 3): `se.repo-maintenance`, a synthetic mid-size TypeScript
 * service repo. Scenarios declare per-taskType difficulty, instance counts
 * and perturbation modes; the world engine (src/lib/lab/worlds/se-world.ts)
 * expands them into deterministic TaskInstances.
 */

import type { TaskScenario } from "../contracts";

export const seWorld = {
  id: "se.repo-maintenance",
  name: "Synthetic mid-size TypeScript service repo",
  description:
    "A synthetic mid-size TypeScript service repository (payments, orders, ingestion, webhooks) with a realistic layout, CI, tests and flaky surfaces. All instances are generated deterministically from (scenario, seed) — nothing here is runtime evidence; it is fixture-grade simulated workload.",
} as const;

export const seWorldScenarios: TaskScenario[] = [
  {
    id: "se.bugfix-regression",
    worldId: "se.repo-maintenance",
    taskTypeId: "impl.bugfix",
    name: "Bug Fix — Regression",
    description:
      "Regressions introduced by recent refactors: CI failures, runtime errors and failing payment/order paths that must be localized, fixed and covered by a regression test.",
    difficultyBase: 0.45,
    instanceCount: 8,
    perturbations: ["noisy-stacktrace", "flaky-test", "cold-cache"],
  },
  {
    id: "se.feature-addition",
    worldId: "se.repo-maintenance",
    taskTypeId: "impl.feature",
    name: "Feature Addition",
    description:
      "Small-to-mid features added to the synthetic service: new endpoint behavior, webhook handling or configuration surface, delivered against existing conventions with test coverage.",
    difficultyBase: 0.6,
    instanceCount: 8,
    perturbations: ["scope-creep", "api-drift"],
  },
  {
    id: "se.flaky-investigation",
    worldId: "se.repo-maintenance",
    taskTypeId: "invest.flake",
    name: "Flaky Test Investigation",
    description:
      "Intermittent test failures across the payments/ingestion suites: isolate the flaky path, establish a deterministic reproduction, and propose or land the stabilization.",
    difficultyBase: 0.5,
    instanceCount: 6,
    perturbations: ["intermittent-repro", "log-gaps"],
  },
];
