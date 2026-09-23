#!/usr/bin/env python3
"""pa_server_watch.py <name> <chat-id> — server-side worker watcher.

REBUILD NOTE (2026-09-23): the PA-era original was lost in sandbox wipe #3;
rebuilt from the Task-85/86h worklog doctrine — for a LIVE worker the
server-side watch is the safe, wedge-proof completion signal (queue_watch's
tablost path can void healthy sessions during load windows; markers from it
are advisory only). This watcher polls the chat via the lesson-107 HTTP
rail (chats_http.get_token/api — no tabs), heartbeats to
flags/pa_server_watch_heartbeat.<name>, and writes transition markers:

  flags/pa_server_watch.<name>.preturn    assistant turn not spawned yet
  flags/pa_server_watch.<name>.generating assistant content is growing
  flags/pa_server_watch.<name>.complete   report marker matched (exit 0)
  flags/pa_server_watch.<name>.stall      frozen > STALL_S with no report
  flags/pa_server_watch.<name>.reaped     chat gone at the API (exit 1)

Content-wipe discipline (Task 86g): server-side chat detail NEVER proves
turn liveness by content (the platform wipes assistant content after
death/completion) — this watcher only reports what it SEES; harvest-verify
(bundle + real-SHA) remains the only truth for delivery.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http  # noqa: E402

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
POLL_S = 45
STALL_S = 2700  # 45 min frozen with no report
ERR_LIMIT = 10
REARM_AFTER_S = 300   # preturn with no assistant for 5min = bounced landing
REARM_STALE_S = 600   # ... and the chat's span never grew = zombie-shaped

REPORT_RE = re.compile(
    r"ROAMLINK\s+[A-Z0-9./-]+\s+COMPLETION\s+REPORT\s+@\s*([0-9a-f]{40})\s+END")


def marker(name, kind, **extra):
    path = os.path.join(FLAGS, f"pa_server_watch.{name}.{kind}")
    with open(path, "w") as f:
        json.dump({"ts": int(time.time() * 1000), **extra}, f)


def heartbeat(name):
    path = os.path.join(FLAGS, f"pa_server_watch_heartbeat.{name}")
    with open(path, "w") as f:
        f.write(str(int(time.time() * 1000)))


def once(name, kind):
    return not os.path.exists(os.path.join(FLAGS, f"pa_server_watch.{name}.{kind}"))


def chat_state(chat_id):
    """(n_msgs, n_assistant, assistant_len, updated_at) from chat detail."""
    data = chats_http.api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = (inner.get("history", {}) or {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    n_assistant = 0
    assistant_len = 0
    report_sha = None
    for m in msgs:
        if m.get("role") != "assistant":
            continue
        n_assistant += 1
        content = m.get("content")
        if isinstance(content, str):
            assistant_len += len(content)
            mm = REPORT_RE.search(content)
            if mm:
                report_sha = mm.group(1)
    updated = rec.get("updated_at") or rec.get("updatedAt") or inner.get("updated_at")
    created = rec.get("created_at") or rec.get("createdAt") or inner.get("created_at")
    return len(msgs), n_assistant, assistant_len, updated, report_sha, created


def parse_ts(updated):
    if not updated:
        return None
    if isinstance(updated, (int, float)):
        ts = float(updated)
        return ts / 1000 if ts > 1e12 else ts
    try:
        from datetime import datetime, timezone
        s = str(updated).replace("Z", "+00:00")
        return datetime.fromisoformat(s).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def zombie_rearm(name, chat_id, created):
    """Autonomy backstop (2026-09-23): a landing whose turn never spawned
    (no assistant, span frozen, 5+ min old) bounced. The assault poller's
    rc=0 clear trusts fresh landings; this catches the fooled ones — void
    the registry row, re-write the capacity flag, log once per name."""
    rearm_marker = os.path.join(FLAGS, f"pa_server_watch.{name}.rearmed-{chat_id[:8]}")
    if os.path.exists(rearm_marker):
        return
    reg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "flags", "session_registry.jsonl")
    prompt_file, url = None, None
    try:
        for line in open(reg).read().split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("name") == name:
                if r.get("prompt_file"):
                    prompt_file = r["prompt_file"]
                if r.get("url"):
                    url = r["url"]
    except Exception:
        pass
    if not prompt_file:
        return
    try:
        with open(reg, "a") as f:
            f.write(json.dumps({"action": "void", "name": name,
                                "note": "server-side zombie re-arm: turn never spawned "
                                        f"(chat {chat_id} preturn 5+min, span frozen) — "
                                        "assault re-armed by pa_server_watch"}) + "\n")
        flag = {"name": name, "prompt_file": prompt_file}
        with open(os.path.join(FLAGS, f"capacity_recover.{name}.json"), "w") as f:
            f.write(json.dumps(flag))
        open(rearm_marker, "w").write(str(int(time.time())))
        print(f"[{name}] ZOMBIE RE-ARM: landing bounced (no turn, 5+min) — "
              f"registry voided + capacity flag re-armed", flush=True)
    except Exception as e:
        print(f"[{name}] re-arm failed: {e!r}", flush=True)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    name, chat_id = sys.argv[1], sys.argv[2]
    chat_id = chat_id.removeprefix("chat-")
    print(f"[pa_server_watch] {name} watching {chat_id} every {POLL_S}s", flush=True)
    errs = 0
    frozen_since = None
    last_len = -1
    try:
        while True:
            heartbeat(name)
            try:
                n_msgs, n_asst, alen, updated, sha, created = chat_state(chat_id)
                errs = 0
            except Exception as e:
                errs += 1
                print(f"[{name}] api error #{errs}: {e!r}", flush=True)
                if errs >= ERR_LIMIT:
                    marker(name, "reaped", errors=errs)
                    print(f"[{name}] chat unreachable {errs}x — reaped marker, exit", flush=True)
                    return 1
                time.sleep(POLL_S)
                continue

            if sha:
                marker(name, "complete", sha=sha, msgs=n_msgs, assistant_len=alen)
                print(f"[{name}] REPORT @ {sha} — complete marker, exit 0", flush=True)
                return 0

            if n_asst == 0:
                if once(name, "preturn"):
                    marker(name, "preturn", msgs=n_msgs)
                    print(f"[{name}] pre-turn ({n_msgs} msgs, no assistant yet)", flush=True)
                cts = parse_ts(created)
                uts = parse_ts(updated)
                if cts and time.time() - cts > REARM_AFTER_S \
                        and (uts is None or uts - cts < REARM_STALE_S):
                    zombie_rearm(name, chat_id, cts)
                frozen_since = None
                last_len = -1
            else:
                if os.path.exists(os.path.join(FLAGS, f"pa_server_watch.{name}.preturn")):
                    os.remove(os.path.join(FLAGS, f"pa_server_watch.{name}.preturn"))
                if alen > last_len:
                    if frozen_since is not None:
                        print(f"[{name}] resumed growing ({last_len} -> {alen})", flush=True)
                    if once(name, "generating"):
                        marker(name, "generating", assistant_len=alen)
                        print(f"[{name}] GENERATING ({n_msgs} msgs, assistant {alen} chars)", flush=True)
                    frozen_since = None
                    last_len = alen
                else:
                    now = time.time()
                    uts = parse_ts(updated)
                    anchor = uts if uts else now
                    if frozen_since is None:
                        frozen_since = now if not uts else min(now, now)
                        frozen_since = now
                        frozen_anchor_len = alen
                    elif now - frozen_since > STALL_S:
                        if once(name, "stall"):
                            marker(name, "stall", assistant_len=alen,
                                   frozen_s=int(now - frozen_since))
                            print(f"[{name}] STALL: frozen {int((now-frozen_since)/60)}min "
                                  f"at {alen} chars, no report — TL decision pending", flush=True)
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
