#!/usr/bin/env python3
"""triage_zombies.py — fresh-tab truth read for tab-lost sessions (lesson 54 +
lesson 3833: the fresh-tab DOM render is the only truth; the server tree never
carries assistant content).

For each name:url pair: open a fresh tab, wait for the SPA history render
(innerText stabilizes), then report body length, marker hits, wait-state
markers, and the tail of the transcript. Leaves the tab OPEN (the caller
decides: harvest / revive / void) and prints its tab id.
"""
import json
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import channel

SESSIONS = {
    "r37": "https://chat.z.ai/c/f149e0b2-9de1-4b11-814c-434b254932d1",
    "r38a": "https://chat.z.ai/c/6a38925d-17e0-4b3a-9246-611b03f0cc52",
    "r38b": "https://chat.z.ai/c/edc09b79-dbed-4f17-8a02-5b2d44568a42",
}

MARKERS = ("COMPLETION REPORT", "Base SHA", "R37", "R38A", "R38B")
WAIT_MARKERS = ("at capacity", "peak hours", "personal limit",
                "try again 1 hour later", "Limit Sandbox Concurrency")


def snapshot(c):
    return c.eval("document.body ? document.body.innerText.length : -1", timeout=15)


def main():
    names = sys.argv[1:] or list(SESSIONS)
    results = {}
    for name in names:
        url = SESSIONS[name]
        print(f"[{name}] opening fresh tab -> {url}", flush=True)
        tab = channel.new_tab(url)
        if not tab:
            print(f"[{name}] FAILED to open tab", flush=True)
            results[name] = {"ok": False}
            continue
        tid = tab["id"]
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
            # wait for SPA render: innerText stable across ~4s and > 3K chars
            prev, stable_since, t0 = -1, None, time.time()
            while time.time() - t0 < 45:
                cur = snapshot(c)
                if cur == prev and cur > 3000:
                    if stable_since is None:
                        stable_since = time.time()
                    elif time.time() - stable_since > 4:
                        break
                else:
                    stable_since = None
                prev = cur
                time.sleep(2)
            body = c.eval("document.body.innerText", timeout=30) or ""
            title = c.eval("document.title", timeout=10) or ""
            href = c.eval("location.href", timeout=10) or ""
            hits = {m: body.count(m) for m in MARKERS if body.count(m)}
            waits = [m for m in WAIT_MARKERS if m in body]
            busy = c.eval(r"""(() => {
              const btns = Array.from(document.querySelectorAll('button'))
                .map(b => (b.innerText||'').trim());
              return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 'busy' : 'idle';
            })()""", timeout=15)
            tail = body[-600:]
            print(f"[{name}] tab={tid[:8]} href={href[:70]}")
            print(f"[{name}] title={title[:50]!r} len={len(body)} busy={busy} "
                  f"hits={hits} waits={waits}", flush=True)
            print(f"[{name}] TAIL>>>\n{tail}\n<<<", flush=True)
            results[name] = {"ok": True, "tab": tid, "len": len(body),
                             "hits": hits, "waits": waits, "busy": busy,
                             "href": href, "title": title}
            try:
                c.close()
            except Exception:
                pass
        except Exception as e:
            print(f"[{name}] tab={tid[:8]} EVAL-ERROR {type(e).__name__}: {e}",
                  flush=True)
            results[name] = {"ok": False, "tab": tid, "err": str(e)}
    print("RESULT_JSON " + json.dumps(results))


if __name__ == "__main__":
    main()
