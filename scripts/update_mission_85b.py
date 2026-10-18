#!/usr/bin/env python3
"""Mission update: mer-B recycled (work lost); r3-w3c redispatched; v4 watch."""
import json, time

P = "/home/z/replay2/data/mission-state.json"
d = json.load(open(P))
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

d["updatedAt"] = now
d["mission"]["subtitle"] = (
    "Repository is the only source of truth (payswapdotorg/PaySwap-3.0 @ c5a4dc7, "
    "PAT era — pushes live). R3: route-compiler + onchain-extensions MERGED; merchant "
    "redispatched (r3-w3c) after the mer-B completion-recycling loss — the salvaged "
    "worklog (82KB) is the prior-art oracle. R4-W1 lab in flight (r4-w1b). Station "
    "watch v4: registry lanes + stuck-start force-unstick + marker auto-harvest."
)

for it in d["items"]:
    if it.get("id") == "r3-w3":
        it["status"] = "in_progress"
        it["title"] = ("merchant rebuild #3 (r3-w3c) — mer-B completed oracle-exact "
                       "(25f/353t) but was RECYCLED mid-delivery (chat+workspace+home-dir "
                       "work lost); 97-file salvage pulled; packet hardened with the "
                       "incremental-delivery laws + two-build oracle envelope")
    if it.get("id") == "r4-w1":
        it["status"] = "in_progress"
        it["title"] = ("lab rebuild (r4-w1b @ 26ead2b9) — prompt landed, generation "
                       "stuck-start in the degraded window; station watch force-unsticks")

tl = d.get("timeline") or []
tl.append({"ts": now, "text": (
    "THE MER-B LOSS (completion-recycling, second occurrence): mer-B finished its "
    "final summary at ~18:35Z (oracle-exact: 25f/353t, tsc 0, 4 commits, 224P/94A/15R/"
    "20N) and went completion-idle with the delivery still in its HOME DIR — the "
    "platform recycled the whole session by 18:52 (chat route gone, URL bounces to "
    "landing; workspace record lingered). 97 files SALVAGED from the app root before "
    "it vanished: the complete 82KB worklog (methodology + census + deviations) + old-"
    "tree evidence reads. The new implementation (77 files) was never in the file API "
    "and is lost. Salvage archived at lanes/r3-w3-salvage/")})
tl.append({"ts": now, "text": (
    "STATION WATCH v4 (the saturation-era rebuild): replaces lane-watch v3 + renudge "
    "v2 + auto-harvest with ONE registry-driven sentinel. New laws: STUCK-START "
    "(stopBtn + body-frozen 3 cycles = dead generation start -> click Stop -> nudge; "
    "the class that fooled the ladder into false SUCCESS), DEAD-LANE FALLBACK "
    "(find_tab's any-tab fallback made the renudge loop read the WRONG chat after "
    "mer-B's tab died — lanes are now pinned by registry tab_id), marker auto-harvest "
    "on every cycle. dispatch_worker send-guard patched twice: fresh-chat home-surface "
    "sessions can be nudged; a tab that advanced to its /c/ url is adopted not "
    "refused. r3-w3c REDISPATCHED with the hardened packet (incremental delivery "
    "after EVERY commit; short final turns; two-build oracle envelope).")})
d["timeline"] = tl[-40:]

json.dump(d, open(P, "w"), indent=2)
print("mission board updated:", now)
