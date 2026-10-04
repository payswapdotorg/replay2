import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recommendationSummaryFromRow } from "../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export async function GET() {
  const rows = await db.labRecommendation.findMany({
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  return NextResponse.json(
    { recommendations: rows.map(recommendationSummaryFromRow) },
    { headers: NO_STORE },
  );
}
