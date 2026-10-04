/**
 * Engineering Lab — typed error for request-level failures.
 *
 * Lab code throws `LabError` when a request names an unknown catalog id or an
 * internally inconsistent spec (e.g. a scenario that belongs to a different
 * task type). API routes map LabError to HTTP 400 with the message; anything
 * else is a genuine engine fault and surfaces as HTTP 500.
 */
export class LabError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LabError";
  }
}
