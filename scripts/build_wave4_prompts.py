#!/usr/bin/env python3
"""build_wave4_prompts.py — generate the wave-4 agents-tab worker prompts.

WO-011 (Scheduling/Triggers/Sharing/Installation), WO-013 (Evaluation and
Differential Compatibility), WO-015 (Additional Execution Environments) —
all unblocked by the WO-010 merge (main @ 67c0460).

Follows the PROVEN WO-010.md template: agents-tab session (shell+git+network),
verbatim work-order packet, source bundle (verbatim boundary-critical files +
signatures for the rest), implementation order, and the exact English
completion-report contract (queue_watch detects the bilingual variant too).

Usage: build_wave4_prompts.py <repo-path> <base-sha>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_prompt import read_file, rust_signatures

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "worker-prompts")

BOOTSTRAP = """BOOTSTRAP (read in the repo, in order):
1. ARCHITECT_START_HERE.md  2. AGENTS.md (follow its formatting/lint rules)  3. docs/architecture/CODEX-UNIVERSAL-ARCHITECTURE.md  4. docs/architecture/CODEX-UNIVERSAL-LOCK.md  5. docs/architecture/CODEX-CAPABILITY-IMPLEMENTATION-MAP.md  6. docs/implementation-roadmap.md  7. docs/development-state/dependency-graph.json  8. This Work Order packet below.
"""

SLUGS = {"WO-011": "workflow-triggers", "WO-013": "eval-compat", "WO-015": "env-adapters"}

DESIGN = {
"WO-011": """DESIGN GUIDANCE (from the Tech Lead; verify against the live clone first)
- A NEW LEAF crate codex-rs/workflow-triggers (lib codex_workflow_triggers) plus one members line in codex-rs/Cargo.toml: the trigger/scheduling/installation plane OVER the WO-010 workflow-app ports. Do NOT edit the existing crates (workflow-app and below are merged surfaces — treat them as frozen dependencies).
- Trigger classes as contract types: USER, SCHEDULE, WEBHOOK, CONNECTOR_EVENT, BROWSER_EVENT, COMPUTER_EVENT, WORKFLOW_EVENT, HUMAN_EVENT — each with an idempotency key (dedupe through the control-plane seam, never event-sourced mutation of workflow meaning).
- A TriggerPort/Registry seam (ports/traits + in-memory impls for tests): evaluate capability/resource/policy readiness BEFORE execution eligibility; durable idempotent handling (same trigger fired twice => one instance transition, second is a recorded no-op).
- Installation/configuration: install an immutable workflow version with EXPLICIT dependency + resource bindings (reuse the workflow-forge install semantics + workflow-app lifecycle ports); rebinding a resource/account must NOT touch the immutable semantic source.
- Sharing/discovery: reuse existing connector/plugin/skill discovery + authorization mechanisms where they exist; model what is missing as ports with in-memory test implementations.
- E2E tests (static): trigger idempotency (double-fire), scheduling eligibility (readiness gating), install/bind diagnostics, authorization checks, version integrity (tampered/sealed), rebinding without source change.""",
"WO-013": """DESIGN GUIDANCE (from the Tech Lead; verify against the live clone first)
- A NEW LEAF crate codex-rs/eval-compat (lib codex_eval_compat) plus one members line in codex-rs/Cargo.toml: the evaluation + differential-compatibility plane. Do NOT edit existing crates (model-provider, workflow-app and below are merged surfaces — frozen dependencies).
- Reproducible evaluation harness: run a fixed workflow (or model-interaction script) through the WO-002 universal model contract AND the WO-010 workflow-app runtime with DETERMINISTIC simulated adapters/providers; record per-run evidence (inputs, outputs, hashes) so runs are replayable and comparable.
- Differential tests: same workflow + same scripted environment, varying model/provider selections (through the provider contract) => assert SEMANTIC equivalence classes (normalized outcomes), surfacing divergences as evidence, never as silent failure.
- Compatibility suite: a regression harness that pins ordinary-Codex and upstream-Codex observable behavior (CLI/app-server unaffected surfaces) — differential snapshots that fail loudly when a future change shifts compatibility.
- Report format: evidence-driven (per-case verdicts + hashes); NO mutation of any installed/published workflow version; evaluation runs read-only over immutable versions.
- E2E tests (static): deterministic replay, differential divergence detection (injected simulated divergence must be caught), compatibility snapshot stability, read-only guarantees.""",
"WO-015": """DESIGN GUIDANCE (from the Tech Lead; verify against the live clone first)
- A NEW LEAF crate codex-rs/env-adapters (lib codex_env_adapters) plus one members line in codex-rs/Cargo.toml: additional execution-environment adapters OVER the WO-005 execution-contracts EnvironmentAdapter seam — following exactly the shape proven by browser-use-adapter (WO-006) and computer-use-adapter (WO-007). Do NOT edit existing crates.
- Implement at least two new environment classes, e.g. remote-desktop (RDP/VNC-style host-bridged sessions) and mobile (device bridge) — each as an EnvironmentAdapter implementation with capability descriptors, resource bindings, policy gating, health/liveness probes, and failure/recovery records. Real host bridges are OUT of scope (host provides them, as in WO-006/007): model the bridge as a port with scripted in-memory implementations for tests.
- Registration: adapters register into the capability/resource readiness registry (execution-contracts) exactly like the existing adapters; mixed-environment runs (browser/computer/remote/mobile) must compose through the SAME workflow-app run paths with no environment-specific orchestration branches.
- Policy: every adapter action passes the native policy/sandbox gates (no bypasses); evidence and approval flows identical to existing adapters.
- E2E tests (static): adapter readiness/registration, policy denial paths, mixed-environment run through workflow-app ports with a new-class adapter bound, recovery on bridge loss, no-op when no workflow is active.""",
}

IMPL = """IMPLEMENTATION (in order):
1. Audit the actual source first (source-first rule: never assume how Codex works). Map the dependency surfaces yourself from the clone: workflow-contracts (WO-003), execution-contracts (WO-005), browser-use-adapter (WO-006), computer-use-adapter (WO-007), teaching-compiler (WO-008), workflow-forge (WO-009), workflow-app (WO-010 — ports/lifecycle/run are the integration seams).
2. Smallest coherent implementation with real tests. Expected shape (verify against the real tree; adapt if it differs and say so): a new leaf crate as specified in DESIGN GUIDANCE, plus exactly one members line in codex-rs/Cargo.toml.
3. Scoped verification: `cargo test -p <your-crate>`; `cargo clippy -p <your-crate> --all-targets -- -D warnings`; `cargo fmt -p <your-crate> -- --check`. If cargo is unavailable, provide strongest-possible static verification instead and say so.
4. Commit on your branch (message in DESIGN GUIDANCE). Keep ALL files (including the full crate and tests) in the sandbox working tree — the Tech Lead harvests your workspace (the sandbox tar is the delivery channel). Keep the sandbox disk lean: run `rm -rf` on cargo target dirs once verification results are recorded (the source tree is what gets delivered).
5. DO NOT PUSH (no credentials; the Tech Lead applies, independently verifies, pushes, and merges).
"""


def env_section(wo, slug, base_sha):
    return f"""ENVIRONMENT (sandbox — you have a shell, git, and network):
