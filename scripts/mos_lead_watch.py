#!/usr/bin/env python3
"""mos_lead_watch.py — resident lane watch daemon (deployment-local, §0).

Rebuilt 2026-10-22:52Z after the second sandbox reset destroyed the previous
instance (scripts/local/ is gitignored by governance).

Contract (unchanged from the pre-reset daemon):
  - Lanes are read from flags/session_registry.jsonl (name | chat_id | url).
  - PRIMARY probe axis: server-side chats API (chat.z.ai/api/v1/chats/<id>,
    Bearer JWT from flags/chat_token); the CDP tab at /c/<chat_id> is
    secondary (tabs roll home during capacity peaks — not trustworthy).
  - Completion oracle: an assistant message containing
    'MOS-COMPLETION-REPORT <ITEM> END' (last line) — verified from the
    transcript — plus the worker branch pushed to the MOS remote
    (git ls-remote /home/z/MOS, branches <family>/<num>-worker-delivery).
  - On completion: flags/<name>_done.json + agent_outbox note. The TL (in
    its own session) harvests, reviews, merges or sends require-changes,
    and dispatches the next lane; this watcher just keeps watching.
  - Patience gate (lesson-185): during capacity events queued lanes are
    NEVER nudged/attacked/re-dispatched. Queued = messages:1, zero
    assistant turns. We just watch.
  - Reaping detection: HTTP 403/404 on a lane = chat reaped server-side →
    one-shot alarm to outbox.
  - Every cycle: heartbeat file. Every 5 cycles (~10 min): visible status
    note to agent_outbox + mission-state refresh (read-modify-write of
    updatedAt + watch fields only) so the operator sees the watch is live
    in the console Mission view.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
TOKEN_PATH = os.path.join(FLAGS, "chat_token")
HB_PATH = os.path.join(FLAGS, "mos_watch_heartbeat")
MOS = "/home/z/MOS"

CYCLE_S = 120          # probe cadence
STALL_S = 30 * 60      # zero-growth alarm (assistant started only)
LOG_PATH = os.path.join(BASE, "logs", "mos_lead_watch.log")
MISSION_STATE = os.path.join(os.path.dirname(BASE), "data", "mission-state.json")
STATUS_NOTE_EVERY = 5  # cycles between visible outbox status notes (~10 min)
_cycle_count = 0

CHAT_API = "https://chat.z.ai/api/v1/chats/"


def log(msg):
    line = "[%s] %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def outbox(text):
    os.makedirs(FLAGS, exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {"ts": int(time.time() * 1000), "from": "agent", "text": text}
        ) + "\n")


def token():
    try:
        return open(TOKEN_PATH).read().strip().strip('"')
    except Exception:
        return ""


def http_chat(cid):
    tok = token()
    if not tok:
        return None
    req = urllib.request.Request(
        CHAT_API + cid,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def lane_snapshot(cid):
    """Server-side truth: (n_msgs, n_assistant, last_role, last_len,
    generating, completion_item_or_None).

    Completion oracle scans ASSISTANT messages ONLY. The dispatch prompt
    (user message) contains the literal 'MOS-COMPLETION-REPORT <ITEM> END'
    instruction line, so scanning the last message regardless of role
    produces a false positive on queued lanes (caught 2026-10-02 23:39).
    """
    d = http_chat(cid)
    rec = d.get("data", d) if isinstance(d, dict) else {}
    inner = rec.get("chat", {}) or {}
    msgs = inner.get("history", {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    msgs.sort(key=lambda m: m.get("createdAt") or 0)
    n_asst = sum(1 for m in msgs if m.get("role") == "assistant")
    last = msgs[-1] if msgs else {}
    c = last.get("content") if isinstance(last.get("content"), str) else ""
    if not c and isinstance(last.get("content"), list):
        c = " ".join(
            x.get("text", "") for x in last["content"]
            if isinstance(x, dict))
    generating = bool(inner.get("generating"))
    total_chars = 0
    item = None
    for m in msgs:
        body = m.get("content")
        if isinstance(body, list):
            body = " ".join(x.get("text", "") for x in body
                             if isinstance(x, dict))
        body = body if isinstance(body, str) else ""
        total_chars += len(body)
        if m.get("role") != "assistant":
            continue
        mm = re.search(
            r"MOS-COMPLETION-REPORT\s+([A-Z]+-[0-9]{3})\s+END", body)
        if mm:
            item = mm.group(1)
            break
    return {"n": len(msgs), "n_asst": n_asst,
            "last_role": last.get("role"), "last_len": len(c or ""),
            "chars": total_chars,
            "generating": generating, "item": item}


def branch_of(item):
    m = re.match(r"([A-Z]+)-([0-9]{3})", item or "")
    if m:
        return "%s/%s-worker-delivery" % (m.group(1).lower(), m.group(2))
    return None


def remote_sha(branch):
    try:
        out = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/" + branch],
            cwd=MOS, capture_output=True, text=True, timeout=30)
        line = (out.stdout or "").strip().split("\t")[0]
        return line if re.fullmatch(r"[0-9a-f]{40}", line) else None
    except Exception:
        return None


def load_lanes():
    """Live lanes from the registry, re-read EVERY cycle.

    2026-10-03 fix: the original daemon loaded lanes once at startup —
    every lane dispatched after the daemon started was invisible to the
    resident watch (LAB-006/MKT-073-r2/STUDIO-007 went unwatched for hours
    while the console's LIVE ORCHESTRATION strip sat empty). Now:
      - latest record per name wins (create/send/void/done);
      - a name whose LATEST record is void/failed/done is retired;
      - a done-flag file retires the name regardless of record shape;
      - chat_id/url come from the latest create/send record.
    """
    latest = {}
    try:
        with open(REG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    m = re.match(
                        r"(\S+)\s*\|\s*(https?://\S+/c/([0-9a-f-]+))",
                        line)
                    if not m:
                        continue
                    rec = {"name": m.group(1), "url": m.group(2),
                           "chat_id": m.group(3), "action": "send"}
                name = rec.get("name") or "lane"
                prev = latest.get(name)
                if prev is None or (rec.get("ts") or 0) >= (prev.get("ts") or 0):
                    latest[name] = rec
    except FileNotFoundError:
        pass
    lanes = []
    for name, rec in latest.items():
        action = rec.get("action")
        if action in ("void", "failed", "done"):
            continue  # retired — bookkeeping, not a lane
        if os.path.exists(os.path.join(FLAGS, "%s_done.json" % name)):
            continue  # done-flagged — the completion oracle already fired
        cid = rec.get("chat_id") or ""
        url = rec.get("url") or ""
        if not cid and url:
            mm = re.search(r"/c/([0-9a-f-]+)", url)
            cid = mm.group(1) if mm else ""
        if cid:
            lanes.append({"name": name, "chat_id": cid, "url": url,
                          "prompt_file": rec.get("prompt_file") or ""})
    lanes.sort(key=lambda l: l["name"])
    return lanes


def write_lane_status(name, snap, lane):
    """Per-lane status snapshot for the console's workers strip
    (flags/lane_status.<name>.json). The Replay Console's /api/workers
    surfaces these when no queue_watch spec owns the session — the
    MOS-era dispatch flow has no per-session queue watcher, so this file
    IS the live-orchestration ground truth for those lanes."""
    try:
        st = {
            "name": name,
            "chat_id": lane["chat_id"],
            "url": lane.get("url") or "",
            "ts": time.time(),
            "n": snap.get("n", 0),
            "n_asst": snap.get("n_asst", 0),
            "chars": snap.get("chars", 0),
            "generating": bool(snap.get("generating")),
            "item": snap.get("item"),
        }
        if st["item"]:
            st["state"] = "complete"
        elif st["n_asst"] > 0 and st["generating"]:
            st["state"] = "generating"
        elif st["n_asst"] > 0:
            st["state"] = "replied"
        else:
            st["state"] = "queued"
        open(os.path.join(FLAGS, "lane_status.%s.json" % name), "w").write(
            json.dumps(st, indent=1))
    except Exception:
        pass


def refresh_mission_state(note):
    try:
        d = json.load(open(MISSION_STATE, encoding="utf-8"))
        d["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                                       time.gmtime())
        d["watch"] = {"status": "live", "pid": os.getpid(),
                      "cycle_s": CYCLE_S, "last_note": note}
        json.dump(d, open(MISSION_STATE, "w", encoding="utf-8"), indent=2)
    except Exception:
        pass


def main():
    global _cycle_count
    log("MOS LEAD RESIDENT WATCH armed (cycle=%ds stall=%ds; patience gate ON)"
        % (CYCLE_S, STALL_S))
    alarmed_reaped = set()
    stalled_at = {}
    known = set()  # lanes already logged as picked up

    while True:
        _cycle_count += 1
        # 2026-10-03 fix: reload lanes EVERY cycle — dispatches that happen
        # after daemon start must enter the watch automatically (the static
        # snapshot bug let whole waves run unwatched).
        lanes = load_lanes()
        for lane in lanes:
            if lane["name"] not in known:
                known.add(lane["name"])
                log("lane picked up: %s (%s)" % (lane["name"],
                                                 lane["chat_id"][:8]))
        # retire stale status files: a lane that left the live set (void/
        # done) must not linger in the console's freshness window
        live_names = {l["name"] for l in lanes}
        try:
            for fn in os.listdir(FLAGS):
                m = re.match(r"lane_status\.(.+)\.json$", fn)
                if m and m.group(1) not in live_names:
                    os.remove(os.path.join(FLAGS, fn))
        except Exception:
            pass
        try:
            open(HB_PATH, "w").write(
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        except Exception:
            pass

        tok = token()
        parts = []
        completed_any = False
        for lane in lanes:
            name = lane["name"]
            if os.path.exists(os.path.join(FLAGS, "%s_done.json" % name)):
                parts.append("%s done-flagged" % name)
                continue
            if not tok:
                parts.append("%s awaiting-operator-login (no JWT)" % name)
                continue
            try:
                snap = lane_snapshot(lane["chat_id"])
            except urllib.error.HTTPError as e:
                if e.code in (403, 404) and name not in alarmed_reaped:
                    alarmed_reaped.add(name)
                    log("%s REAPED: HTTP %d" % (name, e.code))
                    outbox("%s chat reaped server-side (HTTP %d) — TL must "
                           "re-dispatch this lane from inside the replay"
                           % (name, e.code))
                    parts.append("%s reaped(HTTP %d)" % (name, e.code))
                elif e.code >= 500:
                    # server-side error (capacity event / auth transition):
                    # transient, NOT reaping — never alarm on these
                    parts.append("%s api-err(%d, transient)" % (name, e.code))
                else:
                    parts.append("%s http-err(%d)" % (name, e.code))
                continue
            except Exception as e:
                parts.append("%s probe-err(%s)" % (name, str(e)[:40]))
                continue

            if snap["item"]:
                br = branch_of(snap["item"])
                sha = remote_sha(br) if br else None
                if sha:
                    rec = {"item": snap["item"], "branch": br,
                           "remote_sha": sha, "ts": time.time(),
                           "chat_id": lane["chat_id"]}
                    open(os.path.join(FLAGS, "%s_done.json" % name),
                         "w").write(json.dumps(rec, indent=2))
                    log("%s COMPLETION ORACLE: %s branch=%s remote=%s" %
                        (name, snap["item"], br, sha[:10]))
                    outbox("%s completion oracle fired: %s (branch %s, "
                           "remote %s) — TL harvest next" %
                           (name, snap["item"], br, sha[:10]))
                    completed_any = True
                    parts.append("%s DONE(%s)" % (name, snap["item"]))
                else:
                    parts.append("%s report-pending-branch(%s)" %
                                 (name, snap["item"]))
                write_lane_status(name, snap, lane)
                continue

            write_lane_status(name, snap, lane)

            if snap["n_asst"] > 0 and snap["generating"]:
                key = (name,)
                if key not in stalled_at:
                    stalled_at[key] = time.time()
                elif time.time() - stalled_at[key] > STALL_S:
                    log("%s STALL: zero growth %ds" %
                        (name, time.time() - stalled_at[key]))
                    outbox("%s stall alarm: assistant generating but zero "
                           "growth for %dmin — TL inspect" %
                           (name, STALL_S // 60))
                    stalled_at[key] = time.time()
                parts.append("%s working(asst=%d gen)" %
                             (name, snap["n_asst"]))
            elif snap["n_asst"] > 0:
                parts.append("%s replied(asst=%d idle)" %
                             (name, snap["n_asst"]))
            else:
                # patience gate: queued, zero assistant turns — no nudge
                parts.append("%s queued (capacity event, patience gate)"
                             % name)

        note = "[watch] %s | hb ok | %s" % (
            time.strftime("%H:%M:%SZ"), "; ".join(parts))
        if completed_any or _cycle_count % STATUS_NOTE_EVERY == 1:
            outbox(note)
        refresh_mission_state(note)
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
