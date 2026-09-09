/**
 * Composio Connect MCP client — gives the serverless deployment a REAL
 * execution surface: a persistent E2B sandbox (remote bash + python
 * workbench) reached through the operator's Composio consumer key.
 *
 * Auth: x-consumer-api-key header (COMPOSIO_API_KEY env, ck_... key).
 * Transport: MCP Streamable HTTP at https://connect.composio.dev/mcp
 *   (initialize handshake -> mcp-session-id header -> JSON-RPC calls,
 *    responses arrive as SSE `data:` lines or plain JSON).
 *
 * The E2B sandbox is keyed to the consumer key, not the MCP session:
 * files and workbench state persist across calls and cold starts.
 */
const MCP_URL = "https://connect.composio.dev/mcp";

let sessionId: string | null = null;
let sessionAt = 0;
const SESSION_TTL = 25 * 60 * 1000; // re-handshake defensively every 25 min

export function composioAvailable(): boolean {
  return Boolean(process.env.COMPOSIO_API_KEY);
}

async function httpPost(body: Record<string, unknown>, headers: Record<string, string>, timeoutMs: number): Promise<{ text: string; session: string | null }> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(MCP_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        "x-consumer-api-key": process.env.COMPOSIO_API_KEY || "",
        ...headers,
      },
      body: JSON.stringify(body),
      signal: ctl.signal,
      cache: "no-store",
    });
    const text = await r.text();
    const session = r.headers.get("mcp-session-id");
    if (!r.ok) throw new Error(`MCP HTTP ${r.status}: ${text.slice(0, 300)}`);
    return { text, session };
  } finally {
    clearTimeout(timer);
  }
}

function parseMcpMessage(text: string): Record<string, unknown> | null {
  const ct = text.trim();
  if (ct.startsWith("{")) {
    try {
      return JSON.parse(ct);
    } catch {
      return null;
    }
  }
  // SSE frames: take the LAST `data:` line
  let last: string | null = null;
  for (const line of ct.split("\n")) {
    if (line.startsWith("data:")) last = line.slice(5).trim();
  }
  if (last) {
    try {
      return JSON.parse(last);
    } catch {
      return null;
    }
  }
  return null;
}

async function handshake(): Promise<string> {
  const { text, session } = await httpPost(
    {
      jsonrpc: "2.0",
      id: 0,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "replay2-agent", version: "1.0" },
      },
    },
    {},
    30000,
  );
  const msg = parseMcpMessage(text);
  if (!msg || !msg.result) throw new Error(`MCP initialize failed: ${text.slice(0, 200)}`);
  const sid = session || null;
  if (!sid) throw new Error("MCP initialize: no mcp-session-id header");
  await httpPost(
    { jsonrpc: "2.0", method: "notifications/initialized" },
    { "mcp-session-id": sid },
    15000,
  );
  return sid;
}

async function ensureSession(force = false): Promise<string> {
  if (!force && sessionId && Date.now() - sessionAt < SESSION_TTL) return sessionId;
  sessionId = await handshake();
  sessionAt = Date.now();
  return sessionId;
}

export type ComposioResult = {
  ok: boolean;
  data: Record<string, unknown>;
  error?: string;
};

/** Call a Composio meta-tool directly (e.g. COMPOSIO_REMOTE_BASH_TOOL). */
export async function composioCall(
  tool: string,
  args: Record<string, unknown>,
  timeoutMs = 200000,
): Promise<ComposioResult> {
  let sid = await ensureSession();
  let res = await callOnce(tool, args, sid, timeoutMs);
  if (res.staleSession) {
    // session expired — re-handshake once and retry
    sid = await ensureSession(true);
    res = await callOnce(tool, args, sid, timeoutMs);
  }
  if (res.failed) return { ok: false, data: {}, error: res.failed };
  return { ok: true, data: res.data };
}

type CallOutcome = { staleSession?: boolean; failed?: string; data: Record<string, unknown> };

async function callOnce(tool: string, args: Record<string, unknown>, sid: string, timeoutMs: number): Promise<CallOutcome> {
  let out: { text: string; session: string | null };
  try {
    out = await httpPost(
      { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: tool, arguments: args } },
      { "mcp-session-id": sid },
      timeoutMs,
    );
  } catch (e) {
    const msg = String(e);
    if (msg.includes("HTTP 404") || msg.includes("HTTP 401") || msg.includes("abort")) {
      return { staleSession: true, data: {} };
    }
    return { failed: `MCP transport: ${msg.slice(0, 300)}`, data: {} };
  }
  const msg = parseMcpMessage(out.text);
  if (!msg) return { failed: `MCP unparseable: ${out.text.slice(0, 200)}`, data: {} };
  const result = msg.result as Record<string, unknown> | undefined;
  const error = msg.error as { message?: string } | undefined;
  if (error) {
    const m = error.message || JSON.stringify(error);
    if (/invalid session|session not found|expired/i.test(m)) return { staleSession: true, data: {} };
    return { failed: `MCP error: ${m.slice(0, 300)}`, data: {} };
  }
  if (!result) return { failed: "MPC: no result object", data: {} };
  if (result.isError) {
    const content = (result.content as { type?: string; text?: string }[] | undefined)?.[0]?.text || "";
    return { failed: `tool error: ${content.slice(0, 400)}`, data: {} };
  }
  // content[0].text carries the JSON payload {data:..., successful, error}
  const content = (result.content as { type?: string; text?: string }[] | undefined)?.[0]?.text || "{}";
  try {
    const inner = JSON.parse(content) as { data?: Record<string, unknown>; error?: unknown; successful?: boolean };
    if (inner.error) return { failed: `composio: ${String(inner.error).slice(0, 400)}`, data: {} };
    return { data: (inner.data as Record<string, unknown>) || {} };
  } catch {
    return { data: { raw: content.slice(0, 4000) } };
  }
}
