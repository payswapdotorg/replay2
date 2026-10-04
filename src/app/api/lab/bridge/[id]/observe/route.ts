/**
 * Engineering Lab API — the observation intake (mission step 11, B3-b).
 *
 * POST /api/lab/bridge/{id}/observe → executes the OBSERVED outcome through
 * the fixture LabExecutionPort with the deterministic observation seed
 * hashSeed(runId, "observation"): the run's stored spec (workload / task
 * type / scenario, instances regenerated via seWorldEngine from the primary
 * seed) is re-run against the recommendation's winning organization. The
 * predicted side is the run winner's evaluation. Persists the entry →
 * observed + a LabCalibrationObservation row, and responds with the intake
 * plus the REFRESHED calibration model (over the whole observation store).
 *
 * 404 unknown entry, 409 already observed, LabError → 400, unexpected → 500.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { hashSeed } from "@/lib/lab/rng";
import { LabError } from "@/lib/lab/errors";
import {
  buildCurrentCalibrationModel,
  persistBridgeObservation,
  runObservationIntake,
} from "../../../_lib/observation";
import { parseJsonValue, runSummaryFromRow } from "../../../_lib/summary";
import { bridgeEntrySummary } from "../../../_lib/bridge";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    // --- Load the entry + its recommendation + the run.
    const entry = await db.labBridgeEntry.findUnique({ where: { id } });
    if (!entry) {
      return NextResponse.json(
        { error: `Bridge entry "${id}" not found` },
        { status: 404, headers: NO_STORE },
      );
    }
    if (entry.status === "observed" || entry.observedAt !== null) {
      return NextResponse.json(
        {
          error: `Bridge entry "${id}" was already observed at ${entry.observedAt?.toISOString() ?? "unknown time"}`,
        },
        { status: 409, headers: NO_STORE },
      );
    }

    const recommendation = await db.labRecommendation.findUnique({
      where: { id: entry.recommendationId },
    });
    if (!recommendation) {
      return NextResponse.json(
        {
          error: `Recommendation "${entry.recommendationId}" behind bridge entry "${id}" not found`,
        },
        { status: 404, headers: NO_STORE },
      );
    }
    const run = await db.labRun.findUnique({ where: { id: recommendation.runId } });
    if (!run) {
      return NextResponse.json(
        {
          error: `Lab run "${recommendation.runId}" behind recommendation "${recommendation.id}" not found`,
        },
        { status: 404, headers: NO_STORE },
      );
    }

    // --- Deterministic intake (seed derives from the persisted runId).
    const intake = await runObservationIntake({
      run,
      recommendationArtifact: parseJsonValue(recommendation.artifact),
      observationSeed: hashSeed(run.id, "observation"),
    });

    // --- Persist + rebuild the model over the full observation store.
    await persistBridgeObservation(entry.id, intake);
    const calibration = await buildCurrentCalibrationModel();

    const refreshedEntry = await db.labBridgeEntry.findUnique({ where: { id: entry.id } });
    const refreshedRecommendation =
      refreshedEntry === null
        ? null
        : await db.labRecommendation.findUnique({ where: { id: refreshedEntry.recommendationId } });

    return NextResponse.json(
      {
        entry:
          refreshedEntry === null
            ? null
            : bridgeEntrySummary(refreshedEntry, refreshedRecommendation),
        run: runSummaryFromRow(run),
        observation: {
          predicted: intake.predicted,
          observed: intake.observed,
          error: intake.error,
        },
        calibration,
      },
      { status: 201, headers: NO_STORE },
    );
  } catch (error) {
    if (error instanceof LabError) {
      return NextResponse.json({ error: error.message }, { status: 400, headers: NO_STORE });
    }
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Observation intake failed: ${message}` },
      { status: 500, headers: NO_STORE },
    );
  }
}
