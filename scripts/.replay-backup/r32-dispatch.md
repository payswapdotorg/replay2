R32: THE FOURTH-GAP WAVE — the shorts action rail, built against the captured G4 corpus

ROLE: You are the R32 worker on the WebFlix repo (github.com/payswapdotorg/webflix). ONE lane: wfx/r32/shorts-rail. Your job: build exactly ONE corpus-pending surface — now captured — and NOTHING else.

STEP ZERO (mandatory, before any design thought):
1. Clone the repo, checkout main @ c3640cf (the R32 G4-corpus merge — the battery floor 5188/1/0 lives here; the R31 gap wave is merged: the theme-picker submenu + the subscriptions feed are live).
2. Create branch wfx/r32/shorts-rail from main. The binding grammar is docs/parity-lab/r30/gap-captures/20260926-093102/G4-CORPUS.md (+ the raw evidence in the same directory: g4-shorts.json the ladder record, g4-rail-full.json the rail's outerHTML slice, g4-rail-extras.json the counts/subscribe/arrows/chrome geometry, g4-short-live.png the VLM-verified screenshot). READ G4-CORPUS.md FULLY and the prior corpus docs (GAP-CORPUS.md 20260926-052954 — the R31 grammar; docs/parity-lab/r30/lead-captures/CORPUS.md) before writing a line of code.
3. Survey WebFlix's CURRENT shorts surface: components/shorts/ShortsFeed.tsx (911 lines — the feed with the typed-absence action note at the top: "like/save capabilities render no control (typed absence)"; the actionStates machinery: optimistic + receipt-truth + rollback, keyed action:${type}:${itemId}), app/shorts/page.tsx, host/shorts.ts. Survey the seams you will join: the like/save machinery, the REAL subscribe seam (the same POST /api/library the watch page's Subscribe pill, the rail, and the feed use), the monogram avatar law (the rail subscriptions' 24x24 pattern), the item title truth.

THE FROZEN LAWS (violating any = the work is void):
- NEVER BUILD FROM MEMORY. Every surface you ship cites its G4-CORPUS.md line in the code comment AND the completion report. Where WebFlix's real model has no analogous datum, you record an honest divergence row — never fabricate parity.
- THE HONEST-RAIL LAW: the rail binds to REAL capabilities only. The captured rail: like (176K) / comments (512) / Share (text) / remix (12) + the channel avatar below + the @handle + Subscribe 78x32 pill + the title/hashtags + the 56x56 prev/next arrows + the auto-hiding top chrome (pause k / mute m / CC / more / fullscreen f). WebFlix's truth: the like → the EXISTING like/save machinery through the real actionStates seam; the subscribe → the REAL subscribe seam; the avatar → the monogram law; the title → the item's own; prev/next → the shorts queue navigation IF the real queue exists (survey it); comments/remix → WebFlix has NO comments surface and NO remix analog: these render the honest ABSENCE (omit or the established absence-note pattern) + divergence-ledger rows. Count labels bind ONLY to real WebFlix data; where no datum exists the count is ABSENT (never a fabricated "176K").
- §G3 STAYS PENDING: the home-surface resume bar (the second account-state-absent record — 30 cards, zero progress). You do NOT build it.
- THE SEAM LAW: no redesign of the shorts feed, the shell, the rail, or the player chrome beyond what the corpus join demands. The action column joins the existing shorts surface minimally.
- ESCALATIONS: code outside apps/web/** only where the root demands it; every escalation is the minimal seam and is listed in the report.

THE BUILD (one surface — the shorts action rail per the G4 corpus):
- THE ACTION COLUMN (the captured right column): the 48px-wide vertical column hugging the player's right edge — the captured geometry (48x360 container, 48x48 buttons at the 78px vertical pitch) adapted to WebFlix's own shorts layout at its measured scale (cite the adaptation honestly if the layout's geometry differs — the row-local grammar binds).
- THE LIKE: the real like/save machinery through the actionStates seam (optimistic + receipt-truth + rollback — the existing reducer); the count label only if WebFlix carries a real like-count datum (survey; if absent, the icon-only form + a ledger row).
- THE SUBSCRIBE: the channel row's Subscribe pill bound to the REAL subscribe seam (78x32-class pill, the @handle/channel identity truth — the sources-model identity).
- THE AVATAR: the monogram law (the rail subscriptions' established pattern), linking to the channel's real destination if one exists (else no link — honest).
- THE TITLE + HASHTAGS: the item's own title; the hashtags only if the real item model carries them (survey — never fabricated tags).
- THE PREV/NEXT: only if the real shorts queue/navigation exists (survey ShortsFeed's navigation truth); else honest absence + ledger row.
- THE TOP CHROME: ONLY if WebFlix's player already exposes those controls on the shorts surface (survey the existing player chrome; do not build new player controls from this corpus — the player chrome is the R27/R28 watch-surface's own, already corpus-bound).
- THE PINNED CONTROLS: the signed-out shell and every surface you do NOT touch stay byte-identical (pin the controls — the R31 pattern).

GATES (all must pass, in order, on your lane head):
- The full battery: `nice -n 19 ionice -c3 bun test --parallel=1` — the 5188/1/0 floor + your new tests, ZERO regressions (the R11 webtorrent env skip = the honest 1). NOTE: default-parallelism runs OOM-kill this sandbox class — the serial form above is the reproducible gate command (the R31 lesson).
- lint lane-clean (repo-wide pre-existing debt is NOT yours), typecheck (root + journeys + app), contract-check, lane-check, parity-conformance 19/19, build --filter '@wfx/app-web'.
- Evidence: evidence/r32/ — the corpus-citation table (surface -> G4-CORPUS.md section -> code seam), per-surface proof captures, guards.md (every gate's output), and the divergence ledger (WebFlix-real-vs-corpus, honestly — including the §G3 pending row and every absent rail capability).

TRANSPORT (pre-loaded — the R31 lesson): your sandbox has NO GitHub credentials; the `git push` will fail honestly with "could not read Username". Do not fight it. When your gates pass and the evidence pack is written:
- relay evidence/r32/ (every file, same relative paths) into your WORKSPACE STORAGE ROOT (the directory your file tools write to — where package.json/src/ live),
- create a THIN bundle: `git bundle create webflix-r32-thin.bundle c3640cf..wfx/r32/shorts-rail`,
- relay the bundle + a RELAY-MANIFEST.txt (the file list with sha256s + the lane SHAs) into the workspace root,
- reply: RELAY DONE + the file count, then post your report ending with the line: === R32 COMPLETION REPORT === (the lane SHA, the gates table, the citation coverage, the escalation list, the divergence ledger). Keep the report tight — the lead re-verifies every claim on your lane head.

RE-ENTRY LAW: if your session ends mid-flight, RESUME — never restart. Record partial state in evidence/r32/partial-results.md as you go (what is done, what remains, the exact next step). The lead re-enters you with a surgical resumption pointing at that file.
