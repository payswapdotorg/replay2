/**
 * Engineering Lab — calibration model (mission step 11, B3-b).
 *
 * Pure and deterministic: `buildCalibrationModel` folds stored
 * predicted-vs-observed pairs into a multiplicative correction model. No
 * clock, no randomness — the `updatedAt` stamp is applied by the API edge
 * (passed in as a plain string), never inside src/lib/lab.
 *
 * Factor semantics (all dimensions are observed ÷ predicted over rows with
 * predicted > 0, clamped to [0.5, 2.0], rounded to 3 decimals):
 *  - success / quality: factor > 1 means the Lab UNDER-predicted (real
 *    outcomes scored better than the fixture predicted).
 *  - latency / cost: factor is also observed ÷ predicted — consumers
 *    interpret the direction (factor < 1 means the real run was FASTER /
 *    CHEAPER than predicted).
 * With fewer than 3 observations the factors stay at 1 (the estimate is too
 * thin to trust), but the reliability curve is still computed.
 *
 * Curve: predicted-success buckets [0,0.2), [0.2,0.4), [0.4,0.6), [0.6,0.8),
 * [0.8,1] → mean predicted success and mean observed success per bucket
 * (empty buckets are skipped). This is the classic reliability diagram: if
 * the Lab is calibrated, observed ≈ predicted per bucket.
 */

import type { CalibrationBucket, CalibrationModel, EvalDimension } from "../contracts";
import { mean, roundTo } from "../sim/numeric";

/** The per-dimension scalar pair one bridge observation contributes. */
export interface CalibrationObservationPair {
  predicted: { success: number; quality: number; latencyMs: number; costUsd: number };
  observed: { success: number; quality: number; latencyMs: number; costUsd: number };
}

/** Minimum observations before factors are trusted (below: all 1.000). */
export const MIN_FACTORS_OBSERVATIONS = 3;

/** Factor clamp range — corrections beyond 2× or below 0.5× are noise. */
export const FACTOR_MIN = 0.5;
export const FACTOR_MAX = 2.0;

type CalibrationDimension = Extract<EvalDimension, "success" | "quality" | "latency" | "cost">;

const DIMENSIONS: CalibrationDimension[] = ["success", "quality", "latency", "cost"];

/** Latency/cost live under different field names than the dimension keys. */
const DIMENSION_FIELDS: Record<
  CalibrationDimension,
  "success" | "quality" | "latencyMs" | "costUsd"
> = {
  success: "success",
  quality: "quality",
  latency: "latencyMs",
  cost: "costUsd",
};

const FACTOR_DECIMALS = 3;

/** Bucket edges on predicted success: [0,.2), [.2,.4), [.4,.6), [.6,.8), [.8,1]. */
const BUCKET_EDGES = [0, 0.2, 0.4, 0.6, 0.8, 1];

const BUCKET_LABELS = ["0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1"];

function bucketIndex(predictedSuccess: number): number {
  // Clamp into [0, 1]; the last edge is inclusive.
  const clamped = Math.min(1, Math.max(0, predictedSuccess));
  for (let i = BUCKET_EDGES.length - 1; i > 0; i--) {
    if (clamped >= BUCKET_EDGES[i]) {
      return i - 1;
    }
  }
  return 0;
}

/**
 * Build the calibration model. Deterministic and pure — the same observation
 * list always yields the byte-identical model. `updatedAt` is supplied by the
 * API edge (ISO string); omitted it defaults to "" so the function itself
 * never reads a clock.
 */
export function buildCalibrationModel(
  observations: CalibrationObservationPair[],
  updatedAt = "",
): CalibrationModel {
  // --- Factors: observed ÷ predicted per dimension, mean over usable rows.
  const factors: Record<string, number> = {};
  const enoughObservations = observations.length >= MIN_FACTORS_OBSERVATIONS;
  for (const dimension of DIMENSIONS) {
    const field = DIMENSION_FIELDS[dimension];
    if (!enoughObservations) {
      factors[dimension] = 1;
      continue;
    }
    const ratios: number[] = [];
    for (const pair of observations) {
      const predicted = pair.predicted[field];
      if (predicted > 0 && Number.isFinite(predicted)) {
        const observed = pair.observed[field];
        if (Number.isFinite(observed)) {
          ratios.push(observed / predicted);
        }
      }
    }
    factors[dimension] =
      ratios.length > 0
        ? roundTo(Math.min(FACTOR_MAX, Math.max(FACTOR_MIN, mean(ratios))), FACTOR_DECIMALS)
        : 1;
  }

  // --- Reliability curve on predicted success buckets (always computed).
  const buckets: CalibrationBucket[] = [];
  const bucketPredicted: number[][] = BUCKET_LABELS.map(() => []);
  const bucketObserved: number[][] = BUCKET_LABELS.map(() => []);
  for (const pair of observations) {
    const predicted = pair.predicted.success;
    const observed = pair.observed.success;
    if (!Number.isFinite(predicted) || !Number.isFinite(observed)) {
      continue;
    }
    const index = bucketIndex(predicted);
    bucketPredicted[index].push(Math.min(1, Math.max(0, predicted)));
    bucketObserved[index].push(Math.min(1, Math.max(0, observed)));
  }
  for (let i = 0; i < BUCKET_LABELS.length; i++) {
    const count = bucketPredicted[i].length;
    if (count === 0) {
      continue; // skip empty buckets
    }
    buckets.push({
      rangeLabel: BUCKET_LABELS[i],
      predicted: roundTo(mean(bucketPredicted[i]), 4),
      observed: roundTo(mean(bucketObserved[i]), 4),
      count,
    });
  }

  return {
    factors,
    curve: buckets,
    observations: observations.length,
    updatedAt,
  };
}
