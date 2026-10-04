"use client";

/**
 * Engineering Lab — Runs subview (B3-a): the run-control surface.
 *
 * Two modes: (1) the "New run" wizard + run list table, (2) a drilled-in run
 * detail (RunDetail component) when a run is selected. Selection lives in the
 * LabConsole root so the overview + recommendations views can deep-link here.
 * Submits POST /api/lab/runs; toasts use the app-wide shadcn toaster. NO
 * optimistic UI — the detail only renders after the server confirmed.
 */

import { useMemo, useState } from "react";
import { Loader2, RefreshCw, Rocket, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useToast } from "@/hooks/use-toast";
import type { LadderLevel } from "@/lib/lab/contracts";
import {
  buildLookups,
  useCreateLabRun,
  useLabCatalog,
  useLabRuns,
} from "./lab-api";
import { relativeTime, signed } from "./format";
import { LADDER_LEVELS, LadderBadge, RunStatusBadge } from "./badges";
import { RunDetail } from "./run-detail";

export function RunsView({
  activeRunId,
  setActiveRunId,
}: {
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;
}) {
  if (activeRunId !== null) {
    return <RunDetail runId={activeRunId} onBack={() => setActiveRunId(null)} />;
  }
  return <RunBrowser setActiveRunId={setActiveRunId} />;
}

function parseSeeds(text: string): { ok: boolean; seeds: number[]; error: string | null } {
  const trimmed = text.trim();
  if (trimmed.length === 0) return { ok: true, seeds: [], error: null };
  const parts = trimmed.split(",").map((p) => p.trim()).filter((p) => p.length > 0);
  if (parts.some((p) => !/^-?\d+$/.test(p))) {
    return { ok: false, seeds: [], error: "Seeds must be comma-separated integers (e.g. 11, 22, 33)" };
  }
  const seeds = parts.map((p) => Number.parseInt(p, 10));
  if (seeds.length > 5) {
    return { ok: false, seeds: [], error: "At most 5 seeds are allowed" };
  }
  return { ok: true, seeds, error: null };
}

