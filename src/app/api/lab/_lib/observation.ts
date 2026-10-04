/**
 * Engineering Lab API — shared observation intake + calibration IO (B3-b).
 *
 * The single code path behind POST /api/lab/bridge/{id}/observe and the
 * closed-loop demo: it re-derives the OBSERVED TaskOutcome through the
 * fixture LabExecutionPort from the run's stored spec + the recommendation's
 * winning organization, computes the per-dimension predicted-vs-observed
 * error, and persists the observation pair. Deterministic: given the same
 * (run row, recommendation artifact, observation seed) the numbers are
 * byte-identical — the seed is derived by the ROUTES (the bridge route uses
 * hashSeed(runId, "observation"); the demo pins a fixed key so repeated POSTs
 * stay numerically identical).
 *
 * JSON guards follow the _lib conventions: everything parses through
 * `unknown` with type guards, corrupt rows degrade to null, no `any`.
 */

import { db } from "@/lib/db";
import { buildCalibrationModel, type CalibrationObservationPair } from "@/lib/lab/calibration/calibrator";
import type {
  CalibrationError,
  CalibrationModel,
  CapabilityAllocation,
  EvalDimension,
  ModelOccupancy,
  OrganizationSpec,
  TaskOutcome,
} from "@/lib/lab/contracts";
import { getExecutionPort } from "@/lib/lab/execution";
import { LabError } from "@/lib/lab/errors";
import { roundTo } from "@/lib/lab/sim/numeric";
import { seWorldScenarios } from "@/lib/lab/catalog/se-world";
import { seWorldEngine } from "@/lib/lab/worlds/se-world";
import { hashSeed } from "@/lib/lab/rng";
import { parseJsonValue, type RunRowLike } from "./summary";

// ---------------------------------------------------------------------------
// Shapes + guards.
// ---------------------------------------------------------------------------

/** The winner's expected per-dimension values (from the run artifact). */
export interface PredictedOutcome {
  success: number;
  quality: number;
  latencyMs: number;
  costUsd: number;
}

