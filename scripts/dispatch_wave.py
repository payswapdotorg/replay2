#!/usr/bin/env python3
"""dispatch_wave.py <w1xx> [<w1yy> <w1zz> ...] — rapid multi-dispatch (detached).

Fires dispatch_worker.py create for each named worker packet
(scripts/worker-prompts/<name>.md), detached per §13 (long dispatches must
survive the tool shell). Run the moment the capacity window opens.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "worker-prompts")


def main():
    names = sys.argv[1:]
    if not names:
        print(__doc__)
        return 2
    for name in names:
        packet = os.path.join(PROMPTS, f"{name}.md")
        if not os.path.exists(packet):
            print(f"MISSING PACKET: {packet}")
            continue
        log = open(os.path.join(HERE, "logs", f"dispatch-{name}.log"), "a")
        subprocess.Popen(
            ["python3", os.path.join(HERE, "dispatch_worker.py"), "create", name, packet],
            stdout=log, stderr=log, start_new_session=True, cwd=HERE)
        print(f"dispatched (detached): {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
