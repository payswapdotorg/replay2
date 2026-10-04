/**
 * Engineering Lab catalog — aggregator (mission steps 1-3 surface).
 *
 * Pure synchronous aggregation over the fixture modules. B2 fills the bodies/
 * models/ tools slots by appending to their catalog modules; consumers (the
 * /api/lab/catalog route, B3's console views, B2's run engine) all read this
 * single typed snapshot. `catalogVersion` guards the freeze: consumers may
 * assert on it when shapes evolve.
 */

import { agentBodies } from "./agent-bodies";
import { modelDescriptors, toolDescriptors } from "./models";
import { seWorld, seWorldScenarios } from "./se-world";
import { taskTypes } from "./task-types";
import { workloadProfiles } from "./workload-profiles";
import type {
  AgentBodySpec,
  ModelDescriptor,
  TaskScenario,
  TaskTypeDescriptor,
  ToolDescriptor,
  WorkloadProfile,
} from "../contracts";

export interface LabCatalog {
  catalogVersion: string;
  world: {
    id: string;
    name: string;
    description: string;
  };
  workloads: WorkloadProfile[];
  taskTypes: TaskTypeDescriptor[];
  scenarios: TaskScenario[];
  bodies: AgentBodySpec[];
  models: ModelDescriptor[];
  tools: ToolDescriptor[];
}

export function getCatalog(): LabCatalog {
  return {
    catalogVersion: "v1",
    world: {
      id: seWorld.id,
      name: seWorld.name,
      description: seWorld.description,
    },
    workloads: workloadProfiles,
    taskTypes,
    scenarios: seWorldScenarios,
    bodies: agentBodies,
    models: modelDescriptors,
    tools: toolDescriptors,
  };
}
