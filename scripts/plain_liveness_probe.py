#!/usr/bin/env python3
"""plain_liveness_probe.py — platform generation liveness differential probe.

2026-09-21 context: platform-wide generation stall since ~15:35 UTC (both
GLM-5.2 plain canary and GLM-5.3 staged workers show zero batch messages;
chats materialize, pods ran, then load-shedding released every pod and
reaped one staged chat). The waveC stall watch depends on the ORIGINAL
canary replying — but if that canary's queued generation task was silently
reaped (the prod012r fate), the watch waits forever.

This probe measures the CURRENT truth with one cheap plain-mode send:

  1. snapshot the chats list (server-side, Bearer HTTPS)
  2. open a FRESH tab on https://chat.z.ai/ (plain surface, default model —
     never touches agent mode; a fresh tab cannot inherit sticky agent
     state, the Task-90 lesson)
  3. verify surface state (agent mode OFF, record the default model)
  4. send a short unique marker text via the SUBMIT_JS path
  5. poll the chats list for a NEW chat (materialization)
  6. if materialized, poll batch messages for an assistant reply

Verdict:
  materialized + replied   -> generation is LIVE (stall over; act on workers)
  materialized + silent    -> stall CONTINUES (the probe chat is a fresh
                              canary; safe to leave for the stall watch)
  not materialized         -> send-path/gate family (different diagnosis)

Passive: one tiny chat is the entire footprint. Never re-sends.

Usage: plain_liveness_probe.py [--wait 180] [--keep-tab]
Prints one JSON verdict line.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as DW  # noqa: E402
from batch_probe import call, get_token  # noqa: E402

EVAL_T = 30


def ev(c, js, timeout=EVAL_T):
    return DW._eval(c, js, timeout=timeout)


def chats_snapshot():
    """Return dict chat-id -> updatedAt from the chats list (server-side)."""
    data = call("/api/v1/chats/list?limit=100")
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    return {it.get("id"): it.get("updatedAt") for it in items if it.get("id")}


def main() -> int:
    wait = 180
    keep_tab = False
    args = sys.argv[1:]
    if "--wait" in args:
        wait = int(args[args.index("--wait") + 1])
    keep_tab = "--keep-tab" in args

    marker = "LIVENESS-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    text = f"{marker}: platform liveness probe. Reply with the single word OK."

    # 1. before-snapshot
    try:
        before = chats_snapshot()
    except Exception as e:
        print(json.dumps({"err": f"chats list failed: {e!r}"}))
        return 3
    print(f"[probe] chats before: {len(before)}", flush=True)

    # 2. fresh home tab
    tab = channel.new_tab("https://chat.z.ai/")
    if not tab:
        print(json.dumps({"err": "new_tab failed"}))
        return 3
    time.sleep(12)  # hydration allowance (~290-chat sidebar)
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    except Exception as e:
        print(json.dumps({"err": f"ws fail: {e!r}"}))
        return 3

    # 3. surface state
    agent_on = "?"
    model = "?"
    try:
        agent_on = str(ev(c, DW.JS_AGENT_MODE_ON))
        model = str(ev(c, DW.JS_MODEL_TEXT))
    except Exception as e:
        print(f"[probe] state eval failed: {e!r}", flush=True)
    print(f"[probe] agent_mode_on={agent_on} model={model}", flush=True)

    out = {
        "marker": marker,
        "agent_mode_on": agent_on,
        "model": model,
        "materialized": False,
        "replied": False,
        "chat_id": None,
        "verdict": None,
    }

    if agent_on == "true":
        # sticky agent surface on a FRESH tab would send this as an agent
        # dispatch — refuse (wrong path, burns a worker slot)
        out["verdict"] = "refused-agent-surface"
        print(json.dumps(out))
        try:
            DW._close_tab(tab["id"])
        except Exception:
            pass
        return 2

    # 4. send
    res = channel.send_text(text, tab=tab)
    print(f"[probe] send: {json.dumps(res)}", flush=True)
    if not res.get("ok"):
        out["verdict"] = "send-failed"
        print(json.dumps(out))
        if not keep_tab:
            try:
                DW._close_tab(tab["id"])
            except Exception:
                pass
        return 2

    # 5. materialization poll (server-side)
    deadline = time.time() + 60
    new_id = None
    while time.time() < deadline:
        time.sleep(10)
        try:
            after = chats_snapshot()
        except Exception as e:
            print(f"[probe] list poll err: {e!r}", flush=True)
            continue
        fresh = [cid for cid in after if cid not in before]
        if fresh:
            new_id = fresh[0]
            break
    out["materialized"] = new_id is not None
    out["chat_id"] = new_id
    print(f"[probe] materialized={out['materialized']} chat={new_id}", flush=True)

    if not out["materialized"]:
        out["verdict"] = "not-materialized-send-gate"
        print(json.dumps(out))
        if not keep_tab:
            try:
                DW._close_tab(tab["id"])
            except Exception:
                pass
        return 2

    # 6. reply poll (batch store)
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(15)
        try:
            chat = call(f"/api/v1/chats/{new_id}")
        except Exception as e:
            print(f"[probe] chat poll err: {e!r}", flush=True)
            continue
        msgs = ((chat.get("chat") or chat).get("history") or {}).get("messages") or {}
        if isinstance(msgs, list):
            msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
        roles = [m.get("role") for m in msgs.values()]
        if "assistant" in roles:
            out["replied"] = True
            break
    out["verdict"] = "generation-live" if out["replied"] else "stall-continues"
    print(json.dumps(out))
    if not keep_tab:
        try:
            DW._close_tab(tab["id"])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
