/**
 * GET /api/agent/capabilities — what the agent backend can do right now:
 * tool availability (local vs cloud tier), model list, sdk/replayd health.
 * The console header uses this to badge the chat ("full tools" / "cloud").
 */
import { CHAT_MODELS, defaultModel, sdkAvailable } from "@/agent/config";
import { toolAvailability } from "@/agent/tools";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const [avail, sdk] = await Promise.all([toolAvailability(), sdkAvailable()]);
  const localTools = Object.entries(avail).filter(([k, v]) => v && k !== "load_skill" && ["bash", "read_file", "write_file", "list_dir", "browser", "dispatch_session"].includes(k));
  return Response.json(
    {
      ok: true,
      hosting: avail.bash ? "self-hosted" : "serverless",
      sdk: sdk,
      tools: avail,
      local_tool_count: localTools.length,
      models: CHAT_MODELS,
      default_model: defaultModel(),
      ts: Date.now(),
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}
