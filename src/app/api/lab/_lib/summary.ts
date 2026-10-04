/**
 * Engineering Lab API — shared JSON guards + row summaries (B2).
 *
 * These helpers keep the lab API routes free of `any`: artifact JSON stored
 * by the runs route is parsed through `unknown` + type guards, so corrupt or
 * stub artifacts (failed runs) degrade to null instead of throwing. The lab
 * lib itself stays pure — DB access lives only in the routes.
 */

export interface RunRowLike {
  id: string;
  workloadId: string;
  taskTypeId: string;
  scenarioId: string;
  ladderLevel: number;
  status: string;
  artifact: string;
  seeds: string;
  error: string | null;
  createdAt: Date;
}

export interface RecommendationRowLike {
  id: string;
  runId: string;
  status: string;
  artifact: string;
  createdAt: Date;
}

export interface RunSummary {
  id: string;
  workloadId: string;
  taskTypeId: string;
  scenarioId: string;
  ladderLevel: number;
  status: string;
  winnerName: string | null;
  utilityDelta: number | null;
  createdAt: string;
}

export interface RecommendationSummary {
  id: string;
  runId: string;
  status: string;
  confidence: number | null;
  winnerName: string | null;
  createdAt: string;
}

export function parseJsonValue(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asFiniteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asNonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/** winner organization name from a stored RunArtifact JSON string. */
function winnerNameFromArtifact(raw: string): string | null {
  const artifact = asRecord(parseJsonValue(raw));
  const winner = asRecord(artifact?.winner);
  const organization = asRecord(winner?.organization);
  return asNonEmptyString(organization?.name) ?? null;
}

function utilityDeltaFromArtifact(raw: string): number | null {
  const artifact = asRecord(parseJsonValue(raw));
  const winner = asRecord(artifact?.winner);
  const baseline = asRecord(artifact?.baseline);
  const winnerUtility = asFiniteNumber(winner?.utility);
  const baselineUtility = asFiniteNumber(baseline?.utility);
  if (winnerUtility === undefined || baselineUtility === undefined) {
    return null;
  }
  const delta = Number((winnerUtility - baselineUtility).toFixed(6));
  return delta === 0 ? 0 : delta;
}

export function runSummaryFromRow(run: RunRowLike): RunSummary {
  return {
    id: run.id,
    workloadId: run.workloadId,
    taskTypeId: run.taskTypeId,
    scenarioId: run.scenarioId,
    ladderLevel: run.ladderLevel,
    status: run.status,
    winnerName: winnerNameFromArtifact(run.artifact),
    utilityDelta: utilityDeltaFromArtifact(run.artifact),
    createdAt: run.createdAt.toISOString(),
  };
}

export function recommendationSummaryFromRow(rec: RecommendationRowLike): RecommendationSummary {
  const artifact = asRecord(parseJsonValue(rec.artifact));
  const organization = asRecord(artifact?.organization);
  return {
    id: rec.id,
    runId: rec.runId,
    status: rec.status,
    confidence: asFiniteNumber(artifact?.confidence) ?? null,
    winnerName: asNonEmptyString(organization?.name) ?? null,
    createdAt: rec.createdAt.toISOString(),
  };
}
