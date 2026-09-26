R30-B: THE ACCOUNT-CHROME FAMILY — build against the captured logged-in corpus

ROLE: You are the R30-B worker on the WebFlix repo (github.com/payswapdotorg/webflix). ONE lane: wfx/r30/b. Your job: bring the corpus-pending family — the account chrome surfaces — from honest-absence to corpus-bound parity, and NOTHING else.

STEP ZERO (mandatory, before any design thought):
1. Clone the repo, checkout main @ f1bdba6 (the R30-A merge — the battery floor 5142/1/0 lives here).
2. Create branch wfx/r30/b from main, then `git merge origin/wfx/r30/lead-captures` — the R30 lead-corpus lane (evidence/docs ONLY, merges clean). The binding grammar lives in docs/parity-lab/r30/lead-captures/CORPUS.md (+ README.md the window record, raw*/ screenshots + JSON truths, vlm/ reads). READ CORPUS.md FULLY before writing a line of code.
3. Survey WebFlix's CURRENT account model: how the app models the signed-in operator persona, the masthead end-cluster, the rail, the Library/History surfaces (apps/web + packages/client-runtime; the R30-A LibraryEngine.hydrate seam is the durable library read — reuse its law, never fight it).

THE FROZEN LAWS (violating any = the work is void):
- NEVER BUILD FROM MEMORY. Every surface you ship cites its CORPUS.md line (section number) in the code comment AND the completion report. Where WebFlix's real account model has NO analogous surface, you record an honest divergence row — never fabricate parity.
- THE GAPS STAY PENDING: (a) theme-picker submenu rows (CORPUS has only the "Appearance: Device theme" state label), (b) home-surface resume bar, (c) the healthy subscriptions-feed grid (only the degraded live-only state is captured), (d) the shorts action rail (gate confirmed STILL ACTIVE logged-in). You do NOT build these four from anything but the captured lines; absent capture = absent/honest surface, recorded as pending.
- THE SEAM LAW: no redesign of the masthead, rail, pills, or Library. The account chrome joins the existing surfaces the way the corpus grammar binds — minimal honest seams.
- ESCALATIONS: code outside apps/web/** only where the defect/root demands it; every escalation is the minimal seam and is listed in the report.

THE BUILD (each item = corpus section):
1. §1 MASTHEAD CLUSTER: the end-cluster grammar against WebFlix's real signed-in state — the bell button 40x40 with the "9+" cap badge (badge caps at 9+ while the true count surfaces in the title — two grammar layers, implement BOTH), the avatar squircle, the mic 40x40 r50 in-bar (WebFlix's own voice-search honesty law applies: no real transport = honestly-absent or the real one, never decorative).
2. §2 BELL PANEL: the notifications panel anatomy — "Notifications" header + gear + collapse arrow; rows = unread dot + square thumb + bold source/action + title + grey time + kebab; ~360-400px top-right anchored. Only if WebFlix has (or honestly gains) a notification source; otherwise the honest-absence row.
3. §3 ACCOUNT MENU: header (name/handle/"View your channel" link) + the 14-row grammar with state-bearing labels, where WebFlix's account model maps rows to REAL destinations (Settings exists; Appearance/Language/Location only as real settings — the R28 appearance-menu corpus is the logged-out variant measured in color-survey.md; the picker rows themselves are PENDING).
4. §4 RAIL: subscriptions rail — 24x24 channel avatars (the R28 flat-list grammar now with the measured avatar), entries 204x40, the section taxonomy bound to WebFlix's REAL destinations (the R29 divergence-5 ledger is the divergence law — WebFlix's rail = its real surfaces).
5. §6/§8/§9 WATCHED-PROGRESS + PLAYLISTS FAMILY: the resume-bar grammar (red bar in the thumb area — the history-row observed instance) on WebFlix's history/continue surfaces bound to the LibraryEngine's stored truth; the playlist page header grammar (title/owner/count/updated + Play all + Shuffle pills) + the "N unavailable videos are hidden" honest-notice pattern + sort chips (All/Videos/Shorts) where WebFlix's Library rows map.
6. §10 SUBS FEED: only the DEGRADED live-only state is captured — WebFlix's subscriptions surface stays bound to its real connector truth; no fabricated grid.

GATES (all must pass, in order, on your lane head):
- The full battery: `bun test` (or the repo's canonical runner) — 5142/1/0 floor + your new tests, ZERO regressions (the R11 webtorrent env skip = the honest 1).
- lint lane-clean (repo-wide pre-existing evidence debt on main is NOT yours), typecheck, contract-check, lane-check (no cross-lane private imports), parity-conformance 19/19, build --filter web.
- Evidence: evidence/r30-b/ — the corpus-citation table (surface -> CORPUS.md section -> code seam), per-surface proof captures, and the divergence ledger (WebFlix-real-vs-corpus, honestly).
- Push wfx/r30/b with a full message; the gates output pasted in evidence/r30-b/guards.md.

RE-ENTRY LAW: if your session ends mid-flight, RESUME — never restart. Record partial state in evidence/r30-b/partial-results.md as you go (what is done, what remains, the exact next step). The lead re-enters you with a surgical resumption pointing at that file.

COMPLETION: post your report ending with the line: === R30-B COMPLETION REPORT === followed by: the lane SHA, the gates table, the corpus-citation coverage (which CORPUS sections shipped vs diverged vs pending), the escalation list, and the honest-divergence ledger. Keep the report tight — the lead re-verifies every claim on your lane head.
