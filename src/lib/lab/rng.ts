/**
 * Engineering Lab — deterministic seeded RNG.
 *
 * DETERMINISM LAWS: this module (and everything under src/lib/lab/**) forbids
 * `Math.random`, `Date.now` and `new Date()`. All lab randomness flows through
 * `createRng`, and all seeds are derived via `hashSeed` so that every lab
 * artifact is reproducible byte-for-byte from its recorded seed.
 */

export interface Rng {
  /** Uniform float in [0, 1). */
  next(): number;
  /** Uniform integer in [0, maxExclusive). */
  int(maxExclusive: number): number;
  /** Uniform element of `items`. */
  pick<T>(items: readonly T[]): T;
  /** Uniform float in [min, max). */
  range(min: number, max: number): number;
  /** True with probability `p` (clamped to [0, 1]). */
  bernoulli(p: number): boolean;
  /**
   * Deterministic "clamped triangular-ish" draw around `mean`: the sum of two
   * uniforms minus one is symmetric-triangular on [-1, 1], so the result is
   * bounded in [mean - spread, mean + spread] and clamped at zero below.
   */
  sample(mean: number, spread: number): number;
}

/** mulberry32 — small, fast, well-distributed 32-bit PRNG. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next(): number {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Create a deterministic RNG stream. Same seed -> same sequence, forever.
 * Negative / non-integer seeds are normalized through `>>> 0`.
 */
export function createRng(seed: number): Rng {
  const next = mulberry32(seed);
  const rng: Rng = {
    next,
    int(maxExclusive: number): number {
      if (maxExclusive <= 0) {
        return 0;
      }
      return Math.floor(next() * maxExclusive);
    },
    pick<T>(items: readonly T[]): T {
      if (items.length === 0) {
        throw new Error("rng.pick called with an empty array");
      }
      return items[Math.floor(next() * items.length)] as T;
    },
    range(min: number, max: number): number {
      return min + next() * (max - min);
    },
    bernoulli(p: number): boolean {
      const clamped = Math.min(1, Math.max(0, p));
      return next() < clamped;
    },
    sample(mean: number, spread: number): number {
      const centered = next() + next() - 1; // triangular on [-1, 1]
      return Math.max(0, mean + spread * centered);
    },
  };
  return rng;
}

/**
 * FNV-1a-style 32-bit hash combining any number of string / number parts into
 * a seed. Part boundaries are separated with a reserved byte so that
 * `hashSeed("ab", "c") !== hashSeed("a", "bc")`. Numbers are stringified
 * (integers stringify deterministically). Returns an unsigned 32-bit integer.
 */
export function hashSeed(...parts: Array<string | number>): number {
  let h = 0x811c9dc5;
  const mix = (s: string): void => {
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
  };
  for (const part of parts) {
    mix(String(part));
    // part separator: cannot occur in the parts themselves as a lone byte
    mix("\u001f");
  }
  return h >>> 0;
}

/** Clamp to [0, 1] with round-off noise trimmed. */
export function clamp01(x: number): number {
  if (Number.isNaN(x)) {
    return 0;
  }
  return Math.min(1, Math.max(0, x));
}
