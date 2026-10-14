import { NextResponse } from "next/server";
import { readMissionState } from "@/lib/mission";

export const dynamic = "force-dynamic";

export async function GET() {
  const state = await readMissionState();
  return NextResponse.json(state, {
    headers: {
      "Cache-Control": "no-store",
      // Console identity for the replay-stack supervisor's console-heal:
      // the durable my-project git carries a LEGACY copy of this console
      // that the platform boots onto :3000 after sandbox recycles — it
      // serves a valid mission body but lacks this header, so the heal
      // evicts it and redeploys THIS console (R17 live-caught 2026-10-14).
      "X-Console-Id": "replay2-playliquid",
    },
  });
}
