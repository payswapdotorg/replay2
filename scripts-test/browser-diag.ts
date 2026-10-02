/* Diagnose the desktop sandbox: DISPLAY, browser binaries, chrome launch. */
import { loadSDK } from "../src/agent/browserRemote";

async function sh(cmd: string) {
  console.log(`$ ${cmd}`);
}

async function main() {
  const D = await loadSDK();
  const sbx = await D.create({ apiKey: process.env.E2B_API_KEY, timeoutMs: 15 * 60 * 1000 });
  console.log("sandbox:", sbx.sandboxId);
  const run = (cmd: string) => (sbx as any).commands.run(cmd, { timeoutMs: 60_000 });

  const probes = [
    "echo DISPLAY=$DISPLAY; echo WAYLAND=$WAYLAND_DISPLAY; ls /tmp/.X11-unix/ 2>/dev/null",
    "for b in google-chrome google-chrome-stable chromium chromium-browser firefox; do command -v $b 2>/dev/null; done; ls /usr/bin | grep -iE 'chrom|firefox' | head",
    "ps aux | grep -iE 'xfce|xvfb|Xvfb' | grep -v grep | head -5",
    "cat /etc/os-release | head -2",
  ];
  for (const p of probes) {
    await sh(p);
    const r = await run(p);
    console.log(String(r.stdout || "").trim() || "(no stdout)", "\n---");
  }

  // manual chrome launch attempt
  const d = await run("echo $DISPLAY");
  const display = String(d.stdout || "").trim() || ":0";
  console.log("using DISPLAY:", display);
  const launch = `DISPLAY=${display} setsid nohup chromium --remote-debugging-port=9222 --user-data-dir=/home/user/chrome-profile --no-first-run --no-default-browser-check --disable-dev-shm-usage --no-sandbox --disable-gpu --window-size=1366,900 about:blank > /tmp/chrome.log 2>&1 & echo started`;
  const r1 = await run(launch);
  console.log("launch:", String(r1.stdout || "").trim(), "exit:", r1.exitCode);
  await new Promise((res) => setTimeout(res, 8000));
  const r2 = await run("ps aux | grep -E 'chrom' | grep -v grep | head -3; echo ---; cat /tmp/chrome.log | head -20");
  console.log(String(r2.stdout || "").trim());
  const r3 = await run("curl -s http://127.0.0.1:9222/json/version | head -c 200");
  console.log("CDP local:", String(r3.stdout || "").trim() || "(no response)");
  const host = (sbx as any).getHost(9222);
  console.log("CDP public host:", host);
}

main().catch((e) => { console.error("DIAG FAILED:", e); process.exit(1); });
