#!/usr/bin/env python3
"""dep_land.py — create-until-server-landed loop for peak-gated DEP dispatches.

The 2026-09-15 gate: a clean send renders /c/<uuid> locally, passes the 9s
landing check, registers — then the chat is DESTROYED server-side within ~60s
(phantom landing). Only chats present in /api/v1/chats/list are real. This
loop: one dispatch_worker create per round, then a server-list verification
after a settle window; the session is LANDED only when its chat id (read
from the LIVE TAB href, not the registry — the registry truncates the last
char under this gate) appears in the server list. Rounds continue until
landed or budget exhausted. Never waits passively (operator policy).

Usage: dep_land.py <name> <prompt-file> [settle-s=75] [max-rounds=12]
Exit 0 landed; 4 budget exhausted.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
DW = os.path.join(BASE, "dispatch_worker.py")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")


def _eval_js_fresh(js, timeout=55):
    """Run js on a FRESH chat.z.ai tab (wedge-proof API surface), then close it.

    Long-lived home tabs wedge under renderer thrash (2026-09-15 lesson:
    even `1+1` times out on them while fresh tabs eval fine). A fresh tab
    loads the SPA, evals the fetch with credentials, and gets closed."""
    t = channel.new_tab("https://chat.z.ai/")
    try:
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=25)
        for _ in range(20):
            try:
                href = c.eval("location.href", await_promise=False, timeout=8)
                if href and "chat.z.ai" in href and c.eval(
                        "document.readyState", await_promise=False, timeout=8) in ("interactive", "complete"):
                    break
            except Exception:
                pass
            time.sleep(1.5)
        return c.eval(js, await_promise=True, timeout=timeout)
    finally:
        try:
            channel.CDP(t["webSocketDebuggerUrl"], timeout=10).call(
                "Target.closeTarget", {"targetId": t.get("id")}, timeout=8)
        except Exception:
            pass


def server_chats():
    """Return {chat_id: title} from the server list (wedge-proof)."""
    js = """(async () => {
      for (let i = 0; i < 3; i++) {
        try {
          const r = await fetch('/api/v1/chats/list', {credentials:'include'});
          const arr = await r.json();
          return JSON.stringify(arr.map(x => ({id: x.id, title: x.title || ''})));
        } catch (e) { await new Promise(r => setTimeout(r, 2000)); }
      }
      return 'ERR';
    })()"""
    tabs = channel.list_tabs()
    home = next((t for t in tabs if (t.get("url") or "").rstrip("/").endswith("chat.z.ai")
                 and "/c/" not in (t.get("url") or "")), None)
    if home is not None:
        try:
            c = channel.CDP(home["webSocketDebuggerUrl"], timeout=20)
            try:
                raw = c.eval(js, await_promise=True, timeout=30)
            finally:
                c.close()
            if raw and raw != "ERR":
                out = {}
                for x in json.loads(raw):
                    out[x["id"]] = x["title"]
                return out
        except Exception:
            pass  # wedged home tab — fresh-tab fallback
    try:
        raw = _eval_js_fresh(js)
        if raw and raw != "ERR":
            out = {}
            for x in json.loads(raw):
                out[x["id"]] = x["title"]
            return out
    except Exception:
        pass
    return None


def live_tab_chat_id(name):
    """The chat id of name's currently-open tab (tab href = ground truth)."""
    tab_id = None
    try:
        for line in open(REG).read().split("\n"):
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("name") != name:
                continue
            if d.get("action") in ("void", "failed", "done"):
                tab_id = None
            elif d.get("tab_id"):
                tab_id = d["tab_id"]
    except Exception:
        pass
    if not tab_id:
        return None
    tabs = channel.list_tabs()
    for t in tabs:
        if (t.get("id") or "") == tab_id:
            u = t.get("url") or ""
            if "/c/" in u:
                return u.split("/c/")[1].split("?")[0].split("#")[0].strip()
    return None


def void_record(name, reason):
    subprocess.run([sys.executable, DW, "void", name, reason],
                   cwd=BASE, capture_output=True, text=True, timeout=120)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name, prompt = sys.argv[1], sys.argv[2]
    prompt = os.path.abspath(prompt)
    settle = int(sys.argv[3]) if len(sys.argv) > 3 else 75
    max_rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 12

    for rnd in range(1, max_rounds + 1):
        stamp = time.strftime("%H:%M:%S")
        srv = server_chats()
        cid = live_tab_chat_id(name)
        if srv and cid and cid in srv:
            print(f"[{name}] {stamp} LANDED round-verify: chat {cid[:8]} in server list — done", flush=True)
            return 0
        print(f"[{name}] {stamp} round {rnd}/{max_rounds}: create (current tab chat: {str(cid)[:10]})", flush=True)
        try:
            p = subprocess.run([sys.executable, DW, "create", name, prompt],
                               cwd=BASE, capture_output=True, text=True, timeout=900)
            out = (p.stdout or "") + (p.stderr or "")
            tail = [l for l in out.split("\n") if l.strip()][-1:] or ["rc=%s" % p.returncode]
            print(f"[{name}] {stamp} create rc={p.returncode}: {tail[0][:130]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"[{name}] {stamp} create timed out (900s) — void + next round", flush=True)
        time.sleep(settle)
        srv = server_chats()
        cid = live_tab_chat_id(name)
        if srv is None:
            print(f"[{name}] {stamp} server list unreadable — treat as not-landed", flush=True)
            continue
        if cid and cid in srv:
            print(f"[{name}] {stamp} LANDED: chat {cid[:8]} present in server list — done", flush=True)
            return 0
        reason = f"phantom landing (chat {str(cid)[:8]} absent from server list after {settle}s) — round {rnd}"
        print(f"[{name}] {stamp} {reason} — void + retry", flush=True)
        void_record(name, reason)
    print(f"[{name}] exhausted {max_rounds} rounds without server-side landing", flush=True)
    return 4


if __name__ == "__main__":
    sys.exit(main())
