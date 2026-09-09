/**
 * The agent loop: stream GLM completions, execute tool calls, feed results
 * back, repeat until a final answer or the step budget runs out. Everything
 * is pushed to the client through the `emit` callback as SSE events.
 *
 * Protocol events (all JSON, one per SSE data: line):
 *   meta {model, tools}                      — turn header
 *   status {text}                            — retry/backoff notices
 *   delta {text}                             — assistant text chunk
 *   reasoning {text}                         — thinking-phase chunk (if any)
 *   tool_call {id, name, args}               — tool invocation started
 *   tool_result {id, name, ok, durationMs, preview, images}
 *   turn_done {messages: [...]}              — protocol messages to append
 *   error {message}
 *   done {finish}
 */
import { getZai, getZaiFallback, getZaiSelfHosted, selfHostedConfigured } from "./config";
import { buildSystemPrompt, toolsForModel } from "./prompt";
import { TOOL_DEFS, executeTool, toolAvailability, ToolCtx } from "./tools";

export type ChatMsg = {
  role: "system" | "user" | "assistant" | "tool";
  content?: string;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
};

const MAX_STEPS = 16;
const MAX_MESSAGES = 80;
const RETRY_DELAYS_MS = [4000, 8000, 15000];

// Circuit-breaker state for a network-dead primary gateway (module scope —
// shared across requests in the same serverless instance).
let primaryNetDeadUntil = 0;
const PRIMARY_NET_DEAD_COOLDOWN_MS = 120_000;

// Circuit breaker for the self-hosted (Modal) backend — independent cooldown.
let selfHostedDeadUntil = 0;
const SELF_HOSTED_DEAD_COOLDOWN_MS = 120_000;

type Emit = (ev: Record<string, unknown>) => void;

function sanitizeHistory(messages: unknown[]): ChatMsg[] {
  const out: ChatMsg[] = [];
  for (const m of messages.slice(-MAX_MESSAGES)) {
    if (!m || typeof m !== "object") continue;
    const r = (m as { role?: unknown }).role;
    if (r !== "user" && r !== "assistant" && r !== "tool") continue;
    const msg = m as ChatMsg;
    const c = typeof msg.content === "string" ? msg.content.slice(0, 40000) : undefined;
    if (r === "user") out.push({ role: "user", content: c ?? "" });
    if (r === "assistant") {
      const tc = Array.isArray(msg.tool_calls)
        ? msg.tool_calls
            .filter((t) => t?.id && t?.function?.name)
            .map((t) => ({
              id: String(t.id).slice(0, 120),
              type: "function" as const,
              function: { name: String(t.function.name).slice(0, 80), arguments: String(t.function.arguments ?? "{}").slice(0, 20000) },
            }))
        : undefined;
      out.push({ role: "assistant", content: c, ...(tc ? { tool_calls: tc } : {}) });
    }
    if (r === "tool" && msg.tool_call_id) {
      out.push({ role: "tool", tool_call_id: String(msg.tool_call_id).slice(0, 120), content: c ?? "" });
    }
  }
  return out;
}

/** Parse the SDK's raw SSE string stream into JSON objects. */
async function* sseObjects(stream: AsyncIterable<unknown>, signal: AbortSignal) {
  let pending = "";
  for await (const chunk of stream as AsyncIterable<string | Uint8Array>) {
    if (signal.aborted) return;
    const s = typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("utf-8");
    pending += s;
    const lines = pending.split("\n");
    pending = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const d = t.slice(5).trim();
      if (!d || d === "[DONE]") continue;
      try {
        yield JSON.parse(d) as Record<string, unknown>;
      } catch {
        /* tolerate partial noise */
      }
    }
  }
}

