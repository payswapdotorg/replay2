/**
 * Engineering Lab — run engine + the replaceable simulation/learning ladder
 * (mission step 7, B2-owned).
 *
 * `executeLabRun` is PURE and DETERMINISTIC: given the same spec it returns
 * byte-identical artifacts (no clock, no Math.random; timestamps exist only
 * at the Prisma persistence edge, handled by the API routes).
 *
 * The ladder (the replaceable simulation depth — a later wave can swap the
 * L1/L2 internals behind the same artifact shape):
 *  - L0 "analytic": no per-instance outcomes. Scores are closed-form
 *    expectations from scenario.difficultyBase and the capability/model math
 *    (perInstance: [] everywhere). Occupancy is searched analytically too.
 *  - L1 "scenario-sim": instances = seWorldEngine.generateInstances(scenario,
 *    min(instanceCount, 6), primarySeed); baseline + candidates +
 *    occupancy-winner evaluated per-instance via the port (OrgSimulator).
 *  - L2 "robustness": L1 across ALL seeds (spec seeds, cap 3) plus a
 *    perturbation pass per seed (difficulty +0.08, obstacle severity ×1.25,
 *    one stressed batch per perturbation mode). Builds the RobustnessReport
 *    from per-seed means over nominal + stressed outcomes of the final
 *    winner. artifact.robustness is present only at L2.
 *
 * Seeds: spec.seeds when non-empty; otherwise derived deterministically as
 * [hashSeed(scenarioId, workloadId) % 997, +1, +2]. The RESOLVED seeds are
 * recorded in artifact.spec.seeds so every artifact is reproducible.
 */

import { agentBodies } from "../catalog/agent-bodies";
import { modelDescriptors, toolDescriptors } from "../catalog/models";
import { seWorldScenarios } from "../catalog/se-world";
import { findTaskType, taskTypes } from "../catalog/task-types";
import { workloadProfiles } from "../catalog/workload-profiles";
import type {
  CapabilityAllocation,
  LabRunSpec,
  ModelOccupancy,
  OrganizationSpec,
  RecommendationArtifact,
  RobustnessReport,
  RunArtifact,
  TaskInstance,
  TaskOutcome,
  TaskScenario,
  TaskTypeDescriptor,
  WorkloadProfile,
  EvalDimension,
  BaselineComparison,
} from "../contracts";
import { LabError } from "../errors";
import { clamp01, hashSeed } from "../rng";
import { OrgSimulator } from "../sim/org-simulator";
import { formatSigned, populationVariance, roundTo } from "../sim/numeric";
import { seWorldEngine } from "../worlds/se-world";
import {
  buildComparison,
  EVAL_DIMENSIONS,
  evaluateOrganization,
  toCandidateEvaluation,
  type DimensionScores,
  type InstanceSet,
  type TraceEntry,
} from "../search/evaluate";
import { searchOrganizations } from "../search/org-search";
import { searchOccupancy } from "../search/occupancy-search";

export interface LabRunResult {
  artifact: RunArtifact;
  /** runId is "" here — the persisting route assigns the database id. */
  recommendation: RecommendationArtifact;
}

/** Deterministic seed derivation when the spec carries no seeds. */
function deriveDefaultSeeds(spec: LabRunSpec): number[] {
  const base = hashSeed(spec.scenarioId, spec.workloadId) % 997;
  return [base, base + 1, base + 2];
}

/** Perturbation transform: difficulty +0.08, obstacle severity ×1.25. */
function perturbInstances(instances: TaskInstance[], mode: string): TaskInstance[] {
  return instances.map((instance) => ({
    ...instance,
    id: `${instance.id}~${mode}`,
    difficulty: clamp01(roundTo(instance.difficulty + 0.08, 4)),
    obstacles: instance.obstacles.map((obstacle) => ({
      ...obstacle,
      severity: clamp01(roundTo(obstacle.severity * 1.25, 4)),
    })),
  }));
}

function dimensionScale(dimension: EvalDimension, workload: WorkloadProfile): number {
  if (dimension === "latency") {
    return workload.latencySlaMinutes * 60_000;
  }
  if (dimension === "cost") {
    return workload.budgetUsdPerTask;
  }
  return 1;
}

function isWorst(dimension: EvalDimension, value: number, other: number): boolean {
  // Worst = lowest success/quality, highest latency/cost.
  return dimension === "latency" || dimension === "cost" ? value > other : value < other;
}

