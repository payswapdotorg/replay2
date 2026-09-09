/**
 * Tool registry for the replay agent.
 *
 * Two tiers:
 *   LOCAL   — bash / files / replay browser / worker dispatch. Available on
 *             self-hosted deployments (the sandbox). On serverless (Vercel)
 *             they report unavailability instead of failing silently.
 *   CLOUD   — web search, page reader, image gen/search/edit, vision.
 *             Same behavior everywhere the SDK config resolves.
 *
 * Every executor returns { content } (string for the model) plus optional
 * { display } payloads (images / pretty text) that stream to the console UI.
 */
import { spawn } from "child_process";
import { promises as fsp, accessSync, constants as fsConstants } from "fs";
import { join, isAbsolute, resolve as resolvePath } from "path";
import { getZai, VISION_MODEL } from "./config";
import { getSkill } from "./skills";
import { composioAvailable, composioCall } from "./composio";
import { e2bAvailable, e2bRunCommand, e2bRunPython } from "./e2b";
import { REPLAYD_URL } from "@/lib/replay";

// ------------------------------------------------------------------ types

export type ToolCtx = {
  emit: (ev: Record<string, unknown>) => void;
  shots: Map<string, string>; // shot://N -> data URL
  abort: AbortSignal;
};

export type ToolResult = {
  content: string;
  display?: { images?: string[]; text?: string };
};

export type ToolDef = {
  name: string;
  availability: "local" | "cloud";
  description: string;
  parameters: Record<string, unknown>;
};

// ------------------------------------------------------------- capability

const ROOT = process.cwd();

let fsOkCache: boolean | null = null;
export function fsAvailable(): boolean {
  if (fsOkCache !== null) return fsOkCache;
  try {
    accessSync(ROOT, fsConstants.W_OK);
    fsOkCache = true;
  } catch {
    fsOkCache = false;
  }
  return fsOkCache;
}

let replaydCache: { ok: boolean; at: number } | null = null;
export async function replaydAvailable(): Promise<boolean> {
  const now = Date.now();
  if (replaydCache && now - replaydCache.at < 15000) return replaydCache.ok;
  let ok = false;
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 1500);
    const r = await fetch(`${REPLAYD_URL}/healthz`, { signal: ctl.signal, cache: "no-store" });
    clearTimeout(t);
    ok = r.ok;
  } catch {
    ok = false;
  }
  replaydCache = { ok, at: now };
  return ok;
}

async function sdkOk(): Promise<boolean> {
  try {
    await getZai();
    return true;
  } catch {
    return false;
  }
}

export async function toolAvailability(): Promise<Record<string, boolean>> {
  const [replayd, sdk] = await Promise.all([replaydAvailable(), sdkOk()]);
  const fs = fsAvailable();
  const comp = composioAvailable();
  return {
    bash: fs,
    read_file: fs,
    write_file: fs,
    list_dir: fs,
    browser: replayd,
    dispatch_session: fs && replayd,
    web_search: sdk,
    read_web_page: sdk,
    generate_image: sdk,
    search_images: sdk,
    edit_image: sdk,
    analyze_image: sdk,
    load_skill: true,
    remote_bash: e2bAvailable() || comp,
    remote_python: e2bAvailable() || comp,
  };
}

// ------------------------------------------------------------------ defs

