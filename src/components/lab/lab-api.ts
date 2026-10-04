"use client";

/**
 * Engineering Lab — data layer (B3-a).
 *
 * TanStack Query hooks + typed fetchers over the lab API routes (B1/B2/B3):
 *   GET  /api/lab/catalog                    -> LabCatalog
 *   GET  /api/lab/runs                       -> { runs: RunSummary[] }
 *   POST /api/lab/runs                       -> 201 RunSummary + recommendationId
 *   GET  /api/lab/runs/{id}                  -> { run, artifact, recommendation }
 *   GET  /api/lab/recommendations            -> { recommendations }
 *   GET  /api/lab/recommendations/{id}       -> detail
 *   GET  /api/lab/bridge                     -> { entries: BridgeEntrySummary[] }
 *   POST /api/lab/bridge                     -> 201 { entry, recommendation }
 *   GET  /api/lab/bridge/{id}                -> detail + observation
 *   POST /api/lab/bridge/{id}/observe        -> 201 intake + calibration
 *   GET  /api/lab/calibration                -> { calibration, observations }
 *   POST /api/lab/demo/closed-loop           -> 201 { demo, trace }
 *
 * Contract types come from the frozen module '@/lib/lab/contracts' (pure types,
 * client-safe). RunSummary / RecommendationSummary mirror the API _lib shapes
 * and are re-declared here so the client never imports server route files.
 * Every fetch is relative-path, JSON, throws on !ok with the server message.
 * NO optimistic UI anywhere: components render server-confirmed data only.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  AgentBodySpec,
  CalibrationError,
  CalibrationModel,
  LadderLevel,
  ModelDescriptor,
  RecommendationArtifact,
  RunArtifact,
  TaskOutcome,
  TaskScenario,
  TaskTypeDescriptor,
  ToolDescriptor,
  WorkloadProfile,
} from "@/lib/lab/contracts";
// Type-only import (erased at build): the catalog aggregator module also owns
// the LabCatalog response shape served by GET /api/lab/catalog.
import type { LabCatalog } from "@/lib/lab/catalog";

// ===== response shapes (mirror of the API, client-side) =====

export interface RunSummary {
  id: string;
  workloadId: string;
  taskTypeId: string;
  scenarioId: string;
  ladderLevel: number;
  status: string;
  winnerName: string | null;
  utilityDelta: number | null;
  createdAt: string;
}

export interface RecommendationSummary {
  id: string;
  runId: string;
  status: string;
  confidence: number | null;
  winnerName: string | null;
  createdAt: string;
}

export interface RunDetailResponse {
  run: RunSummary & { seeds: number[]; error: string | null };
  artifact: unknown; // RunArtifact for complete runs; stub JSON for failed ones
  recommendation: unknown; // RecommendationArtifact | null
}

export interface RecommendationDetailResponse {
  id: string;
  runId: string;
  status: string;
  artifact: unknown; // RecommendationArtifact
  createdAt: string;
}

export interface NewRunInput {
  workloadId: string;
  taskTypeId: string;
  scenarioId: string;
  ladderLevel: LadderLevel;
  seeds?: number[];
}

// ===== bridge / calibration / demo shapes (B3-b) =====

export interface BridgeEntrySummary {
  id: string;
  recommendationId: string;
  runId: string;
  status: string; // queued | observed | …
  note: string;
  portMode: string; // fixture | flauz
  submittedAt: string;
  observedAt: string | null;
  winnerName: string | null;
  confidence: number | null;
}

/** Per-dimension predicted / observed scalars behind one observation. */
export interface OutcomeScalars {
  success: number;
  quality: number;
  latencyMs: number;
  costUsd: number;
}

export interface BridgeDetailResponse {
  entry: BridgeEntrySummary;
  observation: TaskOutcome | null;
  predicted: OutcomeScalars | null;
  error: CalibrationError[] | null;
  recommendation: RecommendationSummary | null;
}

export interface CalibrationObservationSummary {
  id: string;
  bridgeEntryId: string;
  error: CalibrationError[] | null;
  createdAt: string;
}

export interface CalibrationResponse {
  calibration: CalibrationModel | null;
  observations: CalibrationObservationSummary[];
}

export interface ClosedLoopDemoStage {
  stage: string;
  detail: string;
}

export interface ClosedLoopDemoResponse {
  demo: true;
  trace: {
    stages: ClosedLoopDemoStage[];
    runId: string;
    recommendationId: string;
    bridgeEntryId: string;
    calibration: CalibrationModel;
    bridgeEntry: BridgeEntrySummary | null;
  };
}

/** The trace object of a closed-loop demo response (stability across tab switches). */
export type ClosedLoopDemoTrace = ClosedLoopDemoResponse["trace"];

// ===== fetch helpers =====

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: unknown };
    if (typeof body.error === "string" && body.error.length > 0) {
      return body.error;
    }
  } catch {
    // non-JSON error body — fall through to the status message
  }
  return `Request failed (HTTP ${res.status})`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as T;
}

