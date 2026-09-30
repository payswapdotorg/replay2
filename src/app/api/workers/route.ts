import { promises as fsp } from "fs";
import { existsSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { FLAGS, SCRIPTS } from "@/lib/replay";

/**
 * GET /api/workers — live orchestration status for the Replay Console.
 *
 * Reads the dispatch machinery's own ground truth (no separate state to
 * keep in sync):
 *  - flags/session_registry.jsonl  → every create/void record per session
 *  - flags/queue_watch.spec.<name> → the watched tab + completion marker
 *  - flags/queue_watch_heartbeat.<name> → watcher liveness (supervisor rule)
 *  - /tmp/queue_watch_<name>.log   → the watcher's per-round state lines
 *  - worker-prompts/R*.md          → staged (not-yet-dispatched) packets
 *
 * States surfaced:
 *  generating       — Stop-button visible in the session DOM
 *  working          — no Stop-button but the body is moving (the site
 *                     virtualizes long streaming answers, so the DOM
 *                     length flaps while the sandbox works — movement,
 *                     not stillness, is the live signal)
 *  queued / capacity / rate-limited — waiting server-side
 *  re-dispatching   — tab lost / rolled home / watcher busy recovering
 *  complete         — server-confirmed delivery marker written
 */

const REGISTRY = join(FLAGS, "session_registry.jsonl");
const PROMPTS = join(SCRIPTS, "worker-prompts");

type Rec = {
  name?: string;
  action?: string;
  tab_id?: string;
  url?: string;
  ts?: number;
  prompt_file?: string;
  sent?: boolean;
  reason?: string;
};

type State =
  | "generating"
  | "working"
  | "queued"
  | "capacity"
  | "rate-limited"
  | "re-dispatching"
  | "complete"
  | "unknown";

export interface WorkerInfo {
  name: string;
  title: string;
  lane: string;
  state: State;
  chars: number;
  chatUrl: string | null;
  tabId: string | null;
  dispatches: number;
  lastRoundMs: number;
  watcherAlive: boolean;
  lastStateLine: string;
}

export interface StagedInfo {
  name: string;
  title: string;
  lane: string;
  packetChars: number;
}

function mtimeMs(p: string): number {
  try {
    return statSync(p).mtimeMs;
  } catch {
    return 0;
  }
}

function readLines(p: string): string[] {
  try {
    return readFileSync(p, "utf-8").split("\n").filter((l) => l.trim());
  } catch {
    return [];
  }
}

/** Parse the watcher's per-round state lines for one session. Watchers
 *  launched by the operator flow log to /tmp/queue_watch_<name>.log;
 *  supervisor-resurrected ones append to logs/queue-watch.log (all
 *  sessions mixed). Read both, filter by session name, take the latest. */
function parseWatcherLog(name: string, origName?: string): {
  state: State;
  chars: number;
  moving: boolean;
  lastLine: string;
  lastRoundMs: number;
} {
  const sources = [
    join("/tmp", `queue_watch_${origName || name}.log`),
    join("/tmp", `queue_watch_${name}.log`),
    join(SCRIPTS, "logs", "queue-watch.log"),
    join(SCRIPTS, "logs", `queue_watch_${origName || name}.log`),
  ];
  // only the FRESHEST source is live — the other holds stale lines from a
  // previous incarnation (the mixed log also carries other sessions' lines,
  // so array-order interleaving would risk picking a stale round).
  const live = sources
    .map((p) => ({ p, ms: mtimeMs(p) }))
    .sort((a, b) => b.ms - a.ms)[0];
  const rounds: { raw: string; state: string; chars: number; src: string }[] = [];
  if (live && live.ms > 0) {
    for (const l of readLines(live.p)) {
      const m = l.match(
        /^\[(\S+)\]\s+\d{2}:\d{2}:\d{2}\s+(\S+)\s+chars=(\d+)\s+hits=\d+/,
      );
      // log lines carry the ORIGINAL-case session name (flauz-A2-tl2)
      if (!m || (m[1] !== name && m[1] !== (origName || name))) continue;
      rounds.push({ raw: l, state: m[2], chars: Number(m[3]), src: live.p });
    }
  }
  if (rounds.length === 0) {
    return { state: "unknown", chars: 0, moving: false, lastLine: "", lastRoundMs: 0 };
  }
  const last = rounds[rounds.length - 1];
  const prev = rounds[rounds.length - 2];
  const moving =
    prev !== undefined &&
    prev.state === last.state &&
    prev.chars !== last.chars;
  let state: State;
  switch (last.state) {
    case "generating":
      state = "generating";
      break;
    case "queued":
      state = moving ? "working" : "queued";
      break;
    case "queued-capacity":
      state = "capacity";
      break;
    case "rate-limited":
      state = "rate-limited";
      break;
    case "tablost":
    case "home":
      state = "re-dispatching";
      break;
    default:
      // busy:* and anything else — the watcher is mid-recovery
      state = moving ? "working" : "re-dispatching";
      break;
  }
  return { state, chars: last.chars, moving, lastLine: last.raw, lastRoundMs: mtimeMs(last.src) };
}

/** `# R10 — Native Media production path (Worker 3)` (single-wave era) or
 *  `# R24-W1 — Round title: lane detail (checkpoint chain)` (wave era) →
 *  title + lane. In the wave format the part after the colon is the
 *  distinguishing lane detail, and the -W<N> suffix names the wave.
 *  W-series (SOS frontier era, 2026-09-30): `# W13 — Title (frontier
 *  Worker, lane A)` → title + lane extracted from the paren clause. */
function parseHeader(head: string): { title: string; lane: string } {
  const mw = head.match(/^#\s*W\d+\s*[—-]\s*(.+?)\s*\((.+)\)\s*$/);
  if (mw) {
    const laneM = mw[2].match(/(?:^|\s)lane\s+([A-Za-z0-9]+)/i);
    const workerM = mw[2].match(/Worker\s*([A-Za-z0-9]+)/i);
    return {
      title: mw[1],
      lane: laneM
        ? `Lane ${laneM[1]}`
        : workerM
          ? `Worker ${workerM[1]}`
          : mw[2],
    };
  }
  const m = head.match(/^#\s*R\d+\s*[—-]\s*(.+?)\s*\((Worker\s*\d+)\)\s*$/);
  if (m) return { title: m[1], lane: m[2] };
  const m2 = head.match(/^#\s*R\d+(?:-W\d+)?\s*[—-]\s*(.+)$/);
  if (m2) {
    const tail = m2[1].trim();
    const colon = tail.indexOf(":");
    const laneDetail =
      colon >= 0
        ? tail.slice(colon + 1).replace(/\s*\([^)]*\)\s*$/, "").trim()
        : "";
    const wave = head.match(/^#\s*R\d+-(W\d+)\b/);
    return {
      title: laneDetail || tail.replace(/\s*\([^)]*\)\s*$/, ""),
      lane: wave ? wave[1] : "",
    };
  }
  return { title: head.replace(/^#\s*/, ""), lane: "" };
}

async function readRegistry(): Promise<Rec[]> {
  try {
    const raw = await fsp.readFile(REGISTRY, "utf-8");
    const out: Rec[] = [];
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      try {
        out.push(JSON.parse(t) as Rec);
      } catch {
        /* skip malformed */
      }
    }
    return out;
  } catch {
    return [];
  }
}

async function listStaged(dispatched: Set<string>): Promise<StagedInfo[]> {
  let files: string[] = [];
  try {
    // R03.md (single-wave era), R24-W1.md (wave era), r35a-readpath.md
    // (suffixed era), w13-worker-brief.md (SOS frontier era);
    // *.template.md are the reusable skeletons, never staged
    files = (await fsp.readdir(PROMPTS)).filter(
      (f) => /^[rRwW]\d+(?:-[A-Za-z0-9-]+)?\.md$/.test(f) && !/\.template\.md$/.test(f),
    );
  } catch {
    return [];
  }
  const staged: StagedInfo[] = [];
  for (const f of files) {
    // normalize to the session-name form: R24-W1.md → r24w1 (legacy wave
    // era joins the suffix); r35a-readpath.md → r35a (suffixed era: the part
    // before the first dash IS the session name)
    const stem = f.replace(/\.md$/, "");
    const wave = stem.match(/^[rR]\d+-W\d+$/);
    const name = wave
      ? wave[0].replace("-", "").toLowerCase()
      : stem.split("-")[0].toLowerCase();
    if (dispatched.has(name)) continue;
    const p = join(PROMPTS, f);
    const head = readLines(p)[0] || f;
    const { title, lane } = parseHeader(head);
    let packetChars = 0;
    try {
      packetChars = readFileSync(p, "utf-8").length;
    } catch {
      /* ignore */
    }
    staged.push({ name, title, lane, packetChars });
  }
  staged.sort((a, b) => a.name.localeCompare(b.name));
  return staged;
}

export async function GET() {
  const recs = await readRegistry();

  // latest create-record + dispatch count per R-series session name
  const live = new Map<string, { rec: Rec; dispatches: number }>();
  // latest create-record per name regardless of send state (the capacity
  // fight trail) + total create count (the assault cycle count)
  const latestAny = new Map<string, { rec: Rec; creates: number }>();
  const dispatched = new Set<string>();
  const specName = new Map<string, string>(); // lowercase -> ORIGINAL-case name
  for (const r of recs) {
    const name = (r.name || "").toLowerCase();
    // r03 (single-wave era), r24w1 (wave era), r35a/r34b2 (suffixed era:
    // round + lane letter + optional attempt digit). The regex must accept
    // every naming generation or the panel silently goes empty. flauz-*-tl2
    // (the TL2 Agent OS surge era) joins the accepted generations — as does
    // the ACTUAL TL2 naming form flauz-tl2-* (flauz-tl2-h1, flauz-tl2-acc1):
    // the 2026-09-29 forensics showed the suffix-only pattern hid every TL2
    // session from the live strip (latent since the surge began).
    // w13/w14/... (SOS frontier era, 2026-09-30): same acceptance rule —
    // a naming generation invisible to the strip is a silent-empty bug.
    if (!/^(?:r\d+[a-z0-9]*|flauz-[a-z0-9]+-tl2|flauz-tl2-[a-z0-9]+|w\d+[a-z0-9]*)$/.test(name))
      continue;
    if (r.action === "void") {
      // a void is bookkeeping, not a dispatch
      continue;
    }
    dispatched.add(name);
    specName.set(name, r.name || name); // spec files use the ORIGINAL case
    const cur = live.get(name);
    if (r.sent && r.url) {
      live.set(name, { rec: r, dispatches: (cur?.dispatches ?? 0) + 1 });
    }
    const curAny = latestAny.get(name);
    if (!curAny || (r.ts ?? 0) >= (curAny.rec.ts ?? 0)) {
      latestAny.set(name, {
        rec: r,
        creates: (curAny?.creates ?? 0) + 1,
      });
    } else {
      curAny.creates += 1;
    }
  }

  // every watched session: spec files are the supervisor contract — a spec
  // present means a watcher owns the session RIGHT NOW; sessions without a
  // spec (r01/r02/r08 after their merges) are history, covered by Mission
  // Control, not the live strip.
  const workers: WorkerInfo[] = [];
  for (const [name, { rec, dispatches }] of live) {
    // spec files use the ORIGINAL-case name (flauz-A2-tl2, not the
    // lowercased key) — check both spellings or the lane goes invisible.
    const origName = specName.get(name) || name;
    const specPath = existsSync(join(FLAGS, `queue_watch.spec.${origName}`))
      ? join(FLAGS, `queue_watch.spec.${origName}`)
      : join(FLAGS, `queue_watch.spec.${name}`);
    if (!existsSync(specPath)) continue; // retired — no live watcher
    let tabPrefix = (rec.tab_id || "").slice(0, 8);
    if (existsSync(specPath)) {
      try {
        const spec = JSON.parse(readFileSync(specPath, "utf-8"));
        if (spec.tab_prefix) tabPrefix = String(spec.tab_prefix);
      } catch {
        /* keep registry prefix */
      }
    }
    const complete = existsSync(join(FLAGS, `${name}-complete.marker`));
    const log = parseWatcherLog(name, origName);
    const hbPath = existsSync(join(FLAGS, `queue_watch_heartbeat.${origName}`))
      ? join(FLAGS, `queue_watch_heartbeat.${origName}`)
      : join(FLAGS, `queue_watch_heartbeat.${name}`);
    const hbAge = Date.now() - mtimeMs(hbPath);
    const watcherAlive = hbAge >= 0 && hbAge < 600_000;
    const head = rec.prompt_file ? readLines(rec.prompt_file)[0] || "" : "";
    const { title, lane } = parseHeader(head);
    workers.push({
      name,
      title: title || name.toUpperCase(),
      lane: lane || "Worker",
      state: complete ? "complete" : log.state,
      chars: log.chars,
      chatUrl: rec.url || null,
      tabId: tabPrefix || null,
      dispatches,
      lastRoundMs: mtimeMs(live.p),
      watcherAlive,
      lastStateLine: log.lastLine.slice(0, 200),
    });
  }
  // Capacity-fight visibility (lesson from the 4h r24w2 siege): a dispatched
  // session with NO live watcher spec but a FRESH registry trail is in the
  // autonomous recover/create loop — surface it so the operator can watch
  // the fight instead of an empty strip while the machinery battles the
  // GLM-5.3 capacity wall. A retired session (complete marker, cold trail)
  // stays history — Mission Control owns it.
  //
  // Ground-truth order for the LIVE fight tab: (1) the dispatch inflight
  // heartbeat (dispatch_worker.py writes it every assault round — registry
  // records land only when a create EXITS, so the trail lags one full cycle
  // and its tab is closed by the next create), (2) the registry trail,
  // (3) the last sent-true record.
  const FIGHT_FRESH_MS = 30 * 60_000;
  const INFLIGHT_FRESH_MS = 15 * 60_000;
  for (const [name, { rec: latest, creates }] of latestAny) {
    if (workers.some((w) => w.name === name)) continue;
    if (existsSync(join(FLAGS, `${name}-complete.marker`))) continue;
    const tsMs = (latest.ts ?? 0) * 1000;
    if (!tsMs || Date.now() - tsMs > FIGHT_FRESH_MS) continue;
    const flagPath = join(FLAGS, `capacity_recover.${name}.json`);
    const flagMs = mtimeMs(flagPath);
    const fighting = flagMs > 0 && Date.now() - flagMs < FIGHT_FRESH_MS;
    if (!fighting && Date.now() - tsMs > 10 * 60_000) continue; // cold trail, no loop
    // live in-flight create heartbeat (fresher than the registry trail)
    let inflightTab = "";
    let inflightUrl = "";
    let inflightMs = 0;
    let inflightRound = -1;
    try {
      const inflightPath = join(FLAGS, `dispatch_inflight.${name}.json`);
      const inflightMs0 = mtimeMs(inflightPath);
      if (inflightMs0 > 0 && Date.now() - inflightMs0 < INFLIGHT_FRESH_MS) {
        const inf = JSON.parse(readFileSync(inflightPath, "utf-8"));
        inflightTab = String(inf.tab_id || "");
        inflightUrl = String(inf.url || "");
        inflightRound = Number(inf.round ?? -1);
        inflightMs = inflightMs0;
      }
    } catch {
      /* absent/stale/corrupt — the registry trail stands */
    }
    const head = latest.prompt_file ? readLines(latest.prompt_file)[0] || "" : "";
    const { title, lane } = parseHeader(head);
    const fallback = live.get(name);
    workers.push({
      name,
      title: title || name.toUpperCase(),
      lane: lane || "Worker",
      state: "re-dispatching",
      chars: 0,
      chatUrl: inflightUrl || latest.url || fallback?.rec.url || null,
      tabId:
        (inflightTab || latest.tab_id || fallback?.rec.tab_id || "").slice(0, 8) || null,
      dispatches: creates,
      lastRoundMs: Math.max(tsMs, flagMs, inflightMs),
      watcherAlive: fighting || inflightMs > 0,
      lastStateLine:
        inflightRound >= 0
          ? `capacity assault — create round ${inflightRound} in flight`
          : fighting
            ? "capacity assault — supervisor-guarded recover loop cycling"
            : "create in flight — dispatch_worker running",
    });
  }

  workers.sort((a, b) => a.name.localeCompare(b.name));

  const staged = await listStaged(dispatched);

  return Response.json(
    { ts: new Date().toISOString(), workers, staged },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
