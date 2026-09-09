#!/usr/bin/env python3
"""custodian.py — third ring of the immortality ring (anti-OOM backstop).

Forensics (2026-09-09): the sandbox OOM killer (4GB RAM; chrome 2.1GB +
next-server 1GB) periodically kills processes. The watcher<->supervisor
pair survives single deaths, but one OOM burst can kill BOTH in the same
instant — after which nothing resurrects them ("the watcher died").

Ring of three (any two alive heal the third):
  watcher.py   — resurrects supervisor (PID) + custodian (PID), ~2min
  supervisor.py— resurrects watcher (PID + heartbeat-hang), 10s
  custodian.py — THIS: resurrects the PAIR if both die; also SIGKILLs
                 hung-but-alive instances via heartbeat staleness. 30s.

All pairs covered:
  W dead      -> S (10s) / C (backstop)
  S dead      -> C (30s) / W (~2min)
  C dead      -> W (~2min)
  W+S dead    -> C
  W+C dead    -> S restarts W, W restarts C
  S+C dead    -> W restarts both
  all three   -> only a sandbox reset; resident agent re-bootstraps (worklog)

Design constraints: NO CDP, NO HTTP, NO subprocess in the steady state —
only /proc + flag-file reads. ~15MB RSS, no hang paths, unattractive OOM
target (chrome at 2.1GB dies first; oom_score_adj on chrome is +300).

Single-instance: flock on flags/custodian.lock (same adoption pattern as
the supervisor). Run detached:
  nohup setsid /home/z/.venv/bin/python3 scripts/custodian.py \
      >> scripts/logs/custodian.log 2>&1 &
"""
import fcntl
import os
import subprocess
import time

BASE = "/home/z/my-project/scripts"
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOG = os.path.join(LOGDIR, "custodian.log")
PIDFILE = os.path.join(BASE, "custodian.pid")
LOCK = os.path.join(FLAGS, "custodian.lock")
PY = "/home/z/.venv/bin/python3"

SUP_HB = os.path.join(FLAGS, "supervisor_heartbeat")
WAT_HB = os.path.join(FLAGS, "watcher_heartbeat")

# thresholds (s): heartbeat cadences are 10s (sup/wat) / 120s (queue_watch).
# generous margins so a busy-but-healthy process is never misjudged.
SUP_STALE = 120     # supervisor heartbeat stale beyond this = hung
WAT_STALE = 300     # watcher: custodian acts LATER than supervisor's 180s
PROC_GRACE = 180    # a process younger than this is exempt (startup window)


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def pid_alive(pid, needle=""):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
        if needle and needle not in cmd:
            return False
        return True
    except Exception:
        return False


def read_pid(path):
    try:
        return open(path).read().strip()
    except Exception:
        return ""


def proc_start_epoch(pid):
    """Process start time as epoch seconds (0 on failure)."""
    try:
        with open(f"/proc/{int(pid)}/stat") as f:
            st = f.read()
        after = st[st.rindex(")") + 2:].split()
        ticks = int(after[19])                       # field 22 (starttime)
        btime = int(open("/proc/stat").read().split("btime")[1].split()[0])
        hz = os.sysconf("SC_CLK_TCK") or 100
        return btime + ticks / hz
    except Exception:
        return 0


def hb_age(path):
    """Age of a heartbeat flag in seconds (huge if missing)."""
    try:
        return max(0.0, time.time() - os.path.getmtime(path))
    except Exception:
        return 1e9


def find_pid(needle, pidfile):
    """PID from pidfile if valid, else first pgrep match (pidfile healed)."""
    pid = read_pid(pidfile)
    if pid_alive(pid, needle):
        return pid
    try:
        r = subprocess.run(["pgrep", "-f", needle], capture_output=True, text=True)
        for p in (r.stdout or "").split("\n"):
            if p.strip() and pid_alive(p.strip(), needle):
                try:
                    open(pidfile, "w").write(p.strip())
                except Exception:
                    pass
                return p.strip()
    except Exception:
        pass
    return ""


def kill_hung(pid, what, age):
    log(f"{what} HUNG (pid {pid}, heartbeat {int(age)}s stale) — SIGKILL")
    try:
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)
    except Exception:
        pass


def launch(pyfile, what, out_name):
    out = open(os.path.join(LOGDIR, out_name), "a")
    subprocess.Popen([PY, os.path.join(BASE, pyfile)],
                     stdout=out, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    out.close()
    log(f"{what} relaunched ({pyfile})")


def guard_supervisor():
    pid = find_pid("supervisor.py", os.path.join(BASE, "supervisor.pid"))
    if not pid:
        log("supervisor DEAD — relaunching")
        launch("supervisor.py", "supervisor", "supervisor.err")
        return
    age = hb_age(SUP_HB)
    if age > SUP_STALE and (time.time() - proc_start_epoch(pid)) > PROC_GRACE:
        kill_hung(pid, "supervisor", age)
        launch("supervisor.py", "supervisor", "supervisor.err")
        # the fresh supervisor brings the watcher back if it died too


def guard_watcher():
    pid = find_pid("scripts/watcher.py", os.path.join(BASE, "watcher.pid"))
    if not pid:
        # supervisor (just ensured fresh) restarts it within 10s normally;
        # only act ourselves if it stays missing for 2 consecutive cycles
        if guard_watcher.missing_since == 0:
            guard_watcher.missing_since = time.time()
            log("watcher missing — giving the supervisor one cycle first")
            return
        if time.time() - guard_watcher.missing_since > 45:
            log("watcher still missing after 45s — relaunching directly")
            launch("launch_watcher.py", "watcher", "watcher_launch.log")
            guard_watcher.missing_since = 0
        return
    guard_watcher.missing_since = 0
    age = hb_age(WAT_HB)
    if age > WAT_STALE and (time.time() - proc_start_epoch(pid)) > PROC_GRACE:
        # supervisor's own hang-detection (180s) should have fired first;
        # reaching here means the supervisor path failed — belt and braces.
        kill_hung(pid, "watcher", age)
        launch("launch_watcher.py", "watcher", "watcher_launch.log")


guard_watcher.missing_since = 0


def heartbeat():
    try:
        with open(os.path.join(FLAGS, "custodian_heartbeat"), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def main():
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another custodian already holds the lock — exiting", flush=True)
        return 0
    open(PIDFILE, "w").write(str(os.getpid()))
    log(f"custodian online (pid {os.getpid()}) — guarding supervisor+watcher pair")
    while True:
        try:
            guard_supervisor()
            guard_watcher()
            heartbeat()
        except Exception as e:
            log(f"cycle error {e!r} — continuing")
        time.sleep(30)


if __name__ == "__main__":
    # IMMORTAL: even a crash in main() restarts (watcher also guards us).
    while True:
        try:
            rc = main()
            if rc is not None:
                log(f"main() returned {rc} — relaunching in 15s")
        except Exception as e:
            log(f"FATAL in main: {e!r} — restarting in 15s")
        time.sleep(15)