interface RobustnessArgs {
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  scenario: TaskScenario;
  workload: WorkloadProfile;
  instanceSets: InstanceSet[];
  port: OrgSimulator;
}

async function buildRobustnessReport(args: RobustnessArgs): Promise<RobustnessReport> {
  const perSeedMeans: { seed: number; scores: DimensionScores }[] = [];
  for (const set of args.instanceSets) {
    const outcomes: { outcome: TaskOutcome; instance: TaskInstance }[] = [];
    for (const instance of set.instances) {
      outcomes.push({
        instance,
        outcome: await args.port.executeTask({
          instance,
          organization: args.organization,
          occupancy: args.occupancy,
          capabilities: args.capabilities,
          seed: set.seed,
        }),
      });
    }
    for (const mode of args.scenario.perturbations) {
      for (const instance of perturbInstances(set.instances, mode)) {
        outcomes.push({
          instance,
          outcome: await args.port.executeTask({
            instance,
            organization: args.organization,
            occupancy: args.occupancy,
            capabilities: args.capabilities,
            seed: set.seed,
          }),
        });
      }
    }
    const count = Math.max(1, outcomes.length);
    perSeedMeans.push({
      seed: set.seed,
      scores: {
        success: outcomes.reduce((sum, o) => sum + (seWorldEngine.checkAcceptance(o.outcome, o.instance) ? 1 : 0), 0) / count,
        quality: outcomes.reduce((sum, o) => sum + o.outcome.quality, 0) / count,
        latency: outcomes.reduce((sum, o) => sum + o.outcome.latencyMs, 0) / count,
        cost: outcomes.reduce((sum, o) => sum + o.outcome.costUsd, 0) / count,
      },
    });
  }

  const valuesFor = (dimension: EvalDimension): number[] =>
    perSeedMeans.map((m) => m.scores[dimension]);

  const seedVariance = EVAL_DIMENSIONS.map((dimension) => ({
    dimension,
    variance: roundTo(populationVariance(valuesFor(dimension)), 8),
  }));

  const worstCase = EVAL_DIMENSIONS.map((dimension) => {
    const values = valuesFor(dimension);
    const worst = values.reduce((acc, v) => (isWorst(dimension, v, acc) ? v : acc), values[0] ?? 0);
    return { dimension, value: roundTo(worst, 6) };
  });

  const uncertainty = EVAL_DIMENSIONS.map((dimension) => {
    const values = valuesFor(dimension);
    const low = values.length > 0 ? Math.min(...values) : 0;
    const high = values.length > 0 ? Math.max(...values) : 0;
    const scale = dimensionScale(dimension, args.workload);
    const normalizedSpread = scale > 0 ? clamp01((high - low) / scale) : 0;
    const confidence = clamp01(0.5 + 0.5 * (1 - normalizedSpread));
    return {
      dimension,
      low: roundTo(low, 6),
      high: roundTo(high, 6),
      confidence: roundTo(confidence, 6),
    };
  });

  return {
    seedsEvaluated: perSeedMeans.length,
    perturbations: [...args.scenario.perturbations],
    seedVariance,
    worstCase,
    uncertainty,
  };
}

