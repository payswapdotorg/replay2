import { NextResponse } from "next/server";
import { getCatalog } from "@/lib/lab/catalog";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(await getCatalog(), {
    headers: { "Cache-Control": "no-store" },
  });
}
