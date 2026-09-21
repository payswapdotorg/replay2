#!/usr/bin/env python3
"""worklog_replay.py — deterministic replay of a worker session's file state.

The work log (batch store) records EVERY tool call with full arguments and
in-order blocks. For a delivery whose sandbox is unreachable (files-API
cannot serve outside the project dir), the FINAL file state can be
reconstructed losslessly by replaying:

  - Write     -> files[fp] = content
  - Edit      -> replace first occurrence of old_str (must exist)
  - MultiEdit -> sequential Edits
  - Bash      -> the known delivery-mutating sed/python commands (encoded
                 per work item; everything else is read-only or /tmp)

Validation: any Edit whose old_str is missing aborts the replay (the
worker's session succeeded, so a faithful replay must too). The final
tree is then diffstat-checked against the base by the Lead.

Usage: worklog_replay.py <assistant-message.json> <outdir> <item-name>
Currently encoded mutations: prod024 (SED blocks 201/203/217/310/336).
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def norm(fp):
    fp = fp.replace("/home/z/AISE/", "", 1) if fp.startswith("/home/z/AISE/") else fp
    return fp


class Replay:
    def __init__(self):
        self.files = {}
        self.log = []

    def note(self, s):
        self.log.append(s)

    def write(self, fp, content):
        self.files[norm(fp)] = content

    def edit(self, fp, old, new, replace_all=False):
        fp = norm(fp)
        if fp not in self.files:
            raise RuntimeError(f"Edit on unwritten file {fp}")
        cur = self.files[fp]
        if old not in cur:
            raise RuntimeError(f"Edit old_str NOT FOUND in {fp}: {old[:80]!r}")
        if not replace_all and cur.count(old) > 1:
            # house Edit tool fails on non-unique old_str — but workers
            # sometimes pass replace_all; replay first-occurrence (matches
            # the tool's replace_all=False behavior used by the worker)
            self.note(f"WARN multi-occurrence old_str in {fp} ({cur.count(old)}x), replacing first")
        self.files[fp] = cur.replace(old, new, 1 if not replace_all else -1)

    # ---- prod024 bash mutations (exact sed/python semantics) ----
    def prod024_sed_201(self):
        lvl = lambda n: '"' + "../" * n + "packages/"
        for f in ["service.ts", "model.ts", "operations.ts", "boq.ts", "fixtures.ts"]:
            p = f"apps/web/src/solution/{f}"
            self.files[p] = self.files[p].replace(lvl(3), lvl(4))
        for f in ["agent/port.ts", "panes/BoqPane.tsx", "panes/DetailInspectorPane.tsx",
                  "panes/QuantitiesPane.tsx", "panes/TimelinePane.tsx", "viewer/model.ts"]:
            p = f"apps/web/src/solution/{f}"
            self.files[p] = self.files[p].replace(lvl(4), lvl(6))

    def prod024_sed_203(self):
        lvl = lambda n: '"' + "../" * n + "packages/"
        for f in ["agent/port.ts", "panes/BoqPane.tsx", "panes/QuantitiesPane.tsx",
                  "panes/TimelinePane.tsx", "panes/DetailInspectorPane.tsx", "viewer/model.ts"]:
            p = f"apps/web/src/solution/{f}"
            self.files[p] = self.files[p].replace(lvl(6), lvl(5))
        p = "apps/web/src/solution/panes/labels.ts"
        self.files[p] = self.files[p].replace(lvl(4), lvl(5))
        p = "apps/web/src/solution/SolutionWorkspace.tsx"
        self.files[p] = self.files[p].replace(lvl(3), lvl(4))

    def prod024_sed_217(self):
        p = "apps/web/src/solution/SolutionWorkspace.tsx"
        lines = self.files[p].split("\n")
        self.files[p] = "\n".join(
            ln for ln in lines if "defaultIntentSeq={intentSeq.current}" not in ln)
        p = "apps/web/src/solution/viewer/SceneView.tsx"
        self.files[p] = self.files[p].replace(
            'import { sceneTextAlternative } from "./svg";', "", 1)

    def prod024_sed_310(self):
        sol = "apps/web/src/solution/"
        # sed 1: model.test.ts import line replace
        p = sol + "model.test.ts"
        self.files[p] = self.files[p].replace(
            "import { openWorkspace, stepTimeline, submitIntent, steppedWorkspaceClock, buildDirectManipulationIntent } from \"./operations\";",
            "import { openWorkspace, stepTimeline, submitIntent, buildDirectManipulationIntent } from \"./operations\";", 1)
        # sed 2 (multiline pattern — no-op replace of identical strings, then python does the real work)
        # python heredoc:
        p = sol + "model.test.ts"
        s = self.files[p]
        s = s.replace("  currentVersionOf,\n", "", 1)
        s = s.replace("  initialWorkspaceState,\n", "", 1)
        self.files[p] = s
        p = sol + "operations.test.ts"
        s = self.files[p]
        start = s.index('/** The deterministic demo deps (the local REAL engine binding). */')
        end = s.index('/** Opens the demo workspace (version 1, layer 0). */')
        s = s[:start] + s[end:]
        s = s.replace('  operationIdentityOf,\n  steppedWorkspaceClock,\n  type WorkspaceDeps,\n} from "./operations";',
                      '  operationIdentityOf,\n} from "./operations";', 1)
        self.files[p] = s
        p = sol + "service.test.ts"
        s = self.files[p]
        s = s.replace('import { openWorkspace, steppedWorkspaceClock } from "./operations";',
                      'import { openWorkspace } from "./operations";', 1)
        self.files[p] = s
        p = sol + "workspace.test.tsx"
        s = self.files[p]
        s = s.replace('import { readFileSync } from "node:fs";\n', '', 1)
        s = s.replace('import { join } from "node:path";\n', '', 1)
        self.files[p] = s

    def prod024_sed_312(self):
        p = "apps/web/src/solution/operations.test.ts"
        s = self.files[p]
        s = s.replace('import { createLocalSolutionService } from "./service";\n', '', 1)
        s = s.replace('import { DEMO_SOLUTION_WORLD, demoBaselineGeometry, demoObservedScene } from "./fixtures";',
                      'import { DEMO_SOLUTION_WORLD, demoObservedScene } from "./fixtures";', 1)
        self.files[p] = s

    def prod024_sed_315(self):
        sol = "apps/web/src/solution/"
        # 1. port.test.ts dispatch call sites (global replace — no count in source)
        p = sol + "agent/port.test.ts"
        s = self.files[p]
        s = s.replace(
            '''          decision: dispatchOperationDecisionOf(
            proposal.decision === "propose" ? proposal.proposal : proposal.proposal,
            DEMO_SOLUTION_WORLD.solutionId,
            1,
          ),''',
            '''          decision: dispatchOperationDecisionOf(proposal.proposal, DEMO_SOLUTION_WORLD.solutionId, 1),''')
        self.files[p] = s
        # 2. model.test.ts: re-add steppedWorkspaceClock
        p = sol + "model.test.ts"
        s = self.files[p]
        s = s.replace(
            'import { openWorkspace, stepTimeline, submitIntent, buildDirectManipulationIntent } from "./operations";',
            'import { openWorkspace, stepTimeline, submitIntent, steppedWorkspaceClock, buildDirectManipulationIntent } from "./operations";')
        self.files[p] = s
        # 3. service.test.ts non-null
        p = sol + "service.test.ts"
        s = self.files[p]
        s = s.replace(
            "    expect(inspected.requestedState.stateId).toBe(\n      currentVersionOf(state).states[0]?.stateId,\n    );",
            "    expect(inspected.requestedState.stateId).toBe(\n      currentVersionOf(state).states[0]!.stateId,\n    );")
        self.files[p] = s
        # 4. workspace.test.tsx dispatch + non-nulls
        p = sol + "workspace.test.tsx"
        s = self.files[p]
        s = s.replace(
            '''        decision: dispatchOperationDecisionOf(
          blockWallProposal.decision === "propose" ? blockWallProposal.proposal : blockWallProposal.proposal,
          DEMO_SOLUTION_WORLD.solutionId,
          1,
        ),''',
            '''        decision: dispatchOperationDecisionOf(
          blockWallProposal.proposal,
          DEMO_SOLUTION_WORLD.solutionId,
          1,
        ),''')
        s = s.replace("expect(cursorStateOf(stepped).stateId).toBe(replay.version.states[index]?.stateId);",
                      "expect(cursorStateOf(stepped).stateId).toBe(replay.version.states[index]!.stateId);")
        self.files[p] = s
        # 5. fallback.test.tsx mutable rows
        p = sol + "fallback/fallback.test.tsx"
        s = self.files[p]
        s = s.replace(
            '  const rows: Parameters<typeof QuantitiesPane>[0]["rows"] = [];',
            '  const rows: import("../model").QuantityRow[] = [];')
        self.files[p] = s

    def prod024_sed_336(self):
        p = "DELIVERY.txt"
        self.files[p] = self.files[p].replace(
            "docs/productization-evidence/PROD-024/accessibility-fallback-trace.md",
            "docs/productization-evidence/PROD-024/accessibility-fallback-trace.md\n"
            "docs/productization-evidence/PROD-024/adapter-conformance.md", 1)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    msg_file, outdir, item = sys.argv[1], sys.argv[2], sys.argv[3]
    msg = json.load(open(msg_file))
    blocks = msg.get("content_blocks") or []
    r = Replay()

    # signatures of the mutating bash commands (prefix match on the command)
    def bash_key(cmd):
        if item == "prod024":
            if "sed -i 's|\"\\.\\./\\.\\./\\.\\./packages/|" in cmd and "service.ts model.ts" in cmd:
                return 201
            if "sed -i 's|\"\\.\\./\\.\\./\\.\\./\\.\\./\\.\\./\\.\\./packages/|" in cmd:
                return 203
            if "defaultIntentSeq" in cmd and "sed -i" in cmd:
                return 217
            if "model.test.ts" in cmd and "python3 -" in cmd and "sed -i" in cmd:
                return 310
            if "createLocalSolutionService" in cmd and "operations.test.ts" in cmd:
                return 312
            if "Fix the remaining typecheck issues" in cmd:
                return 315
            if "adapter-conformance.md" in cmd and "DELIVERY.txt" in cmd and "sed -i" in cmd:
                return 336
        return None

    handlers = {201: r.prod024_sed_201, 203: r.prod024_sed_203,
                217: r.prod024_sed_217, 310: r.prod024_sed_310,
                312: r.prod024_sed_312, 315: r.prod024_sed_315,
                336: r.prod024_sed_336}

    n_write = n_edit = n_multi = n_bash = 0
    for b in blocks:
        if b.get("type") != "tool_calls":
            continue
        for tc in (b.get("content") or []):
            fn = (tc.get("function") or {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                continue
            if name == "Write":
                r.write(args.get("filepath"), args.get("content") or "")
                n_write += 1
            elif name == "Edit":
                r.edit(args.get("filepath"), args.get("old_str", ""),
                       args.get("new_str", ""), bool(args.get("replace_all")))
                n_edit += 1
            elif name == "MultiEdit":
                fp = args.get("filepath")
                for e in (args.get("edits") or []):
                    r.edit(fp, e.get("old_str", ""), e.get("new_str", ""),
                           bool(e.get("replace_all")))
                n_multi += 1
            elif name == "Bash":
                k = bash_key(args.get("command") or "")
                if k:
                    handlers[k]()
                    n_bash += 1

    os.makedirs(outdir, exist_ok=True)
    for fp, content in r.files.items():
        dest = os.path.join(outdir, fp)
        os.makedirs(os.path.dirname(dest) or outdir, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    print(f"replay: writes={n_write} edits={n_edit} multiedits={n_multi} "
          f"bash-mutations={n_bash} -> {len(r.files)} files")
    for line in r.log:
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
