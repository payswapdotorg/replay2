import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { parseJsonValue, runSummaryFromRow } from "../../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const run = await db.labRun.findUnique({ where: { id } });
  if (!run) {
    return NextResponse.json(
      { error: `Lab run "${id}" not found` },
      { status: 404, headers: NO_STORE },
    );
  }
  const recommendation = await db.labRecommendation.findFirst({
    where: { runId: run.id },
    orderBy: { createdAt: "desc" },
  });
  const seeds: unknown = parseJsonValue(run.seeds);
  return NextResponse.json(
    {
      run: {
        ...runSummaryFromRow(run),
        seeds: Array.isArray(seeds) ? seeds : [],
        error: run.error,
      },
      artifact: parseJsonValue(run.artifact),
      recommendation: recommendation === null ? null : parseJsonValue(recommendation.artifact),
    },
    { headers: NO_STORE },
  );
}