1. `git clone https://github.com/payswapdotorg/codex` (public, anonymous). Verify the exact base: `git rev-parse {base_sha}^{{commit}}` — main's head as of dispatch. If that commit is unreachable, base on origin/main HEAD and RECORD the exact SHA you based on.
2. `cd codex && git checkout -b wo-{wo.split('-')[1]}/{slug}` on that base.
3. Check `which cargo` — if a Rust toolchain exists, build/test/clippy/fmt for REAL and include exact results. If not, verify compile-correctness by careful static reasoning and say so explicitly; the Tech Lead independently compiles and runs everything.
4. The SOURCE BUNDLE at the end of this prompt is a FALLBACK ONLY (for the no-network case). When the clone succeeds, reconcile EVERYTHING against the live tree — never report from the bundle alone. If bundle and clone disagree, THE CLONE WINS and you must say so.

"""


def report_contract(wo):
    n = wo.split("-")[1]
    return f"""FINAL MESSAGE (exact format, as your last chat message):
=== {wo} COMPLETION REPORT ===
- Work Order ID: {wo}
- base branch + base SHA: main @ <exact SHA you based on>
- head SHA (your branch, after your commit):
- changed files/surfaces:
- implementation summary:
- tests/commands and exact results (or static-verification statement):
- acceptance-criteria evidence (map each bullet to code + tests):
- compatibility impact (especially: ordinary Codex behavior untouched when no workflow is active):
- known limitations:
- deferred items + owning WO:
- risks:
"""

WO_TITLES = {
    "WO-011": "Scheduling, Triggers, Sharing, and Installation",
    "WO-013": "Evaluation and Differential Compatibility",
    "WO-015": "Additional Execution Environments",
}

MANIFESTS = {
"WO-011": [
    ("codex-rs/workflow-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/execution-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/port.rs", "verbatim"),
    ("codex-rs/workflow-app/src/lifecycle.rs", "sig"),
    ("codex-rs/workflow-app/src/run.rs", "sig"),
    ("codex-rs/workflow-app/src/memory.rs", "sig"),
    ("codex-rs/workflow-app/src/event.rs", "sig"),
    ("codex-rs/workflow-forge/src/lib.rs", "sig"),
    ("codex-rs/workflow-forge/src/install.rs", "sig"),
    ("codex-rs/workflow-forge/src/discovery.rs", "sig"),
    ("codex-rs/workflow-forge/src/canonical.rs", "sig"),
    ("codex-rs/teaching-compiler/src/lib.rs", "verbatim"),
    ("codex-rs/browser-use-adapter/src/lib.rs", "sig"),
    ("codex-rs/computer-use-adapter/src/lib.rs", "sig"),
],
"WO-013": [
    ("codex-rs/model-provider/src/lib.rs", "verbatim"),
    ("codex-rs/model-provider/src/provider.rs", "sig"),
    ("codex-rs/model-provider/src/selection.rs", "sig"),
    ("codex-rs/workflow-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/execution-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/port.rs", "sig"),
    ("codex-rs/workflow-app/src/run.rs", "sig"),
    ("codex-rs/workflow-app/src/memory.rs", "sig"),
    ("codex-rs/workflow-forge/src/lib.rs", "sig"),
],
"WO-015": [
    ("codex-rs/execution-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/browser-use-adapter/src/lib.rs", "verbatim"),
    ("codex-rs/computer-use-adapter/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-contracts/src/lib.rs", "sig"),
    ("codex-rs/workflow-app/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/port.rs", "sig"),
    ("codex-rs/workflow-app/src/browser_env.rs", "sig"),
    ("codex-rs/workflow-app/src/computer_env.rs", "sig"),
    ("codex-rs/teaching-compiler/src/lib.rs", "sig"),
],
}

COMMIT_MSGS = {
    "WO-011": "feat(workflow-triggers): WO-011 scheduling, triggers, sharing, and installation",
    "WO-013": "feat(eval-compat): WO-013 evaluation and differential compatibility",
    "WO-015": "feat(env-adapters): WO-015 additional execution environments",
}


def build(wo, repo, base_sha):
    slug = SLUGS[wo]
    packet = read_file(repo, f"docs/work-orders/{wo}.md")
    if not packet:
        print(f"ERROR: {wo} packet not found")
        return 1
    parts = []
    parts.append(f"You are {wo} Worker — an implementation specialist dispatched by the Tech Lead for payswapdotorg/codex. Work autonomously until the Work Order is implemented, tested, and fully reported. This full-stack agents-tab session is the AUTHORITATIVE work record for {wo}.\n\n")
    parts.append(f"ROLE\nImplement exactly {wo} ({WO_TITLES[wo]}). You are not the architect and may not invent product scope, architecture, semantic contracts, or parallel runtimes.\n\n")
    parts.append(env_section(wo, slug, base_sha))
    parts.append(BOOTSTRAP + "\n")
    parts.append(DESIGN[wo].replace("<your-crate>", f"codex-{slug.replace('-', '_')}" if False else ("codex-workflow-triggers" if wo == "WO-011" else "codex-eval-compat" if wo == "WO-013" else "codex-env-adapters")))
    parts.append(f" Commit message: `{COMMIT_MSGS[wo]}`.\n\n")
    parts.append(f"WORK ORDER PACKET — {wo} (verbatim):\n")
    parts.append(packet.strip() + "\n")
    parts.append(f"\n\nSOURCE BUNDLE @ base {base_sha[:16]} (FALLBACK ONLY — the live clone is authoritative; workflow-app is now on main):\n")
    total = 0
    for rel, mode in MANIFESTS[wo]:
        src = read_file(repo, rel)
        if src is None:
            print(f"  WARN: {rel} missing — skipped")
            continue
        if mode == "verbatim":
            body, tag = src, "verbatim"
        else:
            body, tag = rust_signatures(src), "signatures only"
        total += len(body)
        parts.append(f"\n--- {rel} ({tag}) ---\n\n```rust\n{body.strip()}\n```\n")
        print(f"  {rel}: {tag}, {len(body)} chars")
    parts.append(IMPL)
    parts.append(report_contract(wo))
    prompt = "".join(parts)
    out = os.path.join(PROMPTS, f"{wo}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"\nwrote {out}: {len(prompt)} chars (bundle {total})")
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    repo, sha = sys.argv[1], sys.argv[2]
    rc = 0
    for wo in ("WO-011", "WO-013", "WO-015"):
        print(f"=== {wo} ===")
        rc |= build(wo, repo, sha)
    return rc


if __name__ == "__main__":
    sys.exit(main())