export const TOOL_DEFS: ToolDef[] = [
  {
    name: "bash",
    availability: "local",
    description:
      "Run a shell command in the deployment repo root (self-hosted only). Returns stdout+stderr. Use for: file inspection, git, curl checks, process/port status, package installs, dev servers. Not available on serverless hosts.",
    parameters: {
      type: "object",
      properties: {
        command: { type: "string", description: "shell command to run" },
        timeout_ms: { type: "number", description: "max wait, default 60000, max 180000" },
      },
      required: ["command"],
    },
  },
  {
    name: "read_file",
    availability: "local",
    description: "Read a text file (self-hosted only). Paths are repo-relative or absolute.",
    parameters: {
      type: "object",
      properties: { path: { type: "string", description: "file path" } },
      required: ["path"],
    },
  },
  {
    name: "write_file",
    availability: "local",
    description: "Create or overwrite a file with full contents (self-hosted only). Directories are created automatically.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "file path (repo-relative ok)" },
        content: { type: "string", description: "complete file contents" },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "list_dir",
    availability: "local",
    description: "List a directory (self-hosted only): names, sizes, mtimes.",
    parameters: {
      type: "object",
      properties: { path: { type: "string", description: "directory path, default repo root" } },
      required: [],
    },
  },
  {
    name: "browser",
    availability: "local",
    description:
      "Control the replay browser (the live Chrome the operator sees). Actions: look (screenshot + vision description — your eyes), screenshot, click, domclick, dblclick, drag, type, enter, scroll, nav, reload, dialog, tabs, select_tab, eval, status. Coordinates are fractions fx/fy 0..1 of the viewport. Captchas and logins are always the operator's.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["look", "screenshot", "click", "domclick", "dblclick", "drag", "type", "enter", "scroll", "nav", "reload", "dialog", "tabs", "select_tab", "eval", "status"],
          description: "what to do",
        },
        fx: { type: "number", description: "x fraction 0..1 (click/drag/scroll)" },
        fy: { type: "number", description: "y fraction 0..1" },
        toFx: { type: "number", description: "drag target x fraction" },
        toFy: { type: "number", description: "drag target y fraction" },
        steps: { type: "number", description: "drag interpolation steps, default 24" },
        text: { type: "string", description: "text for type action" },
        deltaY: { type: "number", description: "scroll amount px, default 300" },
        url: { type: "string", description: "url for nav" },
        id: { type: "string", description: "tab id for select_tab" },
        expr: { type: "string", description: "JS expression for eval (returnByValue)" },
        question: { type: "string", description: "focused question for look (vision)" },
      },
      required: ["action"],
    },
  },
  {
    name: "dispatch_session",
    availability: "local",
    description:
      "Manage chat.z.ai AGENT worker sessions (self-hosted only). Sessions are created in the site's AGENTS tab with model GLM-5.3 and skill Full-Stack — enforced by the dispatcher. Actions: create {name, prompt} (opens tab, selects agents-mode/GLM-5.3/Full-Stack, inserts + verifies prompt >=97%, handles sandbox concurrency, sends); list; check {name} (progress); void {name, reason} (nullify + close tab); sandboxes (concurrency state). Prompts must be fully self-contained.",
    parameters: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["create", "list", "check", "void", "sandboxes"], description: "operation" },
        name: { type: "string", description: "session name (slug)" },
        prompt: { type: "string", description: "full self-contained prompt text (create)" },
        reason: { type: "string", description: "why the session is voided (void)" },
      },
      required: ["action"],
    },
  },
  {
    name: "web_search",
    availability: "cloud",
    description: "Search the web. Returns ranked results: title, host, date, url, snippet. Use recency_days for time-sensitive queries.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "search query" },
        num: { type: "number", description: "result count, default 8, max 10" },
        recency_days: { type: "number", description: "only results from the last N days" },
      },
      required: ["query"],
    },
  },
  {
    name: "read_web_page",
    availability: "cloud",
    description: "Extract the readable text of a web page (title + body, cleaned). Read before citing.",
    parameters: {
      type: "object",
      properties: { url: { type: "string", description: "page url" } },
      required: ["url"],
    },
  },
  {
    name: "generate_image",
    availability: "cloud",
    description: "Generate an image from a text prompt. Displayed inline to the operator.",
    parameters: {
      type: "object",
      properties: {
        prompt: { type: "string", description: "image description" },
        size: { type: "string", enum: ["1024x1024", "1344x768", "768x1344", "864x1152", "1152x864", "1440x720", "720x1440"], description: "default 1024x1024" },
      },
      required: ["prompt"],
    },
  },
  {
    name: "search_images",
    availability: "cloud",
    description: "Search the real web for images. Returns URLs + captions + sources, displayed inline.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "image search query" },
        count: { type: "number", description: "default 6, max 10" },
      },
      required: ["query"],
    },
  },
  {
    name: "edit_image",
    availability: "cloud",
    description: "Edit an existing image (from URL) with a text instruction. Result displayed inline.",
    parameters: {
      type: "object",
      properties: {
        prompt: { type: "string", description: "edit instruction" },
        image_url: { type: "string", description: "source image URL (http/https)" },
        size: { type: "string", enum: ["1024x1024", "1344x768", "768x1344", "864x1152", "1152x864", "1440x720", "720x1440"] },
      },
      required: ["prompt", "image_url"],
    },
  },
  {
    name: "analyze_image",
    availability: "cloud",
    description: "Ask GLM vision about an image: URL, data URL, or shot://N reference from a browser screenshot.",
    parameters: {
      type: "object",
      properties: {
        image_url: { type: "string", description: "image URL, data: URL, or shot://N" },
        question: { type: "string", description: "what to examine, default full description" },
      },
      required: ["image_url"],
    },
  },
  {
    name: "load_skill",
    availability: "cloud",
    description: "Load a full capability playbook: browser-ops, fullstack-dev, web-research, media-tools, resident-ops, chat-playbook.",
    parameters: {
      type: "object",
      properties: { name: { type: "string", description: "skill name from the index" } },
      required: ["name"],
    },
  },
  {
    name: "remote_bash",
    availability: "cloud",
    description:
      "Run a bash command in the persistent E2B remote sandbox (direct E2B_API_KEY preferred; Composio Connect as fallback). Linux, Python 3 + Node available; files persist across calls while the sandbox lives (~180s per command). Use when local bash is offline (serverless) or for heavy/isolated work. IMPORTANT: this is NOT the repo workspace — clone or create files here explicitly (git is available).",
    parameters: {
      type: "object",
      properties: {
        command: { type: "string", description: "bash command (hard 180s limit — split long tasks)" },
      },
      required: ["command"],
    },
  },
  {
    name: "remote_python",
    availability: "cloud",
    description:
      "Execute Python code in the persistent remote Jupyter workbench (same E2B sandbox as remote_bash — imports, variables, files persist across calls). Returns stdout. Ideal for data processing, scripting bulk operations, and multi-step analysis with state.",
    parameters: {
      type: "object",
      properties: {
        code: { type: "string", description: "Python code to execute (state persists between calls)" },
      },
      required: ["code"],
    },
  },
];

