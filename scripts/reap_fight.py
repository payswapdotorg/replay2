#!/usr/bin/env python3
"""reap_fight.py v3 — SINGLE-ATTEMPT fighter for cron-driven revival.

Long-lived daemons get process-group-killed on this box (cgroup OOM chain).
Doctrine: one create+verify per invocation, state in json, lock against
overlap, exit. The cron watchdog re-invokes every 3 min; each tick is a
fresh short-lived process (nothing resident to kill).

State: flags/reap_fight_state.json  {lane_done, lane_name, lane_suffix, lane_attempts}
Lock:  flags/reap_fight.lock        {pid, ts} — stale if pid dead or ts > 12 min
"""
import json
import os
import subprocess
import sys
import time

SCRIPTS = "/home/z/replay2/scripts"
REG = os.path.join(SCRIPTS, "flags", "session_registry.jsonl")
PROMPTS = os.path.join(SCRIPTS, "worker-prompts")
LOG = os.path.join(SCRIPTS, "logs", "reap_fight.log")
STATE = os.path.join(SCRIPTS, "flags", "reap_fight_state.json")
LOCK = os.path.join(SCRIPTS, "flags", "reap_fight.lock")
MAX_ATTEMPTS = 12
PROBE_A = 75
PROBE_B = 210
PROBE_C = 105

sys.path.insert(0, SCRIPTS)
from batch_probe import call  # noqa: E402

LANES = [
    {"lane": "qa001", "packet": "QA001.md", "suffix": 6},
    {"lane": "qa003", "packet": "QA003.md", "suffix": 5},
    {"lane": "qa002", "packet": "QA002.md", "suffix": 6},
]


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def take_lock():
    now = time.time()
    try:
        lk = json.load(open(LOCK))
        if pid_alive(lk.get("pid", -1)) and now - lk.get("ts", 0) < 720:
            return False  # live holder
    except Exception:
        pass
    json.dump({"pid": os.getpid(), "ts": now}, open(LOCK, "w"))
    return True


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def registry_latest_url(name):
    url = None
    try:
        for line in open(REG):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("name") == name and r.get("url"):
                url = r.get("url")
    except FileNotFoundError:
        return None
    return url


def probe(cid):
    try:
        chat = call(f"/api/v1/chats/{cid}", timeout=30)
    except Exception:
        return (False, 0, 0)
    c = chat.get("chat") or chat
    msgs = (c.get("history") or {}).get("messages") or {}
    if isinstance(msgs, list):
        msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
    chars = sum(len(json.dumps(m)) for m in msgs.values())
    return (True, len(msgs), chars)


def arm(name, url):
    log(f"{name} STUCK — arming watcher")
    wl = os.path.join(SCRIPTS, "logs", f"worker_watch_{name}.log")
    with open(wl, "w") as f:
        subprocess.Popen(
            ["python3", os.path.join(SCRIPTS, "worker_watch.py"), name, url],
            cwd=SCRIPTS, stdout=f, stderr=subprocess.STDOUT,
            start_new_session=True)
    return True


def one_attempt(spec, suffix):
    lane = spec["lane"]
    name = f"{lane}r{suffix}"
    log(f"=== {lane} attempt as {name} ===")
    try:
        p = subprocess.run(
            ["python3", os.path.join(SCRIPTS, "dispatch_worker.py"),
             "create", name, os.path.join(PROMPTS, spec["packet"])],
            cwd=SCRIPTS, capture_output=True, text=True, timeout=840)
        tail = (p.stdout or "").strip().splitlines()[-1:] or ["<no output>"]
        log(f"create rc={p.returncode} | {tail[0][:100]}")
    except subprocess.TimeoutExpired:
        log("create TIMEOUT (840s)")
    url = registry_latest_url(name)
    if not url:
        log(f"{name}: no registry url — attempt failed")
        return False
    cid = url.rstrip("/").split("/c/")[-1]
    time.sleep(PROBE_A)
    p1 = probe(cid)
    log(f"{name} probeA: present={p1[0]} msgs={p1[1]} chars={p1[2]}")
    if not p1[0]:
        return False
    time.sleep(PROBE_B - PROBE_A)
    p2 = probe(cid)
    log(f"{name} probeB: present={p2[0]} msgs={p2[1]} chars={p2[2]}")
    if not p2[0]:
        return False
    if p2[2] > p1[2] or p2[1] > p1[1]:
        return arm(name, url)
    time.sleep(PROBE_C)
    p3 = probe(cid)
    log(f"{name} probeC: present={p3[0]} msgs={p3[1]} chars={p3[2]}")
    if p3[0] and (p3[2] > p2[2] or p3[1] > p2[1]):
        return arm(name, url)
    return False


def main():
    if not take_lock():
        print("lock held — another fighter is working; exiting")
        return 0
    st = load_state()
    for spec in LANES:
        lane = spec["lane"]
        done = st.get(f"{lane}_done")
        if done:
            continue
        attempts = st.get(f"{lane}_attempts", 0)
        if attempts >= MAX_ATTEMPTS:
            log(f"{lane}: EXHAUSTED ({attempts} attempts)")
            st[f"{lane}_done"] = "exhausted"
            save_state(st)
            continue
        suffix = st.get(f"{lane}_suffix", spec["suffix"])
        try:
            stuck = one_attempt(spec, suffix)
        except Exception as e:
            log(f"{lane} attempt EXC {repr(e)[:140]}")
            stuck = False
        if stuck:
            st[f"{lane}_done"] = True
            st[f"{lane}_name"] = f"{lane}r{suffix}"
        else:
            st[f"{lane}_attempts"] = attempts + 1
            st[f"{lane}_suffix"] = suffix + 1
        save_state(st)
        return 0  # ONE attempt per invocation — cron drives the rest
    log("all lanes resolved: " + json.dumps(
        {k: v for k, v in st.items() if k.endswith('_done') or k.endswith('_name')}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
