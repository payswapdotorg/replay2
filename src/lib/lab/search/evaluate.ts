/**
 * Engineering Lab — shared evaluation core for the search engines (B2).
 *
 * A candidate (organization + model occupancy + capability allocation) is
 * evaluated over per-seed instance batches through the LabExecutionPort.
 * When no instances are supplied (L0 analytic mode) the evaluation falls
 * back to the port's closed-form analytic surface.
 *
 * Scoring per dimension: success rate (judged by the world engine's
 * acceptance check — the canonical judge), mean quality, mean latencyMs,
 * mean costUsd. Utility = weighted sum of normalized values:
 *   success/quality are already 0..1;
 *   latency normalizes against workload.latencySlaMinutes × 60000;
 *   cost normalizes against workload.budgetUsdPerTask;
 *   norm = clamp01(1 − value / limit).
 *
 * Utility weights derive from the workload:
 *   base { success .45, quality .25, latency .15, cost .15 };
 *   latencySlaMinutes ≤ 45 → +.10 latency (from quality);
 *   budgetUsdPerTask ≤ 1.0 → +.10 cost (from quality).
 *
 * Comparison deltas (BaselineComparison) are normalized so POSITIVE ALWAYS
 * = BETTER: success/quality → candidate − baseline; latency/cost →
 * baseline − candidate. candidateValue / baselineValue stay raw.
 */

import type {
  BaselineComparison,
  CapabilityAllocation,
  CandidateEvaluation,
  EvalDimension,
  LabExecutionPort,
  ModelOccupancy,
  OrganizationSpec,
  TaskInstance,
  TaskOutcome,
  TaskScenario,
  TaskTypeDescriptor,
  WorkloadProfile,
} from "../contracts";
import { LabError } from "../errors";
import { clamp01 } from "../rng";
import type { AnalyticOutcome, AnalyticOutcomeArgs } from "../sim/org-simulator";
import {
  EXPECTED_ACCEPTANCE_COUNT,
  EXPECTED_CONTEXT_LINES,
} from "../sim/org-simulator";
import { roundTo } from "../sim/numeric";
import { seWorldEngine } from "../worlds/se-world";

export interface TraceEntry {
  stage: string;
  detail: string;
}

/** A per-seed batch of world instances (L2 uses one batch per seed). */
export interface InstanceSet {
  seed: number;
  instances: TaskInstance[];
}

export interface DimensionScores {
  success: number;
  quality: number;
  latency: number;
  cost: number;
}

export interface RawEvaluation {
  scores: DimensionScores;
  utility: number;
  perInstance: { instanceId: string; seed: number; outcome: TaskOutcome }[];
}

export const EVAL_DIMENSIONS: readonly EvalDimension[] = ["success", "quality", "latency", "cost"] as const;

/** A port that can also produce closed-form (L0 analytic) expectations. */
export interface AnalyticExecutionPort extends LabExecutionPort {
  analyticOutcome(args: AnalyticOutcomeArgs): AnalyticOutcome;
}

export function asAnalyticPort(port: LabExecutionPort): AnalyticExecutionPort | null {
  const candidate = port as AnalyticExecutionPort;
  return typeof candidate.analyticOutcome === "function" ? candidate : null;
}

export function deriveUtilityWeights(workload: WorkloadProfile): Record<EvalDimension, number> {
  const weights: Record<EvalDimension, number> = {
    success: 0.45,
    quality: 0.25,
    latency: 0.15,
    cost: 0.15,
  };
  if (workload.latencySlaMinutes <= 45) {
    weights.latency = roundTo(weights.latency + 0.1, 6);
    weights.quality = roundTo(weights.quality - 0.1, 6);
  }
  if (workload.budgetUsdPerTask <= 1.0) {
    weights.cost = roundTo(weights.cost + 0.1, 6);
    weights.quality = roundTo(weights.quality - 0.1, 6);
  }
  return weights;
}

export function normalizeDimension(
  dimension: EvalDimension,
  value: number,
  workload: WorkloadProfile,
): number {
  if (dimension === "success" || dimension === "quality") {
    return clamp01(value);
  }
  const limit =
    dimension === "latency"
      ? workload.latencySlaMinutes * 60_000
      : workload.budgetUsdPerTask;
  if (!(limit > 0)) {
    return 0;
  }
  return clamp01(1 - value / limit);
}

export function utilityFromScores(
  scores: DimensionScores,
  weights: Record<EvalDimension, number>,
  workload: WorkloadProfile,
): number {
  return (
    weights.success * clamp01(scores.success) +
    weights.quality * clamp01(scores.quality) +
    weights.latency * normalizeDimension("latency", scores.latency, workload) +
    weights.cost * normalizeDimension("cost", scores.cost, workload)
  );
}