export async function executeLabRun(spec: LabRunSpec): Promise<LabRunResult> {
  // --- Validate ids against the frozen catalog.
  const workload = workloadProfiles.find((w) => w.id === spec.workloadId);
  if (!workload) {
    throw new LabError(
      `Unknown workloadId "${spec.workloadId}" — known: ${workloadProfiles.map((w) => w.id).join(", ")}`,
    );
  }
  const taskType = findTaskType(spec.taskTypeId);
  if (!taskType) {
    throw new LabError(
      `Unknown taskTypeId "${spec.taskTypeId}" — known: ${taskTypes.map((t) => t.id).join(", ")}`,
    );
  }
  const scenario = seWorldScenarios.find((s) => s.id === spec.scenarioId);
  if (!scenario) {
    throw new LabError(
      `Unknown scenarioId "${spec.scenarioId}" — known: ${seWorldScenarios.map((s) => s.id).join(", ")}`,
    );
  }
  if (scenario.taskTypeId !== taskType.id) {
    throw new LabError(
      `Scenario "${scenario.id}" belongs to taskType "${scenario.taskTypeId}" but spec.taskTypeId is "${taskType.id}"`,
    );
  }
  if (![0, 1, 2].includes(spec.ladderLevel)) {
    throw new LabError(`ladderLevel must be 0, 1 or 2 (got ${spec.ladderLevel})`);
  }
  if (spec.seeds.length > 5) {
    throw new LabError(`seeds must contain at most 5 entries (got ${spec.seeds.length})`);
  }

  // --- Resolve seeds (recorded in the artifact for reproducibility).
  const seeds = spec.seeds.length > 0 ? [...spec.seeds] : deriveDefaultSeeds(spec);
  const primarySeed = seeds[0];

  // --- Instance batches per ladder level.
  const instanceCap = Math.min(scenario.instanceCount, 6);
  let instanceSets: InstanceSet[] = [];
  if (spec.ladderLevel === 1) {
    instanceSets = [
      { seed: primarySeed, instances: seWorldEngine.generateInstances(scenario, instanceCap, primarySeed) },
    ];
  } else if (spec.ladderLevel === 2) {
    instanceSets = seeds.slice(0, 3).map((seed) => ({
      seed,
      instances: seWorldEngine.generateInstances(scenario, instanceCap, seed),
    }));
  }

  const port = new OrgSimulator();

  // --- Stage: world-load.
  const trace: TraceEntry[] = [];
  const worldDetail = `Loaded scenario "${scenario.name}" (${scenario.id}, taskType ${taskType.id}, difficultyBase ${roundTo(scenario.difficultyBase, 2)}, perturbations [${scenario.perturbations.join(", ")}])`;
  if (spec.ladderLevel === 0) {
    trace.push({
      stage: "world-load",
      detail: `${worldDetail} at ladder L0 — analytic mode, no instance simulation.`,
    });
  } else if (spec.ladderLevel === 1) {
    trace.push({
      stage: "world-load",
      detail: `${worldDetail} at ladder L1 — generated ${instanceCap} instance(s) from primary seed ${primarySeed}.`,
    });
  } else {
    const seedList = instanceSets.map((set) => set.seed).join(", ");
    trace.push({
      stage: "world-load",
      detail: `${worldDetail} at ladder L2 — ${instanceCap} instance(s) × ${instanceSets.length} seed(s) [${seedList}] + perturbation pass (${scenario.perturbations.length} mode(s) per seed).`,
    });
  }

  // --- Stage: baseline-eval + org-search.
  const orgSearch = await searchOrganizations({
    bodies: agentBodies,
    models: modelDescriptors,
    tools: toolDescriptors,
    taskType,
    workload,
    scenario,
    instanceSets,
    ladderLevel: spec.ladderLevel,
    port,
  });
  trace.push(...orgSearch.trace);

  // --- Stage: occupancy-search (models + tools on the winner).
  const occupancySearch = await searchOccupancy({
    organization: orgSearch.winner.organization,
    bodies: agentBodies,
    models: modelDescriptors,
    taskType,
    workload,
    scenario,
    instanceSets,
    port,
    weights: orgSearch.utilityWeights,
    preOccupancyUtility: orgSearch.winner.utility,
  });
  trace.push(...occupancySearch.trace);

  // --- Final winner evaluation WITH the searched occupancy + capabilities.
  const winnerRaw = await evaluateOrganization({
    organization: orgSearch.winner.organization,
    occupancy: occupancySearch.occupancy,
    capabilities: occupancySearch.capabilities,
    taskType,
    workload,
    scenario,
    instanceSets,
    port,
    weights: orgSearch.utilityWeights,
  });
  const winner = toCandidateEvaluation(
    orgSearch.winner.candidateId,
    orgSearch.winner.organization,
    occupancySearch.occupancy,
    occupancySearch.capabilities,
    winnerRaw,
  );

  // --- Comparison vs the fixed baseline (positive delta = better).
  const comparison: BaselineComparison[] = buildComparison(winner, orgSearch.baseline);

  // --- Stage: robustness (L2 only).
  let robustness: RobustnessReport | undefined;
  if (spec.ladderLevel === 2) {
    robustness = await buildRobustnessReport({
      organization: winner.organization,
      occupancy: winner.occupancy,
      capabilities: winner.capabilities,
      scenario,
      workload,
      instanceSets,
      port,
    });
    const successUncertainty = robustness.uncertainty.find((u) => u.dimension === "success");
    const worstSuccess = robustness.worstCase.find((w) => w.dimension === "success")?.value ?? 0;
    const perSeedInstances = instanceSets[0]?.instances.length ?? 0;
    const stressedTotal =
      instanceSets.length * (perSeedInstances + scenario.perturbations.length * perSeedInstances);
    trace.push({
      stage: "robustness",
      detail: `Robustness: winner re-executed across ${robustness.seedsEvaluated} seed(s) × (${perSeedInstances} nominal + ${scenario.perturbations.length} mode(s) × ${perSeedInstances} stressed) = ${stressedTotal} executions; worst-case success ${roundTo(worstSuccess, 3)}, success confidence ${successUncertainty?.confidence ?? 0}.`,
    });
  }

  // --- Ladder note.
  const ladderNote =
    spec.ladderLevel === 0
      ? "L0 analytic — closed-form expectation, no instance simulation"
      : spec.ladderLevel === 1
        ? `L1 scenario-sim — ${instanceSets.reduce((n, s) => n + s.instances.length, 0)} instance(s) × 1 seed (primary ${primarySeed}) via the org-sim port`
        : `L2 robustness — ${instanceSets.reduce((n, s) => n + s.instances.length, 0)} instance(s) × ${instanceSets.length} seed(s) + perturbation pass (${scenario.perturbations.length} mode(s)) via the org-sim port`;

  const artifact: RunArtifact = {
    spec: {
      workloadId: spec.workloadId,
      taskTypeId: spec.taskTypeId,
      scenarioId: spec.scenarioId,
      ladderLevel: spec.ladderLevel,
      seeds,
    },
    search: {
      candidatesEvaluated: orgSearch.candidates.length,
      ladderNote,
      trace,
    },
    baseline: orgSearch.baseline,
    winner,
    comparison,
    ...(robustness ? { robustness } : {}),
    utilityWeights: orgSearch.utilityWeights,
  };

  return { artifact, recommendation: buildRecommendation(spec.ladderLevel, artifact, robustness) };
}

