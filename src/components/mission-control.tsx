"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  CircleDot,
  Clock,
  Database,
  GitBranch,
  GitMerge,
  Globe,
  Layers,
  MonitorPlay,
  Radar,
  Rocket,
  Server,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { ItemStatus, MissionState } from "@/lib/mission";

const STATUS_STYLES: Record<
  ItemStatus,
  { label: string; className: string; dot: string }
> = {
  pending: {
    label: "Pending",
    className: "bg-zinc-800/80 text-zinc-300 border-zinc-700",
    dot: "bg-zinc-500",
  },
  dispatched: {
    label: "Dispatched",
    className: "bg-amber-950/70 text-amber-300 border-amber-800/70",
    dot: "bg-amber-400 animate-pulse",
  },
  staged: {
    label: "Staged",
    className: "bg-teal-950/70 text-teal-300 border-teal-800/70",
    dot: "bg-teal-400 animate-pulse",
  },
  "in-review": {
    label: "In Review",
    className: "bg-orange-950/70 text-orange-300 border-orange-800/70",
    dot: "bg-orange-400 animate-pulse",
  },
  "changes-requested": {
    label: "Changes Requested",
    className: "bg-rose-950/70 text-rose-300 border-rose-800/70",
    dot: "bg-rose-400",
  },
  merged: {
    label: "Merged",
    className: "bg-emerald-950/70 text-emerald-300 border-emerald-800/70",
    dot: "bg-emerald-400",
  },
  "merged-local": {
    label: "Merged (push pending)",
    className: "bg-emerald-950/70 text-emerald-300 border-emerald-800/70",
    dot: "bg-emerald-400 animate-pulse",
  },
  done: {
    label: "Done",
    className: "bg-emerald-950/70 text-emerald-300 border-emerald-800/70",
    dot: "bg-emerald-400",
  },
  blocked: {
    label: "Blocked",
    className: "bg-red-950/80 text-red-300 border-red-800/70",
    dot: "bg-red-500 animate-pulse",
  },
};

const INFRA_STYLES: Record<string, { className: string; dot: string }> = {
  ok: { className: "text-emerald-300", dot: "bg-emerald-400" },
  degraded: { className: "text-amber-300", dot: "bg-amber-400" },
  pending: { className: "text-zinc-400", dot: "bg-zinc-500" },
  down: { className: "text-red-300", dot: "bg-red-400" },
};

