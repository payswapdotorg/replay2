"use client";

/**
 * Engineering Lab — run detail (B3-a).
 *
 * Renders a persisted run end-to-end: winner header, organization chart,
 * baseline-vs-winner comparison, occupancy & capabilities, robustness (L2),
 * grouped search trace and the issued recommendation. Failed runs (stub
 * artifacts) degrade to an explicit alert instead of guessing. Everything is
 * server-confirmed data from GET /api/lab/runs/{id}.
 */

import { useMemo } from "react";
import {
  ArrowLeft,
  ChevronRight,
  Lightbulb,
  Loader2,
  RefreshCw,
  Send,
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
import type { EvalDimension } from "@/lib/lab/contracts";
import { useToast } from "@/hooks/use-toast";
import {
  buildLookups,
  isRecommendationArtifact,
  isRunArtifact,
  useLabCatalog,
  useLabRecommendations,
  useLabRun,
  useSendToBridge,
  type RecommendationSummary,
} from "./lab-api";
import {
  DIMENSION_LABELS,
  absoluteTime,
  dimensionValue,
  percent,
  relativeTime,
  signed,
} from "./format";
import {
  DeltaBadge,
  LadderBadge,
  ModelTierBadge,
  RunStatusBadge,
  TopologyBadge,
} from "./badges";
import { OrgChart } from "./org-chart";
import { RobustnessPanel } from "./robustness-panel";

export function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const detail = useLabRun(runId);
  const catalog = useLabCatalog();
  // The recommendation LEDGER (ids + status) for this run — the detail route
  // serves the artifact, the id/status come from the recommendations list.
  const recommendations = useLabRecommendations();
  const recRow =
    recommendations.data?.recommendations.find((r) => r.runId === runId) ?? null;
  const recStatus = recRow?.status ?? "issued";

  const lookups = useMemo(
    () => (catalog.data ? buildLookups(catalog.data) : null),
    [catalog.data],
  );

  if (detail.isPending) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading run detail">
        <Skeleton className="h-10 w-36 rounded-md" />
        <Skeleton className="h-36 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="flex flex-col gap-4">
        <Button
          variant="outline"
          onClick={onBack}
          className="h-11 w-fit border-neutral-700 bg-neutral-900 text-neutral-200 hover:bg-neutral-800 focus-visible:ring-emerald-400/60"
        >
          <ArrowLeft aria-hidden="true" /> Back to runs
        </Button>
        <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Run unavailable</AlertTitle>
          <AlertDescription className="text-rose-300/80">
            {detail.error instanceof Error ? detail.error.message : "fetch failed"}
          </AlertDescription>
          <Button
            variant="outline"
            size="sm"
            className="mt-2 h-11 border-rose-900/70 bg-transparent text-rose-200 hover:bg-rose-950/60"
            onClick={() => void detail.refetch()}
          >
            <RefreshCw aria-hidden="true" /> Retry
          </Button>
        </Alert>
      </div>
    );
  }

  const { run, artifact, recommendation } = detail.data;
  const rec = isRecommendationArtifact(recommendation) ? recommendation : null;

  if (!isRunArtifact(artifact)) {
    // Failed run: persisted stub artifact — surface the server-confirmed error.
    return (
      <div className="flex flex-col gap-4">
        <Button
          variant="outline"
          onClick={onBack}
          className="h-11 w-fit border-neutral-700 bg-neutral-900 text-neutral-200 hover:bg-neutral-800 focus-visible:ring-emerald-400/60"
        >
          <ArrowLeft aria-hidden="true" /> Back to runs
        </Button>
        <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Run {run.id.slice(0, 8)} did not complete</AlertTitle>
          <AlertDescription className="text-rose-300/80">
            {run.error ?? "The run failed before an artifact was produced."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const winnerOrg = artifact.winner.organization;
  const baselineOrg = artifact.baseline.organization;
  const utilityDelta = artifact.winner.utility - artifact.baseline.utility;
  const workloadName = lookups?.workloads.get(run.workloadId)?.name ?? run.workloadId;
  const taskTypeName = lookups?.taskTypes.get(run.taskTypeId)?.name ?? run.taskTypeId;
  const scenarioName = lookups?.scenarios.get(run.scenarioId)?.name ?? run.scenarioId;
  const traceGroups = groupTrace(artifact.search.trace);

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
      <Button
        variant="outline"
        onClick={onBack}
        className="h-11 w-fit border-neutral-700 bg-neutral-900 text-neutral-200 hover:bg-neutral-800 focus-visible:ring-emerald-400/60"
      >
        <ArrowLeft aria-hidden="true" /> Back to runs
      </Button>

      {/* Header */}
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-bold text-neutral-100">{winnerOrg.name}</h2>
          <TopologyBadge topology={winnerOrg.topology} />
          <RunStatusBadge status={run.status} />
          <LadderBadge level={run.ladderLevel} />
          <DeltaBadge dimension="success" delta={utilityDelta} compact />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
          <Detail label="Workload" value={workloadName} />
          <Detail label="Task type" value={taskTypeName} />
          <Detail label="Scenario" value={scenarioName} />
          <Detail label="Baseline" value={baselineOrg.name} />
          <Detail label="Seeds" value={run.seeds.length > 0 ? run.seeds.join(", ") : "derived"} />
          <Detail label="Created" value={`${relativeTime(run.createdAt)} · ${absoluteTime(run.createdAt)}`} />
          <Detail label="Candidates evaluated" value={String(artifact.search.candidatesEvaluated)} />
          <Detail
            label="Utility weights"
            value={(Object.keys(artifact.utilityWeights) as EvalDimension[])
              .map((d) => `${DIMENSION_LABELS[d]} ${percent(artifact.utilityWeights[d])}`)
              .join(" · ")}
          />
        </dl>
        <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">{artifact.search.ladderNote}</p>
      </Card>

      {/* Organization chart */}
      <section aria-label="Winner organization chart">
        {lookups ? (
          <OrgChart
            organization={winnerOrg}
            occupancy={artifact.winner.occupancy}
            capabilities={artifact.winner.capabilities}
            lookups={lookups}
          />
        ) : (
          <Skeleton className="h-64 rounded-xl" />
        )}
      </section>

      {/* Baseline vs winner scores */}
      <section aria-label="Baseline versus winner comparison">
        <h3 className="mb-2 px-1 text-sm font-semibold text-neutral-300">
          Baseline vs winner — deltas oriented positive-better
        </h3>
        <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-0 shadow-none">
          <Table className="text-neutral-300">
            <TableHeader className="[&_tr]:border-neutral-800">
              <TableRow className="hover:bg-transparent">
                <TableHead scope="col" className="pl-4 text-neutral-400">Dimension</TableHead>
                <TableHead scope="col" className="text-neutral-400">Baseline (solo)</TableHead>
                <TableHead scope="col" className="text-neutral-400">Winner</TableHead>
                <TableHead scope="col" className="pr-4 text-neutral-400">Delta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="[&_tr]:border-neutral-800">
              {artifact.comparison.map((row) => (
                <TableRow key={row.dimension} className="hover:bg-neutral-800/40">
                  <TableCell className="pl-4 text-neutral-200">{DIMENSION_LABELS[row.dimension]}</TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-neutral-400">
                    {dimensionValue(row.dimension, row.baselineValue)}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-neutral-100">
                    {dimensionValue(row.dimension, row.candidateValue)}
                  </TableCell>
                  <TableCell className="pr-4"><DeltaBadge dimension={row.dimension} delta={row.delta} /></TableCell>
                </TableRow>
              ))}
              <TableRow className="hover:bg-neutral-800/40">
                <TableCell className="pl-4 text-neutral-200">Utility</TableCell>
                <TableCell className="font-mono text-xs tabular-nums text-neutral-400">
                  {artifact.baseline.utility.toFixed(6)}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums text-neutral-100">
                  {artifact.winner.utility.toFixed(6)}
                </TableCell>
                <TableCell className="pr-4">
                  <span className={`font-mono text-xs tabular-nums ${utilityDelta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {signed(utilityDelta, 6)}
                  </span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </section>

      {/* Occupancy & capabilities */}
      <section aria-label="Occupancy and capabilities">
        <h3 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Occupancy & capabilities</h3>
        <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-0 shadow-none">
          <div className="overflow-x-auto">
            <Table className="text-neutral-300">
              <TableHeader className="[&_tr]:border-neutral-800">
                <TableRow className="hover:bg-transparent">
                  <TableHead scope="col" className="pl-4 text-neutral-400">Node</TableHead>
                  <TableHead scope="col" className="text-neutral-400">Body</TableHead>
                  <TableHead scope="col" className="text-neutral-400">Model</TableHead>
                  <TableHead scope="col" className="pr-4 text-neutral-400">Tools</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="[&_tr]:border-neutral-800">
                {winnerOrg.nodes.map((node) => {
                  const body = lookups?.bodies.get(node.bodyId);
                  const modelId = artifact.winner.occupancy.find((o) => o.nodeId === node.id)?.modelId;
                  const model = modelId ? lookups?.models.get(modelId) : undefined;
                  const toolIds = artifact.winner.capabilities.find((c) => c.nodeId === node.id)?.toolIds ?? [];
                  return (
                    <TableRow key={node.id} className="hover:bg-neutral-800/40">
                      <TableCell className="pl-4">
                        <span className="text-neutral-200">{node.role}</span>
                        <span className="block font-mono text-[10px] text-neutral-600">{node.id}</span>
                      </TableCell>
                      <TableCell className="text-neutral-300">
                        {body?.name ?? node.bodyId}
                        <span className="block text-[10px] text-neutral-600">{body?.archetype ?? "—"}</span>
                      </TableCell>
                      <TableCell>
                        {model ? (
                          <span className="flex items-center gap-1.5 text-neutral-200">
                            {model.name}
                            <ModelTierBadge tier={model.tier} />
                          </span>
                        ) : (
                          <span className="text-neutral-600">unassigned</span>
                        )}
                      </TableCell>
                      <TableCell className="pr-4 text-xs text-neutral-400">
                        {toolIds.length === 0
                          ? "—"
                          : toolIds
                              .map((t) => lookups?.tools.get(t)?.name ?? t)
                              .join(", ")}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      </section>

      {/* Robustness (L2 runs only) */}
      {artifact.robustness ? (
        <RobustnessPanel robustness={artifact.robustness} comparison={artifact.comparison} />
      ) : null}

      {/* Search trace */}
      <section aria-label="Search trace">
        <h3 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Search trace</h3>
        <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-2 shadow-none">
          <ul
            className="max-h-72 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent"
            aria-label="Search trace grouped by stage"
          >
            {traceGroups.map((group) => (
              <li key={group.stage} className="border-b border-neutral-800/60 last:border-0">
                <Collapsible>
                  <CollapsibleTrigger className="group flex min-h-11 w-full items-start gap-2 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-neutral-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60">
                    <ChevronRight
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-500 transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="text-xs font-semibold text-neutral-200">
                        {group.stage}
                        <span className="ml-1.5 font-mono text-[10px] text-neutral-500">×{group.entries.length}</span>
                      </span>
                      <span className="block truncate text-[11px] text-neutral-500">
                        {group.entries[0].detail}
                      </span>
                    </span>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <ul className="ml-8 border-l border-neutral-800 py-1 pr-2">
                      {group.entries.map((entry, i) => (
                        <li key={`${group.stage}-${i}`} className="py-1 pl-3 text-[11px] leading-relaxed text-neutral-400">
                          {entry.detail}
                        </li>
                      ))}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>
              </li>
            ))}
          </ul>
        </Card>
      </section>

      {/* Recommendation */}
      {rec ? (
        <section aria-label="Issued recommendation">
          <h3 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Recommendation</h3>
          <Card className="border-emerald-900/50 bg-neutral-900/60 p-4 shadow-none sm:p-6">
            <div className="flex flex-wrap items-center gap-2">
              <Lightbulb className="h-4 w-4 text-emerald-400" aria-hidden="true" />
              <h4 className="text-sm font-semibold text-neutral-100">{rec.organization.name}</h4>
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                  recStatus === "sent"
                    ? "border-emerald-800/70 bg-emerald-950/60 text-emerald-300"
                    : "border-neutral-700 bg-neutral-900 text-neutral-300"
                }`}
              >
                {recStatus}
              </span>
              {recStatus === "issued" ? (
                <span className="ml-auto">
                  <SendToBridgeButton recRow={recRow} ledgerPending={recommendations.isPending} />
                </span>
              ) : null}
            </div>
            {recStatus === "sent" ? (
              <p className="mt-2 text-[11px] leading-relaxed text-emerald-300/80">
                Sent to the execution bridge — track the entry and its observed
                outcome on the Bridge tab.
              </p>
            ) : null}
            <p className="mt-2 text-xs leading-relaxed text-neutral-300">{rec.rationale}</p>
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="overflow-x-auto">
                <Table className="text-neutral-300">
                  <TableHeader className="[&_tr]:border-neutral-800">
                    <TableRow className="hover:bg-transparent">
                      <TableHead scope="col" className="text-neutral-400">Expected gain</TableHead>
                      <TableHead scope="col" className="text-neutral-400">Baseline</TableHead>
                      <TableHead scope="col" className="text-neutral-400">With org</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className="[&_tr]:border-neutral-800">
                    {rec.expectedGains.map((gain) => (
                      <TableRow key={gain.dimension} className="hover:bg-neutral-800/40">
                        <TableCell className="text-neutral-200">
                          {DIMENSION_LABELS[gain.dimension]}
                          <DeltaBadge dimension={gain.dimension} delta={gain.delta} compact />
                        </TableCell>
                        <TableCell className="font-mono text-xs tabular-nums text-neutral-400">
                          {dimensionValue(gain.dimension, gain.baselineValue)}
                        </TableCell>
                        <TableCell className="font-mono text-xs tabular-nums text-neutral-100">
                          {dimensionValue(gain.dimension, gain.candidateValue)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="flex flex-col gap-3">
                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-neutral-400">Confidence</span>
                    <span className="font-mono tabular-nums text-emerald-300">{percent(rec.confidence)}</span>
                  </div>
                  <div
                    className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-neutral-800"
                    role="progressbar"
                    aria-valuenow={Math.round(rec.confidence * 100)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Recommendation confidence"
                  >
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.round(rec.confidence * 100)}%` }} />
                  </div>
                </div>
                <div>
                  <p className="text-xs text-neutral-400">Caveats</p>
                  <ul className="mt-1.5 flex flex-col gap-1.5">
                    {rec.caveats.map((caveat) => (
                      <li key={caveat} className="flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-300/90">
                        <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                        {caveat}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wider text-neutral-600">{label}</dt>
      <dd className="truncate text-neutral-300" title={value}>{value}</dd>
    </div>
  );
}

/** "Send to execution" — POSTs /api/lab/bridge for this run's recommendation.
 *  On success the mutation invalidates the recommendation + bridge queries,
 *  so the panel flips to the "sent" state from server-confirmed data. */
function SendToBridgeButton({
  recRow,
  ledgerPending,
}: {
  recRow: RecommendationSummary | null;
  ledgerPending: boolean;
}) {
  const send = useSendToBridge();
  const { toast } = useToast();

  const submit = () => {
    if (recRow === null) {
      return;
    }
    send.mutate(recRow.id, {
      onSuccess: (result) => {
        toast({
          title: "Sent to execution",
          description: `Bridge entry ${result.entry.id.slice(0, 8)} queued (fixture mode) — observe it on the Bridge tab.`,
        });
      },
      onError: (error: Error) => {
        toast({ variant: "destructive", title: "Send failed", description: error.message });
      },
    });
  };

  const disabled = send.isPending || recRow === null;

  return (
    <Button
      size="sm"
      className="h-11 bg-emerald-600 text-neutral-950 hover:bg-emerald-500 focus-visible:ring-emerald-400/60"
      onClick={submit}
      disabled={disabled}
      aria-label={
        recRow === null
          ? "Send to execution — recommendation ledger loading"
          : "Send this recommendation to the execution bridge"
      }
    >
      {send.isPending ? (
        <Loader2 className="animate-spin" aria-hidden="true" />
      ) : (
        <Send aria-hidden="true" />
      )}
      {send.isPending ? "Sending…" : ledgerPending && recRow === null ? "Loading…" : "Send to execution"}
    </Button>
  );
}

/** Group the (long) chronological trace by stage, preserving order + counts. */
function groupTrace(trace: { stage: string; detail: string }[]): { stage: string; entries: { stage: string; detail: string }[] }[] {
  const groups: { stage: string; entries: { stage: string; detail: string }[] }[] = [];
  for (const entry of trace) {
    const existing = groups.find((g) => g.stage === entry.stage);
    if (existing) existing.entries.push(entry);
    else groups.push({ stage: entry.stage, entries: [entry] });
  }
  return groups;
}
