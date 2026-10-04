/**
 * Engineering Lab API — shared run persistence (B3-b factored out of the B2
 * runs route so POST /api/lab/runs and POST /api/lab/demo/closed-loop use the
 * SAME code path: executeLabRun → LabRun row + LabRecommendation row).
 *
 * Behavior is byte-compatible with the original inline logic of the runs
 * route: a run-row failure also persists a best-effort failed run; a
 * recommendation failure marks the created run failed. All throws are typed
 * `RunPersistError` carrying the exact HTTP message the runs route used.
 */

import { db } from "@/lib/db";
import type { LabRunResult } from "@/lib/lab/engine/run-engine";
import type { LabRunSpec, RunArtifact } from "@/lib/lab/contracts";
import { runSummaryFromRow, type RunSummary } from "./summary";

export class RunPersistError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunPersistError";
  }
}

export interface PersistedLabRun {
  runId: string;
  recommendationId: string;
  summary: RunSummary;
  /** The engine result (artifact + recommendation) for callers that continue the loop. */
  result: LabRunResult;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

/** Best-effort failed-run persistence (status "failed" + error message). */
export async function persistFailedRun(
  spec: LabRunSpec,
  artifact: RunArtifact | null,
  message: string,
): Promise<void> {
  try {
    await db.labRun.create({
      data: {
        workloadId: spec.workloadId,
        taskTypeId: spec.taskTypeId,
        scenarioId: spec.scenarioId,
        ladderLevel: spec.ladderLevel,
        seeds: JSON.stringify(spec.seeds),
        status: "failed",
        error: message,
        artifact:
          artifact === null
            ? JSON.stringify({ spec, note: "run failed before artifact completion", error: message })
            : JSON.stringify(artifact),
      },
    });
  } catch {
    // Persistence is already failing; nothing more to do.
  }
}

/**
 * Persist a computed run result: LabRun (status complete, RESOLVED seeds,
 * full artifact JSON) + LabRecommendation (status issued, artifact with the
 * assigned runId). Throws RunPersistError on failure with the exact message
 * the runs route has always returned.
 */
export async function persistLabRun(spec: LabRunSpec, result: LabRunResult): Promise<PersistedLabRun> {
  let runId: string;
  let summary: RunSummary;
  try {
    const run = await db.labRun.create({
      data: {
        workloadId: spec.workloadId,
        taskTypeId: spec.taskTypeId,
        scenarioId: spec.scenarioId,
        ladderLevel: spec.ladderLevel,
        seeds: JSON.stringify(result.artifact.spec.seeds),
        status: "complete",
        artifact: JSON.stringify(result.artifact),
        error: null,
      },
    });
    runId = run.id;
    summary = runSummaryFromRow(run);
  } catch (runError) {
    const message = errorMessage(runError);
    await persistFailedRun(spec, result.artifact, message);
    throw new RunPersistError(`Run computed but persistence failed: ${message}`);
  }

  try {
    const recommendation = await db.labRecommendation.create({
      data: {
        runId,
        status: "issued",
        artifact: JSON.stringify({ ...result.recommendation, runId }),
      },
    });
    return { runId, recommendationId: recommendation.id, summary, result };
  } catch (recError) {
    const message = `Recommendation persistence failed: ${errorMessage(recError)}`;
    await db.labRun
      .update({ where: { id: runId }, data: { status: "failed", error: message } })
      .catch(() => undefined);
    throw new RunPersistError(`Run computed but ${message}`);
  }
}
