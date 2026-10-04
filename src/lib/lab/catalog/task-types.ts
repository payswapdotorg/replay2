/**
 * Engineering Lab catalog — task type taxonomy (mission step 2).
 *
 * Task types are the workload -> simulation bridge: a workload's taskMix
 * names these ids, scenarios reference exactly one taskType, and the world
 * engine draws obstacles / acceptance criteria from the type's
 * typicalObstacles / verificationStyle.
 */

import type { TaskTypeDescriptor } from "../contracts";

export const taskTypes: TaskTypeDescriptor[] = [
  {
    id: "impl.bugfix",
    name: "Bug Fix",
    family: "implementation",
    complexity: 0.55,
    contextNeeds: 0.6,
    verificationStyle: "tests",
    typicalTools: [
      "tool.editor",
      "tool.test-runner",
      "tool.shell",
      "tool.search",
      "tool.vcs",
    ],
    typicalObstacles: ["noisy-stacktrace", "flaky-test", "cold-cache", "hidden-coupling"],
  },
  {
    id: "impl.feature",
    name: "Feature",
    family: "implementation",
    complexity: 0.65,
    contextNeeds: 0.7,
    verificationStyle: "tests",
    typicalTools: [
      "tool.editor",
      "tool.shell",
      "tool.search",
      "tool.test-runner",
      "tool.vcs",
      "tool.linter",
    ],
    typicalObstacles: ["scope-creep", "api-drift", "hidden-coupling"],
  },
  {
    id: "maint.refactor",
    name: "Refactor",
    family: "maintenance",
    complexity: 0.5,
    contextNeeds: 0.5,
    verificationStyle: "diff-inspection",
    typicalTools: [
      "tool.editor",
      "tool.search",
      "tool.linter",
      "tool.test-runner",
      "tool.vcs",
    ],
    typicalObstacles: ["hidden-coupling", "api-drift", "cold-cache"],
  },
  {
    id: "review.pr",
    name: "PR Review",
    family: "review",
    complexity: 0.35,
    contextNeeds: 0.4,
    verificationStyle: "review",
    typicalTools: ["tool.vcs", "tool.search", "tool.linter", "tool.editor"],
    typicalObstacles: ["scope-creep", "api-drift", "log-gaps"],
  },
  {
    id: "invest.flake",
    name: "Flaky Investigation",
    family: "investigation",
    complexity: 0.6,
    contextNeeds: 0.5,
    verificationStyle: "runtime-check",
    typicalTools: ["tool.shell", "tool.test-runner", "tool.search", "tool.browser"],
    typicalObstacles: [
      "intermittent-repro",
      "log-gaps",
      "flaky-test",
      "noisy-stacktrace",
    ],
  },
  {
    id: "maint.migration",
    name: "Migration",
    family: "maintenance",
    complexity: 0.7,
    contextNeeds: 0.8,
    verificationStyle: "tests",
    typicalTools: [
      "tool.editor",
      "tool.shell",
      "tool.vcs",
      "tool.search",
      "tool.test-runner",
    ],
    typicalObstacles: ["api-drift", "scope-creep", "cold-cache", "hidden-coupling"],
  },
];

/** Look up a task type by id (deterministic; undefined when unknown). */
export function findTaskType(id: string): TaskTypeDescriptor | undefined {
  return taskTypes.find((t) => t.id === id);
}
