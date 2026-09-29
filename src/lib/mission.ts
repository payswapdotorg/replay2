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
}

const STATE_PATH = path.join(process.cwd(), "data", "mission-state.json");

export async function readMissionState(): Promise<MissionState> {
  try {
    const raw = await readFile(STATE_PATH, "utf8");
    return JSON.parse(raw) as MissionState;
  } catch {
    // Never render a broken console — fall back to a NEUTRAL no-mission
    // state. The console is project-agnostic by governance: mission state
    // is a per-deployment LOCAL file (data/mission-state.json, gitignored).
    // Never hardcode a project here — see AGENT_BOOT_PROMPT.md §0.
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
    };
  }
}
