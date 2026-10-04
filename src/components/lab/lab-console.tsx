"use client";

/**
 * Engineering Lab — console root (mission step 9, wave B3-a).
 *
 * Third view of the operator console (added to page.tsx alongside Replay
 * Console and Mission Control). Owns the internal sub-navigation
 * (overview / runs / bodies / recommendations), the shared "open a run
 * detail" seam used by the overview + recommendations views, and the slim
 * fixture-mode footer. TanStack Query is scoped here via QueryProvider —
 * the other two views and layout.tsx stay untouched.
 *
 * Style: dark neutral like the rest of the app, emerald as the single
 * positive/active/CTA accent, amber pending, rose negative.
 */

import { useState } from "react";
import {
  Boxes,
  FlaskConical,
  LayoutDashboard,
  Lightbulb,
  LineChart,
  Network,
  PlayCircle,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QueryProvider } from "./query-provider";
import { useLabCatalog, type ClosedLoopDemoTrace } from "./lab-api";
import { Overview } from "./overview";
import { RunsView } from "./runs-view";
import { BodiesView } from "./bodies-view";
import { RecommendationsView } from "./recommendations-view";
import { BridgeView } from "./bridge-view";
import { CalibrationView } from "./calibration-view";

export type LabTab =
  | "overview"
  | "runs"
  | "bodies"
  | "recommendations"
  | "bridge"
  | "calibration";

const TRIGGER_CLASS =
  "min-h-11 gap-1.5 border border-transparent px-3 text-neutral-400 " +
  "hover:text-neutral-200 data-[state=active]:border-emerald-500/40 " +
  "data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-300 " +
  "data-[state=active]:shadow-none";

export default function LabConsole() {
  return (
    <QueryProvider>
      <LabConsoleInner />
    </QueryProvider>
  );
}

function LabConsoleInner() {
  const [tab, setTab] = useState<LabTab>("overview");
  const [openRunId, setOpenRunId] = useState<string | null>(null);
  // The latest closed-loop demo trace lives here (never unmounts) so the
  // timeline survives internal tab switches.
  const [demoTrace, setDemoTrace] = useState<ClosedLoopDemoTrace | null>(null);
  const catalog = useLabCatalog();

  /** Cross-view seam: any view can drill into a run detail on the Runs tab. */
  const openRun = (runId: string) => {
    setOpenRunId(runId);
    setTab("runs");
  };

  const catalogVersion = catalog.data?.catalogVersion;

  return (
    <div className="flex min-h-[calc(100dvh-3.6875rem)] flex-col bg-neutral-950 text-neutral-100">
      <main className="mx-auto w-full max-w-7xl flex-1 px-3 py-4 sm:px-6 sm:py-6">
        {/* Console header */}
        <header className="mb-4 sm:mb-5">
          <div className="flex flex-wrap items-center gap-2">
            <FlaskConical className="h-5 w-5 text-emerald-400" aria-hidden="true" />
            <h1 className="text-lg font-bold tracking-tight">Engineering Lab</h1>
            <span className="rounded-full border border-amber-800/70 bg-amber-950/50 px-2 py-0.5 text-[10px] font-medium text-amber-300">
              deterministic fixture mode
            </span>
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-neutral-400">
            Evaluate agent organizations against simulated workloads — search
            bodies, occupancy and tools, compare against the single-agent
            baseline, and issue recommendations. Everything here is
            fixture-grade simulation, not runtime evidence.
          </p>
        </header>

        {/* Internal navigation. */}
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as LabTab)}
          className="gap-4"
        >
          <nav aria-label="Lab console sections">
            <TabsList className="grid h-auto w-full grid-cols-3 gap-1 rounded-lg border border-neutral-800 bg-neutral-900 p-1 sm:inline-flex sm:w-auto">
              <TabsTrigger value="overview" className={TRIGGER_CLASS}>
                <LayoutDashboard className="size-4" aria-hidden="true" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="runs" className={TRIGGER_CLASS}>
                <PlayCircle className="size-4" aria-hidden="true" />
                Runs
              </TabsTrigger>
              <TabsTrigger value="bodies" className={TRIGGER_CLASS}>
                <Boxes className="size-4" aria-hidden="true" />
                Bodies
              </TabsTrigger>
              <TabsTrigger value="recommendations" className={TRIGGER_CLASS}>
                <Lightbulb className="size-4" aria-hidden="true" />
                Recommendations
              </TabsTrigger>
              <TabsTrigger value="bridge" className={TRIGGER_CLASS}>
                <Network className="size-4" aria-hidden="true" />
                Bridge
              </TabsTrigger>
              <TabsTrigger value="calibration" className={TRIGGER_CLASS}>
                <LineChart className="size-4" aria-hidden="true" />
                Calibration
              </TabsTrigger>
            </TabsList>
          </nav>

          <TabsContent value="overview" className="mt-4">
            <Overview
              onOpenRun={openRun}
              demoTrace={demoTrace}
              onDemoTrace={setDemoTrace}
            />
          </TabsContent>
          <TabsContent value="runs" className="mt-4">
            <RunsView
              activeRunId={openRunId}
              setActiveRunId={setOpenRunId}
            />
          </TabsContent>
          <TabsContent value="bodies" className="mt-4">
            <BodiesView />
          </TabsContent>
          <TabsContent value="recommendations" className="mt-4">
            <RecommendationsView onOpenRun={openRun} />
          </TabsContent>
          <TabsContent value="bridge" className="mt-4">
            <BridgeView onOpenRun={openRun} />
          </TabsContent>
          <TabsContent value="calibration" className="mt-4">
            <CalibrationView />
          </TabsContent>
        </Tabs>
      </main>

      {/* Slim footer — sticks to the viewport bottom on short content,
          pushed down naturally when content overflows (mt-auto). */}
      <footer className="mt-auto border-t border-neutral-800 bg-neutral-950">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2.5 text-xs text-neutral-500 sm:px-6">
          <span className="inline-flex items-center gap-1.5">
            <FlaskConical className="h-3 w-3" aria-hidden="true" />
            Engineering Lab
          </span>
          <span aria-hidden="true">·</span>
          <span>deterministic fixture mode</span>
          <span aria-hidden="true">·</span>
          <span>LabExecutionPort: fixture (flauz door closed)</span>
          <span className="ml-auto font-mono">
            catalog {catalogVersion ?? "version loading…"}
          </span>
        </div>
      </footer>
    </div>
  );
}
