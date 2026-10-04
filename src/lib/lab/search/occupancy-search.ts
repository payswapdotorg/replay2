/**
 * Engineering Lab — model occupancy + capability allocation search
 * (mission step 6, B2-owned).
 *
 * Deterministic greedy + local search over the winning organization:
 *  1. Capability allocation first (fixed): per-node tools = archetype tool
 *     set ∩ taskType.typicalTools (full archetype set when the intersection
 *     is empty) — the exact rule the simulator's tool bonus checks.
 *  2. Start every node on model.balanced-a.
 *  3. Greedy upgrades: repeatedly apply the highest-utility-gain single
 *     (node → frontier model) change that keeps expected cost within
 *     workload.budgetUsdPerTask, until no beneficial upgrade remains.
 *     (This wave's policy considers frontier-a / frontier-b upgrades and
 *     fast-a swaps per the B2 spec; balanced-b stays catalog-resident for
 *     later policies.)
 *  4. Local swaps: 3 passes trying model.fast-a on each node (in node
 *     order); a swap is KEPT only when utility does not regress — i.e.
 *     fast-a lands on the low-impact nodes.
 *
 * The run engine re-evaluates the winner WITH the found occupancy +
 * capabilities afterwards; that becomes the final winner evaluation while
 * the pre-occupancy evaluation is preserved in the trace.
 */

import type {
  AgentBodySpec,
  CapabilityAllocation,
  EvalDimension,
  LabExecutionPort,
  ModelDescriptor,
  ModelOccupancy,
  ModelTier,
  OrganizationSpec,
  TaskScenario,
  TaskTypeDescriptor,
  WorkloadProfile,
} from "../contracts";
import { LabError } from "../errors";
import { requiredToolsForArchetype } from "../sim/org-simulator";
import { formatSigned, roundTo } from "../sim/numeric";
import {
  deriveUtilityWeights,
  evaluateOrganization,
  type InstanceSet,
  type TraceEntry,
} from "./evaluate";

const TIER_RANK: Record<ModelTier, number> = { fast: 0, balanced: 1, frontier: 2 };

export interface OccupancySearchArgs {
  /** The winning organization from the org search. */
  organization: OrganizationSpec;
  bodies: AgentBodySpec[];
  models: ModelDescriptor[];
  taskType: TaskTypeDescriptor;
  workload: WorkloadProfile;
  scenario: TaskScenario;
  instanceSets: InstanceSet[];
  port: LabExecutionPort;
  /** Shared utility weights (defaults to deriving them from the workload). */
  weights?: Record<EvalDimension, number>;
  /** Winner utility before occupancy (org-search stage) for trace provenance. */
  preOccupancyUtility?: number;
}

export interface OccupancySearchResult {
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  trace: TraceEntry[];
}

/** Per-node tool allocation by archetype (∩ typical tools, full fallback). */
export function assignArchetypeTools(
  organization: OrganizationSpec,
  bodies: AgentBodySpec[],
  taskType: TaskTypeDescriptor,
): CapabilityAllocation[] {
  return organization.nodes.map((orgNode) => {
    const body = bodies.find((b) => b.id === orgNode.bodyId);
    const toolIds =
      body === undefined ? [] : requiredToolsForArchetype(body.archetype, taskType);
    return { nodeId: orgNode.id, toolIds };
  });
}

function describeOccupancy(occupancy: ModelOccupancy[]): string {
  return occupancy.map((o) => `${o.nodeId}→${o.modelId}`).join(", ");
}

