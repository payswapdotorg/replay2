# PROD-023 — Agent engineering-operation compiler and interaction loop

You are a senior TypeScript engineer executing ONE well-specified work item in
the AISE repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: PROD-023 (the agent engineering-operation compiler and
  interaction loop). Do not start PROD-022/024/025 or any other item. Do not
  build a 3D editor, browser UI, or the solution engine itself (explicit
  non-scope).
- Owned surface (the ONLY files you may create/modify):
  - `backend/api/src/reasoning/solution/**` (NEW subdirectory — see §4)
  - `docs/productization-evidence/PROD-023/**` (evidence documents)
- Explicitly NOT yours: `packages/solution-contract/**` and
  `spec/solution-operation-contract.md` (the PROD-021 contract is FROZEN
  after its merge — IMPORT from `@aise/solution-contract`, never modify it;
  if the contract lacks something you need, STOP and report the conflict),
  `packages/solution-engine/**` and `backend/api/src/solution/**` (a
  concurrent worker owns them — do not create, import or stub-reference
  those paths), `backend/api/src/reasoning/**` OUTSIDE your new
  `solution/` subdirectory (the existing gateway/policy/providers/retrieval
  files are shared — read them, never edit them),
  `backend/api/src/server.ts` and `backend/api/src/main.ts` (shared mount
  points — the Tech Lead wires at the integration station), `apps/**`,
  `packages/**`, every spec file, the root `bun.lock`.
- If a mandated reading contradicts this packet, STOP and report the conflict.
- The compiler core must be DETERMINISTIC and OFFLINE-TESTABLE: no network
  calls, no LLM-provider requirement to pass the gate. An LLM enrichment
  seam may exist as an interface with a deterministic default implementation
  (see §4.1) — but every acceptance criterion must pass with the
  deterministic path alone.
- Never weaken, skip or delete an existing test.
- Your base is FIXED at the commit in §1. Another worker is concurrently
  executing a disjoint item (the solution engine under
  `packages/solution-engine` + `backend/api/src/solution`). Do NOT `git
  pull`, `git merge` or otherwise incorporate upstream changes during your
  run; those paths do not exist at your base and you must not anticipate
  them.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/AISE.git
