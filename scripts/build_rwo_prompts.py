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
"rwo-004": """YOUR WORK ORDER: RWO-004 — PressRoom: Server-Side Publication Terminality
+ Publish Version Guard (P1 Family F — security/trust boundary). Read
docs/validation/work-orders/RWO-004.md IN THE CLONE — it is the CONTRACT.
The Fix scope: docs/validation/fixtures/media/ops.js — (1) editStory (~46):
after the permission check add a status gate (edit allowed only for
draft/in_review/approved; published/corrected → HTTP 409 terminal_state
pointing to the correction path); (2) publishStory (~159): REQUIRE
expectedVersion (HTTP 400 expected_version_required when absent) and call
the existing checkVersion helper — stale version → 409 data_conflict
(reload and re-review); editor/publish form passes the approved version.
UI-only guards stay; the API twin must now match them.""",
"rwo-007": """YOUR WORK ORDER: RWO-007 — FlowMart: Upgrade Means Forward (P1 Family G
product half + P2 rider Family M — ordering + rollback direction). Read
docs/validation/work-orders/RWO-007.md IN THE CLONE — it is the CONTRACT.
The Fix scope: docs/validation/fixtures/marketplace/ops-install.js —
(1) upgradeInstall (~117): semver-ordering comparison targetVersion vs
inst.version — older target → HTTP 409 implicit_downgrade_refused (smallest
fix: refuse, tell the user to use rollback); (2) rollbackInstall (~156):
derive the rollback target from the most recent 'upgraded' history entry's
fromVersion (never 'any toVersion differing from current' — no forward
'rollbacks'); (3) FAILURES.md documents both contracts. The engine half of
Family G is RWO-009's — do NOT touch engine crates.""",
"rwo-008": """YOUR WORK ORDER: RWO-008 — FlowMart Entitlement: Renewal Must Restore
Authority (P1 Family H — entitlement shadowing). Read
docs/validation/work-orders/RWO-008.md IN THE CLONE — it is the CONTRACT.
The Fix scope: docs/validation/fixtures/marketplace/ops-install.js —
(1) entitlementFor (~11): replace first-match with newest-ACTIVE resolution
(active && not past validUntil; latest grantedAt, tie-break highest id;
no active but revoked/expired exist → resolve the most-recent such record
so fail-closed errors name the newest relevant entitlement); (2)
grantEntitlement (~217): document the newest-active selection (smallest
fix — no superseded status needed); (3) FAILURES.md/README: revocation is
terminal per record, recovery is a new grant.""",
"rwo-009": """YOUR WORK ORDER: RWO-009 — Engine Distribution: Visibility Gate on the
Upgrade Path + Ordering Guard Rider (P1 Family I + Family G engine half).
Read docs/validation/work-orders/RWO-009.md IN THE CLONE — it is the
CONTRACT. The Fix scope: codex-rs/workflow-distribution/src/memory.rs (+
unit tests in the crate) — (1) evaluate_upgrade (~435): filter candidates
through the SAME visibility predicate install uses (release_installable —
private releases invisible to foreign installers); (2) decide_upgrade
(~464): re-run the visibility gate on the target before approval
(documented order: visibility → integrity → access → entitlement);
(3) ordering guard: reject upgrade proposals whose 'to' version is older
than 'from' with a typed error (IllegalDowngrade { expected_newer_than,
got } — smallest fix: refuse). Engine crate IS yours in this RWO (unlike
rwo-001); all other engine crates remain frozen.""",
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
"rwo-004": """VERIFICATION (exact commands + results in your report):
- bash docs/validation/fixtures/run-all.sh --reset; bash docs/validation/fixtures/verify-sweep.sh (59/59)
- Re-run both VWO-010 Family F attacks → expect 409 terminal_state (author
  edit on published story) and the version guards (400 expected_version_required
  when expectedVersion absent; 409 data_conflict when stale).
- Re-run the normal editorial path (create → attach → submit → approve →
  publish → correct) → ok; correction path unchanged.
""",
"rwo-007": """VERIFICATION (exact commands + results in your report):
- bash docs/validation/fixtures/run-all.sh --reset; bash docs/validation/fixtures/verify-sweep.sh (59/59)
- Re-run the VWO-010 battery sections A2/B → upgrade with older target →
  409 implicit_downgrade_refused (pin/history/events unchanged); after a
  legit 1.2.0 → 1.3.0 upgrade, rollback → 1.2.0 (the fromVersion — never
  forward).
- Duplicate-version and stale-pin paths (VWO-005/006) still pass; re-run
  the upgrade-rollback user path → ok.
""",
"rwo-008": """VERIFICATION (exact commands + results in your report):
- bash docs/validation/fixtures/run-all.sh --reset; bash docs/validation/fixtures/verify-sweep.sh (59/59)
- Re-run the VWO-010 C-restart battery: revoke ent-0501 → blocked naming the
  revoked record; grant fresh active entitlement (ent-0504-style, valid 2027)
  → the SAME previously blocked operation now succeeds on retry;
  expired-only state still blocks naming the expired record; auto-trial
  install path (no entitlement) unchanged.
""",
"rwo-009": """VERIFICATION (exact commands + results in your report):
- cargo test -p codex-workflow-distribution
- cargo clippy -p codex-workflow-distribution --all-targets -- -D warnings
- Re-run the VWO-009 standalone probe battery attacks 5b/6d/12 → expect
  REFUSED (foreign installer evaluate_upgrade returns None/not-visible;
  decide_upgrade on a smuggled proposal → ReleaseNotVisible; older-target
  upgrade record → typed IllegalDowngrade error; pin unchanged in each).
- All existing distribution tests still pass (search/install visibility,
  gate order, stale-proposal, AlreadyInstalled).
- If cargo is unavailable in your sandbox, say so explicitly, verify by
  careful static reasoning + the cited line-level findings, and the Tech
  Lead independently compiles and runs everything.
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
