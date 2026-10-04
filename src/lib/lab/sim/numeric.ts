/**
 * Engineering Lab — deterministic numeric helpers (B2 sim/search layer).
 *
 * Pure math only (no clock, no randomness). `roundTo` is the single
 * serialization touch-point: equal computations always produce equal floats,
 * and rounding trims representation noise so artifacts serialize
 * byte-identically across processes.
 */

/** Round to `dp` decimal places; normalizes -0 to 0; non-finite maps to 0. */
export function roundTo(value: number, dp: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  const rounded = Number(value.toFixed(dp));
  return rounded === 0 ? 0 : rounded;
}

/** Arithmetic mean; 0 for an empty list. */
export function mean(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

/** Population variance (divide by n); 0 for fewer than two values. */
export function populationVariance(values: number[]): number {
  if (values.length <= 1) {
    return 0;
  }
  const m = mean(values);
  return values.reduce((sum, v) => sum + (v - m) ** 2, 0) / values.length;
}

/** Signed one-line delta, e.g. "+0.192" / "-0.041". */
export function formatSigned(value: number, dp = 3): string {
  const rounded = roundTo(value, dp);
  return `${rounded >= 0 ? "+" : ""}${rounded.toFixed(dp)}`;
}
