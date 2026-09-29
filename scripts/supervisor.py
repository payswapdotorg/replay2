#!/usr/bin/env python3
"""supervisor.py — makes the whole resident stack immortal.

Single-instance daemon (flock-guarded). Every 10s it verifies and, when dead,
automatically restarts:
  1. watcher.py        (login / branch / write-access / dialog / inbox monitor)
  2. Chrome CDP :9222  (+ Xvfb :99 via launch_stack.py)
  3. dev server :$REPLAY_PORT  (operator console; default 3000)
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

# Resurrection-proof console port: env wins, then the deploy-written file,
# then 3000. The ring (custodian/watcher) resurrects this script WITHOUT env,
# so the file is what keeps every generation on the same port.
def _console_port():
    try:
        return int(os.environ.get("REPLAY_PORT", "") or
                   open(os.path.join(FLAGS, "console_port.txt")).read().strip())
    except Exception:
        return 3000
CONSOLE_PORT = _console_port()
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


def console_body_ok(port=None, timeout=4):
    if port is None:
        port = CONSOLE_PORT
    """True only when :port serves the REPLAY CONSOLE itself.

    http_ok() alone accepts ANY http server — after a sandbox reset the boot
    hook auto-starts my-project's `bun run dev` on :3000, and the supervisor
    would happily babysit the WRONG app while the operator stares at a page
    that can never show the replay/login. This check reads the body and
    demands the console identity marker.
    """
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/", timeout=timeout
        ).read(8192).decode("utf-8", "ignore")
        return "Replay Console" in body
    except Exception:
        return False


def _port_listeners(port=3000):
    """[(pid, cwd, cmdline)] for processes LISTENING on :port."""
    out = []
    try:
        ss = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True).stdout
    except Exception:
        return out
    for line in ss.splitlines():
        if f":{port} " not in line:
            continue
        import re
        for m in re.finditer(r"pid=(\d+)", line):
            pid = m.group(1)
            try:
                cwd = os.path.realpath(f"/proc/{pid}/cwd")
            except Exception:
                cwd = ""
            try:
                cmdline = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
            except Exception:
                cmdline = ""
            out.append((pid, cwd, cmdline))
    return out


def evict_port_squatters(port=3000):
    """Kill non-console listeners on :port (e.g. my-project boot-hook dev
    server). Returns human-readable list of evictions."""
    evicted = []
    for pid, cwd, cmdline in _port_listeners(port):
        if "replay2" in cwd or "replay2" in cmdline:
            continue  # our own console — keep
        subprocess.run(["kill", pid], capture_output=True)
        evicted.append(f"pid {pid} ({cwd or cmdline[:70]})")
    return evicted


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
    newest home tabs for in-flight dispatches; session tabs (/c/) never.

    2026-09-20 fix (lead): the /tabs listing is OLDEST-FIRST, so the old
    `home[2:]` kept the two OLDEST (leaked stale tabs) and closed the NEWEST
    — i.e. it killed live creates' tabs mid-shell-wait (the "err:socket is
    already closed" shell-stage failure storm of 10:2x-10:5x UTC). Keep the
    newest FOUR instead (three waves can assault concurrently + one spare).

    2026-09-27 fix (TL1 wave-3 crunch): the listing order is NOT stable —
    observed NEWEST-FIRST under Chrome 153 (a fresh liveness-probe tab died
    at +7s twice while four stale home tabs survived; home[:-4] closed the
    NEWEST tabs — the exact storm the 09-20 fix tried to prevent, reborn by
    ordering flip). Order-blind approach now:
      - every home tab gets a GRACE period (first-seen + GC_GRACE) before it
        is closeable — fresh creates/probes are protected by time, not order;
      - tabs named in live registry records (tab_id of create/send records)
        and the replayd active tab are NEVER closed;
      - beyond that, keep at most MAX_HOME tabs, closing the
        longest-first-seen first; leaked tabs (crashed creates) age out."""
    import time as _time
    GC_GRACE = 600      # s a newly-seen home tab is protected
    MAX_HOME = 4        # steady-state cap (3-wave assaults + spare)
    state_path = os.path.join(FLAGS, "tab_gc_state.json")
    try:
        state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    except Exception:
        state = {}
    now = _time.time()
    try:
        import urllib.request
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:3100/tabs", timeout=10))
        all_tabs = tabs.get("tabs", [])
        home = [t for t in all_tabs
                if (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
        # record first-seen for every current home tab; prune state for gone tabs
        seen_now = {t["id"] for t in home}
        for t in home:
            state.setdefault(t["id"], now)
        state = {k: v for k, v in state.items() if k in seen_now}
        # never close: registry-referenced tabs + replayd active tab
        keep_ids = set()
        try:
            reg_path = os.path.join(FLAGS, "session_registry.jsonl")
            if os.path.exists(reg_path):
                with open(reg_path) as fh:
                    for line in fh:
                        try:
                            r = json.loads(line)
                        except Exception:
                            continue
                        tid = r.get("tab_id")
                        if tid:
                            keep_ids.add(tid)
        except Exception:
            pass
        try:
            active = open(os.path.join(FLAGS, "active_tab.txt")).read().strip()
            if active:
                keep_ids.add(active)
        except Exception:
            pass
        # closeable: past grace, not protected
        closeable = [t for t in home
                     if t["id"] not in keep_ids
                     and now - state.get(t["id"], now) > GC_GRACE]
        closeable.sort(key=lambda t: state.get(t["id"], 0))  # oldest first-seen first
        excess = len(home) - MAX_HOME
        for t in closeable[:max(0, excess)]:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:9222/json/close/" + t["id"], timeout=5).read()
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            json.dump(state, open(state_path, "w"))
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

def _console_pids():
    """PIDs of THIS deployment's console: the tracked dev.pid (bun parent,
    if alive) plus any replay2 next-server child. Never matches sibling apps."""
    pids = []
    try:
        pid = open(os.path.join(FLAGS, "dev.pid")).read().strip()
        if pid.isdigit() and os.path.exists("/proc/" + pid):
            pids.append(pid)
    except Exception:
        pass
    r = subprocess.run(["pgrep", "-f", "replay2/node_modules/.bin/next"],
                       capture_output=True, text=True)
    for p in (r.stdout.strip().split("\n") if r.stdout else []):
        if p.strip() and p not in pids:
            pids.append(p)
    return pids


def _spawn_dev():
    env = dict(os.environ)
    env["REPLAY_PORT"] = str(CONSOLE_PORT)
    subprocess.Popen([PY, os.path.join(BASE, "launch_dev.py")],
                     stdout=open(os.path.join(LOGDIR, "dev_launch.log"), "a"),
                     stderr=subprocess.STDOUT, env=env)


def ensure_dev():
    if http_ok(f"http://127.0.0.1:{CONSOLE_PORT}"):
        if console_body_ok(CONSOLE_PORT):
            _rm_devstate()
            return False
        # Port is up but it is NOT our console — a squatter holds :3000
        # (sandbox boot hook auto-starts my-project's `bun run dev` there).
        # The operator would see the WRONG app and could never reach the
        # replay/login. Evict, wait for the port to free, then take over.
        evicted = evict_port_squatters(CONSOLE_PORT)
        if evicted:
            log(f"PORT GUARD: :{CONSOLE_PORT} held by non-console process(es): "
                + "; ".join(evicted) + " — evicted, console taking over")
            for _ in range(10):
                if not http_ok(f"http://127.0.0.1:{CONSOLE_PORT}"):
                    break
                time.sleep(1)
            _spawn_dev()
            return True
        # Port up, body check failed, but nobody evictable holds it — could be
        # our console mid-compile (cold .next renders no body yet). Be patient.
        return False
    # Port down does NOT mean the process is dead: a cold compile (empty or
    # corrupted .next cache) can take a minute before the port binds. Spawning
    # a second dev server during that window creates a stampede (concurrent
    # next-server compiles -> OOM kills -> EADDRINUSE zombies). Guard on
    # process liveness first; force-restart only after DEV_PATIENCE seconds.
    # Scope: ONLY this deployment's console processes — the tracked dev.pid
    # (bun parent) and its replay2 next-server child. NEVER pgrep all next/bun
    # dev servers: sibling apps (e.g. the my-project mirror on another port)
    # must survive a wedged-console restart. 2026-09-19 incident: the global
    # pgrep killed the :3200 console + the mirror during a CPU-saturation
    # health blip on :3000 and started a duplicate on the wrong port.
    pids = _console_pids()
    if pids:
        first = _dev_down_since()
        if first and time.time() - first > DEV_PATIENCE:
            log(f"dev server :{CONSOLE_PORT} not up for " + str(int(time.time() - first)) + "s with process alive — killing wedged dev, restarting")
            for p in pids:
                subprocess.run(["kill", p], capture_output=True)
            _rm_devstate()
            subprocess.Popen([PY, os.path.join(BASE, "launch_dev.py")],
                             stdout=open(os.path.join(LOGDIR, "dev_launch.log"), "a"),
                             stderr=subprocess.STDOUT)
            return True
        return False  # still starting — be patient, do NOT stampede
    log(f"dev server :{CONSOLE_PORT} DEAD — restarting")
    _spawn_dev()
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


def ensure_stall_recovery():
    """stall_recovery.py — dead-turn detector for worker sessions (frozen
    DOM + server-side open-empty assistant turn -> close tab so queue_watch's
    assault path re-dispatches). Born from the 2026-09-12 rwo-001/002
    forensic: both remediation turns died mid-stream and plain-'queued'
    sessions are never assaulted by queue_watch. pidfile first, pgrep
    fallback, heartbeat-stale SIGKILL (same contract as queue_watch)."""
    pidfile = os.path.join(BASE, "stall_recovery.pid")
    pid = read_pid(pidfile)
    if pid_alive(pid, "stall_recovery.py"):
        age = hb_age(os.path.join(FLAGS, "stall_recovery_heartbeat"))
        if age > 900 and (time.time() - proc_start_epoch(pid)) > 900:
            log("stall_recovery HUNG (heartbeat stale) — SIGKILL + restart")
            try:
                subprocess.run(["kill", "-9", str(pid)], capture_output=True)
            except Exception:
                pass
            time.sleep(1)
        else:
            return
    else:
        r = subprocess.run(["pgrep", "-f", "scripts/stall_recovery.py"],
                           capture_output=True, text=True)
        pid = r.stdout.strip().split("\n")[0] if r.stdout.strip() else ""
        if pid:
            try:
                open(pidfile, "w").write(pid)
            except Exception:
                pass
            return
    log("stall_recovery DEAD — restarting")
    subprocess.Popen(
        [PY, os.path.join(BASE, "stall_recovery.py")],
        stdout=open(os.path.join(LOGDIR, "stall_recovery.out"), "a"),
        stderr=subprocess.STDOUT, start_new_session=True)
    log("stall_recovery restarted")


def ensure_frame_guard():
    """frame_guard.py — console frame freshness watch (2026-09-24 stale-frame
    postmortem: replayd can serve 500s for hours while healthz stays green).
    Standalone by design upstream, but a dead guard silently re-opens the
    4.5h-frozen-preview gap, so the supervisor owns its resurrection
    (pidfile first, pgrep fallback; the guard itself only does local
    HTTP/CDP reads — restart is always safe)."""
    pidfile = os.path.join(BASE, "frame_guard.pid")
    pid = read_pid(pidfile)
    if pid_alive(pid, "frame_guard.py"):
        return
    r = subprocess.run(["pgrep", "-f", "scripts/frame_guard.py"],
                       capture_output=True, text=True)
    pid = r.stdout.strip().split("\n")[0] if r.stdout.strip() else ""
    if pid:
        try:
            open(pidfile, "w").write(pid)
        except Exception:
            pass
        return
    log("frame_guard DEAD — restarting (frame freshness watch)")
    subprocess.Popen(
        [PY, os.path.join(BASE, "frame_guard.py")],
        stdout=open(os.path.join(LOGDIR, "frame_guard.out"), "a"),
        stderr=subprocess.STDOUT, start_new_session=True)
    log("frame_guard restarted")


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



def _mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def ensure_local_services():
    """Keep per-deployment LOCAL daemons alive — a GENERIC mechanism (§0).

    The deployment's own daemons (whatever THIS sandbox is resident on —
    repo watches, pollers, any long-running local helper) are described in
    flags/local_services.json (gitignored per-sandbox runtime state):

        {"services": [
            {"name": "<label>", "cmd": ["<argv0>", "<argv1>", ...],
             "log": "<logfile path>"}
        ]}

    This function only keeps those processes ALIVE via dfork (the 2026-09-28
    reaper lesson: only dfork'd grandchildren survive Bash-call boundaries).
    It knows nothing about WHAT they do and references no project — all
    project-specific content stays in the local JSON + local script files
    (scripts/local/ is gitignored for exactly this). Identity = the LAST
    argv element (script path at cmdline end — the queue_watch lesson:
    never a bare pid).
    """
    spec = os.path.join(FLAGS, "local_services.json")
    try:
        with open(spec, encoding="utf-8") as f:
            services = json.load(f).get("services", [])
    except FileNotFoundError:
        return
    except Exception as exc:
        log(f"local_services spec unreadable ({exc!r}) — skipping")
        return
    for svc in services:
        name = str(svc.get("name") or "")
        cmd = svc.get("cmd")
        logf = str(svc.get("log") or "/tmp/local_service.log")
        if not name or not isinstance(cmd, list) or not cmd:
            continue
        identity = str(cmd[-1])
        r = subprocess.run(["pgrep", "-f", identity + "$"],
                           capture_output=True, text=True)
        if r.returncode == 0 and (r.stdout or "").strip():
            continue
        log(f"local service '{name}' DEAD — dfork-restarting "
            f"(per flags/local_services.json)")
        try:
            subprocess.Popen(
                [PY, os.path.join(BASE, "dfork_launch.py"), logf, *cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        except Exception as exc:
            log(f"local service '{name}' restart failed: {exc!r}")


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
            ensure_local_services()
            ensure_stall_recovery()
            ensure_frame_guard()
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
