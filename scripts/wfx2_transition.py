#!/usr/bin/env python3
"""wfx2_transition.py — the WebFlix 2.0 resident transition monitor.

The operator standing order (2026-09-29 02:34Z): "continuous resident
watch from here on: monitor → harvest → review → approve/require-changes
→ dispatch next, until the roadmap is complete. No early returns. Use the
github repo as guide for roadmap."

60s cycles, flock single-instance. Detects the two transitions and fires
the heavy actor (wfx2_dispatch_child.py) ONCE each, via dfork (the
monitor never blocks; no Bash-call reaper can touch the children):

  GATES       bible (docs/specs/*.md) + boot (prisma/schema.prisma) present
              on origin/main — whoever merged them — → fire laneset=wave2
              (claim WFX2-A + WFX2-U, the 02:45Z stakes).
  ESCALATION  04:15Z reached, gates still absent, and lead-STEEL has
              pushed NOTHING on any ref in the prior 25 minutes (rolling
              activity grace; an active lead's lanes stay theirs) → fire
              laneset=escalation (take over the lapsed WFX2-B + WFX2-S).

Marker-guarded (flags/wfx2_fired.<laneset>) so a transition fires at most
once per laneset; verdicts land in flags/wfx2_transition_verdict.<laneset>
.json. Stateless across restarts (all truth in files) — the supervisor's
ensure_wfx2_transition resurrects this monitor on death (ring member).
"""
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path("/home/z/replay2/scripts")
REPO = Path("/home/z/webflix-2.0")
FLAGS = SCRIPTS / "flags"
PY = "/home/z/.venv/bin/python3"
STATE = FLAGS / "wfx2_transition_state.json"
HB = FLAGS / "wfx2_transition.heartbeat"
LOGDIR = SCRIPTS / "logs"
LOCK = FLAGS / "wfx2_transition.lock"

CYCLE_S = 60
GRACE_S = 25 * 60
ESCALATION_AT_DEFAULT = "2026-09-29T04:15:00Z"
MY_AUTHOR = "TL Station (resident watch)"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    print(line, flush=True)
    try:
        with open(LOGDIR / "wfx2_transition.log", "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def escalation_at() -> float:
    """The escalation deadline (epoch). Overridable via a marker file."""
    override = FLAGS / "wfx2_escalation.override"
    raw = ESCALATION_AT_DEFAULT
    try:
        if override.exists():
            raw = override.read_text().strip() or raw
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None \
            else dt.timestamp()
    except Exception:
        return float("inf")  # broken override = never fire (fail-safe)


def git(*args: str, timeout: int = 60):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, timeout=timeout)


def repo_refresh() -> tuple[str, list[str]]:
    """Fetch all refs; return (main sha, main file tree)."""
    try:
        git("fetch", "origin", "+refs/heads/*:refs/remotes/origin/*",
            timeout=90)
        r = git("rev-parse", "origin/main")
        sha = r.stdout.strip() if r.returncode == 0 else ""
        t = git("ls-tree", "-r", "--name-only", "origin/main")
        tree = t.stdout.split() if t.returncode == 0 else []
        return sha, tree
    except Exception as exc:
        log(f"repo_refresh error: {exc!s:.160}")
        return "", []


def gates_on(tree: list[str]) -> bool:
    has_bible = any(f.startswith("docs/specs/") and f.endswith(".md")
                    for f in tree)
    has_boot = any(f == "prisma/schema.prisma" for f in tree)
    return has_bible and has_boot


def lead_active(within_s: int) -> bool:
    """True if ANY commit on ANY ref newer than within_s was authored by
    someone other than this console (my author string). My own ledger/
    claim pushes do not count as foreign activity."""
    cutoff_iso = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.gmtime(time.time() - within_s))
    try:
        r = git("log", "--all", f"--since={cutoff_iso}", "--format=%an")
        if r.returncode != 0:
            return True  # probe failure = treat as active (fail-safe)
        authors = {a.strip() for a in r.stdout.splitlines() if a.strip()}
        foreign = authors - {MY_AUTHOR}
        return bool(foreign)
    except Exception:
        return True


def fire(laneset: str) -> bool:
    marker = FLAGS / f"wfx2_fired.{laneset}"
    if marker.exists():
        return False
    log(f"FIRE laneset={laneset} — dfork wfx2_dispatch_child")
    marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    subprocess.Popen(
        [PY, str(SCRIPTS / "dfork_launch.py"),
         str(LOGDIR / f"wfx2_child_{laneset}.log"),
         PY, str(SCRIPTS / "wfx2_dispatch_child.py"), laneset],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    return True


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    state["lastCheck"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE)


def heartbeat() -> None:
    try:
        with open(HB, "a"):
            os.utime(HB, None)
    except OSError:
        pass


def main() -> int:
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another wfx2_transition already holds the lock — exiting",
              flush=True)
        return 0
    log("wfx2_transition online — watching for gates/escalation "
        f"(escalation at {ESCALATION_AT_DEFAULT}, grace {GRACE_S//60}min)")

    state = {"startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "fired": {"wave2": (FLAGS / "wfx2_fired.wave2").exists(),
                       "escalation": (FLAGS / "wfx2_fired.escalation").exists()}}
    save_state(state)

    last_grace_log = 0.0
    while True:
        try:
            sha, tree = repo_refresh()
            gates = gates_on(tree)
            state["mainSha"] = sha
            state["gates"] = gates

            if gates and not state["fired"]["wave2"]:
                log(f"GATES LANDED on main @ {sha[:12]} — firing wave2")
                state["fired"]["wave2"] = fire("wave2")

            if not gates and not state["fired"]["escalation"]:
                at = escalation_at()
                now = time.time()
                if now >= at:
                    if lead_active(GRACE_S):
                        if now - last_grace_log > 300:
                            log("escalation deadline passed but lead-STEEL "
                                "ACTIVE (rolling grace extends)")
                            last_grace_log = now
                    else:
                        log(f"ESCALATION — deadline passed, lead inactive "
                            f"{GRACE_S//60}min, gates absent (main @ "
                            f"{sha[:12] or 'seed'}) — firing takeover")
                        state["fired"]["escalation"] = fire("escalation")

            # surface child verdicts when they appear
            for laneset in ("wave2", "escalation"):
                v = FLAGS / f"wfx2_transition_verdict.{laneset}.json"
                if v.exists():
                    key = f"verdict.{laneset}"
                    try:
                        data = json.loads(v.read_text())
                        if state.get(key) != data.get("status"):
                            state[key] = data.get("status")
                            log(f"verdict[{laneset}] = {data.get('status')} "
                                f"— {json.dumps(data.get('dispatched', ''))[:120]}")
                    except Exception:
                        pass
            save_state(state)
            heartbeat()
        except Exception as exc:
            log(f"cycle error {exc!r} — continuing")
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    sys.exit(main())
