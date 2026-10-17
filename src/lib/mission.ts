import { readFile } from "fs/promises";
import path from "path";

export type ItemStatus =
  | "pending"
  | "staged"
  | "dispatched"
  | "in-review"
  | "changes-requested"
  | "merged"
  | "merged-local"
  | "done"
  | "blocked";

export type InfraStatus = "ok" | "degraded" | "pending" | "down";

export interface MissionItem {
  id: string;
  title: string;
  lane: string;
  status: ItemStatus;
  branch: string | null;
  notes: string;
  updatedAt?: string;
  worker?: string | null;
}

export interface MissionLane {
  id: string;
  name: string;
  scope: string;
  items: string[];
}

export interface InfraEntry {
  id: string;
  label: string;
  status: InfraStatus;
  detail: string;
}

export interface TimelineEntry {
  ts: string;
  kind: "info" | "warn" | "error" | "success";
  text: string;
}

// Operator-facing downloadable artifacts (e.g. desktop-client release
// assets). Optional and field-normalized like everything else: absent in
// any legacy state → empty list → nothing renders. `command`/`sha256`/
// `size` are optional install metadata — rendered by the Downloads card
// when present, silently omitted otherwise (same legacy tolerance).
export interface MissionDownload {
  id: string;
  label: string;
  url: string;
  detail?: string | null;
  command?: string | null;
  sha256?: string | null;
  size?: string | null;
}

export interface MissionState {
  updatedAt: string;
  mission: {
    title: string;
    subtitle: string;
    baseline: { main: string; tests: number; roadmap: string };
    cadence: string;
  };
  lanes: MissionLane[];
  items: MissionItem[];
  infra: InfraEntry[];
  timeline: TimelineEntry[];
  production: {
    url: string | null;
    deployedAt: string | null;
    status: string;
  };
  downloads: MissionDownload[];
}

const STATE_PATH = path.join(process.cwd(), "data", "mission-state.json");

// The neutral no-mission state — also the FIELD-LEVEL fallback donor: a
// mission-state whose shape has drifted (a missing field) must NEVER crash
// the board. Live catch 2026-10-14 (recycle #14): a mission-state rewrite
// dropped mission.baseline and Mission Control crashed at line 205
// (`state.mission.baseline.main`). The file-level catch below is not
// enough — normalize field-by-field over these defaults.
function neutralMissionState(): MissionState {
  return {
    updatedAt: new Date().toISOString(),
    mission: {
      title: "No mission loaded",
      subtitle:
        "This console is project-agnostic. To track YOUR project here, write data/mission-state.json locally (copy data/mission-state.example.json). Never commit it — project roadmaps must not enter this repo (governance §0).",
      baseline: { main: "unknown", tests: 0, roadmap: "unknown" },
      cadence: "n/a",
    },
    lanes: [],
    items: [],
    infra: [],
    timeline: [
      {
        ts: new Date().toISOString(),
        kind: "info",
        text: "data/mission-state.json not found — no mission loaded (neutral state)",
      },
    ],
    production: { url: null, deployedAt: null, status: "unknown" },
    downloads: [],
  };
}

export async function readMissionState(): Promise<MissionState> {
  const neutral = neutralMissionState();
  try {
    const raw = await readFile(STATE_PATH, "utf8");
    const parsed = JSON.parse(raw) as Partial<MissionState>;
    // Field-level normalization over the neutral donor (the recycle-#14
    // lesson): every access below is nullish-guarded, so shape drift in
    // the local data file degrades to "unknown" badges, never a crash.
    return {
      updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : neutral.updatedAt,
      mission: {
        title: parsed.mission?.title ?? neutral.mission.title,
        subtitle: parsed.mission?.subtitle ?? neutral.mission.subtitle,
        baseline: {
          main: parsed.mission?.baseline?.main ?? neutral.mission.baseline.main,
          tests: parsed.mission?.baseline?.tests ?? neutral.mission.baseline.tests,
          roadmap: parsed.mission?.baseline?.roadmap ?? neutral.mission.baseline.roadmap,
        },
        cadence: parsed.mission?.cadence ?? neutral.mission.cadence,
      },
      lanes: Array.isArray(parsed.lanes) ? parsed.lanes : [],
      items: Array.isArray(parsed.items) ? parsed.items : [],
      infra: Array.isArray(parsed.infra) ? parsed.infra : [],
      timeline: Array.isArray(parsed.timeline) && parsed.timeline.length > 0 ? parsed.timeline : neutral.timeline,
      production: {
        url: parsed.production?.url ?? null,
        deployedAt: parsed.production?.deployedAt ?? null,
        status: parsed.production?.status ?? "unknown",
      },
      downloads: Array.isArray(parsed.downloads)
        ? parsed.downloads
            .filter(
              (d): d is MissionDownload =>
                !!d && typeof d.id === "string" && typeof d.label === "string" && typeof d.url === "string",
            )
            .map((d) => ({
              id: d.id,
              label: d.label,
              url: d.url,
              detail: typeof d.detail === "string" ? d.detail : null,
              command: typeof d.command === "string" ? d.command : null,
              sha256: typeof d.sha256 === "string" ? d.sha256 : null,
              size: typeof d.size === "string" ? d.size : null,
            }))
        : [],
    };
  } catch {
    // Never render a broken console — fall back to a NEUTRAL no-mission
    // state. The console is project-agnostic by governance: mission state
    // is a per-deployment LOCAL file (data/mission-state.json, gitignored).
    // Never hardcode a project here — see AGENT_BOOT_PROMPT.md §0.
    return neutral;
  }
}
