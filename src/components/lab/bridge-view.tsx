"use client";

/**
 * Engineering Lab — Bridge subview (B3-b, mission step 10).
 *
 * The execution-bridge queue: every entry is a recommendation sent to the
 * LabExecutionPort in FIXTURE mode (the flauz adapter stays closed behind
 * Agent OS — the port law is stated in the header card). Queued entries can
 * be observed through the deterministic intake; observed entries open a
 * dialog with predicted vs observed vs error per dimension (positive-better
 * orientation). No optimistic UI — mutations invalidate and refetch.
 */

import { useState } from "react";
import {
  ArrowUpRight,
  Eye,
  Loader2,
  Network,
  RefreshCw,
  Rocket,
  TriangleAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  useClosedLoopDemo,
  useLabBridge,
  useLabBridgeEntry,
  useObserveBridgeEntry,
  type BridgeEntrySummary,
} from "./lab-api";
import { DIMENSION_LABELS, dimensionValue, percent, relativeTime, shortId } from "./format";
import { DeltaBadge } from "./badges";

/** Positive-better orientation labels per dimension (contract law). */
const DIRECTION_NOTES: Record<EvalDimension, string> = {
  success: "positive = observed succeeded where success was in doubt",
  quality: "positive = observed quality above prediction",
  latency: "positive = observed faster than predicted",
  cost: "positive = observed cheaper than predicted",
};

