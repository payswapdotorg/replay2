#!/usr/bin/env python3
"""composio_mcp.py — thin Composio MCP client (Lead-side tooling).

The Composio v1 REST API is 410-Gone; the current surface is the hosted MCP
server at https://connect.composio.dev/mcp (Authorization: Bearer <MCP key>,
streamable-HTTP transport, SSE responses).

Usage:
  python3 scripts/composio_mcp.py list-tools
  python3 scripts/composio_mcp.py call COMPOSIO_MANAGE_CONNECTIONS '{"action":"list","toolkits":["github"]}'
  python3 scripts/composio_mcp.py raw '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

Auth: COMPOSIO_MCP_API_KEY from environment (auto-sourced from
/home/z/.secrets/env.sh per ~/.bashrc hook; this script also tries that file
so cron-style/detached callers work without a login shell).
"""
import json
import os
import re
import sys
import urllib.request

BASE_URL = "https://connect.composio.dev/mcp"
ENV_FILE = "/home/z/.secrets/env.sh"


def load_key() -> str:
    key = os.environ.get("COMPOSIO_MCP_API_KEY", "")
    if key:
        return key
    try:
        with open(ENV_FILE) as f:
            m = re.search(r'export COMPOSIO_MCP_API_KEY=([^\s]+)', f.read())
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    raise SystemExit("COMPOSIO_MCP_API_KEY not found (env or %s)" % ENV_FILE)


KEY = load_key()


def post(payload: dict, session_id: str | None = None) -> dict | None:
    """POST one JSON-RPC message; return parsed `data:` JSON (or None)."""
    req = urllib.request.Request(BASE_URL, method="POST")
    req.add_header("Authorization", "Bearer %s" % KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    if session_id:
        req.add_header("Mcp-Session-Id", session_id)
    body = json.dumps(payload).encode()
    req.data = body
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8", "replace")
        sid = resp.headers.get("mcp-session-id")
        if sid:
            os.environ["_MCP_SESSION_ID"] = sid
    for line in raw.splitlines():
        if line.startswith("data:"):
            chunk = line[len("data:"):].strip()
            if chunk:
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue
    return None


def open_session() -> str:
    result = post({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "aise-lead", "version": "1.0"},
        },
    })
    if result is None:
        raise SystemExit("initialize failed (no data)")
    post({"jsonrpc": "2.0", "method": "notifications/initialized"},
         session_id=os.environ.get("_MCP_SESSION_ID"))
    return os.environ["_MCP_SESSION_ID"]


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    sid = open_session()
    if args[0] == "list-tools":
        out = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, session_id=sid)
        for t in out.get("result", {}).get("tools", []):
            print("-", t["name"], "::", t.get("title", ""))
    elif args[0] == "call" and len(args) >= 3:
        out = post({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": args[1], "arguments": json.loads(args[2])},
        }, session_id=sid)
        for c in out.get("result", {}).get("content", []):
            if c.get("type") == "text":
                print(c["text"])
    elif args[0] == "raw" and len(args) >= 2:
        out = post(json.loads(args[1]), session_id=sid)
        print(json.dumps(out, indent=2)[:8000])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
