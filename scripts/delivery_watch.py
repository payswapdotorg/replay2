#!/usr/bin/env python3
"""delivery_watch.py <name> <tab_prefix> <session_url> <msg_file> <marker>

SAFE delivery-only watcher for a session whose WORK IS ALREADY DONE but whose
turn queue is blocked by GLM-5.3 capacity peaks. NEVER voids or re-creates
the session (the sandbox holds the deliverable commit); instead:

  - if the tab drifts (about:blank hop seen live on 2026-09-10): re-navigate
    the SAME tab back to the session URL;
  - if a capacity dialog is up: Cancel it (operator: "press cancel and
    retry");
  - if the composer holds the staged message: press Enter (one retry per
    cycle, 90s cadence — a grind would re-arm the personal usage limit);
  - if the composer is empty and the body is growing: generating — wait;
  - when the marker text appears >= 2 times in the body (1 = prompt echo,
    2 = the worker's reply): write flags/<name>-deliver.marker and exit.

Marker file: flags/<name>-deliver.marker (distinct from the completion
marker — this is the DELIVERY phase).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "delivery-watch.log")

CAPACITY_TEXTS = ("currently at capacity", "peak hours", "try again later or switch")
GEN_RE = re.compile(r"^(Stop|Pause|Halt)$", re.I)


def log(name, *args):
    line = f"[{name}] {time.strftime('%H:%M:%S')} " + " ".join(str(a) for a in args)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def heartbeat(name):
    try:
        with open(os.path.join(FLAGS, f"delivery_watch_heartbeat.{name}"), "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def get_tab(prefix):
    for t in channel.list_tabs():
        if t["id"].startswith(prefix):
            return t
    return None


def eval_(c, expr, timeout=15):
    return c.eval(expr, timeout=timeout)


def dismiss_dialogs(c):
    """Cancel any [role=dialog] that has a Cancel button; return count."""
    try:
        res = eval_(c, r"""(() => {
          let n = 0;
          for (const d of document.querySelectorAll('[role=dialog]')) {
            const btns = Array.from(d.querySelectorAll('button'))
              .filter(b => /^(Cancel|取消|Close|关闭)$/i.test((b.innerText||'').trim()));
            if (btns.length) { btns[0].click(); n++; }
          }
          return n;
        })()""")
        if str(res) != "0":
            time.sleep(1.5)
        return int(res or 0)
    except Exception:
        return 0


def press_enter(c):
    for typ in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {
            "type": typ, "key": "Enter", "code": "Enter",
            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=10)


def stage_message(c, msg):
    """Ensure the composer holds exactly msg (clear + insert with bounds)."""
    for _ in range(3):
        try:
            cur = eval_(c, '(() => { const i = document.querySelector("#chat-input, textarea"); return i ? String((i.value||"").length) : "gone"; })()')
            if cur == str(len(msg)):
                return True
            # clear (React-safe): select all + Delete via Input domain
            eval_(c, '(() => { const i = document.querySelector("#chat-input, textarea"); i.focus(); i.select(); return "ok"; })()')
            time.sleep(0.2)
            for typ in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {
                    "type": typ, "key": "Delete", "code": "Delete",
                    "windowsVirtualKeyCode": 46, "nativeVirtualKeyCode": 46}, timeout=10)
            time.sleep(0.5)
            cur = eval_(c, '(() => { const i = document.querySelector("#chat-input, textarea"); return i ? String((i.value||"").length) : "gone"; })()')
            if cur != "0":
                continue
            c.call("Input.insertText", {"text": msg}, timeout=15)
            time.sleep(1.0)
        except Exception:
            time.sleep(1)
    try:
        cur = eval_(c, '(() => { const i = document.querySelector("#chat-input, textarea"); return i ? String((i.value||"").length) : "gone"; })()')
        return cur == str(len(msg))
    except Exception:
        return False


def main():
    name, tab_prefix, session_url, msg_file, marker = sys.argv[1:6]
    msg = open(msg_file, encoding="utf-8").read().strip() + "\n"
    marker_path = os.path.join(FLAGS, f"{name}-deliver.marker")
    log(name, f"delivery watch started tab={tab_prefix} marker={marker!r} msg={len(msg)} chars")
    while True:
        heartbeat(name)
        try:
            tab = get_tab(tab_prefix)
            if not tab:
                log(name, "tab gone — waiting (NEVER re-dispatch: sandbox holds the commit)")
                time.sleep(90)
                continue
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
            try:
                url = eval_(c, "location.href", timeout=10)
                if session_url.rstrip("/") not in url.rstrip("/"):
                    log(name, f"tab drifted ({url[:50]}) — re-navigating to session")
                    c.call("Page.navigate", {"url": session_url}, timeout=30)
                    time.sleep(15)
                    continue
                body = eval_(c, "(document.body.innerText||'')", timeout=25) or ""
                hits = body.count(marker)
                if hits >= 2:
                    open(marker_path, "w").write(f"{time.time()} {url}\n")
                    log(name, f"DELIVERED — marker written ({hits} hits)")
                    return 0
                # RATE-LIMIT GUARD (AG-16 lesson): grinding sends during an
                # explicit account cooldown re-arms the personal usage limit.
                # Stop sending for a full hour; just heartbeat + watch.
                if "exceeds the personal limit" in body or "try again 1 hour later" in body:
                    log(name, "rate-limited (account cooldown) — standing down for 3600s")
                    time.sleep(3600)
                    continue
                # generating?
                gen = eval_(c, """(() => {
                  const btns = Array.from(document.querySelectorAll('button'))
                    .map(b => (b.innerText||'').trim());
                  return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 'busy' : 'idle';
                })()""")
                if gen == "busy":
                    log(name, f"generating (chars={len(body)} hits={hits}) — waiting")
                    time.sleep(90)
                    continue
                # capacity error in the last assistant message?
                last_msg = eval_(c, """(() => {
                  const cs = [...document.querySelectorAll('[class*=chat-assistant]')];
                  return cs.length ? (cs[cs.length-1].innerText||'').slice(0, 200) : '';
                })()""")
                capacity = any(t in body[-2500:] for t in CAPACITY_TEXTS) or any(t in last_msg for t in CAPACITY_TEXTS)
                n_dlg = dismiss_dialogs(c)
                if n_dlg:
                    log(name, f"dismissed {n_dlg} dialog(s)")
                if capacity or n_dlg:
                    ok = stage_message(c, msg)
                    if ok:
                        press_enter(c)
                        log(name, "capacity blocked — re-staged + Enter (bounded 90s cadence)")
                    else:
                        log(name, "could not stage message cleanly — retry next cycle")
                else:
                    # no capacity sign: if the composer still holds the text,
                    # one Enter attempt; if empty, the turn may have been
                    # accepted — wait for the reply.
                    comp = eval_(c, '(() => { const i = document.querySelector("#chat-input, textarea"); return i ? String((i.value||"").length) : "gone"; })()')
                    if comp == str(len(msg)):
                        press_enter(c)
                        log(name, f"composer staged (len={comp}) — Enter sent; chars={len(body)}")
                    else:
                        log(name, f"waiting (chars={len(body)} hits={hits} composer={comp})")
            finally:
                c.close()
        except Exception as e:
            log(name, f"loop-error {type(e).__name__}: {str(e)[:80]} — continuing")
        time.sleep(90)


if __name__ == "__main__":
    sys.exit(main())
