#!/usr/bin/env python3
"""vpn_heal.py — the browser-egress keeper.

REBUILT 2026-10-16 (recycle #24/#25 wiped the runtime-only original; this
faithfully restores the drought-breakthrough-1 spec, field-proven through
the 2026-10-15/16 capacity siege):

  - every PROBE_EVERY seconds, run `vpn_connect.py status` — the popup-
    renderer fetch probe (the popup page is extension-local, never wedged
    by chat.z.ai retry-storms, and its fetch goes through the process-wide
    tunnel, so it is the honest egress truth for the BROWSER);
  - GOOD = a line starting `egress: EGRESS` (the probe returned an IP);
  - lesson-72 law: on FAIL_THRESHOLD consecutive bad probes, run the full
    `vpn_connect.py` heal one-shot (dead-tunnel toggle: disconnect ->
    reconnect -> verify). VPN node rotation flaps the egress every few
    minutes — the 2-failure window tolerates single flaps without
    thrashing the popup with toggles;
  - heartbeat every cycle: flags/vpn_heal_hb = "<epoch> ok fails=N".

The completions sends (worker dispatch, canaries) die with the 405 ESA
edge-block class whenever the browser egress falls back to the sandbox IP,
so this keeper is a hard dependency of the whole dispatch machine.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
HB_PATH = os.path.join(BASE, "flags", "vpn_heal_hb")
VPN_CONNECT = os.path.join(BASE, "vpn_connect.py")
PROBE_EVERY = 45          # seconds between egress probes
FAIL_THRESHOLD = 2        # consecutive bad probes before the lesson-72 toggle
PY = sys.executable


def log(msg):
    print(f"[vpn_heal {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe_egress():
    """True iff the popup egress probe returned an IP."""
    try:
        r = subprocess.run(
            [PY, VPN_CONNECT, "status"],
            capture_output=True, text=True, timeout=90, cwd=BASE,
        )
    except subprocess.TimeoutExpired:
        return False
    out = r.stdout or ""
    return any(line.startswith("egress: EGRESS") for line in out.splitlines())


def heal():
    """The full lesson-72 one-shot: dead-tunnel toggle / connect / verify."""
    try:
        r = subprocess.run(
            [PY, VPN_CONNECT],
            capture_output=True, text=True, timeout=180, cwd=BASE,
        )
        log("heal rc=%s :: %s" % (r.returncode, (r.stdout or "").strip().replace("\n", " | ")[:300]))
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        log("heal TIMEOUT")
        return False


def heartbeat(fails):
    try:
        os.makedirs(os.path.dirname(HB_PATH), exist_ok=True)
        with open(HB_PATH, "w") as f:
            f.write(f"{int(time.time())} ok fails={fails}\n")
    except OSError:
        pass


def main():
    log(f"keeper up (probe={PROBE_EVERY}s threshold={FAIL_THRESHOLD})")
    fails = 0
    while True:
        good = probe_egress()
        if good:
            if fails:
                log(f"egress GOOD again after {fails} bad probe(s)")
            fails = 0
        else:
            fails += 1
            log(f"egress BAD (consecutive={fails})")
            if fails >= FAIL_THRESHOLD:
                log(f"threshold hit — lesson-72 heal")
                if heal():
                    fails = 0
                else:
                    fails = FAIL_THRESHOLD  # stay armed to retry next cycle
        heartbeat(fails)
        time.sleep(PROBE_EVERY)


if __name__ == "__main__":
    main()
