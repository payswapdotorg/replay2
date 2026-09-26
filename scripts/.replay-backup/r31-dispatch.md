R31: THE GAP WAVE — the theme-picker submenu + the subscriptions-feed grid, built against the captured gap corpus

ROLE: You are the R31 worker on the WebFlix repo (github.com/payswapdotorg/webflix). ONE lane: wfx/r31/gaps. Your job: build exactly TWO corpus-pending surfaces — now captured — and NOTHING else.

STEP ZERO (mandatory, before any design thought):
1. Clone the repo, checkout main @ 54e0e4f (the R31 gap-corpus merge — the battery floor 5165/1/0 lives here; the R30-B account-chrome family is merged: AccountMenu, MastheadBell, RailSubscriptions, the playlist family are all live).
2. Create branch wfx/r31/gaps from main. The binding grammar is docs/parity-lab/r30/gap-captures/20260926-052954/GAP-CORPUS.md (+ the raw .json/.jpg/.html captures in the same directory, + g1-targeted-2.json the picker attempt of record). READ GAP-CORPUS.md FULLY and the two prior corpus docs (docs/parity-lab/r30/lead-captures/CORPUS.md — the account-menu grammar your picker joins; docs/parity-lab/r29/... the account-menu family's origin) before writing a line of code.
3. Survey WebFlix's CURRENT seams you will join: components/shell/AccountMenu.tsx (the "Appearance: <state>" row — R30-B built it state-bearing with NO picker; your picker opens behind this row), the theme seam (the stored theme truth — "Device theme" with no stored choice, Dark/Light when persisted — WebFlix's own boot law, already implemented), and the subscriptions truth (the R30-A LibraryEngine.hydrate seam — the stored Subscriptions the rail and Library render; your grid reads the SAME stored truth, never a new source).

THE FROZEN LAWS (violating any = the work is void):
- NEVER BUILD FROM MEMORY. Every surface you ship cites its GAP-CORPUS.md line (§G1/§G2) in the code comment AND the completion report. Where WebFlix's real model has no analogous datum, you record an honest divergence row — never fabricate parity.
- THE TWO GAPS STAY PENDING: (a) the home-surface resume bar (the account's home renders zero progress bars — nothing captured to bind), (b) the shorts action rail (the risk-engine gate blocks the player itself — three consistent records; WebFlix's own shorts surface stays untouched). You do NOT build these.
- THE SEAM LAW: no redesign of the account menu, masthead, rail, or Library. The picker joins the existing Appearance row; the grid joins the existing subscriptions truth. Minimal honest seams.
- ESCALATIONS: code outside apps/web/** only where the root demands it; every escalation is the minimal seam and is listed in the report.

THE BUILD (exactly two surfaces):

1. §G1 THE THEME-PICKER SUBMENU (behind the existing Appearance row):
   - The captured grammar (GAP-CORPUS.md §G1; g1-2-theme-picker.jpg VLM-verified + .html): a submenu panel with header "Appearance" + a BACK ARROW icon (left), subtext "Setting applies to this browser only", exactly 3 option rows in order: "Use device theme", "Dark theme", "Light theme".
   - Row geometry: 300x40 per row, stacked at a 40px vertical pitch; the panel is a sub-page of the account menu (opens on the Appearance row activation; the back arrow returns to the main menu).
   - The SELECTED state: the row matching the theme seam's stored truth carries a CHECKMARK ICON INSIDE A BOX to its left (a check-in-box, NOT a radio dot — the corpus's explicit finding). No stored choice = "Use device theme" selected (the captured state); "Dark theme"/"Light theme" when persisted.
   - Selecting a row writes through the REAL theme seam (the same stored truth the R30-B account-menu state row reads — selecting Dark persists, the menu row's state label updates on return; the subtext's truth: the setting applies to this browser — WebFlix's own persistence scope, honestly).
   - The signed-out shell and the closed-menu state stay byte-identical to R30-B's verified chrome (pin the control).

2. §G2 THE SUBSCRIPTIONS-FEED GRID (the healthy state):
   - The captured grammar (GAP-CORPUS.md §G2; g2-subs-feed.json/.jpg — 14 real cards): the two-column browse grid (grid bar x=72 y=56 w=1352 in the 1440 viewport — the corpus-measured geometry), subscription cards with title, channel name, meta line (channel · views · age), thumbnail.
   - The data truth: WebFlix's REAL stored Subscriptions (the LibraryEngine seam — the same truth the rail's Subscriptions section and the Library list render). The grid lists the subscribed items' content through the real connector read; UNJOINED items render honestly (the established UNLINKED law), never fabricated.
   - The destination: the subscriptions feed joins WebFlix's real navigation the way its other feed surfaces do (the corpus taxonomy's Subscriptions entry — the rail's Subscriptions section already points at the real destination per R30-B; your grid IS that destination's content surface, bound to the same route law the rail's rows follow).
   - The degraded live-only state (R30 lead-captures raw/07) remains an honest state class: when the connector truth is live-only, the grid renders that state honestly (the R30-B divergence-ledger law).
   - Empty state: no subscriptions stored = the honest empty state (the capability row's own vocabulary — never fabricated cards).

GATES (all must pass, in order, on your lane head):
- The full battery: `bun test` — 5165/1/0 floor + your new tests, ZERO regressions (the R11 webtorrent env skip = the honest 1).
- lint lane-clean (repo-wide pre-existing debt is NOT yours), typecheck, contract-check, lane-check (no cross-lane private imports), parity-conformance 19/19, build --filter web.
- Evidence: evidence/r31/ — the corpus-citation table (surface -> GAP-CORPUS.md section -> code seam), per-surface proof captures, guards.md (every gate's output), and the divergence ledger (WebFlix-real-vs-corpus, honestly — including the two still-pending gaps recorded as pending).
- Push wfx/r31/gaps with a full message; the gates output pasted in evidence/r31/guards.md.

RE-ENTRY LAW: if your session ends mid-flight, RESUME — never restart. Record partial state in evidence/r31/partial-results.md as you go (what is done, what remains, the exact next step). The lead re-enters you with a surgical resumption pointing at that file.

COMPLETION: post your report ending with the line: === R31 COMPLETION REPORT === followed by: the lane SHA, the gates table, the corpus-citation coverage (§G1/§G2 shipped vs diverged; the two gaps recorded pending), the escalation list, and the honest-divergence ledger. Keep the report tight — the lead re-verifies every claim on your lane head.
