#!/usr/bin/env python3
"""agent_session_watch.py — read-only monitor for ONE dispatched agents-tab session.

Doctrine (boot prompt):
- lesson 121: dispatch decisions (send/void/recreate) belong to the resident TL.
  This watcher NEVER dispatches — it only logs snapshots and writes flags.
- lessons 176/178/181: the completion marker is checked ONLY inside the LAST
  .chat-assistant container tail (the prompt echo in the user message contains
  the marker text and must never fire completion). Sub-1KB DOM growth is a
  DEATH marker, not life (lesson 181) — the tail text is always logged.
- lessons 104/118/181: queued/static/streaming semantics; a wedged or closed
  tab escalates as tablost (TL re-opens at the same URL per section 3.8; a
  bounce-to-home is NOT death for a fresh chat — check the sidebar, lesson 185).

Flags written (TL acts on them, in order):
  flags/<name>.report   — completion marker seen in last assistant container
  flags/<name>.stall    — server-static or queue/pre-stream starve
  flags/<name>.tablost  — session tab gone or wedged (TL verdict required)

Usage: agent_session_watch.py <session-name> [marker-string]
"""
import json
import os
import sys
import time
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "clapp-040"
MARKER = sys.argv[2] if len(sys.argv) > 2 else "CLAPP-COMPLETION-REPORT CLAPP-040 END"
CYCLE_S = 150
STATIC_MIN = 6      # static snapshots (aLen frozen >0, no stream) -> stall flag
PRESTREAM_MAX = 16  # empty/absent assistant container, no stream -> stall flag

REG = os.path.join(BASE, "flags", "session_registry.jsonl")
LOG = os.path.join(BASE, "logs", "agent_watch_%s.log" % NAME)
F_DONE = os.path.join(BASE, "flags", "%s.report" % NAME)
F_STALL = os.path.join(BASE, "flags", "%s.stall" % NAME)
F_LOST = os.path.join(BASE, "flags", "%s.tablost" % NAME)
HB = os.path.join(BASE, "flags", "heartbeat")

SNAP_JS = r"""(() => {
  const els = document.querySelectorAll('.chat-assistant');
  const last = els.length ? els[els.length-1] : null;
  const aText = last ? (last.innerText || '') : '';
  const body = (document.body.innerText || '');
  let folded = false;
  if (last) {
    for (const el of last.querySelectorAll('div,span,button')) {
      const t = (el.textContent || '').trim();
      if (t === 'Show full message' || t === 'show more') { folded = true; break; }
    }
  }
  return JSON.stringify({
    url: location.href,
    n: els.length,
    aLen: aText.length,
    aTail: aText.slice(-500),
    domLen: body.length,
    stream: /Thinking|Generating|typing…/.test(body),
    folded: folded
  });
})()"""


def log(msg):
    with open(LOG, "a") as f:
        f.write("[%s] %s\n" % (datetime.datetime.now().strftime("%m-%d %H:%M:%S"), msg))


def latest_create():
    """Latest create record (sent:true / tab-reopen) not invalidated later."""
    rec = None
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                if s.get("name") != NAME:
                    continue
                if s.get("action") in ("void", "failed", "done") or s.get("state") in ("void", "dead", "done"):
                    rec = None
                elif s.get("sent") and s.get("url"):
                    rec = s
                elif s.get("action") == "tab-reopen" and s.get("url"):
                    rec = s
    except FileNotFoundError:
        pass
    return rec


