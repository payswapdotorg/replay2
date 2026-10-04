/**
 * Engineering Lab catalog — workload profile fixtures (mission step 2).
 *
 * Workload profiles describe WHERE the user's engineering effort actually
 * goes (signals) and WHAT kinds of tasks that effort decomposes into
 * (taskMix). These three fixtures are the B-wave workload representation;
 * "learned" profiles (derived from observed traffic) land in a later wave
 * and must satisfy the same frozen WorkloadProfile contract.
 */

import type { WorkloadProfile, WorkloadSignal } from "../contracts";

export const workloadProfiles: WorkloadProfile[] = [
  {
    id: "wl.solo-maintainer",
    name: "Solo Maintainer",
    description:
      "A single maintainer carrying a mid-size TypeScript service: steady commit flow, light review traffic, occasional incidents, and a long tail of flaky tests and doc drift.",
    signals: [
      {
        kind: "repo-commits",
        label: "Repository commit volume",
        weight: 0.7,
        value: 0.55,
      },
      {
        kind: "pr-review-volume",
        label: "PR review traffic",
        weight: 0.3,
        value: 0.25,
      },
      {
        kind: "incident-rate",
        label: "Production incident rate",
        weight: 0.1,
        value: 0.15,
      },
      {
        kind: "test-flake-rate",
        label: "Test flakiness",
        weight: 0.2,
        value: 0.35,
      },
      {
        kind: "docs-drift",
        label: "Documentation drift",
        weight: 0.15,
        value: 0.4,
      },
    ],
    taskMix: [
      { taskTypeId: "impl.bugfix", share: 0.5 },
      { taskTypeId: "maint.refactor", share: 0.2 },
      { taskTypeId: "review.pr", share: 0.2 },
      { taskTypeId: "invest.flake", share: 0.1 },
    ],
    budgetUsdPerTask: 0.8,
    latencySlaMinutes: 120,
    source: "fixture",
  },
  {
    id: "wl.feature-team",
    name: "Feature Team",
    description:
      "A product feature team shipping against a roadmap: heavy commits and review volume, growing CI duration, moderate incidents, and constant spec churn.",
    signals: [
      {
        kind: "repo-commits",
        label: "Repository commit volume",
        weight: 0.9,
        value: 0.8,
      },
      {
        kind: "pr-review-volume",
        label: "PR review traffic",
        weight: 0.8,
        value: 0.75,
      },
      {
        kind: "incident-rate",
        label: "Production incident rate",
        weight: 0.2,
        value: 0.25,
      },
      {
        kind: "feature-spec-churn",
        label: "Feature specification churn",
        weight: 0.5,
        value: 0.45,
      },
      {
        kind: "ci-duration",
        label: "CI pipeline duration",
        weight: 0.35,
        value: 0.4,
      },
      {
        kind: "test-flake-rate",
        label: "Test flakiness",
        weight: 0.25,
        value: 0.2,
      },
    ],
    taskMix: [
      { taskTypeId: "impl.feature", share: 0.45 },
      { taskTypeId: "impl.bugfix", share: 0.25 },
      { taskTypeId: "review.pr", share: 0.2 },
      { taskTypeId: "maint.migration", share: 0.1 },
    ],
    budgetUsdPerTask: 2.5,
    latencySlaMinutes: 240,
    source: "fixture",
  },
  {
    id: "wl.oncall-sre",
    name: "On-call SRE",
    description:
      "An on-call reliability engineer working an incident-heavy queue: flaky test investigations, urgent bug fixes, and short-fused reviews under MTTR pressure.",
    signals: [
      {
        kind: "incident-rate",
        label: "Production incident rate",
        weight: 0.9,
        value: 0.85,
      },
      {
        kind: "repo-commits",
        label: "Repository commit volume",
        weight: 0.4,
        value: 0.3,
      },
      {
        kind: "pr-review-volume",
        label: "PR review traffic",
        weight: 0.2,
        value: 0.15,
      },
      {
        kind: "log-gaps",
        label: "Observability log gaps",
        weight: 0.45,
        value: 0.5,
      },
      {
        kind: "mttr-pressure",
        label: "Mean-time-to-resolution pressure",
        weight: 0.5,
        value: 0.6,
      },
    ],
    taskMix: [
      { taskTypeId: "invest.flake", share: 0.4 },
      { taskTypeId: "impl.bugfix", share: 0.4 },
      { taskTypeId: "review.pr", share: 0.2 },
    ],
    budgetUsdPerTask: 0.5,
    latencySlaMinutes: 30,
    source: "fixture",
  },
];

/**
 * The highest-impact signals of a profile (weight * value), descending.
 * Useful for one-line console summaries and recommendation rationales.
 * Pure and deterministic (Array#sort is stable, comparator is total).
 */
export function summarySignals(profile: WorkloadProfile, limit = 3): WorkloadSignal[] {
  return [...profile.signals]
    .sort((a, b) => b.weight * b.value - a.weight * a.value)
    .slice(0, Math.max(0, limit));
}
