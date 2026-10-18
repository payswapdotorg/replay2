#!/usr/bin/env python3
"""Update mission board: mer-B complete worker-side; saturation window; gate armed."""
import json, time

P = "/home/z/replay2/data/mission-state.json"
d = json.load(open(P))
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

d["updatedAt"] = now
d["mission"]["subtitle"] = (
    "Repository is the only source of truth (payswapdotorg/PaySwap-3.0 @ c5a4dc7, "
    "PAT era — pushes live). R3: route-compiler + onchain-extensions MERGED; merchant "
    "COMPLETE worker-side (25f/353t oracle-exact) — app-root delivery waiting out the "
    "17:20Z+ generation-saturation window (auto-harvest armed). R4 packets staged; "
    "ladder + saturation gate carry the dispatch. P8 certification last."
)

for it in d["items"]:
    if it.get("id") == "r3-w3":
        it["status"] = "in_progress"
        it["title"] = ("merchant rebuild — WORKER-SIDE COMPLETE: 4 commits over e80c932 "
                       "(fea934d), battery 25f/353t ALL PASS, tsc 0; delivery to app root "
                       "blocked by the saturation window — renudge + auto-harvest armed")
    if it.get("id") == "r4-w1":
        it["status"] = "in_progress"
        it["title"] = ("lab rebuild — 4 fresh chats rolled back by the saturation window; "
                       "dispatch ladder (patched URL parsing) + saturation gate armed to "
                       "relaunch on window-clear")
    if it.get("id") == "ops-pat":
        it["status"] = "done"
        it["title"] = "OPERATOR ACTION — GitHub PAT installed (x-access-token); pushes live (c5a4dc7)"

for ln in d.get("lanes", []):
    if ln.get("id") == "r3":
        ln["scope"] = ("route-compiler MERGED c5a4dc7 + pushed; onchain-extensions e80c932; "
                       "merchant COMPLETE worker-side — delivery pending saturation window")
    if ln.get("id") == "r4":
        ln["scope"] = ("lab dispatch in ladder+gate custody (saturation window); "
                       "opportunities + security-ln packets staged for slot-free dispatch")

tl = d.get("timeline") or []
tl.append({"ts": now, "text": (
    "MER-B R3-W3 COMPLETE worker-side: worklog shows 4 commits over e80c932 (6580682 pins / "
    "9ae01a0 implementation / a8c7172 tests / fea934d spec+evidence), battery 25 files / 353 "
    "tests ALL PASS (oracle-exact), tsc 0, census 43+30 files, deviations D1-D5 recorded. "
    "Delivery artifacts staged at the worker home dir — TL delivery order sent (copy to app "
    "root) but the 17:20Z+ saturation window kills every generation attempt ('No response' + "
    "HTML error pages). Renudge loop + slow-pulse gate nudges carry the retry; auto-harvest "
    "fires the moment markers reach the app root.")})
tl.append({"ts": now, "text": (
    "SATURATION-ERA HARDENING: r4-w1 ladder burned 4 attempts (b/c/d/e all rolled back — "
    "fresh chats die while established chats survive); ladder URL-parse bug found + patched "
    "(registry-based chat lookup — it was abandoning every chat it created); saturation gate "
    "armed: watches mer-B for window-clear (2 consecutive clean probes), kills the old-code "
    "ladder, voids dead r4-w1 chats, relaunches the patched ladder. PAT-era pushes verified "
    "(origin/main = c5a4dc7).")})
d["timeline"] = tl[-40:]

json.dump(d, open(P, "w"), indent=2)
print("mission board updated:", now)
