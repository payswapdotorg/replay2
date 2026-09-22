
### Repository archaeology required?

NONE. Every step above was driven by the repository's own front-door
documentation: the one command and its phase banners (EVALUATOR-GUIDE.md §2),
the local runtime legs (§3A), the failure-fix command for the foreign
DATABASE_URL (§2 note + §5 row), the idempotency policy (§2 "skipped when"
table), the teardown flags (§2) and the install reference underneath it all
(docs/INSTALL.md). No source file was opened to make the demo work; the only
files read were the two documents the bootstrap itself prints.
