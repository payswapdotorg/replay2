#!/usr/bin/env python3
"""test_bridge_branches.py — offline unit test of the branch-card pagination
fix (_branch_card).

2026-10-04 (R4) telemetry postmortem: payswapdotorg/Flauz crossed 130
branches, 'main' fell off /branches?per_page=50 page 1, and cmd_status
answered main_sha "?" while the rest of the repo card worked. The fix: when
page 1 lacks 'main' (but HAS branches), fetch /branches/main directly and
prepend it. Offline: gh() is monkeypatched with a call-counting fake —
no network, no PAT, no CDP.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import bridge  # noqa: E402


def _br(name, sha):
    return {"name": name, "commit": {"sha": sha}}


def _fake_gh(responses):
    """gh() fake: counts calls; answers scripted paths (default: 404-ish)."""
    calls = []

    def gh(repo, path, token=""):
        calls.append(path)
        return responses.get(path, {"message": "Not Found"})

    return gh, calls


def main():
    fails = 0

    # 1. main ON page 1 -> resolved from page 1, ZERO extra API calls
    gh, calls = _fake_gh({})
    bridge.gh = gh
    MAIN_SHA = "9fb883d8087f" + "0" * 28          # full 40-char sha
    page1 = [_br("dev", "a" * 40), _br("main", MAIN_SHA), _br("feat", "b" * 40)]
    blist, main_sha = bridge._branch_card("org/repo", "pat", page1)
    assert main_sha == MAIN_SHA[:10], main_sha
    assert calls == [], calls
    assert blist[0]["name"] == "dev" and len(blist) == 3
    print("PASS: main on page 1 -> resolved, zero extra calls")

    # 2. main OFF page 1 (130+ branches) -> one /branches/main call,
    #    'main' prepended to the card, sha resolved
    gh, calls = _fake_gh({"/branches/main": _br("main", MAIN_SHA)})
    bridge.gh = gh
    page1 = [_br(f"flauz-aprod/w{i:03d}", "a" * 40) for i in range(50)]
    blist, main_sha = bridge._branch_card("org/repo", "pat", page1)
    assert main_sha == MAIN_SHA[:10], main_sha
    assert calls == ["/branches/main"], calls
    assert blist[0] == {"name": "main", "sha": MAIN_SHA[:10]}, blist[0]
    assert len(blist) == 51 and blist[1]["name"] == "flauz-aprod/w000"
    print("PASS: main off page 1 -> fetched directly, prepended, resolved")

    # 3. no branches (empty page 1 / API failure dict) -> "?" with the
    #    empty-list guard: no extra call
    for brs in ([], {"message": "API rate limit exceeded"}, None):
        gh, calls = _fake_gh({"/branches/main": _br("main", "z" * 40)})
        bridge.gh = gh
        blist, main_sha = bridge._branch_card("org/repo", "pat", brs)
        assert main_sha == "?", (brs, main_sha)
        assert blist == [] and calls == [], (brs, calls)
    print("PASS: no branches -> '?', empty-list guard (no extra call)")

    # 4. main off page 1 AND the direct fetch fails (404/telemetry hole) ->
    #    honest "?", page-1 card still served
    gh, calls = _fake_gh({})
    bridge.gh = gh
    page1 = [_br("dev", "a" * 40), _br("feat", "b" * 40)]
    blist, main_sha = bridge._branch_card("org/repo", "pat", page1)
    assert main_sha == "?" and len(blist) == 2 and calls == ["/branches/main"]
    print("PASS: direct fetch fails -> honest '?' (card still served)")

    print(f"bridge branch card: {4 - fails}/4 PASS" if fails else "bridge branch card: 4/4 PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