// ------------------------------------------------------------- utilities

const UNAVAILABLE = (why: string) =>
  `TOOL UNAVAILABLE: ${why}. ${
    e2bAvailable() || composioAvailable()
      ? "Local surface is offline — use remote_bash / remote_python (persistent E2B sandbox: direct key or Composio fallback) for real execution instead."
      : "This deployment is serverless (no local execution surface). Explain the limitation to the operator and adapt: author code/content in your reply, use the cloud tools (web_search, read_web_page, images, vision), or ask the operator to run the command themselves and paste the output."
  }`;

function cap(s: string, max = 20000, keep = "middle"): string {
  if (s.length <= max) return s;
  const half = Math.floor(max / 2) - 20;
  const head = keep === "middle" ? s.slice(0, half) : s.slice(0, half);
  const tail = s.slice(s.length - half);
  return `${head}\n…[${s.length - max} chars truncated]…\n${tail}`;
}

function safePath(p: string): string {
  const clean = (p || "").trim();
  return isAbsolute(clean) ? resolvePath(clean) : join(ROOT, clean);
}

async function bashExec(command: string, timeoutMs: number, signal: AbortSignal): Promise<{ out: string; code: number | null }> {
  return new Promise((res) => {
    const child = spawn("bash", ["-lc", command], { cwd: ROOT });
    let out = "";
    const onData = (d: Buffer) => {
      out += d.toString("utf-8");
      if (out.length > 400000) child.kill("SIGKILL");
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    const timer = setTimeout(() => child.kill("SIGKILL"), timeoutMs);
    const onAbort = () => {
      child.kill("SIGKILL");
    };
    signal.addEventListener("abort", onAbort, { once: true });
    child.on("close", (code) => {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      res({ out, code });
    });
    child.on("error", (e) => {
      clearTimeout(timer);
      res({ out: out + `\nspawn error: ${e}`, code: -1 });
    });
  });
}

async function replayd(path: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const r = await fetch(`${REPLAYD_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  const text = await r.text();
  try {
    return JSON.parse(text);
  } catch {
    return { ok: false, error: text.slice(0, 500) };
  }
}

// ------------------------------------------------------------- executors

async function visionQ(dataUrl: string, question: string): Promise<string> {
  const zai = await getZai();
  const r = await zai.chat.completions.createVision({
    model: VISION_MODEL,
    messages: [
      {
        role: "user",
        content: [
          { type: "image_url", image_url: { url: dataUrl } },
          { type: "text", text: question },
        ],
      },
    ],
  });
  const msg = r?.choices?.[0]?.message?.content;
  return typeof msg === "string" ? msg : JSON.stringify(msg).slice(0, 3000);
}

async function resolveImageRef(ref: string, ctx: ToolCtx): Promise<string | null> {
  if (!ref) return null;
  if (ref.startsWith("shot://")) {
    const hit = ctx.shots.get(ref);
    return hit ?? null;
  }
  if (ref.startsWith("data:")) return ref;
  if (/^https?:\/\//i.test(ref)) return ref;
  return null;
}

async function execBrowser(args: Record<string, unknown>, ctx: ToolCtx): Promise<ToolResult> {
  const action = String(args.action || "");
  const post = (payload: Record<string, unknown>) =>
    replayd("/event", { method: "POST", body: JSON.stringify(payload) });

  switch (action) {
    case "status": {
      const h = await replayd("/healthz");
      const t = await replayd("/tabs");
      return {
        content: `replayd health: ${JSON.stringify(h)}\ntabs: ${JSON.stringify(t).slice(0, 1500)}`,
      };
    }
    case "tabs":
      return { content: JSON.stringify(await replayd("/tabs")).slice(0, 3000) };
    case "select_tab":
      return { content: JSON.stringify(await replayd("/tabs", { method: "POST", body: JSON.stringify({ id: String(args.id || "") }) })).slice(0, 1000) };
    case "nav":
      return { content: JSON.stringify(await post({ type: "nav", url: String(args.url || "https://chat.z.ai/") })) };
    case "reload":
      return { content: JSON.stringify(await post({ type: "reload" })) };
    case "dialog":
      return { content: JSON.stringify(await post({ type: "dialog" })) };
    case "enter":
      return { content: JSON.stringify(await post({ type: "enter" })) };
    case "type":
      return { content: JSON.stringify(await post({ type: "type", text: String(args.text || "") })) };
    case "scroll":
      return { content: JSON.stringify(await post({ type: "scroll", deltaY: Number(args.deltaY ?? 300), fx: Number(args.fx ?? 0.5), fy: Number(args.fy ?? 0.5) })) };
    case "click":
    case "domclick":
    case "dblclick":
      return { content: JSON.stringify(await post({ type: action, fx: Number(args.fx ?? 0), fy: Number(args.fy ?? 0) })) };
    case "drag": {
      const r = await post({
        type: "drag",
        fromFx: Number(args.fx ?? 0), fromFy: Number(args.fy ?? 0),
        toFx: Number(args.toFx ?? 0), toFy: Number(args.toFy ?? 0),
        steps: Number(args.steps ?? 24),
      });
      return { content: JSON.stringify(r) };
    }
    case "eval":
      return { content: cap(JSON.stringify(await post({ type: "eval", expr: String(args.expr || "") })), 12000) };
    case "screenshot":
    case "look": {
      const r = await fetch(`${REPLAYD_URL}/frame`, { cache: "no-store" });
      if (!r.ok) return { content: `screenshot failed: HTTP ${r.status}` };
      const buf = Buffer.from(await r.arrayBuffer());
      const dataUrl = `data:image/jpeg;base64,${buf.toString("base64")}`;
      const ref = `shot://${ctx.shots.size + 1}`;
      ctx.shots.set(ref, dataUrl);
      if (action === "screenshot") {
        return {
          content: `Screenshot captured: ${ref} (${buf.length} bytes jpeg). Use analyze_image {image_url:"${ref}"} to examine it, or it is displayed to the operator.`,
          display: { images: [dataUrl] },
        };
      }
      // look = screenshot + vision description
      const question = String(args.question || "Describe this browser screenshot factually: which site/page is visible, its current UI state, any dialogs, sliders, captchas, login forms or error messages, and the approximate fx/fy fractions (0-1) of the most important interactive elements.");
      let desc = "";
      try {
        desc = await visionQ(dataUrl, question);
      } catch (e) {
        desc = `(vision analysis failed: ${String(e).slice(0, 200)}) — screenshot stored as ${ref}`;
      }
      return {
        content: `BROWSER VIEW (${ref}):\n${desc}`,
        display: { images: [dataUrl], text: desc },
      };
    }
    default:
      return { content: `unknown browser action: ${action}` };
  }
}