def clear_flag(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def write_flag(path, payload):
    with open(path, "w") as f:
        json.dump(payload, f)


def main():
    log("agent_session_watch up: name=%s marker_tail='...%s' CYCLE_S=%d STATIC_MIN=%d PRESTREAM_MAX=%d" % (
        NAME, MARKER[-18:], CYCLE_S, STATIC_MIN, PRESTREAM_MAX))
    static_n = 0
    pre_n = 0
    lost_n = 0
    last_aLen = -1
    done_written = False
    while True:
        try:
            open(HB, "a").close()
        except OSError:
            pass
        s = latest_create()
        if not s:
            log("no live create record for %s — idle" % NAME)
            time.sleep(CYCLE_S)
            continue
        tab = None
        try:
            for t in channel.list_tabs():
                if t.get("id") == s.get("tab_id") or (
                        s.get("url") and s["url"].split("chat.z.ai")[-1][:30] in (t.get("url") or "")):
                    tab = t
                    break
        except Exception as e:
            log("list_tabs error: %s" % e)
        if not tab:
            lost_n += 1
            log("session tab LOST (%d) — was %s url=%s (TL: bounce-test + sidebar check per lesson 185 before voiding)"
                % (lost_n, (s.get("tab_id") or "")[:8], s.get("url")))
            if lost_n >= 2:
                write_flag(F_LOST, {"name": NAME, "url": s.get("url"),
                                    "ts": datetime.datetime.now().isoformat(),
                                    "note": "tab closed, navigation, or renderer purge needed"})
            time.sleep(CYCLE_S)
            continue
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            try:
                raw = c.eval(SNAP_JS, timeout=25)
            finally:
                try:
                    c.close()
                except Exception:
                    pass
            snap = json.loads(raw)
        except Exception as e:
            lost_n += 1
            log("tab %s unresponsive (%d): %s" % ((tab.get("id") or "")[:8], lost_n, e))
            if lost_n >= 4:
                write_flag(F_LOST, {"name": NAME, "url": s.get("url"),
                                    "ts": datetime.datetime.now().isoformat(),
                                    "note": "tab wedged (CDP eval timeouts)"})
            time.sleep(CYCLE_S)
            continue
        lost_n = 0
        aLen = snap.get("aLen", 0)
        n = snap.get("n", 0)
        domLen = snap.get("domLen", 0)
        stream = bool(snap.get("stream"))
        folded = bool(snap.get("folded"))
        url_now = snap.get("url") or ""
        aTail = snap.get("aTail") or ""
        tail_log = aTail.replace("\n", "\\n")[-120:]

        # completion — marker scoped to the LAST assistant container tail only
        if not done_written and MARKER in aTail:
            done_written = True
            write_flag(F_DONE, {"name": NAME, "chat_id": s.get("url", "").split("/c/")[-1],
                                "aLen": aLen, "domlen": domLen, "folded": folded,
                                "ts": datetime.datetime.now().isoformat(),
                                "tail": aTail[-300:]})
            log("REPORT MARKER (assistant-scoped, last container) aLen=%d folded=%s — flags/%s.report written; TL harvest per closure runbook"
                % (aLen, folded, NAME))
            time.sleep(CYCLE_S)
            continue

        if stream:
            log("STREAM aLen=%d n=%d domLen=%d folded=%s tail='%s'" % (aLen, n, domLen, folded, tail_log))
            static_n = 0
            pre_n = 0
            clear_flag(F_STALL)
        elif aLen > last_aLen and last_aLen >= 0:
            log("LIVE aLen=%d n=%d domLen=%d folded=%s tail='%s'" % (aLen, n, domLen, folded, tail_log))
            static_n = 0
            pre_n = 0
            clear_flag(F_STALL)
        elif last_aLen < 0:
            log("FIRST-SNAP aLen=%d n=%d domLen=%d stream=%s url=%s" % (aLen, n, domLen, stream, url_now))
        else:
            if aLen == 0:
                pre_n += 1
                log("QUEUED/PRE-STREAM (no assistant text) pre=%d/%d domLen=%d url=%s" % (
                    pre_n, PRESTREAM_MAX, domLen, url_now))
                if not done_written and pre_n >= PRESTREAM_MAX:
                    write_flag(F_STALL, {"kind": "queue-starve", "pre": pre_n, "domLen": domLen,
                                         "ts": datetime.datetime.now().isoformat()})
                    log("STALL FLAG (queue/pre-stream starve %d cycles)" % pre_n)
            else:
                static_n += 1
                log("STATIC aLen=%d static=%d/%d folded=%s tail='%s'"
                    % (aLen, static_n, STATIC_MIN, folded, tail_log))
                if not done_written and static_n >= STATIC_MIN:
                    write_flag(F_STALL, {"kind": "server-static", "static": static_n, "aLen": aLen,
                                         "folded": folded, "tail": aTail[-200:],
                                         "ts": datetime.datetime.now().isoformat()})
                    log("STALL FLAG (server-static %d cycles, aLen=%d, folded=%s)" % (static_n, aLen, folded))
        last_aLen = aLen
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    main()
