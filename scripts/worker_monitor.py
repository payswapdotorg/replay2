#!/usr/bin/env python3
"""worker_monitor.py — detached monitor for the live worker pods.

Every POLL_S seconds, append one status line per watched chat to
logs/worker_monitor.log: timestamp, pod status (fresh-tab wedge-proof
POST), server-side chat updated_at age, and checkpoint-artifact flags
read from the pod's ls-tree (DEP-XXX-files.tgz present?).

Watched: the dep-011 + dep-014 chats (wave B redispatch).
"""
import json
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

POLL_S = 300
WATCH = {
    "2442b7bd-d8c7-43de-a593-141eca8c15c0": "dep-011",
    "687ad7c5-f2f8-4596-9a6b-0e316d8a7dba": "dep-014",
}
LOG = "/home/z/replay2/scripts/logs/worker_monitor.log"


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


def log(line):
    with open(LOG, "a") as f:
        f.write(time.strftime("[%H:%M:%S] ") + line + "\n")


def probe():
    js_list = """(async () => {
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/web-dev/workspaces/user-fc', { credentials: 'include', headers: { 'Authorization': 'Bearer ' + t } });
      const j = await r.json();
      const items = j.workspaces || (j.data && j.data.workspaces) || [];
      const out = {};
      for (const w of items) {
        const cid = (w.chat_id || '').replace('chat-', '');
        for (const [want, name] of Object.entries(%s)) {
          if (cid.startsWith(want.slice(0, 8))) {
            const s = await fetch('/api/v1/web-dev/workspaces/status', { method: 'POST', credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ chat_id: cid }) });
            let sj = null; try { sj = await s.json(); } catch (e) {}
            const tree = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', { method: 'POST', credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ chatId: cid, workspace_id: w.function_name }) });
            const tj = await tree.json();
            const files = Array.isArray(tj) ? tj : (tj.data || []);
            const tgz = files.filter(p => typeof p === 'string' && /files\\.tgz$/.test(p));
            const wl = files.filter(p => typeof p === 'string' && p === 'worklog.md' || /worklog/.test(String(p))).length;
            out[name] = {
              pod: (sj && sj.pod) ? sj.pod.status : 'http' + s.status,
              ws: w.function_name,
              tgz: tgz,
              files: files.length,
            };
          }
        }
      }
      return JSON.stringify(out);
    })()""" % json.dumps(WATCH)
    try:
        raw = fresh_eval(js_list, timeout=90)
        return json.loads(raw)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    log(f"monitor start: watching {list(WATCH.values())}")
    while True:
        try:
            state = probe()
            if "error" in state:
                log(f"probe error: {state['error']}")
            else:
                for name, s in state.items():
                    if isinstance(s, dict):
                        log(f"{name}: pod={s.get('pod')} files={s.get('files')} tgz={s.get('tgz')}")
                    else:
                        log(f"{name}: {s}")
        except Exception as e:
            log(f"outer error: {type(e).__name__}: {e}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
