#!/usr/bin/env python3
"""build_wave5_prompts.py — generate the wave-5 agents-tab worker prompts.

WO-012 (Workflow Distribution, Marketplace, Monetization) — depends on
WO-010 + WO-011 (workflow-triggers must be ON main before dispatch).
WO-014 (Learning and Governed Evolution) — depends on WO-010 + WO-013
(eval-compat must be ON main before dispatch).

Same proven template as wave-4. Guarded: skips a WO whose dependency crate
is not yet on main (the prompts embed the dependency surface verbatim).

Usage: build_wave5_prompts.py <repo-path> <base-sha>
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

SLUGS = {"WO-012": "workflow-distribution", "WO-014": "workflow-evolution"}
LIBS = {"WO-012": "codex_workflow_distribution", "WO-014": "codex_workflow_evolution"}

DESIGN = {
"WO-012": """DESIGN GUIDANCE (from the Tech Lead; verify against the live clone first)
- A NEW LEAF crate codex-rs/workflow-distribution (lib codex_workflow_distribution) plus one members line in codex-rs/Cargo.toml: the publication/distribution/licensing/marketplace plane OVER workflow-forge (publish/install/discovery) and workflow-triggers (installation/configuration bindings). Do NOT edit existing crates (workflow-app and below are merged surfaces — frozen dependencies).
- Distribution states as contract types over IMMUTABLE versions: Private, Shared, Public, Forked, Installed, Published — transitions through explicit ports (never event-sourced mutation of published meaning; a published version is sealed forever).
- Publication metadata: attribution, ownership, licensing (SPDX-style identifiers + custom terms), provenance (source lineage), compatibility (minimum runtime/capability requirements), and upgrade policy (pin vs follow) — a versioned, integrity-checkable metadata document bound to the immutable release (hash-chained to the version seal).
- A DistributionPort/MarketplacePort seam (ports/traits + in-memory implementations for tests): publish, list/search with filter facets, fetch by id+version, fork (new immutable version with provenance pointing back), install with license/access policy evaluation (reuse the workflow-triggers authorization port shape; do not duplicate authorization semantics — compose or reference them).
- Commercial entitlements as a SEPARATE boundary: an EntitlementPort with in-memory implementations expressing paid release / subscription / license-grant CHECKS ONLY (entitlement grants live in a host-owned store; NO payment processing, NO credentials, NO monetization logic in the workflow engine, NO payment semantics in workflow source or evidence). Denial of an entitlement must never change executable semantics — it gates distribution/installation only.
- Marketplace discovery: search/filter over published releases (by capability, capability-class, resource needs, license, provenance, compatibility) through the discovery port; results are metadata-only views of immutable versions.
- E2E tests (static): publish→immutable (tamper rejected), fork lineage provenance, license-gated install (deny + allow paths), entitlement boundary (entitlement denial never mutates semantics), upgrade policy (pin stays, follow advances with explicit approval), search/filter correctness, no-credentials-invariants.
""",
"WO-014": """DESIGN GUIDANCE (from the Tech Lead; verify against the live clone first)
- A NEW LEAF crate codex-rs/workflow-evolution (lib codex_workflow_evolution) plus one members line in codex-rs/Cargo.toml: the evidence-driven improvement + governed-evolution plane OVER eval-compat (replay/differential evaluation) and workflow-forge (version publication/lineage). Do NOT edit existing crates (workflow-app and below are merged surfaces — frozen dependencies).
- ImprovementCandidate as a contract type: a PROPOSED change (workflow definition delta, capability binding change, recovery-policy adjustment, dependency choice, schedule tuning) with full provenance (which evidence stream, which runs, which replay/simulation validated it) — generated ONLY from execution/evaluation evidence (read-only over evidence stores; never from live engine state, never from model suggestions treated as authorization).
- Candidate validation pipeline as ports: replay through eval-compat's deterministic harness, differential comparison (candidate vs incumbent normalized outcomes), policy checks (authorization, resource, compatibility) — each stage records evidence; a candidate is Promoted only when every gate passes EXPLICITLY.
- Governed evolution: an ApprovalPort (in-memory impl) requiring explicit human/policy approval; publication of a successor version goes through workflow-forge (new immutable version with lineage: predecessor, candidate provenance, validation evidence, approval record). The installed/published PREDECESSOR version is never mutated — ever.
- Rollback: an install/upgrade policy referencing lineage can pin or move between versions; rollback to a predecessor is an explicit governed transition (recorded, never silent).
- Retention: bounded, policy-driven retention of evidence and candidates; no unbounded retention of sensitive credentials or external content (credentials never enter evidence or candidates — enforce with a scrubbing/checking step).
- E2E tests (static): evidence→candidate provenance, replay-differential validation (a divergence fails the gate), approval required (no auto-promotion), immutable predecessor (mutation rejected), lineage/rollback transitions, retention bounds, no-credential invariant.
""",
}

IMPL = """IMPLEMENTATION (in order):
1. Audit the actual source first (source-first rule: never assume how Codex works). Map the dependency surfaces yourself from the clone: workflow-contracts (WO-003), workflow-forge (WO-009), workflow-app (WO-010), plus your direct dependencies from the wave-4/5 merges (workflow-triggers / eval-compat).
2. Smallest coherent implementation with real tests. Expected shape (verify against the real tree; adapt if it differs and say so): a new leaf crate as specified in DESIGN GUIDANCE, plus exactly one members line in codex-rs/Cargo.toml.
3. Scoped verification: `cargo test -p <your-crate>`; `cargo clippy -p <your-crate> --all-targets -- -D warnings`; `cargo fmt -p <your-crate> -- --check`. If cargo is unavailable, provide strongest-possible static verification instead and say so.
4. Commit on your branch (message in DESIGN GUIDANCE). Keep ALL files (including the full crate and tests) in the sandbox working tree — the Tech Lead harvests your workspace (the sandbox tar is the delivery channel). Keep the sandbox disk lean: run `rm -rf` on cargo target dirs once verification results are recorded (the source tree is what gets delivered).
5. DO NOT PUSH (no credentials; the Tech Lead applies, independently verifies, pushes, and merges).

