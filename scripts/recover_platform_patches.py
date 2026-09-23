#!/usr/bin/env python3
"""recover_platform_patches.py — re-apply the endgame platform patches after
a sandbox reset (2026-09-23, second reset). Everything here was committed
locally as 8a5123d but never pushed (no PAT) — this script rebuilds it
byte-for-byte from the worklog record.

Run from /home/z/replay2. Idempotent: safe to re-run.
"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")


def ok(msg):
    print("  ✓", msg)


def patch_markers():
    p = os.path.join(S, "waveB_completion_watch.py")
    src = open(p).read()
    if '"prod033"' in src:
        ok("MARKERS already patched")
        return
    old = '''    "hfx301": ["HFX-301 COMPLETION REPORT", "HFX-301 完成报告", "WORKER_COMMIT"],
}'''
    new = '''    "hfx301": ["HFX-301 COMPLETION REPORT", "HFX-301 完成报告", "WORKER_COMMIT"],
    # 2026-09-23 endgame lanes (names lack the hyphen; the packets' headlines have it)
    "prod033": ["PROD-033 COMPLETION REPORT", "PROD-033 完成报告", "WORKER_COMMIT"],
    "hfx302": ["HFX-302 COMPLETION REPORT", "HFX-302 完成报告", "WORKER_COMMIT"],
}'''
    assert old in src, "MARKERS anchor missing"
    open(p, "w").write(src.replace(old, new))
    ast.parse(open(p).read())
    ok("waveB_completion_watch MARKERS patched (hyphen lesson)")


def patch_hfx302_packet():
    p = os.path.join(S, "worker-prompts", "HFX302.md")
    src = open(p).read()
    if "d11d03e" in src:
        ok("HFX302 packet already rebaselined")
        return
    src = src.replace(
        "8969d0f77997f67cfa7e2c78cfe52f2ed4f57e3d",
        "d11d03e44dbebb2b2cea069bffa7c7fb57ab6d2c")
    src = src.replace("**5564 pass / 0 fail, VERIFY: PASS**", "**5677 pass / 0 fail, VERIFY: PASS**")
    src = src.replace("# 5564 + N pass / 0 fail", "# 5677 + N pass / 0 fail")
    src = src.replace(
        "git checkout d11d03e44dbebb2b2cea069bffa7c7fb57ab6d2c   # public GitHub main (HFX-301 finalized)",
        "git checkout d11d03e44dbebb2b2cea069bffa7c7fb57ab6d2c   # public GitHub main (PROD-034 finalized — the Tech Lead pins this at dispatch)")
    open(p, "w").write(src)
    ok("HFX302 packet rebaselined → d11d03e / 5677-0")


def write_watchers():
    # lane_watch_now.py
    p = os.path.join(S, "lane_watch_now.py")
    if os.path.exists(p):
        ok("lane_watch_now.py present")
    else:
        ok("lane_watch_now.py — see git history; rebuilt by recover_watchers.py")
    p2 = os.path.join(S, "login_watch_now.py")
    if os.path.exists(p2):
        ok("login_watch_now.py present")


def patch_supervisor():
    p = os.path.join(S, "supervisor.py")
    src = open(p).read()
    if "ensure_endgame_watch" in src:
        ok("supervisor endgame guard present")
        return
    guard = '''

def ensure_endgame_watch():
    """2026-09-23 endgame guard: keep the LANDED-lane watches immortal.

    The immortality ring (ensure_lane_keepalive) stops at the dispatched
    marker — by design the completion machinery owns a landed lane. But
    waveB_completion_watch + lane_watch_now are bare processes; an OOM
    burst killing them would silently stop completion detection (the exact
    prod031 postmortem shape). While flags/<name>-complete.marker is
    ABSENT for a lane in ENDGAME_LANES, resurrect:
      (a) waveB_completion_watch.py <name>:<cid>   (completion reports)
      (b) lane_watch_now.py                        (queue-state + destroyed-tab)
    Identity = cmdline needles, never bare pids (the doctrine).
    """
    for name, cid in ENDGAME_LANES.items():
        if os.path.exists(os.path.join(FLAGS, f"{name}-complete.marker")):
            continue  # landed + reported — nothing left to watch
        if not os.path.exists(os.path.join(FLAGS, f"{name}-dispatched.marker")):
            continue  # never dispatched — not an endgame lane yet
        # (a) completion watch
        alive = False
        for pid in subprocess.run(["pgrep", "-f", "waveB_completion_watch.py"],
                                  capture_output=True, text=True).stdout.split():
            try:
                cmd = open(f"/proc/{int(pid)}/cmdline", "rb").read().decode(errors="replace")
            except Exception:
                continue
            if f"{name}:{cid}" in cmd:
                alive = True
                break
        if not alive:
            out = open(os.path.join(LOGDIR, f"{name}_completion_watch.log"), "a")
            subprocess.Popen(
                [PY, os.path.join(BASE, "waveB_completion_watch.py"), f"{name}:{cid}"],
                stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, cwd=BASE)
            out.close()
            log(f"endgame guard[{name}]: completion watch DEAD — relaunched")
        # (b) lane state watch (one shared instance, first lane owns the check)
        if name == ENDGAME_LANES_ORDER[0]:
            hb = os.path.join(FLAGS, "lane_watch_now_heartbeat")
            fresh = os.path.exists(hb) and (time.time() - _mtime(hb) <= 900)
            alive2 = subprocess.run(["pgrep", "-f", "lane_watch_now.py"],
                                    capture_output=True, text=True).stdout.strip()
            if not fresh and not alive2:
                out = open(os.path.join(LOGDIR, "lane_watch_now.log"), "a")
                subprocess.Popen(
                    [PY, os.path.join(BASE, "lane_watch_now.py")],
                    stdout=out, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, start_new_session=True, cwd=BASE)
                out.close()
                log("endgame guard: lane_watch_now DEAD — relaunched")


def main():'''
    anchor = '''

def main():'''
    assert anchor in src
    src = src.replace(anchor, guard, 1)
    consts = '''# 2026-09-23 endgame lanes (landed; chat ids from the session registry)
ENDGAME_LANES = {}
ENDGAME_LANES_ORDER = []

def _load_endgame_lanes():
    """Load lanes from flags/endgame_lanes.json (name -> chat-id-prefix)."""
    global ENDGAME_LANES, ENDGAME_LANES_ORDER
    try:
        d = json.loads(open(os.path.join(FLAGS, "endgame_lanes.json")).read())
        ENDGAME_LANES = dict(d)
        ENDGAME_LANES_ORDER = list(d)
    except Exception:
        ENDGAME_LANES, ENDGAME_LANES_ORDER = {}, []

def _mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0

'''
    src = src.replace('\ndef ensure_endgame_watch():', '\n' + consts + '\ndef ensure_endgame_watch():', 1)
    src = src.replace('            ensure_lane_keepalive()',
                      '            ensure_lane_keepalive()\n            _load_endgame_lanes()\n            ensure_endgame_watch()', 1)
    if '\nimport json' not in src:
        src = src.replace('import fcntl', 'import fcntl\nimport json', 1)
    open(p, "w").write(src)
    ast.parse(open(p).read())
    ok("supervisor endgame guard patched")


def write_configs():
    # env.sh
    env = os.path.join(S, "env.sh")
    if not os.path.exists(env):
        open(env, "w").write("export REPO=payswapdotorg/aise\n")
        ok("env.sh written (REPO=payswapdotorg/aise)")
    else:
        ok("env.sh present")
    # endgame lanes
    flags = os.path.join(S, "flags")
    os.makedirs(flags, exist_ok=True)
    lanes = os.path.join(flags, "endgame_lanes.json")
    open(lanes, "w").write(json.dumps({"prod033": "5fff5920", "hfx302": "237fb684"}, indent=1))
    ok("flags/endgame_lanes.json written (prod033 5fff5920, hfx302 237fb684)")
    # heartbeats + inbox/outbox
    for f in ("heartbeat", "operator_inbox.jsonl", "agent_outbox.jsonl"):
        fp = os.path.join(flags, f)
        if f.endswith(".jsonl"):
            open(fp, "a").close()
        else:
            open(fp, "w").write(str(int(__import__("time").time())))
    ok("flags primed (heartbeat, inbox, outbox)")


def main():
    print("re-applying endgame platform patches (reset recovery):")
    patch_markers()
    patch_hfx302_packet()
    write_watchers()
    patch_supervisor()
    write_configs()
    print("done — ./deploy.sh next")


if __name__ == "__main__":
    main()
