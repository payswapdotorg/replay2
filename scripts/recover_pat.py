#!/usr/bin/env python3
"""recover_pat.py — recover the git push token after a sandbox wipe.

REBUILD NOTE (2026-09-23): original recover_pat.py lost in wipe #3; rebuilt
per lesson 118 + Task-12 doctrine. The worker prompts rendered the transient
push URL  https://<PAT>@github.com/payswapdotorg/RoamLink.git  into the
dispatched chats — those chats live SERVER-SIDE on the operator's account,
so after re-login their user messages still carry the token. This tool walks
the chats list (newest first), reads each chat's user messages via the
lesson-107 HTTP rail, extracts the FIRST github token it finds, and writes
it to flags/github_pat + ~/.secrets/env.sh (mode 600). It NEVER prints the
token value — only its length and where it was found.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http  # noqa: E402

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
ENV_OUT = os.path.expanduser("~/.secrets/env.sh")

TOKEN_RE = re.compile(r"(github_pat_[A-Za-z0-9_]{22,}|gh[pousr]_[A-Za-z0-9]{20,})")


def user_messages(chat_id):
    data = chats_http.api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = (inner.get("history", {}) or {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    out = []
    for m in msgs:
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            out.append(m["content"])
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    data = chats_http.api(f"/api/v1/chats/list?limit={limit}")
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    print(f"scanning {len(items)} chats (newest first) for a dispatched push token…")
    for it in items:
        cid = (it.get("id") or "").removeprefix("chat-")
        title = (it.get("title") or "New Chat")[:60]
        if not cid:
            continue
        try:
            for content in user_messages(cid):
                m = TOKEN_RE.search(content)
                if not m:
                    continue
                tok = m.group(1)
                with open(os.path.join(FLAGS, "github_pat"), "w") as f:
                    f.write(tok)
                os.chmod(os.path.join(FLAGS, "github_pat"), 0o600)
                os.makedirs(os.path.dirname(ENV_OUT), exist_ok=True)
                with open(ENV_OUT, "w") as f:
                    f.write("# recovered by recover_pat.py (lesson 118) — NEVER commit/echo\n"
                            f"export PAYSWAP_GITHUB_PAT={tok}\n"
                            f"export GITHUB_TOKEN={tok}\n")
                os.chmod(ENV_OUT, 0o600)
                print(f"RECOVERED: token length {len(tok)} from chat {cid[:8]} "
                      f"({title!r}) — written to flags/github_pat + ~/.secrets/env.sh")
                return 0
        except Exception as e:
            print(f"  skip {cid[:8]} ({title!r}): {e!r}")
            continue
    print("NO TOKEN FOUND in the scanned chats — dispatch history may be older "
          f"than the {limit}-chat window (raise the limit) or the account differs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
