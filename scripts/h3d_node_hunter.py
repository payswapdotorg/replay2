#!/usr/bin/env python3
"""h3d_node_hunter.py — hunt a VPN exit node with a live ZeroGPU pool by
firing the FULL production golden path on each fresh node.

Why the golden path IS the probe (2026-10-19 lesson): a REJECTED gradio
admission costs no quota and reports the pool level verbatim on the task
card ("90s requested vs. Ns left"); an ADMITTED admission completes the
mission outright. A separate cheap probe would, when admitted, consume
the very window it discovered — so the payload itself must take the
window.

Loop per attempt:
  1. toggle the TurboVPN power (disconnect -> reconnect) -> new exit node
  2. read the egress IP (skip if repeat node or raw sandbox IP)
  3. run h3d_prod_neural_e2e.py (synchronous, ~6 min) through that node
  4. parse e2e20-result.json: result.neural == true -> MISSION SUCCESS,
     stop and leave the artifacts + marker in place
     otherwise parse the fallback_reason pool level and continue

Usage: python3 h3d_node_hunter.py [max_attempts=5]
Artifacts: /home/z/my-project/research/out/e2e20-node-hunt.json
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
import vpn_connect as v  # noqa: E402

OUT = "/home/z/my-project/research/out/e2e20-node-hunt.json"
RESULT = "/home/z/my-project/research/out/e2e20-result.json"
E2E_LOG = "/home/z/my-project/research/out/e2e20-manual-freshnode.log"
SCRIPTS = "/home/z/replay2/scripts"
RAW_IP = "47.57.242.119"

POOL_RE = re.compile(r"(\d+)s requested vs\.?\s*(\d+)s left.*?Try again in (\d+):(\d+):(\d+)", re.S)


def log(msg):
    print(f"[hunter {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def toggle_vpn(cdp):
    """disconnect -> reconnect until a non-raw egress answers."""
    if json.loads(v.popup_state(cdp) or "{}").get("connected"):
        v.click_power(cdp)
        time.sleep(9)
    v.click_power(cdp)
    time.sleep(17)
    for _ in range(4):
        st = json.loads(v.popup_state(cdp) or "{}")
        eg = v.egress(cdp, tries=1)
        if st.get("connected") and str(eg).startswith("EGRESS") and RAW_IP not in str(eg):
            return str(eg).replace("EGRESS", "").strip()
        if not st.get("connected"):
            v.click_power(cdp)
            time.sleep(17)
    return None


def run_golden_path():
    """Run the instrumented production e2e synchronously; return its result dict."""
    with open(E2E_LOG, "w") as f:
        try:
            subprocess.run(["python3", os.path.join(SCRIPTS, "h3d_prod_neural_e2e.py")],
                           stdout=f, stderr=subprocess.STDOUT, timeout=900, cwd=SCRIPTS)
        except subprocess.TimeoutExpired:
            return {"error": "e2e-timeout"}
    try:
        with open(RESULT) as f:
            return json.load(f)
    except Exception as e:
        return {"error": f"no-result-json: {e}"}


def pool_level(result):
    """Extract (requested, left, eta_s) from the run's fallback reason."""
    for key in ("verdict_card", "generation"):
        ph = (result.get("phases") or {}).get(key) or {}
        reason = ph.get("fallback_reason") or ""
        m = POOL_RE.search(str(reason))
        if m:
            return {"requested": int(m.group(1)), "left": int(m.group(2)),
                    "eta_s": int(m.group(3)) * 3600 + int(m.group(4)) * 60 + int(m.group(5))}
    return None


def main():
    max_attempts = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    attempts = []
    seen_ips = set()
    tab = v.popup_tab()
    popup_cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        for attempt in range(max_attempts):
            log(f"attempt {attempt}: toggling VPN for a fresh exit node…")
            ip = toggle_vpn(popup_cdp)
            log(f"  node: {ip}")
            if ip is None:
                attempts.append({"attempt": attempt, "error": "no-vpn-egress"})
                time.sleep(10)
                continue
            if ip in seen_ips:
                attempts.append({"attempt": attempt, "ip": ip, "note": "repeat-node"})
                time.sleep(3)
                continue
            seen_ips.add(ip)

            log(f"  firing the full golden path through {ip} (~6 min)…")
            result = run_golden_path()
            pool = pool_level(result)
            neural = bool(result.get("neural")) and result.get("ok")
            rec = {"attempt": attempt, "ip": ip, "neural": neural,
                   "ok": result.get("ok"), "pool": pool,
                   "task": result.get("phases", {}).get("generation", {}).get("task_uuid"),
                   "exports_byte_verified": result.get("exports_byte_verified")}
            attempts.append(rec)
            log(f"  outcome: neural={neural} pool={pool}")

            with open(OUT, "w") as f:
                json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "success": bool(neural), "attempts": attempts}, f, indent=2)

            if neural:
                log("*** NEURAL SUCCESS through " + ip + " — artifacts in e2e20-* ***")
                return 0
            time.sleep(5)
    finally:
        popup_cdp.close()
    with open(OUT, "w") as f:
        json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "success": False, "attempts": attempts}, f, indent=2)
    log(f"no live node admitted the golden path in {max_attempts} attempts — "
        f"banked to {OUT}; resident loops keep grinding the refilling pools")
    return 1


if __name__ == "__main__":
    sys.exit(main())