async function execDispatch(args: Record<string, unknown>): Promise<ToolResult> {
  const { execFile } = await import("child_process");
  const { promisify } = await import("util");
  const execFileAsync = promisify(execFile) as unknown as (
    cmd: string,
    a: string[],
    o: Record<string, unknown>
  ) => Promise<{ stdout: string; stderr: string }>;
  const PY = process.env.PYTHON_BIN || "python3";
  const script = join(ROOT, "scripts", "dispatch_worker.py");
  const action = String(args.action || "list");
  try {
    if (action === "create") {
      const name = String(args.name || "").replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 60);
      const prompt = String(args.prompt || "");
      if (!name || !prompt) return { content: "create requires name and prompt" };
      const file = join(ROOT, "scripts", "flags", `dispatch_${name}_${Date.now()}.md`);
      await fsp.mkdir(join(ROOT, "scripts", "flags"), { recursive: true });
      await fsp.writeFile(file, prompt, "utf-8");
      const { stdout, stderr } = await execFileAsync(PY, [script, "create", name, file], { timeout: 240000, maxBuffer: 4 * 1024 * 1024 });
      return { content: cap(`${stdout}\n${stderr}`, 8000) };
    }
    if (action === "check") {
      const name = String(args.name || "");
      if (!name) return { content: "check requires name" };
      const { stdout, stderr } = await execFileAsync(PY, [script, "check", name], { timeout: 60000, maxBuffer: 4 * 1024 * 1024 });
      return { content: cap(`${stdout}\n${stderr}`, 12000) };
    }
    if (action === "void") {
      const name = String(args.name || "");
      if (!name) return { content: "void requires name" };
      const reason = String(args.reason || "not needed");
      const { stdout, stderr } = await execFileAsync(PY, [script, "void", name, reason], { timeout: 60000, maxBuffer: 1024 * 1024 });
      return { content: cap(`${stdout}\n${stderr}`, 6000) };
    }
    if (action === "sandboxes") {
      const { stdout, stderr } = await execFileAsync(PY, [script, "sandboxes"], { timeout: 60000, maxBuffer: 1024 * 1024 });
      return { content: cap(`${stdout}\n${stderr}`, 6000) };
    }
    const { stdout, stderr } = await execFileAsync(PY, [script, "list"], { timeout: 30000, maxBuffer: 1024 * 1024 });
    return { content: cap(`${stdout}\n${stderr}`, 8000) };
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string; message?: string };
    return { content: cap(`dispatch_session failed: ${err.stderr || err.stdout || err.message || String(e)}`, 8000) };
  }
}