export interface EvaluationArgs {
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  taskType: TaskTypeDescriptor;
  workload: WorkloadProfile;
  scenario: TaskScenario;
  /** Empty batches (or all-empty) => L0 analytic mode. */
  instanceSets: InstanceSet[];
  port: LabExecutionPort;
  weights: Record<EvalDimension, number>;
}

export async function evaluateOrganization(args: EvaluationArgs): Promise<RawEvaluation> {
  const totalInstances = args.instanceSets.reduce((n, set) => n + set.instances.length, 0);

  if (totalInstances === 0) {
    // L0 analytic: closed-form expectations, no instance simulation.
    const analytic = asAnalyticPort(args.port);
    if (!analytic) {
      throw new LabError("Analytic (L0) evaluation requires a port with an analyticOutcome surface (org-sim)");
    }
    const outcome = analytic.analyticOutcome({
      organization: args.organization,
      occupancy: args.occupancy,
      capabilities: args.capabilities,
      taskType: args.taskType,
      difficulty: args.scenario.difficultyBase,
      acceptanceCount: EXPECTED_ACCEPTANCE_COUNT,
      contextLines: EXPECTED_CONTEXT_LINES,
    });
    const scores: DimensionScores = {
      success: outcome.successProbability,
      quality: outcome.quality,
      latency: outcome.latencyMs,
      cost: outcome.costUsd,
    };
    return {
      scores,
      utility: utilityFromScores(scores, args.weights, args.workload),
      perInstance: [],
    };
  }

  let successSum = 0;
  let qualitySum = 0;
  let latencySum = 0;
  let costSum = 0;
  let count = 0;
  const perInstance: RawEvaluation["perInstance"] = [];
  for (const set of args.instanceSets) {
    for (const instance of set.instances) {
      const outcome = await args.port.executeTask({
        instance,
        organization: args.organization,
        occupancy: args.occupancy,
        capabilities: args.capabilities,
        seed: set.seed,
      });
      // The world engine is the canonical judge of success.
      const judged = seWorldEngine.checkAcceptance(outcome, instance);
      successSum += judged ? 1 : 0;
      qualitySum += outcome.quality;
      latencySum += outcome.latencyMs;
      costSum += outcome.costUsd;
      count += 1;
      perInstance.push({ instanceId: instance.id, seed: set.seed, outcome });
    }
  }
  const scores: DimensionScores = {
    success: successSum / count,
    quality: qualitySum / count,
    latency: latencySum / count,
    cost: costSum / count,
  };
  return {
    scores,
    utility: utilityFromScores(scores, args.weights, args.workload),
    perInstance,
  };
}

/** Serialize a raw evaluation into the artifact's CandidateEvaluation shape. */
export function toCandidateEvaluation(
  candidateId: string,
  organization: OrganizationSpec,
  occupancy: ModelOccupancy[],
  capabilities: CapabilityAllocation[],
  raw: RawEvaluation,
): CandidateEvaluation {
  return {
    candidateId,
    organization,
    occupancy,
    capabilities,
    scores: [
      { dimension: "success", value: roundTo(raw.scores.success, 6) },
      { dimension: "quality", value: roundTo(raw.scores.quality, 6) },
      { dimension: "latency", value: roundTo(raw.scores.latency, 6), unit: "ms" },
      { dimension: "cost", value: roundTo(raw.scores.cost, 6), unit: "usd" },
    ],
    perInstance: raw.perInstance,
    utility: roundTo(raw.utility, 6),
  };
}

export function scoreOf(evaluation: CandidateEvaluation, dimension: EvalDimension): number {
  return evaluation.scores.find((s) => s.dimension === dimension)?.value ?? 0;
}

/**
 * Baseline comparison across the four dimensions. Raw values on both sides;
 * the delta is oriented so positive ALWAYS means the candidate is better.
 */
export function buildComparison(
  candidate: CandidateEvaluation,
  baseline: CandidateEvaluation,
): BaselineComparison[] {
  return EVAL_DIMENSIONS.map((dimension) => {
    const candidateValue = scoreOf(candidate, dimension);
    const baselineValue = scoreOf(baseline, dimension);
    const delta =
      dimension === "latency" || dimension === "cost"
        ? baselineValue - candidateValue
        : candidateValue - baselineValue;
    return {
      dimension,
      candidateValue,
      baselineValue,
      delta: roundTo(delta, 6),
    };
  });
}

/** One-line score summary for trace entries. */
export function describeScores(scores: DimensionScores): string {
  return `success ${roundTo(scores.success, 3)}, quality ${roundTo(scores.quality, 3)}, latency ${Math.round(scores.latency)}ms, cost $${roundTo(scores.cost, 4)}`;
}
