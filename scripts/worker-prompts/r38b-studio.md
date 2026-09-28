# R38-B — the studio surfaces: content list, video details editor, analytics, comments management, and channel customization (survey row 30)

You are a senior TypeScript engineer executing ONE well-specified work item in the
WebFlix repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: R38-B — the creator-studio surfaces per the survey's WAVE R38
  spec: the Studio — content list (drafts/scheduled/published), the video
  details editor, analytics (reach/engagement/audience per video + channel),
  comments management (hold/review/pin/reply), and channel customization
  (banner/avatar/handle/description). Do not start R37 (live), R38-A
  (upload), or any other item.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/app/studio/**` (NEW — the /studio routes: content list,
    details editor, analytics, comments, customization)
  - `apps/web/src/components/studio/**` (NEW — the studio surfaces:
    ContentTable, DetailsEditor, AnalyticsPanels, CommentsModeration,
    ChannelCustomization)
  - `apps/web/src/host/studio-store/**` (NEW — the studio truth store: the
    draft/scheduled/published states, the edits, the moderation actions,
    the customization writes — persistence following the existing
    subscription-list/reactions seam law: reload-durable, the R30 law)
  - `packages/domain/src/graph/**` (EXTEND ADDITIVELY ONLY — a
    channel-profile EDIT seam if the R36 channel-profile entity needs a
    write path; never modify, rename or weaken an existing type, function
    or test — R36's read surfaces stay byte-compatible)
  - `apps/web/src/host/byof/byof-fixtures.ts` (EXTEND ADDITIVELY ONLY — a
    clearly delimited studio-seed section if the fixtures boot needs
    pre-seeded studio state; never reword existing fixture entries)
  - `journeys/web/j48-studio-edit-customize.ts` (NEW — the J48 journey) +
    `journeys/web/index.ts` (ADDITIVE registration only)
  - `docs/validation/webflix-golden-journeys.md` (ONE dated additive section)
  - `evidence/r38b/**` (NEW — your lane evidence, yours entirely)
  - Colocated lane tests `*.test.ts` inside the directories you own above
- Explicitly NOT yours: `apps/web/src/app/live/**`,
  `apps/web/src/components/live/**`, `apps/web/src/app/watch/**`,
  `apps/web/src/components/watch/**`, `apps/web/src/host/livechat/**`
  (R37 — a CONCURRENT worker lane), `apps/web/src/app/upload/**`,
  `apps/web/src/components/upload/**`, `apps/web/src/host/local-catalog/**`
  (R38-A — a CONCURRENT worker lane; never create, modify or plan around
  them), `apps/web/src/app/channel/**`, `apps/web/src/components/channel/**`,
  `apps/web/src/components/search/**`, `apps/web/src/components/cards/**`,
  `apps/web/src/components/player/ChannelRow.tsx` (R36 — merged at your
  base; read-only for you — the studio's customization WRITES go through
  your own host/studio-store seam, composing with R36's read surfaces via
  the domain graph's additive edit seam only), `apps/api/**`,
  `apps/desktop/**`, `apps/mobile/**`, every other package (`persistence`,
  `experience`, `actions`, `client-runtime`, `platform-contracts`,
  `model-fabric`, `native-media`, `recommendation`, `torrent-engine`),
  `packages/connectors/**` (R38-A's concurrent lane), `journeys/desktop/**`,
  `journeys/lib/**`, `journeys/runner.ts`, `scripts/**`, the root `bun.lock`
  and `package.json` (NO new dependencies — zero; build with what the repo
  already has).
- THE CONCURRENT-CATALOG LAW: R38-A (upload) is building the local-catalog
  write seam CONCURRENTLY — it is NOT yours. Your studio content list and
  details editor operate on the catalog truth that EXISTS at your base
  (the connector-fed fixtures + any item your studio store owns as
  drafts). Design your store so an uploaded-items source can compose later
  (at merge) — read through the same resolution seams, never around them.
- THE HONEST-ANALYTICS LAW (binding, the R28 law extended): analytics
  render ONLY what the real local transport carries. Reach/engagement/
  audience panels show the LOCAL truth of the user's own real actions
  (their own views, their own interactions — the local wallet law), and
  every metric without honest backing renders the TYPED ABSENCE state —
  never a fabricated chart, never a seeded number, never a fake axis.
  `evidence/r38b/honesty.md` proves each panel's backing or its typed
  absence.
- THE MODERATION LAW: comments management (hold/review/pin/reply) operates
  on the SAME comments truth the watch surface renders (the R28 honest
  comments law) — your studio actions are real persisted moderation
  states, never cosmetic.
- THE CUSTOMIZATION LAW: channel customization (banner/avatar/handle/
  description) writes real persisted profile state through the additive
  domain-graph seam; the R36 channel page then renders the customized
  truth (composition via the graph — never by editing R36's files).
- Lane law (unchanged): branch `wfx/r38b/studio`, lane-local evidence only,
  battery floor + lane tests + affected journeys green. `scripts/check-lanes.mjs`
  must stay green (read it first — it is the lane-convention enforcement).
- Your base is FIXED at the commit in §1. Do NOT `git pull`, `git merge` or
  otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/WebFlix.git
cd WebFlix
git checkout 37effa325c5060e14afda7e07db5b7eb61e45d9e   # main (R36 + R35b merges)
git rev-parse HEAD          # must print 37effa325c5060e14afda7e07db5b7eb61e45d9e
bun install
git checkout -b wfx/r38b/studio
bun run ci
```

Baseline expectation (the battery of record at main): **5297 tests / 5296
pass / 1 skip / 0 fail** — the 1 skip is the pre-existing R11 webtorrent
platform issue of record; your regression floor is "no NEW failures and pass
count ≥ 5296 + your lane tests".
Record the exact totals from your own baseline run in `evidence/r38b/guards.md`.
If the baseline is red beyond the 1 pre-existing skip, STOP and report.

## 2. Mandatory reading (in-repo, in this order)

1. `docs/plans/2026-09-28-youtube-parity-survey.md` — §1 row 30 (the studio
   gap you close) + §2 WAVE R38 (your spec) + the lane law paragraph.
2. `packages/domain/src/graph/model.ts` + the R36 channel-profile entity
   (`packages/domain/src/graph/**` — the profile truth your customization
   seam edits; the `Covers`/closed-vocabulary patterns; the `wfxcre_` id
   grammar).
3. `apps/web/src/components/player/ChannelRow.tsx` + the
   `subscription-list` persistence seam + the reactions store — the REAL
   persistence law your studio store follows (reload-durable, the R30 law).
4. `apps/web/src/components/watch/**` — the R28 CommentsSection: the honest
   comments truth your moderation operates on.
5. `apps/web/src/host/byof/byof-fixtures.ts` — how fixture truth feeds the
   dev boot; where studio seeds plug in.
6. `journeys/README.md` — the harness laws: journeys are checks not theater;
   the layering law (journeys import nothing from @wfx packages); the
   browser-validation protocol (open → networkidle → snapshot -i, fresh
   snapshot after every DOM-changing interaction); determinism; honest
   listing; evidence committed.
7. `scripts/check-lanes.mjs` — the lane-convention enforcement.
8. The surface precedents (read the code, follow the grammar): the settings
   surface (forms + typed states), the BYOF import flow (the staged
   preview→confirm pattern), the library surface (list + state grammar),
   and the R36 channel page (what renders the profile you customize).
9. `git log --oneline -30` + `docs/work-items/` — the R24–R36 history your
   surfaces must compose with.

## 3. The work — five milestones

### M1 — The studio survey (before any edit)

Map the creator truth end-to-end: what item/metadata truth exists at base
(the connector-fed catalog), where drafts/scheduled/published states can
bind honestly, how the comments truth flows, what the R36 channel profile
carries. Write `evidence/r38b/plan.md`: the studio-store design (the
content states, the persistence law), the editor design, the analytics
backing map (which panels have REAL local backing vs typed absence — be
brutally honest here), the moderation design, the customization seam
design (the additive graph edit), and the journey sketch — each decision
citing the file/line that grounds it.

### M2 — The studio store + the content list (truth first)

The studio store: content records with draft/scheduled/published states
(reload-durable), seeded honestly from the catalog truth that exists at
base. The `/studio` content list: the table with states, filters, and the
honest empty states. Typecheck green; no existing test touched.

### M3 — The details editor + comments management

The video details editor: title/description/visibility edits with typed
save states, writing real persisted state. Comments management: the list
per video with hold/review/pin/reply — real persisted moderation states
composing with the R28 comments truth.

### M4 — Analytics + channel customization

Analytics: per-video + channel panels, each either REAL local backing
(the user's own real actions — the local wallet law) or the TYPED ABSENCE
state, labeled honestly. Channel customization: banner/avatar/handle/
description editor writing the additive graph seam; the R36 channel page
renders the customized truth through the graph.

### M5 — The journey + the gate

Encode `journeys/web/j48-studio-edit-customize.ts` (the J48 studio edit +
customize round trip per the harness laws) and register it additively.
Run the affected existing journeys that your surfaces touch (J01–J46
affected set — J45/J46 are R37's concurrent lane: if not present at your
base, your affected set is J01–J44; J44 is R36's, present at base) and
prove no regression. Full gate per §4, then the relay (§5).

## 4. Verification — the honest gate

- `bun run ci` green at or above the recorded floor (no new failures;
  typecheck, contract-check, lane-check all green; exact totals recorded).
- `bun run journeys:web` — J48 green + the affected existing journeys
  green.
- `git diff main --stat` = ONLY your owned surface from §0.
- The honest-analytics proof: `evidence/r38b/honesty.md` maps EVERY
  analytics panel to its REAL backing or its typed absence — no fabricated
  metrics anywhere.
- `git status` clean; everything committed on `wfx/r38b/studio`.

## 5. Commit and relay the delivery

```bash
git add -A
git commit -m "feat(studio): the R38-B studio surfaces — content list, details editor, honest analytics, comments moderation, channel customization (J48) (R38-B)"
git bundle create webflix-r38b-studio.bundle main..wfx/r38b/studio
sha256sum webflix-r38b-studio.bundle evidence/r38b/* 2>/dev/null | sort -k2 > RELAY-MANIFEST.txt
```

Then WRITE the relay files into your workspace storage root with your
file-tools (the exact three artifacts, at the storage root unless noted):

1. `RELAY-MANIFEST.txt` (the sha256 list; the final line must be
   `R38B lane head <your full commit sha>`)
2. `webflix-r38b-studio.bundle` (the git bundle of main..wfx/r38b/studio)
3. `evidence/r38b/**` (the full evidence tree — plan, guards, run
   manifests, battery summary, honesty proof)

Then report in the chat (no source code, no tokens, exact shape):

```
=== R38B COMPLETION REPORT ===
branch: wfx/r38b/studio
base: 37effa325c5060e14afda7e07db5b7eb61e45d9e
content list: <the states/filters/empty-grammar landed>
details editor: <the edits + typed save states landed>
analytics: <per panel: the REAL backing or the typed absence — the honest map>
comments: <hold/review/pin/reply — the persisted moderation truth>
customization: <banner/avatar/handle/description — the graph seam + the R36 composition proof>
journey: J48 <pass/fail> + affected journeys <exact totals>
battery: <exact totals vs the 5296/1/0 floor + your lane test count>
honesty: <the typed-absence states you encoded, per surface>
defect-candidates: <any named product defects found, or "none">
relay: RELAY-MANIFEST.txt + webflix-r38b-studio.bundle + evidence/r38b/** written via file-tools
lane head: <full commit sha>
=== R38B COMPLETION REPORT @ <the full commit sha> END ===
```

The LAST line above (with the literal full commit sha) is the completion
marker — the Tech Lead gates on it. Do not paste source code, tokens or any
credential material in the report — paths, counts and outcomes only.

CRITICAL ANTI-FABRICATION RULE: if at any point you cannot execute a step
(no working terminal, no file-tools, no network), say so EXACTLY and stop —
report `Status: BLOCKED` with the specific blocker. NEVER invent test counts,
commit SHAs, file paths or outcomes. A fabricated report is worse than a
blocked one.
