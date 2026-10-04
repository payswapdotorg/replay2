/**
 * Engineering Lab — execution port factory (mission step 10).
 *
 * The single place that decides which LabExecutionPort backs a request.
 * "fixture" resolves to the deterministic OrgSimulator (the live, sanctioned
 * simulation path); "flauz" resolves to the closed-door adapter that refuses
 * to execute until the Agent OS lane is wired. Callers decide the mode — the
 * bridge route uses fixture and records the portMode on every entry so the
 * fixture/flauz distinction is always auditable in the database.
 */

import type { LabExecutionPort } from "../contracts";
import { OrgSimulator } from "../sim/org-simulator";
import { FlauzExecutionAdapter } from "./flauz-adapter";

export function getExecutionPort(mode: "fixture" | "flauz"): LabExecutionPort {
  return mode === "fixture" ? new OrgSimulator() : new FlauzExecutionAdapter();
}
