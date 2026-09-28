# R38-A — the upload pipeline: drag-drop video, processing state, details form, and publish into the REAL local catalog (survey row 29)

You are a senior TypeScript engineer executing ONE well-specified work item in the
WebFlix repository. This document is your task packet — follow it exactly. The
repository itself is your specification library; read the mandated files below
BEFORE writing anything.

## 0. Ground rules

- ONE work item: R38-A — the content-upload pipeline per the survey's WAVE R38
  spec: the upload flow — drag-drop video (file pick too), the honest
  processing state, the details form (title / description / visibility
  public-unlisted-private-scheduled / thumbnail pick), and PUBLISH into the
  REAL local catalog — uploaded items become watchable and appear in
  home/search/channel/shorts per their type. Do not start R37 (live), R38-B
  (studio), or any other item.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/app/upload/**` (NEW — the /upload route + flow)
  - `apps/web/src/components/upload/**` (NEW — dropzone, processing state,
    details form, thumbnail picker, publish confirmation)
  - `apps/web/src/host/local-catalog/**` (NEW — the local catalog store +
    write seam: the uploaded-items truth, its persistence (the same
    persistence law the existing subscription-list/reactions use), the
    local-catalog source that feeds the existing resolution surfaces)
  - `packages/connectors/**` (EXTEND ADDITIVELY ONLY — a local-catalog
    source connector following the existing connector patterns so uploaded
    items flow through the SAME resolution path as provider items; never
    modify, rename or weaken an existing type, function or test)
  - `apps/web/src/host/byof/byof-fixtures.ts` (EXTEND ADDITIVELY ONLY — a
    clearly delimited uploaded-items seed section if the fixtures boot needs
    pre-seeded uploads; never reword existing fixture entries)
  - `journeys/web/j47-upload-watch-roundtrip.ts` (NEW — the J47 journey) +
    `journeys/web/index.ts` (ADDITIVE registration only)
  - `docs/validation/webflix-golden-journeys.md` (ONE dated additive section)
  - `evidence/r38a/**` (NEW — your lane evidence, yours entirely)
  - Colocated lane tests `*.test.ts` inside the directories you own above
- Explicitly NOT yours: `apps/web/src/app/live/**`,
  `apps/web/src/components/live/**`, `apps/web/src/app/watch/**`,
  `apps/web/src/components/watch/**`, `apps/web/src/host/livechat/**`
  (R37 — a CONCURRENT worker lane), `apps/web/src/app/studio/**`,
  `apps/web/src/components/studio/**` (R38-B — a CONCURRENT worker lane;
  never create, modify or plan around them), `apps/web/src/app/channel/**`,
  `apps/web/src/components/channel/**`, `packages/domain/src/graph/**`,
  `apps/web/src/components/search/**`, `apps/web/src/components/cards/**`,
  `apps/web/src/components/player/ChannelRow.tsx` (R36 — merged at your
  base; read-only for you), `apps/api/**`, `apps/desktop/**`,
  `apps/mobile/**`, every other package (`persistence`, `experience`,
  `actions`, `client-runtime`, `platform-contracts`, `model-fabric`,
  `native-media`, `recommendation`, `torrent-engine`), `journeys/desktop/**`,
  `journeys/lib/**`, `journeys/runner.ts`, `scripts/**`, the root `bun.lock`
  and `package.json` (NO new dependencies — zero; build with what the repo
  already has).
- THE REAL-CATALOG LAW: an uploaded item is a FIRST-CLASS catalog item. It
  flows through the same connector→resolution→surface path as provider
  items; it is watchable on the watch surface, findable in search, listed on
  its channel, and in the shorts rail if short-form. NEVER a side-list only
  the upload page can see.
- THE HONEST-PROCESSING LAW: the processing state tells the truth. The
  fixtures/dev boot processes deterministically (a fast deterministic
  pipeline — never a fake spinner with random timing); the states are typed
  (uploading → processing → ready / failed with a typed reason); a failed
  upload surfaces the typed failure honestly.
- THE HONEST-TRANSPORT LAW (R28, binding): view counts, likes, any social
  number on an uploaded item render only what the real local transport
  carries (zero at first — never a fabricated seed count); the typed-absence
  state otherwise.
- THE VISIBILITY LAW: public / unlisted / private / scheduled are REAL
  persisted states with REAL effects (private items never surface outside
  the owner's own lists at this tier; unlisted items are reachable by
  direct link but never in browse/search; scheduled items show their
  scheduled state until due — the scheduler truth is the persisted
  publish-at time, honestly rendered).
- Lane law (unchanged): branch `wfx/r38a/upload`, lane-local evidence only,
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
git checkout -b wfx/r38a/upload
bun run ci
```

Baseline expectation (the battery of record at main): **5297 tests / 5296
pass / 1 skip / 0 fail** — the 1 skip is the pre-existing R11 webtorrent
platform issue of record; your regression floor is "no NEW failures and pass
count ≥ 5296 + your lane tests".
Record the exact totals from your own baseline run in `evidence/r38a/guards.md`.
If the baseline is red beyond the 1 pre-existing skip, STOP and report.

## 2. Mandatory reading (in-repo, in this order)

1. `docs/plans/2026-09-28-youtube-parity-survey.md` — §1 row 29 (the upload
   gap you close) + §2 WAVE R38 (your spec) + the lane law paragraph.
2. `packages/connectors/` — the connector patterns: how a source declares
   items, how items flow to resolution; where a local-catalog source plugs
   in (the YouTubeConnector + the BYOF import path are your precedents).
3. `apps/web/src/host/byof/byof-fixtures.ts` — how fixture truth feeds the
   dev boot; how the local catalog composes with provider-fed items.
4. `apps/web/src/components/player/ChannelRow.tsx` + the
   `subscription-list` persistence seam — the REAL persistence law your
   local-catalog store follows (reload-durable, the R30 law).
5. `journeys/README.md` — the harness laws: journeys are checks not theater;
   the layering law (journeys import nothing from @wfx packages); the
   browser-validation protocol (open → networkidle → snapshot -i, fresh
   snapshot after every DOM-changing interaction); determinism; honest
   listing; evidence committed.
6. `scripts/check-lanes.mjs` — the lane-convention enforcement.
7. The surface precedents (read the code, follow the grammar): the settings
   surface (`apps/web/src/app/settings/**` — forms + typed states), the
   BYOF import flow (the staged preview→confirm pattern), and the watch
   surface (how an item id + connector resolves to a playable surface).
8. `git log --oneline -30` + `docs/work-items/` — the R24–R36 history your
   surfaces must compose with.

## 3. The work — five milestones

### M1 — The pipeline survey (before any edit)

Map the catalog truth end-to-end: how items flow from connectors to
resolution to surfaces; where a local uploaded-item source binds; what the
watch surface needs to play a local item (the native-media/local asset
precedent — J27's constrained-truth law); where the masthead/routes expect
an upload entry. Write `evidence/r38a/plan.md`: the local-catalog entity
design (fields + id grammar following the `wfxitm_` pattern), the
persistence design (the reload-durability law), the processing-state
machine, the visibility semantics, the thumbnail truth (a real frame pick
or the honest placeholder — never a fabricated image), and the journey
sketch — each decision citing the file/line that grounds it.

### M2 — The local-catalog truth (store + connector + fixtures, additive)

The local-catalog store: uploaded items with full catalog-item shape
(title/description/type/duration/thumbnail/visibility/publish-at), the
deterministic processing pipeline state, reload-durable persistence
following the subscription-list seam law. The local-catalog source
connector so uploads flow through the SAME resolution path. Typecheck
green; no existing test touched.

### M3 — The upload flow

`/upload`: drag-drop + file pick (accept the honest web-local set —
the typed-acceptance states; an unsupported type is a typed, named
rejection, never a silent nothing), the processing state (deterministic,
honest), then the details form: title, description, visibility
(public/unlisted/private/scheduled + the publish-at picker when
scheduled), thumbnail pick. Publish writes the REAL catalog item.

### M4 — The catalog integration proof

An uploaded public item: watchable on the watch surface, findable in
search (title match), listed on its channel page (R36's surface renders
it via the resolution path — read-only composition, no R36 file edits),
in the shorts rail when short-form. An unlisted item: direct-link
watchable, never in browse/search. A private item: never public. A
scheduled item: honestly rendered as scheduled until due. Each proof
browser-verified with committed snapshots.

### M5 — The journey + the gate

Encode `journeys/web/j47-upload-watch-roundtrip.ts` (the J47 upload →
watch round trip per the harness laws) and register it additively. Run
the affected existing journeys that your surfaces touch (J01–J46 affected
set — J45/J46 are R37's concurrent lane: if not present at your base,
your affected set is J01–J44) and prove no regression. Full gate per §4,
then the relay (§5).

## 4. Verification — the honest gate

- `bun run ci` green at or above the recorded floor (no new failures;
  typecheck, contract-check, lane-check all green; exact totals recorded).
- `bun run journeys:web` — J47 green + the affected existing journeys
  green.
- `git diff main --stat` = ONLY your owned surface from §0.
- The honest-transport proof: `evidence/r38a/honesty.md` shows the REAL
  backing for every number and state (zero-count truth at publish, the
  typed processing states, the typed visibility effects) — never a
  fabricated value.
- `git status` clean; everything committed on `wfx/r38a/upload`.

## 5. Commit and relay the delivery

```bash
git add -A
git commit -m "feat(upload): the R38-A upload pipeline — drag-drop, honest processing, details form with visibility, publish into the real local catalog (J47) (R38-A)"
git bundle create webflix-r38a-upload.bundle main..wfx/r38a/upload
sha256sum webflix-r38a-upload.bundle evidence/r38a/* 2>/dev/null | sort -k2 > RELAY-MANIFEST.txt
```

Then WRITE the relay files into your workspace storage root with your
file-tools (the exact three artifacts, at the storage root unless noted):

1. `RELAY-MANIFEST.txt` (the sha256 list; the final line must be
   `R38A lane head <your full commit sha>`)
2. `webflix-r38a-upload.bundle` (the git bundle of main..wfx/r38a/upload)
3. `evidence/r38a/**` (the full evidence tree — plan, guards, run
   manifests, battery summary, honesty proof)

Then report in the chat (no source code, no tokens, exact shape):

```
=== R38A COMPLETION REPORT ===
branch: wfx/r38a/upload
base: 37effa325c5060e14afda7e07db5b7eb61e45d9e
upload flow: <the surfaces landed + the typed acceptance states>
processing: <the deterministic state machine + the typed failure path>
details form: <title/description/visibility/scheduled/thumbnail — landed how>
local catalog: <the store + connector design + the persistence proof>
catalog integration: <watch/search/channel/shorts proofs — exact evidence>
journey: J47 <pass/fail> + affected journeys <exact totals>
battery: <exact totals vs the 5296/1/0 floor + your lane test count>
honesty: <the typed-absence states you encoded, per surface>
defect-candidates: <any named product defects found, or "none">
relay: RELAY-MANIFEST.txt + webflix-r38a-upload.bundle + evidence/r38a/** written via file-tools
lane head: <full commit sha>
=== R38A COMPLETION REPORT @ <the full commit sha> END ===
```

The LAST line above (with the literal full commit sha) is the completion
marker — the Tech Lead gates on it. Do not paste source code, tokens or any
credential material in the report — paths, counts and outcomes only.

CRITICAL ANTI-FABRICATION RULE: if at any point you cannot execute a step
(no working terminal, no file-tools, no network), say so EXACTLY and stop —
report `Status: BLOCKED` with the specific blocker. NEVER invent test counts,
commit SHAs, file paths or outcomes. A fabricated report is worse than a
blocked one.
