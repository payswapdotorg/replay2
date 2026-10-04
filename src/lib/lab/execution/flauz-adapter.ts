/**
 * Engineering Lab — the flauz execution adapter (mission step 10's door).
 *
 * THE DOOR EXISTS BUT IS EXPLICITLY CLOSED. The Lab's port surface is honest:
 * a real Flauz execution adapter would hand the winning organization to the
 * live Agent OS stack (authorization, approvals, leases, browser policy,
 * environment trust) and bring back a TaskOutcome observed from a real run.
 * None of that is wired in this deployment, so `executeTask` refuses with a
 * typed LabError instead of simulating success — the Lab never bypasses
 * Agent OS, and bridge entries stay fixture-mode until that lane exists.
 */

import { LabError } from "../errors";
import type { ExecutionRequest, LabExecutionPort, TaskOutcome } from "../contracts";

export const FLAUZ_REFUSAL_MESSAGE =
  "Flauz execution is not wired in this deployment: the Lab never bypasses Agent OS (authorization, approvals, leases, browser policy, environment trust). Bridge entries stay fixture-mode until the Agent OS lane is connected.";

export class FlauzExecutionAdapter implements LabExecutionPort {
  readonly id = "flauz-bridge";
  readonly mode = "flauz" as const;

  async executeTask(_req: ExecutionRequest): Promise<TaskOutcome> {
    // Deliberately never resolves — the closed door throws instead of faking
    // a real execution. Callers route this to HTTP 400 (LabError).
    throw new LabError(FLAUZ_REFUSAL_MESSAGE);
  }
}
