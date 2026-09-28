import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  const checks: Record<string, unknown> = {
    host: "my-project :3000 — WebFlix Productionization Mission Control",
    missionState: "unknown",
    monorepo: "unknown",
  };
  try {
    await readFile(path.join(process.cwd(), "data", "mission-state.json"), "utf8");
    checks.missionState = "ok";
  } catch {
    checks.missionState = "missing";
  }
  try {
    const stat = await readFile(path.join(process.cwd(), "webflix", "package.json"), "utf8");
    checks.monorepo = JSON.parse(stat).name === "webflix" ? "ok (@wfx workspace linked)" : "unexpected";
  } catch {
    checks.monorepo = "missing";
  }
  return NextResponse.json({ ok: true, ...checks });
}
