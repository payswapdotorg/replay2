import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { parseJsonValue } from "../../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const recommendation = await db.labRecommendation.findUnique({ where: { id } });
  if (!recommendation) {
    return NextResponse.json(
      { error: `Lab recommendation "${id}" not found` },
      { status: 404, headers: NO_STORE },
    );
  }
  return NextResponse.json(
    {
      id: recommendation.id,
      runId: recommendation.runId,
      status: recommendation.status,
      artifact: parseJsonValue(recommendation.artifact),
      createdAt: recommendation.createdAt.toISOString(),
    },
    { headers: NO_STORE },
  );
}
