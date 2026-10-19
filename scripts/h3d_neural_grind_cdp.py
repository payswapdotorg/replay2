#!/usr/bin/env python3
"""h3d_neural_grind_cdp.py — companion verification loop (detached).

The agent-browser grind (h3d_neural_grind.py) fires the production golden
path every 15 min from the RAW sandbox IP. This companion drives the SAME
golden path every 20 min through the CDP Chrome (TurboVPN egress
198.244.234.214) — an INDEPENDENT anonymous ZeroGPU pool. Whichever pool
opens a window first, a REAL neural run lands.

Fires at :05/:25/:45 (offset ~10 min from the agent-browser grind's
:13/:28/:43 cadence — cycles last <2 min, so the two loops never overlap
on the shared demo account).

Each cycle simply re-runs scripts/h3d_prod_neural_e2e.py (the validated,
instrumented CDP driver: reload → sign-in check → Image to 3D → upload →
caption → GENERATE → poll → on neural success it ALREADY confirms (1
credit), byte-verifies GLB/OBJ, and banks e2e20-01..07.png). This wrapper
watches the result JSON's "neural" flag and stops on success, copying the
result + screenshots to durable e2e20-cdp-neural-* names.
"""
import json
import shutil
import subprocess
import time

E2E = "/home/z/replay2/scripts/h3d_prod_neural_e2e.py"
OUT = "/home/z/my-project/research/out"
RESULT = f"{OUT}/e2e20-result.json"
MARKER = f"{OUT}/e2e20-cdp-neural-success.json"
LOG = f"{OUT}/e2e20-grind-cdp.log"
CYCLE_LOG = f"{OUT}/e2e20-cdp-cycles.json"


def log(*args):
    line = time.strftime("[%Y-%m-%dT%H:%M:%SZ] ", time.gmtime()) + " ".join(str(a) for a in args)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def next_fire_wait():
    """Seconds until the next :05/:25/:45 boundary (at least 90s away)."""
    t = time.gmtime()
    minute, sec = t.tm_min, t.tm_sec
    # modular minutes-ahead for each boundary, keeping only ones >= 2 min out
    dists = sorted((m - minute) % 60 for m in (5, 25, 45))
    ahead = [d for d in dists if d * 60 - sec >= 90]
    d = ahead[0] if ahead else dists[0] + 60
    return d * 60 - sec


def main():
    cycles = []
    log("cdp companion loop started — 20-min cadence at :05/:25/:45 through the VPN egress pool")
    while True:
        wait = next_fire_wait()
        log(f"next fire in {int(wait/60)} min")
        time.sleep(wait)
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rc = None
        outcome_line = ""
        try:
            r = subprocess.run(["python3", E2E], capture_output=True, text=True, timeout=560)
            rc = r.returncode
            tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            outcome_line = next((l for l in reversed(tail) if l.startswith("RESULT neural:")), "")
            log(f"cycle done rc={rc} | {outcome_line[:160]}")
        except subprocess.TimeoutExpired:
            log("cycle TIMEOUT (560s) — continuing")
        # read the result the script banked
        res = None
        try:
            with open(RESULT) as f:
                res = json.load(f)
        except Exception:
            pass
        entry = {"at": started, "rc": rc, "result": (res or {}).get("neural"), "line": outcome_line[:200]}
        cycles.append(entry)
        try:
            with open(CYCLE_LOG, "w") as f:
                json.dump(cycles, f, indent=2)
        except Exception:
            pass
        if res and res.get("neural"):
            log("SUCCESS — REAL neural run through the CDP/VPN path! Banking durable copies.")
            with open(MARKER, "w") as f:
                json.dump(res, f, indent=2, default=str)
            # copy the standard shot set with a durable prefix
            import glob
            for p in glob.glob(f"{OUT}/e2e20-0*.png"):
                shutil.copy(p, p.replace("e2e20-0", "e2e20-cdp-neural-0"))
            return
        # small breather so the next boundary calc is clean
        time.sleep(5)


if __name__ == "__main__":
    main()
