/**
 * E2B desktop sandbox + Chrome + CDP — the remote browser tier.
 *
 * Gives serverless deployments (Vercel) the browser tool the resident
 * sandbox has: one persistent E2B *desktop* sandbox (Xfce) per process,
 * with a headful Chrome driven through the Chrome DevTools Protocol,
 * reached via E2B's port forwarding (`getHost(9222)` → public HTTPS/WSS).
 *
 * Why CDP instead of GUI xdotool: precise coordinates, DOM text and
 * element extraction (text-only grounding — no vision required), fast
 * screenshots — while the GUI desktop stays intact for live streaming
 * (the operator can watch the agent browse via the E2B stream URL).
 *
 * Lifecycle mirrors e2b.ts: module cache + best-effort resume via
 * .data/browser-sandbox.json (transparently replaced when expired),
 * TTL extended on every call, invalidate-and-retry-once on connection
 * loss. Chrome itself is (re)launched in the sandbox on demand.
 *
 * Env: E2B_API_KEY. Serverless-safe: no local fs assumptions (state
 * write is best-effort), Node ≥18 (fetch), WebSocket via global or 'ws'.
 */
import { promises as fsp } from "fs";
import { join } from "path";

const ROOT = process.cwd();
const STATE_FILE = join(ROOT, ".data", "browser-sandbox.json");
const SANDBOX_TTL_MS = 15 * 60 * 1000;
const CDP_TIMEOUT_MS = 15 * 1000;
const NAV_TIMEOUT_MS = 25 * 1000;
const CHROME_PORT = 9222;
const PROXY_PORT = 9223; // nginx: Host-rewrite proxy (Chrome rejects non-localhost Host headers,
//                          and the E2B port-forward routes BY Host — so it cannot be overridden client-side)

export function browserRemoteAvailable(): boolean {
  return Boolean(process.env.E2B_API_KEY);
}

// ------------------------------------------------------------------ types

type DesktopSandbox = {
  sandboxId?: string;
  commands?: { run?: (cmd: string, opts?: Record<string, unknown>) => Promise<{ exitCode?: number; stdout?: unknown; stderr?: unknown }> };
  setTimeout?: (ms: number) => Promise<void>;
  getHost?: (port: number) => string;
  isRunning?: () => boolean | Promise<boolean>;
  kill?: () => Promise<void>;
  getScreenSize?: () => Promise<{ width: number; height: number }>;
  screenshot?: () => Promise<Buffer>;
};

export type BrowserRemoteResult = {
  content: string;
  images?: string[]; // data URLs for the console UI
  error?: string;
};

// ------------------------------------------------------- sandbox lifecycle

let cached: DesktopSandbox | null = null;
let connecting: Promise<DesktopSandbox> | null = null;
let cachedClass: { create: (o?: unknown) => Promise<DesktopSandbox>; connect?: (id: string, o?: unknown) => Promise<DesktopSandbox> } | null = null;

export async function loadSDK(): Promise<NonNullable<typeof cachedClass>> {
  if (cachedClass) return cachedClass;
  const mod = (await import("@e2b/desktop")) as unknown as Record<string, unknown>;
  let D: unknown = mod.Sandbox ?? mod.default;
  for (let i = 0; i < 2 && D && typeof (D as { create?: unknown }).create !== "function"; i++) {
    D = (D as { default?: unknown; Sandbox?: unknown }).default ?? (D as { Sandbox?: unknown }).Sandbox;
  }
  if (!D || typeof (D as { create?: unknown }).create !== "function") {
    throw new Error("E2B desktop SDK: Sandbox class not resolvable");
  }
  cachedClass = D as unknown as typeof cachedClass;
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
    const dir = join(ROOT, ".data");
    await fsp.mkdir(dir, { recursive: true });
    const serverless = Boolean(process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME);
    const p = serverless ? join("/tmp", "browser-sandbox.json") : STATE_FILE;
    await fsp.writeFile(p, JSON.stringify({ sandboxId: id, at: Date.now() }), { mode: 0o600 });
    if (serverless) {
      try {
        await fsp.mkdir(join(ROOT, ".data"), { recursive: true });
        await fsp.writeFile(STATE_FILE, JSON.stringify({ sandboxId: id, at: Date.now() }), { mode: 0o600 });
      } catch { /* best effort */ }
    }
  } catch {
    /* read-only fs — resume just won't persist */
  }
}

