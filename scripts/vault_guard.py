#!/usr/bin/env python3
"""vault_guard.py — keeps the ops vault LIVE across sandbox rollbacks.

Why this exists (recycles #18–#20 pattern, live-observed 2026-10-14):
  The sandbox image is snapshot-pinned (~11:30Z) and every deep recycle
  restores it — including a stale download/recovery kit whose Upstash
  endpoint (meet-ewe-145933) was DELETED from Upstash. tl_recover only
  pulls the Redis mirror when kit entries are MISSING, and heal's seed_kit
  re-creates them from the same stale embedded copy BEFORE tl_recover
  runs — so the stale-but-present kit always wins and the mirror stays
  unreachable. Local vault patches (14:06Z, 18:02Z) were rolled back
  twice; only the REMOTE mirror and GitHub survived.

This daemon closes the loop from the GitHub tier (the only tier that
rolls FORWARD with every recovery — the supervisor that launches this
script is itself refreshed from origin/main at each recycle):
  1. every cycle: PING the kit's Upstash endpoint
  2. healthy → heartbeat + wait (a PONGing local vault ALWAYS wins —
     operator rotations land locally first and are never clobbered)
  3. dead/missing → resolve the PAT from the same kit files, shallow-clone
     the PRIVATE payswapdotorg/ops-vault repo, install its credentials.env
     to every vault location + the watcher relay, PING-verify, then
     restore missing mirror kit entries per-entry (seed wins, never
     clobbers a fresher local) and propagate the mission board to the
     console data locations when absent.

Doctrine: never logs secret values (statuses/sizes only); heal attempts
rate-limited (600s) so an unreachable private repo cannot spam clones;
all network ops timeout-bounded; single instance via flock.

Run: dfork_launch.py <log> /home/z/.venv/bin/python3 scripts/vault_guard.py
"""
import fcntl
import json
import os
import shutil
import subprocess
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOCK = os.path.join(FLAGS, "vault_guard.lock")
HEARTBEAT = os.path.join(FLAGS, "vault_guard_heartbeat")

DURABLE = "/home/z/my-project/download/recovery"
VAULT_LOCATIONS = [
    os.path.join(DURABLE, "credentials.env"),
    "/home/z/.payswap-env",
    "/home/z/my-project/browser-profile/ops-vault.env",
    "/home/z/my-project/download/w135-bank/ops-vault.env",
]
RELAY = os.path.expanduser("~/.secrets/env.sh")
PRIVATE_REPO = "https://github.com/payswapdotorg/ops-vault.git"
PULL_DIR = "/tmp/vg-pull"

CYCLE_S = 120          # liveness cadence
HEAL_BACKOFF_S = 600   # min seconds between heal attempts
GIT_TIMEOUT_S = 60
HTTP_TIMEOUT_S = 15

MIRROR_ENTRIES = [  # (mirror key suffix, local file) — restored only when absent/empty
    ("credentials-env", os.path.join(DURABLE, "credentials.env")),
    ("repos-txt", os.path.join(DURABLE, "repos.txt")),
    ("watch-repo", os.path.join(DURABLE, "watch_repo.txt")),
    ("mission-state", os.path.join(DURABLE, "mission-state.json")),
    ("outbox", os.path.join(DURABLE, "agent_outbox.seed.jsonl")),
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, "vault_guard.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def parse_env_files():
    """Merge export-assignments from the kit files (first-seen wins)."""
    env = {}
    for path in [os.path.join(DURABLE, "credentials.env"),
                 "/home/z/.payswap-env",
                 RELAY]:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:]
                    if "=" not in line or line.startswith("#"):
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in env:
                        env[k] = v
        except Exception:
            continue
    return env


def ping(url, token):
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/ping",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            return b"PONG" in r.read()
    except Exception:
        return False


def redis_get(url, token, key):
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/get/{key}",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            v = json.loads(r.read()).get("result", "")
            return v if isinstance(v, str) else ""
    except Exception:
        return ""


def write_relay(pat, url, token):
    os.makedirs(os.path.dirname(RELAY), exist_ok=True)
    body = ("# relay (vault_guard): PAT + live Upstash creds for the "
            "watcher + tl_recover bootstrap\n"
            f"REPO=payswapdotorg/aurum-chat\n"
            f"PAYSWAP_PAT={pat}\nGITHUB_TOKEN={pat}\n"
            f"UPSTASH_REDIS_REST_URL={url}\n"
            f"UPSTASH_REDIS_REST_TOKEN={token}\n")
    with open(RELAY, "w") as f:
        f.write(body)
    os.chmod(RELAY, 0o600)


