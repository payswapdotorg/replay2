"""launch_stack.py — start Xvfb + Chrome (CDP :9222) for the replay.

Relocatable + configurable via env:
  REPLAY_DISPLAY   (default :99)
  REPLAY_WxH       (default 1440x900)
  CHROME_BIN       (default: auto-discover playwright chromium / system chrome)
  REPLAY_START_URL (default https://chat.z.ai/)
  CDP_PORT         (default 9222)

The browser profile is resolved by profile.py (2026-10-05 operator
directive: logins must survive sandbox resets). Default durable location:
/home/z/my-project/browser-profile (visible+unignored inside the platform
app — the path class that survives every observed reset); env override
REPLAY_PROFILE_DIR; legacy scripts/browser-profile auto-migrated on first
launch. Never store the profile inside this repository.
"""
import glob
import os
import subprocess
import time
import urllib.request

import profile as _profile_mod

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

DISPLAY = os.environ.get("REPLAY_DISPLAY", ":99")
SCREEN = os.environ.get("REPLAY_WxH", "1440x900")
CDP_PORT = os.environ.get("CDP_PORT", "9222")
START_URL = os.environ.get("REPLAY_START_URL", "https://chat.z.ai/")
PROFILE = _profile_mod.resolve()


def find_chrome():
    """CHROME_BIN env -> playwright cache glob -> system chrome."""
    cand = os.environ.get("CHROME_BIN", "")
    if cand and os.path.exists(cand):
        return cand
    for pat in (
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"),
        os.path.expanduser("~/.cache/ms-playwright/chrome-linux*/chrome"),
        "/usr/bin/google-chrome*",
        "/usr/bin/chromium*",
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return ""


chrome = find_chrome()
if not chrome:
    print("ERROR: no chrome/chromium binary found. Set CHROME_BIN=/path/to/chrome")
    raise SystemExit(1)
print("chrome:", chrome)


def clear_stale_singletons(profile_dir):
    """Remove stale Chromium Singleton* locks after a hard sandbox reset.

    Incident (reset-19, 2026-10-06): the durable profile's SingletonLock
    symlink encodes the holding Chrome as `<host>-<pid>`; a machine reboot
    kills that Chrome but the symlink survives INSIDE the durable profile,
    so every subsequent Chromium launch aborts with "profile appears to be
    in use by another Chromium process" and the supervisor crash-loops
    Chrome until the locks are deleted by hand — defeating the whole
    durable-profile directive. launch_stack is the single launcher (the
    supervisor re-runs it only when CDP is dead), so a lock whose pid is
    dead or non-Chrome is definitionally stale: clear it (plus the
    Cookie/Socket symlinks). A pid that is ALIVE and IS chrome means real
    contention — leave everything untouched. Login data (Cookies, Login
    Data) lives in other files and is never touched.
    """
    import re
    lock = os.path.join(profile_dir, "SingletonLock")
    if not (os.path.islink(lock) or os.path.exists(lock)):
        return []
    holder_alive_chrome = False
    try:
        tgt = os.path.basename(os.readlink(lock)) if os.path.islink(lock) else ""
        m = re.search(r"-(\d+)$", tgt)
        if m:
            pid = int(m.group(1))
            try:
                comm = open(f"/proc/{pid}/comm").read().strip()
                holder_alive_chrome = comm.startswith("chrome")
            except OSError:
                holder_alive_chrome = False  # dead pid — stale
    except OSError:
        pass  # unreadable/dangling — stale
    if holder_alive_chrome:
        print("profile lock held by a LIVE chrome (pid in lock) — not touching")
        return []
    removed = []
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        p = os.path.join(profile_dir, name)
        try:
            if os.path.islink(p) or os.path.exists(p):
                os.remove(p)
                removed.append(name)
        except OSError:
            pass
    if removed:
        print("stale profile singleton lock cleared (holder dead/non-chrome):",
              ",".join(removed))
    return removed


clear_stale_singletons(PROFILE)

# 1. Xvfb (a duplicate display bind simply fails and exits — harmless)
p1 = subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", f"{SCREEN}x24"],
    stdout=open(os.path.join(BASE, "xvfb.log"), "w"), stderr=subprocess.STDOUT,
    start_new_session=True)
open(os.path.join(BASE, "xvfb.pid"), "w").write(str(p1.pid))
time.sleep(2)

# 2. Chrome with CDP
# Pre-installed operator extensions (e.g. TurboVPN) — auto-loaded whenever
# the directory exists, so watchdog restarts keep them installed.
EXT_ROOT = os.path.join(BASE, "extensions")
ext_args = []
if os.path.isdir(EXT_ROOT):
    for name in sorted(os.listdir(EXT_ROOT)):
        ext_dir = os.path.join(EXT_ROOT, name)
        if os.path.isdir(ext_dir) and os.path.exists(os.path.join(ext_dir, "manifest.json")):
            ext_args.append(f"--load-extension={ext_dir}")
            print("extension loaded:", ext_dir)
env = dict(os.environ)
env["DISPLAY"] = DISPLAY
# Turbo VPN extension (operator-directed fix for generation-queue geo block;
# unpacked from CRX 2.0.4 — see AGENT_BOOT_PROMPT lesson 45/49).
# Default path survives supervisor/watchdog restarts (no env needed); the env
# var overrides, and a missing dir disables the flag cleanly.
load_ext = os.environ.get("CHROME_LOAD_EXTENSION", "/home/z/turbovpn/ext")
ext_flags = []
if load_ext and os.path.isdir(load_ext):
    ext_flags.append(f"--load-extension={load_ext}")
p2 = subprocess.Popen([chrome,
    f"--remote-debugging-port={CDP_PORT}", "--remote-debugging-address=127.0.0.1",
    "--remote-allow-origins=*", f"--user-data-dir={PROFILE}",
    f"--window-size={SCREEN.replace('x', ',')}", "--window-position=0,0",
    "--no-first-run", "--no-default-browser-check",
    # 2026-10-05 (Task-20 doctrine, re-applied after reset-5 ate the live
    # tree before the commit landed): GPU compositing costs renderer memory
    # this 2GB container cannot spare — the Stripe-dashboard OOM cascade
    # (renderer SIGKILL code 9) stops with this flag. Nothing here needs
    # actual GPU output (Xvfb has none anyway).
    "--disable-gpu",
    "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
    "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding", "--disable-dev-shm-usage", "--disable-features=Translate",
    "--lang=en-US", "--no-sandbox", *ext_args, START_URL],
    stdout=open(os.path.join(BASE, "browser.log"), "w"), stderr=subprocess.STDOUT,
    start_new_session=True, env=env)
open(os.path.join(BASE, "browser.pid"), "w").write(str(p2.pid))
print(f"xvfb pid={p1.pid} chrome pid={p2.pid}")
time.sleep(8)
try:
    v = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=5).read()
    print("CDP OK:", v[:60])
except Exception as e:
    print("CDP not up yet:", e)
