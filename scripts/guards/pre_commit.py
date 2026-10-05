#!/usr/bin/env python3
"""pre_commit.py — §0 anti-contamination + secret-leak guard (pre-commit hook).

OPERATOR DIRECTIVE (2026-10-05, binding): this repository is GENERIC
remote-browser-control infrastructure. Future agents using the replay to
dispatch workers for THEIR OWN projects must never contaminate it with
project-specific content — roadmaps, work orders, wave packets, mission
states, "durable masters", project scripts — and must never commit secrets.
.gitignore is NOT enforcement (git add -f walks straight past it — proven
by the 2026-10-02 fleetos-packets incident); this hook is the enforcement
layer. deploy.sh installs it into .git/hooks/pre-commit idempotently, so
every fresh clone gets it on first deploy.

What it blocks (STAGED files, added/copied/modified/renamed):
  - known contamination directories (scripts/prompts/, scripts/worker-prompts/,
    scripts/worker-reports/, scripts/missions/, scripts/roadmaps/,
    scripts/local/, scripts/harvests/, scripts/evidence/, scripts/drills/,
    scripts/gates/, scripts/replay-campaign/, scripts/prompts-template/,
    scripts/flauz-surface/, .data/, browser-profile/ anywhere);
  - data/ except *.example.* templates (deployment-local mission state);
  - filenames carrying contamination tokens (roadmap, work-order/work_order/
    workorder, mission-state, durable-master, wave-packet) except templates;
  - secrets: env.sh, .env*, *.env, credentials*, *pat*, *token*, *secret*,
    browser-profile content.

Where project content belongs instead: the operator-designated PROJECT repo,
or per-deployment LOCAL paths (data/, scripts/local/, scripts/worker-prompts/
— all gitignored on purpose). See AGENT_BOOT_PROMPT.md §0.

Maintainer bypass: git commit --no-verify — ONLY after explicit operator
authorization for a change that has been checked against §0 by hand.

The hook is deliberately a guard-rail, not crypto-enforcement: patterns
catch the known vectors; §0 judgment stays primary. Keep this file's
patterns in sync with .gitignore's governance block.
"""
import re
import subprocess
import sys

DENY_PREFIXES = (
    "scripts/prompts/",
    "scripts/worker-prompts/",
    "scripts/worker-reports/",
    "scripts/missions/",
    "scripts/roadmaps/",
    "scripts/local/",
    "scripts/harvests/",
    "scripts/evidence/",
    "scripts/drills/",
    "scripts/gates/",
    "scripts/replay-campaign/",
    "scripts/prompts-template/",
    "scripts/flauz-surface/",
    ".data/",
    "browser-profile/",
)
DENY_DATA_PREFIX = "data/"
DENY_NAME_TOKENS = (
    "roadmap",
    "work-order",
    "work_order",
    "workorder",
    "mission-state",
    "durable-master",
    "wave-packet",
)
SECRET_NAME_RE = re.compile(
    r"(^|/)(env\.sh|\.env(\..*)?|.*\.env|credentials(\..*)?|.*_pat\..*|github_pat.*|"
    r".*pat\.txt|.*token.*|.*secret.*)$",
    re.IGNORECASE,
)

MSG_HEAD = """
================ §0 ANTI-CONTAMINATION GUARD: COMMIT BLOCKED ================
This repository (payswapdotorg/replay2) is GENERIC infrastructure. It must
never carry project-specific content or secrets (AGENT_BOOT_PROMPT.md §0,
operator directives 2026-09-29 / 2026-10-02 / 2026-10-05).
"""


def is_template(path):
    return ".example." in path or path.endswith(".example")


def violations(paths):
    bad = []
    for p in paths:
        low = p.lower()
        base = low.rsplit("/", 1)[-1]
        if any(low.startswith(pre) for pre in DENY_PREFIXES):
            bad.append((p, "contamination directory (project-local by design)"))
            continue
        if low.startswith(DENY_DATA_PREFIX) and not is_template(p):
            bad.append((p, "deployment-local data/ (mission state etc.)"))
            continue
        if not is_template(p) and any(tok in base for tok in DENY_NAME_TOKENS):
            bad.append((p, "project-content filename token"))
            continue
        if "browser-profile" in low:
            bad.append((p, "browser profile content"))
            continue
        if SECRET_NAME_RE.match(low):
            bad.append((p, "possible secret/credential material"))
            continue
    return bad


def main():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    paths = [p for p in out.split("\0") if p]
    if not paths:
        return 0
    bad = violations(paths)
    if not bad:
        return 0
    print(MSG_HEAD, file=sys.stderr)
    for p, why in bad:
        print(f"  BLOCKED: {p}\n           ({why})", file=sys.stderr)
    print(
        "\nProject content belongs in YOUR project's own repo, or in the\n"
        "per-deployment LOCAL paths (data/, scripts/local/, scripts/worker-prompts/\n"
        "— gitignored on purpose). Secrets never belong in git at all.\n"
        "Maintainer bypass (operator-authorized changes only): git commit --no-verify\n"
        "============================================================================",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
