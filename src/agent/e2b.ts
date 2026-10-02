/**
 * Direct E2B code-interpreter tier — the operator's raw E2B key.
 *
 * This is the PREFERRED remote execution surface for the agent chat:
 *   remote_bash  -> shell command in the persistent sandbox
 *   remote_python-> Jupyter cell (state persists across calls)
 * The Composio Connect MCP path (composio.ts) remains the fallback when
 * E2B_API_KEY is absent.
 *
 * Lifecycle: one sandbox per server process, best-effort resume across
 * cold starts via a saved sandbox id (`CodeInterpreter.connect`). A paused
 * or expired sandbox is transparently replaced by a fresh one — command
 * wrappers invalidate the cache and retry exactly once. State (files,
 * python variables) persists while the sandbox lives.
 *
 * Env: E2B_API_KEY (required for this tier — read by the SDK natively, also
 * passed explicitly). Works on Vercel Node runtime: no local fs assumptions
 * (the state file write is best-effort and ignored when read-only).
 */
import { promises as fsp } from "fs";
import { join } from "path";

const ROOT = process.cwd();
const STATE_FILE = join(ROOT, ".data", "e2b-sandbox.json");
const SANDBOX_TIMEOUT_MS = 15 * 60 * 1000; // extend on every successful call
const COMMAND_TIMEOUT_MS = 170 * 1000;

export function e2bAvailable(): boolean {
  return Boolean(process.env.E2B_API_KEY);
}

type SandboxLike = {
  sandboxId?: string;
  runCode?: (code: string, opts?: Record<string, unknown>) => Promise<ExecLike>;
  commands?: { run?: (cmd: string, opts?: Record<string, unknown>) => Promise<CmdLike> };
  setTimeout?: (ms: number) => Promise<void>;
  isRunning?: () => boolean | Promise<boolean>;
  kill?: () => Promise<void>;
};

type ExecLike = {
  results?: unknown[];
  logs?: { stdout?: string[]; stderr?: string[] };
  error?: unknown;
};

type CmdLike = {
  exitCode?: number;
  stdout?: unknown;
  stderr?: unknown;
};

let cached: SandboxLike | null = null;
let connecting: Promise<SandboxLike> | null = null;
let cachedClass: {
  create: (o?: unknown) => Promise<SandboxLike>;
  connect?: (id: string, o?: unknown) => Promise<SandboxLike>;
} | null = null;

/** Resolve the CodeInterpreter class across CJS/ESM bundler interops. */
async function loadSDK(): Promise<NonNullable<typeof cachedClass>> {
  if (cachedClass) return cachedClass;
  const mod = (await import("@e2b/code-interpreter")) as unknown as Record<string, unknown>;
  let CI: unknown = mod.CodeInterpreter ?? mod.default;
  // The ESM build exports {Sandbox, default}; under webpack/turbopack CJS
  // interop mod.default may be the module.exports OBJECT whose .default or
  // .Sandbox is the class — unwrap until something has a static create.
  for (let i = 0; i < 2 && CI && typeof (CI as { create?: unknown }).create !== "function"; i++) {
    CI = (CI as { default?: unknown; Sandbox?: unknown }).default ?? (CI as { Sandbox?: unknown }).Sandbox;
  }
  if (!CI || typeof (CI as { create?: unknown }).create !== "function") {
    throw new Error("E2B SDK: CodeInterpreter class not resolvable");
  }
  cachedClass = CI as unknown as typeof cachedClass;
  return cachedClass as NonNullable<typeof cachedClass>;
}

async function readSavedId(): Promise<string | null> {
  try {
    const d = JSON.parse(await fsp.readFile(STATE_FILE, "utf-8")) as { sandboxId?: string };
    return d.sandboxId || null;
  } catch {
    return null;
  }
}

async function saveId(id: string | undefined): Promise<void> {
  if (!id) return;
  try {
    await fsp.mkdir(join(ROOT, ".data"), { recursive: true });
    await fsp.writeFile(STATE_FILE, JSON.stringify({ sandboxId: id, at: Date.now() }), { mode: 0o600 });
  } catch {
    /* read-only fs (serverless) — resume just won't persist */
  }
}

async function startSandbox(): Promise<SandboxLike> {
  const CI = await loadSDK();
  const opts = { apiKey: process.env.E2B_API_KEY, timeoutMs: SANDBOX_TIMEOUT_MS };
  // best-effort resume: `connect(id)` reattaches to a live sandbox.
  // NOTE: statics must be called ON the class — destructuring them loses the
  // `this` receiver and crashes inside the SDK (defaultTemplate of undefined).
  const saved = await readSavedId();
  if (saved && typeof CI.connect === "function") {
    try {
      const sbx = await CI.connect(saved, opts);
      if (sbx) {
        await saveId(sbx.sandboxId);
        return sbx;
      }
    } catch {
      /* sandbox gone (paused > TTL / expired) — fall through to create */
    }
  }
  const sbx = await CI.create(opts);
  await saveId(sbx.sandboxId);
  return sbx;
}

