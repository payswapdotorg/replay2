#!/usr/bin/env python3
"""watcher.py — the resident program watcher (post-reset rebuild).

Monitors (gentle, low-frequency):
  1. browser chat.z.ai login state  -> when login appears: sets login flag file
  2. worker branches on GitHub      -> new branch push = worker completion event
  3. operator PAT write access      -> when granted: write-access flag file

Writes JSON lines to watcher.log; flags as files in scripts/flags/.
Self-documenting: survives as long as the sandbox; the worklog + repo state
carry across resets. Run via launch_watcher.py (start_new_session).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "watcher.log")
FLAGS = os.path.join(BASE, "flags")
os.makedirs(FLAGS, exist_ok=True)

STATE = {
    "login": "unknown",
    "branches": set(),
    "write": False,
}


def log(msg):
    line = time.strftime("[%H:%M:%S] ") + msg
    try:
        # self-rotate so the log can never grow unbounded
        if os.path.exists(LOG) and os.path.getsize(LOG) > 2 * 1024 * 1024:
            with open(LOG, "rb") as f:
                f.seek(-150 * 1024, 2)
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def get_pat():
    try:
        env = open(os.path.join(BASE, "env.sh")).read()
        m = re.search(r"OPERATOR_PAT=(ghp_\w+)", env)
        return m.group(1) if m else ""
    except Exception:
        return ""


def check_login():
    try:
        tabs = channel.list_tabs()
        tab = next((t for t in tabs if "chat.z.ai" in (t.get("url") or "")), None)
        if not tab:
            return STATE["login"]
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=12)
        try:
            body = cdp.eval("document.body.innerText || ''", timeout=10) or ""
        finally:
            cdp.close()
        if "tepa" in body:
            return "logged-in(tepa)"
        if "Sign in" in body or "Log in" in body:
            return "logged-out"
        return "page:" + str(len(body))
    except Exception:
        return STATE["login"]


def check_branches(pat):
    r = subprocess.run(["curl", "-s", "--max-time", "15",
                        "-H", f"Authorization: token {pat}",
                        "https://api.github.com/repos/payswapdotorg/codex/branches?per_page=50"],
                       capture_output=True, text=True)
    try:
        bs = json.loads(r.stdout)
        return {b["name"]: b["commit"]["sha"][:10] for b in bs if isinstance(b, dict)}
    except Exception:
        return None


def check_write(pat):
    r = subprocess.run(["curl", "-s", "--max-time", "10",
                        "-H", f"Authorization: token {pat}",
                        "https://api.github.com/repos/payswapdotorg/codex"],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return bool((d.get("permissions") or {}).get("push"))
    except Exception:
        return STATE["write"]


def check_dialogs():
    """Auto-accept 'Reload site?' / beforeunload dialogs on the active tab."""
    try:
        tabs = channel.list_tabs()
        aid = ""
        try:
            aid = open(os.path.join(FLAGS, "active_tab.txt")).read().strip()
        except Exception:
            pass
        tab = next((t for t in tabs if t.get("id") == aid), None) or \
            next((t for t in tabs if "chat.z.ai" in (t.get("url") or "")), None)
        if not tab:
            return False
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=8)
        try:
            cdp.call("Page.enable", {}, timeout=8)
            cdp.call("Page.handleJavaScriptDialog", {"accept": True}, timeout=8)
            return True  # a dialog was actually accepted
        except Exception:
            return False  # no dialog open — normal case
        finally:
            cdp.close()
    except Exception:
        return False


def check_inbox():
    """Surface new operator messages into watcher.log so the agent notices them."""
    path = os.path.join(FLAGS, "operator_inbox.jsonl")
    try:
        if not os.path.exists(path):
            return
        lines = [l for l in open(path, encoding="utf-8").read().split("\n") if l.strip()]
        n = len(lines)
        prev = STATE.get("inbox_lines", 0)
        if n > prev:
            for l in lines[prev:]:
                try:
                    d = json.loads(l)
                    log(f"OPERATOR MESSAGE: {str(d.get('text'))[:200]}")
                except Exception:
                    pass
        STATE["inbox_lines"] = n
    except Exception:
        pass


def check_procs():
    """Restart dead infrastructure (Xvfb / Chrome / dev server / supervisor /
    custodian).
    Ring of three (any two members heal the third):
      - the supervisor restarts us (PID + heartbeat-hang detection, 10s)
      - we restart the supervisor (PID + heartbeat-hang detection, ~2min)
      - the custodian (small, OOM-safe) guards the pair against simultaneous
        death; we resurrect the custodian if IT dies
    """
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        # Chrome dead => CDP endpoint gone
        import urllib.request
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3).read()
        except Exception:
            log("CDP dead — restarting Chrome + Xvfb")
            subprocess.run(["/home/z/.venv/bin/python3", os.path.join(base, "launch_stack.py")], timeout=120)
        # dev server dead => operator console unreachable
        try:
            urllib.request.urlopen("http://127.0.0.1:3000", timeout=4).read(64)
        except Exception:
            # liveness-guarded: a cold compile binds the port late; spawning
            # extra dev servers during that window stampedes memory (OOM).
            # The supervisor owns the patience/restart policy — we only spawn
            # when no dev process exists at all.
            r = subprocess.run(["pgrep", "-f", "next dev|bun run dev|next-server"],
                               capture_output=True, text=True)
            if not r.stdout.strip():
                log("dev server :3000 dead — restarting")
                subprocess.Popen(["/home/z/.venv/bin/python3", os.path.join(base, "launch_dev.py")],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(5)
        # replay daemon dead => console loses realtime frames + drags
        try:
            urllib.request.urlopen("http://127.0.0.1:3100/healthz", timeout=3).read(64)
        except Exception:
            log("replayd :3100 dead — restarting")
            subprocess.Popen(["/home/z/.venv/bin/python3", os.path.join(base, "launch_replayd.py")],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        # supervisor dead OR hung => resurrect it (it holds the flock, so a
        # fresh launch simply adopts the role). Hung = alive-but-stuck:
        # supervisor_heartbeat is written every 10s; stale beyond 180s with a
        # process older than 180s (startup grace) means wedged — SIGKILL
        # first so the restart always yields a fresh process.
        sup_pid = ""
        try:
            sup_pid = open(os.path.join(base, "supervisor.pid")).read().strip()
        except Exception:
            pass
        alive = False
        if sup_pid:
            try:
                cmd = open(f"/proc/{sup_pid}/cmdline", "rb").read().decode(errors="replace")
                alive = "supervisor.py" in cmd
            except Exception:
                alive = False
        if alive:
            try:
                age = time.time() - os.path.getmtime(os.path.join(FLAGS, "supervisor_heartbeat"))
                started = 0
                try:
                    with open(f"/proc/{sup_pid}/stat") as f:
                        st = f.read()
                    after = st[st.rindex(")") + 2:].split()
                    ticks = int(after[19])
                    btime = int(open("/proc/stat").read().split("btime")[1].split()[0])
                    started = btime + ticks / (os.sysconf("SC_CLK_TCK") or 100)
                except Exception:
                    pass
                if age > 180 and (time.time() - started) > 180:
                    log(f"supervisor HUNG (hb {int(age)}s stale) — SIGKILL + resurrect")
                    try:
                        subprocess.run(["kill", "-9", sup_pid], capture_output=True)
                    except Exception:
                        pass
                    time.sleep(1)
                    alive = False
            except Exception:
                pass
        if not alive:
            log("supervisor dead — resurrecting")
            subprocess.Popen(
                ["/home/z/.venv/bin/python3", os.path.join(base, "supervisor.py")],
                stdout=open(os.path.join(base, "logs", "supervisor.err"), "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True)
        # custodian (third ring member) dead => resurrect it. Tiny loop, no
        # CDP; it guards the supervisor+watcher pair against simultaneous
        # OOM death and SIGKILLs hung instances.
        cus_pid = ""
        try:
            cus_pid = open(os.path.join(base, "custodian.pid")).read().strip()
        except Exception:
            pass
        cus_alive = False
        if cus_pid:
            try:
                cmd = open(f"/proc/{cus_pid}/cmdline", "rb").read().decode(errors="replace")
                cus_alive = "custodian.py" in cmd
            except Exception:
                cus_alive = False
        if not cus_alive:
            log("custodian dead — resurrecting")
            subprocess.Popen(
                ["/home/z/.venv/bin/python3", os.path.join(base, "custodian.py")],
                stdout=open(os.path.join(base, "logs", "custodian.log"), "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True)
    except Exception as e:
        log(f"proc check error {e!r}")


def main():
    log("watcher online (login + branches + write-access + dialogs + operator-inbox)")
    pat = get_pat()
    if not pat:
        log("NO PAT in env.sh — watcher runs in degraded mode")
    while True:
        try:
            # 1. login state
            login = check_login()
            if login != STATE["login"]:
                log(f"login: {STATE['login']} -> {login}")
                STATE["login"] = login
                if login.startswith("logged-in"):
                    open(os.path.join(FLAGS, "LOGIN_READY"), "w").write(time.strftime("%H:%M:%S"))
                else:
                    p = os.path.join(FLAGS, "LOGIN_READY")
                    if os.path.exists(p):
                        os.remove(p)

            # 2. branches (new pushes)
            if pat:
                brs = check_branches(pat)
                if brs is not None:
                    names = set(brs.keys())
                    if STATE["branches"] and names != STATE["branches"]:
                        added = names - STATE["branches"]
                        removed = STATE["branches"] - names
                        if added:
                            log(f"NEW BRANCH(ES): {sorted(added)} — worker completion event")
                            for n in sorted(added):
                                open(os.path.join(FLAGS, f"BRANCH_{n.replace('/', '__')}"), "w").write(brs[n])
                        if removed:
                            log(f"branch(es) gone: {sorted(removed)}")
                    elif not STATE["branches"]:
                        log(f"baseline branches: {sorted(names)}")
                    STATE["branches"] = names

                # 3. write access
                w = check_write(pat)
                if w != STATE["write"]:
                    log(f"write access: {STATE['write']} -> {w}")
                    STATE["write"] = w
                    if w:
                        open(os.path.join(FLAGS, "WRITE_ACCESS"), "w").write(time.strftime("%H:%M:%S"))
        except Exception as e:
            log(f"loop error {e!r}")

        # 4. dialogs (fast sub-cycle) + operator inbox
        for _ in range(12):
            check_dialogs()
            check_inbox()
            try:
                open(os.path.join(FLAGS, "watcher_heartbeat"), "w").write(
                    time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
            time.sleep(10)
        check_procs()


if __name__ == "__main__":
    try:
        open(os.path.join(BASE, "watcher.pid"), "w").write(str(os.getpid()))
    except Exception:
        pass
    # IMMORTAL: even if main() somehow raises, restart after a short backoff.
    # (the supervisor additionally relaunches the whole process if it dies.)
    while True:
        try:
            main()
        except Exception as e:
            try:
                log(f"FATAL in main: {e!r} — restarting in 15s")
            except Exception:
                pass
            time.sleep(15)
        else:
            try:
                log("main() returned unexpectedly — restarting in 15s")
            except Exception:
                pass
            time.sleep(15)
