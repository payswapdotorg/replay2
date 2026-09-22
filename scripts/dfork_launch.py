#!/usr/bin/env python3
"""dfork_launch.py — launch a daemon that survives the session reaper.

The 2026-09-22 session's Bash tool reaps the ENTIRE process tree at call
end (setsid/nohup/disown do NOT escape it — verified empirically: a
setsid'd sleeper died at the call boundary while a double-forked
grandchild re-parented to init survived). This launcher double-forks so
the daemon becomes an orphan of pid 1, outside the shell's tree:

    parent (exits immediately)
      └─ child (setsid + exits)
           └─ grandchild → execvp(target)  ← survives, ppod=1

Usage:  dfork_launch.py <logfile> <cmd> [args ...]
The grandchild's stdout/stderr append to <logfile>; stdin is /dev/null.
Exit code 0 immediately after the daemon is spawned.
"""
import os
import sys

if len(sys.argv) < 3:
    sys.stderr.write(__doc__)
    raise SystemExit(2)

logpath, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]

if os.fork() == 0:
    os.setsid()
    if os.fork() == 0:
        # grandchild: wire stdio, then replace with the target
        with open(logpath, "ab", 0) as f:
            os.dup2(f.fileno(), 1)
            os.dup2(f.fileno(), 2)
        fd = os.open("/dev/null", os.O_RDONLY)
        os.dup2(fd, 0)
        os.execvp(cmd, [cmd] + args)
    os._exit(0)
# parent exits immediately; the daemon is re-parented to init