async function readSavedIdAny(): Promise<string | null> {
  const a = await readSavedId();
  if (a) return a;
  try {
    const d = JSON.parse(await fsp.readFile(join("/tmp", "browser-sandbox.json"), "utf-8")) as { sandboxId?: string };
    return d.sandboxId || null;
  } catch {
    return null;
  }
}

async function startSandbox(): Promise<DesktopSandbox> {
  const D = await loadSDK();
  const opts = { apiKey: process.env.E2B_API_KEY, timeoutMs: SANDBOX_TTL_MS };
  const saved = await readSavedIdAny();
  if (saved && typeof D.connect === "function") {
    try {
      const sbx = await D.connect(saved, opts);
      if (sbx) {
        await saveId(sbx.sandboxId);
        return sbx;
      }
    } catch {
      /* expired — create fresh */
    }
  }
  const sbx = await D.create(opts);
  await saveId(sbx.sandboxId);
  return sbx;
}

async function getSandbox(): Promise<DesktopSandbox> {
  if (cached) return cached;
  if (connecting) return connecting;
  connecting = startSandbox().finally(() => {
    connecting = null;
  });
  return connecting;
}

async function invalidateSandbox() {
  const old = cached;
  cached = null;
  cdp = null;
  page = null;
  try {
    old?.kill?.().catch(() => undefined);
  } catch { /* best effort */ }
}

async function extendLife(sbx: DesktopSandbox) {
  try {
    await sbx.setTimeout?.(SANDBOX_TTL_MS);
  } catch { /* plan cap */ }
}

function run(sbx: DesktopSandbox, cmd: string, timeoutMs = 60_000) {
  if (typeof sbx.commands?.run !== "function") throw new Error("desktop sandbox: commands.run unavailable");
  return sbx.commands.run(cmd, { timeoutMs });
}

// ------------------------------------------------------------- CDP client

type WsLike = {
  send: (data: string) => void;
  close: () => void;
  onMessage: (cb: (data: string) => void) => void;
  onClose: (cb: () => void) => void;
};

async function openSocket(url: string, timeoutMs = 8000): Promise<WsLike> {
  const GW = (globalThis as { WebSocket?: unknown }).WebSocket;
  if (typeof GW === "function") {
    return await new Promise<WsLike>((resolve, reject) => {
      const ws = new (GW as new (u: string) => { send: (d: string) => void; close: () => void; addEventListener: (t: string, cb: (ev: { data?: unknown }) => void) => void })(url);
      const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error("ws open timeout")); }, timeoutMs);
      ws.addEventListener("open", () => { clearTimeout(timer); resolve(wrap()); });
      ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("ws error")); });
      const listeners: ((d: string) => void)[] = [];
      const closers: (() => void)[] = [];
      ws.addEventListener("message", (ev) => { const d = typeof ev.data === "string" ? ev.data : Buffer.from(ev.data as ArrayBuffer).toString(); for (const l of listeners) l(d); });
      ws.addEventListener("close", () => { for (const c of closers) c(); });
      const wrap = (): WsLike => ({
        send: (d) => ws.send(d),
        close: () => ws.close(),
        onMessage: (cb) => listeners.push(cb),
        onClose: (cb) => closers.push(cb),
      });
    });
  }
  // Node <21 fallback: the 'ws' package (server-side only)
  const wsMod = (await import("ws")) as unknown as { default?: unknown } | Record<string, unknown>;
  const WsCtor = ((wsMod as { default?: unknown }).default ?? wsMod) as new (u: string) => {
    send: (d: string) => void; close: () => void; on: (t: string, cb: (ev: { data?: unknown }) => void) => void;
  };
  return await new Promise<WsLike>((resolve, reject) => {
    const ws = new WsCtor(url);
    const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error("ws open timeout")); }, timeoutMs);
    ws.on("open", () => { clearTimeout(timer); resolve(wrap()); });
    ws.on("error", () => { clearTimeout(timer); reject(new Error("ws error")); });
    const listeners: ((d: string) => void)[] = [];
    const closers: (() => void)[] = [];
    ws.on("message", (ev: { data?: unknown }) => { const d = typeof ev.data === "string" ? ev.data : Buffer.from(ev.data as Buffer).toString(); for (const l of listeners) l(d); });
    ws.on("close", () => { for (const c of closers) c(); });
    const wrap = (): WsLike => ({
      send: (d) => ws.send(d),
      close: () => ws.close(),
      onMessage: (cb) => listeners.push(cb),
      onClose: (cb) => closers.push(cb),
    });
  });
}