const TIMELINE_KIND: Record<string, string> = {
  info: "text-zinc-300",
  warn: "text-amber-300",
  error: "text-red-300",
  success: "text-emerald-300",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function MissionControl() {
  const [state, setState] = useState<MissionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/mission", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState((await res.json()) as MissionState);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const poll = setInterval(() => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void refresh();
      }
    }, 5000);
    const clock = setInterval(() => setTick((t) => t + 1), 30000);
    return () => {
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [refresh]);

  if (!state) {
    return (
      <div className="flex flex-1 items-center justify-center bg-neutral-950 text-zinc-200">
        <div className="flex flex-col items-center gap-3">
          <Radar className="h-8 w-8 text-rose-500 animate-spin" aria-hidden />
          <p className="text-sm text-zinc-400">
            {error ? `Mission state unavailable: ${error}` : "Establishing mission uplink…"}
          </p>
        </div>
      </div>
    );
  }

  const doneCount = state.items.filter(
    (i) => i.status === "done" || i.status === "merged"
  ).length;
  const activeCount = state.items.filter(
    (i) => i.status === "dispatched" || i.status === "in-review"
  ).length;
  const lanesById = new Map(state.lanes.map((l) => [l.id, l]));

  return (
    <div className="flex flex-1 flex-col bg-neutral-950 text-zinc-100" data-tick={tick}>
      {/* Header */}
      <header className="border-b border-zinc-800/80 bg-neutral-950/95 backdrop-blur supports-[backdrop-filter]:bg-neutral-950/75">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-4">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <MonitorPlay className="h-7 w-7 text-rose-500 shrink-0" aria-hidden />
            <div className="min-w-0">
              <h1 className="text-lg font-bold tracking-tight">
                {(() => {
                  const t = state.mission.title || "Mission Control";
                  const sp = t.indexOf(" ");
                  const head = sp > 0 ? t.slice(0, sp) : t;
                  const tail = sp > 0 ? t.slice(sp) : "";
                  return (
                    <>
                      <span className="text-rose-500 font-black">{head}</span>
                      <span className="text-zinc-200">{tail}</span>
                    </>
                  );
                })()}
              </h1>
              <p className="text-xs text-zinc-500 truncate">{state.mission.subtitle}</p>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {state.production.url ? (
                <a
                  href={state.production.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-emerald-800/70 bg-emerald-950/60 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-900/60 transition-colors"
                >
                  <Globe className="h-3.5 w-3.5" aria-hidden />
                  {state.production.url.replace(/^https?:\/\//, "")}
                </a>
              ) : (
                <Badge
                  variant="outline"
                  className="border-zinc-700 bg-zinc-900/60 text-zinc-400"
                >
                  <Globe className="mr-1 h-3 w-3" aria-hidden />
                  not deployed yet
                </Badge>
              )}
              <Badge
                variant="outline"
                className="border-zinc-700 bg-zinc-900/60 text-zinc-300 font-mono"
              >
                main @ {state.mission.baseline.main.slice(0, 7)}
              </Badge>
              <Badge
                variant="outline"
                className="border-zinc-700 bg-zinc-900/60 text-zinc-300"
              >
                <ShieldCheck className="mr-1 h-3 w-3 text-emerald-400" aria-hidden />
                {state.mission.baseline.tests} tests green
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-6 space-y-6">
        {/* Stats strip */}
        <section aria-label="Track statistics" className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            {
              icon: Layers,
              label: "Track progress",
              value: `${doneCount}/${state.items.length}`,
              sub: "work items merged or done",
            },
            {
              icon: Activity,
              label: "In flight",
              value: `${activeCount}`,
              sub: "dispatched or in review",
            },
            {
              icon: GitMerge,
              label: "Architecture baseline",
              value: "001–043",
              sub: "complete · frozen contracts",
            },
            {
              icon: UserCheck,
              label: "Worker lanes",
              value: "3",
              sub: state.mission.cadence,
            },
          ].map((stat) => (
            <Card
              key={stat.label}
              className="border-zinc-800 bg-zinc-900/40 p-4 shadow-none"
            >
              <div className="flex items-center gap-2 text-zinc-500">
                <stat.icon className="h-4 w-4" aria-hidden />
                <span className="text-[11px] font-medium uppercase tracking-wider">
                  {stat.label}
                </span>
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-zinc-100">
                {stat.value}
              </p>
              <p className="mt-0.5 text-xs text-zinc-500 truncate">{stat.sub}</p>
            </Card>
          ))}
        </section>

        {/* Lane board */}
        <section aria-label="Worker lanes">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {state.lanes.map((lane, laneIdx) => (
              <div key={lane.id} className="flex flex-col gap-3">
                <div className="flex items-center gap-2 px-1">
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-rose-950/60 text-[11px] font-bold text-rose-400 border border-rose-900/60">
                    {lane.id}
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-zinc-200 truncate">
                      {lane.name}
                    </h2>
                    <p className="text-[11px] text-zinc-600 truncate">{lane.scope}</p>
                  </div>
                </div>
                <div className="flex flex-col gap-2.5">
                  {lane.items.map((itemId, itemIdx) => {
                    const item = state.items.find((i) => i.id === itemId);
                    if (!item) return null;
                    const st = STATUS_STYLES[item.status] ?? STATUS_STYLES.pending;
                    return (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          duration: 0.25,
                          delay: (laneIdx * 4 + itemIdx) * 0.04,
                        }}
                      >
                        <Card className="border-zinc-800 bg-zinc-900/40 p-3.5 shadow-none hover:border-zinc-700 transition-colors">
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-mono text-[11px] font-semibold text-rose-400/90">
                              {item.id}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium ${st.className}`}
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} aria-hidden />
                              {st.label}
                            </span>
                          </div>
                          <h3 className="mt-1.5 text-[13px] font-semibold leading-snug text-zinc-100">
                            {item.title}
                          </h3>
                          {item.notes && (
                            <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">
                              {item.notes}
                            </p>
                          )}
                          {item.branch && (
                            <p className="mt-2 inline-flex max-w-full items-center gap-1 rounded bg-zinc-800/70 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 truncate">
                              <GitBranch className="h-3 w-3 shrink-0" aria-hidden />
                              {item.branch}
                            </p>
                          )}
                          {item.updatedAt && (
                            <p className="mt-1.5 text-[10px] text-zinc-600">
                              updated {timeAgo(item.updatedAt)}
                            </p>
                          )}
                        </Card>
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Infrastructure + Timeline */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Infrastructure */}
          <section aria-label="Infrastructure status" className="lg:col-span-2">
            <h2 className="mb-3 flex items-center gap-2 px-1 text-sm font-semibold text-zinc-300">
              <Server className="h-4 w-4 text-zinc-500" aria-hidden />
              Free-tier infrastructure
            </h2>
            <Card className="border-zinc-800 bg-zinc-900/40 shadow-none divide-y divide-zinc-800/70">
              {state.infra.map((entry) => {
                const st = INFRA_STYLES[entry.status] ?? INFRA_STYLES.pending;
                return (
                  <div key={entry.id} className="flex items-start gap-3 p-3.5">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${st.dot}`} aria-hidden />
                    <div className="min-w-0">
                      <p className={`text-[13px] font-semibold ${st.className}`}>{entry.label}</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-500">
                        {entry.detail}
                      </p>
                    </div>
                  </div>
                );
              })}
            </Card>
          </section>

          {/* Timeline */}
          <section aria-label="Mission timeline" className="lg:col-span-3">
            <h2 className="mb-3 flex items-center gap-2 px-1 text-sm font-semibold text-zinc-300">
              <Clock className="h-4 w-4 text-zinc-500" aria-hidden />
              Mission timeline
            </h2>
            <Card className="border-zinc-800 bg-zinc-900/40 shadow-none p-0 overflow-hidden">
              <div className="max-h-80 overflow-y-auto mission-scroll p-3.5 space-y-3">
                {state.timeline.map((entry, idx) => (
                  <div key={`${entry.ts}-${idx}`} className="flex items-start gap-3">
                    <CircleDot
                      className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                        entry.kind === "success"
                          ? "text-emerald-400"
                          : entry.kind === "warn"
                            ? "text-amber-400"
                            : entry.kind === "error"
                              ? "text-red-400"
                              : "text-zinc-600"
                      }`}
                      aria-hidden
                    />
                    <div className="min-w-0">
                      <p className={`text-xs leading-relaxed ${TIMELINE_KIND[entry.kind] ?? "text-zinc-300"}`}>
                        {entry.text}
                      </p>
                      <p className="mt-0.5 text-[10px] text-zinc-600 font-mono">
                        {entry.ts.replace("T", " ").replace("Z", " UTC")}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        </div>

        <Separator className="bg-zinc-800/60" />
      </main>

      {/* Sticky footer */}
      <footer className="mt-auto border-t border-zinc-800/80 bg-neutral-950/95 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-zinc-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-500 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
            </span>
            <span className="text-zinc-400 font-medium">Lead resident</span>
          </span>
          <span>· monitor → review → merge loop active</span>
          <span>· remote repo is the single source of truth</span>
          <span className="ml-auto inline-flex items-center gap-1.5 font-mono">
            <Database className="h-3 w-3" aria-hidden />
            state synced {timeAgo(state.updatedAt)} · auto-refresh 5s
          </span>
        </div>
      </footer>
    </div>
  );
}
