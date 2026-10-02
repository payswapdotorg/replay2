/* Diag 2: launch google-chrome properly, verify CDP locally + via public host. */
import { loadSDK } from "../src/agent/browserRemote";

async function main() {
  const D = await loadSDK();
  const id = process.argv[2];
  const sbx = id ? await D.connect(id, { apiKey: process.env.E2B_API_KEY, timeoutMs: 15 * 60 * 1000 }) : await D.create({ apiKey: process.env.E2B_API_KEY, timeoutMs: 15 * 60 * 1000 });
  console.log("sandbox:", sbx.sandboxId);
  const run = (cmd: string) => (sbx as any).commands.run(cmd, { timeoutMs: 60_000 });

  const launch = `DISPLAY=:0 setsid nohup google-chrome --remote-debugging-port=9222 --user-data-dir=/home/user/chrome-profile --no-first-run --no-default-browser-check --disable-dev-shm-usage --no-sandbox --disable-gpu --window-size=1024,700 about:blank > /tmp/chrome.log 2>&1 & echo launched`;
  const r1 = await run(launch);
  console.log("launch:", String(r1.stdout || "").trim());
  for (let i = 1; i <= 20; i++) {
    await new Promise((res) => setTimeout(res, 1000));
    const r = await run("curl -s --max-time 2 http://127.0.0.1:9222/json/version | head -c 120");
    const out = String(r.stdout || "").trim();
    if (out) {
      console.log(`CDP up after ${i}s:`, out);
      break;
    }
    if (i === 5 || i === 20) {
      const lg = await run("cat /tmp/chrome.log 2>/dev/null | head -10; ps aux | grep chrome | grep -v grep | wc -l");
      console.log(`[t=${i}s] log+procs:`, String(lg.stdout || "").trim().slice(0, 400));
    }
  }
  const host = (sbx as any).getHost(9222);
  const pub = `https://${host}`;
  console.log("public host:", pub);
  try {
    const r = await fetch(`${pub}/json/version`, { signal: AbortSignal.timeout(8000) });
    const j = await r.json();
    console.log("PUBLIC CDP:", JSON.stringify(j).slice(0, 200));
  } catch (e) {
    console.log("PUBLIC CDP FAILED:", String(e).slice(0, 200));
  }
  try {
    const r = await fetch(`${pub}/json/list`, { signal: AbortSignal.timeout(8000) });
    const list = (await r.json()) as Array<{ type: string; url: string; webSocketDebuggerUrl?: string }>;
    console.log("targets:", list.map((t) => `${t.type} ${t.url.slice(0, 50)} ws=${Boolean(t.webSocketDebuggerUrl)}`).join(" | "));
  } catch (e) {
    console.log("LIST FAILED:", String(e).slice(0, 150));
  }
}

main().catch((e) => { console.error("DIAG2 FAILED:", e); process.exit(1); });