async function getSandbox(): Promise<SandboxLike> {
  if (cached) return cached;
  if (connecting) return connecting;
  connecting = startSandbox().finally(() => {
    connecting = null;
  });
  return connecting;
}

function invalidate() {
  const old = cached;
  cached = null;
  try {
    old?.kill?.().catch(() => undefined);
  } catch {
    /* best effort */
  }
}

async function extendLife(sbx: SandboxLike) {
  try {
    await sbx.setTimeout?.(SANDBOX_TIMEOUT_MS);
  } catch {
    /* plan cap — default TTL applies */
  }
}

export type E2BResult = {
  ok: boolean;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  error?: string;
};

function textOf(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    const s = String(v);
    return s === "[object Object]" ? JSON.stringify(v) : s;
  } catch {
    return "";
  }
}

/** Run a bash command in the sandbox (native `commands.run` if available,
 *  otherwise a python subprocess wrapper through the Jupyter kernel). */
export async function e2bRunCommand(command: string): Promise<E2BResult> {
  const attempt = async (sbx: SandboxLike): Promise<E2BResult> => {
    if (typeof sbx.commands?.run === "function") {
      const r = await sbx.commands.run(command, { timeoutMs: COMMAND_TIMEOUT_MS });
      const code = typeof r.exitCode === "number" ? r.exitCode : null;
      return { ok: code === 0, stdout: textOf(r.stdout), stderr: textOf(r.stderr), exitCode: code };
    }
    // Jupyter fallback: bash via subprocess — the command is embedded as a
    // JSON string literal, which is also a valid python string literal for
    // every character JSON escapes (fully injection-safe).
    const py = [
      "import subprocess, sys",
      `_r = subprocess.run(["bash","-lc",${JSON.stringify(command)}], capture_output=True, text=True, timeout=165)`,
      "sys.stdout.write(_r.stdout)",
      "sys.stderr.write(_r.stderr)",
      "print(f'\\n[__exit {_r.returncode}]')",
    ].join("\n");
    const cell = await sbx.runCode?.(py, { timeoutMs: COMMAND_TIMEOUT_MS });
    return parseCell(cell);
  };

  const first = await getSandbox();
  try {
    const r = await attempt(first);
    if (!/Sandbox|connection|closed|disconnect|timeout|Timeout/i.test(r.error || "")) {
      await extendLife(first);
      return r;
    }
    throw new Error(r.error || "sandbox connection lost");
  } catch (e) {
    invalidate();
    const second = await getSandbox();
    const r = await attempt(second);
    await extendLife(second);
    return { ...r, error: r.error ? `${String(e).slice(0, 150)} → retried on fresh sandbox: ${r.error}` : String(e).slice(0, 300) };
  }
}

/** Execute a Python cell — imports, variables and files persist across calls. */
export async function e2bRunPython(code: string): Promise<E2BResult> {
  const attempt = (sbx: SandboxLike) => runCell(sbx, code);
  const first = await getSandbox();
  try {
    const r = await attempt(first);
    await extendLife(first);
    return r;
  } catch (e) {
    invalidate();
    const second = await getSandbox();
    const r = await attempt(second);
    await extendLife(second);
    return { ...r, error: r.error ? `${String(e).slice(0, 150)} → retried on fresh sandbox: ${r.error}` : String(e).slice(0, 300) };
  }
}

async function runCell(sbx: SandboxLike, code: string): Promise<E2BResult> {
  const cell = await sbx.runCode?.(code, { timeoutMs: COMMAND_TIMEOUT_MS });
  return parseCell(cell);
}

function parseCell(cell: ExecLike | undefined): E2BResult {
  if (!cell) return { ok: false, stdout: "", stderr: "", exitCode: null, error: "no execution result" };
  const stdout = (cell.logs?.stdout ?? []).join("");
  const stderr = (cell.logs?.stderr ?? []).join("");
  const resultTexts = (cell.results ?? [])
    .map((r) => textOf((r as { text?: unknown }).text ?? r))
    .filter((t) => t && t !== "undefined");
  const errObj = cell.error as { message?: string; value?: string; toString?: () => string } | null | undefined;
  const error = errObj ? (errObj.message || errObj.value || (typeof errObj.toString === "function" ? errObj.toString() : String(errObj))).slice(0, 1500) : undefined;
  const exitMatch = stdout.match(/\n?\[__exit (-?\d+)\]\s*$/);
  const exitCode = exitMatch ? Number(exitMatch[1]) : errObj ? 1 : 0;
  const cleanStdout = stdout.replace(/\n?\[__exit -?\d+\]\s*$/, "");
  return {
    ok: !errObj && exitCode === 0,
    stdout: (resultTexts.length ? `${cleanStdout}${resultTexts.join("\n")}` : cleanStdout).trim(),
    stderr: stderr.trim(),
    exitCode,
    error,
  };
}
