"use client";

/**
 * Engineering Lab — robustness panel (B3-a, shown for L2 runs).
 *
 * Per-dimension uncertainty rendered as low..high range bars with a mean
 * marker (the winner's nominal score from the comparison), a worst-case row,
 * the seed count and perturbation badges. All values come from the
 * RobustnessReport the run engine persisted; no synthetic numbers.
 */

import { TriangleAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { BaselineComparison, EvalDimension, RobustnessReport } from "@/lib/lab/contracts";
import { DIMENSION_LABELS, dimensionValue } from "./format";

const TRACK_FILL: Record<EvalDimension, string> = {
  success: "bg-emerald-500",
  quality: "bg-emerald-400",
  latency: "bg-amber-400",
  cost: "bg-amber-300",
};

export function RobustnessPanel({
  robustness,
  comparison,
}: {
  robustness: RobustnessReport;
  comparison: BaselineComparison[];
}) {
  // Domain per dimension: 0..max(high, nominal winner value) * 1.1 (both from
  // the API), so every bar is on an honest, data-derived scale.
  const domains = new Map<EvalDimension, number>();
  for (const u of robustness.uncertainty) {
    const nominal = comparison.find((c) => c.dimension === u.dimension)?.candidateValue ?? 0;
    domains.set(u.dimension, Math.max(u.high, nominal) * 1.1);
  }

  return (
    <section aria-label="Robustness report">
      <h3 className="mb-2 px-1 text-sm font-semibold text-neutral-300">Robustness — multi-seed + perturbations</h3>
      <Card className="border-neutral-800 bg-neutral-900/60 p-4 shadow-none sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="border-neutral-700 bg-neutral-900 text-[10px] text-neutral-300">
            {robustness.seedsEvaluated} seed{robustness.seedsEvaluated === 1 ? "" : "s"} evaluated
          </Badge>
          {robustness.perturbations.map((mode) => (
            <Badge
              key={mode}
              variant="outline"
              className="border-amber-800/70 bg-amber-950/50 text-[10px] text-amber-300"
            >
              ~{mode}
            </Badge>
          ))}
        </div>

        {/* Uncertainty ranges: low..high bar with the nominal winner marker. */}
        <ul className="mt-4 flex flex-col gap-3.5">
          {robustness.uncertainty.map((u) => {
            const domain = domains.get(u.dimension) ?? 1;
            const lowPct = Math.max(0, Math.min(100, (u.low / domain) * 100));
            const highPct = Math.max(0, Math.min(100, (u.high / domain) * 100));
            const nominal = comparison.find((c) => c.dimension === u.dimension)?.candidateValue;
            const markerPct =
              nominal === undefined ? null : Math.max(0, Math.min(100, (nominal / domain) * 100));
            return (
              <li key={u.dimension} className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="font-medium text-neutral-200">{DIMENSION_LABELS[u.dimension]}</span>
                  <span className="font-mono text-[10px] tabular-nums text-neutral-500">
                    {dimensionValue(u.dimension, u.low)} – {dimensionValue(u.dimension, u.high)}
                  </span>
                </div>
                <div
                  className="relative h-2.5 w-full rounded-full bg-neutral-800/80"
                  role="meter"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round((lowPct + highPct) / 2)}
                  aria-label={`${DIMENSION_LABELS[u.dimension]} uncertainty range from ${u.low.toFixed(4)} to ${u.high.toFixed(4)}, confidence ${(u.confidence * 100).toFixed(1)} percent`}
                >
                  <div
                    className={`absolute h-full rounded-full ${TRACK_FILL[u.dimension] ?? "bg-emerald-500"} opacity-80`}
                    style={{ left: `${lowPct}%`, width: `${Math.max(highPct - lowPct, 1)}%` }}
                  />
                  {markerPct === null ? null : (
                    <div
                      className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-neutral-100"
                      style={{ left: `calc(${markerPct}% - 2px)` }}
                      title="nominal winner score"
                      aria-hidden="true"
                    />
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="text-neutral-600">low … high (marker = nominal winner)</span>
                  <span className="text-neutral-500">
                    confidence{" "}
                    <span className="font-mono text-emerald-300">{(u.confidence * 100).toFixed(1)}%</span>
                  </span>
                </div>
              </li>
            );
          })}
        </ul>

        {/* Worst case + seed variance */}
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 border-t border-neutral-800 pt-4">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-neutral-600">Worst case</span>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              {robustness.worstCase.map((w) => (
                <li key={w.dimension} className="text-[11px] text-neutral-300">
                  {DIMENSION_LABELS[w.dimension]}{" "}
                  <span className="font-mono tabular-nums text-amber-300">{dimensionValue(w.dimension, w.value)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-neutral-600">Seed variance</span>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              {robustness.seedVariance.map((v) => (
                <li key={v.dimension} className="text-[11px] text-neutral-300">
                  {DIMENSION_LABELS[v.dimension]}{" "}
                  <span className="font-mono tabular-nums text-neutral-400">
                    {v.variance.toExponential(2)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-4 flex items-start gap-1.5 text-[11px] leading-relaxed text-neutral-500">
          <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" aria-hidden="true" />
          Uncertainty spans nominal and perturbed outcomes across seeds —
          fixture-grade simulation, not runtime evidence. B3-b adds
          calibration against observed bridges.
        </p>
      </Card>
    </section>
  );
}
