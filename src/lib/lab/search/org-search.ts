/**
 * Engineering Lab — organization search (mission step 5, B2-owned).
 *
 * Evaluates every organization candidate from the template library against a
 * FIXED single-agent baseline (solo generalist, model.balanced-a, every
 * typical tool of the task type) over the same instance batches and seeds.
 *
 * Candidates are scored in the neutral default state (no occupancy → the
 * simulator assumes balanced-a; no capability allocation → no tool bonus):
 * this stage ranks TOPOLOGY + BODIES only. Model and tool allocation is
 * searched next (occupancy-search.ts), and the winner is re-evaluated with
 * the found allocation before the artifact is finalized.
 *
 * Utility: weighted sum of normalized dimension values (weights derived from
 * the workload — see evaluate.ts). Winner = highest utility; ties resolve to
 * the earlier candidate in template order (deterministic).
 */

import type {
  AgentBodySpec,
  CandidateEvaluation,
  EvalDimension,
  LabExecutionPort,
  LadderLevel,
  ModelDescriptor,
  ModelOccupancy,
  OrganizationSpec,
  TaskScenario,
  TaskTypeDescriptor,
  ToolDescriptor,
  WorkloadProfile,
} from "../contracts";
import { buildBaselineOrganization, buildOrgCandidates } from "../org/templates";
import { LabError } from "../errors";
import { formatSigned, roundTo } from "../sim/numeric";
import {
  deriveUtilityWeights,
  describeScores,
  evaluateOrganization,
  toCandidateEvaluation,
  type InstanceSet,
  type RawEvaluation,
  type TraceEntry,
} from "./evaluate";

export interface OrgSearchArgs {
  bodies: AgentBodySpec[];
  models: ModelDescriptor[];
  tools: ToolDescriptor[];
  taskType: TaskTypeDescriptor;
  workload: WorkloadProfile;
  scenario: TaskScenario;
  /** Empty batches (or all-empty) => L0 analytic mode. */
  instanceSets: InstanceSet[];
  ladderLevel: LadderLevel;
  port: LabExecutionPort;
}

export interface OrgSearchResult {
  candidates: CandidateEvaluation[];
  baseline: CandidateEvaluation;
  winner: CandidateEvaluation;
  trace: TraceEntry[];
  utilityWeights: Record<EvalDimension, number>;
}

export async function searchOrganizations(args: OrgSearchArgs): Promise<OrgSearchResult> {
  const weights = deriveUtilityWeights(args.workload);
  const trace: TraceEntry[] = [];
  const totalInstances = args.instanceSets.reduce((n, set) => n + set.instances.length, 0);
  const seedCount = args.instanceSets.length;
  const modeLabel =
    totalInstances === 0
      ? "analytic (no instances)"
      : `${totalInstances} instance(s) × ${seedCount} seed(s)`;

  // --- Baseline: fixed solo generalist on balanced-a with all typical tools.
  const balanced =
    args.models.find((m) => m.id === "model.balanced-a") ??
    args.models.find((m) => m.tier === "balanced");
  if (!balanced) {
    throw new LabError("Catalog error: no balanced model available for the evaluation baseline");
  }
  const knownToolIds = new Set(args.tools.map((t) => t.id));
  const baselineTools = args.taskType.typicalTools.filter((toolId) => knownToolIds.has(toolId));
  const baselineOrg = buildBaselineOrganization();
  const baselineOccupancy: ModelOccupancy[] = [{ nodeId: "n1", modelId: balanced.id }];
  const baselineRaw = await evaluateOrganization({
    organization: baselineOrg,
    occupancy: baselineOccupancy,
    capabilities: [{ nodeId: "n1", toolIds: baselineTools }],
    taskType: args.taskType,
    workload: args.workload,
    scenario: args.scenario,
    instanceSets: args.instanceSets,
    port: args.port,
    weights,
  });
  const baseline = toCandidateEvaluation(
    baselineOrg.id,
    baselineOrg,
    baselineOccupancy,
    [{ nodeId: "n1", toolIds: baselineTools }],
    baselineRaw,
  );
  trace.push({
    stage: "baseline-eval",
    detail: `Baseline ${baselineOrg.id} "${baselineOrg.name}" (body.generalist on ${balanced.id}, ${baselineTools.length} typical tools): utility ${roundTo(baselineRaw.utility, 3)} — ${describeScores(baselineRaw.scores)} — ${modeLabel}.`,
  });

  // --- Candidates: neutral default (balanced-a, no tool allocation).
  const candidateOrgs = buildOrgCandidates(args.bodies, args.taskType.id);
  if (candidateOrgs.length === 0) {
    throw new LabError("No candidate organizations could be assembled from the body library");
  }
  const evaluations: CandidateEvaluation[] = [];
  const raws: RawEvaluation[] = [];
  for (const org of candidateOrgs) {
    const raw = await evaluateOrganization({
      organization: org,
      occupancy: [],
      capabilities: [],
      taskType: args.taskType,
      workload: args.workload,
      scenario: args.scenario,
      instanceSets: args.instanceSets,
      port: args.port,
      weights,
    });
    raws.push(raw);
    evaluations.push(toCandidateEvaluation(org.id, org, [], [], raw));
    trace.push({
      stage: "org-search",
      detail: `Candidate ${org.id} "${org.name}" (${org.topology}, ${org.nodes.length} node(s), neutral balanced-a default): utility ${roundTo(raw.utility, 3)} — ${describeScores(raw.scores)}.`,
    });
  }

  // --- Winner: highest utility; ties resolve to the earlier candidate.
  let winnerIndex = 0;
  for (let i = 1; i < raws.length; i++) {
    if (raws[i].utility > raws[winnerIndex].utility) {
      winnerIndex = i;
    }
  }
  const winner = evaluations[winnerIndex];
  trace.push({
    stage: "org-search",
    detail: `Winner: ${winner.candidateId} "${winner.organization.name}" utility ${roundTo(winner.utility, 3)} vs baseline ${roundTo(baseline.utility, 3)} (${formatSigned(winner.utility - baseline.utility)}) — best of ${evaluations.length} candidates at ladder L${args.ladderLevel}.`,
  });

  return {
    candidates: evaluations,
    baseline,
    winner,
    trace,
    utilityWeights: weights,
  };
}
