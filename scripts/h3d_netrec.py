#!/usr/bin/env python3
"""h3d_netrec.py — CDP network recorder for the hyper3d.ai tab.

Records request/response pairs (incl. POST bodies + JSON response bodies)
to /home/z/h3d-capture/network.jsonl while the lead drives the site.
Re-attaches when the tab navigates or the renderer swaps. Survives as a
dfork daemon.
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402
import websocket  # noqa: E402

OUT = "/home/z/h3d-capture/network.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

MATCH = "hyper3d"
_last_seen = {}


def log(*a):
    with open("/home/z/h3d-capture/netrec.log", "a") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def find_tab():
    for t in channel.list_tabs():
        if MATCH in (t.get("url") or ""):
            return t
    return None


class Rec:
    def __init__(self, tab):
        self.tab = tab
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=5)
        self.mid = 0
        self.pending = {}  # loaderId/requestId -> meta

    def send(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method,
                                 "params": params or {}}))
        return self.mid

    def pump(self, fh, deadline):
        self.ws.settimeout(max(0.1, deadline - time.time()))
        try:
            raw = self.ws.recv()
        except websocket.WebSocketTimeoutException:
            return True
        except Exception as e:
            log("recv-err", repr(e))
            return False
        try:
            ev = json.loads(raw)
        except Exception:
            return True
        if "id" in ev:  # command reply
            self.pending_reply(ev)
            return True
        m = ev.get("method", "")
        p = ev.get("params", {})
        if m == "Network.requestWillBeSent":
            r = p.get("request", {})
            rec = {
                "t": round(time.time(), 3),
                "kind": "request",
                "reqId": p.get("requestId"),
                "url": r.get("url"),
                "method": r.get("method"),
                "rtype": p.get("type"),
                "postData": (r.get("postData") or "")[:4000],
                "headers": {k: v for k, v in (r.get("headers") or {}).items()
                            if k.lower() in ("authorization", "content-type", "accept")},
            }
            fh.write(json.dumps(rec) + "\n")
        elif m == "Network.responseReceived":
            r = p.get("response", {})
            rec = {
                "t": round(time.time(), 3),
                "kind": "response",
                "reqId": p.get("requestId"),
                "url": r.get("url"),
                "status": r.get("status"),
                "mimeType": r.get("mimeType"),
                "headers": {k: v for k, v in (r.get("headers") or {}).items()
                            if k.lower() in ("content-type", "content-length")},
            }
            fh.write(json.dumps(rec) + "\n")
            _last_seen[p.get("requestId")] = r.get("url")
        elif m == "Network.loadingFinished":
            rid = p.get("requestId")
            url = _last_seen.get(rid, "")
            if not url:
                return True
            # fetch bodies only for API-ish/JSON responses, capped
            if any(s in url for s in ("/api/", "api.", "/v1/", "/v2/", "graphql")) or \
               "json" in str(ev.get("params", {})):
                try:
                    mid = self.send("Network.getResponseBody",
                                    {"requestId": rid})
                    self._body_want[mid] = rid
                except Exception:
                    pass
        return True

    _body_want = {}

    def pending_reply(self, ev):
        mid = ev.get("id")
        rid = self._body_want.pop(mid, None)
        if rid and ev.get("result", {}).get("base64Encoded") is False:
            body = ev["result"].get("body", "")
            url = _last_seen.get(rid, "")
            with open(OUT, "a") as fh:
                fh.write(json.dumps({
                    "t": round(time.time(), 3),
                    "kind": "body",
                    "reqId": rid,
                    "url": url,
                    "body": body[:60000],
                }) + "\n")


def main():
    log("netrec start")
    while True:
        tab = find_tab()
        if tab is None:
            time.sleep(3)
            continue
        try:
            rec = Rec(tab)
            rec.send("Network.enable")
            rec.send("Network.setCacheDisabled", {"cacheDisabled": True})
            log("attached", tab["id"][:8], tab.get("url"))
            with open(OUT, "a") as fh:
                while True:
                    if not rec.pump(fh, time.time() + 5):
                        break
                    # tab still on hyper3d?
                    cur = find_tab()
                    if cur is None:
                        break
        except Exception as e:
            log("attach-err", repr(e))
        try:
            rec.ws.close()
        except Exception:
            pass
        time.sleep(2)


if __name__ == "__main__":
    main()