function RunBrowser({ setActiveRunId }: { setActiveRunId: (id: string | null) => void }) {
  const catalog = useLabCatalog();
  const runs = useLabRuns();
  const createRun = useCreateLabRun();
  const { toast } = useToast();

  // Wizard selection state. `undefined` means "untouched" — the effective
  // value then falls back to API-derived defaults (workload 0 + its dominant
  // task-mix entry + the first matching scenario). Derived state instead of
  // an initializing effect, so no cascading renders.
  const [workloadId, setWorkloadId] = useState<string | undefined>(undefined);
  const [taskTypeId, setTaskTypeId] = useState<string | undefined>(undefined);
  const [scenarioId, setScenarioId] = useState<string | undefined | null>(undefined);
  const [ladder, setLadder] = useState<LadderLevel>(1);
  const [seedsText, setSeedsText] = useState("");

  const data = catalog.data;
  const defaultWorkloadId = data?.workloads[0]?.id ?? null;
  const defaultTaskTypeId = useMemo(() => {
    if (!data) return null;
    const workload = data.workloads[0];
    const dominant = workload
      ? [...workload.taskMix].sort((a, b) => b.share - a.share)[0]?.taskTypeId
      : undefined;
    return dominant ?? data.taskTypes[0]?.id ?? null;
  }, [data]);
  const defaultScenarioId = useMemo(
    () =>
      data && defaultTaskTypeId !== null
        ? (data.scenarios.find((s) => s.taskTypeId === defaultTaskTypeId)?.id ?? null)
        : null,
    [data, defaultTaskTypeId],
  );

  const effectiveWorkloadId = workloadId ?? defaultWorkloadId;
  const effectiveTaskTypeId = taskTypeId ?? defaultTaskTypeId;
  // `null` = explicitly no scenario for the picked task type; `undefined` = untouched.
  const effectiveScenarioId = scenarioId === undefined ? defaultScenarioId : scenarioId;

  const scenariosForTaskType = useMemo(
    () => (data && effectiveTaskTypeId ? data.scenarios.filter((s) => s.taskTypeId === effectiveTaskTypeId) : []),
    [data, effectiveTaskTypeId],
  );

  const seedState = useMemo(() => parseSeeds(seedsText), [seedsText]);
  const canSubmit =
    effectiveWorkloadId !== null &&
    effectiveTaskTypeId !== null &&
    effectiveScenarioId !== null &&
    seedState.ok &&
    !createRun.isPending;

  const submit = () => {
    if (!canSubmit || effectiveWorkloadId === null || effectiveTaskTypeId === null || effectiveScenarioId === null) {
      return;
    }
    createRun.mutate(
      {
        workloadId: effectiveWorkloadId,
        taskTypeId: effectiveTaskTypeId,
        scenarioId: effectiveScenarioId,
        ladderLevel: ladder,
        ...(seedState.seeds.length > 0 ? { seeds: seedState.seeds } : {}),
      },
      {
        onSuccess: (run) => {
          toast({
            title: "Run complete",
            description:
              run.winnerName === null
                ? `Run ${run.id.slice(0, 8)} finished — check the detail view.`
                : `Winner: ${run.winnerName} · Δutility ${run.utilityDelta === null ? "—" : signed(run.utilityDelta)}`,
          });
          setActiveRunId(run.id);
        },
        onError: (error: Error) => {
          toast({ variant: "destructive", title: "Run failed", description: error.message });
        },
      },
    );
  };

  const lookups = useMemo(() => (data ? buildLookups(data) : null), [data]);

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
      {/* New run wizard */}
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
        <div className="flex items-center gap-2">
          <Rocket className="h-4 w-4 text-emerald-400" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-neutral-200">New run</h2>
        </div>
        <p className="mt-1 text-xs text-neutral-500">
          Configure an evaluation — runs complete synchronously in fixture mode
          (sub-second) and persist a full artifact.
        </p>
        {catalog.isPending ? (
          <p className="mt-4 text-sm text-neutral-500" aria-busy="true">Loading catalog…</p>
        ) : catalog.isError ? (
          <Alert className="mt-4 border-rose-900/70 bg-rose-950/40 text-rose-200">
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
        ) : data ? (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lab-workload" className="text-xs text-neutral-400">Workload</Label>
              <Select value={effectiveWorkloadId ?? ""} onValueChange={setWorkloadId}>
                <SelectTrigger id="lab-workload" className="h-11 w-full border-neutral-700 bg-neutral-900 text-neutral-200">
                  <SelectValue placeholder="Select workload" />
                </SelectTrigger>
                <SelectContent className="border-neutral-800 bg-neutral-900 text-neutral-200">
                  {data.workloads.map((w) => (
                    <SelectItem key={w.id} value={w.id} className="focus:bg-neutral-800 focus:text-neutral-100">
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-neutral-600">
                {effectiveWorkloadId ? `budget $${(lookups?.workloads.get(effectiveWorkloadId)?.budgetUsdPerTask ?? 0).toFixed(2)}/task · SLA ${lookups?.workloads.get(effectiveWorkloadId)?.latencySlaMinutes ?? "—"} min` : "fixture profile"}
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lab-tasktype" className="text-xs text-neutral-400">Task type</Label>
              <Select
                value={effectiveTaskTypeId ?? ""}
                onValueChange={(value) => {
                  setTaskTypeId(value);
                  // Reset the scenario to the first match of the new task type.
                  setScenarioId(data.scenarios.find((s) => s.taskTypeId === value)?.id ?? null);
                }}
              >
                <SelectTrigger id="lab-tasktype" className="h-11 w-full border-neutral-700 bg-neutral-900 text-neutral-200">
                  <SelectValue placeholder="Select task type" />
                </SelectTrigger>
                <SelectContent className="border-neutral-800 bg-neutral-900 text-neutral-200">
                  {data.taskTypes.map((t) => (
                    <SelectItem key={t.id} value={t.id} className="focus:bg-neutral-800 focus:text-neutral-100">
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-neutral-600">
                {effectiveTaskTypeId ? `${lookups?.taskTypes.get(effectiveTaskTypeId)?.family} family · ${lookups?.taskTypes.get(effectiveTaskTypeId)?.verificationStyle}` : "6 fixture types"}
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lab-scenario" className="text-xs text-neutral-400">Scenario</Label>
              <Select
                value={effectiveScenarioId ?? ""}
                onValueChange={setScenarioId}
                disabled={scenariosForTaskType.length === 0}
              >
                <SelectTrigger id="lab-scenario" className="h-11 w-full border-neutral-700 bg-neutral-900 text-neutral-200 disabled:opacity-50">
                  <SelectValue
                    placeholder={scenariosForTaskType.length === 0 ? "No scenario for this task type" : "Select scenario"}
                  />
                </SelectTrigger>
                <SelectContent className="border-neutral-800 bg-neutral-900 text-neutral-200">
                  {scenariosForTaskType.map((s) => (
                    <SelectItem key={s.id} value={s.id} className="focus:bg-neutral-800 focus:text-neutral-100">
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-neutral-600">
                {effectiveScenarioId ? `${lookups?.scenarios.get(effectiveScenarioId)?.instanceCount ?? "—"} instances · difficulty base ${lookups?.scenarios.get(effectiveScenarioId)?.difficultyBase ?? "—"}` : "world-generated fixtures"}
              </p>
            </div>

            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <span className="text-xs text-neutral-400" id="lab-ladder-label">Evaluation ladder</span>
              <ToggleGroup
                type="single"
                value={String(ladder)}
                onValueChange={(value) => {
                  if (value) setLadder(Number.parseInt(value, 10) as LadderLevel);
                }}
                aria-labelledby="lab-ladder-label"
                className="grid w-full grid-cols-3 gap-2"
              >
                {LADDER_LEVELS.map(({ level, title, note }) => (
                  <ToggleGroupItem
                    key={level}
                    value={String(level)}
                    aria-label={`${title}: ${note}`}
                    className="h-auto min-h-11 flex-col items-start justify-center gap-0.5 rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2.5 text-left whitespace-normal data-[state=on]:border-emerald-500/40 data-[state=on]:bg-emerald-500/10 data-[state=on]:text-emerald-300 hover:bg-neutral-800/60"
                  >
                    <span className="text-xs font-semibold">{title}</span>
                    <span className="text-[10px] font-normal leading-tight text-neutral-500">{note}</span>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lab-seeds" className="text-xs text-neutral-400">Seeds (optional)</Label>
              <Input
                id="lab-seeds"
                value={seedsText}
                onChange={(e) => setSeedsText(e.target.value)}
                placeholder="e.g. 11, 22, 33 (≤5)"
                aria-invalid={!seedState.ok}
                aria-describedby={seedState.error ? "lab-seeds-error" : undefined}
                className="h-11 border-neutral-700 bg-neutral-900 text-neutral-200 placeholder:text-neutral-600"
              />
              {seedState.error ? (
                <p id="lab-seeds-error" role="alert" className="text-[10px] text-rose-400">{seedState.error}</p>
              ) : (
                <p className="text-[10px] text-neutral-600">defaults derive deterministically when empty</p>
              )}
            </div>
          </div>
        ) : null}

        <Button
          onClick={submit}
          disabled={!canSubmit}
          className="mt-4 h-11 min-w-44 bg-emerald-600 px-5 text-neutral-50 hover:bg-emerald-500 focus-visible:ring-emerald-400/60"
        >
          {createRun.isPending ? (
            <>
              <Loader2 className="animate-spin" aria-hidden="true" /> Running evaluation…
            </>
          ) : (
            <>
              <Rocket aria-hidden="true" /> Run evaluation
            </>
          )}
        </Button>
      </Card>

      {/* Run list */}
      <section aria-label="Run history">
        <div className="mb-2 flex items-center justify-between gap-2 px-1">
          <h2 className="text-sm font-semibold text-neutral-300">Run history</h2>
          <Button
            variant="outline"
            size="sm"
            className="h-11 border-neutral-700 bg-neutral-900 text-neutral-300 hover:bg-neutral-800"
            onClick={() => void runs.refetch()}
          >
            <RefreshCw aria-hidden="true" /> Refresh
          </Button>
        </div>
        {runs.isPending ? (
          <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
            <p className="text-sm text-neutral-500" aria-busy="true">Loading runs…</p>
          </Card>
        ) : runs.isError ? (
          <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Runs unavailable</AlertTitle>
            <AlertDescription className="text-rose-300/80">
              {runs.error instanceof Error ? runs.error.message : "fetch failed"}
            </AlertDescription>
          </Alert>
        ) : runs.data.runs.length === 0 ? (
          <Card className="border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400 shadow-none">
            No runs yet — configure one above.
          </Card>
        ) : (
          <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-0 shadow-none">
            <div className="max-h-96 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent">
              <Table className="text-neutral-300">
                <TableHeader className="sticky top-0 z-10 bg-neutral-900 [&_tr]:border-neutral-800">
                  <TableRow className="hover:bg-transparent">
                    <TableHead scope="col" className="pl-4 text-neutral-400">Run</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Workload</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Task type</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Scenario</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Ladder</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Status</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Winner</TableHead>
                    <TableHead scope="col" className="text-neutral-400">Δ utility</TableHead>
                    <TableHead scope="col" className="pr-4 text-right text-neutral-400">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="[&_tr]:border-neutral-800">
                  {runs.data.runs.map((run) => {
                    const workload = lookups?.workloads.get(run.workloadId)?.name ?? run.workloadId;
                    const taskType = lookups?.taskTypes.get(run.taskTypeId)?.name ?? run.taskTypeId;
                    const scenario = lookups?.scenarios.get(run.scenarioId)?.name ?? run.scenarioId;
                    return (
                      <TableRow
                        key={run.id}
                        className="cursor-pointer hover:bg-neutral-800/50"
                        onClick={() => setActiveRunId(run.id)}
                      >
                        <TableCell className="pl-4">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-11 px-0 font-mono text-xs text-emerald-300 hover:bg-transparent hover:text-emerald-200 focus-visible:ring-emerald-400/60"
                            onClick={() => setActiveRunId(run.id)}
                            aria-label={`Open run ${run.id} (${workload}, ${taskType}, ${scenario})`}
                          >
                            {run.id.slice(0, 8)}…
                          </Button>
                        </TableCell>
                        <TableCell className="text-neutral-300">{workload}</TableCell>
                        <TableCell className="text-neutral-300">{taskType}</TableCell>
                        <TableCell className="text-neutral-400">{scenario}</TableCell>
                        <TableCell><LadderBadge level={run.ladderLevel} /></TableCell>
                        <TableCell><RunStatusBadge status={run.status} /></TableCell>
                        <TableCell className="max-w-56 truncate text-neutral-200">
                          {run.winnerName ?? <span className="text-rose-300">—</span>}
                        </TableCell>
                        <TableCell
                          className={`font-mono text-xs tabular-nums ${
                            run.utilityDelta === null ? "text-neutral-600" : run.utilityDelta >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {run.utilityDelta === null ? "—" : signed(run.utilityDelta)}
                        </TableCell>
                        <TableCell className="pr-4 text-right text-[11px] text-neutral-500">
                          {relativeTime(run.createdAt)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}
