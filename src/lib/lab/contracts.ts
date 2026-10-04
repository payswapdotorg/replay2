/**
 * Engineering Lab — FROZEN CONTRACT SET (mission steps 1-3).
 *
 * This file is the inter-lane contract surface. B2 (bodies / organization /
 * model search / run engine) and B3 (console / bridge / calibration) compile
 * against these shapes. Do not rename or reshape anything here without a new
 * TL-sanctioned freeze.
 *
 * DETERMINISM LAWS (enforced across src/lib/lab/**): no `Math.random`, no
 * `Date.now` / `new Date()` inside the lab. All randomness flows through the
 * seeded RNG (src/lib/lab/rng.ts). Timestamps exist only at API persistence
 * edges (Prisma `@default(now())` is fine) and arrive here as plain strings.
 */

export type LabId = string;

// ===== workload & taxonomy =====
export interface WorkloadSignal {
  kind: string; // e.g. "repo-commits", "pr-review-volume", "incident-rate"
  label: string;
  weight: number; // 0..1 relative importance
  value: number; // 0..1 normalized intensity
}

export interface WorkloadProfile {
  id: LabId;
  name: string;
  description: string;
  signals: WorkloadSignal[];
  taskMix: { taskTypeId: LabId; share: number }[]; // shares sum to ~1
  budgetUsdPerTask: number;
  latencySlaMinutes: number;
  source: "fixture" | "learned";
}

export interface TaskTypeDescriptor {
  id: LabId;
  name: string;
  family: "implementation" | "review" | "investigation" | "maintenance";
  complexity: number; // 0..1
  contextNeeds: number; // 0..1
  verificationStyle: "tests" | "review" | "runtime-check" | "diff-inspection";
  typicalTools: string[]; // tool ids (see ToolDescriptor, B2 fills catalog)
  typicalObstacles: string[]; // obstacle kinds used by world generation
}

// ===== worlds =====
export interface TaskScenario {
  id: LabId;
  worldId: LabId;
  taskTypeId: LabId;
  name: string;
  description: string;
  difficultyBase: number; // 0..1
  instanceCount: number;
  perturbations: string[]; // perturbation mode ids
}

export interface TaskInstance {
  id: LabId;
  scenarioId: LabId;
  index: number;
  seed: number;
  brief: string;
  contextFiles: { path: string; lines: number; relevance: number }[];
  obstacles: { kind: string; severity: number }[]; // severity 0..1
  acceptance: string[];
  difficulty: number; // 0..1 realized
}

/**
 * A world engine turns a scenario + seed into concrete task instances and
 * judges outcomes against the instance's acceptance criteria. Implementations
 * MUST be pure and deterministic (same inputs -> byte-identical instances).
 */
export interface WorldEngine {
  worldId: string;
  generateInstances(scenario: TaskScenario, count: number, seed: number): TaskInstance[];
  checkAcceptance(outcome: TaskOutcome, instance: TaskInstance): boolean;
}

// ===== agent bodies & organizations (catalog content owned by B2) =====
export type BodyArchetype = "planner" | "coder" | "reviewer" | "verifier" | "researcher" | "integrator";

export interface AgentBodySpec {
  id: LabId;
  name: string;
  archetype: BodyArchetype;
  description: string;
  capabilities: Record<string, number>; // capability id -> 0..1
  contextWindowTokens: number;
  costTier: "economy" | "standard" | "premium";
  modelAgnostic: true;
  benchmark: { capabilityId: string; score: number; samples: number }[];
}

export type OrgTopology = "single" | "pipeline" | "hierarchical" | "hub-and-spoke";

export interface OrgNode {
  id: LabId;
  bodyId: LabId;
  role: string;
  reportsTo?: LabId;
}

export interface OrgEdge {
  from: LabId;
  to: LabId;
  kind: "delegation" | "review" | "handoff";
}

export interface OrganizationSpec {
  id: LabId;
  name: string;
  topology: OrgTopology;
  nodes: OrgNode[];
  edges: OrgEdge[];
  notes?: string;
}