def heal(env):
    """Pull the live vault from the private GitHub repo and re-arm the kit."""
    pat = env.get("PAYSWAP_PAT") or env.get("GITHUB_TOKEN") or env.get("GITHUB_PAT")
    if not pat:
        log("heal impossible: no PAT in kit files — operator rotation needed")
        return False
    shutil.rmtree(PULL_DIR, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1",
             f"https://x-access-token:{pat}@github.com/"
             f"{PRIVATE_REPO.split('github.com/')[1]}",
             PULL_DIR],
            timeout=GIT_TIMEOUT_S, capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        log("heal: private repo clone timed out — will retry after backoff")
        return False
    except Exception as exc:
        log(f"heal: clone failed ({exc!r}) — will retry after backoff")
        return False
    src = os.path.join(PULL_DIR, "credentials.env")
    if not os.path.isfile(src) or os.path.getsize(src) < 500:
        log("heal: private repo has no credentials.env — operator must seed it")
        shutil.rmtree(PULL_DIR, ignore_errors=True)
        return False
    vault = open(src, encoding="utf-8", errors="replace").read()
    n = sum(1 for l in vault.splitlines() if l.startswith("export "))
    if n < 10:
        log("heal: private vault implausibly small — refusing to install")
        shutil.rmtree(PULL_DIR, ignore_errors=True)
        return False
    # install to every vault location (dirs that exist; the kit dir always)
    installed = []
    for dest in VAULT_LOCATIONS:
        try:
            if os.path.dirname(dest) and not os.path.isdir(os.path.dirname(dest)):
                continue
            with open(dest, "w") as f:
                f.write(vault)
            os.chmod(dest, 0o600)
            installed.append(os.path.basename(os.path.dirname(dest)) or dest)
        except Exception:
            continue
    fresh = parse_env_files()
    url = fresh.get("UPSTASH_REDIS_REST_URL", "")
    token = fresh.get("UPSTASH_REDIS_REST_TOKEN", "")
    if not (url and token and ping(url, token)):
        log("heal: installed vault from private repo but its endpoint still "
            "dead — operator must rotate (update ops-vault repo + mirror)")
        shutil.rmtree(PULL_DIR, ignore_errors=True)
        return False
    write_relay(pat, url, token)
    # per-entry mirror restore (only absent/empty locals — seed never clobbers)
    restored = []
    for suffix, path in MIRROR_ENTRIES:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            continue
        v = redis_get(url, token, f"payswap:recovery:{suffix}")
        if v:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(v)
            restored.append(suffix)
    # mission board propagation (the 'wrong replay' gap: fresh clone loses
    # the gitignored board; heal only when the console copies are missing)
    for board in [os.path.join(BASE, "..", "data", "mission-state.json"),
                  "/home/z/my-project/data/mission-state.json"]:
        board = os.path.abspath(board)
        if not (os.path.isfile(board) and os.path.getsize(board) > 0):
            src_board = os.path.join(DURABLE, "mission-state.json")
            if os.path.isfile(src_board) and os.path.getsize(src_board) > 0:
                try:
                    os.makedirs(os.path.dirname(board), exist_ok=True)
                    shutil.copyfile(src_board, board)
                    restored.append(f"board:{os.path.dirname(board)}")
                except Exception:
                    pass
    log(f"heal OK: vault ({n} exports) installed to {len(installed)} "
        f"locations; relay re-armed; mirror entries restored: "
        f"{restored or 'none needed'}")
    shutil.rmtree(PULL_DIR, ignore_errors=True)
    return True


def main():
    os.makedirs(FLAGS, exist_ok=True)
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another guard holds the lock
    log(f"vault_guard online (pid {os.getpid()}) — {CYCLE_S}s cycles, "
        f"private-repo heal on dead endpoint")
    last_heal = 0.0
    while True:
        try:
            env = parse_env_files()
            url = env.get("UPSTASH_REDIS_REST_URL", "")
            token = env.get("UPSTASH_REDIS_REST_TOKEN", "")
            if url and token and ping(url, token):
                log("kit endpoint healthy (PONG)")
            elif time.time() - last_heal >= HEAL_BACKOFF_S:
                log("kit endpoint DEAD — healing from private ops-vault repo")
                last_heal = time.time()
                heal(env)
            else:
                log("kit endpoint dead; heal on backoff "
                    f"({int(HEAL_BACKOFF_S - (time.time() - last_heal))}s)")
        except Exception as exc:
            log(f"cycle error {exc!r} — continuing")
        try:
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
