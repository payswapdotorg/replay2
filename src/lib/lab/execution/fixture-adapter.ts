/**
 * Engineering Lab — fixture execution adapter (mission step: the port surface).
 *
 * This is the LabExecutionPort placeholder that keeps the execution door REAL
 * while B2 owns the organization/model math. Outcomes are deterministic draws
 * derived ONLY from the instance (difficulty, context shape, acceptance) and
 * the request seed — body/model assignments are deliberately ignored here.
 *
 * TODO(B2): replaced by the org-simulator's body/model-aware outcome model.
 */

import type { ExecutionRequest, LabExecutionPort, TaskOutcome } from "../contracts";
import { clamp01, createRng, hashSeed } from "../rng";

export class FixtureExecutionAdapter implements LabExecutionPort {
  readonly id = "fixture";
  readonly mode = "fixture" as const;

  async executeTask(req: ExecutionRequest): Promise<TaskOutcome> {
    const { instance, seed } = req;
    const rng = createRng(hashSeed(this.id, instance.id, seed));

    // Success probability decays with realized difficulty.
    const success = rng.bernoulli(clamp01(0.9 - instance.difficulty));

    // Rough deterministic draws for the outcome dimensions.
    const quality = clamp01(rng.sample(success ? 0.82 : 0.35, 0.18));
    const contextLines = instance.contextFiles.reduce((sum, f) => sum + f.lines, 0);
    const latencyMs = Math.round(
      45_000 + contextLines * 12 + instance.difficulty * 600_000 * rng.range(0.6, 1.4) + (success ? 0 : 120_000),
    );
    const costUsd = Number(
      (0.05 + instance.difficulty * 0.9 * rng.range(0.5, 1.5) + contextLines / 100_000).toFixed(4),
    );

    // Verification checks are generated from instance.acceptance (the world's
    // canonical strings) with pass tied to success.
    const verification = instance.acceptance.map((check) => ({ check, passed: success }));

    return {
      success,
      quality: Number(quality.toFixed(4)),
      latencyMs,
      costUsd,
      verification,
    };
  }
}