let msgId = 1;
const pending = new Map<number, { resolve: (v: Record<string, unknown>) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
let notifyHandler: ((method: string, params: Record<string, unknown>) => void) | null = null;

let cdp: { base: string; sbxId: string } | null = null; // public CDP http base
let page: WsLike | null = null; // current page-target ws

function cdpSend(method: string, params: Record<string, unknown> = {}, timeoutMs = CDP_TIMEOUT_MS): Promise<Record<string, unknown>> {
  if (!page) throw new Error("browser not connected (call open first)");
  const id = msgId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`CDP timeout: ${method}`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    try {
      page!.send(JSON.stringify({ id, method, params }));
    } catch (e) {
      pending.delete(id);
      clearTimeout(timer);
      reject(e as Error);
    }
  });
}

function feedCdpMessage(raw: string) {
  let j: Record<string, unknown>;
  try {
    j = JSON.parse(raw);
  } catch {
    return;
  }
  const id = j.id as number | undefined;
  if (id != null && pending.has(id)) {
    const p = pending.get(id)!;
    pending.delete(id);
    clearTimeout(p.timer);
    if (j.error) p.reject(new Error(`CDP ${j.error.message || "error"}`));
    else p.resolve((j.result ?? {}) as Record<string, unknown>);
    return;
  }
  if (j.method) notifyHandler?.(j.method, (j.params ?? {}) as Record<string, unknown>);
}

// --------------------------------------------------------- browser bootstrap

type CdpJsonTarget = { id: string; type: string; url: string; title: string; webSocketDebuggerUrl?: string };

async function cdpBaseFor(sbx: DesktopSandbox): Promise<string> {
  const host = sbx.getHost?.(PROXY_PORT);
  if (!host) throw new Error("E2B getHost unavailable");
  return host.startsWith("http") ? host : `https://${host}`;
}

async function cdpAlive(base: string): Promise<boolean> {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 3000);
    const r = await fetch(`${base}/json/version`, { signal: ctl.signal, cache: "no-store" });
    clearTimeout(t);
    return r.ok;
  } catch {
    return false;
  }
}

async function findChromeBinary(sbx: DesktopSandbox): Promise<string> {
  const r = await run(sbx, "for b in google-chrome google-chrome-stable chromium chromium-browser; do command -v $b 2>/dev/null && break; done", 15_000);
  const bin = String(r.stdout || "").trim().split("\n")[0];
  if (!bin) throw new Error("no chromium-family browser in the desktop sandbox");
  return bin;
}

async function chromeLocalAlive(sbx: DesktopSandbox): Promise<boolean> {
  const r = await run(sbx, `curl -s --max-time 2 http://127.0.0.1:${CHROME_PORT}/json/version | head -c 20`, 10_000);
  return String(r.stdout || "").includes("Browser");
}

