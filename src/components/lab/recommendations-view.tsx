"use client";

/**
 * Engineering Lab — Recommendations subview (B3-a).
 *
 * List of issued recommendations with confidence bars and a "→ run" drill
 * that switches to the Runs tab and opens the run detail (via the shared
 * openRun seam in LabConsole). Each row expands inline (Collapsible) to the
 * full recommendation detail fetched from GET /api/lab/recommendations/{id}.
 */

import { useState } from "react";
import {
  ChevronRight,
  ArrowUpRight,
  Lightbulb,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  isRecommendationArtifact,
  useLabRecommendation,
  useLabRecommendations,
  type RecommendationSummary,
} from "./lab-api";
import { DIMENSION_LABELS, dimensionValue, percent, relativeTime } from "./format";
import { DeltaBadge, TopologyBadge } from "./badges";

export function RecommendationsView({ onOpenRun }: { onOpenRun: (runId: string) => void }) {
  const recommendations = useLabRecommendations();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (recommendations.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading recommendations">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  if (recommendations.isError) {
    return (
      <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Recommendations unavailable</AlertTitle>
        <AlertDescription className="text-rose-300/80">
          {recommendations.error instanceof Error ? recommendations.error.message : "fetch failed"}
        </AlertDescription>
        <Button
          variant="outline"
          size="sm"
          className="mt-2 h-11 border-rose-900/70 bg-transparent text-rose-200 hover:bg-rose-950/60"
          onClick={() => void recommendations.refetch()}
        >
          <RefreshCw aria-hidden="true" /> Retry
        </Button>
      </Alert>
    );
  }

  const list = recommendations.data.recommendations;

  if (list.length === 0) {
    return (
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
        No recommendations yet — run an evaluation on the Runs tab; every
        completed run issues one.
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Issued recommendations">
        <ul
          className="max-h-[44rem] overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent"
          aria-label="Recommendations, newest first"
        >
          {list.map((rec) => (
            <li key={rec.id} className="mb-3 last:mb-0">
              <RecommendationRow
                rec={rec}
                onOpenRun={onOpenRun}
                expanded={expandedId === rec.id}
                onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function RecommendationRow({
  rec,
  onOpenRun,
  expanded,
  onToggle,
}: {
  rec: RecommendationSummary;
  onOpenRun: (runId: string) => void;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <Collapsible open={expanded} onOpenChange={onToggle}>
      <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-2 shadow-none transition-colors data-[state=open]:border-neutral-700">
        <div className="flex items-center gap-2">
          <CollapsibleTrigger className="group flex min-h-11 flex-1 items-center gap-2 rounded-lg px-2 text-left transition-colors hover:bg-neutral-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60">
            <ChevronRight
              className="h-4 w-4 shrink-0 text-neutral-500 transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
              aria-hidden="true"
            />
            <Lightbulb className="h-4 w-4 shrink-0 text-emerald-400" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-neutral-100">
                {rec.winnerName ?? "recommendation"}
              </span>
              <span className="block truncate text-[10px] text-neutral-500">
                {relativeTime(rec.createdAt)} · run {rec.runId.slice(0, 8)}
              </span>
            </span>
            <span className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-neutral-800 sm:block" aria-hidden="true">
              <span
                className="block h-full rounded-full bg-emerald-500"
                style={{ width: `${Math.round((rec.confidence ?? 0) * 100)}%` }}
              />
            </span>
            <span className="font-mono text-[10px] tabular-nums text-emerald-300">
              {rec.confidence === null ? "—" : percent(rec.confidence)}
            </span>
            <span className="rounded-full border border-emerald-800/70 bg-emerald-950/60 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
              {rec.status}
            </span>
          </CollapsibleTrigger>
          <Button
            variant="ghost"
            size="sm"
            className="h-11 shrink-0 px-3 text-neutral-400 hover:bg-neutral-800/60 hover:text-emerald-300 focus-visible:ring-emerald-400/60"
            onClick={() => onOpenRun(rec.runId)}
            aria-label={`Open the run behind recommendation ${rec.id}`}
          >
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            run
          </Button>
        </div>
        <CollapsibleContent>
          <RecommendationDetailBody recommendationId={rec.id} />
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function RecommendationDetailBody({ recommendationId }: { recommendationId: string }) {
  const detail = useLabRecommendation(recommendationId);

  if (detail.isPending) {
    return <Skeleton className="m-2 h-32 rounded-lg" />;
  }

  if (detail.isError || !detail.data) {
    return (
      <Alert className="m-2 border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertDescription className="text-rose-300/80">
          {detail.error instanceof Error ? detail.error.message : "fetch failed"}
        </AlertDescription>
      </Alert>
    );
  }

  const artifact = detail.data.artifact;
  if (!isRecommendationArtifact(artifact)) {
    return (
      <p className="m-2 text-xs text-neutral-500">
        Recommendation artifact unavailable for {detail.data.id}.
      </p>
    );
  }

  const nodeSummary = artifact.organization.nodes
    .map((n) => n.role)
    .join(", ");
  const modelsSummary =
    artifact.occupancy.length > 0
      ? [...new Set(artifact.occupancy.map((o) => o.modelId))].join(", ")
      : "default occupancy";

  return (
    <div className="border-t border-neutral-800 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-neutral-100">{artifact.organization.name}</span>
        <TopologyBadge topology={artifact.organization.topology} />
        <span className="font-mono text-[10px] text-neutral-600">
          {artifact.organization.nodes.length} nodes
        </span>
      </div>
      <p className="mt-1 text-[11px] text-neutral-500">
        {nodeSummary} · occupancy: <span className="font-mono">{modelsSummary}</span>
      </p>
      <p className="mt-2 text-xs leading-relaxed text-neutral-300">{artifact.rationale}</p>

      <div className="mt-3 overflow-x-auto">
        <Table className="text-neutral-300">
          <TableHeader className="[&_tr]:border-neutral-800">
            <TableRow className="hover:bg-transparent">
              <TableHead scope="col" className="text-[10px] text-neutral-500">Expected gain</TableHead>
              <TableHead scope="col" className="text-[10px] text-neutral-500">Baseline</TableHead>
              <TableHead scope="col" className="text-[10px] text-neutral-500">With org</TableHead>
              <TableHead scope="col" className="text-[10px] text-neutral-500">Delta</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr]:border-neutral-800/60">
            {artifact.expectedGains.map((gain) => (
              <TableRow key={gain.dimension} className="hover:bg-neutral-800/40">
                <TableCell className="text-[11px] text-neutral-200">{DIMENSION_LABELS[gain.dimension]}</TableCell>
                <TableCell className="font-mono text-[11px] tabular-nums text-neutral-400">
                  {dimensionValue(gain.dimension, gain.baselineValue)}
                </TableCell>
                <TableCell className="font-mono text-[11px] tabular-nums text-neutral-100">
                  {dimensionValue(gain.dimension, gain.candidateValue)}
                </TableCell>
                <TableCell><DeltaBadge dimension={gain.dimension} delta={gain.delta} compact /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="mt-3 flex flex-col gap-1.5">
        {artifact.caveats.map((caveat) => (
          <li key={caveat} className="flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-300/90">
            <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
            {caveat}
          </li>
        ))}
      </ul>
    </div>
  );
}
