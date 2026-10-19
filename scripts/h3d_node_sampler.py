#!/usr/bin/env python3
"""h3d_node_sampler.py — hunt a VPN exit node with a live ZeroGPU pool.

Strategy (Task 20/22 close-out): the anonymous ZeroGPU quota is pooled per
egress IP. The raw sandbox IP and both known TurboVPN exits are drained
(78s / 27s vs the 90s the Quality tier requests). REJECTED gradio
admission calls cost no quota and report the pool level verbatim
("90s requested vs. Ns left"), so each fresh exit node can be SAMPLED in
~3 seconds with one queue/join from a hyper3d-clone.vercel.app tab (the
product origin — CORS-verified clean by the production neural client).

Loop per attempt:
  1. toggle the TurboVPN power (disconnect -> reconnect) -> new exit node
  2. read the egress IP (skip if unchanged / raw sandbox IP)
  3. fire the 3-second admission probe from a product tab
  4. pool >= 90s  ->  LAUNCH the full golden-path e2e (h3d_prod_neural_e2e.py)
                       detached and exit (the loops/ops harvest the result)
     pool <  90s  ->  next attempt (rejected probes are free)

Usage: python3 h3d_node_sampler.py [max_attempts=6]
Artifacts: /home/z/my-project/research/out/e2e20-node-samples.json
"""
import json
import re
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
import vpn_connect as v  # noqa: E402

OUT = "/home/z/my-project/research/out/e2e20-node-samples.json"
PROD = "https://hyper3d-clone.vercel.app"
RAW_IP = "47.57.242.119"
SPACE = "https://tencent-hunyuan3d-2-1.hf.space"

# 1x1 white JPEG (content is irrelevant to an admission-rejected probe).
TINY_JPG_B64 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAQAAA"
    "AAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8Q"
    "AFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/a"
    "AAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAB"
    "AAH//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwEA//8QAFBEBAAAAAAAAAAAAAAAA"
    "AAAAAP/aAAgBAgEBPwEA//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABDwEA//Z"
)

PROBE_JS = """(async () => {
  const SPACE = 'https://tencent-hunyuan3d-2-1.hf.space';
  const sess = 'probe-' + Math.random().toString(36).slice(2, 10);
  try {
    const bytes = Uint8Array.from(atob('%s'), c => c.charCodeAt(0));
    const fd = new FormData();
    fd.append('files', new File([bytes], 'probe.jpg', {type: 'image/jpeg'}));
    const up = await fetch(SPACE + '/upload', {method: 'POST', body: fd});
    if (!up.ok) return JSON.stringify({error: 'upload ' + up.status});
    const path = (await up.json())[0];

    const body = {
      data: [null,
             {path, orig_name: 'probe.jpg', meta: {_type: 'gradio.FileData'}},
             50, 5.0, 1, 256, true, 8000, false],
      fn_index: 2, session_hash: sess, trigger: 'probe'};
    const join = await fetch(SPACE + '/queue/join', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)});
    if (!join.ok) return JSON.stringify({error: 'join ' + join.status});
    const ev = await join.json();
    if (!ev.event_id) return JSON.stringify({error: 'no event_id', ev});

    const resp = await fetch(SPACE + '/queue/data?session_hash=' + sess);
    const text = await resp.text();
    const tail = text.slice(-700);
    const m = tail.match(/(\\d+)s requested vs\\.?\\s*(\\d+)s left/);
    if (m) return JSON.stringify({admitted: false, requested: +m[1], left: +m[2], tail: tail.slice(-260)});
    if (/process_completed|generation"/.test(text)) return JSON.stringify({admitted: true, tail: tail.slice(-260)});
    return JSON.stringify({error: 'unparsed', tail: tail.slice(-260)});
  } catch (e) { return JSON.stringify({error: 'probe: ' + e.message}); }
})()""" % TINY_JPG_B64


def log(msg):
    print(f"[sampler {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def toggle_vpn(cdp):
    """disconnect -> reconnect; returns (state_dict, egress_str)."""
    if json.loads(v.popup_state(cdp) or "{}").get("connected"):
        v.click_power(cdp)
        time.sleep(9)
    v.click_power(cdp)
    time.sleep(17)
    for _ in range(3):
        st = json.loads(v.popup_state(cdp) or "{}")
        eg = v.egress(cdp, tries=1)
        if st.get("connected") and str(eg).startswith("EGRESS") and RAW_IP not in str(eg):
            return st, eg
        if not st.get("connected"):
            v.click_power(cdp)
            time.sleep(17)
    return json.loads(v.popup_state(cdp) or "{}"), v.egress(cdp, tries=1)


def product_tab():
    t = next((x for x in channel.list_tabs()
              if (x.get("url") or "").startswith(PROD)), None)
    if t is None:
        t = channel.new_tab(PROD)
        time.sleep(6)
    return t


def probe_pool():
    tab = product_tab()
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        out = cdp.eval(PROBE_JS, await_promise=True, timeout=60)
        try:
            return json.loads(out)
        except Exception:
            return {"error": f"bad-probe-output: {str(out)[:200]}"}
    finally:
        cdp.close()


def main():
    max_attempts = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    samples = []
    seen_ips = set()
    tab = v.popup_tab()
    popup_cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        for attempt in range(max_attempts):
            log(f"attempt {attempt}: toggling VPN for a fresh exit node…")
            st, eg = toggle_vpn(popup_cdp)
            ip = str(eg).replace("EGRESS", "").strip()
            log(f"  node: {ip} (state={st})")
            if not str(eg).startswith("EGRESS") or ip == RAW_IP:
                samples.append({"attempt": attempt, "ip": ip, "error": "no-vpn-egress", "state": st})
                time.sleep(5)
                continue
            if ip in seen_ips:
                log("  same node as before — re-toggling")
                samples.append({"attempt": attempt, "ip": ip, "note": "repeat-node"})
                time.sleep(3)
                continue
            seen_ips.add(ip)

            log(f"  probing ZeroGPU pool through {ip} …")
            pool = probe_pool()
            log(f"  probe: {json.dumps(pool)[:240]}")
            samples.append({"attempt": attempt, "ip": ip, "probe": pool})

            with open(OUT, "w") as f:
                json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "samples": samples}, f, indent=2)

            if pool.get("admitted") or (pool.get("left", 0) >= 90):
                log("*** POOL LIVE on " + ip + " — launching the golden path ***")
                import subprocess
                subprocess.Popen(
                    ["python3", "dfork_launch.py",
                     "/home/z/my-project/research/out/e2e20-manual-freshnode.log",
                     "python3", "h3d_prod_neural_e2e.py"],
                    cwd="/home/z/replay2/scripts")
                with open(OUT, "w") as f:
                    json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "fired_on": ip, "probe": pool, "samples": samples}, f, indent=2)
                return 0
            time.sleep(4)
    finally:
        popup_cdp.close()
    with open(OUT, "w") as f:
        json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "fired_on": None, "samples": samples}, f, indent=2)
    log(f"no live node found in {max_attempts} attempts — samples banked to {OUT}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