export async function searchOccupancy(args: OccupancySearchArgs): Promise<OccupancySearchResult> {
  const weights = args.weights ?? deriveUtilityWeights(args.workload);
  const trace: TraceEntry[] = [];

  const evaluate = async (
    occupancy: ModelOccupancy[],
    capabilities: CapabilityAllocation[],
  ) =>
    evaluateOrganization({
      organization: args.organization,
      occupancy,
      capabilities,
      taskType: args.taskType,
      workload: args.workload,
      scenario: args.scenario,
      instanceSets: args.instanceSets,
      port: args.port,
      weights,
    });

  // 1. Fixed capability allocation by node archetype.
  const capabilities = assignArchetypeTools(args.organization, args.bodies, args.taskType);
  const toolCount = capabilities.reduce((n, c) => n + c.toolIds.length, 0);

  // 2. Start on balanced-a everywhere.
  const balanced =
    args.models.find((m) => m.id === "model.balanced-a") ??
    args.models.find((m) => m.tier === "balanced");
  if (!balanced) {
    throw new LabError("Catalog error: no balanced model available to start occupancy search");
  }
  let occupancy: ModelOccupancy[] = args.organization.nodes.map((orgNode) => ({
    nodeId: orgNode.id,
    modelId: balanced.id,
  }));
  let currentUtility = (await evaluate(occupancy, capabilities)).utility;
  trace.push({
    stage: "occupancy-search",
    detail: `Start: all ${args.organization.nodes.length} node(s) on ${balanced.id} with ${toolCount} archetype-matched tool allocation(s); utility ${roundTo(currentUtility, 3)}.`,
  });

  // 3. Greedy frontier upgrades under the budget gate.
  const upgradeModels = args.models.filter((m) => m.tier === "frontier");
  const modelById = new Map(args.models.map((m) => [m.id, m]));
  let upgradesApplied = 0;
  for (;;) {
    let best: {
      nodeId: string;
      modelId: string;
      occupancy: ModelOccupancy[];
      utility: number;
      cost: number;
    } | null = null;
    for (const orgNode of args.organization.nodes) {
      const currentModelId = occupancy.find((o) => o.nodeId === orgNode.id)?.modelId;
      const currentModel = currentModelId === undefined ? undefined : modelById.get(currentModelId);
      const currentRank = currentModel === undefined ? TIER_RANK.balanced : TIER_RANK[currentModel.tier];
      for (const model of upgradeModels) {
        if (currentRank >= TIER_RANK[model.tier]) {
          continue; // only strictly stronger tiers
        }
        const trial: ModelOccupancy[] = occupancy.map((o) =>
          o.nodeId === orgNode.id ? { nodeId: orgNode.id, modelId: model.id } : o,
        );
        const evaluation = await evaluate(trial, capabilities);
        if (evaluation.scores.cost > args.workload.budgetUsdPerTask) {
          continue; // budget gate: expected cost per task stays within budget
        }
        if (best === null || evaluation.utility > best.utility) {
          best = {
            nodeId: orgNode.id,
            modelId: model.id,
            occupancy: trial,
            utility: evaluation.utility,
            cost: evaluation.scores.cost,
          };
        }
      }
    }
    if (best === null || best.utility <= currentUtility + 1e-9) {
      break;
    }
    const previousUtility = currentUtility;
    occupancy = best.occupancy;
    currentUtility = best.utility;
    upgradesApplied += 1;
    trace.push({
      stage: "occupancy-search",
      detail: `Greedy upgrade: ${best.nodeId} → ${best.modelId} (utility ${roundTo(previousUtility, 3)} → ${roundTo(currentUtility, 3)}, ${formatSigned(best.utility - previousUtility)}; mean cost $${roundTo(best.cost, 4)} ≤ budget $${roundTo(args.workload.budgetUsdPerTask, 4)}).`,
    });
  }
  trace.push({
    stage: "occupancy-search",
    detail: `Greedy converged after ${upgradesApplied} upgrade(s); occupancy: ${describeOccupancy(occupancy)}.`,
  });

  // 4. Local swap passes: try fast-a per node; keep non-regressing swaps.
  const fast =
    args.models.find((m) => m.id === "model.fast-a") ??
    args.models.find((m) => m.tier === "fast");
  if (fast) {
    for (let pass = 1; pass <= 3; pass++) {
      let keptThisPass = 0;
      for (const orgNode of args.organization.nodes) {
        if (occupancy.find((o) => o.nodeId === orgNode.id)?.modelId === fast.id) {
          continue;
        }
        const trial: ModelOccupancy[] = occupancy.map((o) =>
          o.nodeId === orgNode.id ? { nodeId: orgNode.id, modelId: fast.id } : o,
        );
        const evaluation = await evaluate(trial, capabilities);
        if (evaluation.utility >= currentUtility - 1e-9) {
          occupancy = trial;
          currentUtility = evaluation.utility;
          keptThisPass += 1;
        }
      }
      trace.push({
        stage: "occupancy-search",
        detail: `Local swap pass ${pass}/3 (${fast.id} trials on every node): kept ${keptThisPass} swap(s); utility ${roundTo(currentUtility, 3)}.`,
      });
    }
  }

  if (typeof args.preOccupancyUtility === "number") {
    trace.push({
      stage: "occupancy-search",
      detail: `Pre-occupancy winner evaluation (neutral default, utility ${roundTo(args.preOccupancyUtility, 3)}) retained for comparison; post-occupancy state utility ${roundTo(currentUtility, 3)}.`,
    });
  }

  return { occupancy, capabilities, trace };
}
