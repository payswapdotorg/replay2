/**
 * Engineering Lab catalog — Agent Body library (mission step 4, B2-owned).
 *
 * Bodies are MODEL-INDEPENDENT capability bundles: an archetype (the role the
 * body plays in an organization), a capability map (0..1 per capability id),
 * a context window and a cost tier. Model assignment happens later, in the
 * occupancy search — a body never names a model.
 *
 * Capability id namespace (shared with models.ts, the tool catalog and the
 * org simulator):
 *   cap.code, cap.plan, cap.review, cap.verify, cap.search, cap.integrate,
 *   cap.context
 *
 * Determinism laws apply: pure data, no clock, no randomness.
 */

import type { AgentBodySpec } from "../contracts";

/** Human-readable labels for the capability id namespace (for consoles). */
export const capabilityLabels: Record<string, string> = {
  "cap.code": "Implementation",
  "cap.plan": "Planning",
  "cap.review": "Code review",
  "cap.verify": "Verification",
  "cap.search": "Repository search",
  "cap.integrate": "Integration",
  "cap.context": "Context handling",
};

export const agentBodies: AgentBodySpec[] = [
  {
    id: "body.generalist",
    name: "Generalist Solo",
    archetype: "coder",
    description:
      "A balanced all-round operator that carries planning, implementation, review and verification alone — the reference single-agent shape every organization is measured against.",
    capabilities: {
      "cap.code": 0.6,
      "cap.plan": 0.6,
      "cap.review": 0.58,
      "cap.verify": 0.57,
      "cap.search": 0.6,
      "cap.integrate": 0.6,
      "cap.context": 0.62,
    },
    contextWindowTokens: 128_000,
    costTier: "standard",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.code", score: 0.61, samples: 120 },
      { capabilityId: "cap.plan", score: 0.58, samples: 90 },
      { capabilityId: "cap.review", score: 0.57, samples: 80 },
      { capabilityId: "cap.search", score: 0.6, samples: 110 },
      { capabilityId: "cap.context", score: 0.62, samples: 140 },
    ],
  },
  {
    id: "body.lead-planner",
    name: "Lead Planner",
    archetype: "planner",
    description:
      "A senior planning lead that decomposes work, routes it to implementers and integrates the results; strong at planning and context, deliberately light on hands-on code.",
    capabilities: {
      "cap.code": 0.5,
      "cap.plan": 0.85,
      "cap.review": 0.55,
      "cap.verify": 0.45,
      "cap.search": 0.6,
      "cap.integrate": 0.6,
      "cap.context": 0.8,
    },
    contextWindowTokens: 200_000,
    costTier: "premium",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.plan", score: 0.86, samples: 160 },
      { capabilityId: "cap.context", score: 0.81, samples: 150 },
      { capabilityId: "cap.integrate", score: 0.58, samples: 80 },
      { capabilityId: "cap.review", score: 0.54, samples: 70 },
      { capabilityId: "cap.search", score: 0.59, samples: 90 },
    ],
  },
  {
    id: "body.senior-coder",
    name: "Senior Implementer",
    archetype: "coder",
    description:
      "A senior implementer with top-tier code capability and deep context handling — the workhorse body for demanding implementation slots.",
    capabilities: {
      "cap.code": 0.9,
      "cap.plan": 0.6,
      "cap.review": 0.55,
      "cap.verify": 0.5,
      "cap.search": 0.5,
      "cap.integrate": 0.55,
      "cap.context": 0.75,
    },
    contextWindowTokens: 200_000,
    costTier: "premium",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.code", score: 0.91, samples: 180 },
      { capabilityId: "cap.context", score: 0.74, samples: 140 },
      { capabilityId: "cap.plan", score: 0.58, samples: 90 },
      { capabilityId: "cap.verify", score: 0.51, samples: 80 },
    ],
  },
  {
    id: "body.junior-coder",
    name: "Junior Implementer",
    archetype: "coder",
    description:
      "An economy implementer for well-scoped coding work that needs review support and shallow-context tasks to stay reliable.",
    capabilities: {
      "cap.code": 0.6,
      "cap.plan": 0.35,
      "cap.review": 0.3,
      "cap.verify": 0.35,
      "cap.search": 0.4,
      "cap.integrate": 0.35,
      "cap.context": 0.5,
    },
    contextWindowTokens: 128_000,
    costTier: "economy",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.code", score: 0.58, samples: 60 },
      { capabilityId: "cap.context", score: 0.48, samples: 50 },
      { capabilityId: "cap.search", score: 0.41, samples: 45 },
    ],
  },
  {
    id: "body.code-reviewer",
    name: "Review Gate",
    archetype: "reviewer",
    description:
      "A dedicated review gate that catches defects and convention drift before merge, with moderate depth on the verification side.",
    capabilities: {
      "cap.code": 0.5,
      "cap.plan": 0.4,
      "cap.review": 0.9,
      "cap.verify": 0.6,
      "cap.search": 0.55,
      "cap.integrate": 0.45,
      "cap.context": 0.6,
    },
    contextWindowTokens: 200_000,
    costTier: "standard",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.review", score: 0.89, samples: 170 },
      { capabilityId: "cap.verify", score: 0.61, samples: 100 },
      { capabilityId: "cap.context", score: 0.59, samples: 90 },
      { capabilityId: "cap.search", score: 0.54, samples: 70 },
    ],
  },
  {
    id: "body.test-verifier",
    name: "Test Verifier",
    archetype: "verifier",
    description:
      "A verification specialist that writes and runs the tests proving a change, with enough coding ability for fixture and harness work.",
    capabilities: {
      "cap.code": 0.5,
      "cap.plan": 0.35,
      "cap.review": 0.45,
      "cap.verify": 0.85,
      "cap.search": 0.5,
      "cap.integrate": 0.4,
      "cap.context": 0.55,
    },
    contextWindowTokens: 128_000,
    costTier: "standard",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.verify", score: 0.84, samples: 160 },
      { capabilityId: "cap.code", score: 0.49, samples: 80 },
      { capabilityId: "cap.context", score: 0.54, samples: 70 },
    ],
  },
  {
    id: "body.repo-researcher",
    name: "Repo Researcher",
    archetype: "researcher",
    description:
      "A repository researcher that locates relevant code, history and evidence fast, with light implementation ability.",
    capabilities: {
      "cap.code": 0.4,
      "cap.plan": 0.5,
      "cap.review": 0.35,
      "cap.verify": 0.45,
      "cap.search": 0.85,
      "cap.integrate": 0.4,
      "cap.context": 0.7,
    },
    contextWindowTokens: 200_000,
    costTier: "standard",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.search", score: 0.86, samples: 150 },
      { capabilityId: "cap.context", score: 0.69, samples: 130 },
      { capabilityId: "cap.plan", score: 0.49, samples: 60 },
      { capabilityId: "cap.code", score: 0.41, samples: 60 },
    ],
  },
  {
    id: "body.integrator",
    name: "Integrator",
    archetype: "integrator",
    description:
      "A merge-and-integrate specialist that lands diffs across branches and modules while keeping the review bar.",
    capabilities: {
      "cap.code": 0.6,
      "cap.plan": 0.5,
      "cap.review": 0.5,
      "cap.verify": 0.45,
      "cap.search": 0.5,
      "cap.integrate": 0.8,
      "cap.context": 0.6,
    },
    contextWindowTokens: 200_000,
    costTier: "standard",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.integrate", score: 0.79, samples: 140 },
      { capabilityId: "cap.code", score: 0.58, samples: 90 },
      { capabilityId: "cap.context", score: 0.58, samples: 80 },
      { capabilityId: "cap.review", score: 0.51, samples: 70 },
    ],
  },
  {
    id: "body.fast-ops",
    name: "Fast Ops",
    archetype: "coder",
    description:
      "An economy sprint body for quick, shallow operations — small edits, quick greps, smoke verification — where speed and cost beat depth.",
    capabilities: {
      "cap.code": 0.55,
      "cap.plan": 0.3,
      "cap.review": 0.3,
      "cap.verify": 0.5,
      "cap.search": 0.45,
      "cap.integrate": 0.35,
      "cap.context": 0.4,
    },
    contextWindowTokens: 128_000,
    costTier: "economy",
    modelAgnostic: true,
    benchmark: [
      { capabilityId: "cap.code", score: 0.54, samples: 50 },
      { capabilityId: "cap.verify", score: 0.48, samples: 45 },
      { capabilityId: "cap.search", score: 0.44, samples: 40 },
    ],
  },
];

/** Look up a body by id (deterministic; undefined when unknown). */
export function findBody(id: string): AgentBodySpec | undefined {
  return agentBodies.find((b) => b.id === id);
}
