#!/usr/bin/env python3
"""queue_watch.py <name> <tab-prefix> <marker> — resident watch for a queued/running worker session.

State machine (two-state capacity protocol + operator assault policy):
- ACCEPTED (URL /c/<id>, prompt in transcript) + capacity popup: NEVER touch
  the dialog — the task is queued server-side; the popup is cosmetic.
- Tab LOST or URL rolled home (the site destroys queued sessions during
  peaks): re-dispatch via dispatch_worker.create (full assault loop).
- Generating: watch for completion (marker count >= 2: prompt echo + answer).
- Complete: write flags/<name>-complete.marker and exit 0.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/my-project/scripts")
import channel
import dispatch_worker as dw

BASE = "/home/z/my-project/scripts"
FLAGS = os.path.join(BASE, "flags")


def state(tab_prefix):
    try:
        tab = None
        for t in channel.list_tabs():
            if t["id"].startswith(tab_prefix):
                tab = t
                break
        if not tab:
            return "tablost", 0, 0, ""
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            url = dw._eval(c, "location.href", timeout=15)
            body = dw._eval(c, "document.body.innerText || ''", timeout=25) or ""
            c.close()
        except Exception as e:
            return f"busy:{type(e).__name__}", 0, 0, ""
    except Exception as e:
        return f"busy:{type(e).__name__}", 0, 0, ""
    hits = body.count(sys.argv[3]) if len(sys.argv) > 3 else 0
    gen = bool(re.search(r"\b(Stop|Pause|Halt)\b", body[-1500:]))
    cap = "currently at capacity" in body or "peak hours" in body
    if "/c/" not in url:
        return "home", len(body), hits, url
    if gen:
        return "generating", len(body), hits, url
    return ("queued-capacity" if cap else "queued"), len(body), hits, url


def main():
    name, tab_prefix = sys.argv[1], sys.argv[2]
    marker = sys.argv[3] if len(sys.argv) > 3 else "COMPLETION REPORT"
    # supervisor contract: while this spec exists, the supervisor resurrects
    # this watcher; we remove it when the session completes
    spec = os.path.join(FLAGS, "queue_watch.spec")
    open(spec, "w").write(json.dumps({"name": name, "tab_prefix": tab_prefix,
                                      "marker": marker, "pid": os.getpid()}) + "\n")
    rounds_since_progress = 0
    last_len = 0
    while True:
        try:
            st, ln, hits, url = state(tab_prefix)
            stamp = time.strftime("%H:%M:%S")
            print(f"{stamp} {st} chars={ln} hits={hits} url={url[:60]}", flush=True)
            mk = os.path.join(FLAGS, f"{name}-complete.marker")
            if hits >= 2:
                open(mk, "w").write(f"{time.time()} {url}\n")
                print("COMPLETE — marker written", flush=True)
                try:
                    os.remove(spec)
                except Exception:
                    pass
                return 0
            if st == "tablost" or st == "home":
                print(f"{stamp} session destroyed ({st}) — re-dispatching (assault)", flush=True)
                subprocess.call([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "create", name,
                                 os.path.join(BASE, "worker-prompts", f"{name.replace('wo-', 'WO-')}.md")])
                # refresh tab prefix from the registry's latest record
                rec = dw._find(name)
                if rec:
                    tab_prefix = (rec.get("tab_id") or "")[:8]
                    print(f"{stamp} new session tab={tab_prefix}", flush=True)
            # progress bookkeeping
            if ln != last_len:
                rounds_since_progress = 0
                last_len = ln
            else:
                rounds_since_progress += 1
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} loop-error {type(e).__name__} — continuing", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    sys.exit(main())
