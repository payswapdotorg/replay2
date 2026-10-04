"use client";

/**
 * Engineering Lab — pure display formatting helpers (B3-a).
 *
 * UI-only: timestamp formatting via date-fns is explicitly allowed (the
 * determinism laws govern src/lib/lab, not presentation). Every function here
 * is pure — no clock reads, no randomness.
 */

import { format, formatDistanceToNowStrict } from "date-fns";
import type { EvalDimension } from "@/lib/lab/contracts";

export const DIMENSION_LABELS: Record<EvalDimension, string> = {
  success: "Success",
  quality: "Quality",
  latency: "Latency",
  cost: "Cost",
};

/** Signed number with 2-3 decimals, e.g. "+0.123" / "-0.05". */
export function signed(value: number, decimals = 3): string {
  const fixed = value.toFixed(decimals);
  return value >= 0 ? `+${fixed}` : fixed;
}

/** 0-1 fraction as one-decimal percent, e.g. 0.333 -> "33.3%". */
export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Percentage-point delta for 0-1 dimensions, e.g. 0.25 -> "+25.0 pp". */
export function percentPoints(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
}

/** Milliseconds as seconds, e.g. 9239 -> "9.24 s". */
export function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(2)} s`;
}

/** USD with 4 decimals, e.g. 0.025665 -> "$0.0257". */
export function usd(value: number): string {
  return `$${value.toFixed(4)}`;
}

/** Eval dimension value with its unit (latency in s, cost in $, 0-1 as %). */
export function dimensionValue(dimension: EvalDimension, value: number): string {
  switch (dimension) {
    case "success":
    case "quality":
      return percent(value);
    case "latency":
      return seconds(value);
    case "cost":
      return usd(value);
  }
}

/** Deltas are positive-better per contract; format each dimension's delta. */
export function dimensionDelta(dimension: EvalDimension, delta: number): string {
  switch (dimension) {
    case "success":
    case "quality":
      return percentPoints(delta);
    case "latency":
      return `${delta >= 0 ? "+" : ""}${seconds(delta)}`;
    case "cost":
      return `${delta >= 0 ? "+" : ""}${usd(delta)}`;
  }
}

/** Token count as compact form, e.g. 128000 -> "128k". */
export function tokens(value: number): string {
  return value >= 1000 ? `${Math.round(value / 1000)}k` : `${value}`;
}

/** Relative time for list rows ("2 minutes ago"). */
export function relativeTime(iso: string): string {
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

/** Absolute timestamp for headers ("2026-10-01 06:24"). */
export function absoluteTime(iso: string): string {
  return format(new Date(iso), "yyyy-MM-dd HH:mm");
}

/** Cuid-style id shortened for table rows. */
export function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** Truncate long names for SVG node cards. */
export function truncate(text: string, max = 24): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
