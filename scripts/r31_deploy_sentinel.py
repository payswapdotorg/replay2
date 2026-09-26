#!/usr/bin/env python3
"""r31_deploy_sentinel.py — the production-deploy watch for the R31 wave.

The Vercel git-app stopped creating deployments for this repo after 05:36Z
(the R31 merge push + a retrigger push both produced no deployment). This
sentinel polls the production alias; when the R31 build lands (the feed
route responds non-404 or the built CSS carries wfx-picker), it:
  - posts the outbox completion
  - writes flags/r31-deploy-landed
The production user-level spot-check is then run by the lead (or the
operator can simply use the app).

Poll cadence: 150s. Horizon: 24h.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

ALIAS = "https://webflix-steel.vercel.app"
FLAG = "/home/z/replay2/scripts/flags/r31-deploy-landed"
OUTBOX = "/home/z/replay2/scripts/flags/agent_outbox.jsonl"
LOG = "/home/z/replay2/scripts/logs/r31-deploy-sentinel.log"
CYCLE_S = 150
HORIZON_S = 24 * 3600


def log(m):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}", flush=True)


def fetch(url, head=False):
    try:
        req = urllib.request.Request(url, method="HEAD" if head else "GET")
        req.add_header("Cache-Control", "no-cache")
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, (b"" if head else r.read())
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return -1, str(e).encode()[:80]


def deployed():
    code, _ = fetch(ALIAS + "/feed/subscriptions", head=True)
    if code not in (404, -1):
        return f"feed route HTTP {code}"
    code, body = fetch(ALIAS + "/?cb=" + str(time.time()))
    if code == 200:
        import re
        m = re.search(rb'/_next/static/[^"\']+\.css', body)
        if m:
            css = m.group(0).decode()
            c2, cssbody = fetch(ALIAS + css)
            if c2 == 200 and b"wfx-picker" in cssbody:
                return f"css marker live ({css.rsplit('/', 1)[-1]})"
    return None


def post_outbox(text):
    rec = {"ts": int(time.time() * 1000), "from": "agent", "text": text}
    with open(OUTBOX, "a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    t0 = time.time()
    n = 0
    log("deploy sentinel start (R31)")
    while time.time() - t0 < HORIZON_S:
        n += 1
        sig = deployed()
        if sig:
            log(f"DEPLOY LANDED — {sig}")
            with open(FLAG, "w") as f:
                f.write(f"{sig} at {time.strftime('%H:%M:%SZ', time.gmtime())}\n")
            post_outbox(
                "R31 PRODUCTION DEPLOY LANDED (" + sig + "): webflix-steel.vercel.app "
                "now serves the gap wave — the theme-picker submenu + the subscriptions "
                "feed. The lead runs the production user-level spot-check next (the "
                "local user-level test already passed every golden path: the picker "
                "grammar incl. the adjudicated bare checkmark + write-throughs, the "
                "feed grid + real subscribe + click-through, zero page errors).")
            return 0
        if n % 20 == 0:
            log(f"cycle {n}: not yet (uptime {int((time.time()-t0)/60)} min)")
        time.sleep(CYCLE_S)
    log("HORIZON — deploy never landed in 24h")
    return 1


if __name__ == "__main__":
    sys.exit(main())