function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/tr)\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n\s*\n+/g, "\n\n")
    .trim();
}

// ------------------------------------------------------ remote execution

/** Composio Connect fallback for the remote execution tools. */
async function composioRemote(kind: "bash" | "python", payload: string): Promise<ToolResult | null> {
  if (!composioAvailable()) return null;
  const tool = kind === "bash" ? "COMPOSIO_REMOTE_BASH_TOOL" : "COMPOSIO_REMOTE_WORKBENCH";
  const params = kind === "bash" ? { command: payload } : { code_to_execute: payload };
  try {
    const r = await composioCall(tool, params, 200000);
    if (!r.ok) return { content: `remote_${kind} (composio fallback) failed: ${r.error}` };
    const stdout = String(r.data.stdout ?? "");
    const stderr = String(r.data.stderr ?? "");
    const out = (stdout + (stderr ? `\n[stderr]\n${stderr}` : "")).trim() || "(no output)";
    return { content: cap(out, 20000) };
  } catch (e) {
    return { content: `remote_${kind} (composio fallback) failed: ${String(e).slice(0, 300)}` };
  }
}

/**
 * Dual-backend remote execution: direct E2B (preferred — persistent sandbox
 * via E2B_API_KEY), Composio Connect (fallback). A NON-ZERO exit code is a
 * valid result (shown to the model); only transport-level failures fall
 * through to the composio backend.
 */
