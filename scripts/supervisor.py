#!/usr/bin/env python3
"""supervisor.py — makes the whole resident stack immortal.

Single-instance daemon (flock-guarded). Every 10s it verifies and, when dead,
automatically restarts:
  1. watcher.py        (login / branch / write-access / dialog / inbox monitor)
  2. Chrome CDP :9222  (+ Xvfb :99 via launch_stack.py)
  3. dev server :3000  (operator console)
  4. replayd    :3100  (persistent CDP daemon — realtime frames + drags)

Also rotates logs so nothing grows unbounded, and touches
flags/supervisor_heartbeat (distinct from the agent heartbeat flag).
This process itself is launched detached (setsid) so it survives CLI session
resets; if IT is ever killed, any later `launch_supervisor` run will adopt the
role thanks to the flock. The custodian.py (third ring member) additionally
guards the supervisor+watcher PAIR against simultaneous OOM death, and the
watcher resurrects the custodian — ring of three, any two heal the third.

Run: nohup setsid /home/z/.venv/bin/python3 scripts/supervisor.py \
        >> scripts/logs/supervisor.log 2>&1 &
"""
import fcntl
import json
import os
import subprocess
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
os.makedirs(FLAGS, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "supervisor.log")
PIDFILE = os.path.join(BASE, "supervisor.pid")
LOCK = os.path.join(FLAGS, "supervisor.lock")

PY = "/home/z/.venv/bin/python3"
MAX_LOG = 2 * 1024 * 1024      # rotate above 2MB
KEEP_TAIL = 150 * 1024         # keep last 150KB


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


def http_ok(url, timeout=4):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(64)
        return True
    except Exception:
        return False


def read_pid(path):
    try:
        return open(path).read().strip()
    except Exception:
        return ""


def hb_age(path):
    """Age of a heartbeat flag in seconds (huge if missing)."""
    try:
        return max(0.0, time.time() - os.path.getmtime(path))
    except Exception:
        return 1e9


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


def rotate_logs():
    for name in ("watcher.log", "channel.log"):
        p = os.path.join(BASE, name)
        _rotate(p)
    for name in ("supervisor.log",):
        _rotate(os.path.join(LOGDIR, name))
    _rotate(os.path.join(BASE, "dev.log"))


