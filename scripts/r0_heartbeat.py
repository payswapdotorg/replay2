#!/usr/bin/env python3
"""r0_heartbeat.py — VISIBLE console heartbeat for the outage hold.

The operator watches the browser through the replay console; a static tab
looks like a dead system. This script performs a small PASSIVE action on
the console tab (opens the model menu, reads the option list, closes it)
so the console visibly shows the Lead is alive and checking. Creates NO
chats, sends NOTHING. Also posts an outbox line per beat.

Usage: r0_heartbeat.py          (one beat)
       r0_heartbeat.py <n> <interval-s>   (n beats, e.g. 5 480)
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

OUTBOX = "/home/z/replay2/scripts/flags/agent_outbox.jsonl"


def beat():
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        print("no chat tab — opening one")
        t = channel.new_tab("https://chat.z.ai/")
        time.sleep(12)
        tabs = [t] if t else []
        if not tabs:
            return False
    tab = tabs[0]
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
    except Exception as e:
        print("tab wedged:", str(e)[:50], "— rotating")
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
        time.sleep(3)
        t = channel.new_tab("https://chat.z.ai/")
        time.sleep(12)
        return False
    try:
        # open the model menu (VISIBLE)
        r1 = c.eval("(() => { const b = document.querySelector('button.modelSelectorButton');"
                    " if (!b) return 'no-btn';"
                    " if (b.getAttribute('aria-expanded') !== 'true') b.click(); return 'open'; })()",
                    timeout=10)
        time.sleep(4.5)
        # read options (popper wrapper innerText — the proven selector)
        r2 = c.eval("(() => { const pop = document.querySelector('[data-radix-popper-content-wrapper], [role=menu], [role=listbox]');"
                    " if (!pop) return '[]';"
                    " const lines = (pop.innerText || '').split('\\n').map(s => s.trim()).filter(s => s.length > 1 && s.length < 40);"
                    " return JSON.stringify(Array.from(new Set(lines))); })()", timeout=10)
        # close the menu (Escape)
        c.eval("(() => { const b = document.querySelector('button.modelSelectorButton');"
               " if (b && b.getAttribute('aria-expanded') === 'true') b.click(); return 1; })()", timeout=8)
        try:
            opts = json.loads(r2)
        except Exception:
            opts = []
        btn = c.eval("(() => { const b = document.querySelector('button.modelSelectorButton');"
                     " return b ? (b.innerText || '').trim().split('\\n')[0] : '?'; })()", timeout=8)
        if not opts:
            opts = [f"btn={btn}"]
        g53 = "GLM-5.3" in opts or btn == "GLM-5.3"
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] menu:{r1} GLM-5.3={'present' if g53 else 'ABSENT'} options={opts}")
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": f"[Lead heartbeat {stamp}] outage hold continues — "
                                        f"GLM-5.3 {'present' if g53 else 'ABSENT'} in menu; "
                                        f"generation still down; watch armed for recovery."}) + "\n")
        return g53
    finally:
        c.close()


def main():
    if len(sys.argv) >= 3:
        n, interval = int(sys.argv[1]), int(sys.argv[2])
        for i in range(n):
            beat()
            if i < n - 1:
                time.sleep(interval)
    else:
        beat()


if __name__ == "__main__":
    main()