async function execRemote(kind: "bash" | "python", payload: string): Promise<ToolResult> {
  const label = `remote_${kind}`;
  if (e2bAvailable()) {
    try {
      const r = kind === "bash" ? await e2bRunCommand(payload) : await e2bRunPython(payload);
      if (r.exitCode !== null) {
        // a real command/cell result (even on error) — surface it directly
        const out = (r.stdout + (r.stderr ? `\n[stderr]\n${r.stderr}` : "")).trim() || "(no output)";
        const label2 = r.exitCode === 0 ? "" : `(exit ${r.exitCode}) `;
        return { content: cap(`${label2}${r.error ? `${r.error}\n` : ""}${out}`, 20000) };
      }
      // transport-level failure (no exit code) — try the composio fallback
      const fb = await composioRemote(kind, payload);
      if (fb && !fb.content.startsWith(`remote_${kind} (composio`)) {
        return { content: `[E2B direct unavailable: ${String(r.error || "transport failure").slice(0, 150)} — composio fallback used]\n${fb.content}` };
      }
      return { content: `${label} failed: ${String(r.error || fb?.content || "E2B transport failure").slice(0, 400)}` };
    } catch (e) {
      const fb = await composioRemote(kind, payload);
      if (fb && !fb.content.startsWith(`remote_${kind} (composio`)) {
        return { content: `[E2B direct failed: ${String(e).slice(0, 150)} — composio fallback used]\n${fb.content}` };
      }
      return { content: `${label} (E2B) failed: ${String(e).slice(0, 400)}` };
    }
  }
  const fb = await composioRemote(kind, payload);
  return fb ?? { content: `${label}: no remote execution backend available` };
}

// ----------------------------------------------------------- entry point

