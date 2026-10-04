"use client";

/**
 * Engineering Lab — shared badge atoms (B3-a).
 * Color laws: emerald = positive/active, amber = pending/warning,
 * rose = negative/error, neutrals for everything else. No indigo, no blue.
 */

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { EvalDimension, LadderLevel, ModelTier } from "@/lib/lab/contracts";
import { dimensionDelta } from "./format";

const LADDER_LABELS: Record<number, string> = {
  0: "L0 · analytic",
  1: "L1 · scenario",
  2: "L2 · robustness",
};

export function LadderBadge({ level }: { level: number }) {
  const label = LADDER_LABELS[level] ?? `L${level}`;
  const accent =
    level === 2
      ? "border-emerald-800/70 bg-emerald-950/60 text-emerald-300"
      : "border-neutral-700 bg-neutral-900 text-neutral-300";
  return (
    <Badge variant="outline" className={cn("font-mono text-[10px]", accent)}>
      {label}
    </Badge>
  );
}

export function RunStatusBadge({ status }: { status: string }) {
  const accent =
    status === "complete"
      ? "border-emerald-800/70 bg-emerald-950/60 text-emerald-300"
      : status === "failed"
        ? "border-rose-900/70 bg-rose-950/60 text-rose-300"
        : "border-amber-800/70 bg-amber-950/60 text-amber-300";
  return (
    <Badge variant="outline" className={cn("text-[10px] capitalize", accent)}>
      {status}
    </Badge>
  );
}

/** Delta chip — contract orientation: positive is always better. */
export function DeltaBadge({
  dimension,
  delta,
  compact = false,
}: {
  dimension: EvalDimension;
  delta: number;
  compact?: boolean;
}) {
  const positive = delta >= 0;
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono tabular-nums",
        compact ? "text-[10px]" : "text-[11px]",
        positive
          ? "border-emerald-800/70 bg-emerald-950/60 text-emerald-300"
          : "border-rose-900/70 bg-rose-950/60 text-rose-300",
      )}
      aria-label={`${dimension} delta ${positive ? "improvement" : "regression"} ${dimensionDelta(dimension, delta)}`}
    >
      {dimensionDelta(dimension, delta)}
    </Badge>
  );
}

const TIER_ACCENTS: Record<ModelTier, string> = {
  frontier: "border-amber-800/70 bg-amber-950/60 text-amber-300",
  balanced: "border-neutral-700 bg-neutral-900 text-neutral-300",
  fast: "border-emerald-800/70 bg-emerald-950/60 text-emerald-300",
};

export function ModelTierBadge({ tier }: { tier: ModelTier }) {
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] capitalize", TIER_ACCENTS[tier])}
    >
      {tier}
    </Badge>
  );
}

const COST_TIERS: Record<string, string> = {
  economy: "border-emerald-800/70 bg-emerald-950/60 text-emerald-300",
  standard: "border-neutral-700 bg-neutral-900 text-neutral-300",
  premium: "border-amber-800/70 bg-amber-950/60 text-amber-300",
};

export function CostTierBadge({ tier }: { tier: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] capitalize", COST_TIERS[tier] ?? COST_TIERS.standard)}
    >
      {tier}
    </Badge>
  );
}

export function TopologyBadge({ topology }: { topology: string }) {
  return (
    <Badge
      variant="outline"
      className="border-neutral-700 bg-neutral-900 text-[10px] text-neutral-300"
    >
      {topology}
    </Badge>
  );
}

/** Ladder option descriptor shared by the wizard and KPI copy. */
export const LADDER_LEVELS: { level: LadderLevel; title: string; note: string }[] = [
  { level: 0, title: "L0", note: "Analytic — closed-form, fastest" },
  { level: 1, title: "L1", note: "Scenario sim — instance-level" },
  { level: 2, title: "L2", note: "Robustness — multi-seed + perturbations" },
];

export function LadderHint({ level }: { level: LadderLevel }) {
  const entry = LADDER_LEVELS.find((l) => l.level === level);
  return (
    <span className="text-neutral-400">{entry?.note ?? `L${level}`}</span>
  );
}