// ===== runtime guards (failed runs persist stub artifacts) =====

export function isRunArtifact(value: unknown): value is RunArtifact {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    "spec" in v &&
    "search" in v &&
    "baseline" in v &&
    "winner" in v &&
    "comparison" in v &&
    "utilityWeights" in v
  );
}

export function isRecommendationArtifact(
  value: unknown,
): value is RecommendationArtifact {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    "organization" in v &&
    "rationale" in v &&
    "confidence" in v &&
    "caveats" in v
  );
}

// ===== catalog lookups (pure maps, no clock / no randomness) =====

export interface CatalogLookups {
  workloads: Map<string, WorkloadProfile>;
  taskTypes: Map<string, TaskTypeDescriptor>;
  scenarios: Map<string, TaskScenario>;
  bodies: Map<string, AgentBodySpec>;
  models: Map<string, ModelDescriptor>;
  tools: Map<string, ToolDescriptor>;
}

export function buildLookups(catalog: LabCatalog): CatalogLookups {
  return {
    workloads: new Map(catalog.workloads.map((w) => [w.id, w])),
    taskTypes: new Map(catalog.taskTypes.map((t) => [t.id, t])),
    scenarios: new Map(catalog.scenarios.map((s) => [s.id, s])),
    bodies: new Map(catalog.bodies.map((b) => [b.id, b])),
    models: new Map(catalog.models.map((m) => [m.id, m])),
    tools: new Map(catalog.tools.map((t) => [t.id, t])),
  };
}

// ===== query hooks =====

export function useLabCatalog() {
  return useQuery({
    queryKey: ["lab", "catalog"],
    queryFn: () => fetchJson<LabCatalog>("/api/lab/catalog"),
  });
}

export function useLabRuns() {
  return useQuery({
    queryKey: ["lab", "runs"],
    queryFn: () => fetchJson<{ runs: RunSummary[] }>("/api/lab/runs"),
  });
}

export function useLabRun(id: string | null) {
  return useQuery({
    queryKey: ["lab", "run", id],
    queryFn: () => fetchJson<RunDetailResponse>(`/api/lab/runs/${id}`),
    enabled: id !== null,
  });
}

export function useLabRecommendations() {
  return useQuery({
    queryKey: ["lab", "recommendations"],
    queryFn: () =>
      fetchJson<{ recommendations: RecommendationSummary[] }>(
        "/api/lab/recommendations",
      ),
  });
}

export function useLabRecommendation(id: string | null) {
  return useQuery({
    queryKey: ["lab", "recommendation", id],
    queryFn: () =>
      fetchJson<RecommendationDetailResponse>(`/api/lab/recommendations/${id}`),
    enabled: id !== null,
  });
}

/** POST a new run; invalidates the run + recommendation lists on success. */
export function useCreateLabRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: NewRunInput) =>
      postJson<RunSummary & { recommendationId: string }>(
        "/api/lab/runs",
        input,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lab", "runs"] });
      void queryClient.invalidateQueries({
        queryKey: ["lab", "recommendations"],
      });
    },
  });
}

// ===== bridge / calibration / demo hooks (B3-b) =====

export function useLabBridge() {
  return useQuery({
    queryKey: ["lab", "bridge"],
    queryFn: () => fetchJson<{ entries: BridgeEntrySummary[] }>("/api/lab/bridge"),
  });
}

export function useLabBridgeEntry(id: string | null) {
  return useQuery({
    queryKey: ["lab", "bridge-entry", id],
    queryFn: () => fetchJson<BridgeDetailResponse>(`/api/lab/bridge/${id}`),
    enabled: id !== null,
  });
}

export function useLabCalibration() {
  return useQuery({
    queryKey: ["lab", "calibration"],
    queryFn: () => fetchJson<CalibrationResponse>("/api/lab/calibration"),
  });
}

/** POST /api/lab/bridge — queue an issued recommendation for execution. */
export function useSendToBridge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recommendationId: string) =>
      postJson<{ entry: BridgeEntrySummary; recommendation: { id: string; status: string } }>(
        "/api/lab/bridge",
        { recommendationId },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lab", "recommendations"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "bridge"] });
    },
  });
}

/** POST /api/lab/bridge/{id}/observe — run the observation intake. */
export function useObserveBridgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) =>
      postJson<{
        entry: BridgeEntrySummary | null;
        observation: { predicted: OutcomeScalars; observed: TaskOutcome; error: CalibrationError[] };
        calibration: CalibrationModel | null;
      }>(`/api/lab/bridge/${entryId}/observe`, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lab", "bridge"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "calibration"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "recommendations"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "bridge-entry"] });
    },
  });
}

/** POST /api/lab/demo/closed-loop — the full deterministic loop in one shot. */
export function useClosedLoopDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      postJson<ClosedLoopDemoResponse>("/api/lab/demo/closed-loop", {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lab", "runs"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "recommendations"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "bridge"] });
      void queryClient.invalidateQueries({ queryKey: ["lab", "calibration"] });
    },
  });
}
