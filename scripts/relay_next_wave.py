#!/usr/bin/env python3
"""relay_next_wave.py — arm the next capacity fighter when the prior item lands.

Lesson-108 contract: flags are the arming interface, the supervisor is the
launcher. This relay watches the PRIOR item's capacity flag; when the flag
disappears AND the registry's last row for the prior item shows sent=true
(a real landing), it settles 90s, then atomically writes the NEXT item's
flag (capacity_recover.<next>.json). The supervisor auto-spawns a persistent
recover_capacity.py fighter for it.

The relay sequences the ASSAULT side only — the TL's verify/merge quality
gate stays fully manual.

Usage:
  relay_next_wave.py <prior-name> <next-name> <prompt-file>

Exit codes:
  0  next flag armed (or already armed / prior already done)
  1  prior's last registry row is failed/voided — landing never happened
  2  timeout (PRIOR flag never cleared within RELAY_TIMEOUT_S)
"""
import json
import os
import sys
import time
import tempfile
import urllib.request
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")

SETTLE_S = 90
POLL_S = 60
RELAY_TIMEOUT_S = int(os.environ.get("RELAY_TIMEOUT_S", "21600"))  # 6h default


def prior_flag_path(prior: str) -> str:
    return os.path.join(FLAGS, f"capacity_recover.{prior}.json")


def next_flag_path(next_name: str) -> str:
    return os.path.join(FLAGS, f"capacity_recover.{next_name}.json")


def last_row_for(name: str):
    """Walk-order semantics: the LAST registry row mentioning name wins."""
    row = None
    try:
        with open(REGISTRY, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("name") == name:
                    row = rec
    except FileNotFoundError:
        return None
    return row


def chat_exists_server_side(url: str) -> bool | None:
    """Lesson-106 phantom check: the ONLY landing truth is the server tree.

    Returns True (chat in list), False (phantom), or None (tooling failure —
    caller fails OPEN with a warning so the pipeline never dead-locks on
    monitoring tooling).
    """
    m = re.search(r"/c/([0-9a-f-]{36})", url or "")
    if not m:
        return None
    chat_id = m.group(1)
    tok = ""
    cache = os.path.join(FLAGS, "chat_token")
    if os.path.isfile(cache):
        tok = open(cache).read().strip()
    if not tok:
        try:
            import channel
            js = "JSON.stringify(localStorage.getItem('token') || '')"
            for t in channel.list_tabs():
                if "chat.z.ai" not in (t.get("url") or ""):
                    continue
                try:
                    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                    raw = c.eval(js, timeout=10)
                    c.close()
                    tok = (json.loads(raw) if raw.startswith('"') else raw).strip().strip('"')
                    if tok:
                        with open(cache, "w") as fh:
                            fh.write(tok)
                        os.chmod(cache, 0o600)
                        break
                except Exception:
                    continue
        except Exception:
            return None
    if not tok:
        return None
    try:
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/chats/list?limit=100",
            headers={"Authorization": f"Bearer {tok.strip('\"')}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    return any((it.get("id") or "") == chat_id for it in items)


def write_flag_atomic(path: str, payload: dict) -> None:
    """Lesson-65: tmp + rename so the supervisor never reads a half-write."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".relay-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    prior, next_name, prompt_file = sys.argv[1], sys.argv[2], sys.argv[3]
    prompt_file = os.path.abspath(prompt_file)
    if not os.path.isfile(prompt_file):
        print(f"relay: prompt file missing: {prompt_file}")
        return 2

    print(f"relay: prior={prior} next={next_name} prompt={prompt_file}")
    started = time.time()
    armed = False
    flag_seen = os.path.exists(prior_flag_path(prior))
    if not flag_seen:
        print(f"relay: prior flag absent at start — checking registry verdict")

    while time.time() - started < RELAY_TIMEOUT_S:
        # Already armed by someone else? Done.
        if os.path.exists(next_flag_path(next_name)):
            print(f"relay: next flag {next_name} already present — exiting")
            return 0

        exists = os.path.exists(prior_flag_path(prior))
        if exists:
            flag_seen = True
            time.sleep(POLL_S)
            continue

        # Flag vanished (or never existed). Registry decides what happened.
        row = last_row_for(prior)
        if row is None:
            print(f"relay: no registry row for {prior} — nothing to chain")
            return 1
        if row.get("action") in ("failed", "void", "voided", "done"):
            print(f"relay: prior {prior} last row action={row.get('action')} — not a landing; exit")
            return 1
        if row.get("sent") is not True:
            # Fighting machinery not via flag (e.g. plain create) — treat as
            # still in flight only if it was ever seen; otherwise dead.
            if flag_seen:
                time.sleep(POLL_S)
                continue
            print(f"relay: prior {prior} unsent row and no flag — exit")
            return 1

        # Real landing: lesson-106 phantom check (chats list is the truth).
        exists = chat_exists_server_side(row.get("url") or "")
        if exists is False:
            print(f"relay: prior {prior} sent=true but chat ABSENT from server list — phantom; exit")
            return 1
        if exists is None:
            print(f"relay: WARNING phantom check unavailable — arming anyway (fail-open)")
        print(f"relay: prior {prior} landed (sent=true, flag cleared) — settling {SETTLE_S}s")
        time.sleep(SETTLE_S)
        if os.path.exists(next_flag_path(next_name)):
            print(f"relay: next flag appeared during settle — exiting")
            return 0
        write_flag_atomic(
            next_flag_path(next_name),
            {"name": next_name, "prompt_file": prompt_file, "uuid": "", "tab_id": ""},
        )
        print(f"relay: ARMED {next_name} -> {next_flag_path(next_name)}")
        armed = True
        break

    if not armed:
        print("relay: timeout waiting for prior flag to clear")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
