/**
 * Engineering Lab API — the closed-loop demo (mission step 12, B3-b).
 *
 * POST /api/lab/demo/closed-loop → runs the COMPLETE loop deterministically
 * with a FIXED demo spec (wl.feature-team / impl.feature / se.feature-addition
 * / L2 / seeds [11, 22, 33]):
 *   1. executeLabRun → LabRun + LabRecommendation (the SAME persist code path
 *      as POST /api/lab/runs, via _lib/persist);
 *   2. bridge entry created (fixture mode) + recommendation status → "sent";
 *   3. the observation intake runs (same code path as the bridge observe
 *      route) and persists LabCalibrationObservation;
 *   4. the calibration model is rebuilt from the observation THIS pass
 *      produced.
 *
 * DETERMINISM: every POST creates fresh rows (repeatable demo) but the
 * numeric results are identical — the demo pins its observation seed to a
 * fixed key instead of the fresh db runId (the bridge observe route uses
 * hashSeed(runId, "observation") per entry), and the trace stage details
 * carry only deterministic numbers (ids live in the dedicated response
 * fields). The store-wide calibration model is served by
 * GET /api/lab/calibration.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { executeLabRun } from "@/lib/lab/engine/run-engine";
import { buildCalibrationModel, type CalibrationObservationPair } from "@/lib/lab/calibration/calibrator";
import { hashSeed } from "@/lib/lab/rng";
import { LabError } from "@/lib/lab/errors";
import { formatSigned } from "@/lib/lab/sim/numeric";
import { seWorldScenarios } from "@/lib/lab/catalog/se-world";
import { findTaskType } from "@/lib/lab/catalog/task-types";
import { workloadProfiles } from "@/lib/lab/catalog/workload-profiles";
import type { LabRunSpec } from "@/lib/lab/contracts";
import { BRIDGE_NOTE, bridgeEntrySummary } from "../../_lib/bridge";
import { persistBridgeObservation, runObservationIntake } from "../../_lib/observation";
import { persistLabRun, RunPersistError } from "../../_lib/persist";
import { parseJsonValue } from "../../_lib/summary";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

const DEMO_SPEC: LabRunSpec = {
  workloadId: "wl.feature-team",
  taskTypeId: "impl.feature",
  scenarioId: "se.feature-addition",
  ladderLevel: 2,
  seeds: [11, 22, 33],
};

/**
 * Stable observation seed for the demo (the bridge observe route derives
 * hashSeed(runId, "observation") from the persisted runId; the demo pins a
 * fixed key so repeated POSTs stay numerically identical).
 */
const DEMO_OBSERVATION_SEED = hashSeed("demo.closed-loop", "observation");

interface DemoStage {
  stage:
    | "workload"
    | "task-type"
    | "world"
    | "org-search"
    | "occupancy"
    | "evaluation"
    | "recommendation"
    | "bridge"
    | "observation"
    | "calibration";
  detail: string;
}

