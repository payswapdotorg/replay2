// ali4 station heal watchdog — the permanence ladder's top rung.
// Doctrine: likewise-station recovery-#15 (mini-services survive recycles; the platform
// auto-starts every mini-service at boot — proven live on this box 2026-10-14 11:08:31,
// when the platform brought the replayd gateway up BEFORE agent tools returned).
// ali4 recycle-#14 lesson: a ~4h agent-tool outage that ends in a box recycle = up to ~4h
// of station downtime that this watchdog cures in ~90s unattended.
//
// Contract:
//  - Probes gateway :3100 + console frame :3000 every PROBE_MS (fast first probe at boot).
//  - Fires recover.sh (the full manual: creds -> clone replay2 -> env -> reset-restore -> GC dfork)
//    only when the stack is DOWN: 1 failure at first-probe (boot context), 2 consecutive
//    failures in steady state, with a COOLDOWN between fires.
//  - Healthy stack = silent poll, zero side effects (~19ms probe class).
//  - Status endpoint on :3040 (best-effort; the watchdog survives even if the port is taken).
//  - NEVER mutates a healthy station; recover.sh is flock-serialized against concurrent runs.

const PORT = 3040;
const PROBE_MS = 60_000; // steady-state probe cadence
const COOLDOWN_MS = 10 * 60_000; // min spacing between recovery fires
const LOG = "/home/z/my-project/mini-services/heal/heal.log";

function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try { Bun.appendFile(LOG, line); } catch {}
  console.log(line.trim());
}

async function stackHealthy(): Promise<boolean> {
  try {
    const gw = await fetch("http://127.0.0.1:3100/healthz", { signal: AbortSignal.timeout(5000) });
    if (!gw.ok) return false;
  } catch { return false; }
  try {
    const frame = await fetch("http://127.0.0.1:3000/api/frame", { signal: AbortSignal.timeout(5000) });
    return frame.ok;
  } catch { return false; }
}

let healRunning = false;
let lastFireAt = 0;
let fires = 0;
let cycles = 0;
let consecutiveFailures = 0;
const bootedAt = new Date().toISOString();

async function fireRecovery(): Promise<void> {
  healRunning = true;
  lastFireAt = Date.now();
  fires++;
  log(`HEAL FIRING (fire #${fires}) — stack down, running recover.sh`);
  try {
    const p = Bun.spawn(["bash", "/home/z/my-project/mini-services/heal/recover.sh"], {
      stdout: "ignore",
      stderr: "ignore",
      cwd: "/home/z/my-project/mini-services/heal",
    });
    const code = await p.exited;
    log(`recover.sh exited ${code}`);
  } catch (e) {
    log(`recover.sh spawn failed: ${e}`);
  }
  healRunning = false;
}

// Best-effort status endpoint — never fatal to the watchdog.
try {
  Bun.serve({
    port: PORT,
    fetch: () => new Response(
      JSON.stringify({ service: "ali4-heal", bootedAt, cycles, fires, healRunning, lastFireAt: lastFireAt ? new Date(lastFireAt).toISOString() : null }, null, 2),
      { headers: { "content-type": "application/json" } },
    ),
  });
  log(`status endpoint live on :${PORT}`);
} catch (e) {
  log(`status endpoint unavailable (${e}) — watchdog continues headless`);
}

log(`ali4-heal watchdog online`);

// Main watchdog loop.
(async () => {
  let first = true;
  while (true) {
    cycles++;
    const healthy = await stackHealthy();
    if (healthy) {
      consecutiveFailures = 0;
    } else {
      consecutiveFailures++;
      const cold = Date.now() - lastFireAt >= COOLDOWN_MS;
      // Boot context: fire on first failure (the stack cannot be "mid-maintenance" at t=0).
      // Steady state: require 2 consecutive failures (avoids twitchy misfires).
      const trigger = !healRunning && cold && (first ? consecutiveFailures >= 1 : consecutiveFailures >= 2);
      if (trigger) await fireRecovery();
    }
    if (cycles % 5 === 0) log(`poll #${cycles}: healthy=${healthy} fires=${fires} failures=${consecutiveFailures}`);
    first = false;
    await Bun.sleep(PROBE_MS);
  }
})();
