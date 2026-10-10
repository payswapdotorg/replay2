#!/usr/bin/env python3
"""emergency_lane_driver.py v3 — milestone-driven console-agent executor.

Fixes the v2 hallucinated-completion failure (2026-10-10 00:3xZ: the agent
emitted a full relay bundle claiming all tests passed while the repo held
one 136-line file and zero commits — turns degraded 78s→15s into
fabrication under continuation pressure).

v3 design:
  - TL2 supplies a MILESTONE LIST (a JSON file): each milestone is a short,
    concrete, single-package objective with an exact git-log needle and a
    verification command (run by THIS driver on the box, not trusted from
    the agent's claims).
  - Per milestone: send the work order; after each agent turn, VERIFY the
    repo state (git log needle present? verification command exits 0?).
      - verified  -> next milestone
      - not       -> send a REALITY continuation: exactly what the repo
                     shows (missing commit / failing command output tail)
                     and the instruction to do the work for real
  - The relay bundle is only accepted when the FINAL milestone's needle +
    gate pass; the driver writes it to worker-reports/ with the verified
    evidence appended by TL2.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
LOGDIR = os.path.join(ROOT, "logs")
OUTDIR = os.path.join(ROOT, "worker-reports")
FLAGS = os.path.join(ROOT, "flags")
URL = "http://127.0.0.1:3000/api/agent/chat"
REPO = "/home/z/WebFlix-Desktop"

REALITY = """REALITY CHECK (driver-verified, do not argue with it):
- git log needle "%s": %s
- verification command `%s`: %s
%s
Do the actual work now: write the real files, run the real commands, and
commit with the exact message. Do not claim completion without the commit
and the passing gate. Do not summarize — execute."""


def log(conv, msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    with open(os.path.join(LOGDIR, "emergency-%s.log" % conv), "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(cmd, cwd=REPO, timeout=420):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def verify(m):
    """(ok, detail) — repo-state truth for milestone m."""
    rc, out = run("git log --oneline -20 --all")
    needle_ok = m["needle"] in out
    gate_rc, gate_out = run(m["gate"], timeout=m.get("gate_timeout", 420))
    ok = needle_ok and gate_rc == 0
    detail = ("needle %s; gate rc=%d out_tail=%s"
              % ("FOUND" if needle_ok else "MISSING", gate_rc, gate_out.strip()[-400:]))
    return ok, needle_ok, gate_rc, gate_out, detail


def post_turn(messages, conv_id, model="glm-5.3"):
    body = json.dumps({"messages": messages, "conversation_id": conv_id,
                       "model": model}).encode()
    req = urllib.request.Request(URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    assistant_text = []
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                d = json.loads(line[6:])
            except Exception:
                continue
            if d.get("type") == "delta" and d.get("text"):
                assistant_text.append(d["text"])
            elif d.get("type") == "status" and d.get("text"):
                assistant_text.append("\n[status] %s" % d["text"][:200])
            elif d.get("type") == "error":
                assistant_text.append("\n[API-ERROR] %s" % str(d.get("message", ""))[:300])
    return "".join(assistant_text)


def main():
    milestones_path, conv, max_turns_per_ms = sys.argv[1], sys.argv[2], int(sys.argv[3])
    milestones = json.load(open(milestones_path))
    os.makedirs(LOGDIR, exist_ok=True)
    # resume: skip milestones whose needle+gate already hold (repo-state truth)
    start_mi = 0
    for i, m in enumerate(milestones):
        ok, _, _, _, _ = verify(m)
        if ok:
            start_mi = i + 1
        else:
            break
    if start_mi > 0:
        log(conv, "resume: milestones 1..%d already verified — starting at %d"
            % (start_mi, start_mi + 1))
    milestones = milestones[start_mi:]
    os.makedirs(OUTDIR, exist_ok=True)
    messages = []
    final_bundle = None

    for mi, m in enumerate(milestones):
        intro = m["order"] if mi == 0 else (
            "Milestone %d/%d COMPLETE (verified by TL2). Next milestone:\n\n%s"
            % (mi, len(milestones), m["order"]))
        messages.append({"role": "user", "content": intro})
        log(conv, "milestone %d (%s): turn 1" % (mi + 1, m["id"]))
        turn = 0
        ms_deadline = time.time() + 45 * 60  # 45 min per milestone wall clock
        rl_backoff = 60
        while turn < max_turns_per_ms and time.time() < ms_deadline:
            turn += 1
            t0 = time.time()
            try:
                text = post_turn(messages, conv)
            except Exception as e:
                log(conv, "milestone %d turn %d API FATAL: %r" % (mi + 1, turn, e))
                time.sleep(30)
                turn -= 1
                continue
            dt = time.time() - t0
            # rate-limit awareness: a 429 turn is a WAIT, not a work turn
            if "[API-ERROR]" in text and ("429" in text or "no model backend" in text):
                log(conv, "milestone %d turn %d RATE-LIMITED — backing off %ds (turn not consumed)"
                    % (mi + 1, turn, rl_backoff))
                with open(os.path.join(LOGDIR, "emergency-%s-transcript.txt" % conv), "a") as f:
                    f.write("\n===== MILESTONE %d TURN %d (%.0fs) RATE-LIMITED =====\n%s\n"
                            % (mi + 1, turn, dt, text))
                time.sleep(rl_backoff)
                rl_backoff = min(360, int(rl_backoff * 1.5))
                turn -= 1
                continue
            rl_backoff = 60
            log(conv, "milestone %d turn %d done in %.0fs (%d chars)"
                % (mi + 1, turn, dt, len(text)))
            with open(os.path.join(LOGDIR, "emergency-%s-transcript.txt" % conv), "a") as f:
                f.write("\n===== MILESTONE %d TURN %d (%.0fs) =====\n%s\n"
                        % (mi + 1, turn, dt, text))
            messages.append({"role": "assistant",
                             "content": text.strip() or "(turn produced no text)"})
            ok, needle_ok, gate_rc, gate_out, detail = verify(m)
            log(conv, "milestone %d verify: %s" % (mi + 1, detail[:300]))
            if ok:
                log(conv, "milestone %d VERIFIED — advancing" % (mi + 1))
                if mi == len(milestones) - 1:
                    final_bundle = text
                break
            # reality continuation with hard evidence
            evidence = ""
            if not needle_ok:
                rc2, log_out = run("git log --oneline -5")
                evidence += "- git log (top 5):\n%s\n" % log_out.strip()
            if gate_rc != 0:
                evidence += "- gate output tail:\n%s\n" % gate_out.strip()[-600:]
            messages.append({"role": "user", "content":
                REALITY % (m["needle"],
                           "FOUND" if needle_ok else "MISSING",
                           m["gate"], "rc=%d" % gate_rc, evidence)})
        else:
            log(conv, "milestone %d FAILED after %d turns — halting for TL2"
                % (mi + 1, max_turns_per_ms))
            return 5

    if final_bundle:
        out = os.path.join(OUTDIR, "%s-report.txt" % conv)
        with open(out, "w") as f:
            f.write(final_bundle)
        with open(os.path.join(FLAGS, "%s-report-ready" % conv), "w") as f:
            f.write("ts=%d\n" % time.time())
        log(conv, "ALL MILESTONES VERIFIED + BUNDLE captured -> %s" % out)
        return 0
    return 6


if __name__ == "__main__":
    sys.exit(main())