// ===== models & capabilities (catalog content owned by B2) =====
export type ModelTier = "frontier" | "balanced" | "fast";

export interface ModelDescriptor {
  id: LabId;
  name: string;
  tier: ModelTier;
  contextTokens: number;
  costUsdPerMTok: number;
  strengths: string[]; // capability ids where it excels
  latencyMsPerKtok: number;
}

export interface ToolDescriptor {
  id: LabId;
  name: string;
  kind: "editor" | "shell" | "browser" | "search" | "linter" | "test-runner" | "vcs";
  capabilityId: string;
}

export interface ModelOccupancy {
  nodeId: LabId;
  modelId: LabId;
}
export interface CapabilityAllocation {
  nodeId: LabId;
  toolIds: string[];
}

// ===== execution port (the Lab's ONLY door to task execution) =====
export interface ExecutionRequest {
  instance: TaskInstance;
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  seed: number;
}

export interface TaskOutcome {
  success: boolean;
  quality: number; // 0..1
  latencyMs: number;
  costUsd: number;
  verification: { check: string; passed: boolean }[];
}

export interface LabExecutionPort {
  readonly id: string;
  readonly mode: "fixture" | "flauz";
  executeTask(req: ExecutionRequest): Promise<TaskOutcome>;
}
// The Lab NEVER bypasses Agent OS: a real "flauz" adapter may only be wired
// by the bridge lane behind authorization/approvals/leases/browser policy.

// ===== runs & evaluation =====
export type LadderLevel = 0 | 1 | 2;

export interface LabRunSpec {
  workloadId: LabId;
  taskTypeId: LabId;
  scenarioId: LabId;
  ladderLevel: LadderLevel;
  seeds: number[];
}

export type EvalDimension = "success" | "quality" | "latency" | "cost";
export interface EvalScore {
  dimension: EvalDimension;
  value: number;
  unit?: string;
}

export interface CandidateEvaluation {
  candidateId: LabId;
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  scores: EvalScore[];
  perInstance: { instanceId: LabId; seed: number; outcome: TaskOutcome }[];
  utility: number;
}

export interface BaselineComparison {
  dimension: EvalDimension;
  candidateValue: number;
  baselineValue: number;
  delta: number; // candidate - baseline, positive = better
}

export interface RobustnessReport {
  seedsEvaluated: number;
  perturbations: string[];
  seedVariance: { dimension: EvalDimension; variance: number }[];
  worstCase: { dimension: EvalDimension; value: number }[];
  uncertainty: { dimension: EvalDimension; low: number; high: number; confidence: number }[];
}

export interface RunArtifact {
  spec: LabRunSpec;
  search: {
    candidatesEvaluated: number;
    ladderNote: string;
    trace: { stage: string; detail: string }[];
  };
  baseline: CandidateEvaluation;
  winner: CandidateEvaluation;
  comparison: BaselineComparison[];
  robustness?: RobustnessReport; // present when ladderLevel >= 2
  utilityWeights: Record<EvalDimension, number>;
}

// ===== recommendations, bridge, calibration =====
export interface RecommendationArtifact {
  runId: LabId;
  organization: OrganizationSpec;
  occupancy: ModelOccupancy[];
  capabilities: CapabilityAllocation[];
  rationale: string;
  expectedGains: BaselineComparison[];
  confidence: number; // 0..1
  caveats: string[];
}

export type BridgeStatus = "queued" | "executing" | "observed" | "blocked";

export interface CalibrationError {
  dimension: EvalDimension;
  predicted: number;
  observed: number;
  error: number;
}
export interface CalibrationBucket {
  rangeLabel: string;
  predicted: number;
  observed: number;
  count: number;
}
export interface CalibrationModel {
  factors: Record<string, number>; // dimension -> multiplicative correction
  curve: CalibrationBucket[];
  observations: number;
  updatedAt: string;
}
