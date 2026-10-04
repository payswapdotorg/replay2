/**
 * Engineering Lab — the organization simulator (mission step 5's execution
 * engine, the Lab's fixture-mode LabExecutionPort).
 *
 * Deterministic outcome model combining world difficulty × body capability
 * coverage × model tier × topology × seed. All randomness flows through the
 * seeded RNG: per (instance, organization, seed) for quality, and per
 * (instance, organization, seed, checkIndex) for each acceptance check, so
 * every single check is independently reproducible. No clock, no
 * Math.random anywhere.
 *
 * Recipe (B2 frozen math, shared by the per-instance and the L0 analytic
 * closed-form paths via `computeCore`):
 * - Required capabilities per task type family:
 *     implementation → [cap.code, cap.plan, cap.context]
 *     review        → [cap.review, cap.context]
 *     investigation → [cap.search, cap.verify, cap.context]
 *     maintenance   → [cap.code, cap.verify, cap.integrate]
 * - Org effective capability per required cap = BEST across nodes, weighted:
 *     nodes whose archetype maps to the cap count fully, others at 0.7×;
 *     cap.context is universal (every archetype maps to it). The scalar
 *     `effectiveCapability` is the mean over the required caps.
 * - Model multiplier per node from occupancy: frontier 1.0 (1.05 when the
 *     node's primary archetype capability is in the model's strengths),
 *     balanced 0.85 (0.9), fast 0.7 (0.75). Org-level model multiplier =
 *     token-usage-weighted average over nodes.
 * - Topology: coordinationLatencyFactor = 1 + 0.15 × (nodes − 1); coverage
 *     advantage comes from best-per-cap aggregation (single-node orgs are
 *     penalized on caps their solo body is weak at, naturally).
 * - checkP = clamp01(0.2 + 0.8 × effectiveCapability × modelMultiplier ×
 *     (1 − 0.4 × difficulty) + toolBonus + reviewBonus).
 * - verification: one check per instance.acceptance string (verbatim, per
 *     the B1 convention), each drawn from its own sub-RNG.
 * - tokens per node = (Σ contextFiles.lines × 8 × taskType.contextNeeds) /
 *     nodes + 1200 output tokens; latency = Σ per-node token ms ×
 *     coordination factor; cost = Σ per-node token cost.
 * - With no occupancy passed, model.balanced-a is assumed on every node
 *     (the neutral default the org search starts from).
 */

import { findBody } from "../catalog/agent-bodies";
import { findModel, modelDescriptors } from "../catalog/models";
import { seWorldScenarios } from "../catalog/se-world";
import { findTaskType } from "../catalog/task-types";
import { LabError } from "../errors";
import type {
  AgentBodySpec,
  BodyArchetype,
  CapabilityAllocation,
  ExecutionRequest,
  LabExecutionPort,
  ModelDescriptor,
  ModelOccupancy,
  ModelTier,
  OrganizationSpec,
  TaskOutcome,
  TaskTypeDescriptor,
} from "../contracts";
import { clamp01, createRng, hashSeed } from "../rng";
import { roundTo } from "./numeric";

// ---------------------------------------------------------------------------
// Frozen constants of the outcome model.
// ---------------------------------------------------------------------------

/** The capability each archetype is the dedicated owner of. */
export const ARCHETYPE_PRIMARY_CAP: Record<BodyArchetype, string> = {
  planner: "cap.plan",
  coder: "cap.code",
  reviewer: "cap.review",
  verifier: "cap.verify",
  researcher: "cap.search",
  integrator: "cap.integrate",
};

/** Capability every archetype maps to at full weight. */
export const UNIVERSAL_CAP = "cap.context";

/** Weight of a node contribution when its archetype does NOT map to the cap. */
export const CROSS_ARCHETYPE_WEIGHT = 0.7;

/** Required capability sets per task type family. */
export const REQUIRED_CAPS_BY_FAMILY: Record<TaskTypeDescriptor["family"], string[]> = {
  implementation: ["cap.code", "cap.plan", "cap.context"],
  review: ["cap.review", "cap.context"],
  investigation: ["cap.search", "cap.verify", "cap.context"],
  maintenance: ["cap.code", "cap.verify", "cap.integrate"],
};

/** Tier multipliers (base, and when the node's primary cap is a strength). */
export const MODEL_TIER_MULTIPLIER: Record<ModelTier, { base: number; strength: number }> = {
  frontier: { base: 1.0, strength: 1.05 },
  balanced: { base: 0.85, strength: 0.9 },
  fast: { base: 0.7, strength: 0.75 },
};

/** Tool allocation per archetype (capability allocation search basis). */
export const ARCHETYPE_TOOLS: Record<BodyArchetype, string[]> = {
  planner: ["tool.search"],
  coder: ["tool.editor", "tool.shell", "tool.test-runner"],
  reviewer: ["tool.vcs", "tool.linter"],
  verifier: ["tool.test-runner", "tool.shell"],
  researcher: ["tool.search", "tool.browser"],
  integrator: ["tool.editor", "tool.vcs"],
};