export function BridgeView({ onOpenRun }: { onOpenRun: (runId: string) => void }) {
  const bridge = useLabBridge();
  const demo = useClosedLoopDemo();
  const { toast } = useToast();
  const [detailEntryId, setDetailEntryId] = useState<string | null>(null);

  const runDemo = () => {
    demo.mutate(undefined, {
      onSuccess: (result) => {
        toast({
          title: "Closed-loop demo complete",
          description: `10 stages · run ${shortId(result.trace.runId)} · bridge entry observed`,
        });
      },
      onError: (error: Error) => {
        toast({ variant: "destructive", title: "Closed-loop demo failed", description: error.message });
      },
    });
  };

  if (bridge.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading execution bridge">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }

  if (bridge.isError) {
    return (
      <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Execution bridge unavailable</AlertTitle>
        <AlertDescription className="text-rose-300/80">
          {bridge.error instanceof Error ? bridge.error.message : "fetch failed"}
        </AlertDescription>
        <Button
          variant="outline"
          size="sm"
          className="mt-2 h-11 border-rose-900/70 bg-transparent text-rose-200 hover:bg-rose-950/60"
          onClick={() => void bridge.refetch()}
        >
          <RefreshCw aria-hidden="true" /> Retry
        </Button>
      </Alert>
    );
  }

  const entries = bridge.data.entries;

  return (
    <div className="flex flex-col gap-4">
      {/* Port law header */}
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
        <div className="flex items-center gap-2">
          <Network className="h-4 w-4 text-emerald-400" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-neutral-200">Execution bridge</h2>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-neutral-400">
          The Lab never bypasses Agent OS — the flauz adapter stays closed;
          entries execute in fixture mode. Every sent recommendation becomes a
          bridge entry; observing one runs the deterministic intake and feeds
          the calibration model.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-800/70 bg-emerald-950/60 px-2.5 py-1 text-[10px] font-medium text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
            fixture · live
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-900/70 bg-rose-950/50 px-2.5 py-1 text-[10px] font-medium text-rose-300">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-400" aria-hidden="true" />
            flauz · closed — requires Agent OS lane
          </span>
        </div>
      </Card>

      {/* Entries */}
      <section aria-label="Bridge entries">
        <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Bridge entries</h2>
        {entries.length === 0 ? (
          <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
            <p>No recommendations sent yet.</p>
            <p className="mt-1 text-xs text-neutral-500">
              Send an issued recommendation from a run detail (open a completed
              run and use “Send to execution”), or light the whole loop up at
              once:
            </p>
            <Button
              className="mt-3 h-11 bg-emerald-600 text-neutral-950 hover:bg-emerald-500 focus-visible:ring-emerald-400/60"
              onClick={runDemo}
              disabled={demo.isPending}
            >
              {demo.isPending ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Rocket aria-hidden="true" />
              )}
              {demo.isPending ? "Running the loop…" : "Run closed-loop demo"}
            </Button>
          </Card>
        ) : (
          <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-0 shadow-none">
            <div className="overflow-x-auto">
              <Table className="text-neutral-300">
                <TableHeader className="[&_tr]:border-neutral-800">
                  <TableRow className="hover:bg-transparent">
                    <TableHead scope="col" className="pl-4 text-neutral-400">Recommendation</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Run</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Status</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Port</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Submitted</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Observed</TableHead>
                    <TableHead scope="col" className="pr-4 text-right text-neutral-400">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="[&_tr]:border-neutral-800">
                  {entries.map((entry) => (
                    <BridgeRow
                      key={entry.id}
                      entry={entry}
                      onOpenRun={onOpenRun}
                      onOpenDetail={() => setDetailEntryId(entry.id)}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        )}
      </section>

      {/* Observed-entry detail dialog */}
      <ObservationDialog entryId={detailEntryId} onClose={() => setDetailEntryId(null)} />
    </div>
  );
}

function BridgeStatusBadge({ status }: { status: string }) {
  const accent =
    status === "observed"
      ? "border-emerald-800/70 bg-emerald-950/60 text-emerald-300"
      : status === "blocked"
        ? "border-rose-900/70 bg-rose-950/60 text-rose-300"
        : "border-amber-800/70 bg-amber-950/60 text-amber-300";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${accent}`}>
      {status}
    </span>
  );
}

function BridgeRow({
  entry,
  onOpenRun,
  onOpenDetail,
}: {
  entry: BridgeEntrySummary;
  onOpenRun: (runId: string) => void;
  onOpenDetail: () => void;
}) {
  const observe = useObserveBridgeEntry();
  const { toast } = useToast();

  const observeOutcome = () => {
    observe.mutate(entry.id, {
      onSuccess: () => {
        toast({
          title: "Outcome observed",
          description: `Entry ${shortId(entry.id)} observed — calibration model refreshed.`,
        });
      },
      onError: (error: Error) => {
        toast({ variant: "destructive", title: "Observation failed", description: error.message });
      },
    });
  };

  return (
    <TableRow className="hover:bg-neutral-800/40">
      <TableCell className="pl-4">
        <span className="block max-w-[16rem] truncate text-[13px] font-semibold text-neutral-100">
          {entry.winnerName ?? "recommendation"}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5">
          <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-neutral-800 sm:block" aria-hidden="true">
            <span
              className="block h-full rounded-full bg-emerald-500"
              style={{ width: `${Math.round((entry.confidence ?? 0) * 100)}%` }}
            />
          </span>
          <span className="font-mono text-[10px] tabular-nums text-emerald-300">
            {entry.confidence === null ? "—" : percent(entry.confidence)}
          </span>
        </span>
      </TableCell>
      <TableCell>
        {entry.runId ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-11 px-3 text-neutral-400 hover:bg-neutral-800/60 hover:text-emerald-300 focus-visible:ring-emerald-400/60"
            onClick={() => onOpenRun(entry.runId)}
            aria-label={`Open the run behind bridge entry ${entry.id}`}
          >
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            run
          </Button>
        ) : (
          <span className="text-neutral-600">—</span>
        )}
      </TableCell>
      <TableCell><BridgeStatusBadge status={entry.status} /></TableCell>
      <TableCell className="font-mono text-[10px] text-neutral-400">{entry.portMode}</TableCell>
      <TableCell className="text-xs text-neutral-400">{relativeTime(entry.submittedAt)}</TableCell>
      <TableCell className="text-xs text-neutral-400">
        {entry.observedAt === null ? "—" : relativeTime(entry.observedAt)}
      </TableCell>
      <TableCell className="pr-4 text-right">
        {entry.status === "observed" ? (
          <Button
            variant="outline"
            size="sm"
            className="h-11 border-neutral-700 bg-neutral-900 text-neutral-200 hover:bg-neutral-800 focus-visible:ring-emerald-400/60"
            onClick={onOpenDetail}
            aria-label={`Show the observed outcome for bridge entry ${entry.id}`}
          >
            <Eye className="h-4 w-4" aria-hidden="true" />
            Details
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="h-11 border-emerald-800/70 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-950/70 focus-visible:ring-emerald-400/60"
            onClick={observeOutcome}
            disabled={observe.isPending}
            aria-label={`Observe the outcome of bridge entry ${entry.id}`}
          >
            {observe.isPending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : null}
            {observe.isPending ? "Observing…" : "Observe outcome"}
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

function ObservationDialog({ entryId, onClose }: { entryId: string | null; onClose: () => void }) {
  const detail = useLabBridgeEntry(entryId);

  return (
    <Dialog open={entryId !== null} onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-y-auto border-neutral-800 bg-neutral-900 p-4 text-neutral-200 sm:p-6 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700">
        {detail.isPending ? (
          <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading bridge entry detail">
            <DialogHeader>
              <DialogTitle>Observed outcome</DialogTitle>
              <DialogDescription className="sr-only">Loading the observed outcome.</DialogDescription>
            </DialogHeader>
            <Skeleton className="h-40 w-full" />
          </div>
        ) : detail.isError || !detail.data ? (
          <div className="flex flex-col gap-3">
            <DialogHeader>
              <DialogTitle>Observed outcome</DialogTitle>
              <DialogDescription>The observation detail could not be loaded.</DialogDescription>
            </DialogHeader>
            <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
              <TriangleAlert aria-hidden="true" />
              <AlertDescription className="text-rose-300/80">
                {detail.error instanceof Error ? detail.error.message : "fetch failed"}
              </AlertDescription>
            </Alert>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle className="text-left">
                {detail.data.entry.winnerName ?? "Observed outcome"}
              </DialogTitle>
              <DialogDescription className="text-left text-xs text-neutral-400">
                Bridge entry {shortId(detail.data.entry.id)} · fixture mode ·{" "}
                {detail.data.entry.observedAt === null
                  ? "not observed"
                  : `observed ${relativeTime(detail.data.entry.observedAt)}`}
              </DialogDescription>
            </DialogHeader>

            {detail.data.predicted === null || detail.data.error === null ? (
              <p className="text-xs text-neutral-500">
                No calibration observation recorded for this entry yet.
              </p>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <Table className="text-neutral-300">
                    <TableHeader className="[&_tr]:border-neutral-800">
                      <TableRow className="hover:bg-transparent">
                        <TableHead scope="col" className="pl-0 text-neutral-400">Dimension</TableHead>
                        <TableHead scope="col" className="text-neutral-400">Predicted</TableHead>
                        <TableHead scope="col" className="text-neutral-400">Observed</TableHead>
                        <TableHead scope="col" className="pr-0 text-neutral-400">Error</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody className="[&_tr]:border-neutral-800">
                      {detail.data.error.map((row) => (
                        <TableRow key={row.dimension} className="hover:bg-neutral-800/40">
                          <TableCell className="pl-0 text-neutral-200">
                            {DIMENSION_LABELS[row.dimension]}
                            <span className="block text-[9px] text-neutral-600">
                              {DIRECTION_NOTES[row.dimension]}
                            </span>
                          </TableCell>
                          <TableCell className="font-mono text-xs tabular-nums text-neutral-400">
                            {dimensionValue(row.dimension, row.predicted)}
                          </TableCell>
                          <TableCell className="font-mono text-xs tabular-nums text-neutral-100">
                            {dimensionValue(row.dimension, row.observed)}
                          </TableCell>
                          <TableCell className="pr-0">
                            <DeltaBadge dimension={row.dimension} delta={row.error} compact />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {detail.data.observation ? (
                  <section aria-label="Observed verification checks">
                    <h3 className="text-xs font-semibold text-neutral-300">Verification checks</h3>
                    <ul className="mt-1.5 flex flex-col gap-1">
                      {detail.data.observation.verification.map((check) => (
                        <li
                          key={check.check}
                          className="flex items-start gap-1.5 text-[11px] leading-relaxed text-neutral-400"
                        >
                          <span
                            className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${check.passed ? "bg-emerald-400" : "bg-rose-400"}`}
                            aria-hidden="true"
                          />
                          <span className="min-w-0">
                            {check.check}
                            <span className="sr-only"> — {check.passed ? "passed" : "failed"}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                <p className="text-[11px] leading-relaxed text-neutral-500">{detail.data.entry.note}</p>
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
