import { execFile } from "child_process";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

/**
 * Path + interpreter resolution for the replay stack.
 *
 * The console dev server runs with cwd = /home/z/my-project (the sandbox's
 * user-visible Next.js app), while the replay stack (scripts/, flags/, logs/)
 * lives in the deployed replay2 repo. REPLAY_ROOT resolves that repo —
 * env-overridable, default /home/z/replay2.
 *
 * The python interpreter is resolved by deploy.sh (it needs the `websocket`
 * module) and recorded in scripts/python_bin.txt; we read it lazily.
 */
// Resolve the deployed replay2 repo root, resurrection-proof under any
// spawner (supervisor/watcher/custodian relaunch without custom env):
// 1. REPLAY_ROOT env (explicit override)
// 2. process.cwd() when the console dev server runs from the repo itself
// 3. known deployment locations (probed for scripts/bridge.py)
const ROOT_CANDIDATES = [
  process.env.REPLAY_ROOT,
  process.cwd(),
  "/home/z/my-project/replay2",
  "/home/z/replay2",
].filter((x): x is string => Boolean(x));
const ROOT = ROOT_CANDIDATES.find((c) => {
  try {
    return existsSync(join(c, "scripts", "bridge.py"));
  } catch {
    return false;
  }
}) || "/home/z/replay2";
export const SCRIPTS = join(ROOT, "scripts");
export const FLAGS = join(SCRIPTS, "flags");
export const BRIDGE = join(SCRIPTS, "bridge.py");
export const WATCHER_LOG = join(SCRIPTS, "watcher.log");
export const WATCHER_HEARTBEAT = join(FLAGS, "watcher_heartbeat");
export const REPLAYD_URL =
  process.env.REPLAYD_URL || "http://127.0.0.1:3100";

function resolvePython(): string {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  try {
    const p = readFileSync(join(SCRIPTS, "python_bin.txt"), "utf-8").trim();
    if (p) return p;
  } catch {
    /* fall through */
  }
  return "python3";
}

/** Lazily resolved interpreter: deploy.sh may write python_bin.txt AFTER the
 * console is already running (e.g. a platform-managed dev server), so
 * resolving once at module load can pin a wrong "python3" fallback for the
 * whole server lifetime. */
export function pyBin(): string {
  return resolvePython();
}

/** Run bridge.py <cmd> and return stdout as Buffer (binary-safe). */
export function runBridge(cmd: string, arg?: string, timeoutMs = 25000) {
  const args = arg ? [BRIDGE, cmd, arg] : [BRIDGE, cmd];
  return execFileAsync(pyBin(), args, {
    timeout: timeoutMs,
    maxBuffer: 16 * 1024 * 1024,
    encoding: "buffer",
  });
}

/** Run bridge.py <cmd> and parse the last JSON line from stdout. */
export async function runBridgeJson(cmd: string, arg?: string, timeoutMs = 25000) {
  const { stdout } = await execFileAsync(pyBin(), arg ? [BRIDGE, cmd, arg] : [BRIDGE, cmd], {
    timeout: timeoutMs,
    maxBuffer: 4 * 1024 * 1024,
  });
  const text = stdout.toString("utf-8").trim().split("\n").pop() || "{}";
  return JSON.parse(text);
}

export function timeoutSignal(ms: number): AbortSignal {
  const ctl = new AbortController();
  setTimeout(() => ctl.abort(), ms);
  return ctl.signal;
}

/** True when the deployed replay repo (scripts/ dir) is present. */
export function replayStackPresent(): boolean {
  try {
    return existsSync(SCRIPTS);
  } catch {
    return false;
  }
}
