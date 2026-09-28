# R37 — live video + live chat: the /live browse, watch-page live mode with current chat over the WS seam, and chat replay on archived live VODs

You are a senior TypeScript engineer executing ONE well-specified work item in
the WebFlix repository. This document is your task packet — follow it exactly.
The repository itself is your specification library; read the mandated files
below BEFORE writing anything.

## 0. Ground rules

- ONE work item: R37 — the live surfaces per the survey's WAVE R37 spec: the
  live item designation (LIVE badge + viewer count, honest backing), the
  `/live` browse rail, the watch-page live mode with CURRENT LIVE CHAT over
  the real-time transport (the WS seam), live chat replay on archived live
  VODs timed to the playhead, and the chat grammar (member badges, pinned
  message, slow mode, emojis). Premieres are DEFERRED to R40 — do not build
  them. R36 (channels) is ALREADY MERGED at your base — build on it (the
  channel Live tab composes with your /live rail); never modify R36's
  surfaces. Do not start R38 (upload/studio) or any other item.
- Owned surface (the ONLY files you may create/modify):
  - `apps/web/src/app/live/**` (NEW — the /live browse)
  - `apps/web/src/components/live/**` (NEW — the live surfaces + live chat UI)
  - `apps/web/src/app/watch/**` + `apps/web/src/components/watch/**`
    (EXTEND — the live mode composition; the default watch surface stays
    byte-compatible for non-live items)
  - `apps/web/src/host/livechat/**` (NEW — the live-chat transport, following
    the R25-D bridge law: a typed-wire WS mini-service inside the dev
    process, started from instrumentation.ts)
  - `apps/web/src/instrumentation.ts` (EXTEND ADDITIVELY ONLY — start the
    live-chat bridge alongside the existing realtime bridge; never modify the
    existing bridge startup)
  - `apps/web/src/host/realtime/**` (READ-ONLY — the transport precedent; if
    you believe a shared seam change is required, record it in the report as
    a named out-of-lane note and continue — never edit it yourself)
  - `packages/connectors/**` (EXTEND ADDITIVELY ONLY — the live designation
    + live metadata on items + the archived live-chat log artifact, following
    the existing connector patterns; never modify, rename or weaken an
    existing type, function or test)
  - `apps/web/src/host/byof/byof-fixtures.ts` (EXTEND ADDITIVELY ONLY — live
    fixture entries + archived live VODs with chat logs, clearly delimited;
    never reword existing fixture entries)
  - `journeys/web/j45-live-watch-chat.ts` + `journeys/web/j46-chat-replay-scrub.ts`
    (NEW — the J45/J46 journeys) + `journeys/web/index.ts` (ADDITIVE
    registration only)
  - `docs/validation/webflix-golden-journeys.md` (ONE dated additive section)
  - `evidence/r37/**` (NEW — your lane evidence, yours entirely)
  - Colocated lane tests `*.test.ts` inside the directories you own above
- Explicitly NOT yours: `apps/web/src/app/channel/**`,
  `apps/web/src/components/channel/**`, `packages/domain/src/graph/**`,
  `apps/web/src/components/search/**`, `apps/web/src/components/cards/**`,
  `apps/web/src/components/player/ChannelRow.tsx` (R36 — MERGED at your base;
  read-only for you), `apps/web/src/app/upload/**`,
  `apps/web/src/components/upload/**`, `apps/web/src/host/local-catalog/**`
  (R38-A — a CONCURRENT worker lane), `apps/web/src/app/studio/**`,
  `apps/web/src/components/studio/**` (R38-B — a CONCURRENT worker lane;
  never create, modify or plan around any of them), `apps/api/**`,
  `apps/desktop/**`, `apps/mobile/**`, every other package (`persistence`,
  `experience`, `actions`, `client-runtime`, `platform-contracts`,
  `model-fabric`, `native-media`, `recommendation`, `torrent-engine`),
  `journeys/desktop/**`, `journeys/lib/**`, `journeys/runner.ts`,
  `scripts/**`, the root `bun.lock` and `package.json` (NO new dependencies —
  zero; the WS transport uses only what the repo already has — the R25-D
  bridge pattern is your precedent).