/** +checkP when every node's required tools are allocated. */
export const TOOL_BONUS = 0.05;
/** +checkP when a dedicated reviewer node (cap.review > threshold) exists. */
export const REVIEW_BONUS = 0.04;
/** Review-capability threshold that makes a reviewer node "dedicated". */
export const REVIEWER_REVIEW_CAP_THRESHOLD = 0.6;

/** Approximate tokens represented by one context line. */
export const TOKENS_PER_CONTEXT_LINE = 8;
/** Output tokens each node produces per instance (deterministic). */
export const OUTPUT_TOKENS_PER_NODE = 1200;
/** Latency coordination penalty per node beyond the first. */
export const COORDINATION_LATENCY_STEP = 0.15;

/**
 * Expected Σ context lines for a se.repo-maintenance instance, used by the
 * L0 analytic path (world generation draws 3–6 files × 40–900 lines:
 * 4.5 × 470 = 2115).
 */
export const EXPECTED_CONTEXT_LINES = 2115;
/** Expected acceptance criteria per instance (world draws 2–4). */
export const EXPECTED_ACCEPTANCE_COUNT = 3;

/** Model assumed on every node when no occupancy is passed. */
export const DEFAULT_MODEL_ID = "model.balanced-a";

// ---------------------------------------------------------------------------
// Analytic (L0) surface.
// ---------------------------------------------------------------------------

export interface AnalyticOutcomeArgs {
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  taskType: TaskTypeDescriptor;
  difficulty: number;
  acceptanceCount: number;
  contextLines: number;
}

export interface AnalyticOutcome {
  checkP: number;
  effectiveCapability: number;
  modelMultiplier: number;
  /** Expected probability that ALL acceptance checks pass. */
  successProbability: number;
  quality: number;
  latencyMs: number;
  costUsd: number;
}

// ---------------------------------------------------------------------------
// The simulator.
// ---------------------------------------------------------------------------

interface CoreInput {
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  taskType: TaskTypeDescriptor;
  difficulty: number;
  contextLines: number;
}

interface CoreOutput {
  checkP: number;
  effectiveCapability: number;
  modelMultiplier: number;
  nodeTokens: number;
  latencyMs: number;
  costUsd: number;
}

function archetypeMapsToCap(archetype: BodyArchetype, cap: string): boolean {
  return cap === UNIVERSAL_CAP || ARCHETYPE_PRIMARY_CAP[archetype] === cap;
}

/**
 * The tools a node REQUIRES for its archetype: the archetype tool set
 * intersected with the task type's typical tools; the full archetype set
 * when the intersection is empty. Shared by the tool bonus here and by the
 * capability allocation in the occupancy search.
 */
export function requiredToolsForArchetype(archetype: BodyArchetype, taskType: TaskTypeDescriptor): string[] {
  const full = ARCHETYPE_TOOLS[archetype];
  const required = full.filter((toolId) => taskType.typicalTools.includes(toolId));
  return required.length > 0 ? required : [...full];
}

export class OrgSimulator implements LabExecutionPort {
  readonly id = "org-sim";
  readonly mode = "fixture" as const;

  async executeTask(req: ExecutionRequest): Promise<TaskOutcome> {
    const { instance, organization, occupancy, capabilities, seed } = req;
    const taskType = this.resolveTaskType(instance.scenarioId);
    const contextLines = instance.contextFiles.reduce((sum, f) => sum + f.lines, 0);
    const core = this.computeCore({
      organization,
      occupancy,
      capabilities,
      taskType,
      difficulty: instance.difficulty,
      contextLines,
    });

    // One check per acceptance string, each from its own deterministic
    // sub-RNG so any single check can be regenerated alone.
    const verification = instance.acceptance.map((check, checkIndex) => {
      const rng = createRng(hashSeed(instance.id, organization.id, seed, checkIndex));
      return { check, passed: rng.bernoulli(core.checkP) };
    });
    const success = verification.length > 0 && verification.every((v) => v.passed);

    // Quality draw from the per-(instance, organization, seed) stream.
    const rng = createRng(hashSeed(instance.id, organization.id, seed));
    const quality = clamp01(rng.sample(core.checkP, 0.1));

    return {
      success,
      quality: roundTo(quality, 4),
      latencyMs: core.latencyMs,
      costUsd: core.costUsd,
      verification,
    };
  }

  /** Closed-form expectation (L0 analytic): no RNG draws, no instances. */
  analyticOutcome(args: AnalyticOutcomeArgs): AnalyticOutcome {
    const core = this.computeCore({
      organization: args.organization,
      occupancy: args.occupancy,
      capabilities: args.capabilities,
      taskType: args.taskType,
      difficulty: clamp01(args.difficulty),
      contextLines: Math.max(0, args.contextLines),
    });
    const checks = Math.max(1, args.acceptanceCount);
    return {
      checkP: core.checkP,
      effectiveCapability: core.effectiveCapability,
      modelMultiplier: core.modelMultiplier,
      successProbability: clamp01(core.checkP ** checks),
      quality: clamp01(core.checkP),
      latencyMs: core.latencyMs,
      costUsd: core.costUsd,
    };
  }

  // -------------------------------------------------------------------------
  // Internals.
  // -------------------------------------------------------------------------

