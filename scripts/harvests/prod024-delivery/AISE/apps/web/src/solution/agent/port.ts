/**
 * PROD-024 — the AGENT SEAM of the interactive solution workspace.
 *
 * The port through which the workspace routes natural-language intents to
 * the PROD-023 agent operation compiler (`backend/api/src/reasoning/solution/`
 * — the deterministic NL → `EngineeringOperationIntent` compiler plus its
 * clarification/proposal interaction loop). The compiler lives in the
 * backend zone and CANNOT be imported from apps (the AISE-001 boundary
 * matrix: apps → apps|packages only), so this module defines the port as
 * STRUCTURAL MIRRORS of the compiler's public shapes — the same field
 * names and JSON shapes as `reasoning/solution/model.ts` + `interaction.ts`
 * (the `workspace/model.ts` mirror discipline). The REAL compiler's values
 * satisfy these types as-is; the Tech Lead's binding at the integration
 * station wires the real `createSolutionCommandCompiler()` +
 * `decideNextTurn` (directly, or through the mounted
 * `POST /v1/solution-agent/compile|turn` routes this module's HTTP adapter
 * speaks) with zero workspace edits.
 *
 * The workspace NEVER re-implements the compiler: it never parses language,
 * never invents dimensions/materials and never fabricates operations. It
 * submits utterances (+ pending state) to the port and renders the typed
 * outcomes VERBATIM — clarification questions, proposals (previewed before
 * execution), unsupported/ambiguous/unsafe-refusal states and read-only
 * tool commands. Confirmed proposals are applied through the SAME
 * submission path as direct manipulation (§4.2 of the work order — one
 * operation semantics).
 *
 * Two port implementations ship:
 *
 *  1. `createHttpSolutionAgentPort` — the same-origin HTTP binding over the
 *     PROD-023 route factory's paths (fetch INJECTED; PROD-001 contract).
 *  2. `createScriptedSolutionAgentPort` — a CLEARLY-LABELED DETERMINISTIC
 *     TEST DOUBLE for the co-located tests (the PROD-023 discipline of
 *     `createInMemorySolutionToolDouble`): it replays fixed scripted
 *     responses — REAL contract intents built through
 *     `createOperationIntent` with agent provenance — and never parses
 *     anything. It is a double OF the seam, never a second compiler.
 */

import {
  createOperationIntent,
  REFERENCE_BUILDING_DOMAIN,
  type EngineeringOperationIntent,
  type OperationTarget,
  type TypedOperationParameter,
} from "../../../../packages/solution-contract/src/index";

/* ------------------------------------------------------------------ */
/* Structural mirrors of the PROD-023 compiler shapes                  */
/* (backend/api/src/reasoning/solution/model.ts + interaction.ts)      */
/* ------------------------------------------------------------------ */

/** Mirror of `SessionFocus` — a caller-asserted spatial anchoring focus. */
export interface AgentSessionFocus {
  readonly focusId: string;
  readonly label: string;
  readonly aliases: readonly string[];
  readonly selectorKind: OperationTarget["selectorKind"];
  readonly nodeRefs: readonly string[];
  readonly geometryRefs: OperationTarget["geometryRefs"];
  readonly knownParameters?: readonly TypedOperationParameter[];
}

/** Mirror of `RecentOperationSummary` — a session operation, caller-projected. */
export interface AgentRecentOperation {
  readonly operationId: string;
  readonly operationType: string;
  readonly parameters: readonly TypedOperationParameter[];
}

/** Mirror of `AgentSessionContext` — everything the compiler may look at. */
export interface AgentSessionContext {
  readonly sessionId: string;
  readonly agentId: string;
  readonly userId?: string;
  readonly proposedTo?: { readonly solutionId: string; readonly versionNumber: number };
  readonly foci?: readonly AgentSessionFocus[];
  readonly defaultFocusId?: string;
  readonly recentOperations?: readonly AgentRecentOperation[];
}

/** Mirror of `ClarificationQuestion` — one targeted missing-slot question. */
export interface AgentClarificationQuestion {
  readonly slotKind: "dimension" | "material" | "location" | "sequencing" | "constraint";
  readonly slot: string;
  readonly question: string;
  readonly offeredChoices?: readonly string[];
}

/** Mirror of `AmbiguityReading` — one reading of an ambiguous utterance. */
export interface AgentAmbiguityReading {
  readonly description: string;
  readonly operationType?: string;
  readonly differingSlot?: string;
}