async function createCompletion(
  body: Record<string, unknown>,
  emit: Emit,
  signal: AbortSignal
): Promise<AsyncIterable<unknown> | Record<string, unknown>> {
  // Circuit breaker: after a network-class primary failure (e.g. the
  // internal gateway being permanently unreachable from Vercel), skip the
  // doomed ~10s fetch timeout on subsequent turns for a cooldown window.
  const skipPrimary = Date.now() < primaryNetDeadUntil;
  const primary = skipPrimary ? null : await getZai().catch((e) => {
    if (primaryDead(e)) {
      primaryNetDeadUntil = Date.now() + PRIMARY_NET_DEAD_COOLDOWN_MS;
      return null;
    }
    throw e;
  });
  let lastErr: unknown = null;

  const run = async (
    client: Awaited<ReturnType<typeof getZai>>,
    b: Record<string, unknown>,
    tag: string
  ): Promise<AsyncIterable<unknown> | Record<string, unknown>> => {
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
      if (signal.aborted) throw new Error("aborted");
      try {
        return await client.chat.completions.create(b as never);
      } catch (e) {
        lastErr = e;
        const msg = String(e);
        const retriable = /429|rate|timeout|502|503|ECONN/i.test(msg);
        if (!retriable || attempt === RETRY_DELAYS_MS.length) throw e;
        const wait = RETRY_DELAYS_MS[attempt];
        emit({ type: "status", text: `${tag} busy (attempt ${attempt + 1}/${RETRY_DELAYS_MS.length + 1}) — retrying in ${wait / 1000}s` });
        await new Promise((r) => setTimeout(r, wait));
      }
    }
    throw lastErr;
  };

  // Self-hosted model backend (operator's Modal vLLM endpoint) — tried first
  // when configured: fully independent of Z.ai quotas. It serves ONE model
  // id; a request for another id 404s here and falls through to the chain.
  if (selfHostedConfigured() && Date.now() >= selfHostedDeadUntil) {
    const sh = await getZaiSelfHosted();
    if (sh) {
      try {
        return await run(sh, body, "self-hosted");
      } catch (e) {
        if (signal.aborted) throw e;
        const msg = String(e);
        const transient = /429|rate|502|503|504|timeout/i.test(msg);
        const dead = /fetch failed|ENOTFOUND|ECONNREFUSED|EAI_AGAIN|ECONN|network|timeout|404|not found|no such model/i.test(msg);
        if (dead) selfHostedDeadUntil = Date.now() + SELF_HOSTED_DEAD_COOLDOWN_MS;
        if (!dead && !transient) throw e; // auth/validation errors surface directly
        emit({ type: "status", text: "self-hosted model backend unavailable — continuing on the standard chain" });
      }
    }
  }

  // Network-class failure (e.g. the internal gateway being unreachable from
  // Vercel, or no primary config at all) is as fatal to the primary as a rate
  // limit: fall through to the fallback credential instead of surfacing fetch
  // errors to the user.
  const primaryDead = (e: unknown) =>
    /429|rate|fetch failed|ENOTFOUND|ECONNREFUSED|EAI_AGAIN|ECONN|network|timeout|502|503|no z-ai config/i.test(String(e));

  if (primary) {
    try {
      return await run(primary, body, "gateway");
    } catch (e) {
      if (signal.aborted) throw e;
      if (primaryDead(e)) primaryNetDeadUntil = Date.now() + PRIMARY_NET_DEAD_COOLDOWN_MS;
      else throw e; // auth/validation errors surface directly
    }
  }

  // 429/network-class exhaustion — try the operator's fallback credential
  // (separate quota pool: open-platform key vs the built-in session
  // credential). The open-platform v4 API accepts thinking.type in
  // {enabled, disabled} (NOT low/high/max, despite error 1210's wording —
  // verified empirically: {type:"low"} → 1210, {type:"enabled"} → passes
  // validation) and rejects disabled on glm-5.3 — adapt once on that error.
  const fb = await getZaiFallback();
  if (fb) {
    emit({ type: "status", text: "primary credential unavailable (rate limit or unreachable gateway) — switching to the operator fallback key" });
    const fbRun = async (b: Record<string, unknown>) => {
      try {
        return await fb.chat.completions.create(b as never);
      } catch (e) {
        if (/1210|engages in thinking/.test(String(e))) {
          return await fb.chat.completions.create({ ...b, thinking: { type: "enabled" } } as never);
        }
        throw e;
      }
    };
    try {
      return await fbRun(body);
    } catch (e2) {
      if (signal.aborted) throw e2;
      // Insufficient balance is terminal for BOTH credentials — downgrading
      // the model or retrying cannot fix it; surface it immediately.
      if (/1113|insufficient balance|quota/i.test(String(e2))) throw e2;
      if (!/429|rate|fetch failed|ENOTFOUND|ECONNREFUSED|EAI_AGAIN|network|timeout|502|503/i.test(String(e2))) throw e2;
    }
  }

  // Last resort: downgrade to the fast lane (separate quota class).
  const lane = fb ?? primary;
  if (lane && (body.model === "glm-5.3" || body.model === "glm-5.2")) {
    emit({ type: "status", text: "rate limits persist — finishing this round on glm-5.3-flash" });
    return run(lane, { ...body, model: "glm-5.3-flash" }, "flash");
  }
  throw lastErr ?? new Error("no model backend available (primary unreachable, no fallback credential)");
}