export async function executeTool(
  name: string,
  args: Record<string, unknown>,
  ctx: ToolCtx
): Promise<ToolResult> {
  try {
    switch (name) {
      case "bash": {
        if (!fsAvailable()) return { content: UNAVAILABLE("bash needs a local execution surface") };
        const command = String(args.command || "");
        if (!command.trim()) return { content: "empty command" };
        const timeout = Math.min(180000, Math.max(5000, Number(args.timeout_ms) || 60000));
        const { out, code } = await bashExec(command, timeout, ctx.abort);
        const label = code === 0 ? "" : `(exit ${code}) `;
        return { content: cap(`${label}${out}` || "(no output)", 20000) };
      }
      case "read_file": {
        if (!fsAvailable()) return { content: UNAVAILABLE("read_file needs a local filesystem") };
        const p = safePath(String(args.path || ""));
        try {
          const st = await fsp.stat(p);
          if (st.size > 400000) return { content: `file too large: ${st.size} bytes — read slices with bash (sed/head/tail)` };
          return { content: cap(await fsp.readFile(p, "utf-8"), 20000) };
        } catch (e) {
          return { content: `read_file failed: ${String(e)}` };
        }
      }
      case "write_file": {
        if (!fsAvailable()) return { content: UNAVAILABLE("write_file needs a local filesystem") };
        const p = safePath(String(args.path || ""));
        try {
          await fsp.mkdir(join(p, ".."), { recursive: true });
          const content = String(args.content ?? "");
          await fsp.writeFile(p, content, "utf-8");
          return { content: `wrote ${content.length} bytes to ${p}` };
        } catch (e) {
          return { content: `write_file failed: ${String(e)}` };
        }
      }
      case "list_dir": {
        if (!fsAvailable()) return { content: UNAVAILABLE("list_dir needs a local filesystem") };
        const p = safePath(String(args.path || "."));
        try {
          const entries = await fsp.readdir(p, { withFileTypes: true });
          const lines = entries
            .slice(0, 500)
            .map((e) => `${e.isDirectory() ? "d" : "-"} ${e.name}`)
            .sort();
          return { content: `${p}\n${lines.join("\n")}`.slice(0, 12000) };
        } catch (e) {
          return { content: `list_dir failed: ${String(e)}` };
        }
      }
      case "browser": {
        if (!(await replaydAvailable())) {
          return { content: UNAVAILABLE("browser control needs the local replayd daemon (CDP bridge to the headless Chrome)") };
        }
        return execBrowser(args, ctx);
      }
      case "remote_bash": {
        if (!e2bAvailable() && !composioAvailable()) return { content: UNAVAILABLE("remote_bash needs E2B_API_KEY (direct E2B) or COMPOSIO_API_KEY (Composio Connect)") };
        let command = String(args.command ?? "");
        if (!command.trim()) command = String(args.code ?? ""); // param-slop tolerance
        if (!command.trim()) return { content: "empty command" };
        if (ctx.abort.aborted) return { content: "aborted before start" };
        return execRemote("bash", command);
      }
      case "remote_python": {
        if (!e2bAvailable() && !composioAvailable()) return { content: UNAVAILABLE("remote_python needs E2B_API_KEY (direct E2B) or COMPOSIO_API_KEY (Composio Connect)") };
        let code = String(args.code ?? "");
        if (!code.trim()) code = String(args.command ?? ""); // param-slop tolerance
        if (!code.trim()) return { content: "empty code" };
        if (ctx.abort.aborted) return { content: "aborted before start" };
        return execRemote("python", code);
      }
      case "dispatch_session": {
        if (!fsAvailable() || !(await replaydAvailable())) {
          return { content: UNAVAILABLE("dispatch_session needs the local stack (replayd + dispatch_worker.py)") };
        }
        return execDispatch(args);
      }
      case "web_search": {
        const zai = await getZai();
        const items = await zai.functions.invoke("web_search", {
          query: String(args.query || ""),
          num: Math.min(10, Number(args.num) || 8),
          ...(args.recency_days ? { recency_days: Number(args.recency_days) } : {}),
        });
        const lines = (items || []).map(
          (i: { rank?: number; name?: string; host_name?: string; date?: string; url?: string; snippet?: string }) =>
            `${i.rank ?? "?"}. ${i.name ?? ""} — ${i.host_name ?? ""} (${i.date ?? "?"})\n   ${i.url ?? ""}\n   ${(i.snippet ?? "").slice(0, 200)}`
        );
        return { content: lines.join("\n") || "no results" };
      }
      case "read_web_page": {
        const zai = await getZai();
        const r = await zai.functions.invoke("page_reader", { url: String(args.url || "") });
        const d = r?.data ?? r;
        const title = d?.title ?? "";
        const text = stripHtml(String(d?.html ?? "")).slice(0, 16000);
        return { content: `# ${title}\n${d?.url ?? args.url}\n${d?.publishedTime ? `published: ${d.publishedTime}\n` : ""}\n${text}` };
      }
      case "generate_image": {
        const zai = await getZai();
        const r = await zai.images.generations.create({
          prompt: String(args.prompt || ""),
          size: (args.size as never) || "1024x1024",
        });
        const b64 = r?.data?.[0]?.base64;
        if (!b64) return { content: "image generation returned no data" };
        const url = `data:image/png;base64,${b64}`;
        return {
          content: `Image generated (${args.size || "1024x1024"}), displayed to the operator.`,
          display: { images: [url] },
        };
      }
      case "search_images": {
        const zai = await getZai();
        const r = await zai.images.search.create({
          query: String(args.query || ""),
          count: Math.min(10, Number(args.count) || 6),
        });
        const items = r?.results ?? [];
        const urls: string[] = [];
        const lines: string[] = [];
        for (const it of items) {
          if (it.original_url) {
            urls.push(it.original_url);
            lines.push(`- ${it.caption ?? "(no caption)"} — ${it.source ?? ""} — ${it.original_width ?? "?"}x${it.original_height ?? "?"}\n  ${it.original_url}`);
          }
        }
        return { content: lines.join("\n") || "no results", display: { images: urls.slice(0, 6) } };
      }
      case "edit_image": {
        const zai = await getZai();
        const r = await zai.images.generations.edit({
          prompt: String(args.prompt || ""),
          image: String(args.image_url || ""),
          size: (args.size as never) || "1024x1024",
        });
        const b64 = r?.data?.[0]?.base64;
        if (!b64) return { content: "image edit returned no data" };
        const url = `data:image/png;base64,${b64}`;
        return { content: `Edited image displayed to the operator.`, display: { images: [url] } };
      }
      case "analyze_image": {
        const ref = String(args.image_url || "");
        const resolved = await resolveImageRef(ref, ctx);
        if (!resolved) {
          return { content: `cannot resolve image reference: ${ref}. Use an http(s) URL, data: URL, or shot://N from a browser screenshot.` };
        }
        const answer = await visionQ(resolved, String(args.question || "Describe this image in detail."));
        return { content: answer, display: { images: [resolved].filter((u) => !u.startsWith("shot://")) } };
      }
      case "load_skill": {
        const skill = getSkill(String(args.name || ""));
        if (!skill) return { content: `unknown skill. Available: browser-ops, fullstack-dev, web-research, media-tools, resident-ops, chat-playbook` };
        return { content: skill.body };
      }
      default:
        return { content: `unknown tool: ${name}` };
    }
  } catch (e) {
    return { content: `tool ${name} failed: ${String(e).slice(0, 800)}` };
  }
}