/** Mirror of `CommandAttribution` — the executed command's attribution. */
export interface AgentCommandAttribution {
  readonly rawUtterance: string;
  readonly normalizedCommand: string;
  readonly normalizedCommandText: string;
  readonly compilerPath: "deterministic" | "provider-enriched";
  readonly agentId: string;
  readonly userId?: string;
  readonly sessionId: string;
  readonly compiledAt: string;
}

/** Mirror of the `CompiledCommand` union (the operation-authoring members
 *  the workspace renders; the tool-command member below). */
export type AgentCompiledCommand =
  | { readonly kind: "operation-intent"; readonly intent: EngineeringOperationIntent; readonly attribution: AgentCommandAttribution }
  | {
      readonly kind: "clarification-needed";
      readonly questions: readonly [AgentClarificationQuestion, ...AgentClarificationQuestion[]];
      readonly partialOperationType?: string;
      readonly attribution: AgentCommandAttribution;
    }
  | { readonly kind: "unsupported"; readonly vertical?: string; readonly reason: string; readonly attribution: AgentCommandAttribution }
  | {
      readonly kind: "ambiguous";
      readonly readings: readonly [AgentAmbiguityReading, ...AgentAmbiguityReading[]];
      readonly attribution: AgentCommandAttribution;
    }
  | { readonly kind: "unsafe-refusal"; readonly reasonCode: string; readonly reason: string; readonly attribution: AgentCommandAttribution }
  | {
      readonly kind: "tool-command";
      readonly toolCommandKind: "validate" | "inspect" | "navigate" | "explain" | "boq-step-lookup";
      readonly command: AgentToolCommand;
      readonly attribution: AgentCommandAttribution;
    };

/** Mirror of the `SolutionToolCommand` union (the read-only/agentic commands). */
export type AgentToolCommand =
  | { readonly kind: "validate"; readonly attribution: AgentCommandAttribution; readonly solutionId: string; readonly versionNumber: number }
  | {
      readonly kind: "apply";
      readonly attribution: AgentCommandAttribution;
      readonly intent: EngineeringOperationIntent;
      readonly solutionId: string;
      readonly versionNumber: number;
    }
  | { readonly kind: "inspect"; readonly attribution: AgentCommandAttribution; readonly solutionId: string; readonly versionNumber: number }
  | {
      readonly kind: "navigate";
      readonly attribution: AgentCommandAttribution;
      readonly solutionId: string;
      readonly versionNumber: number;
      readonly target: {
        readonly kind: "goto-step" | "list-steps" | "current-state";
        readonly stateIndex?: number;
      };
    }
  | {
      readonly kind: "explain";
      readonly attribution: AgentCommandAttribution;
      readonly solutionId: string;
      readonly versionNumber: number;
      readonly operationIndex: number;
    }
  | {
      readonly kind: "boq-step-lookup";
      readonly attribution: AgentCommandAttribution;
      readonly solutionId: string;
      readonly versionNumber: number;
      readonly operationIndex: number;
    };

/** Mirror of `OperationProposal` — the pre-execution review surface. */
export interface AgentOperationProposal {
  readonly intent: EngineeringOperationIntent;
  readonly attribution: AgentCommandAttribution;
  readonly renderedCommand: string;
  readonly target: {
    readonly description: string;
    readonly selectorKind: OperationTarget["selectorKind"];
    readonly nodeRefs: readonly string[];
    readonly geometryRefs: OperationTarget["geometryRefs"];
  };
  readonly estimatedQuantities: readonly {
    readonly label: string;
    readonly dimension: "length" | "area" | "volume" | "count";
    readonly value: number;
    readonly unit: string;
    readonly basis: string;
  }[];
  readonly irreversible: boolean;
  readonly reviewRequirements: readonly string[];
}

/** Mirror of `PendingClarification` — a clarification awaiting the answer. */
export interface AgentPendingClarification {
  readonly utterance: string;
  readonly questions: readonly AgentClarificationQuestion[];
}

/** Mirror of `PendingProposal` — a proposal awaiting confirmation. */
export interface AgentPendingProposal {
  readonly proposal: AgentOperationProposal;
  readonly utterance: string;
}

