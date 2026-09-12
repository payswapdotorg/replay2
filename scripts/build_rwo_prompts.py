#!/usr/bin/env python3
"""build_rwo_prompts.py — generate remediation worker prompts (RWO-*).

First remediation wave per VWO-010 spec: up to three independent workers.
  RWO-001 — mount the workflow/teaching control plane (P0, Family A root)
  RWO-002 — FlowMart configure JSON contract + reserved-key deny-list (P1 B)
  RWO-003 — FlowMart cross-tenant write guard (P1 E, security)
The RWO doc ON MAIN is the contract; the prompt points at it and adds the
standing environment/verification/report rules. Echo-safe: no filled SHAs.

Usage: build_rwo_prompts.py <repo-path> <base-sha> [rwo-001 rwo-002 ...]
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "worker-prompts")
os.makedirs(PROMPTS, exist_ok=True)

SLUGS = {
    "rwo-001": "mount-control-plane",
    "rwo-002": "flowmart-configure-contract",
    "rwo-003": "flowmart-org-guard",
    "rwo-004": "pressroom-publication-terminality",
    "rwo-007": "flowmart-downgrade-guard",
    "rwo-008": "entitlement-shadowing",
    "rwo-009": "upgrade-visibility-gate",
}

MISSION = {
"rwo-001": """YOUR WORK ORDER: RWO-001 — Mount the Workflow/Teaching Control Plane Behind
User-Facing Surfaces (P0, canonical Family A — the single root finding of the
entire validation program, 6 report confirmations). Read
docs/validation/work-orders/RWO-001.md IN THE CLONE — it is the CONTRACT
(objective, findings closed, reproduction evidence pointer, bounded fix
scope, acceptance criteria, verification commands, rollback, size estimate).
The Fix scope: additive protocol methods (app-server-protocol), app-server
handlers delegating to EXISTING engine ports, one CLI workflow subcommand
group. NO new engine semantics; frozen engine crates are untouched except
wiring (VALIDATION-PROGRAM.md §11). You may consult the engine crates as
libraries (read their ports) but must NOT edit them.""",
"rwo-002": """YOUR WORK ORDER: RWO-002 — FlowMart Configure Op: Parse Form JSON + Reject
Identity-Impersonating Keys (P1 Family B + P2/P3 rider Family L). Read
docs/validation/work-orders/RWO-002.md IN THE CLONE — it is the CONTRACT.
The Fix scope: docs/validation/fixtures/marketplace/ops-install.js
configureInstall (+ the install op's config intake, same pattern): JSON.parse
string config values (HTTP 400 invalid_json on parse failure — never a
silent {} success), reserved-key deny-list (version, digest, targetVersion,
manifest, packageId, expectedVersion, any __-prefixed key), FAILURES.md/README
contract documentation.""",
"rwo-003": """YOUR WORK ORDER: RWO-003 — FlowMart Cross-Tenant Write Guard (P1 Family E,
security: cross-tenant install writes incl. pin moves). Read
docs/validation/work-orders/RWO-003.md IN THE CLONE — it is the CONTRACT.
The Fix scope: docs/validation/fixtures/marketplace/ops-install.js — in
configureInstall (~line 100), upgradeInstall (~117), rollbackInstall (~156):
after resolving the install, verify the actor's org matches the install's
org, else HTTP 403 permission_denied naming the install, its org, and the
denied action (the RWO doc carries the exact code sketch).""",
}

VERIF = {
"rwo-001": """VERIFICATION (exact commands + results in your report):
- cargo test -p codex-app-server-protocol -p codex-app-server -p codex-cli
- cargo test -p codex-workflow-app -p codex-workflow-durable -p codex-teaching-compiler
- cargo clippy --workspace --all-targets -- -D warnings  (your crates at minimum; workspace if time allows)
- cargo fmt -p <your crates> -- --check
- Re-run the VWO-010 mount probe and INVERT it: rg -c 'workflow' codex-rs/app-server-protocol/src/
  must now be > 0 (the absence probe must FAIL to find absence).
- If cargo is unavailable in your sandbox, say so explicitly, verify by
  careful static reasoning + the merge-order contract, and the Tech Lead
  independently compiles and runs everything.
""",
"rwo-002": """VERIFICATION (exact commands + results in your report):
- bash docs/validation/fixtures/run-all.sh --reset (five apps healthy)
- bash docs/validation/fixtures/verify-sweep.sh (59/59 must stay green)
- Reproduce the VWO-010 Family B evidence flow, then verify the FIX:
  valid JSON via the browser-path equivalent (curl against the fixture API
  with the same form semantics) persists keys; invalid JSON gets 400
  invalid_json; reserved keys get 400 reserved_config_key; no silent {}
  success; history entries name the keys.
- Update FAILURES.md/README; cite the evidence file you wrote.
""",
"rwo-003": """VERIFICATION (exact commands + results in your report):
- bash docs/validation/fixtures/run-all.sh --reset; bash docs/validation/fixtures/verify-sweep.sh (59/59 green)
- Re-run the VWO-010 Family E reproduction (petra.voss/Acme cross-tenant
  configure/upgrade/rollback on Northwind's ins-0402) — every write must now
  403 permission_denied naming install + org + action; same-org operations
  still succeed; reads remain org-scoped and unaffected.
""",
}

EVIDENCE = """EVIDENCE (docs/validation/evidence/{name}/, canonical layout):
- post-hoc/: the before/after reproduction transcript (the failing call at
  base, the fixed call on your branch — same request, contrasting results),
  plus each acceptance criterion's verification transcript.
- _infra/: environment identity (base SHA verified, toolchain versions).
- Every claim in your report cites an evidence file. No credentials in any
  evidence file (defang: <redacted>, fake values only).
"""


def build(name, base_sha):
    wo = name.upper()
    slug = SLUGS[name]
    prompt = f"""WORK ORDER: {wo} — Remediation Implementation Specialist
ROLE: You implement ONE bounded remediation work order end-to-end: read its
contract, implement the fix exactly as scoped, verify with the named
commands, capture evidence, commit on your branch, and report honestly.
Source-first: read the actual tree before writing a line. The RWO doc on
main WINS over this prompt if they disagree — say so in your deviations.

ENVIRONMENT (sandbox — you have a shell, git, and network):
1. `git clone https://github.com/payswapdotorg/codex` (public, anonymous).
   Verify the exact base: `git rev-parse {base_sha}^{{commit}}` — main's head
   as of dispatch (VWO-010 synthesis merged). If unreachable, base on
   origin/main HEAD and RECORD the exact SHA you based on.
2. `cd codex && git checkout -b {name}/{slug}` on that base.
3. Check `which cargo` (Rust work) / `which node` (fixture work). If a
   toolchain exists, build/test for REAL and include exact results. If not,
   verify by careful static reasoning and say so explicitly; the Tech Lead
   independently compiles and runs everything.

{MISSION[name]}
IMPLEMENTATION (in order):
1. Read the RWO doc + its cited reproduction evidence + the owning files.
2. Implement the Fix scope EXACTLY as the doc bounds it. Anything beyond
   the scope: STOP and record it as a question in your report instead.
3. Run the RWO's Verification commands; capture exact results.
4. Keep ALL files in the sandbox working tree (the Tech Lead harvests your
   workspace; the sandbox tar is the delivery channel). Keep the sandbox
   disk lean: rm -rf cargo target dirs once verification results are
   recorded.
5. DO NOT PUSH (no credentials; the Tech Lead independently verifies,
   pushes, and merges).

{VERIF[name]}
{EVIDENCE}
RULES (non-negotiable):
- Bounded scope: only the RWO's Fix scope; no drive-by fixes; frozen engine
  crates (codex-workflow-*, codex-execution-contracts) are NEVER edited
  without the RWO saying so.
- No fabrication: every verification result is a real command's output.
- Honest deviations: list every deviation from the RWO contract.
- No credentials in evidence; no contract mutation (the RWO doc itself,
  the six validation reports, and REPORT-SCHEMA stay byte-identical).

FINAL MESSAGE (exact format, as your last chat message):
=== {wo} COMPLETION REPORT ===
- Work Order ID: {wo}
- base branch + base SHA: main @ <exact SHA you based on>
- head SHA (your branch, after your commit):
- changed files/surfaces:
- implementation summary:
- verification commands and exact results:
- acceptance-criteria evidence (map each RWO acceptance criterion to its
  verification transcript):
- rollback note:
- known limitations / honest deviations:
=== END {wo} COMPLETION REPORT ===

DELIVERY NOTE: also create a git bundle of exactly your commit:
`git bundle create /home/z/my-project/{wo}-delivery.bundle {base_sha}..{name}/{slug}`
"""
    out = os.path.join(PROMPTS, f"{wo}.md")
    with open(out, "w") as f:
        f.write(prompt)
    print(f"wrote {out} ({len(prompt)} chars)")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    repo, sha = sys.argv[1], sys.argv[2]
    assert len(sha) in (7, 40) and all(c in "0123456789abcdef" for c in sha)
    names = sys.argv[3:] or ["rwo-001", "rwo-002", "rwo-003"]
    for n in names:
        assert n in SLUGS and n in MISSION, f"unknown RWO {n}"
        build(n, sha)
    print("echo-safety: base SHA embedded as the dispatch-time literal; "
          "report markers are template forms only — OK")


if __name__ == "__main__":
    main()
