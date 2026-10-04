/**
 * Engineering Lab API — single bridge entry detail (B3-b).
 *
 * GET /api/lab/bridge/{id} → { entry, observation, predicted, error,
 * recommendation } — the entry summary, the parsed observed TaskOutcome, the
 * predicted per-dimension values + error rows from the linked
 * LabCalibrationObservation, and the linked recommendation summary. 404 for
 * unknown ids.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  parseCalibrationErrors,
  parseOutcomeScalars,
  parseTaskOutcome,
} from "../../_lib/observation";
import { bridgeEntrySummary } from "../../_lib/bridge";
import { parseJsonValue, recommendationSummaryFromRow } from "../../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const entry = await db.labBridgeEntry.findUnique({ where: { id } });
    if (!entry) {
      return NextResponse.json(
        { error: `Bridge entry "${id}" not found` },
        { status: 404, headers: NO_STORE },
      );
    }
    const recommendation = await db.labRecommendation.findUnique({
      where: { id: entry.recommendationId },
    });
    const calibrationRow = await db.labCalibrationObservation.findFirst({
      where: { bridgeEntryId: entry.id },
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json(
      {
        entry: bridgeEntrySummary(entry, recommendation),
        observation: entry.observation === null ? null : parseTaskOutcome(parseJsonValue(entry.observation)),
        predicted: calibrationRow === null ? null : parseOutcomeScalars(parseJsonValue(calibrationRow.predicted)),
        error: calibrationRow === null ? null : parseCalibrationErrors(parseJsonValue(calibrationRow.error)),
        recommendation:
          recommendation === null ? null : recommendationSummaryFromRow(recommendation),
      },
      { headers: NO_STORE },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Bridge entry lookup failed: ${message}` },
      { status: 500, headers: NO_STORE },
    );
  }
}