export async function POST(_request: Request) {
  try {
    // --- (1) Run the engine + persist (same path as POST /api/lab/runs).
    const result = await executeLabRun(DEMO_SPEC);
    const persisted = await persistLabRun(DEMO_SPEC, result);
    const artifact = result.artifact;

    // --- (2) Bridge entry (fixture mode) + recommendation → "sent".
    const entry = await db.labBridgeEntry.create({
      data: {
        recommendationId: persisted.recommendationId,
        status: "queued",
        note: BRIDGE_NOTE,
        portMode: "fixture",
      },
    });
    const sentRecommendation = await db.labRecommendation.update({
      where: { id: persisted.recommendationId },
      data: { status: "sent" },
    });

    // --- (3) Observation intake (shared with the bridge observe route).
    const runRow = await db.labRun.findUnique({ where: { id: persisted.runId } });
    if (!runRow) {
      throw new RunPersistError(`Demo run "${persisted.runId}" disappeared before observation`);
    }
    const intake = await runObservationIntake({
      run: runRow,
      recommendationArtifact: parseJsonValue(sentRecommendation.artifact),
      observationSeed: DEMO_OBSERVATION_SEED,
    });
    await persistBridgeObservation(entry.id, intake);

    // --- (4) Calibration model rebuilt from THIS pass's observation.
    const pair: CalibrationObservationPair = {
      predicted: {
        success: intake.predicted.success,
        quality: intake.predicted.quality,
        latencyMs: intake.predicted.latencyMs,
        costUsd: intake.predicted.costUsd,
      },
      observed: {
        success: intake.observed.success ? 1 : 0,
        quality: intake.observed.quality,
        latencyMs: intake.observed.latencyMs,
        costUsd: intake.observed.costUsd,
      },
    };
    const calibration = buildCalibrationModel([pair], new Date().toISOString());

    // --- Trace (deterministic details only; ids live in the response fields).
    const workload = workloadProfiles.find((w) => w.id === DEMO_SPEC.workloadId);
    const taskType = findTaskType(DEMO_SPEC.taskTypeId);
    const scenario = seWorldScenarios.find((s) => s.id === DEMO_SPEC.scenarioId);
    const winner = artifact.winner;
    const utilityDelta = winner.utility - artifact.baseline.utility;
    const occupancyCounts = new Map<string, number>();
    for (const slot of winner.occupancy) {
      occupancyCounts.set(slot.modelId, (occupancyCounts.get(slot.modelId) ?? 0) + 1);
    }
    const occupancySummary =
      occupancyCounts.size > 0
        ? [...occupancyCounts.entries()].map(([modelId, count]) => `${count}× ${modelId}`).join(", ")
        : "default balanced-a on every node";
    const comparisonSummary = artifact.comparison
      .map((row) => `${row.dimension} ${formatSigned(row.delta)}`)
      .join(", ");
    const factors = calibration.factors;
    const factorsSummary = (["success", "quality", "latency", "cost"] as const)
      .map((dimension) => `${dimension} ×${factors[dimension] ?? 1}`)
      .join(", ");

    const stages: DemoStage[] = [
      {
        stage: "workload",
        detail: `Loaded workload "${workload?.name ?? DEMO_SPEC.workloadId}" (${DEMO_SPEC.workloadId}) — budget $${(workload?.budgetUsdPerTask ?? 0).toFixed(2)}/task, SLA ${workload?.latencySlaMinutes ?? 0} min; utility weights ${(["success", "quality", "latency", "cost"] as const)
          .map((d) => `${d} ${Math.round((artifact.utilityWeights[d] ?? 0) * 100)}%`)
          .join(", ")}.`,
      },
      {
        stage: "task-type",
        detail: `Task type "${taskType?.name ?? DEMO_SPEC.taskTypeId}" (${DEMO_SPEC.taskTypeId}, family ${taskType?.family ?? "—"}) — complexity ${taskType?.complexity ?? 0}, context needs ${taskType?.contextNeeds ?? 0}, verification ${taskType?.verificationStyle ?? "—"}.`,
      },
      {
        stage: "world",
        detail: `Scenario "${scenario?.name ?? DEMO_SPEC.scenarioId}" (${DEMO_SPEC.scenarioId}) — ${scenario?.instanceCount ?? 0} instance slots (6 per seed cap), difficultyBase ${scenario?.difficultyBase ?? 0}, perturbations ${(scenario?.perturbations ?? []).join(", ")}.`,
      },
      {
        stage: "org-search",
        detail: `Evaluated ${artifact.search.candidatesEvaluated} candidate organizations against the solo-generalist baseline — winner "${winner.organization.name}" (${winner.organization.topology}, ${winner.organization.nodes.length} nodes), Δutility ${formatSigned(utilityDelta, 6)}.`,
      },
      {
        stage: "occupancy",
        detail: `Occupancy search settled on ${occupancySummary} with archetype tool allocation across ${winner.organization.nodes.length} nodes.`,
      },
      {
        stage: "evaluation",
        detail: `${artifact.search.ladderNote} — winner utility ${formatSigned(winner.utility, 6)} vs baseline ${formatSigned(artifact.baseline.utility, 6)} (${comparisonSummary}).`,
      },
      {
        stage: "recommendation",
        detail: `Issued recommendation for "${result.recommendation.organization.name}" — confidence ${Math.round(result.recommendation.confidence * 1000) / 10}%, ${result.recommendation.caveats.length} caveat(s) recorded; status flipped to "sent".`,
      },
      {
        stage: "bridge",
        detail: `Sent to execution via the LabExecutionPort bridge in fixture mode (entry queued, then observed) — the flauz adapter stays closed behind Agent OS (authorization, approvals, leases, browser policy).`,
      },
      {
        stage: "observation",
        detail: `Observed the outcome through the fixture port with the pinned demo seed: success ${intake.observed.success}, quality ${intake.observed.quality}, latency ${intake.observed.latencyMs} ms, cost $${intake.observed.costUsd} — errors vs the winner prediction recorded per dimension.`,
      },
      {
        stage: "calibration",
        detail: `Rebuilt the calibration model from this pass: factors ${factorsSummary}; curve ${calibration.curve.length} bucket(s) from ${calibration.observations} observation(s) (factors stay 1.000 below 3 observations).`,
      },
    ];

    const refreshedEntry = await db.labBridgeEntry.findUnique({ where: { id: entry.id } });

    return NextResponse.json(
      {
        demo: true as const,
        trace: {
          stages,
          runId: persisted.runId,
          recommendationId: persisted.recommendationId,
          bridgeEntryId: entry.id,
          calibration,
          bridgeEntry:
            refreshedEntry === null ? null : bridgeEntrySummary(refreshedEntry, sentRecommendation),
        },
      },
      { status: 201, headers: NO_STORE },
    );
  } catch (error) {
    if (error instanceof LabError) {
      return NextResponse.json({ error: error.message }, { status: 400, headers: NO_STORE });
    }
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Closed-loop demo failed: ${message}` },
      { status: 500, headers: NO_STORE },
    );
  }
}
