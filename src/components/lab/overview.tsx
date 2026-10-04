"use client";

/**
 * Engineering Lab — Overview subview (B3-a).
 *
 * KPI cards (world + catalog counts + run/recommendation counts from the
 * APIs), a recent-runs list (max 8, scrollable, drill-through to the run
 * detail) and the closed-loop status stepper. Every number on screen comes
 * from an API response — no invented stats.
 */

import {
  ArrowUpRight,
  Boxes,
  Briefcase,
  ClipboardList,
  Cpu,
  Globe,
  Lightbulb,
  Loader2,
  PlayCircle,
  RefreshCw,
  Rocket,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  useClosedLoopDemo,
  useLabBridge,
  useLabCalibration,
  useLabCatalog,
  useLabRecommendations,
  useLabRuns,
  type ClosedLoopDemoTrace,
  type RunSummary,
} from "./lab-api";
import { relativeTime, shortId, signed } from "./format";
import { LadderBadge, RunStatusBadge } from "./badges";

/** The core-loop stages; the last three are LIVE (B3-b) — they turn emerald
 *  as bridge entries, observations and calibration data appear. */
const LOOP_STAGE_LABELS = [
  "workload",
  "task type",
  "world",
  "org search",
  "occupancy",
  "evaluation",
  "recommendation",
  "bridge",
  "observation",
  "calibration",
] as const;

type LoopStageState = "available" | "live" | "pending";

