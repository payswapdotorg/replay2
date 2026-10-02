#!/usr/bin/env python3
"""rearm_lanes.py — re-arm parked experiment lanes + remote watch after a reset.

The sandbox wipes /home/z/replay2 (clones, prompts, flags, daemons) and /tmp
every few hours while /home/z/my-project survives. reset-restore.sh rebuilds
the STACK (console/browser/replayd/supervisor); this script rebuilds the
LANES from the reset-surviving lane registry at
/home/z/my-project/replay-lanes.json:

  for each lane (prompt == "chat"):
    - recover the dispatch packet from the chat's server-side history tree
      (the prompt lives server-side; nothing local is authoritative)
    - write scripts/prompts/<name>.md
    - idempotently register the lane + launch parked_watch (the committed
      resident watcher: spawn handoff / completion oracle / morning law)
  if remote_watch configured:
    - launch remote_watch.py (read-only origin observer, also committed)

Usage:  python3 scripts/rearm_lanes.py [--lanes /home/z/my-project/replay-lanes.json]
Exit 0 on success. Idempotent: a lane whose parked_watch spec already exists
is skipped (fresh heartbeats win).
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

DEFAULT_LANES = "/home/z/my-project/replay-lanes.json"
PROMPTS = os.path.join(BASE, "prompts")
FLAGS = os.path.join(BASE, "flags")


def log(m):
    print(f"[rearm {time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {m}", flush=True)


def recover_prompt(chat_id):
    """Pull the last user message (the dispatch packet) from the chat's
    server-side history tree via an in-page fetch. Returns str or None."""
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        log("no chat.z.ai tab — cannot recover prompt server-side")
        return None
    ws = channel.CDP(tabs[-1]["webSocketDebuggerUrl"])
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
          const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
          const r = await fetch('/api/v1/chats/%s', {credentials: 'include', cache: 'no-store', headers: hdr});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const msgs = ((j.chat || {}).history || {}).messages || {};
          const byTs = Object.values(msgs).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
          const users = byTs.filter(m => m.role === 'user');
          const last = users[users.length - 1] || {};
          let content = '';
          if (Array.isArray(last.content)) content = last.content.map(p => (typeof p === 'string' ? p : (p.text || ''))).join('');
          else if (typeof last.content === 'string') content = last.content;
          return JSON.stringify({content});
        })()""" % chat_id
        r = ws.call("Runtime.evaluate", {"expression": js, "awaitPromise": True,
                                         "returnByValue": True}, timeout=45)
        v = json.loads(r.get("result", {}).get("value") or "{}")
        return v.get("content") or None
    except Exception as e:
        log(f"prompt recovery failed for {chat_id[:8]}: {e}")
        return None
    finally:
        try:
            ws.close()
        except Exception:
            pass


def watch_alive(name):
    """A parked_watch for this lane is already resident (fresh spec + fresh
    heartbeat) — idempotence guard."""
    spec = os.path.join(FLAGS, f"parked_watch.spec.{name}")
    hb = os.path.join(FLAGS, f"parked_watch_heartbeat.{name}")
    if not os.path.isfile(spec):
        return False
    try:
        if time.time() - int(open(hb).read().strip()) > 600:
            return False   # spec exists but the watcher is stale/dead
    except Exception:
        return False
    return True


def main():
    lanes_path = DEFAULT_LANES
    if "--lanes" in sys.argv:
        lanes_path = sys.argv[sys.argv.index("--lanes") + 1]
    cfg = json.load(open(lanes_path))
    os.makedirs(PROMPTS, exist_ok=True)
    os.makedirs(FLAGS, exist_ok=True)

    for lane in cfg.get("lanes", []):
        name = lane["name"]
        if watch_alive(name):
            log(f"lane {name}: parked_watch already resident — skip")
            continue
        chat_id = lane["chat_id"]
        marker = lane.get("marker", "COMPLETION REPORT")
        prompt_file = os.path.join(PROMPTS, f"{name}.md")
        if lane.get("prompt") == "chat":
            content = recover_prompt(chat_id)
            if not content:
                log(f"lane {name}: PROMPT RECOVERY FAILED — lane NOT armed")
                continue
            open(prompt_file, "w", encoding="utf-8").write(content)
            log(f"lane {name}: packet recovered ({len(content)} chars) -> {os.path.basename(prompt_file)}")
        elif not os.path.isfile(prompt_file):
            log(f"lane {name}: no local prompt file and prompt!='chat' — NOT armed")
            continue
        r = subprocess.run([sys.executable, os.path.join(BASE, "launch_parked_watch.py"),
                            name, chat_id, marker, prompt_file],
                           capture_output=True, text=True, timeout=120)
        log(f"lane {name}: " + ((r.stdout or "").strip().split("\n")[-1] or "launch silent"))

    rw = cfg.get("remote_watch") or {}
    if rw.get("repo"):
        env = dict(os.environ)
        if not env.get("RW_PAT") and os.path.isfile("/home/z/.payswap-env"):
            try:
                env["RW_PAT"] = open("/home/z/.payswap-env").read().split("GITHUB_PAT=")[1].split()[0].strip()
            except Exception:
                pass
        if subprocess.run(["pgrep", "-f", "remote_watch.py"], capture_output=True).returncode != 0:
            p = subprocess.Popen([sys.executable, os.path.join(BASE, "remote_watch.py"), "--repo", rw["repo"]],
                                 stdout=open("/tmp/remote_watch.log", "w"),
                                 stderr=subprocess.STDOUT, start_new_session=True,
                                 cwd=BASE, env=env)
            log(f"remote_watch detached pid {p.pid} (repo {rw['repo']})")
        else:
            log("remote_watch already resident — skip")
    log("REARM COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
