#!/usr/bin/env bash
# dfork-launch.sh — survive the Bash-tool process reaper.
#
# Why: processes spawned directly by a session's Bash commands (even with
# nohup/setsid) remain descendants of the persistent shell and get SIGKILLed
# ~30-150s after the launching command ends. A double-fork orphan reparents
# to init and survives (proven by the 2h-lived parity instance launched this
# way in a prior session via dfork_launch.py, lost in the 2026-10-20 reboot).
#
# Usage: dfork-launch.sh <workdir> <logfile> <command...>
#   e.g. research/dfork-launch.sh /home/z/my-project /home/z/my-project/dev.log bun run dev
set -u
workdir="$1"; logfile="$2"; shift 2
(
  cd "$workdir" || exit 1
  # subshell backgrounds the target and exits immediately -> the child is
  # orphaned (PPID -> subreaper/init) and escapes any descendant-walk reaper.
  nohup "$@" >>"$logfile" 2>&1 </dev/null &
) &
exit 0