/** Mirror of the `TurnDecision` union (the workspace's consumption side). */
export type AgentTurnDecision =
  | { readonly decision: "ask"; readonly questions: readonly AgentClarificationQuestion[]; readonly pendingClarification: AgentPendingClarification }
  | { readonly decision: "propose"; readonly proposal: AgentOperationProposal; readonly pendingProposal: AgentPendingProposal }
  | { readonly decision: "dispatch-operation"; readonly command: AgentToolCommand & { readonly kind: "apply" }; readonly proposal: AgentOperationProposal }
  | { readonly decision: "dispatch-tool"; readonly command: AgentToolCommand }
  | { readonly decision: "unsupported"; readonly command: AgentCompiledCommand & { readonly kind: "unsupported" } }
  | { readonly decision: "ambiguous"; readonly command: AgentCompiledCommand & { readonly kind: "ambiguous" } }
  | { readonly decision: "refuse"; readonly command: AgentCompiledCommand & { readonly kind: "unsafe-refusal" } }
  | { readonly decision: "cancelled"; readonly note: string };

/** Mirror of `TurnInput` — one interaction turn. */
export interface AgentTurnInput {
  readonly utterance: string;
  readonly session: AgentSessionContext;
  readonly pendingClarification?: AgentPendingClarification;
  readonly pendingProposal?: AgentPendingProposal;
}

/* ------------------------------------------------------------------ */
/* The port                                                            */
/* ------------------------------------------------------------------ */

/** Honest identity of the agent binding (metadata, never authority). */
export interface SolutionAgentDescriptor {
  readonly agentId: string;
  /** Which path produced this binding ("http-route" | "scripted-double"). */
  readonly binding: string;
}

/**
 * THE agent seam: compiles utterances and decides interaction turns
 * through the PROD-023 compiler (real binding wired by the Tech Lead; the
 * scripted double exists for tests only). The workspace renders the typed
 * outcomes verbatim and NEVER authors operations itself.
 */
export interface SolutionAgentPort {
  readonly descriptor: SolutionAgentDescriptor;
  compile(input: {
    readonly utterance: string;
    readonly session: AgentSessionContext;
  }): Promise<AgentCompiledCommand>;
  decideTurn(input: AgentTurnInput): Promise<AgentTurnDecision>;
}

/* ------------------------------------------------------------------ */
/* The HTTP binding (the Lead's production wiring)                      */
/* ------------------------------------------------------------------ */

/** A fetch-like transport (the browser global, or a test stub). */
export type AgentFetchLike = (
  input: string,
  init?: { readonly method?: string; readonly body?: string },
) => Promise<{ readonly ok: boolean; readonly status: number; readonly text: () => Promise<string> }>;

async function postAgentJson(
  fetchImpl: AgentFetchLike,
  path: string,
  body: unknown,
): Promise<unknown> {
  const response = await fetchImpl(path, { method: "POST", body: JSON.stringify(body) });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`solution agent ${path} answered HTTP ${response.status}: ${text}`);
  }
  return JSON.parse(text) as unknown;
}

/**
 * The same-origin HTTP binding over the PROD-023 route factory's paths
 * (`POST /v1/solution-agent/compile` and `/v1/solution-agent/turn` —
 * see `backend/api/src/reasoning/solution/router.ts`). Fetch is INJECTED
 * (the PROD-001 same-origin contract).
 */
export function createHttpSolutionAgentPort(options: {
  readonly fetchImpl: AgentFetchLike;
  readonly basePath?: string;
  readonly agentId?: string;
}): SolutionAgentPort {
  const base = options.basePath ?? "/v1/solution-agent";
  const fetchImpl = options.fetchImpl;
  return {
    descriptor: { agentId: options.agentId ?? "aise-solution-agent", binding: "http-route" },
    compile: async (input) =>
      postAgentJson(fetchImpl, `${base}/compile`, input) as Promise<AgentCompiledCommand>,
    decideTurn: async (input) => {
      const payload = await postAgentJson(fetchImpl, `${base}/turn`, input) as {
        decision: AgentTurnDecision;
      };
      return payload.decision;
    },
  };
}

/* ------------------------------------------------------------------ */
/* The scripted TEST DOUBLE (clearly labeled — NOT the compiler)        */
/* ------------------------------------------------------------------ */

/** One scripted compile outcome, keyed by the EXACT utterance. */
export interface ScriptedAgentTurn {
  /** The exact user utterance this script answers (verbatim match). */
  readonly utterance: string;
  /** The outcome the double answers `decideTurn` with (a full decision). */
  readonly decision: AgentTurnDecision;
}