/** The full intake result persisted as one LabCalibrationObservation row. */
export interface ObservationIntake {
  observed: TaskOutcome;
  predicted: PredictedOutcome;
  error: CalibrationError[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asFiniteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asStringArray(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((v) => typeof v === "string") ? (value as string[]) : null;
}

/** Predicted/observed 4-scalar pair parse (success is boolean on the observed
 *  TaskOutcome side and a rate on the predicted side — both are accepted). */
export function parseOutcomeScalars(raw: unknown): PredictedOutcome | null {
  const record = asRecord(raw);
  if (record === null) return null;
  const success =
    typeof record.success === "boolean" ? (record.success ? 1 : 0) : asFiniteNumber(record.success);
  const quality = asFiniteNumber(record.quality);
  const latencyMs = asFiniteNumber(record.latencyMs);
  const costUsd = asFiniteNumber(record.costUsd);
  if (success === undefined || quality === undefined || latencyMs === undefined || costUsd === undefined) {
    return null;
  }
  return { success, quality, latencyMs, costUsd };
}

/** Full TaskOutcome parse (scalars + verification checks) for detail views. */
export function parseTaskOutcome(raw: unknown): TaskOutcome | null {
  const scalars = parseOutcomeScalars(raw);
  const record = asRecord(raw);
  if (scalars === null || record === null) return null;
  const verificationRaw = record.verification;
  if (!Array.isArray(verificationRaw)) return null;
  const verification: { check: string; passed: boolean }[] = [];
  for (const entry of verificationRaw) {
    const entryRecord = asRecord(entry);
    if (entryRecord === null || typeof entryRecord.check !== "string" || typeof entryRecord.passed !== "boolean") {
      return null;
    }
    verification.push({ check: entryRecord.check, passed: entryRecord.passed });
  }
  return {
    success: typeof record.success === "boolean" ? record.success : scalars.success > 0,
    quality: scalars.quality,
    latencyMs: scalars.latencyMs,
    costUsd: scalars.costUsd,
    verification,
  };
}
/** CalibrationError[] parse for observation summaries. */
export function parseCalibrationErrors(raw: unknown): CalibrationError[] | null {
  if (!Array.isArray(raw)) return null;
  const dimensions = new Set<string>(["success", "quality", "latency", "cost"]);
  const errors: CalibrationError[] = [];
  for (const entry of raw) {
    const record = asRecord(entry);
    const dimension = record?.dimension;
    const predicted = asFiniteNumber(record?.predicted);
    const observed = asFiniteNumber(record?.observed);
    const error = asFiniteNumber(record?.error);
    if (
      typeof dimension !== "string" ||
      !dimensions.has(dimension) ||
      predicted === undefined ||
      observed === undefined ||
      error === undefined
    ) {
      return null;
    }
    errors.push({ dimension: dimension as EvalDimension, predicted, observed, error });
  }
  return errors;
}

/** Winner expected values from a parsed RunArtifact (guarded). */
export function predictedFromRunArtifact(raw: unknown): PredictedOutcome | null {
  const artifact = asRecord(raw);
  const winner = asRecord(artifact?.winner);
  const scores = winner?.scores;
  if (!Array.isArray(scores)) return null;
  const byDimension = new Map<string, number>();
  for (const score of scores) {
    const record = asRecord(score);
    const dimension = record?.dimension;
    const value = asFiniteNumber(record?.value);
    if (typeof dimension === "string" && value !== undefined) {
      byDimension.set(dimension, value);
    }
  }
  return {
    success: byDimension.get("success") ?? 0,
    quality: byDimension.get("quality") ?? 0,
    latencyMs: byDimension.get("latency") ?? 0,
    costUsd: byDimension.get("cost") ?? 0,
  };
}

/** Organization/occupancy/capabilities from a stored RecommendationArtifact JSON. */
export function parseRecommendationExecution(raw: unknown): {
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
} | null {
  const artifact = asRecord(raw);
  const organization = asRecord(artifact?.organization);
  const nodes = organization?.nodes;
  const edges = organization?.edges;
  const occupancy = artifact?.occupancy;
  const capabilities = artifact?.capabilities;
  if (
    organization === null ||
    typeof organization.id !== "string" ||
    typeof organization.name !== "string" ||
    typeof organization.topology !== "string" ||
    !Array.isArray(nodes) ||
    !Array.isArray(edges) ||
    !Array.isArray(occupancy) ||
    !Array.isArray(capabilities)
  ) {
    return null;
  }
  for (const node of nodes) {
    const record = asRecord(node);
    if (record === null || typeof record.id !== "string" || typeof record.bodyId !== "string") {
      return null;
    }
  }
  for (const slot of occupancy) {
    const record = asRecord(slot);
    if (record === null || typeof record.nodeId !== "string" || typeof record.modelId !== "string") {
      return null;
    }
  }
  for (const allocation of capabilities) {
    const record = asRecord(allocation);
    if (record === null || typeof record.nodeId !== "string" || asStringArray(record.toolIds) === null) {
      return null;
    }
  }
  // Cast is safe: every field the port touches was validated above; the JSON
  // was originally serialized from the frozen contract types.
  return {
    organization: organization as unknown as OrganizationSpec,
    occupancy: occupancy as unknown as ModelOccupancy[],
    capabilities: capabilities as unknown as CapabilityAllocation[],
  };
}

// ---------------------------------------------------------------------------
// The intake (shared by the bridge observe route and the closed-loop demo).
// ---------------------------------------------------------------------------

export interface ObservationIntakeArgs {
  run: RunRowLike;
  recommendationArtifact: unknown;
  observationSeed: number;
}

/**
 * Run the OBSERVED outcome through the fixture port:
 *  - regenerate the run's primary-seed instance batch via seWorldEngine
 *    (same cap as the engine: min(instanceCount, 6));
 *  - execute the first instance with the recommendation's winning
 *    organization / occupancy / capabilities and the given observation seed;
 *  - predicted = the run winner's per-dimension evaluation; error per
 *    dimension is oriented positive-better (success/quality: observed −
 *    predicted; latency/cost: predicted − observed).
 */
export async function runObservationIntake(args: ObservationIntakeArgs): Promise<ObservationIntake> {
  const scenario = seWorldScenarios.find((s) => s.id === args.run.scenarioId);
  if (!scenario) {
    throw new LabError(`Run references unknown scenario "${args.run.scenarioId}"`);
  }
  const execution = parseRecommendationExecution(args.recommendationArtifact);
  if (!execution) {
    throw new LabError("Recommendation artifact does not carry a executable organization");
  }
  const predicted = predictedFromRunArtifact(parseJsonValue(args.run.artifact));
  if (!predicted) {
    throw new LabError("Run artifact does not carry a winner evaluation to predict from");
  }

  const seedsRaw: unknown = parseJsonValue(args.run.seeds);
  const seeds = Array.isArray(seedsRaw) ? seedsRaw.filter((s): s is number => typeof s === "number") : [];
  // Same default derivation as the engine when the stored seeds are unusable.
  const primarySeed = seeds.length > 0 ? seeds[0] : hashSeed(scenario.id, args.run.workloadId) % 997;

  const instanceCap = Math.min(scenario.instanceCount, 6);
  const instances = seWorldEngine.generateInstances(scenario, instanceCap, primarySeed);
  const instance = instances[0];
  if (!instance) {
    throw new LabError(`Scenario "${scenario.id}" produced no instances from seed ${primarySeed}`);
  }

  const port = getExecutionPort("fixture");
  const observed = await port.executeTask({
    instance,
    organization: execution.organization,
    occupancy: execution.occupancy,
    capabilities: execution.capabilities,
    seed: args.observationSeed,
  });

  const observedSuccess = observed.success ? 1 : 0;
  const error: CalibrationError[] = [
    {
      dimension: "success",
      predicted: roundTo(predicted.success, 6),
      observed: observedSuccess,
      error: roundTo(observedSuccess - predicted.success, 6),
    },
    {
      dimension: "quality",
      predicted: roundTo(predicted.quality, 6),
      observed: roundTo(observed.quality, 6),
      error: roundTo(observed.quality - predicted.quality, 6),
    },
    {
      dimension: "latency",
      predicted: roundTo(predicted.latencyMs, 6),
      observed: roundTo(observed.latencyMs, 6),
      // Positive = observed was faster than predicted.
      error: roundTo(predicted.latencyMs - observed.latencyMs, 6),
    },
    {
      dimension: "cost",
      predicted: roundTo(predicted.costUsd, 6),
      observed: roundTo(observed.costUsd, 6),
      // Positive = observed was cheaper than predicted.
      error: roundTo(predicted.costUsd - observed.costUsd, 6),
    },
  ];

  return {
    observed,
    predicted: {
      success: roundTo(predicted.success, 6),
      quality: roundTo(predicted.quality, 6),
      latencyMs: roundTo(predicted.latencyMs, 6),
      costUsd: roundTo(predicted.costUsd, 6),
    },
    error,
  };
}

/**
 * Persist one intake: LabCalibrationObservation row + flip the bridge entry
 * to observed (observedAt + observation JSON). Timestamps live here — this is
 * an API edge, never src/lib/lab.
 */
export async function persistBridgeObservation(
  entryId: string,
  intake: ObservationIntake,
): Promise<{ observedAt: Date; observationId: string }> {
  const observedAt = new Date();
  const observation = await db.labCalibrationObservation.create({
    data: {
      bridgeEntryId: entryId,
      predicted: JSON.stringify(intake.predicted),
      observed: JSON.stringify(intake.observed),
      error: JSON.stringify(intake.error),
    },
  });
  await db.labBridgeEntry.update({
    where: { id: entryId },
    data: {
      status: "observed",
      observedAt,
      observation: JSON.stringify(intake.observed),
    },
  });
  return { observedAt, observationId: observation.id };
}

/** Parse every stored observation into calibration pairs (corrupt rows skipped). */
export async function loadCalibrationPairs(): Promise<CalibrationObservationPair[]> {
  const rows = await db.labCalibrationObservation.findMany({ orderBy: { createdAt: "asc" } });
  const pairs: CalibrationObservationPair[] = [];
  for (const row of rows) {
    const predicted = parseOutcomeScalars(parseJsonValue(row.predicted));
    const observed = parseOutcomeScalars(parseJsonValue(row.observed));
    if (predicted !== null && observed !== null) {
      pairs.push({ predicted, observed });
    }
  }
  return pairs;
}

/** The refreshed model over the full observation store; null when empty. */
export async function buildCurrentCalibrationModel(): Promise<CalibrationModel | null> {
  const pairs = await loadCalibrationPairs();
  if (pairs.length === 0) {
    return null;
  }
  return buildCalibrationModel(pairs, new Date().toISOString());
}
