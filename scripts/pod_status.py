#!/usr/bin/env python3
"""pod_status.py — wedge-proof workspace+pod status via a FRESH tab
(the dep_land._eval_js_fresh pattern). Uses the same endpoints as
check_workspaces.py: GET user-fc + POST status {chat_id}."""
import json
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel


def fresh_eval(js, timeout=55):
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


def main():
    js = """(async () => {
      const t = localStorage.getItem('token') || '';
      const H = { 'Authorization': 'Bearer ' + t };
      const out = { workspaces: [], status: {} };
      const r = await fetch('/api/v1/web-dev/workspaces/user-fc', { credentials: 'include', headers: H });
      const j = await r.json();
      const items = j.workspaces || (j.data && j.data.workspaces) || [];
      out.workspaces = items.map(w => ({ fn: w.function_name, chat: (w.chat_id||'').slice(5,13), active: w.is_active, created: (w.created_at||'').slice(0,19), title: (w.chat_title||'').slice(0,44) }));
      for (const w of items) {
        const s = await fetch('/api/v1/web-dev/workspaces/status', { method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: (w.chat_id||'').replace('chat-','') }) });
        let sj = null;
        try { sj = await s.json(); } catch (e) {}
        out.status[(w.chat_id||'').slice(5,13)] = (sj && sj.pod) ? sj.pod.status : ('http' + s.status);
      }
      return JSON.stringify(out);
    })()"""
    raw = fresh_eval(js, timeout=90)
    d = json.loads(raw)
    print("workspaces:")
    for w in d.get("workspaces", []):
        print(f"  {w['fn'][:20]} chat={w['chat']} active={w['active']} created={w['created']} | {w['title']}")
    print("pod status:")
    for k, v in d.get("status", {}).items():
        print(f"  chat {k}: {v}")


if __name__ == "__main__":
    main()
