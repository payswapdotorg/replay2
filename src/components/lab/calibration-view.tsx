"use client";

/**
 * Engineering Lab — Calibration subview (B3-b, mission step 11).
 *
 * The calibration model over the observation store: multiplicative factors
 * per dimension (observed ÷ predicted, with direction notes), the reliability
 * curve as an accessible grouped-bar chart (predicted vs observed success per
 * bucket — pure divs, no new deps), the latest observation rows with
 * per-dimension error badges, and the model's updatedAt stamp. Empty state
 * offers the closed-loop demo. Fixture honesty is stated in the caption.
 */

import {
  LineChart,
  Loader2,
  RefreshCw,
  Rocket,
  TriangleAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import { useClosedLoopDemo, useLabCalibration } from "./lab-api";
import { DIMENSION_LABELS, percent, relativeTime, shortId } from "./format";
import { DeltaBadge } from "./badges";

const DIMENSIONS: EvalDimension[] = ["success", "quality", "latency", "cost"];

/** Direction notes: factors are observed ÷ predicted for every dimension. */
const FACTOR_NOTES: Record<EvalDimension, string> = {
  success: "observed ÷ predicted — above 1: real outcomes beat the prediction",
  quality: "observed ÷ predicted — above 1: real quality above the prediction",
  latency: "observed ÷ predicted — below 1: real runs faster than predicted",
  cost: "observed ÷ predicted — below 1: real runs cheaper than predicted",
};

export function CalibrationView() {
  const calibration = useLabCalibration();
  const demo = useClosedLoopDemo();
  const { toast } = useToast();

  const runDemo = () => {
    demo.mutate(undefined, {
      onSuccess: (result) => {
        toast({
          title: "Closed-loop demo complete",
          description: `10 stages · run ${shortId(result.trace.runId)} · calibration rebuilt`,
        });
      },
      onError: (error: Error) => {
        toast({ variant: "destructive", title: "Closed-loop demo failed", description: error.message });
      },
    });
  };

  if (calibration.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading calibration model">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  if (calibration.isError) {
    return (
      <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Calibration unavailable</AlertTitle>
        <AlertDescription className="text-rose-300/80">
          {calibration.error instanceof Error ? calibration.error.message : "fetch failed"}
        </AlertDescription>
        <Button
          variant="outline"
          size="sm"
          className="mt-2 h-11 border-rose-900/70 bg-transparent text-rose-200 hover:bg-rose-950/60"
          onClick={() => void calibration.refetch()}
        >
          <RefreshCw aria-hidden="true" /> Retry
        </Button>
      </Alert>
    );
  }

  const model = calibration.data.calibration;
  const observations = calibration.data.observations;

  if (model === null) {
    return (
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
        <div className="flex items-center gap-2">
          <LineChart className="h-4 w-4 text-neutral-500" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-neutral-200">Calibration model</h2>
        </div>
        <p className="mt-1.5">
          No calibration observations yet — the model builds once a bridge
          entry is observed (predicted vs observed per dimension).
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
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Factors */}
      <section aria-label="Calibration factors">
        <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Calibration model</h2>
        <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-neutral-400">
              {model.observations} observation{model.observations === 1 ? "" : "s"} · factors
              stay 1.000 below 3 observations
            </span>
            <span className="text-xs text-neutral-500">
              updated {model.updatedAt ? relativeTime(model.updatedAt) : "—"}
            </span>
          </div>
          <div className="mt-3 overflow-x-auto">
            <Table className="text-neutral-300">
              <TableHeader className="[&_tr]:border-neutral-800">
                <TableRow className="hover:bg-transparent">
                  <TableHead scope="col" className="pl-0 text-neutral-400">Dimension</TableHead>
                  <TableHead scope="col" className="text-neutral-400">Factor</TableHead>
                  <TableHead scope="col" className="pr-0 text-neutral-400">Direction</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="[&_tr]:border-neutral-800">
                {DIMENSIONS.map((dimension) => {
                  const factor = model.factors[dimension] ?? 1;
                  return (
                    <TableRow key={dimension} className="hover:bg-neutral-800/40">
                      <TableCell className="pl-0 text-neutral-200">{DIMENSION_LABELS[dimension]}</TableCell>
                      <TableCell>
                        <span
                          className={`font-mono text-xs tabular-nums ${
                            factor > 1
                              ? "text-emerald-300"
                              : factor < 1
                                ? "text-amber-300"
                                : "text-neutral-300"
                          }`}
                        >
                          ×{factor.toFixed(3)}
                        </span>
                      </TableCell>
                      <TableCell className="pr-0 text-[11px] leading-relaxed text-neutral-500">
                        {FACTOR_NOTES[dimension]}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">
            Fixture-mode calibration — demonstrates the loop; live factors
            apply once the flauz door opens.
          </p>
        </Card>
      </section>

      {/* Reliability curve */}
      <section aria-label="Calibration reliability curve">
        <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">
          Reliability curve — predicted vs observed success
        </h2>
        <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
          <div className="flex flex-wrap items-center gap-4 text-[11px] text-neutral-400">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-sm bg-neutral-500" aria-hidden="true" />
              predicted success
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-sm bg-emerald-500" aria-hidden="true" />
              observed success
            </span>
          </div>
          <ul className="mt-4 flex flex-col gap-4">
            {model.curve.map((bucket) => (
              <li key={bucket.rangeLabel}>
                <div className="flex items-center justify-between text-[11px] text-neutral-400">
                  <span className="font-mono">{bucket.rangeLabel}</span>
                  <span>
                    {bucket.count} observation{bucket.count === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-col gap-1">
                  <div
                    className="h-2.5 w-full overflow-hidden rounded-full bg-neutral-800"
                    role="img"
                    aria-label={`Bucket ${bucket.rangeLabel}: predicted success ${percent(bucket.predicted)}`}
                  >
                    <div className="h-full rounded-full bg-neutral-500" style={{ width: `${Math.round(bucket.predicted * 100)}%` }} />
                  </div>
                  <div
                    className="h-2.5 w-full overflow-hidden rounded-full bg-neutral-800"
                    role="img"
                    aria-label={`Bucket ${bucket.rangeLabel}: observed success ${percent(bucket.observed)}`}
                  >
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.round(bucket.observed * 100)}%` }} />
                  </div>
                </div>
                <p className="mt-1 text-[10px] tabular-nums text-neutral-500">
                  predicted {percent(bucket.predicted)} · observed {percent(bucket.observed)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </section>

      {/* Observation ledger */}
      <section aria-label="Calibration observations">
        <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Observations</h2>
        {observations.length === 0 ? (
          <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
            No observation rows returned.
          </Card>
        ) : (
          <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-2 shadow-none">
            <ul
              className="max-h-72 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent"
              aria-label="Calibration observations, newest first"
            >
              {observations.map((row) => (
                <li key={row.id} className="border-b border-neutral-800/60 px-2 py-2.5 last:border-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-[10px] text-neutral-500">
                      {shortId(row.id)} · entry {shortId(row.bridgeEntryId)} · {relativeTime(row.createdAt)}
                    </span>
                  </div>
                  {row.error === null ? (
                    <p className="mt-1 text-[11px] text-neutral-500">error details unavailable</p>
                  ) : (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {row.error.map((entry) => (
                        <span key={entry.dimension} className="inline-flex items-center gap-1.5">
                          <span className="text-[10px] text-neutral-500">
                            {DIMENSION_LABELS[entry.dimension]}
                          </span>
                          <DeltaBadge dimension={entry.dimension} delta={entry.error} compact />
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>
    </div>
  );
}
