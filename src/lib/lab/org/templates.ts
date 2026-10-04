/**
 * Engineering Lab — organization templates (mission step 5, B2-owned).
 *
 * `buildOrgCandidates` assembles the model-independent organization search
 * space from fixed templates over the body library. Node ids are "n1".."nk",
 * roles are human-readable, edges are typed delegation / review / handoff and
 * hierarchy is expressed via `reportsTo`. Every org id is stable
 * ("org.<template>-<anchor body>") and only references real body ids.
 *
 * The evaluation baseline (a fixed solo generalist with balanced-a and all
 * typical tools) is also defined here — the org search scores it identically
 * to the candidates.
 */

import { findTaskType } from "../catalog/task-types";
import { LabError } from "../errors";
import type { AgentBodySpec, OrgEdge, OrgNode, OrganizationSpec } from "../contracts";

function node(id: string, bodyId: string, role: string, reportsTo?: string): OrgNode {
  return reportsTo === undefined
    ? { id, bodyId, role }
    : { id, bodyId, role, reportsTo };
}

function edge(from: string, to: string, kind: OrgEdge["kind"]): OrgEdge {
  return { from, to, kind };
}

// ---------------------------------------------------------------------------
// Base templates (every task family; filtered by body availability).
// ---------------------------------------------------------------------------

const BASE_TEMPLATES: OrganizationSpec[] = [
  {
    id: "org.single-generalist",
    name: "Solo Generalist",
    topology: "single",
    nodes: [node("n1", "body.generalist", "Solo generalist")],
    edges: [],
    notes: "One balanced body carries plan, code, review and verify alone.",
  },
  {
    id: "org.single-senior-coder",
    name: "Solo Senior Implementer",
    topology: "single",
    nodes: [node("n1", "body.senior-coder", "Solo senior implementer")],
    edges: [],
    notes: "One strong implementer; planning and verification stay shallow.",
  },
  {
    id: "org.pipeline-2-senior-coder",
    name: "Pipeline: Implement → Review",
    topology: "pipeline",
    nodes: [
      node("n1", "body.senior-coder", "Implementer"),
      node("n2", "body.code-reviewer", "Reviewer"),
    ],
    edges: [edge("n1", "n2", "handoff"), edge("n2", "n1", "review")],
    notes: "The implementer hands off to a dedicated review gate that pushes feedback back.",
  },
  {
    id: "org.pipeline-3-senior-coder",
    name: "Pipeline: Research → Implement → Verify",
    topology: "pipeline",
    nodes: [
      node("n1", "body.repo-researcher", "Researcher"),
      node("n2", "body.senior-coder", "Implementer"),
      node("n3", "body.test-verifier", "Verifier"),
    ],
    edges: [
      edge("n1", "n2", "handoff"),
      edge("n2", "n3", "handoff"),
      edge("n3", "n2", "review"),
    ],
    notes: "Full delivery pipeline: evidence first, then implementation, then proof.",
  },
  {
    id: "org.hierarchical-3-lead-planner",
    name: "Hierarchy: Lead + Implementer + Verifier",
    topology: "hierarchical",
    nodes: [
      node("n1", "body.lead-planner", "Lead planner"),
      node("n2", "body.senior-coder", "Implementer", "n1"),
      node("n3", "body.test-verifier", "Verifier", "n1"),
    ],
    edges: [
      edge("n1", "n2", "delegation"),
      edge("n1", "n3", "delegation"),
      edge("n2", "n3", "handoff"),
    ],
    notes: "A planning lead delegates implementation and verification and owns integration.",
  },
  {
    id: "org.hub-and-spoke-4-lead-planner",
    name: "Hub: Lead + Research + Junior + Review",
    topology: "hub-and-spoke",
    nodes: [
      node("n1", "body.lead-planner", "Hub lead"),
      node("n2", "body.repo-researcher", "Research spoke", "n1"),
      node("n3", "body.junior-coder", "Junior implementer spoke", "n1"),
      node("n4", "body.code-reviewer", "Review spoke", "n1"),
    ],
    edges: [
      edge("n1", "n2", "delegation"),
      edge("n1", "n3", "delegation"),
      edge("n1", "n4", "delegation"),
      edge("n2", "n3", "handoff"),
      edge("n3", "n4", "handoff"),
    ],
    notes: "The lead routes work through research, a cheap implementation spoke and a review gate.",
  },
  {
    id: "org.pipeline-3-economy",
    name: "Economy Pipeline: Scout → Junior → Review",
    topology: "pipeline",
    nodes: [
      node("n1", "body.fast-ops", "Scout"),
      node("n2", "body.junior-coder", "Junior implementer"),
      node("n3", "body.code-reviewer", "Review gate"),
    ],
    edges: [
      edge("n1", "n2", "handoff"),
      edge("n2", "n3", "handoff"),
      edge("n3", "n2", "review"),
    ],
    notes: "The economy end: a fast scout locates the work, a junior lands it, a gate reviews it.",
  },
];