/**
 * A CLEARLY-LABELED DETERMINISTIC TEST DOUBLE of the agent seam — the
 * PROD-023 `createInMemorySolutionToolDouble` discipline carried into the
 * workspace's tests. It performs NO language understanding: it matches the
 * EXACT scripted utterance and replays the scripted typed decision;
 * anything else answers an honest `unsupported` mirroring the compiler's
 * own shape. Scripted intents are REAL contract objects (built through
 * `createOperationIntent` with agent provenance) so the tests exercise the
 * REAL submission path and the REAL identity derivations.
 */
export function createScriptedSolutionAgentPort(script: {
  readonly agentId: string;
  readonly turns: readonly ScriptedAgentTurn[];
}): SolutionAgentPort {
  const byUtterance = new Map<string, AgentTurnDecision>(
    script.turns.map((turn) => [turn.utterance, turn.decision]),
  );
  return {
    descriptor: { agentId: script.agentId, binding: "scripted-double" },
    compile: async (input) => {
      const decision = byUtterance.get(input.utterance.trim());
      if (decision === undefined) {
        return unsupportedOutcome(script.agentId, input);
      }
      return decisionOutcome(decision);
    },
    decideTurn: async (input) => {
      const decision = byUtterance.get(input.utterance.trim());
      if (decision !== undefined) {
        return decision;
      }
      // A pending clarification merges the answer into the original
      // request (the interaction loop's contract): the double replays the
      // script keyed by the MERGED utterance when one is scripted.
      if (input.pendingClarification !== undefined) {
        const merged = `${input.pendingClarification.utterance} ${input.utterance.trim()}`;
        const mergedDecision = byUtterance.get(merged);
        if (mergedDecision !== undefined) {
          return mergedDecision;
        }
      }
      if (input.pendingProposal !== undefined) {
        return {
          decision: "cancelled",
          note:
            "the scripted double has no script for this confirmation — " +
            "script it explicitly (the double never improvises)",
        };
      }
      const unsupported = unsupportedOutcome(script.agentId, input);
      switch (unsupported.kind) {
        case "unsupported":
          return { decision: "unsupported", command: unsupported };
        default:
          return { decision: "cancelled", note: "unscripted utterance" };
      }
    },
  };
}

function decisionOutcome(decision: AgentTurnDecision): AgentCompiledCommand {
  switch (decision.decision) {
    case "propose":
      return {
        kind: "operation-intent",
        intent: decision.proposal.intent,
        attribution: decision.proposal.attribution,
      };
    case "ask":
      return {
        kind: "clarification-needed",
        questions: [decision.questions[0] ?? fallbackQuestion()],
        attribution: clarificationAttribution(decision.pendingClarification.utterance),
      };
    case "unsupported":
      return decision.command;
    case "ambiguous":
      return decision.command;
    case "refuse":
      return decision.command;
    default:
      return unsupportedPlain("the scripted double serves decideTurn scripts only");
  }
}

function fallbackQuestion(): AgentClarificationQuestion {
  return {
    slotKind: "dimension",
    slot: "depth",
    question: "How deep should the excavation be?",
  };
}

function clarificationAttribution(utterance: string): AgentCommandAttribution {
  return {
    rawUtterance: utterance,
    normalizedCommand: "",
    normalizedCommandText: "",
    compilerPath: "deterministic",
    agentId: "scripted-double",
    sessionId: "scripted",
    compiledAt: "2026-09-16T10:00:00.000Z",
  };
}

function unsupportedOutcome(
  agentId: string,
  input: { readonly utterance: string },
): AgentCompiledCommand & { readonly kind: "unsupported" } {
  return {
    kind: "unsupported",
    reason:
      `the scripted test double has no script for this utterance — it never ` +
      `improvises (the REAL compiler is wired at the integration station)`,
    attribution: {
      rawUtterance: input.utterance,
      normalizedCommand: "",
      normalizedCommandText: "",
      compilerPath: "deterministic",
      agentId,
      sessionId: "scripted",
      compiledAt: "2026-09-16T10:00:00.000Z",
    },
  };
}

function unsupportedPlain(reason: string): AgentCompiledCommand {
  return {
    kind: "unsupported",
    reason,
    attribution: clarificationAttribution(""),
  };
}

/* ------------------------------------------------------------------ */
/* Test-double script builders (REAL contract intents, agent origin)    */
/* ------------------------------------------------------------------ */

