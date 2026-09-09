/**
 * Agent backend config — resolves the z-ai-web-dev-sdk client.
 *
 * Resolution order:
 *   1. ZAI_BASE_URL + ZAI_API_KEY env vars (the Vercel/serverless path)
 *      → materialized as <cwd>/.z-ai-config so the SDK can pick it up.
 *   2. Existing .z-ai-config in cwd / home / /etc (the sandbox path).
 *
 * The SDK (z-ai-web-dev-sdk) is the same engine that powers the Z.ai chat
 * product: GLM models with streaming + native tool calling, plus search,
 * page-reader, image generation/edit/search, vision, TTS/ASR endpoints.
 */
import { promises as fsp } from "fs";
import { join } from "path";
import os from "os";
import ZAI from "z-ai-web-dev-sdk";

let cached: ZAI | null = null;
let cachedError: string | null = null;
let lastFailAt = 0;
const FAIL_COOLDOWN_MS = 5000;

async function writeEnvConfig(): Promise<boolean> {
  const baseUrl = process.env.ZAI_BASE_URL;
  const apiKey = process.env.ZAI_API_KEY;
  if (!baseUrl || !apiKey) return false;
  const cfg: Record<string, string> = { baseUrl, apiKey };
  if (process.env.ZAI_CHAT_ID) cfg.chatId = process.env.ZAI_CHAT_ID;
  if (process.env.ZAI_USER_ID) cfg.userId = process.env.ZAI_USER_ID;
  if (process.env.ZAI_TOKEN) cfg.token = process.env.ZAI_TOKEN;
  const payload = JSON.stringify(cfg);
  // Serverless (Vercel/Lambda): cwd is the read-only bundle and HOME may be
  // unwritable — redirect HOME to /tmp (the only writable path) and write
  // there. The SDK resolves <homedir>/.z-ai-config, so it finds it.
  const serverless = Boolean(process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME);
  const candidates = [
    join(process.cwd(), ".z-ai-config"),
    join(os.homedir(), ".z-ai-config"),
  ];
  if (serverless) {
    process.env.HOME = "/tmp";
    candidates.push("/tmp/.z-ai-config");
  }
  for (const p of candidates) {
    try {
      const raw = JSON.parse(await fsp.readFile(p, "utf-8"));
      if (raw?.baseUrl === baseUrl && raw?.apiKey === apiKey) return true; // already current
    } catch {
      /* write below */
    }
    try {
      await fsp.writeFile(p, payload, { mode: 0o600 });
      return true;
    } catch {
      /* next candidate */
    }
  }
  return false;
}

async function findFileConfig(): Promise<boolean> {
  const paths = [
    join(process.cwd(), ".z-ai-config"),
    join(os.homedir(), ".z-ai-config"),
    "/tmp/.z-ai-config",
    "/etc/.z-ai-config",
  ];
  for (const p of paths) {
    try {
      const raw = JSON.parse(await fsp.readFile(p, "utf-8"));
      if (raw?.baseUrl && raw?.apiKey) return true;
    } catch {
      /* next */
    }
  }
  return false;
}

export async function getZai(): Promise<ZAI> {
  if (cached) return cached;
  // transient failures (bundling races, cold fs) deserve a retry after a
  // cooldown — never cache an error forever per route-bundle.
  if (cachedError && Date.now() - lastFailAt < FAIL_COOLDOWN_MS) {
    throw new Error(cachedError);
  }
  try {
    await writeEnvConfig();
    const ok = await findFileConfig();
    if (!ok) {
      throw new Error(
        "No z-ai config: set ZAI_BASE_URL + ZAI_API_KEY env vars (serverless) or provide .z-ai-config (self-hosted)."
      );
    }
    cached = await ZAI.create();
    cachedError = null;
    return cached;
  } catch (e) {
    cachedError = String(e);
    lastFailAt = Date.now();
    throw e;
  }
}

export async function sdkAvailable(): Promise<boolean> {
  try {
    await getZai();
    return true;
  } catch {
    return false;
  }
}

/** Chat models offered in the console model picker (validated names). */
export const CHAT_MODELS = [
  { id: "glm-5.3", label: "GLM-5.3", note: "flagship · coding + long-horizon" },
  { id: "glm-5.3-flash", label: "GLM-5.3-Flash", note: "fast · everyday tasks" },
  { id: "glm-5.2", label: "GLM-5.2", note: "previous flagship" },
  { id: "glm-4.6", label: "GLM-4.6", note: "stable classic" },
] as const;

export const VISION_MODEL = "glm-4.6v";

export function defaultModel(): string {
  const m = process.env.AGENT_MODEL;
  if (m && CHAT_MODELS.some((c) => c.id === m)) return m;
  return "glm-5.3";
}