export async function runAgentTurn(opts: {
  history: unknown[];
  model?: string;
  emit: Emit;
  signal: AbortSignal;
}): Promise<void> {
  const { emit, signal } = opts;
  const zai = await getZai();
  const model = opts.model || "glm-5.3";
  const avail = await toolAvailability();
  const tools = toolsForModel(TOOL_DEFS, avail);
  const system = await buildSystemPrompt();

  const history = sanitizeHistory(opts.history);
  const messages: ChatMsg[] = [{ role: "system", content: system }, ...history];
  const turnMessages: ChatMsg[] = []; // protocol messages added this turn

  emit({ type: "meta", model, tools: tools.map((t) => (t as { function: { name: string } }).function.name) });

  const ctx: ToolCtx = { emit, shots: new Map(), abort: signal };

  for (let step = 0; step <= MAX_STEPS; step++) {
    if (signal.aborted) {
      emit({ type: "status", text: "stopped by operator" });
      break;
    }

    const isLastStep = step === MAX_STEPS;
    const body: Record<string, unknown> = {
      model,
      messages,
      stream: true,
      tools,
      tool_choice: "auto",
    };
    if (isLastStep) {
      // final step: force a plain answer, no more tool calls
      delete body.tools;
      delete body.tool_choice;
      messages.push({
        role: "user",
        content: "Step budget reached — wrap up now with your best final answer using what you have. No more tool calls.",
      });
    }

    let text = "";
    let reasoning = "";
    let finish: string | null = null;
    const toolCallMap = new Map<number, { id: string; name: string; args: string }>();

    const stream = (await createCompletion(body, emit, signal)) as AsyncIterable<unknown>;
    try {
      for await (const j of sseObjects(stream, signal)) {
        const choice = (j as { choices?: { delta?: Record<string, unknown>; finish_reason?: string }[] }).choices?.[0];
        if (!choice) continue;
        const d = choice.delta ?? {};
        if (typeof d.content === "string" && d.content) {
          text += d.content;
          emit({ type: "delta", text: d.content });
        }
        const rc = (d as { reasoning_content?: string }).reasoning_content;
        if (typeof rc === "string" && rc) {
          reasoning += rc;
          emit({ type: "reasoning", text: rc });
        }
        const tcs = (d as { tool_calls?: { index?: number; id?: string; function?: { name?: string; arguments?: string } }[] }).tool_calls;
        if (Array.isArray(tcs)) {
          for (const tc of tcs) {
            const idx = tc.index ?? 0;
            const cur = toolCallMap.get(idx) ?? { id: "", name: "", args: "" };
            if (tc.id) cur.id = tc.id;
            if (tc.function?.name) cur.name = tc.function.name;
            if (tc.function?.arguments) cur.args += tc.function.arguments;
            toolCallMap.set(idx, cur);
          }
        }
        if (choice.finish_reason) finish = choice.finish_reason;
      }
    } catch (e) {
      if (signal.aborted) {
        break;
      }
      emit({ type: "status", text: `stream error: ${String(e).slice(0, 160)} — finishing with partial output` });
    }

    const calls = [...toolCallMap.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);

    if (calls.length && finish === "tool_calls") {
      const assistantMsg: ChatMsg = {
        role: "assistant",
        content: text || undefined,
        tool_calls: calls.map((c) => ({
          id: c.id || `call_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          type: "function" as const,
          function: { name: c.name, arguments: c.args || "{}" },
        })),
      };
      messages.push(assistantMsg);
      turnMessages.push(assistantMsg);

      for (const c of calls) {
        if (signal.aborted) break;
        const id = c.id || `call_${Date.now()}`;
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(c.args || "{}");
        } catch {
          emit({ type: "status", text: `malformed tool args for ${c.name} — skipping` });
        }
        emit({ type: "tool_call", id, name: c.name, args });
        const t0 = Date.now();
        const result = await executeTool(c.name, args, ctx);
        const durationMs = Date.now() - t0;
        const toolMsg: ChatMsg = { role: "tool", tool_call_id: id, content: result.content.slice(0, 40000) };
        messages.push(toolMsg);
        turnMessages.push(toolMsg);
        emit({
          type: "tool_result",
          id,
          name: c.name,
          ok: !/^TOOL UNAVAILABLE|^tool .* failed|unknown tool/.test(result.content),
          durationMs,
          preview: result.content.slice(0, 1200),
          images: result.display?.images ?? [],
        });
      }
      continue; // next round
    }

    // final answer
    if (text || !calls.length) {
      if (text) {
        const finalMsg: ChatMsg = { role: "assistant", content: text };
        turnMessages.push(finalMsg);
      }
    }
    break;
  }

  emit({ type: "turn_done", messages: turnMessages });
  emit({ type: "done" });
}
