import { NextResponse } from "next/server";
import { readMissionState } from "@/lib/mission";

export const dynamic = "force-dynamic";

export async function GET() {
  const state = await readMissionState();
  return NextResponse.json(state, {
    headers: { "Cache-Control": "no-store" },
  });
}
