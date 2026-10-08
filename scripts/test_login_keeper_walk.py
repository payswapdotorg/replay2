#!/usr/bin/env python3
"""test_login_keeper_walk.py — offline unit test of the 2026-10-08 walk law
(login_state / _live_chat_tab / restore_pass tab selection).

Field defect (2026-10-08 reset-#13 recovery): the keeper's chat_tab()
returned tabs[0], whose renderer was wedged (SecurityError on localStorage).
The keeper judged the LOGGED-IN browser as 'not authenticated' and hammered
stale-token restores against the dead tab while 4 healthy tabs carried the
live ali17 session. This test drives the walk with fake tabs/CDP (offline —
no Chrome touched) and verifies: (1) login_state skips the wedged first tab
and reads a healthy one; (2) all-dead is the only failure and names the
last error; (3) _live_chat_tab returns the first live tab; (4) restore_pass
injects into a live tab even when tabs[0] is wedged.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import login_keeper  # noqa: E402
import channel       # noqa: E402


class FakeCDP:
    """channel.CDP stand-in: '1' liveness evals and the token reads succeed
    on healthy tabs; everything raises on wedged tabs."""

    def __init__(self, ws_url, timeout=20, wedge=False, tok="", ident="?"):
        self.ws_url = ws_url
        self.wedge = wedge
        self.tok = tok
        self.ident = ident
        self.closed = False
        self.eval_log = []

    def eval(self, expr, await_promise=False, timeout=8):
        self.eval_log.append(expr)
        if self.wedge:
            raise RuntimeError('js error: {"className": "DOMException", '
                               '"description": "SecurityError"}')
        if expr == "1":
            return 1
        if "getItem('token')" in expr and "function" not in expr:
            return self.tok
        if expr.startswith("(function()"):
            return self.ident
        return None

    def close(self):
        self.closed = True


LIVE_TOK = "aa.bb.cc"


def _fake_pages(tabs):
    def pages():
        return [{"type": "page", "id": t[0], "url": t[1],
                 "webSocketDebuggerUrl": "ws://fake/" + t[0]} for t in tabs]
    return pages


def main():
    fails = 0

    # (1) login_state skips a wedged tabs[0], reads the first healthy tab
    made = {}

    def fake_cdp(ws_url, timeout=20):
        tab_id = ws_url.rsplit("/", 1)[-1]
        wedge = tab_id == "WEDGED01"
        made[tab_id] = FakeCDP(ws_url, timeout, wedge=wedge,
                               tok=LIVE_TOK, ident="ali17@payswap.org")
        return made[tab_id]

    login_keeper.pages = _fake_pages([
        ("WEDGED01", "https://chat.z.ai/"),
        ("HEALTHY1", "https://chat.z.ai/"),
        ("HEALTHY2", "https://chat.z.ai/"),
    ])
    channel.CDP = fake_cdp
    tok, ident = login_keeper.login_state()
    assert tok == LIVE_TOK and ident == "ali17@payswap.org", \
        f"walk must read a healthy tab, got ({tok}, {ident})"
    assert made["WEDGED01"].closed, "wedged tab ws must be closed in finally"
    assert made["HEALTHY1"].closed, "healthy tab ws must be closed in finally"
    print("PASS: login_state walks past a wedged tabs[0] (live session read)")

    # (2) all-dead is the only failure, and it names the last error
    def fake_cdp_dead(ws_url, timeout=20):
        tab_id = ws_url.rsplit("/", 1)[-1]
        return FakeCDP(ws_url, timeout, wedge=True)

    channel.CDP = fake_cdp_dead
    tok, reason = login_keeper.login_state()
    assert tok is None and "all-tabs-dead" in reason and "RuntimeError" in reason, \
        f"all-dead must be reported with the last error, got ({tok}, {reason})"
    print("PASS: all-tabs-dead reports the diagnostic (last error named)")

    # (3) _live_chat_tab returns the first LIVE tab (not the wedged first)
    channel.CDP = fake_cdp
    login_keeper.pages = _fake_pages([
        ("WEDGED01", "https://chat.z.ai/"),
        ("HEALTHY1", "https://chat.z.ai/"),
    ])
    tab, c = login_keeper._live_chat_tab()
    assert tab is not None and tab["id"] == "HEALTHY1", \
        "_live_chat_tab must skip the wedged tab"
    assert not c.closed, "returned connection must stay open for the caller"
    c.close()
    print("PASS: _live_chat_tab picks the first live tab")

    # (4) restore_pass injects into a live tab even with a wedged tabs[0]
    injected = {}

    def fake_cdp_inject(ws_url, timeout=20):
        tab_id = ws_url.rsplit("/", 1)[-1]
        wedge = tab_id == "WEDGED01"
        fake = FakeCDP(ws_url, timeout, wedge=wedge, tok="", ident="guest-x")
        orig_eval = fake.eval

        def eval_spy(expr, await_promise=False, timeout=8):
            if "setItem" in expr:
                injected[tab_id] = expr
            return orig_eval(expr, await_promise, timeout)

        fake.eval = eval_spy
        return fake

    channel.CDP = fake_cdp_inject
    with tempfile.TemporaryDirectory() as td:
        login_keeper.DURABLE = os.path.join(td, "tok.txt")
        with open(login_keeper.DURABLE, "w") as f:
            f.write(LIVE_TOK + "\n")
        login_keeper.RESTORE_RETRY = 1
        # login_state after injection returns the live identity → restored
        login_keeper.login_state = lambda: (LIVE_TOK, "ali17@payswap.org")
        ok = login_keeper.restore_pass()
        assert ok, "restore_pass must succeed via a live tab"
        assert "WEDGED01" not in injected and injected, \
            "injection must land on a live tab, never the wedged one"
        assert json.dumps(LIVE_TOK) in list(injected.values())[0], \
            "THE LAW: token injected JSON-quoted (bare value semantics)"
        print("PASS: restore_pass injects into a live tab (walk law)")

    print(f"\n{4 - fails}/4 PASS" if fails == 0 else f"\n{fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