cd AISE
git checkout 36acb217dcd5142ab920f0ad860068f457c5879e   # public GitHub main (adapter wave complete: PROD-016 + 017 + 019 + 020 + 021 merged)
git rev-parse HEAD   # must print 36acb217dcd5142ab920f0ad860068f457c5879e
BASE=$(git rev-parse HEAD)   # record this — your delivery diff base
bun install
git checkout -b prod-023/agent-operation-compiler
bun run verify
```

Baseline expectation: **3983 pass / 0 fail, VERIFY: PASS** (includes the
PROD-021 solution-contract suite and the PROD-017 apps/web suite). If the
baseline is red, STOP and report (do not try to fix the baseline).

## 2. Mandatory reading (in-repo, in this order)

1. `README.md` and `AGENTS.md` (operating contract, authority hierarchy —
   note the authority rules: agents never declare reality/approval)
2. `spec/architecture-lock.md` (immutable invariants)
3. `spec/agent-ownership.md` (what the agent owns and NEVER owns) and
   `spec/governance/architecture-change-record-005.md` (ACR-005: the
   interactive engineering solution workflow)
4. `spec/solution-operation-contract.md` (the PROD-021 contract —
   especially: the one constructor surface `createOperationIntent` with two
   provenance origins, capability negotiation honesty rules, lifecycle
   states, and the non-goals section owned by this item)
5. `docs/interactive-engineering-solution-workflow.md` (the interaction
   model your compiler serves) and `docs/productization-work-orders.md`
   §PROD-023 (your work order — reproduced in §3)
6. `packages/solution-contract/` in FULL: `src/intent.ts` (the intent
   constructor you MUST use — never hand-roll intent objects),
   `src/operation.ts` (origins, targets, parameters, units, provenance
   shapes), `src/negotiation.ts`, `src/state.ts`, `src/solution.ts`,
   `src/validation.ts`, `src/identity.ts`, plus `README.md` and
   `fixtures/operation/` (the valid intent fixtures are your compilation
   TARGETS — e.g. `EngineeringOperationIntent.valid-backfill.json`,
   valid-block-wall, valid-plaster, valid-demolition)
7. `backend/api/src/reasoning/` in full (gateway.ts, model.ts, policy.ts,
   providers/, retrieval.ts — the module your subdirectory integrates
   with; follow its code style, error taxonomy and testkit patterns)
8. `backend/api/src/execution/router.ts` header + tests (the transport
   conventions of this repo, should you expose route factories)

## 3. The work order (verbatim from docs/productization-work-orders.md)

> ## PROD-023 — Agent engineering-operation compiler and interaction loop
> **Owner:** AI/REASONING — **Depends on:** PROD-021
> **Protected surfaces:** reasoning/agent integration code and
> solution-command tests; no shared contract edits after PROD-021.
> **Purpose:** Let a competent real-world problem solver interact with the
> virtual solution through natural language while keeping engineering
> execution deterministic and inspectable.
> **Scope:**
> - parse natural-language requests into typed
>   `EngineeringOperationIntent` objects;
> - ask targeted clarification questions for missing dimensions, materials,
>   locations, sequencing or constraints;
> - show the proposed operation before execution where ambiguity or material
>   consequences exist;
> - call deterministic solution/validation tools rather than generating
>   geometry directly;
> - support navigation, explanation, inspection and BOQ-step lookup
>   commands;
> - preserve agent/user attribution and the exact normalized command that
>   was executed.
> **Explicit non-scope:** The agent must not declare reality, readiness,
> validation success, engineering approval or cost authority. It must not
> write raw geometry or bypass the solution engine.
> **Acceptance:** Representative building commands such as excavation
> dimensions, plaster thickness, block-wall height and material/layer
> changes compile into typed operations or explicit
> clarification/unsupported states. Equivalent commands from different
> phrasings resolve to equivalent semantic operations where unambiguous.
> **Evidence:** Command corpus + parser/tool trace + ambiguity/clarification
> tests + refusal/unsafe-operation tests + semantic-equivalence tests.

## 4. Implementation shape (follow the repo's own conventions)

All new code lives in `backend/api/src/reasoning/solution/`. Follow the
reasoning module's existing conventions (typed models, error taxonomy,
testkit). Required components:

1. **The compiler core** (`compiler.ts` + friends) — deterministic
   natural-language → operation compilation:
   - Input: a user utterance (plus optional session context: current
     solution id/version, recent operations). Output: a typed
     `CompiledCommand` union — `operation-intent` (a fully-resolved
     `EngineeringOperationIntent` built ONLY via the contract's
     `createOperationIntent` with origin `"agent"` and honest provenance),
     `clarification-needed` (missing dimensions, materials, locations,
     sequencing or constraints — each carrying a targeted question naming
     the exact missing slot and, where inferable, the offered choices),
     `unsupported` (outside the building operation vocabulary — explicit,
     never a guess), `ambiguous` (multiple readings that cannot be
     discriminated — list the readings), or `unsafe-refusal` (the request
     would bypass determinism or claim authority — refuse with reason).
   - Coverage target (the acceptance corpus): excavation dimensions
     (length/width/depth), backfill, block-wall height + material,
     plaster thickness + layers, demolition targets, and material/layer
     changes — the operation types of the contract's valid intent
     fixtures. Compile them from multiple natural phrasings (imperative,
     question-form, conversational, unit variants incl. cm/mm/m mixes,
     "make it deeper by X" deltas vs absolute values).
   - **Semantic equivalence**: where unambiguous, different phrasings MUST
     produce intents with identical operation type, target and parameter
     semantics (identity-stable where the contract's deterministic
     identity says they should be — proven by tests comparing the
     contract's identity derivations across phrasings).
   - The parser is deterministic (grammar/pattern based). An optional
     `NlUnderstandingPort` interface may mark the seam where an LLM
     provider (the module's existing provider stack) could later enrich
     parsing — with a deterministic default implementation, and the
     provenance recording WHICH path produced the interpretation.
2. **The clarification + proposal model** (`interaction.ts`) — the loop
   logic: given a CompiledCommand, decide the next turn — ask the targeted
   question, show the PROPOSED operation (the typed intent rendered for
   review, with its material consequences: affected target, quantities if
   computable from parameters alone, irreversible steps flagged) before
   execution when ambiguity or material consequences exist, or hand the
   intent to the tool port. The loop NEVER executes anything itself.
3. **The tool port** (`tools.ts`) — a `SolutionToolPort` interface with the
   deterministic tool calls the work order names: validate, step (apply),
   inspect, and navigation/explanation/BOQ-step lookup commands. The
   production binding (the solution engine + BOQ services) is wired by the
   Tech Lead at composition time (PROD-024/026 era); you ship the
   interface, a typed command/response model, and a clearly-labeled
   in-memory TEST DOUBLE so your loop tests run offline. The agent path
   calls ONLY this port — it never generates geometry, never writes raw
   state, never claims validation success (the port's responses are echoed
   with their authority labels, never re-authored).
4. **Command corpus** (`corpus.ts` + fixtures) — a versioned, enumerable
   corpus: representative commands (the acceptance set above),
   equivalents, ambiguities, unsupported domains, unsafe/authority-claiming
   requests (e.g. "mark it validated", "approve this", "just write the
   geometry directly", "set the cost to X"), clarification cases. This
   corpus drives the tests and doubles as the evidence inventory.
5. **Attribution + provenance** — every executed command records: the raw
   utterance, the normalized command (the exact typed intent actually
   executed, serialized canonically), the compiler path (deterministic /
   provider-enriched), agent vs user attribution per the contract's
   provenance shapes. The exact normalized command is recoverable from
   every tool call (the parser/tool trace).
6. **Route factory** (`router.ts`, optional but recommended) — a PURE
   transport adapter exposing compile/next-turn over the loop (follow the
   execution router pattern; not mounted in server.ts — the Lead wires it).
7. **Tests** (all under `backend/api/src/reasoning/solution/`):
   - compilation tests (corpus-driven: each representative command →
     expected typed outcome);
   - ambiguity/clarification tests (each missing-slot case → the targeted
     question naming the slot);
   - refusal/unsafe tests (authority claims, determinism bypasses →
     unsafe-refusal with reasons; prove NO intent object is produced);
   - semantic-equivalence tests (phrasing sets → identical
     type/target/parameters; identity-derivation comparisons);
   - tool-trace tests (every tool call carries attribution + the exact
     normalized command; no direct geometry writes — sabotage-style test
     proving the only effect surface is the port);
   - interaction-loop tests (clarify → user answers → proposed operation
     → confirm; ambiguity → readings listed; unsupported → honest state).
8. **Evidence docs** under `docs/productization-evidence/PROD-023/`:
   `compiler-artifacts.md` (what exists, where, commands + expected output
   summary), `command-corpus.md` (the corpus inventory: category → count →
   example), `equivalence-and-refusal.md` (equivalence sets, refusal
   taxonomy, clarification slots), `tool-trace.md` (the port interface,
   the attribution/normalized-command guarantee, where the engine binding
   will be wired).

Style: the reasoning module's zod-based typed models and error taxonomy; no
new runtime dependencies; no I/O in the compiler core (the corpus may be a
TS module, which keeps it lint-visible and side-effect free).

## 5. Gate (must pass before reporting)

```bash
bun run verify
```

Expected: **(3983 + N) pass / 0 fail** where N = your new tests (state N in
the report), typecheck + lint clean, boundary scan clean (backend/api may
import packages; your subdirectory must not import apps/** or reach outside
the reasoning module except `@aise/solution-contract` and other packages),
final line `VERIFY: PASS`. Your tests must be picked up by the root gate via
the workspace glob — confirm they are counted.

Then commit locally (no push):

```bash
git add <your owned files only>   # NOT bun.lock
git -c user.name="worker" -c user.email="worker@aise" commit -m "PROD-023: agent engineering-operation compiler and interaction loop"
git diff $BASE..HEAD --stat
```

## 6. Delivery — stage INSIDE the workspace-tracked project directory

Your repo clone lives OUTSIDE the workspace root, which the Tech Lead's harvest
API cannot see. After committing, copy EVERY new/changed file (the complete
diff vs the base commit `$BASE` from §1) into the PROJECT directory
(the one containing package.json / src/ — the workspace root), preserving
repo-relative paths:

```bash
mkdir -p delivery
git diff --name-only $BASE..HEAD > /tmp/changed.txt
while read -r f; do mkdir -p "delivery/$(dirname "$f")"; cp "$f" "delivery/$f"; done < /tmp/changed.txt
{ echo "commit: $(git rev-parse HEAD)"; echo "base: $BASE"; echo; git diff $BASE..HEAD --stat; } > delivery/DELIVERY.txt
ls -R delivery | head -50   # sanity: the full tree is staged
```

EXCLUDE `bun.lock` from the delivery if it appears. The Lead regenerates the
canonical lockfile at the integration station. Also exclude binary/build
artifacts — source only.

Do NOT change anything else after the gate run. No re-runs, no edits, no push.

## 7. Final report — reply with EXACTLY this format

```
PROD-023 COMPLETION REPORT
base: public main @ 36acb217dcd5142ab920f0ad860068f457c5879e (adapter wave complete: PROD-016 + 017 + 019 + 020 + 021 merged)
repo path in sandbox: <absolute path of your AISE clone>
commit: <local commit sha>
changed files: <count + the diffstat>
new tests: N = <count> (suite: 3983 + N pass / 0 fail)
module layout: <file list of backend/api/src/reasoning/solution/>
command corpus: <category counts: representative / equivalent / ambiguous / unsupported / unsafe / clarification>
acceptance:
- representative building commands compile to typed ops or explicit states: <one-line proof incl. corpus counts>
- equivalent phrasings resolve to equivalent semantic operations: <one-line proof incl. identity-derivation comparison>
- targeted clarification for missing slots: <one-line proof incl. slot inventory>
- unsafe/authority-claiming requests refused: <one-line proof incl. refusal taxonomy>
- deterministic tools only (no direct geometry writes): <one-line proof incl. sabotage test>
- attribution + exact normalized command preserved: <one-line proof>
tool port: <interface surface + where the engine binding will be wired>
verify: <paste the final summary lines: tests total, pass/fail, VERIFY: PASS>
delivery: staged under delivery/ in the workspace root (file list in DELIVERY.txt; bun.lock excluded)
notes: <any deviation from this packet, or "none">
```

Do not paste source code in the report — paths, counts and the verify output
only.
