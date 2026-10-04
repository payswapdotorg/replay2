/**
 * Engineering Lab catalog — models & tools (mission steps 5-6, B2-owned).
 *
 * ModelDescriptor = occupiable model slots. An organization's occupancy maps
 * nodes to model ids; the org simulator turns tier/strengths/latency/cost
 * into the multiplier, latency and cost terms of the outcome model. The
 * occupancy search of this wave upgrades nodes to frontier models and tries
 * fast-a swaps; balanced-b is a catalog-resident alternative that later
 * search policies may reach.
 *
 * ToolDescriptor = capability-bearing tools the Lab allocates to organization
 * nodes (CapabilityAllocation). Determinism laws apply: pure data.
 */

import type { ModelDescriptor, ToolDescriptor } from "../contracts";

export const modelDescriptors: ModelDescriptor[] = [
  {
    id: "model.frontier-a",
    name: "Frontier A",
    tier: "frontier",
    contextTokens: 200_000,
    costUsdPerMTok: 12,
    strengths: ["cap.code", "cap.plan", "cap.context"],
    latencyMsPerKtok: 2400,
  },
  {
    id: "model.frontier-b",
    name: "Frontier B",
    tier: "frontier",
    contextTokens: 200_000,
    costUsdPerMTok: 9,
    strengths: ["cap.review", "cap.integrate", "cap.verify"],
    latencyMsPerKtok: 2000,
  },
  {
    id: "model.balanced-a",
    name: "Balanced A",
    tier: "balanced",
    contextTokens: 128_000,
    costUsdPerMTok: 2.5,
    strengths: ["cap.code", "cap.verify"],
    latencyMsPerKtok: 900,
  },
  {
    id: "model.balanced-b",
    name: "Balanced B",
    tier: "balanced",
    contextTokens: 128_000,
    costUsdPerMTok: 1.8,
    strengths: ["cap.search", "cap.context"],
    latencyMsPerKtok: 800,
  },
  {
    id: "model.fast-a",
    name: "Fast A",
    tier: "fast",
    contextTokens: 128_000,
    costUsdPerMTok: 0.4,
    strengths: ["cap.search"],
    latencyMsPerKtok: 350,
  },
];

export const toolDescriptors: ToolDescriptor[] = [
  {
    id: "tool.editor",
    name: "Code editor",
    kind: "editor",
    capabilityId: "cap.code",
  },
  {
    id: "tool.shell",
    name: "Sandboxed shell",
    kind: "shell",
    capabilityId: "cap.verify",
  },
  {
    id: "tool.browser",
    name: "Headless browser",
    kind: "browser",
    capabilityId: "cap.search",
  },
  {
    id: "tool.search",
    name: "Repository search",
    kind: "search",
    capabilityId: "cap.search",
  },
  {
    id: "tool.linter",
    name: "Linter",
    kind: "linter",
    capabilityId: "cap.review",
  },
  {
    id: "tool.test-runner",
    name: "Test runner",
    kind: "test-runner",
    capabilityId: "cap.verify",
  },
  {
    id: "tool.vcs",
    name: "Version control",
    kind: "vcs",
    capabilityId: "cap.integrate",
  },
];

/** Look up a model by id (deterministic; undefined when unknown). */
export function findModel(id: string): ModelDescriptor | undefined {
  return modelDescriptors.find((m) => m.id === id);
}

/** Look up a tool by id (deterministic; undefined when unknown). */
export function findTool(id: string): ToolDescriptor | undefined {
  return toolDescriptors.find((t) => t.id === id);
}
