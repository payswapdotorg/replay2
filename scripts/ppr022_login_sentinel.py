#!/usr/bin/env python3
"""ppr022_login_sentinel.py — reset8 epoch (2026-10-01 11:20Z): on operator
login, DIAGNOSE the PPR-022 (Hermes-Agent) worker state. Read-only.

State at authoring (2026-10-01 11:20 UTC, reset8):
  - Machine rebooted 11:06Z; full stack recovered 11:10-11:16
    (console :3000 Replay Console identity verified via launch_dev.py —
    my-project was re-provisioned to the PRISTINE scaffold by the reset,
    so the durable launcher flag flags/console_launcher.txt=launch_dev.py;
    Chrome CDP :9222 fresh profile; replayd :3100; VPN egress 79.110.54.211;
    PG rail :55432; supervisor ring UP).
  - FRONTIER TRUTH (Zeck origin/main 0d2c9dc): PPR-020 delivered (PR #162),
    PPR-021 delivered (PR #163, currentBase c6f8957), eligible=[PPR-022].
    PPR-022 WIP branch work/PPR-022-hermes-agent-proof @ d81abf3 (the
    Lead narrative-harvest rebuild, 31 files / 9008 insertions) was pushed
    02:24Z and the worker RE-DISPATCHED on it (§10h protocol).
  - Pre-reset forensics (§10k): the worker reported "2 pre-existing
    architecture failures on clean 0d2c9dc" — DISPROVEN (stale main refs;
    Lead's integration run: 139 files / 2230 tests / ZERO failures). Cure:
    pre-gate `git fetch origin main:main` ref sync.
  - browser_login=logged-out(guest) — the wiped browser profile gates
    everything (batch-store probes need the tab's localStorage token).

On login (30s poll, 16h window, read-only — NO release, NO dispatch):
  1. chats_http.py list 60 — enumerate; find hermes/PPR-022 candidates.
  2. Per candidate: chats_http.py turns <uuid> + batch_tail.py <uuid> 8 —
     capture msgs/updated/batchLen/nBlocks + the §10e report-marker verdict
     (a text block containing BOTH "=== PPR-022 COMPLETION REPORT ===" and
     "=== END REPORT ===").
  3. check_workspaces.py — snapshot slot rows (Expired/Live) for the Lead's
     release decision (§9a/§9b: never auto-release).
  4. Verdict JSON -> flags/ppr022_probe_verdict.json + outbox summary.

Launch detached: dfork_launch.py /tmp/ppr022_sentinel.log <py> ppr022_login_sentinel.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
VERDICT = os.path.join(FLAGS, "ppr022_probe_verdict.json")

STATUS_URL = "http://localhost:3000/api/status"
REPORT_START = "=== PPR-022 COMPLETION REPORT ==="
REPORT_END = "=== END REPORT ==="
CANDIDATE_RE = re.compile(r"hermes|ppr[-_ ]?022", re.I)


def log(msg):
    print(f"[{time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post(text):
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def heartbeat():
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(os.path.join(FLAGS, "ppr022_sentinel.heartbeat"), "w") as f:
            f.write(str(int(time.time() * 1000)))
    except Exception:
        pass


def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=BASE)
        return (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired:
        return "", 124
    except Exception as e:
        return f"ERR {e}", 125


def login_state():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=8) as r:
            d = json.loads(r.read().decode())
        return str(d.get("browser_login", ""))
    except Exception:
        return ""


def probe_candidate(cid, title):
    """Server-side probe of one chat. Full UUID only (§9d)."""
    out = {"id": cid, "title": title}
    txt, _ = run([PY, os.path.join(BASE, "chats_http.py"), "turns", cid], timeout=120)
    out["turns_raw"] = txt[-3000:]
    m = re.search(r"msgs[=: ]+(\d+)", txt)
    if m:
        out["msgs"] = int(m.group(1))
    btxt, _ = run([PY, os.path.join(BASE, "batch_tail.py"), cid, "8"], timeout=180)
    out["batch_raw"] = btxt[-4000:]
    m = re.search(r"totalLen:\s*(\d+)", btxt)
    if m:
        out["batchChars"] = int(m.group(1))
    m = re.search(r"nBlocks:\s*(\d+)", btxt)
    if m:
        out["nBlocks"] = int(m.group(1))
    # §10e verdict shape — a block containing BOTH markers (co-occurrence
    # in the same block; reasoning quotes that mention the phrase without
    # the END line do not count).
    out["report_marker"] = (REPORT_START in btxt) and (REPORT_END in btxt)
    return out


def main():
    log("ppr022 login sentinel armed (reset8, read-only diagnostics)")
    post("Reset8 sentinel armed: waiting for operator login through the replay "
         "console (preview panel, port 3000). On login I will diagnose the "
         "PPR-022 Hermes worker state (chat enumeration + batch-store report "
         "probe) and post the verdict here. No dispatch until the Lead "
         "reviews. — Tech Lead")
    deadline = time.time() + 16 * 3600
    n = 0
    while time.time() < deadline:
        heartbeat()
        st = login_state()
        if st.startswith("logged-in"):
            log(f"LOGIN DETECTED: {st}")
            post(f"Login detected ({st}) — PPR-022 diagnosis starting.")
            break
        n += 1
        if n % 20 == 0:
            log(f"still waiting for login (state={st or 'unreachable'})")
        time.sleep(30)
    else:
        log("16h window expired without login — exiting")
        post("Sentinel window expired (16h, no login). Re-arm needed.")
        return 1

    time.sleep(20)  # let the UI settle + token land in localStorage

    # 1. enumerate chats
    txt, _ = run([PY, os.path.join(BASE, "chats_http.py"), "list", "60"], timeout=120)
    log("chats list:\n" + txt[-2500:])
    candidates = []
    try:
        # chats_http list prints JSON lines or a table; parse ids defensively
        for m in re.finditer(r'[{"\']?(id|chat_id)["\']?\s*[:=]\s*["\']([0-9a-f-]{36})["\']', txt):
            cid = m.group(2)
            tm = re.search(r'["\']?title["\']?\s*[:=]\s*["\']([^"\']{0,120})', txt[m.end():m.end() + 300])
            title = tm.group(1) if tm else ""
            if CANDIDATE_RE.search(title) or CANDIDATE_RE.search(cid):
                if cid not in [c["id"] for c in candidates]:
                    candidates.append({"id": cid, "title": title})
    except Exception as e:
        log(f"candidate parse error: {e}")
    # fallback: any line mentioning hermes/ppr-022 with a uuid
    for line in txt.splitlines():
        if CANDIDATE_RE.search(line):
            m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", line)
            if m and m.group(1) not in [c["id"] for c in candidates]:
                tm = re.search(r'title["\']?\s*[:=]\s*["\']([^"\']{0,120})', line)
                candidates.append({"id": m.group(1), "title": (tm.group(1) if tm else line[:100])})
    log(f"candidates: {json.dumps(candidates, indent=1)}")

    # 2. probe each candidate (max 4)
    probed = []
    for c in candidates[:4]:
        try:
            r = probe_candidate(c["id"], c.get("title", ""))
            probed.append(r)
            log(f"probe {c['id'][:8]}: msgs={r.get('msgs')} batchChars={r.get('batchChars')} "
                f"nBlocks={r.get('nBlocks')} report={r.get('report_marker')}")
        except Exception as e:
            log(f"probe error {c['id'][:8]}: {e}")

    # 3. workspace snapshot (read-only)
    wtxt, _ = run([PY, os.path.join(BASE, "check_workspaces.py")], timeout=120)
    log("workspaces:\n" + wtxt[-2000:])

    verdict = {
        "ts": int(time.time() * 1000),
        "login": st,
        "candidates": probed,
        "chats_list_tail": txt[-3000:],
        "workspaces_tail": wtxt[-2000:],
    }
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(VERDICT, "w") as f:
            json.dump(verdict, f, indent=1)
    except Exception as e:
        log(f"verdict write error: {e}")

    summ = "; ".join(
        f"{r['id'][:8]} msgs={r.get('msgs')} batch={r.get('batchChars')} blocks={r.get('nBlocks')} "
        f"REPORT={'YES' if r.get('report_marker') else 'no'}"
        for r in probed) or "no hermes-titled chat found — Lead must enumerate manually"
    post(f"PPR-022 diagnosis complete: {summ}. Verdict file: flags/ppr022_probe_verdict.json. "
         "Lead review next (§10j: no re-dispatch without stale-differential).")
    log("SENTINEL DONE — verdict written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