  private computeCore(input: CoreInput): CoreOutput {
    const nodes = input.organization.nodes;
    const nodeCount = Math.max(1, nodes.length);
    const requiredCaps = REQUIRED_CAPS_BY_FAMILY[input.taskType.family];

    // Org effective capability: best per required cap across weighted nodes.
    const perCap: number[] = [];
    for (const cap of requiredCaps) {
      let best = 0;
      for (const orgNode of nodes) {
        const body = this.resolveBody(orgNode.bodyId);
        const raw = body.capabilities[cap] ?? 0;
        const weight = archetypeMapsToCap(body.archetype, cap) ? 1 : CROSS_ARCHETYPE_WEIGHT;
        best = Math.max(best, raw * weight);
      }
      perCap.push(best);
    }
    const effectiveCapability =
      perCap.length > 0 ? perCap.reduce((sum, v) => sum + v, 0) / perCap.length : 0;

    // Token model (equal split of context across nodes + fixed output).
    const contextTokens = input.contextLines * TOKENS_PER_CONTEXT_LINE * input.taskType.contextNeeds;
    const nodeTokens = contextTokens / nodeCount + OUTPUT_TOKENS_PER_NODE;

    // Per-node model effects: usage-weighted multiplier, latency and cost.
    let weightedMultiplier = 0;
    let tokenSum = 0;
    let latencySumMs = 0;
    let costSumUsd = 0;
    for (const orgNode of nodes) {
      const body = this.resolveBody(orgNode.bodyId);
      const model = this.resolveModel(
        input.occupancy.find((o) => o.nodeId === orgNode.id)?.modelId,
      );
      const tier = MODEL_TIER_MULTIPLIER[model.tier];
      const primaryCap = ARCHETYPE_PRIMARY_CAP[body.archetype];
      const multiplier = model.strengths.includes(primaryCap) ? tier.strength : tier.base;
      weightedMultiplier += nodeTokens * multiplier;
      tokenSum += nodeTokens;
      latencySumMs += (nodeTokens / 1000) * model.latencyMsPerKtok;
      costSumUsd += (nodeTokens * model.costUsdPerMTok) / 1_000_000;
    }
    const modelMultiplier = tokenSum > 0 ? weightedMultiplier / tokenSum : 1;
    const coordinationFactor = 1 + COORDINATION_LATENCY_STEP * (nodeCount - 1);
    const latencyMs = Math.round(latencySumMs * coordinationFactor);
    const costUsd = roundTo(costSumUsd, 6);

    // Bonuses: full tool allocation, and a dedicated review gate.
    const toolBonus = this.computeToolBonus(nodes, input.taskType, input.capabilities);
    const reviewBonus = nodes.some((orgNode) => {
      const body = this.resolveBody(orgNode.bodyId);
      return (
        body.archetype === "reviewer" &&
        (body.capabilities["cap.review"] ?? 0) > REVIEWER_REVIEW_CAP_THRESHOLD
      );
    })
      ? REVIEW_BONUS
      : 0;

    const checkP = clamp01(
      0.2 +
        0.8 * effectiveCapability * modelMultiplier * (1 - 0.4 * clamp01(input.difficulty)) +
        toolBonus +
        reviewBonus,
    );

    return { checkP, effectiveCapability, modelMultiplier, nodeTokens, latencyMs, costUsd };
  }

  private computeToolBonus(
    nodes: OrganizationSpec["nodes"],
    taskType: TaskTypeDescriptor,
    capabilities: CapabilityAllocation[],
  ): number {
    for (const orgNode of nodes) {
      const body = this.resolveBody(orgNode.bodyId);
      const required = requiredToolsForArchetype(body.archetype, taskType);
      if (required.length === 0) {
        continue;
      }
      const allocated = capabilities.find((c) => c.nodeId === orgNode.id)?.toolIds ?? [];
      if (!required.every((toolId) => allocated.includes(toolId))) {
        return 0;
      }
    }
    return TOOL_BONUS;
  }

  private resolveBody(bodyId: string): AgentBodySpec {
    const body = findBody(bodyId);
    if (!body) {
      throw new LabError(`Organization references unknown body "${bodyId}"`);
    }
    return body;
  }

  private resolveModel(modelId: string | undefined): ModelDescriptor {
    if (modelId !== undefined) {
      const model = findModel(modelId);
      if (model) {
        return model;
      }
    }
    const fallback = findModel(DEFAULT_MODEL_ID);
    if (!fallback) {
      throw new LabError(`Catalog error: default model "${DEFAULT_MODEL_ID}" missing from modelDescriptors (${modelDescriptors.length} models)`);
    }
    return fallback;
  }

  private resolveTaskType(scenarioId: string): TaskTypeDescriptor {
    const scenario = seWorldScenarios.find((s) => s.id === scenarioId);
    const taskTypeId = scenario?.taskTypeId;
    const taskType = taskTypeId === undefined ? undefined : findTaskType(taskTypeId);
    if (!taskType) {
      throw new LabError(`Cannot resolve a task type for scenario "${scenarioId}"`);
    }
    return taskType;
  }
}