// ---------------------------------------------------------------------------
// Family-conditional variants (one extra candidate per task family).
// ---------------------------------------------------------------------------

const SINGLE_CODE_REVIEWER: OrganizationSpec = {
  id: "org.single-code-reviewer",
  name: "Solo Review Gate",
  topology: "single",
  nodes: [node("n1", "body.code-reviewer", "Solo review gate")],
  edges: [],
  notes: "A dedicated reviewer working the review queue alone.",
};

const SINGLE_REPO_RESEARCHER: OrganizationSpec = {
  id: "org.single-repo-researcher",
  name: "Solo Researcher",
  topology: "single",
  nodes: [node("n1", "body.repo-researcher", "Solo researcher")],
  edges: [],
  notes: "A dedicated researcher carrying investigation work alone.",
};

const PIPELINE_2_JUNIOR: OrganizationSpec = {
  id: "org.pipeline-2-junior-coder",
  name: "Economy Pipeline: Junior → Review",
  topology: "pipeline",
  nodes: [
    node("n1", "body.junior-coder", "Junior implementer"),
    node("n2", "body.code-reviewer", "Reviewer"),
  ],
  edges: [edge("n1", "n2", "handoff"), edge("n2", "n1", "review")],
  notes: "The economy implementation shape: cheap hands behind a real review gate.",
};

const FAMILY_VARIANTS: Record<string, OrganizationSpec> = {
  implementation: PIPELINE_2_JUNIOR,
  maintenance: PIPELINE_2_JUNIOR,
  review: SINGLE_CODE_REVIEWER,
  investigation: SINGLE_REPO_RESEARCHER,
};

// ---------------------------------------------------------------------------
// Public builders.
// ---------------------------------------------------------------------------

/**
 * Assemble the organization candidate list for a task type: the seven base
 * templates plus one family-conditional variant, capped at eight orgs.
 * Candidates whose bodies are all present in `bodies` are returned in a
 * fixed order; templates referencing unknown bodies are skipped defensively.
 */
export function buildOrgCandidates(bodies: AgentBodySpec[], taskTypeId: string): OrganizationSpec[] {
  const taskType = findTaskType(taskTypeId);
  if (!taskType) {
    throw new LabError(`Unknown taskTypeId "${taskTypeId}" — cannot assemble organization candidates`);
  }
  const knownBodies = new Set(bodies.map((b) => b.id));
  const variant = FAMILY_VARIANTS[taskType.family];
  const templates = variant === undefined ? BASE_TEMPLATES : [...BASE_TEMPLATES, variant];
  return templates.filter((org) => org.nodes.every((n) => knownBodies.has(n.bodyId)));
}

/**
 * The fixed evaluation baseline: one generalist body, model.balanced-a on the
 * node (materialized by the org search) and every typical tool of the task
 * type. The org search evaluates it exactly like the candidates.
 */
export function buildBaselineOrganization(): OrganizationSpec {
  return {
    id: "org.baseline-solo",
    name: "Baseline — Solo Generalist",
    topology: "single",
    nodes: [node("n1", "body.generalist", "Solo generalist")],
    edges: [],
    notes: "Fixed evaluation baseline: generalist body, balanced-a model, all typical tools.",
  };
}