def _rotate(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_LOG:
            with open(path, "rb") as f:
                f.seek(-KEEP_TAIL, 2)
                tail = f.read()
            with open(path, "wb") as f:
                f.write(tail)
    except Exception:
        pass


def ensure_capacity_recovery():
    """Keep the GLM-5.3 capacity-recovery pollers alive while flags exist.

    Flags (flags/capacity_recover*.json — one PER exhausted session; the
    legacy single capacity_recover.json is still honored) are written when a
    session needs send-recovery; recover_capacity.py removes its flag when
    done (or the session died). While a flag exists, a dead poller for THAT
    flag is relaunched automatically. Per-flag pidfiles prevent cross-talk.
    """
    import glob as _glob
    for flag in sorted(_glob.glob(os.path.join(FLAGS, "capacity_recover*.json"))):
        stem = os.path.basename(flag)[len("capacity_recover"):-len(".json")] or ""
        pidf = os.path.join(FLAGS, f"capacity_recover.pid{stem}")
        pid = read_pid(pidf)
        if pid and pid_alive(pid, "recover_capacity"):
            continue  # alive
        log(f"capacity recovery poller dead but flag present ({os.path.basename(flag)}) — relaunching")
        with open(flag) as f:
            spec = json.load(f)
        # the aggressive assault needs name+prompt_file (uuid alone is legacy)
        if not (spec.get("name") and spec.get("prompt_file")):
            # legacy flag: let recover_capacity resolve it via the registry
            if not spec.get("uuid"):
                continue
        out = open(os.path.join(LOGDIR, "recover.log"), "a")
        subprocess.Popen(
            [PY, os.path.join(BASE, "recover_capacity.py"), flag, spec.get("uuid", "")],
            stdout=out, stderr=out, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        out.close()


def ensure_tab_gc():
    """Close leaked chat-home tabs (crashed creates leak one tab each; they
    exhaust the renderer and cause the CDP websocket timeouts). Keeps the
    newest 2 home tabs for in-flight dispatches; session tabs (/c/) never."""
    try:
        import urllib.request
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:3100/tabs", timeout=10))
        home = [t for t in tabs.get("tabs", [])
                if (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
        for t in home[2:]:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + t["id"], timeout=5).read()
            except Exception:
                pass
    except Exception:
        pass


def ensure_watcher():
    # 1. liveness: pidfile, then pgrep fallback (heals stale pidfile)
    pid = read_pid(os.path.join(BASE, "watcher.pid"))
    if not pid_alive(pid, "watcher.py"):
        r = subprocess.run(["pgrep", "-f", "scripts/watcher.py"], capture_output=True, text=True)
        pid = r.stdout.strip().split("\n")[0] if r.stdout.strip() else ""
    if pid:
        try:
            open(os.path.join(BASE, "watcher.pid"), "w").write(str(pid))
        except Exception:
            pass
        # 2. HANG detection: alive-but-stuck is NOT alive. The watcher writes
        # watcher_heartbeat every 10s; its slow checks take <=~60s. Stale
        # beyond 180s = hung (OOM-thrash / stuck syscall) — SIGKILL so the
        # restart always yields a fresh process. The PROC_GRACE startup
        # window prevents killing a watcher that just launched and has not
        # yet written its first heartbeat (stale flag from predecessor).
        age = hb_age(os.path.join(FLAGS, "watcher_heartbeat"))
        if age > 180 and (time.time() - proc_start_epoch(pid)) > 180:
            log(f"watcher HUNG (pid {pid}, heartbeat {int(age)}s stale) — SIGKILL + restart")
            try:
                subprocess.run(["kill", "-9", str(pid)], capture_output=True)
            except Exception:
                pass
            time.sleep(1)
        else:
            return False
    log("watcher DEAD — restarting")
    subprocess.Popen([PY, os.path.join(BASE, "launch_watcher.py")],
                     stdout=open(os.path.join(LOGDIR, "watcher_launch.log"), "a"),
                     stderr=subprocess.STDOUT)
    return True


def ensure_browser():
    if http_ok("http://127.0.0.1:9222/json/version"):
        return False
    log("Chrome CDP DEAD — restarting stack (Xvfb + Chrome)")
    # Xvfb may be dead too; launch_stack restarts both (a duplicate Xvfb simply
    # fails to bind and exits, which is harmless)
    subprocess.run([PY, os.path.join(BASE, "launch_stack.py")], timeout=120,
                   stdout=open(os.path.join(LOGDIR, "stack_launch.log"), "a"),
                   stderr=subprocess.STDOUT)
    return True



DEV_PATIENCE = 240  # s: a non-listening dev process gets this long before forced restart


def _dev_down_since():
    """First-sighting timestamp for 'port down but process alive' (or None)."""
    p = os.path.join(FLAGS, "dev_down_since")
    try:
        return float(open(p).read().strip())
    except Exception:
        try:
            now = time.time()
            open(p, "w").write(str(now))
        except Exception:
            pass
        return None


def _rm_devstate():
    try:
        os.remove(os.path.join(FLAGS, "dev_down_since"))
    except Exception:
        pass

def ensure_dev():
    if http_ok(f"http://127.0.0.1:3000"):
        _rm_devstate()
        return False
    # Port down does NOT mean the process is dead: a cold compile (empty or
    # corrupted .next cache) can take a minute before the port binds. Spawning
    # a second dev server during that window creates a stampede (concurrent
    # next-server compiles -> OOM kills -> EADDRINUSE zombies). Guard on
    # process liveness first; force-restart only after DEV_PATIENCE seconds.
    r = subprocess.run(["pgrep", "-f", "next dev|bun run dev|next-server"],
                       capture_output=True, text=True)
    pids = [p for p in r.stdout.strip().split("\n") if p.strip()]
    if pids:
        first = _dev_down_since()
        if first and time.time() - first > DEV_PATIENCE:
            log("dev server :3000 not up for " + str(int(time.time() - first)) + "s with process alive — killing wedged dev, restarting")
            for p in pids:
                subprocess.run(["kill", p], capture_output=True)
            _rm_devstate()
            subprocess.Popen([PY, os.path.join(BASE, "launch_dev.py")],
                             stdout=open(os.path.join(LOGDIR, "dev_launch.log"), "a"),
                             stderr=subprocess.STDOUT)
            return True
        return False  # still starting — be patient, do NOT stampede
    log("dev server :3000 DEAD — restarting")
    subprocess.Popen([PY, os.path.join(BASE, "launch_dev.py")],
                     stdout=open(os.path.join(LOGDIR, "dev_launch.log"), "a"),
                     stderr=subprocess.STDOUT)
    return True


def ensure_replayd():
    if http_ok("http://127.0.0.1:3100/healthz"):
        return False
    log("replayd :3100 DEAD — restarting")
    subprocess.Popen([PY, os.path.join(BASE, "launch_replayd.py")],
                     stdout=open(os.path.join(LOGDIR, "replayd_launch.log"), "a"),
                     stderr=subprocess.STDOUT)
    return True


def heartbeat():
    try:
        p = os.path.join(FLAGS, "supervisor_heartbeat")
        with open(p, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def ensure_queue_watch():
    """Resurrect queue_watch.py for every flags/queue_watch.spec.<name>.

    Multi-watch (wave-4+): each spec file names ONE session; a watcher owns
    exactly one. The spec is written by queue_watch.py itself; it removes the
    spec when the watched session completes, which retires the guard. Also
    SIGKILLs a HUNG instance (queue_watch_heartbeat.<name> stale beyond 600s —
    its loop is ~120s sleep + <=~60s of CDP work; forensic case 2026-09-09:
    an instance sat hung-but-alive for 40 minutes with nobody noticing).
    """
    import glob as _glob
    for spec_path in sorted(_glob.glob(os.path.join(FLAGS, "queue_watch.spec.*"))):
        try:
            spec = json.loads(open(spec_path).read().strip() or "{}")
        except Exception:
            continue
        name = spec.get("name", "")
        pid = spec.get("pid")
        if pid and pid_alive(pid, "queue_watch"):
            age = hb_age(os.path.join(FLAGS, f"queue_watch_heartbeat.{name}"))
            if age > 600 and (time.time() - proc_start_epoch(pid)) > 600:
                log(f"queue_watch[{name}] HUNG (pid {pid}, heartbeat {int(age)}s stale) — SIGKILL + restart")
                try:
                    subprocess.run(["kill", "-9", str(pid)], capture_output=True)
                except Exception:
                    pass
                time.sleep(1)
            else:
                continue
        # alive under a different pid for THIS session? (match by name arg)
        r = subprocess.run(["pgrep", "-f", f"scripts/queue_watch.py {name} "],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            p = r.stdout.strip().split("\n")[0]
            try:
                spec["pid"] = p
                open(spec_path, "w").write(json.dumps(spec) + "\n")
            except Exception:
                pass
            continue
        log(f"queue_watch[{name}] DEAD — restarting (spec present)")
        args = [PY, os.path.join(BASE, "queue_watch.py"),
                name, spec.get("tab_prefix", ""), spec.get("marker", "")]
        subprocess.Popen(args, stdout=open(os.path.join(LOGDIR, "queue-watch.log"), "a"),
                         stderr=subprocess.STDOUT)
        log(f"queue_watch[{name}] restarted: tab={spec.get('tab_prefix')}")


def main():
    # single-instance guard
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another supervisor already holds the lock — exiting", flush=True)
        return 0
    open(PIDFILE, "w").write(str(os.getpid()))
    log(f"supervisor online (pid {os.getpid()}) — watching watcher/CDP/dev")

    cycle = 0
    while True:
        try:
            ensure_watcher()
            ensure_replayd()
            ensure_capacity_recovery()
            ensure_tab_gc()
            ensure_queue_watch()
            if cycle % 3 == 0:          # browser check every ~30s
                ensure_browser()
                ensure_dev()
                rotate_logs()
            heartbeat()
        except Exception as e:
            log(f"cycle error {e!r} — continuing")
        cycle += 1
        time.sleep(10)


if __name__ == "__main__":
    main()
