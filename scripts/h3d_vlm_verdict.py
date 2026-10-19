#!/usr/bin/env python3
"""h3d_vlm_verdict.py — the Task 20/22 close-out verdict.

Compares the clone's neural-run poster against the banked REAL
Hunyuan3D-2.1 engine output (same engine, same input apple photo —
hunyuan3d21_apple_10k_preview.png from the 2026-10-18 engine recon)
with a fixed rubric via the z-ai vision CLI.

Usage:
  python3 h3d_vlm_verdict.py <candidate.png> [more.png ...]
    (defaults pick the FIRST existing of:
     e2e20-05-viewer.png — the e2e's CURRENT run shot (overwritten each
       cycle, so right after a neural success it holds the neural viewer)
     e2e20-neural-05.png — the raw agent-browser loop's success shots
     e2e20-cdp-neural-05-viewer.png — the CDP loop's post-success copy
       (HAZARD: a stale pre-audit false-positive file may sit under this
        name from the 2026-10-19 02:45Z FP — always prefer the first two)

Rubric (fixed for comparability with the banked baselines):
  reference-vs-fallback poster = 4/10 (2026-10-19 21:30Z dry run)
  reference itself = 8/10 (Task 19 verdict context)
  close-out threshold for the neural poster: >= 6/10

Artifacts: research/out/e2e20-vlm-verdict.json (+ echo to stdout)
"""
import json
import subprocess
import sys
import time

REF = "/home/z/my-project/research/out/hunyuan3d21_apple_10k_preview.png"
OUT = "/home/z/my-project/research/out/e2e20-vlm-verdict.json"
DEFAULTS = [
    "/home/z/my-project/research/out/e2e20-05-viewer.png",
    "/home/z/my-project/research/out/e2e20-neural-05.png",
    "/home/z/my-project/research/out/e2e20-cdp-neural-05-viewer.png",
]

PROMPT = (
    "Image 1 is the REFERENCE output of the Hunyuan3D-2.1 engine "
    "(image-to-3D of an apple photo). Image 2 is a CANDIDATE 3D render "
    "from a web app that should be reproducing that engine. Score how "
    "faithfully the candidate reproduces the reference's shape quality "
    "(mesh fidelity, silhouette, stem, proportions) on a 1-10 scale. "
    "Answer with just: SCORE: n/10, then one sentence why."
)


def main():
    cands = sys.argv[1:]
    if not cands:
        import os
        cands = [p for p in DEFAULTS if os.path.isfile(p)]
    if not cands:
        print("no candidate poster found — pass one explicitly")
        return 2
    cand = cands[0]

    cmd = ["z-ai", "vision", "-p", PROMPT, "-i", REF, "-i", cand,
           "-o", OUT.replace(".json", "-raw.json")]
    print(f"[verdict] reference: {REF}")
    print(f"[verdict] candidate: {cand}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                       cwd="/home/z/my-project")
    raw_path = OUT.replace(".json", "-raw.json")
    content = None
    try:
        with open(raw_path) as f:
            content = json.load(f)["choices"][0]["message"]["content"]
    except Exception:
        print("vision call failed:", (r.stdout or "")[-200:], (r.stderr or "")[-200:])
        return 3

    score = None
    for tok in content.replace("/", " ").split():
        try:
            n = int(tok)
            if 1 <= n <= 10:
                score = n
                break
        except ValueError:
            continue

    record = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reference": REF, "candidate": cand, "content": content,
        "score": score, "threshold": 6,
        "verdict": ("PASS" if score is not None and score >= 6 else
                    "FAIL" if score is not None else "UNPARSED"),
        "baselines": {"reference_self": 8, "fallback_poster": 4,
                      "note": "fallback 4/10 dry-run 2026-10-19T21:30Z, "
                              "lathe ceiling documented 3/10 in Task 19"},
    }
    with open(OUT, "w") as f:
        json.dump(record, f, indent=2)
    print(json.dumps(record, indent=2))
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
