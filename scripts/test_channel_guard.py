#!/usr/bin/env python3
"""test_channel_guard.py — offline unit test of the CDP dead-socket recv guard.

The 2026-10-03 replay-freeze postmortem: a wedged CDP websocket surfaces as
an EMPTY or non-JSON frame; the old call() fed that to json.loads, masked
the truth as JSONDecodeError, and kept using the corpse socket. The guard
must raise WebSocketConnectionClosedException on both shapes (the signal
every consumer drops the conn on), and stay transparent for the normal
event+response flow.

Offline: drives CDP.call() against a fake websocket (no Chrome, no CDP
port, no tabs) — same script-test pattern as test_drag.py, minus the E2E.
"""
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import channel  # noqa: E402


class _FakeWS:
    """Records sends; replays scripted recv frames."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []

    def settimeout(self, t):
        pass

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        if not self._frames:
            raise channel.websocket.WebSocketTimeoutException("script exhausted")
        return self._frames.pop(0)


def _cdp(frames):
    c = channel.CDP.__new__(channel.CDP)   # skip create_connection
    c.ws = _FakeWS(frames)
    c._id = 0
    c.events = []
    return c


def main():
    fails = 0

    # 1. empty recv -> dead-socket signal (NOT JSONDecodeError)
    try:
        _cdp([""]).call("Runtime.evaluate", {"expression": "1"})
        print("FAIL: empty recv did not raise")
        fails += 1
    except channel.websocket.WebSocketConnectionClosedException as e:
        assert "empty recv" in str(e)
        print("PASS: empty recv -> WebSocketConnectionClosedException")
    except Exception as e:
        print(f"FAIL: empty recv raised {type(e).__name__}: {e}")
        fails += 1

    # 2. non-JSON frame -> dead-socket signal
    try:
        _cdp(["<html>Bad Gateway</html>"]).call("Page.enable", {})
        print("FAIL: non-JSON frame did not raise")
        fails += 1
    except channel.websocket.WebSocketConnectionClosedException as e:
        assert "non-JSON frame" in str(e)
        print("PASS: non-JSON frame -> WebSocketConnectionClosedException")
    except Exception as e:
        print(f"FAIL: non-JSON frame raised {type(e).__name__}: {e}")
        fails += 1

    # 3. normal flow: buffered event frame + matching response
    c = _cdp([
        json.dumps({"method": "Page.frameStartedLoading", "params": {}}),
        json.dumps({"id": 1, "result": {"value": 42}}),
    ])
    r = c.call("Runtime.evaluate", {"expression": "1"})
    assert r == {"value": 42}, f"bad result: {r!r}"
    assert len(c.events) == 1 and c.events[0]["method"] == "Page.frameStartedLoading"
    assert c.ws.sent and json.loads(c.ws.sent[0])["method"] == "Runtime.evaluate"
    print("PASS: normal event+response (event buffered, result returned)")

    # 4. normal flow over BYTES frames (websocket-client returns bytes for
    #    binary frames) — guard must not misjudge a healthy binary recv
    c = _cdp([
        json.dumps({"method": "Network.requestWillBeSent", "params": {}}).encode(),
        json.dumps({"id": 1, "result": {}}).encode(),
    ])
    r = c.call("Page.enable", {})
    assert r == {} and len(c.events) == 1
    print("PASS: bytes frames pass the guard untouched")

    print(f"channel recv-guard: {4 - fails}/4 PASS" if fails else "channel recv-guard: 4/4 PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