async function launchChrome(sbx: DesktopSandbox, startUrl = "about:blank"): Promise<void> {
  const bin = await findChromeBinary(sbx);
  // DISPLAY: the desktop template exports it for commands; detect + reuse.
  const d = await run(sbx, "echo $DISPLAY", 10_000);
  const display = String(d.stdout || "").trim() || ":0";
  const cmd = [
    `pkill -f remote-debugging-port=${CHROME_PORT} 2>/dev/null || true`,
    `rm -f /home/user/chrome-profile/Singleton* 2>/dev/null || true`,
    `DISPLAY=${display} setsid nohup ${bin}`,
    `--remote-debugging-port=${CHROME_PORT}`,
    `--user-data-dir=/home/user/chrome-profile`,
    `--no-first-run --no-default-browser-check --disable-dev-shm-usage --no-sandbox --disable-gpu`,
    `--window-size=1024,700`,
    `'${startUrl.replace(/'/g, "")}'`,
    `> /tmp/chrome.log 2>&1 &`,
  ].join(" ");
  await run(sbx, cmd, 20_000);
  for (let i = 0; i < 30; i++) {
    if (await chromeLocalAlive(sbx)) return;
    await new Promise((r) => setTimeout(r, 1000));
  }
  const log = await run(sbx, "tail -5 /tmp/chrome.log 2>/dev/null || true", 10_000);
  throw new Error(`Chrome did not open CDP within 30s; log: ${String(log.stdout || "").slice(0, 300)}`);
}

const NGINX_CONF = [
  "map $http_upgrade $connection_upgrade { default upgrade; '' close; }",
  "server {",
  `  listen ${PROXY_PORT};`,
  "  location / {",
    `    proxy_pass http://127.0.0.1:${CHROME_PORT};`,
  "    proxy_http_version 1.1;",
  "    proxy_set_header Host localhost;",
  "    proxy_set_header Upgrade $http_upgrade;",
  "    proxy_set_header Connection $connection_upgrade;",
  "    proxy_read_timeout 3600s;",
  "    proxy_send_timeout 3600s;",
  "  }",
  "}",
].join("\n");

