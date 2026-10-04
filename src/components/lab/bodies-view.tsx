"use client";

/**
 * Engineering Lab — Bodies subview (B3-a).
 *
 * The model-independent Agent Body library (capability bars labeled via the
 * catalog's capabilityLabels), plus the occupiable models table and tool
 * catalog. Everything comes from GET /api/lab/catalog; long grids scroll in
 * bounded containers with subtle scrollbars.
 */

import {
  Boxes,
  ChevronRight,
  RefreshCw,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { capabilityLabels } from "@/lib/lab/catalog/agent-bodies";
import type { AgentBodySpec } from "@/lib/lab/contracts";
import { useLabCatalog } from "./lab-api";
import { tokens } from "./format";
import { CostTierBadge, ModelTierBadge } from "./badges";

const SCROLLBAR =
  "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:bg-neutral-700 [&::-webkit-scrollbar-track]:bg-transparent";

export function BodiesView() {
  const catalog = useLabCatalog();

  if (catalog.isPending) {
    return (
      <div className="flex flex-col gap-4 sm:gap-6" aria-busy="true" aria-label="Loading body library">
        <Skeleton className="h-8 w-48 rounded-md" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-72 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (catalog.isError || !catalog.data) {
    return (
      <Alert className="border-rose-900/70 bg-rose-950/40 text-rose-200">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Body library unavailable</AlertTitle>
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

  const { bodies, models, tools } = catalog.data;

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
      <section aria-label="Agent body library">
        <div className="mb-2 flex items-center gap-2 px-1">
          <Boxes className="h-4 w-4 text-neutral-500" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-neutral-300">Agent bodies</h2>
          <span className="text-[11px] text-neutral-600">
            model-independent capability bundles — {bodies.length} in catalog
          </span>
        </div>
        <div className={`max-h-[44rem] overflow-y-auto pr-1 ${SCROLLBAR}`}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {bodies.map((body) => (
              <BodyCard key={body.id} body={body} />
            ))}
          </div>
        </div>
      </section>

      <section aria-label="Models and tools">
        <h2 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Models & tools</h2>
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card className="gap-0 border-neutral-800 bg-neutral-900/60 p-0 shadow-none">
              <div className="overflow-x-auto">
                <Table className="text-neutral-300">
                  <TableHeader className="[&_tr]:border-neutral-800">
                    <TableRow className="hover:bg-transparent">
                      <TableHead scope="col" className="pl-4 text-neutral-400">Model</TableHead>
                      <TableHead scope="col" className="text-neutral-400">Tier</TableHead>
                      <TableHead scope="col" className="text-neutral-400">Context</TableHead>
                      <TableHead scope="col" className="text-neutral-400">$ / MTok</TableHead>
                      <TableHead scope="col" className="text-neutral-400">Latency</TableHead>
                      <TableHead scope="col" className="pr-4 text-neutral-400">Strengths</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className="[&_tr]:border-neutral-800">
                    {models.map((model) => (
                      <TableRow key={model.id} className="hover:bg-neutral-800/40">
                        <TableCell className="pl-4 text-neutral-200">{model.name}</TableCell>
                        <TableCell><ModelTierBadge tier={model.tier} /></TableCell>
                        <TableCell className="font-mono text-xs text-neutral-400">{tokens(model.contextTokens)}</TableCell>
                        <TableCell className="font-mono text-xs text-neutral-400">${model.costUsdPerMTok.toFixed(2)}</TableCell>
                        <TableCell className="font-mono text-xs text-neutral-400">{model.latencyMsPerKtok} ms/ktok</TableCell>
                        <TableCell className="pr-4 text-[11px] text-neutral-400">
                          {model.strengths.map((s) => capabilityLabels[s] ?? s).join(", ")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Card>
          </div>
          <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
            <div className="flex items-center gap-2">
              <Wrench className="h-4 w-4 text-neutral-500" aria-hidden="true" />
              <h3 className="text-sm font-semibold text-neutral-200">Tools</h3>
              <span className="text-[11px] text-neutral-600">{tools.length} in catalog</span>
            </div>
            <ul className="mt-3 flex flex-wrap gap-2">
              {tools.map((tool) => (
                <li key={tool.id}>
                  <Badge
                    variant="outline"
                    className="border-neutral-700 bg-neutral-900 text-[11px] text-neutral-300"
                    title={tool.id}
                  >
                    {tool.name}
                    <span className="ml-1 text-[9px] text-neutral-600">
                      {capabilityLabels[tool.capabilityId] ?? tool.capabilityId}
                    </span>
                  </Badge>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">
              Tools are capability-bearing allocations the occupancy search
              assigns to organization nodes.
            </p>
          </Card>
        </div>
      </section>
    </div>
  );
}

function BodyCard({ body }: { body: AgentBodySpec }) {
  const capabilities = Object.entries(body.capabilities)
    .map(([id, value]) => ({ id, label: capabilityLabels[id] ?? id, value }))
    .sort((a, b) => b.value - a.value);

  return (
    <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-neutral-100">{body.name}</h3>
        <Badge variant="outline" className="border-neutral-700 bg-neutral-900 text-[10px] capitalize text-neutral-300">
          {body.archetype}
        </Badge>
        <CostTierBadge tier={body.costTier} />
        <span className="ml-auto font-mono text-[10px] text-neutral-600">{tokens(body.contextWindowTokens)} ctx</span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-neutral-400">{body.description}</p>

      <div className="mt-3 flex flex-col gap-1.5">
        <span className="text-[10px] uppercase tracking-wider text-neutral-600">Capabilities</span>
        <ul className="flex flex-col gap-1.5">
          {capabilities.map((cap) => (
            <li key={cap.id} className="flex items-center gap-2">
              <span className="w-32 shrink-0 truncate text-[10px] text-neutral-400" title={cap.label}>
                {cap.label}
              </span>
              <div
                className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-800"
                role="meter"
                aria-valuenow={Math.round(cap.value * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${cap.label} capability ${cap.value.toFixed(2)} of 1`}
              >
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${cap.value * 100}%` }} />
              </div>
              <span className="w-7 shrink-0 text-right font-mono text-[9px] tabular-nums text-neutral-500">
                {cap.value.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-3">
        <Collapsible>
          <CollapsibleTrigger className="group flex min-h-11 w-full items-center gap-1.5 rounded-md px-1 text-[11px] text-neutral-400 transition-colors hover:bg-neutral-800/60 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60">
            <ChevronRight
              className="h-3.5 w-3.5 transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
              aria-hidden="true"
            />
            Benchmarks ({body.benchmark.length})
          </CollapsibleTrigger>
          <CollapsibleContent>
            <Table className="mt-1 text-neutral-300">
              <TableHeader>
                <TableRow className="hover:bg-transparent [&]:border-neutral-800">
                  <TableHead scope="col" className="h-8 px-1 text-[10px] text-neutral-500">Capability</TableHead>
                  <TableHead scope="col" className="h-8 px-1 text-[10px] text-neutral-500">Score</TableHead>
                  <TableHead scope="col" className="h-8 px-1 text-right text-[10px] text-neutral-500">Samples</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {body.benchmark.map((entry) => (
                  <TableRow key={entry.capabilityId} className="hover:bg-neutral-800/40 [&]:border-neutral-800/60">
                    <TableCell className="px-1 py-1.5 text-[11px] text-neutral-300">
                      {capabilityLabels[entry.capabilityId] ?? entry.capabilityId}
                    </TableCell>
                    <TableCell className="px-1 py-1.5 font-mono text-[11px] tabular-nums text-neutral-200">
                      {entry.score.toFixed(2)}
                    </TableCell>
                    <TableCell className="px-1 py-1.5 text-right font-mono text-[11px] tabular-nums text-neutral-500">
                      {entry.samples}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </Card>
  );
}
