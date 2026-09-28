# R36 — creator channels end-to-end: the /channel surfaces, channel search results, and the subscribe bell (the #1 structural YouTube-parity gap closed)

You are a senior TypeScript engineer executing ONE well-specified work item in the
WebFlix repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: R36 — the creator-channel surfaces end-to-end per the survey's
  WAVE R36 spec: `/channel/[handle]` (+ id) routes (banner, avatar, identity,
  subs count, join date, description, links), tabs (Home featured / Videos with
  latest-popular-oldest sort / Shorts / Playlists / About) + channel search,
  Subscribe + bell (all/personalized/none — honest backing) on the channel,
  cards' + watch-page channel rows linking to channels, and channel result rows
  in search with inline Subscribe. Do not start R37 (live) or any other item.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/app/channel/**` (NEW — the /channel routes)
  - `apps/web/src/components/channel/**` (NEW — banner, tabs, subscribe-bell)
  - `apps/web/src/components/search/**` (EXTEND — channel result rows; keep
    every existing result surface byte-compatible)
  - `apps/web/src/components/cards/**` + `apps/web/src/components/player/ChannelRow.tsx`
    (EXTEND — channel identity becomes a link to the channel page; additive)
  - `packages/domain/src/graph/**` (EXTEND ADDITIVELY ONLY — a channel-profile
    truth: banner/avatar/subs-count/join-date/description/links + channel feed
    resolution, following the existing entity patterns; NEVER modify, rename or
    weaken an existing type, function or test)
  - `apps/web/src/host/byof/byof-fixtures.ts` (EXTEND ADDITIVELY ONLY — the
    channel-profile fixture section, clearly delimited; never reword existing
    fixture entries)
  - `journeys/web/j44-channel-browse-subscribe.ts` (NEW — the J44 journey) +
    `journeys/web/index.ts` (ADDITIVE registration only)
  - `docs/validation/webflix-golden-journeys.md` (ONE dated additive section)
  - `evidence/r36/**` (NEW — your lane evidence, yours entirely)
  - Colocated lane tests `*.test.ts` inside the directories you own above
- Explicitly NOT yours: `apps/web/src/app/live/**`, `apps/web/src/components/live/**`,
  `apps/web/src/app/watch/**`, `apps/web/src/components/watch/**`,
  `apps/web/src/host/livechat/**`, `apps/web/src/host/realtime/**`,
  `packages/connectors/**` (R37 — a CONCURRENT worker lane; never create,
  modify or plan around them), `apps/api/**`, `apps/desktop/**`, `apps/mobile/**`,
  every other package (`persistence`, `experience`, `actions`, `client-runtime`,
  `platform-contracts`, `model-fabric`, `native-media`, `recommendation`,
  `torrent-engine`), `journeys/desktop/**`, `journeys/lib/**`,
  `journeys/runner.ts`, `scripts/**`, the root `bun.lock` and `package.json`
  (NO new dependencies — zero; build with what the repo already has).
- THE HONEST-TRANSPORT LAW (R28, binding on every social surface): only real
  user actions are counted and persisted; viewer/subscriber counts and any
  social number you cannot honestly back is rendered as the TYPED ABSENCE
  state, never a fabricated number. The bell's all/personalized/none settings
  are real per-channel persisted state (the same persistence seam the existing
  subscription-list uses); never fake a count.
- Lane law (unchanged): branch `wfx/r36/channels`, lane-local evidence only,
  battery floor + lane tests + affected journeys green. `scripts/check-lanes.mjs`
  must stay green (read it first — it is the lane-convention enforcement).
- Your base is FIXED at the commit in §1. Do NOT `git pull`, `git merge` or
  otherwise incorporate upstream changes during your run.

## 1. Setup — public main

```bash
git clone https://github.com/payswapdotorg/WebFlix.git
cd WebFlix
git checkout acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419   # main (R35-A)
git rev-parse HEAD          # must print acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419
bun install
git checkout -b wfx/r36/channels
bun run ci
```

Baseline expectation (the battery of record at main): **5265 pass / 1 fail / 0
skip** — the 1 fail is the pre-existing platform failure of record; your
regression floor is "no NEW failures and pass count ≥ 5265 + your lane tests".
Record the exact totals from your own baseline run in `evidence/r36/guards.md`.
If the baseline is red beyond the 1 pre-existing fail, STOP and report.

## 2. Mandatory reading (in-repo, in this order)

1. `docs/plans/2026-09-28-youtube-parity-survey.md` — §1 rows 17/18/19 (the
   channel gaps you close) + §2 WAVE R36 (your spec) + the lane law paragraph.
2. `packages/domain/src/graph/model.ts` — the entity patterns: `Creator`
   (id/name/kind), `Topic`, the id grammar (`wfxcre_` prefix), the closed
   vocabularies with `Covers` guards. Your channel-profile additions follow
   these patterns exactly.
3. `apps/web/src/host/byof/byof-fixtures.ts` — how fixture truth feeds the
   dev boot; where channel profiles plug in.
4. `journeys/README.md` — the harness laws: journeys are checks not theater;
   the layering law (journeys import nothing from @wfx packages); the
   browser-validation protocol (open → networkidle → snapshot -i, fresh
   snapshot after every DOM-changing interaction); determinism; honest
   listing; evidence committed.
5. `scripts/check-lanes.mjs` — the lane-convention enforcement (what a legal
   lane looks like on this repo).
6. The surface precedents (read the code, follow the grammar): the shorts
   surface (`apps/web/src/app/shorts/**` + `apps/web/src/components/shorts/**`),
   the search surface (`apps/web/src/app/search/**` +
   `apps/web/src/components/search/**`), the watch surface's ChannelRow
   (`apps/web/src/components/player/ChannelRow.tsx` — the existing subscribe
   seam + `subscription-list`), and the shell/masthead grammar (R29-B).
7. `git log --oneline -30` + `docs/work-items/` — the R28-B/R29-B grammar
   history your surfaces must compose with.

## 3. The work — five milestones

### M1 — The surface survey (before any edit)

Map the channel data truth end-to-end: how `Creator` identities flow from
fixtures/connectors into cards, search results and the watch-page ChannelRow
today; where the subscribe seam persists (`subscription-list`); what the
masthead/rail grammar expects of a new top-level surface. Write
`evidence/r36/plan.md`: the route map, the component inventory, the
channel-profile entity design (fields + id grammar), the fixture plan, and
the journey sketch — each decision citing the file/line that grounds it.

### M2 — The channel-profile truth (domain + fixtures, additive)

Add the channel-profile entity + channel feed resolution to the domain graph
(additive only, following the `Covers`/closed-vocabulary patterns), and the
fixture channel profiles (banner/avatar/subs/join-date/description/links +
their item memberships) in a clearly delimited additive fixtures section.
Typecheck green; no existing test touched.

### M3 — The channel surfaces

`/channel/[handle]` (+ the id form) with banner, avatar, identity, subs
count, join date, description, links; tabs Home (featured) / Videos (sort
latest/popular/oldest) / Shorts / Playlists / About; channel search; the
channel-level Subscribe + bell (all/personalized/none — real persisted
state, typed states where backing is absent). Every surface obeys the
honest-transport law and the R29-B shell/rail grammar; anonymous viewing is
never gated (the R23 law — subscribe offers sign-in as an upgrade, not a wall).

### M4 — Discovery integration

Search: channel result rows (avatar, name, subs, description) with inline
Subscribe — composed with the existing result grammar, existing item results
untouched. Cards' channel identities + the watch-page ChannelRow link to the
channel page. Every link round-trips (navigate → the channel renders → back).

### M5 — The journey + the gate

Encode `journeys/web/j44-channel-browse-subscribe.ts` (the J44 channel
browse/subscribe round trip per the harness laws) and register it additively.
Run the affected existing journeys that your surfaces touch (per the survey:
J01–J43 affected set) and prove no regression. Full gate per §4, then the
relay (§5).

## 4. Verification — the honest gate

- `bun run ci` green at or above the recorded floor (no new failures;
  typecheck, contract-check, lane-check all green; exact totals recorded).
- `bun run journeys:web` — J44 green + the affected existing journeys green.
- `git diff main --stat` = ONLY your owned surface from §0.
- The honest-transport proof: for the subs count, the bell settings and any
  social number on the channel surface, `evidence/r36/honesty.md` shows the
  REAL backing (the persisted state / the typed absence) — never a fabricated
  number.
- `git status` clean; everything committed on `wfx/r36/channels`.

## 5. Commit and relay the delivery

```bash
git add -A
git commit -m "feat(channels): the R36 creator-channel surfaces — /channel routes, tabs, subscribe+bell, channel search rows, card/ChannelRow links (J44) (R36)"
git bundle create webflix-r36-channels.bundle main..wfx/r36/channels
sha256sum webflix-r36-channels.bundle evidence/r36/* 2>/dev/null | sort -k2 > RELAY-MANIFEST.txt
```

Then WRITE the relay files into your workspace storage root with your
file-tools (the exact three artifacts, at the storage root unless noted):

1. `RELAY-MANIFEST.txt` (the sha256 list; the final line must be
   `R36 lane head <your full commit sha>`)
2. `webflix-r36-channels.bundle` (the git bundle of main..wfx/r36/channels)
3. `evidence/r36/**` (the full evidence tree — plan, guards, run manifests,
   battery summary, honesty proof)

Then report in the chat (no source code, no tokens, exact shape):

```
=== R36 COMPLETION REPORT ===
branch: wfx/r36/channels
base: acff71b8b363ba6f85ab7a3e9b08ca7ba3e5a419
routes: <the channel routes you landed>
tabs: <the tabs landed + the Videos sort orders>
bell: all/personalized/none persisted state — <the honest backing statement>
search: channel result rows with inline Subscribe — <landed/how>
links: cards + watch-page ChannelRow link to channels — <landed/how>
journey: J44 <pass/fail> + affected journeys <exact totals>
battery: <exact totals vs the 5265/1/0 floor + your lane test count>
honesty: <the typed-absence states you encoded, per surface>
defect-candidates: <any named product defects found, or "none">
relay: RELAY-MANIFEST.txt + webflix-r36-channels.bundle + evidence/r36/** written via file-tools
lane head: <full commit sha>
=== R36 COMPLETION REPORT @ <the full commit sha> END ===
```

The LAST line above (with the literal full commit sha) is the completion
marker — the Tech Lead gates on it. Do not paste source code, tokens or any
credential material in the report — paths, counts and outcomes only.

CRITICAL ANTI-FABRICATION RULE: if at any point you cannot execute a step
(no working terminal, no file-tools, no network), say so EXACTLY and stop —
report `Status: BLOCKED` with the specific blocker. NEVER invent test counts,
commit SHAs, file paths or outcomes. A fabricated report is worse than a
blocked one.