/** Install + start the nginx Host-rewrite proxy (idempotent, ~once per sandbox). */
async function ensureProxy(sbx: DesktopSandbox): Promise<void> {
  // cheap probe: nginx up and proxying?
  const probe = await run(sbx, `curl -s --max-time 2 -H 'Host: localhost' http://127.0.0.1:${PROXY_PORT}/json/version | head -c 40`, 10_000);
  if (String(probe.stdout || "").includes("Browser")) return;
  const r = await run(
    sbx,
    `command -v nginx >/dev/null 2>&1 || (sudo apt-get update -qq >/dev/null 2>&1; sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx-light >/dev/null 2>&1); command -v nginx`,
    180_000
  );
  if (!String(r.stdout || "").includes("nginx")) throw new Error("nginx install failed in sandbox");
  const quoted = NGINX_CONF.replace(/'/g, `'\\''`);
  await run(
    sbx,
    `printf '%s' '${quoted}' > /tmp/cdp-proxy.conf; sudo cp /tmp/cdp-proxy.conf /etc/nginx/conf.d/cdp-proxy.conf; sudo nginx -t 2>&1 | tail -1; (sudo nginx 2>/dev/null || sudo nginx -s reload 2>/dev/null || sudo service nginx start 2>&1) | tail -1; sleep 1`,
    60_000
  );
  const check = await run(sbx, `curl -s --max-time 3 -H 'Host: localhost' http://127.0.0.1:${PROXY_PORT}/json/version | head -c 40`, 15_000);
  if (!String(check.stdout || "").includes("Browser")) {
    throw new Error(`nginx CDP proxy not responding (chrome may be down): ${String(check.stdout || check.stderr || "").slice(0, 200)}`);
  }
}

async function listTargets(base: string): Promise<CdpJsonTarget[]> {
  const r = await fetch(`${base}/json/list`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/json/list ${r.status}`);
  const list = (await r.json()) as CdpJsonTarget[];
  return list.filter((t) => t.type === "page");
}

async function connectPage(sbx: DesktopSandbox, targetId?: string): Promise<{ url: string; title: string }> {
  const base = cdp!.base;
  let targets = await listTargets(base);
  let target = targetId ? targets.find((t) => t.id === targetId) : targets.find((t) => !/^devtools|^chrome-extension/.test(t.url || ""));
  if (!target) {
    // no page target — create one and relist
    const r = await fetch(`${base}/json/new?about:blank`, { method: "PUT", cache: "no-store" });
    if (!r.ok) throw new Error(`json/new ${r.status}`);
    targets = await listTargets(base);
    target = targets[targets.length - 1];
  }
  if (!target) throw new Error("no CDP page target");
  // public ws: wss://<public-host>/<path from in-sandbox ws url>
  const path = (target.webSocketDebuggerUrl || "").replace(/^wss?:\/\/[^/]+/, "");
  const wsUrl = `${cdp!.base.replace(/^http/, "ws")}${path}`;
  const ws = await openSocket(wsUrl, 10_000);
  ws.onMessage(feedCdpMessage);
  ws.onClose(() => { if (page === ws) page = null; });
  page?.close();
  page = ws;
  await cdpSend("Page.enable", {});
  await cdpSend("Runtime.enable", {});
  return { url: target.url, title: target.title };
}

/** Ensure sandbox + nginx proxy + chrome + CDP page connection are all live. */
async function ensureBrowser(): Promise<{ sbx: DesktopSandbox; base: string }> {
  const sbx = await getSandbox();
  let base = cdp?.base;
  if (!base || !(await cdpAlive(base))) {
    base = await cdpBaseFor(sbx);
    if (!(await cdpAlive(base))) {
      // distinguish: chrome down (relaunch) vs proxy down (reinstall/restart)
      if (!(await chromeLocalAlive(sbx))) await launchChrome(sbx);
      await ensureProxy(sbx);
    }
    cdp = { base, sbxId: sbx.sandboxId || "" };
    page = null;
  }
  if (!page) {
    await connectPage(sbx);
  }
  return { sbx, base };
}

// ------------------------------------------------------------------ helpers

async function evalInPage(expr: string): Promise<unknown> {
  const r = await cdpSend("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: false }, 20_000);
  const res = (r.result ?? {}) as { value?: unknown; exceptionDetails?: { text?: string; exception?: { description?: string } } };
  if (res.exceptionDetails) {
    throw new Error(`page eval failed: ${(res.exceptionDetails.exception?.description || res.exceptionDetails.text || "").slice(0, 200)}`);
  }
  return res.value;
}

async function viewportSize(): Promise<{ w: number; h: number }> {
  const v = (await evalInPage("({w: innerWidth, h: innerHeight})")) as { w?: number; h?: number } | null;
  return { w: Math.max(200, v?.w || 1280), h: Math.max(200, v?.h || 900) };
}

async function pageInfo(): Promise<{ url: string; title: string }> {
  const v = (await evalInPage("({u: location.href, t: document.title})")) as { u?: string; t?: string } | null;
  return { url: String(v?.u || "?"), title: String(v?.t || "") };
}

async function waitLoad(timeoutMs = NAV_TIMEOUT_MS): Promise<void> {
  const start = Date.now();
  for (;;) {
    const ready = await evalInPage("document.readyState").catch(() => "loading");
    if (ready === "complete" || ready === "interactive") {
      await new Promise((r) => setTimeout(r, 600)); // settle JS render
      return;
    }
    if (Date.now() - start > timeoutMs) return;
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function capture(): Promise<string> {
  const r = await cdpSend("Page.captureScreenshot", { format: "jpeg", quality: 70 }, 20_000);
  return String(r.data || "");
}

const KEY_CODES: Record<string, { vk: number; code: string; text?: string }> = {
  enter: { vk: 13, code: "Enter", text: "\r" },
  tab: { vk: 9, code: "Tab", text: "\t" },
  escape: { vk: 27, code: "Escape" },
  esc: { vk: 27, code: "Escape" },
  backspace: { vk: 8, code: "Backspace" },
  delete: { vk: 46, code: "Delete" },
  space: { vk: 32, code: "Space", text: " " },
  arrowup: { vk: 38, code: "ArrowUp" },
  arrowdown: { vk: 40, code: "ArrowDown" },
  arrowleft: { vk: 37, code: "ArrowLeft" },
  arrowright: { vk: 39, code: "ArrowRight" },
  home: { vk: 36, code: "Home" },
  end: { vk: 35, code: "End" },
  pageup: { vk: 33, code: "PageUp" },
  pagedown: { vk: 34, code: "PageDown" },
};

const MODIFIERS: Record<string, number> = { ctrl: 2, alt: 1, shift: 8, meta: 4, cmd: 4 };

async function dispatchKey(spec: string): Promise<void> {
  const parts = spec.split("+").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const key = parts[parts.length - 1];
  const mods = parts.slice(0, -1).reduce((m, p) => m | (MODIFIERS[p] || 0), 0);
  const kc = KEY_CODES[key];
  const vk = kc?.vk ?? (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0);
  const code = kc?.code ?? (key.length === 1 ? `Key${key.toUpperCase()}` : key);
  const keyName = key.charAt(0).toUpperCase() + key.slice(1);
  // CDP semantics: keys that produce text (Enter '\r', Tab, space, printable)
  // must be keyDown WITH text; pure control keys use rawKeyDown. A plain
  // 'char' event does NOT trigger form submission on Enter.
  const hasText = Boolean(kc?.text);
  const downType = hasText ? "keyDown" : "rawKeyDown";
  await cdpSend("Input.dispatchKeyEvent", { type: downType, key: keyName, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: mods, text: kc?.text ?? undefined });
  await cdpSend("Input.dispatchKeyEvent", { type: "keyUp", key: keyName, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: mods });
}

async function dispatchClick(fx: number, fy: number, clickCount = 1, button = "left"): Promise<void> {
  const { w, h } = await viewportSize();
  const x = Math.round(Math.min(Math.max(fx, 0), 1) * w);
  const y = Math.round(Math.min(Math.max(fy, 0), 1) * h);
  const base = { x, y, button, clickCount };
  await cdpSend("Input.dispatchMouseEvent", { ...base, type: "mousePressed" });
  await cdpSend("Input.dispatchMouseEvent", { ...base, type: "mouseReleased" });
}

// ------------------------------------------------------------ public actions

export async function browserRemoteAction(args: Record<string, unknown>): Promise<BrowserRemoteResult> {
  const action = String(args.action || "status");
  const attempt = async (): Promise<BrowserRemoteResult> => {
    const { sbx } = await ensureBrowser();
    await extendLife(sbx);
    switch (action) {
      case "status": {
        const info = await pageInfo();
        const vs = await viewportSize();
        const targets = await listTargets(cdp!.base).catch(() => [] as CdpJsonTarget[]);
        return {
          content: [
            `sandbox: ${sbx.sandboxId || "?"} (E2B desktop)`,
            `cdp: ${cdp!.base}`,
            `page: ${info.url}`,
            `title: ${info.title}`,
            `viewport: ${vs.w}x${vs.h} css px (fractions fx/fy 0..1)`,
            `tabs: ${targets.length}`,
          ].join("\n"),
        };
      }
      case "open":
      case "nav": {
        const url = String(args.url || "");
        if (!url) return { content: "open requires url" };
        const full = /^[a-z]+:\/\//i.test(url) ? url : `https://${url}`;
        await cdpSend("Page.navigate", { url: full }, 30_000);
        await waitLoad();
        const info = await pageInfo();
        return { content: `navigated to ${info.url}\ntitle: ${info.title}` };
      }
      case "reload": {
        await cdpSend("Page.reload", { ignoreCache: true }, 30_000);
        await waitLoad();
        const info = await pageInfo();
        return { content: `reloaded — ${info.url} (${info.title})` };
      }
      case "back": {
        await evalInPage("history.back()");
        await waitLoad();
        const info = await pageInfo();
        return { content: `back — ${info.url}` };
      }
      case "read": {
        const v = (await evalInPage(
          `(() => { try { return JSON.stringify({t: document.title, u: location.href, x: (document.body ? document.body.innerText : '').slice(0, 9000)}); } catch (e) { return JSON.stringify({err: String(e)}); } })()`
        )) as string;
        const d = JSON.parse(v || "{}") as { t?: string; u?: string; x?: string; err?: string };
        if (d.err) return { content: `read failed: ${d.err}` };
        return { content: `# ${d.t || ""}\nURL: ${d.u || ""}\n\n${(d.x || "").trim().slice(0, 9000)}` };
      }
      case "elements": {
        const v = (await evalInPage(
          `(() => { try { const vw = innerWidth, vh = innerHeight; const sels = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [onclick], [contenteditable="true"]'; const els = Array.from(document.querySelectorAll(sels)).slice(0, 500); const out = []; for (const el of els) { const r = el.getBoundingClientRect(); if (r.width < 4 || r.height < 4) continue; if (r.bottom < -40 || r.top > vh + 40 || r.right < 0 || r.left > vw) continue; const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.alt || '').trim().replace(/\\s+/g, ' ').slice(0, 70); if (!text && el.tagName === 'A') continue; out.push({ tag: el.tagName.toLowerCase(), fx: +((r.x + r.width / 2) / vw).toFixed(3), fy: +((r.y + r.height / 2) / vh).toFixed(3), text, type: el.getAttribute('type') || '' }); } out.sort((a, b) => (a.fy - b.fy) || (a.fx - b.fx)); return JSON.stringify(out.slice(0, 60)); } catch (e) { return JSON.stringify({ err: String(e) }); } })()`
        )) as string;
        const list = JSON.parse(v || "[]") as Array<{ tag: string; fx: number; fy: number; text: string; type?: string }> | { err?: string };
        if (!Array.isArray(list)) return { content: `elements failed: ${(list as { err?: string }).err}` };
        const vs = await viewportSize();
        const lines = list.map((e, i) => `[${i}] ${e.tag}${e.type ? `:${e.type}` : ""} fx=${e.fx} fy=${e.fy} ${e.text ? `'${e.text}'` : ""}`);
        return { content: `viewport ${vs.w}x${vs.h} — click with fx/fy fractions. Interactive elements:\n${lines.join("\n") || "(none visible)"}` };
      }
      case "screenshot": {
        const b64 = await capture();
        const info = await pageInfo();
        return {
          content: `screenshot of ${info.url} (${info.title}) — use 'read' or 'elements' for the text layer`,
          images: [`data:image/jpeg;base64,${b64}`],
        };
      }
      case "click": {
        await dispatchClick(Number(args.fx), Number(args.fy), 1);
        await new Promise((r) => setTimeout(r, 500));
        const info = await pageInfo();
        return { content: `clicked (${Number(args.fx).toFixed(3)}, ${Number(args.fy).toFixed(3)}) — now: ${info.title || info.url}` };
      }
      case "dblclick": {
        await dispatchClick(Number(args.fx), Number(args.fy), 2);
        await new Promise((r) => setTimeout(r, 500));
        const info = await pageInfo();
        return { content: `double-clicked — now: ${info.title || info.url}` };
      }
      case "type": {
        const text = String(args.text ?? "");
        await cdpSend("Input.insertText", { text });
        return { content: `typed ${text.length} chars` };
      }
      case "press": {
        const key = String(args.key || args.text || "enter");
        await dispatchKey(key);
        await new Promise((r) => setTimeout(r, 500));
        const info = await pageInfo();
        return { content: `pressed ${key} — now: ${info.title || info.url}` };
      }
      case "scroll": {
        const { w, h } = await viewportSize();
        const dy = Number(args.deltaY ?? 300);
        const x = Math.round((Number(args.fx ?? 0.5)) * w);
        const y = Math.round((Number(args.fy ?? 0.5)) * h);
        await cdpSend("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: dy, button: "none" });
        await new Promise((r) => setTimeout(r, 400));
        const sy = (await evalInPage("scrollY")) as number;
        return { content: `scrolled ${dy > 0 ? "down" : "up"} ${Math.abs(dy)}px (scrollY=${sy})` };
      }
      case "drag": {
        const { w, h } = await viewportSize();
        const fromX = Math.round(Number(args.fx) * w), fromY = Math.round(Number(args.fy) * h);
        const toX = Math.round(Number(args.toFx) * w), toY = Math.round(Number(args.toFy) * h);
        await cdpSend("Input.dispatchMouseEvent", { type: "mousePressed", x: fromX, y: fromY, button: "left", clickCount: 1 });
        const steps = Number(args.steps || 12);
        for (let i = 1; i <= steps; i++) {
          await cdpSend("Input.dispatchMouseEvent", {
            type: "mouseMoved", x: Math.round(fromX + ((toX - fromX) * i) / steps), y: Math.round(fromY + ((toY - fromY) * i) / steps), button: "left", clickCount: 1,
          });
        }
        await cdpSend("Input.dispatchMouseEvent", { type: "mouseReleased", x: toX, y: toY, button: "left", clickCount: 1 });
        const info = await pageInfo();
        return { content: `dragged to (${args.toFx}, ${args.toFy}) — now: ${info.title || info.url}` };
      }
      case "eval": {
        const expr = String(args.expr || "");
        if (!expr) return { content: "eval requires expr" };
        const v = await evalInPage(expr);
        return { content: `=> ${typeof v === "string" ? v.slice(0, 3000) : JSON.stringify(v)?.slice(0, 3000)}` };
      }
      case "tabs": {
        const targets = await listTargets(cdp!.base);
        const cur = await pageInfo();
        return {
          content: targets.map((t, i) => `[${i}]${t.url === cur.url ? " *" : " "} ${t.title.slice(0, 60)} — ${t.url.slice(0, 90)}`).join("\n") || "(no tabs)",
        };
      }
      case "new_tab": {
        const url = String(args.url || "about:blank");
        const full = /^[a-z]+:\/\//i.test(url) ? url : `https://${url}`;
        const r = await fetch(`${cdp!.base}/json/new?${encodeURIComponent(full)}`, { method: "PUT", cache: "no-store" });
        if (!r.ok) return { content: `new_tab failed: ${r.status}` };
        const t = (await r.json()) as CdpJsonTarget;
        await connectPage(sbx, t.id);
        await waitLoad(12_000);
        const info = await pageInfo();
        return { content: `new tab: ${info.url}` };
      }
      case "select_tab": {
        const idx = Number(args.index ?? 0);
        const targets = await listTargets(cdp!.base);
        const t = targets[idx];
        if (!t) return { content: `no tab index ${idx} (have ${targets.length})` };
        await fetch(`${cdp!.base}/json/activate/${t.id}`, { cache: "no-store" }).catch(() => undefined);
        await connectPage(sbx, t.id);
        const info = await pageInfo();
        return { content: `switched to [${idx}] ${info.title} — ${info.url}` };
      }
      case "close_tab": {
        const idx = Number(args.index ?? 0);
        const targets = await listTargets(cdp!.base);
        const t = targets[idx];
        if (!t) return { content: `no tab index ${idx}` };
        await fetch(`${cdp!.base}/json/close/${t.id}`, { cache: "no-store" }).catch(() => undefined);
        await connectPage(sbx);
        return { content: `closed tab [${idx}]` };
      }
      default:
        return { content: `unknown browser_remote action: ${action}` };
    }
  };

  try {
    return await attempt();
  } catch (e) {
    // connection-class failure: rebuild sandbox + chrome once, retry once
    const msg = String(e);
    if (!/Sandbox|connection|closed|disconnect|timeout|Timeout|ws error|CDP/i.test(msg)) {
      return { content: `browser_remote error: ${msg.slice(0, 300)}` };
    }
    await invalidateSandbox();
    try {
      return await attempt();
    } catch (e2) {
      return { content: `browser_remote failed after reconnect: ${String(e2).slice(0, 300)}` };
    }
  }
}