- THE LIVE-DESIGNATION LAW: the live truth is encoded at the connector/
  fixture + view-model layer (your owned surface) — you do NOT touch the
  domain graph (R36 landed it at your base; read-only for you). An item is
  live, or is an archived
  live VOD, because its connector metadata says so; the surfaces derive,
  never guess.
- THE HONEST-TRANSPORT LAW (R28, binding): viewer counts, chat participants,
  member badges — every social number renders only what the transport really
  carries; the typed-absence state otherwise. Never fabricate a viewer count,
  a chat message, or a badge. The dev fixtures' chat double is LOUDLY LABELED
  (the R25 dev-double precedent) — deterministic, honest, never mistaken for
  a live provider.
- THE TRANSPORT LAW (R25-D, adapted): Browser → WebFlix WebSocket (your
  livechat bridge) → the session seam (deterministic dev double in the
  fixtures boot). NEVER browser → any provider with a credential. Typed wire
  validation on every message; the chat log artifact for replay is committed
  data, not a stream capture.
- Lane law (unchanged): branch `wfx/r37/live`, lane-local evidence only,
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
git checkout -b wfx/r37/live
bun run ci
```

Baseline expectation (the battery of record at main): **5297 tests / 5296
pass / 1 skip / 0 fail** — the 1 skip is the pre-existing R11 webtorrent
platform issue of record; your regression floor is "no NEW failures and pass
count ≥ 5296 + your lane tests".
Record the exact totals from your own baseline run in `evidence/r37/guards.md`.
If the baseline is red beyond the 1 pre-existing fail, STOP and report.

## 2. Mandatory reading (in-repo, in this order)

1. `docs/plans/2026-09-28-youtube-parity-survey.md` — §1 rows 20/21 (the live
   gaps you close) + §2 WAVE R37 (your spec) + the lane law paragraph.
2. `apps/web/src/host/realtime/realtime-bridge.ts` + `realtime-route.ts` +
   `realtime-boot.ts` + `dev-realtime-session.ts` + `apps/web/src/instrumentation.ts`
   — the R25-D transport precedent: the WS mini-service law, the typed wire
   validation, the dev-double labeling, the gate order.
3. `packages/connectors/` — the connector patterns (how item metadata flows
   from source to surface; where the live designation + the archived chat
   log plug in).
4. `apps/web/src/host/byof/byof-fixtures.ts` — how fixture truth feeds the
   dev boot; where live entries + archived live VODs plug in.
5. `journeys/README.md` — the harness laws: journeys are checks not theater;
   the layering law (journeys import nothing from @wfx packages); the
   browser-validation protocol (open → networkidle → snapshot -i, fresh
   snapshot after every DOM-changing interaction); determinism; honest
   listing; evidence committed.
6. `scripts/check-lanes.mjs` — the lane-convention enforcement.
7. The watch-surface precedents (read the code, follow the grammar):
   `apps/web/src/app/watch/**`, `apps/web/src/components/watch/**`, the
   player chrome + the LiveCaptionsSurface (R25) for how live-mode states
   compose, and the shorts surface for the full-screen vertical grammar.
8. `git log --oneline -30` + `docs/work-items/` — the R24–R35 history your
   surfaces must compose with.

## 3. The work — five milestones

### M1 — The surface survey (before any edit)

Map the live truth end-to-end: how items flow from connectors to surfaces;
where a live designation + viewer count can bind honestly; how the R25-D
bridge is started and gated; what the watch surface expects of a live mode.
Write `evidence/r37/plan.md`: the item-designation design (connector layer),
the transport design (the livechat bridge — port, wire schema, the dev
double), the /live browse design, the live-mode watch composition, the
chat-replay design (the log artifact + the playhead binding), and the journey
sketch — each decision citing the file/line that grounds it.

### M2 — The live catalog truth (connectors + fixtures, additive)

The live designation + live metadata (LIVE badge truth, viewer count source,
archived-live VOD marker + the chat-log artifact) at the connector layer,
plus the fixture entries: live items for the /live rail, at least one
archived live VOD with a committed chat log. Typecheck green; no existing
test touched.

### M3 — The /live browse + the watch live mode + current live chat

The `/live` browse rail (LIVE badges, viewer counts — honest backing). The
watch-page live mode: the player presents the live item honestly (no
scrubbing a live edge — the grammar states what is true), the current live
chat over your bridge: member badges, pinned message, slow mode, emojis —
each a real transport behavior or the typed-absence state. The dev chat
double is deterministic and loudly labeled.

### M4 — Live chat replay on archived live VODs

On an archived live VOD, the chat replay renders the committed log timed to
the playhead: scrub → the chat window follows; play → messages arrive in
time order; the surface states the replay truth honestly (an archived log,
never a live stream).

### M5 — The journeys + the gate

Encode `journeys/web/j45-live-watch-chat.ts` (the J45 live watch + chat
round trip) and `journeys/web/j46-chat-replay-scrub.ts` (the J46 chat
replay scrub) per the harness laws; register both additively. Run the
affected existing journeys that your surfaces touch (J01–J44 affected set —
J44 is R36's creator-channel journey, PRESENT at your base) and prove no
regression. Full gate per §4, then
the relay (§5).

## 4. Verification — the honest gate

- `bun run ci` green at or above the recorded floor (no new failures;
  typecheck, contract-check, lane-check all green; exact totals recorded).
- `bun run journeys:web` — J45 + J46 green + the affected existing journeys
  green.
- `git diff main --stat` = ONLY your owned surface from §0.
- The honest-transport proof: `evidence/r37/honesty.md` shows the REAL
  backing for every live number (viewer count, chat presence, badges) and
  the typed-absence states where backing is absent; the dev double's
  deterministic transcript is committed.
- `git status` clean; everything committed on `wfx/r37/live`.

## 5. Commit and relay the delivery

```bash
git add -A
git commit -m "feat(live): the R37 live surfaces — /live browse, watch live mode with live chat over the WS seam, archived chat replay (J45, J46) (R37)"
git bundle create webflix-r37-live.bundle main..wfx/r37/live
sha256sum webflix-r37-live.bundle evidence/r37/* 2>/dev/null | sort -k2 > RELAY-MANIFEST.txt
```

Then WRITE the relay files into your workspace storage root with your
file-tools (the exact three artifacts, at the storage root unless noted):

1. `RELAY-MANIFEST.txt` (the sha256 list; the final line must be
   `R37 lane head <your full commit sha>`)
2. `webflix-r37-live.bundle` (the git bundle of main..wfx/r37/live)
3. `evidence/r37/**` (the full evidence tree — plan, guards, run manifests,
   battery summary, honesty proof)

Then report in the chat (no source code, no tokens, exact shape):

```
=== R37 COMPLETION REPORT ===
branch: wfx/r37/live
base: 37effa325c5060e14afda7e07db5b7eb61e45d9e
live designation: <how items declare live truth (connector layer)>
/live browse: <landed surfaces + the honest viewer-count backing>
watch live mode: <the composition + what the grammar states honestly>
live chat: <the transport (bridge/dev double) + the chat grammar landed (badges/pinned/slow/emojis)>
chat replay: <the log artifact + the playhead binding + the scrub proof>
journeys: J45 <pass/fail> + J46 <pass/fail> + affected journeys <exact totals>
battery: <exact totals vs the 5296/1/0 floor + your lane test count>
honesty: <the typed-absence states you encoded, per surface>
defect-candidates: <any named product defects found, or "none">
relay: RELAY-MANIFEST.txt + webflix-r37-live.bundle + evidence/r37/** written via file-tools
lane head: <full commit sha>
=== R37 COMPLETION REPORT @ <the full commit sha> END ===
```

The LAST line above (with the literal full commit sha) is the completion
marker — the Tech Lead gates on it. Do not paste source code, tokens or any
credential material in the report — paths, counts and outcomes only.

CRITICAL ANTI-FABRICATION RULE: if at any point you cannot execute a step
(no working terminal, no file-tools, no network), say so EXACTLY and stop —
report `Status: BLOCKED` with the specific blocker. NEVER invent test counts,
commit SHAs, file paths or outcomes. A fabricated report is worse than a
blocked one.