/**
 * Builds a REAL contract operation intent with AGENT provenance (the
 * single constructor surface, origin `"agent"`, the exact command text) —
 * the shape the REAL compiler produces. Used by the scripted double's
 * scripts and by the equivalence tests.
 */
export function buildAgentIntent(input: {
  readonly intentId: string;
  readonly operationType: string;
  readonly parameters: readonly { readonly name: string; readonly value: number | string | boolean; readonly unit?: string }[];
  readonly target: OperationTarget;
  readonly commandText: string;
  readonly authoredAt: string;
  readonly authoredBy?: string;
  readonly proposedTo?: { readonly solutionId: string; readonly versionNumber: number };
  readonly dependsOn?: readonly { readonly operationRef: string; readonly dependencyKind: "completion-before" | "state-precondition" }[];
}): EngineeringOperationIntent {
  return createOperationIntent({
    intentId: input.intentId,
    operationType: input.operationType,
    domain: REFERENCE_BUILDING_DOMAIN,
    parameters: [...input.parameters],
    target: input.target,
    provenance: {
      origin: "agent",
      authoredBy: input.authoredBy ?? "agent-demo-assistant",
      authoredAt: input.authoredAt,
      evidenceIds: [],
      commandText: input.commandText,
    },
    ...(input.dependsOn === undefined
      ? {}
      : {
          dependsOn: input.dependsOn.map((dependency) => ({
            ...dependency,
            contractVersion: "1.0.0",
          })),
        }),
    ...(input.proposedTo === undefined ? {} : { proposedTo: input.proposedTo }),
  });
}

/** Builds a `propose` decision over an intent (the preview surface). */
export function proposeDecisionOf(input: {
  readonly intent: EngineeringOperationIntent;
  readonly renderedCommand: string;
  readonly estimatedQuantities: readonly {
    readonly label: string;
    readonly dimension: "length" | "area" | "volume" | "count";
    readonly value: number;
    readonly unit: string;
    readonly basis: string;
  }[];
  readonly irreversible: boolean;
  readonly reviewRequirements: readonly string[];
  readonly utterance: string;
}): AgentTurnDecision {
  return {
    decision: "propose",
    proposal: {
      intent: input.intent,
      attribution: {
        rawUtterance: input.utterance,
        normalizedCommand: "",
        normalizedCommandText: input.renderedCommand,
        compilerPath: "deterministic",
        agentId: input.intent.provenance.authoredBy,
        sessionId: "scripted",
        compiledAt: input.intent.provenance.authoredAt,
      },
      renderedCommand: input.renderedCommand,
      target: {
        description: input.intent.target.description,
        selectorKind: input.intent.target.selectorKind,
        nodeRefs: [...input.intent.target.nodeRefs],
        geometryRefs: input.intent.target.geometryRefs.map((ref) => ({ ...ref })),
      },
      estimatedQuantities: [...input.estimatedQuantities],
      irreversible: input.irreversible,
      reviewRequirements: [...input.reviewRequirements],
    },
    pendingProposal: {
      proposal: {
        intent: input.intent,
        attribution: {
          rawUtterance: input.utterance,
          normalizedCommand: "",
          normalizedCommandText: input.renderedCommand,
          compilerPath: "deterministic",
          agentId: input.intent.provenance.authoredBy,
          sessionId: "scripted",
          compiledAt: input.intent.provenance.authoredAt,
        },
        renderedCommand: input.renderedCommand,
        target: {
          description: input.intent.target.description,
          selectorKind: input.intent.target.selectorKind,
          nodeRefs: [...input.intent.target.nodeRefs],
          geometryRefs: input.intent.target.geometryRefs.map((ref) => ({ ...ref })),
        },
        estimatedQuantities: [...input.estimatedQuantities],
        irreversible: input.irreversible,
        reviewRequirements: [...input.reviewRequirements],
      },
      utterance: input.utterance,
    },
  };
}

/** Builds a `dispatch-operation` decision (a confirmed apply). */
export function dispatchOperationDecisionOf(
  proposal: AgentOperationProposal,
  solutionId: string,
  versionNumber: number,
): AgentTurnDecision {
  return {
    decision: "dispatch-operation",
    command: {
      kind: "apply",
      attribution: proposal.attribution,
      intent: proposal.intent,
      solutionId,
      versionNumber,
    },
    proposal,
  };
}
