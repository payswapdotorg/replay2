import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { executeLabRun, type LabRunResult } from "@/lib/lab/engine/run-engine";
import { LabError } from "@/lib/lab/errors";
import type { LabRunSpec } from "@/lib/lab/contracts";
import { RunPersistError, persistFailedRun, persistLabRun } from "../_lib/persist";
import { runSummaryFromRow } from "../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

function badRequest(error: string): NextResponse {
  return NextResponse.json({ error }, { status: 400, headers: NO_STORE });
}

function serverError(error: string): NextResponse {
  return NextResponse.json({ error }, { status: 500, headers: NO_STORE });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

/** Manual, zod-free request validation with clear 400 messages. */
function parseRunSpec(body: unknown): LabRunSpec {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw new LabError("Request body must be a JSON object");
  }
  const record = body as Record<string, unknown>;
  for (const key of ["workloadId", "taskTypeId", "scenarioId"] as const) {
    const value = record[key];
    if (typeof value !== "string" || value.length === 0) {
      throw new LabError(`Field "${key}" is required and must be a non-empty string`);
    }
  }
  let ladderLevel: number = 1; // default: scenario-sim
  if (record.ladderLevel !== undefined) {
    if (
      typeof record.ladderLevel !== "number" ||
      !Number.isInteger(record.ladderLevel) ||
      record.ladderLevel < 0 ||
      record.ladderLevel > 2
    ) {
      throw new LabError('Field "ladderLevel" must be an integer 0, 1 or 2 (default 1)');
    }
    ladderLevel = record.ladderLevel;
  }
  let seeds: number[] = [];
  if (record.seeds !== undefined) {
    if (!Array.isArray(record.seeds)) {
      throw new LabError('Field "seeds" must be an array of integers');
    }
    if (record.seeds.length > 5) {
      throw new LabError('Field "seeds" must contain at most 5 entries');
    }
    seeds = record.seeds.map((seed, index) => {
      if (typeof seed !== "number" || !Number.isInteger(seed)) {
        throw new LabError(`seeds[${index}] must be an integer`);
      }
      return seed;
    });
  }
  return {
    workloadId: record.workloadId as string,
    taskTypeId: record.taskTypeId as string,
    scenarioId: record.scenarioId as string,
    ladderLevel: ladderLevel as LabRunSpec["ladderLevel"],
    seeds,
  };
}

export async function GET() {
  const rows = await db.labRun.findMany({
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  return NextResponse.json(
    { runs: rows.map(runSummaryFromRow) },
    { headers: NO_STORE },
  );
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return badRequest("Request body must be valid JSON");
  }

  let spec: LabRunSpec;
  try {
    spec = parseRunSpec(body);
  } catch (error) {
    if (error instanceof LabError) {
      return badRequest(error.message);
    }
    return serverError(`Invalid run spec: ${errorMessage(error)}`);
  }

  let result: LabRunResult;
  try {
    result = await executeLabRun(spec);
  } catch (error) {
    if (error instanceof LabError) {
      return badRequest(error.message);
    }
    const message = errorMessage(error);
    await persistFailedRun(spec, null, message);
    return serverError(`Lab run failed: ${message}`);
  }

  // Shared persist path (also used by the closed-loop demo route):
  // LabRun row + LabRecommendation row, identical failure semantics.
  try {
    const persisted = await persistLabRun(spec, result);
    return NextResponse.json(
      {
        ...persisted.summary,
        recommendationId: persisted.recommendationId,
      },
      { status: 201, headers: NO_STORE },
    );
  } catch (error) {
    if (error instanceof RunPersistError) {
      return serverError(error.message);
    }
    return serverError(`Run computed but persistence failed: ${errorMessage(error)}`);
  }
}
