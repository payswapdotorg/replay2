#!/usr/bin/env python3
"""webflix2_watch.py — the WebFlix 2.0 repo watch (monitor-only).

Polls payswapdotorg/webflix-2.0 for origin/main movement (lead-STEEL's Wave 1
merges are the expected first events), plus the webflix-1.0 wind-down tail.

NEVER dispatches, NEVER claims — claims are operator decisions per the 2.0
ledger law (claim-before-dispatch, push-order precedence, 4h binding).

Outputs:
  data/webflix2-events.json  — the console-side truth (heads + event list)
  logs/webflix2_watch.log    — one line per poll-cycle change / error
"""
import json
import subprocess
import time
from pathlib import Path

BASE = Path("/home/z/replay2")
EVENTS = BASE / "data" / "webflix2-events.json"
LOG = BASE / "logs" / "webflix2_watch.log"
POLL_SECONDS = 60
MAX_EVENTS = 60

REPOS = {
    "webflix-2.0": Path("/home/z/webflix-2.0"),
    "webflix-1.0": Path("/home/z/webflix"),
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg: str) -> None:
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=45,
    )


def head_of(repo: Path) -> str | None:
    r = git(repo, "rev-parse", "origin/main")
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def subject_of(repo: Path, sha: str) -> str:
    r = git(repo, "log", "-1", "--format=%s", sha)
    return (r.stdout.strip() or "")[:160]


def load_state() -> dict:
    try:
        return json.loads(EVENTS.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    tmp = EVENTS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(EVENTS)


def main() -> None:
    state = {
        "startedAt": now_iso(),
        "lastCheck": now_iso(),
        "repos": {},
        "events": [],
    }
    # Baseline pass: record current heads WITHOUT eventing (no false alarms).
    for name, path in REPOS.items():
        head = head_of(path)
        state["repos"][name] = {"head": head, "status": "ok"}
        log(f"baseline {name} head={head}")
    save_state(state)
    log(f"webflix2_watch armed — polling {list(REPOS)} every {POLL_SECONDS}s (monitor-only)")

    while True:
        time.sleep(POLL_SECONDS)
        state["lastCheck"] = now_iso()
        for name, path in REPOS.items():
            try:
                fetch = git(path, "fetch", "-q", "origin")
                if fetch.returncode != 0:
                    state["repos"][name]["status"] = f"fetch-error: {fetch.stderr.strip()[:120]}"
                    log(f"fetch-error {name}: {fetch.stderr.strip()[:160]}")
                    continue
                head = head_of(path)
                prev = state["repos"][name].get("head")
                if head and head != prev:
                    subj = subject_of(path, head)
                    event = {
                        "ts": now_iso(),
                        "repo": name,
                        "from": prev,
                        "to": head,
                        "subject": subj,
                    }
                    state["events"].append(event)
                    state["events"] = state["events"][-MAX_EVENTS:]
                    log(f"EVENT {name} {prev and prev[:8]} -> {head[:8]} — {subj}")
                    state["repos"][name]["head"] = head
                state["repos"][name]["status"] = "ok"
            except subprocess.TimeoutExpired:
                state["repos"][name]["status"] = "timeout"
                log(f"timeout {name}")
            except Exception as exc:  # never die on one bad cycle
                state["repos"][name]["status"] = f"error: {exc!s:.120}"
                log(f"error {name}: {exc!s:.160}")
        try:
            save_state(state)
        except Exception as exc:
            log(f"save-state error: {exc!s:.160}")


if __name__ == "__main__":
    main()
