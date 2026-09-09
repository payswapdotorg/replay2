/**
 * POST /api/agent/chat — the agent conversation endpoint.
 *
 * Body: { messages: ChatMsg[] (no system), model?, conversation_id? }
 * Response: text/event-stream of agent-loop events (see src/agent/loop.ts).
 *
 * Extra behaviors:
 *  - Vision pre-pass: user messages may carry `images` (data URLs). Each is
 *    described by GLM vision and the descriptions are folded into the text
 *    content before the tool loop starts — works on serverless too.
 *  - Operator-inbox mirroring: on self-hosted deployments the last user text
 *    is appended to scripts/flags/operator_inbox.jsonl (source-tagged) so
 *    the resident CLI agent (if any) stays aware of the conversation.
 *  - Transcript persistence: turns are appended to
 *    .data/agent_sessions/<conversation_id>.jsonl when the FS is writable.
 */
import { promises as fsp } from "fs";
import { join } from "path";
import { getZai, VISION_MODEL, defaultModel } from "@/agent/config";
import { runAgentTurn } from "@/agent/loop";
import { fsAvailable } from "@/agent/tools";
import { FLAGS } from "@/lib/replay";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 800; // Vercel clamps per plan; self-hosted unlimited

type IncomingMsg = {
  role: "user" | "assistant" | "tool";
  content?: string;
  images?: string[];
  tool_calls?: unknown[];
  tool_call_id?: string;
};

const ROOT = process.cwd();

async function visionDescribe(dataUrl: string): Promise<string> {
  const zai = await getZai();
  const r = await zai.chat.completions.createVision({
    model: VISION_MODEL,
    messages: [
      {
        role: "user",
        content: [
          { type: "image_url", image_url: { url: dataUrl } },
          {
            type: "text",
            text: "Extract ALL information from this image that could be relevant to the user's request: text content, UI elements, data values, diagrams, error messages. Be factual and complete.",
          },
        ],
      },
    ],
  });
  const c = r?.choices?.[0]?.message?.content;
  return typeof c === "string" ? c.slice(0, 4000) : "";
}

export async function POST(req: Request) {
  let body: { messages?: IncomingMsg[]; model?: string; conversation_id?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "bad json" }, { status: 400 });
  }
  const model =
    typeof body.model === "string" && /^glm-[0-9a-z.\-]+$/i.test(body.model) ? body.model : defaultModel();
  const conversationId = (body.conversation_id || "default").replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 64) || "default";

  const encoder = new TextEncoder();
  const ctl = new AbortController();
  const onReqAbort = () => ctl.abort();
  req.signal.addEventListener("abort", onReqAbort, { once: true });

  const stream = new ReadableStream({
    async start(controller) {
      let closed = false;
      const send = (obj: Record<string, unknown>) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
        } catch {
          closed = true;
        }
      };

      try {
        // ---- vision pre-pass for image attachments on the last user message
        const history = [...(body.messages ?? [])];
        const lastUser = [...history].reverse().find((m) => m.role === "user");
        if (lastUser && Array.isArray(lastUser.images) && lastUser.images.length) {
          const descriptions: string[] = [];
          for (const img of lastUser.images.slice(0, 4)) {
            if (typeof img !== "string" || !img.startsWith("data:")) continue;
            try {
              send({ type: "status", text: "analyzing attached image…" });
              const d = await visionDescribe(img);
              if (d) descriptions.push(d);
            } catch (e) {
              descriptions.push(`(image analysis failed: ${String(e).slice(0, 120)})`);
            }
          }
          if (descriptions.length) {
            lastUser.content = `${lastUser.content ?? ""}\n\n[attached image${descriptions.length > 1 ? "s" : ""} — vision extraction]\n${descriptions
              .map((d, i) => `image ${i + 1}: ${d}`)
              .join("\n\n")}`.trim();
          }
          lastUser.images = undefined;
        }

        // ---- mirror last user text to the resident operator inbox
        if (fsAvailable() && lastUser?.content) {
          try {
            const line =
              JSON.stringify({
                ts: Date.now(),
                from: "operator",
                source: "agent-chat",
                text: String(lastUser.content).slice(0, 2000),
              }) + "\n";
            await fsp.appendFile(join(FLAGS, "operator_inbox.jsonl"), line, "utf-8");
          } catch {
            /* best effort */
          }
        }

        // ---- run the agent loop
        await runAgentTurn({ history, model, emit: send, signal: ctl.signal });
      } catch (e) {
        send({ type: "error", message: String(e).slice(0, 500) });
        send({ type: "done" });
      } finally {
        // ---- persist transcript (best effort, local)
        if (fsAvailable()) {
          try {
            const dir = join(ROOT, ".data", "agent_sessions");
            await fsp.mkdir(dir, { recursive: true });
            const entry =
              JSON.stringify({
                ts: Date.now(),
                conversation_id: conversationId,
                model,
                turn: (body.messages ?? []).slice(-3),
              }) + "\n";
            await fsp.appendFile(join(dir, `${conversationId}.jsonl`), entry, "utf-8");
          } catch {
            /* best effort */
          }
        }
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      }
    },
    cancel() {
      ctl.abort();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
