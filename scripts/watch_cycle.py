#!/usr/bin/env python3
"""watch_cycle.py — one compact monitoring line for the Lead's resident loop."""
import glob
import os
import subprocess
import time

F = "/home/z/replay2/scripts/flags"
now = time.strftime("%H:%M:%S")

def tail1(p):
    try:
        return open(p).read().strip().splitlines()[-1][:100]
    except Exception:
        return "-"

probe = tail1("/tmp/freeze_probe_watch.log")
recovered = "RECOVERED!" if os.path.exists(f"{F}/backend_recovered.txt") else "armed"
p033 = "P033-DONE" if os.path.exists(f"{F}/prod033-complete.marker") else "-"
h302 = "H302-DONE" if os.path.exists(f"{F}/hfx302-complete.marker") else "-"
er = tail1("/home/z/replay2/scripts/logs/endgame_recover.log")
nproc = int(subprocess.run(["bash", "-c",
    "pgrep -c -f 'freeze_probe_watch|endgame_recover|lane_watch|frame_guard|waveB_completion|supervisor'"],
    capture_output=True, text=True).stdout.strip() or "0")
newest = max(glob.glob(f"{F}/*"), key=os.path.getmtime, default="?")
newest = os.path.basename(newest) + " " + time.strftime("%H:%M", time.localtime(os.path.getmtime(newest)))

print(f"[{now} UTC] probe: {probe}")
print(f"  chain:{recovered} workers:{p033}/{h302} procs:{nproc}/6 newest-flag:{newest}")
print(f"  recover: {er}")