DELIVERY NOTE: create a git bundle of exactly your commit as well:
`git bundle create /home/z/my-project/<wo>-delivery.bundle <base-sha>..<your-branch>` — the Tech Lead fetches the workspace archive; the bundle is the preferred delivery artifact.
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
    "WO-012": "Workflow Distribution, Marketplace, and Monetization",
    "WO-014": "Learning and Governed Evolution",
}

# dependency guard: the crate that must be on main before this WO dispatches
DEP_GUARDS = {
    "WO-012": "codex-rs/workflow-triggers/src/lib.rs",
    "WO-014": "codex-rs/eval-compat/src/lib.rs",
}

MANIFESTS = {
"WO-012": [
    ("codex-rs/workflow-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-forge/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-forge/src/install.rs", "sig"),
    ("codex-rs/workflow-forge/src/discovery.rs", "sig"),
    ("codex-rs/workflow-forge/src/canonical.rs", "sig"),
    ("codex-rs/workflow-triggers/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-triggers/src/install.rs", "sig"),
    ("codex-rs/workflow-triggers/src/discovery.rs", "sig"),
    ("codex-rs/workflow-triggers/src/configuration.rs", "sig"),
    ("codex-rs/workflow-triggers/src/port.rs", "sig"),
    ("codex-rs/workflow-app/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/port.rs", "sig"),
    ("codex-rs/execution-contracts/src/lib.rs", "sig"),
],
"WO-014": [
    ("codex-rs/workflow-contracts/src/lib.rs", "verbatim"),
    ("codex-rs/eval-compat/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-forge/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-forge/src/canonical.rs", "sig"),
    ("codex-rs/workflow-forge/src/install.rs", "sig"),
    ("codex-rs/workflow-forge/src/discovery.rs", "sig"),
    ("codex-rs/workflow-app/src/lib.rs", "verbatim"),
    ("codex-rs/workflow-app/src/port.rs", "sig"),
    ("codex-rs/workflow-app/src/run.rs", "sig"),
],
}

COMMIT_MSGS = {
    "WO-012": "feat(workflow-distribution): WO-012 distribution, marketplace, and commercial entitlements",
    "WO-014": "feat(workflow-evolution): WO-014 learning and governed evolution",
}


def build(wo, repo, base_sha):
    slug = SLUGS[wo]
    guard = DEP_GUARDS[wo]
    if read_file(repo, guard) is None:
        print(f"SKIP {wo}: dependency {guard} not on main yet (merge the dep WO first)")
        return 0
    packet = read_file(repo, f"docs/work-orders/{wo}.md")
    if not packet:
        print(f"ERROR: {wo} packet not found")
        return 1
    parts = []
    parts.append(f"You are {wo} Worker — an implementation specialist dispatched by the Tech Lead for payswapdotorg/codex. Work autonomously until the Work Order is implemented, tested, and fully reported. This full-stack agents-tab session is the AUTHORITATIVE work record for {wo}.\n\n")
    parts.append(f"ROLE\nImplement exactly {wo} ({WO_TITLES[wo]}). You are not the architect and may not invent product scope, architecture, semantic contracts, or parallel runtimes.\n\n")
    parts.append(env_section(wo, slug, base_sha))
    parts.append(BOOTSTRAP + "\n")
    parts.append(DESIGN[wo])
    parts.append(f" Commit message: `{COMMIT_MSGS[wo]}`.\n\n")
    parts.append(f"WORK ORDER PACKET — {wo} (verbatim):\n")
    parts.append(packet.strip() + "\n")
    parts.append(f"\n\nSOURCE BUNDLE @ base {base_sha[:16]} (FALLBACK ONLY — the live clone is authoritative):\n")
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
    parts.append(IMPL.replace("<wo>", wo.lower()).replace("<base-sha>", base_sha).replace("<your-branch>", f"wo-{wo.split('-')[1]}/{slug}"))
    parts.append(report_contract(wo))
    prompt = "".join(parts)
    out = os.path.join(PROMPTS, f"{wo}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"\nwrote {out}: {len(prompt)} chars (bundle {total})")
    return 0


def main():
    repo, base_sha = sys.argv[1], sys.argv[2]
    for wo in ("WO-012", "WO-014"):
        build(wo, repo, base_sha)


if __name__ == "__main__":
    sys.exit(main())