function buildRecommendation(
  ladderLevel: number,
  artifact: RunArtifact,
  robustness: RobustnessReport | undefined,
): RecommendationArtifact {
  const { winner, baseline, comparison } = artifact;
  const organization = winner.organization;

  const topGains = [...comparison].sort((a, b) => b.delta - a.delta).slice(0, 2);
  const gainsText =
    topGains.length > 0
      ? topGains.map((g) => `${g.dimension} ${formatSigned(g.delta)}`).join(", ")
      : "no positive gains over the baseline";
  const occupancyCounts = new Map<string, number>();
  for (const o of winner.occupancy) {
    occupancyCounts.set(o.modelId, (occupancyCounts.get(o.modelId) ?? 0) + 1);
  }
  const occupancySummary =
    winner.occupancy.length > 0
      ? [...occupancyCounts.entries()].map(([modelId, count]) => `${count}× ${modelId}`).join(", ")
      : "default balanced-a on every node";
  const seedsEvaluated = robustness?.seedsEvaluated ?? (ladderLevel === 1 ? 1 : 0);
  const evidence =
    winner.perInstance.length > 0
      ? `${winner.perInstance.length} simulated instances across ${seedsEvaluated} seed(s)`
      : "closed-form analytic expectations (no instance simulation)";
  const rationale =
    `Winner: ${organization.name} (${organization.topology}, ${organization.nodes.length} node(s)) — top gains vs the solo-generalist baseline: ${gainsText}. ` +
    `Occupancy: ${occupancySummary}. ` +
    `Expected utility ${roundTo(winner.utility, 3)} vs baseline ${roundTo(baseline.utility, 3)} (${formatSigned(winner.utility - baseline.utility)}) from ${evidence} at ladder L${ladderLevel}.`;

  const successConfidence =
    robustness?.uncertainty.find((u) => u.dimension === "success")?.confidence ?? 0;
  const confidence = clamp01(0.45 + 0.15 * ladderLevel + 0.2 * successConfidence);

  const caveats = [
    "Single-world evidence: se.repo-maintenance only",
    "Fixture-mode simulation (org-sim): deterministic expectations, not runtime evidence",
  ];
  if (ladderLevel === 0) {
    caveats.push("Analytic ladder only — confirm at L2 before execution");
  } else if (ladderLevel === 1) {
    caveats.push("Single-seed simulation — confirm robustness at L2 before execution");
  }

  return {
    runId: "", // assigned by the persisting API route
    organization,
    occupancy: winner.occupancy,
    capabilities: winner.capabilities,
    rationale,
    expectedGains: comparison,
    confidence: roundTo(confidence, 6),
    caveats,
  };
}
