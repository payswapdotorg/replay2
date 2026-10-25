# Task 54 — t53 Deferred Items: Browser-Level Closure (verification-only)

**Date:** 2026-10-25 · **Type:** deferred-verification sweep · **Code changes: NONE**
(both t53 deferrals closed green; zero implementation needed — see §3)

## 1. Deep-link referral signup panel (t53 deferral #1) — PASS

Browser: agent-browser (headless) against parity :3210, memory-safe sequence
(main :3000 taken down first per t51/t53 OOM laws → ~2.7GB headroom →
browser pass → sequenced recovery after).

| Case | Input | Assertions | Result |
|---|---|---|---|
| Positive | `/?auth=signup&referral_code=T54VERIFY` | dialog opens; signup mode (Username/Email/Password + Sign Up); `#h3d-referral` value=`T54VERIFY` **readOnly**; caption "Applied from your invite link."; intent "You were invited — create an account to continue."; Google/GitHub/SSO chrome present | **ALL PASS** (DOM-eval asserted) |
| Negative 1 | `/?auth=signup` (no code) | panel opens in signup mode; **no** referral field; intent "Create an account to continue."; cookie banner does NOT re-prompt (consent already stored) | **ALL PASS** |
| Negative 2 | `/` (no params) | 0 dialogs on page; no auto-open | **PASS** |

**Interaction path (verified end-to-end):** auth panel open → click-away
overlay (transparent, reference-style) closes panel → cookie card (t50)
becomes visible/clickable → "Accept all" → banner gone + granular consent
persisted to `localStorage["h3d-clone-cookie-ok"]` =
`{"analytics":true,"personalization":true,"advertising":true}`.

**Documented observation (no fix, by-design sequencing):** on deep-link
arrival the cookie card (z 40) renders *under* the auth panel (z 21011) and
its click-away overlay (z 21010) — invite-signup intent is prioritized;
consent remains obtainable immediately after the panel closes (verified).
Suppression-until-close would be an alternative, not obviously better.

## 2. Fresh rendered-DOM reference drift check (t53 deferral #2) — NO DRIFT

Method: browser-load `hyper3d.ai/workspace/rodin` (CSR) → full innerText
capture (4557 chars) + viewport/full-page screenshots → VLM compare vs
t49 baseline (`ux-parity-t49/ref-01-workspace-current.png`) → **every VLM
"difference" then DOM-probed to resolution**.

**Verdict: reference is materially unchanged since t49.** Confirmed stable:
topbar (7-Day Trial, Subscribe, Add On, API, MCP&CLI, Login, globe), hero
(Rodin, Gen-2.5 Agent-Ready, Feynman quote block), workspace controls
(GENERATE, 0.5 Credits, Presets/Gen-2.5/High/Agentic OFF, direction bar,
effort ladder), ASSET/EXPLORE/Featured gallery, footer (PRODUCT/FEATURES/
PLUG-INS/LEGAL), cookie popup.

### The four VLM false-positives — all animation-frame artifacts

| VLM claim | DOM probe resolution |
|---|---|
| "GENERATE button + settings row missing" | Present in DOM text + full-page shot — viewport-crop artifact of the first screenshot |
| "ASSET/EXPLORE section absent" | Same — crop artifact; full-page VLM + innerText both confirm |
| "Product tab changed Video → Image" | Reference tabs = stacked opacity layers: **Avatar/3D/Video (opacity 1) each with an opacity-0 swap layer "Image"** (`transition-[opacity]`); screenshots caught swap frames |
| "Add On badge icon changed M → green circle" | Badge = **7-logo cross-fade carousel** (blender/unreal/unity/godot/c4d/maya/omniverse, scale 1↔0.35 + fade 500ms, ~2s/icon); t49 caught the Maya frame ("M"), t54 caught Unreal ("green circle") |

## 3. Clone-fidelity corollary (why zero code changes)

Both micro-details the VLM casts raised are **already implemented in the
clone** (t49-era, DOM-measured):
- `studio.tsx` product pill renders **Avatar / 3D / Video** with the
  Video→Image hover-swap layer + red "new" dot (a11y tree reads the stacked
  spans as "Video Image" — that's the accessible name, not the visible label)
- `AddOnIconCarousel` implements the 7-mark cross-fade with the reference's
  measured parameters (2000ms cycle, scale 1↔0.35, 500ms ease-in-out)

The t49 VLM table's "Add On icon mismatch" row was itself an artifact:
clone-screenshot Blender frame vs reference-screenshot Maya frame of two
equivalent carousels.

## 4. Production touch (sanity, no deploy)

Zero code changed → ship repo untouched. Sanity probes: home 200 ·
`/signup` → 307 → `/?auth=signup` · `/r/T54PROBE` → 307 →
`/?auth=signup&referral_code=T54PROBE`. The deep-link client behavior
browser-verified on parity is the same ship commit (`0cb5502`) live on
production.

## 5. Artifacts

Screenshots: `deeplink-referral-dialog.png`, `clone-workspace-plain.png`,
`ref-workspace-now.png`, `ref-workspace-now-full.png`, `ref-topbar-zoom.png`
(+`ref-topbar-crop.png`) · VLM JSON: `vlm-drift-compare.json`,
`vlm-fullpage-verify.json`, `vlm-topbar-zoom.json` · this file.

**Banked lesson (VLM discipline):** never accept a cross-screenshot VLM
"changed/missing" verdict on an animated or long-page target without a
DOM-level probe — 4/4 claims here were framing or animation-frame artifacts.
Screenshots prove pixels at an instant; DOM probes prove semantics.
