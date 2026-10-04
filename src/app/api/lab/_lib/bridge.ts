/**
 * Engineering Lab API — bridge entry summaries (B3-b).
 *
 * Shared shape + mapper so the bridge list / detail / observe routes and the
 * closed-loop demo render identical entry JSON. Follows the _lib conventions:
 * the joined recommendation's artifact is read through the guard pattern, and
 * rows degrade to nulls instead of throwing.
 */

import { recommendationSummaryFromRow, type RecommendationRowLike } from "./summary";

/** The note stamped on every fixture-mode bridge entry. */
export const BRIDGE_NOTE =
  "Queued via LabExecutionPort (fixture mode). Real Flauz execution requires the Agent OS lane — the flauz adapter refuses until wired.";

export interface BridgeEntrySummary {
  id: string;
  recommendationId: string;
  runId: string;
  status: string;
  note: string;
  portMode: string;
  submittedAt: string;
  observedAt: string | null;
  winnerName: string | null;
  confidence: number | null;
}

export interface BridgeEntryRowLike {
  id: string;
  recommendationId: string;
  status: string;
  note: string;
  portMode: string;
  submittedAt: Date;
  observedAt: Date | null;
}

export function bridgeEntrySummary(
  entry: BridgeEntryRowLike,
  recommendation: RecommendationRowLike | null,
): BridgeEntrySummary {
  const rec = recommendation === null ? null : recommendationSummaryFromRow(recommendation);
  return {
    id: entry.id,
    recommendationId: entry.recommendationId,
    runId: rec?.runId ?? "",
    status: entry.status,
    note: entry.note,
    portMode: entry.portMode,
    submittedAt: entry.submittedAt.toISOString(),
    observedAt: entry.observedAt === null ? null : entry.observedAt.toISOString(),
    winnerName: rec?.winnerName ?? null,
    confidence: rec?.confidence ?? null,
  };
}