export function Overview({
  onOpenRun,
  demoTrace,
  onDemoTrace,
}: {
  onOpenRun: (runId: string) => void;
  demoTrace: ClosedLoopDemoTrace | null;
  onDemoTrace: (trace: ClosedLoopDemoTrace) => void;
}) {
  const catalog = useLabCatalog();
  const runs = useLabRuns();
  const recommendations = useLabRecommendations();
  const bridge = useLabBridge();
  const calibration = useLabCalibration();
  const demo = useClosedLoopDemo();
  const { toast } = useToast();

  const bridgeEntries = bridge.data?.entries ?? [];
  const bridgeLive = bridgeEntries.length > 0;
  const observationLive = bridgeEntries.some((entry) => entry.status === "observed");
  const calibrationLive = (calibration.data?.calibration?.observations ?? 0) > 0;
  const loopStages: { label: string; status: LoopStageState }[] = LOOP_STAGE_LABELS.map(
    (label, index) => ({
      label,
      status:
        index < 7
          ? "available"
          : index === 7
            ? bridgeLive
              ? "live"
              : "pending"
            : index === 8
              ? observationLive
                ? "live"
                : "pending"
              : calibrationLive
                ? "live"
                : "pending",
    }),
  );
  const availableCount = loopStages.filter((stage) => stage.status !== "pending").length;

  const runDemo = () => {
    demo.mutate(undefined, {
      onSuccess: (result) => {
        onDemoTrace(result.trace);
        toast({
          title: "Closed-loop demo complete",
          description: `10 stages · run ${shortId(result.trace.runId)} · bridge entry observed · calibration rebuilt`,
        });
      },
      onError: (error: Error) => {
        toast({ variant: "destructive", title: "Closed-loop demo failed", description: error.message });
      },
    });
  };

  if (catalog.isPending) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4" aria-busy="true" aria-label="Loading lab overview">
        <Skeleton className="col-span-2 h-40 rounded-xl" />
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }

  if (catalog.isError) {
    return (
      <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Catalog unavailable</AlertTitle>
        <AlertDescription className="text-rose-300/80">
          {catalog.error instanceof Error ? catalog.error.message : "fetch failed"}
        </AlertDescription>
        <Button
          variant="outline"
          size="sm"
          className="mt-2 h-11 border-rose-900/70 bg-transparent text-rose-200 hover:bg-rose-950/60"
          onClick={() => void catalog.refetch()}
        >
          <RefreshCw aria-hidden="true" /> Retry
        </Button>
      </Alert>
    );
  }

  const data = catalog.data;
  const recentRuns = (runs.data?.runs ?? []).slice(0, 8);
  const runCount = runs.data?.runs.length;
  const recommendationCount = recommendations.data?.recommendations.length;

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
      {/* KPI cards */}
      <section aria-label="Lab catalog statistics" className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
        <Card className="col-span-2 border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
          <div className="flex items-center gap-2 text-neutral-500">
            <Globe className="h-4 w-4" aria-hidden="true" />
            <span className="text-[11px] font-medium uppercase tracking-wider">Task world</span>
          </div>
          <p className="mt-2 text-lg font-bold leading-snug text-neutral-100">{data.world.name}</p>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-neutral-400">{data.world.description}</p>
          <p className="mt-2 font-mono text-[10px] text-neutral-600">{data.world.id}</p>
        </Card>
        <KpiCard icon={Briefcase} label="Workloads" value={data.workloads.length} sub="fixture profiles" />
        <KpiCard icon={ClipboardList} label="Task types" value={data.taskTypes.length} sub="4 families" />
        <KpiCard icon={Globe} label="Scenarios" value={data.scenarios.length} sub={`${data.world.id} world`} />
        <KpiCard icon={Boxes} label="Agent bodies" value={data.bodies.length} sub="model-independent" />
        <KpiCard icon={Cpu} label="Models" value={data.models.length} sub="occupancy slots" />
        <KpiCard icon={Wrench} label="Tools" value={data.tools.length} sub="capability allocations" />
        <KpiCard icon={PlayCircle} label="Lab runs" value={runCount} sub="persisted, newest first" />
        <KpiCard icon={Lightbulb} label="Recommendations" value={recommendationCount} sub="issued from runs" />
      </section>

      {/* Recent runs + closed-loop status */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-5">
        <section aria-label="Recent runs" className="lg:col-span-3">
          <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Recent runs</h2>
          {runs.isError ? (
            <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>Runs unavailable</AlertTitle>
              <AlertDescription className="text-rose-300/80">
                {runs.error instanceof Error ? runs.error.message : "fetch failed"}
              </AlertDescription>
            </Alert>
          ) : runs.isPending ? (
            <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
              <Skeleton className="h-28 w-full" />
            </Card>
          ) : recentRuns.length === 0 ? (
            <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
              No runs yet — open the <span className="text-neutral-200">Runs</span> tab and start an evaluation.
            </Card>
          ) : (
            <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-2 shadow-none">
              <ul
                className="max-h-72 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent"
                aria-label="Recent lab runs"
              >
                {recentRuns.map((run) => (
                  <li key={run.id}>
                    <RecentRunRow run={run} onOpenRun={onOpenRun} />
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>

        <section aria-label="Closed-loop status" className="lg:col-span-2">
          <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Closed-loop status</h2>
          <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-neutral-400">Core loop stages</span>
              <span className="rounded-full border border-amber-800/70 bg-amber-950/50 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                fixture mode
              </span>
            </div>
            <Button
              className="mt-3 h-11 w-full bg-emerald-600 text-neutral-950 hover:bg-emerald-500 focus-visible:ring-emerald-400/60 sm:w-auto"
              onClick={runDemo}
              disabled={demo.isPending}
              aria-label="Run the deterministic closed-loop demo"
            >
              {demo.isPending ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Rocket aria-hidden="true" />
              )}
              {demo.isPending ? "Running the loop…" : "Run closed-loop demo"}
            </Button>
            {/* Progress track: live count of lit stages (7 structural + 3 loop stages). */}
            <div
              className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800"
              role="progressbar"
              aria-valuenow={availableCount}
              aria-valuemin={0}
              aria-valuemax={loopStages.length}
              aria-label="Closed-loop stages lit"
            >
              <div
                className="h-full rounded-full bg-emerald-500 transition-[width] motion-reduce:transition-none"
                style={{ width: `${(availableCount / loopStages.length) * 100}%` }}
              />
            </div>
            <ol className="mt-3 grid grid-cols-3 gap-x-2 gap-y-2.5 sm:grid-cols-5 lg:grid-cols-3">
              {loopStages.map((stage, index) => (
                <li key={stage.label} className="flex items-start gap-1.5">
                  <span
                    className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${
                      stage.status === "pending" ? "bg-amber-400/70" : "bg-emerald-400"
                    }`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    <span className="block text-[10px] leading-tight text-neutral-300">{stage.label}</span>
                    <span
                      className={`block text-[9px] leading-tight ${
                        stage.status === "pending" ? "text-amber-400/80" : "text-neutral-500"
                      }`}
                    >
                      {stage.status === "pending" ? "pending" : stage.status === "live" ? "live" : "available"}
                    </span>
                    <span className="sr-only">{`stage ${index + 1} of ${loopStages.length}: ${stage.label}, ${stage.status}`}</span>
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">
              Stages 1–7 run against the deterministic org-sim fixture adapter.
              Bridge, observation and calibration are live in fixture mode —
              send a recommendation (run detail) or run the closed-loop demo to
              light the last three stages. The flauz door stays closed behind
              Agent OS (authorization, approvals, leases, browser policy).
            </p>
            {demoTrace ? <DemoTraceTimeline trace={demoTrace} onOpenRun={onOpenRun} /> : null}
          </Card>
        </section>
      </div>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: typeof Briefcase;
  label: string;
  value: number | undefined;
  sub: string;
}) {
  return (
    <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
      <div className="flex items-center gap-2 text-neutral-500">
        <Icon className="h-4 w-4" aria-hidden="true" />
        <span className="text-[11px] font-medium uppercase tracking-wider">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums text-neutral-100" aria-label={`${label}: ${value ?? "loading"}`}>
        {value === undefined ? "…" : value}
      </p>
      <p className="mt-0.5 truncate text-xs text-neutral-500">{sub}</p>
    </Card>
  );
}

function RecentRunRow({ run, onOpenRun }: { run: RunSummary; onOpenRun: (runId: string) => void }) {
  const delta = run.utilityDelta;
  return (
    <button
      type="button"
      onClick={() => onOpenRun(run.id)}
      className="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-neutral-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
      aria-label={`Open run ${run.id}: ${run.winnerName ?? run.status}`}
    >
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold text-neutral-100">
          {run.winnerName ?? <span className="text-rose-300">run failed</span>}
        </span>
        <span className="block truncate font-mono text-[10px] text-neutral-500">
          {run.id.slice(0, 8)} · {relativeTime(run.createdAt)}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        {delta === null ? null : (
          <span className={`font-mono text-xs tabular-nums ${delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {signed(delta)}
          </span>
        )}
        <RunStatusBadge status={run.status} />
        <LadderBadge level={run.ladderLevel} />
      </span>
    </button>
  );
}

/** The closed-loop demo's returned trace, rendered as a timeline. */
function DemoTraceTimeline({
  trace,
  onOpenRun,
}: {
  trace: ClosedLoopDemoTrace;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <div className="mt-4 rounded-lg border border-emerald-900/50 bg-neutral-950/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-neutral-200">Closed-loop demo trace</span>
        <span className="flex items-center gap-2">
          <span className="text-[10px] text-neutral-500">
            bridge entry {shortId(trace.bridgeEntryId)} observed
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-11 px-3 text-neutral-400 hover:bg-neutral-800/60 hover:text-emerald-300 focus-visible:ring-emerald-400/60"
            onClick={() => onOpenRun(trace.runId)}
            aria-label="Open the run created by the closed-loop demo"
          >
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            run
          </Button>
        </span>
      </div>
      <ol
        className="mt-2 max-h-72 overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent"
        aria-label="Closed-loop demo stages"
      >
        {trace.stages.map((stage, index) => (
          <li key={`${stage.stage}-${index}`} className="flex items-start gap-2 border-b border-neutral-800/60 py-2 last:border-0">
            <span className="mt-0.5 font-mono text-[10px] tabular-nums text-neutral-600">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold text-emerald-300">{stage.stage}</span>
              <span className="block text-[11px] leading-relaxed text-neutral-400">{stage.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
