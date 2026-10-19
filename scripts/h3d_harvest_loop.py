#!/usr/bin/env python3
"""h3d_harvest_loop.py — keep re-running harvest_robust (resumable) until
the base/ tree is fully harvested. Survives the intermittent 'Failed to
fetch' bursts (VPN proxy drops) that crash single-shot harvests.
"""
import os
import subprocess
import sys
import time

BASE = "/home/z/replay2"
CHAT = "2ec65694-072c-418c-bce7-6fdddd3c572f"
WS = "ws-c405d9e9-8884-4c85-9926-9233df5cc173"
LOCAL = "/home/z/h3d-harvest/build"

def count_files():
    n = 0
    for _root, _dirs, files in os.walk(LOCAL):
        n += len(files)
    return n

def main():
    for attempt in range(1, 41):
        n0 = count_files()
        print(f"[{time.strftime('%H:%M:%S')}] attempt {attempt}: {n0} files on disk", flush=True)
        p = subprocess.run(
            ["python3", os.path.join(BASE, "scripts", "harvest_robust.py"),
             CHAT, WS, "base", LOCAL],
            cwd=BASE, timeout=1800,
        )
        n1 = count_files()
        print(f"[{time.strftime('%H:%M:%S')}] exit={p.returncode} files {n0}->{n1}", flush=True)
        if p.returncode == 0:
            print("HARVEST-COMPLETE", flush=True)
            with open(os.path.join(BASE, "scripts/flags", "H3D_HARVEST_DONE"), "w") as f:
                f.write(str(int(time.time())))
            return
        time.sleep(20)
    print("GAVE-UP-AFTER-40", flush=True)

if __name__ == "__main__":
    main()
