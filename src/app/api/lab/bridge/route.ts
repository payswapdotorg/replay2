/**
 * Engineering Lab API — the execution bridge (mission step 10, B3-b).
 *
 * GET  /api/lab/bridge        → { entries }  newest first (take 50), joined
 *                               with the linked recommendation for
 *                               winnerName / confidence / runId.
 * POST /api/lab/bridge        → queue an issued recommendation for execution
 *                               through the LabExecutionPort. Creates a
 *                               LabBridgeEntry (fixture mode — the flauz
 *                               adapter refuses until the Agent OS lane is
 *                               wired) and flips the recommendation to "sent".
 *
 * Conventions: force-dynamic, no-store, manual validation (LabError → 400),
 * unknown ids → 404, duplicate bridge entries → 409, unexpected → 500.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { LabError } from "@/lib/lab/errors";
import { BRIDGE_NOTE, bridgeEntrySummary } from "../_lib/bridge";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET() {
  const entries = await db.labBridgeEntry.findMany({
    orderBy: { submittedAt: "desc" },
    take: 50,
  });
  const recommendationIds = [...new Set(entries.map((entry) => entry.recommendationId))];
  const recommendations =
    recommendationIds.length > 0
      ? await db.labRecommendation.findMany({ where: { id: { in: recommendationIds } } })
      : [];
  const byId = new Map(recommendations.map((rec) => [rec.id, rec]));
  return NextResponse.json(
    {
      entries: entries.map((entry) => bridgeEntrySummary(entry, byId.get(entry.recommendationId) ?? null)),
    },
    { headers: NO_STORE },
  );
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Request body must be valid JSON" },
      { status: 400, headers: NO_STORE },
    );
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return NextResponse.json(
      { error: 'Request body must be a JSON object with a "recommendationId" field' },
      { status: 400, headers: NO_STORE },
    );
  }
  const recommendationId = (body as Record<string, unknown>).recommendationId;
  if (typeof recommendationId !== "string" || recommendationId.length === 0) {
    return NextResponse.json(
      { error: 'Field "recommendationId" is required and must be a non-empty string' },
      { status: 400, headers: NO_STORE },
    );
  }

  try {
    const recommendation = await db.labRecommendation.findUnique({
      where: { id: recommendationId },
    });
    if (!recommendation) {
      return NextResponse.json(
        { error: `Recommendation "${recommendationId}" not found` },
        { status: 404, headers: NO_STORE },
      );
    }

    const existing = await db.labBridgeEntry.findFirst({
      where: { recommendationId },
    });
    if (existing) {
      return NextResponse.json(
        {
          error: `A bridge entry (${existing.id}, status "${existing.status}") already exists for recommendation "${recommendationId}"`,
        },
        { status: 409, headers: NO_STORE },
      );
    }

    const entry = await db.labBridgeEntry.create({
      data: {
        recommendationId,
        status: "queued",
        note: BRIDGE_NOTE,
        portMode: "fixture",
      },
    });
    const sent = await db.labRecommendation.update({
      where: { id: recommendationId },
      data: { status: "sent" },
    });

    return NextResponse.json(
      {
        entry: bridgeEntrySummary(entry, sent),
        recommendation: { id: sent.id, status: sent.status },
      },
      { status: 201, headers: NO_STORE },
    );
  } catch (error) {
    if (error instanceof LabError) {
      return NextResponse.json({ error: error.message }, { status: 400, headers: NO_STORE });
    }
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Bridge queue failed: ${message}` },
      { status: 500, headers: NO_STORE },
    );
  }
}
