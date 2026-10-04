/**
 * Engineering Lab API — the calibration model (mission step 11, B3-b).
 *
 * GET /api/lab/calibration → { calibration, observations }:
 *  - calibration: the refreshed CalibrationModel over the FULL observation
 *    store (factors + reliability curve + count), or null when no
 *    observations exist yet (clear empty-state shape).
 *  - observations: latest 50 summaries { id, bridgeEntryId, error, createdAt }
 *    with the per-dimension CalibrationError[] parsed through guards.
 *
 * updatedAt is stamped here (API edge); the calibrator itself stays pure.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { buildCurrentCalibrationModel, parseCalibrationErrors } from "../_lib/observation";
import { parseJsonValue } from "../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET() {
  try {
    const rows = await db.labCalibrationObservation.findMany({
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    const calibration = await buildCurrentCalibrationModel();
    return NextResponse.json(
      {
        calibration,
        observations: rows.map((row) => ({
          id: row.id,
          bridgeEntryId: row.bridgeEntryId,
          error: parseCalibrationErrors(parseJsonValue(row.error)),
          createdAt: row.createdAt.toISOString(),
        })),
      },
      { headers: NO_STORE },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Calibration lookup failed: ${message}` },
      { status: 500, headers: NO_STORE },
    );
  }
}
