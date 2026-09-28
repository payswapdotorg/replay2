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
    // Never render a broken console — fall back to a minimal valid state.
    return {
      updatedAt: new Date().toISOString(),
      mission: {
        title: "WebFlix Productionization",
        subtitle: "Mission state file unavailable",
        baseline: { main: "unknown", tests: 0, roadmap: "unknown" },
        cadence: "resident lead",
      },
      lanes: [],
      items: [],
      infra: [],
      timeline: [
        {
          ts: new Date().toISOString(),
          kind: "error",
          text: "data/mission-state.json could not be read",
        },
      ],
      production: { url: null, deployedAt: null, status: "unknown" },
    };
  }
}
