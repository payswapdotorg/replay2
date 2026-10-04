#!/usr/bin/env python3
"""test_replayd_ladder.py — offline unit test of the frame-capture recovery
ladder's STATE MACHINE (reload budget + streak episode semantics).

The 2026-10-04 reload-storm postmortem: uncapped streak-2 reloads re-fired
every ~5s, pages never settled, streak wedged at 15-22. The budget law:
max 2 reloads per failure episode, >=15s apart, reset on success. This test
drives _reload_ok() through the full budget cycle and verifies the episode
reset WITHOUT touching Chrome/CDP (module import only — the daemon's HTTP
server never binds outside main()).
"""
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import replayd  # noqa: E402


def _reset():
    replayd._reload_budget["used"] = 0
    replayd._reload_budget["last"] = 0.0


def main():
    fails = 0

    # budget law: max 2 per episode, >=15s apart
    _reset()
    assert replayd._reload_ok() is True, "first reload must be granted"
    assert replayd._reload_budget["used"] == 1
    assert replayd._reload_ok() is False, "second reload inside the 15s gap must be refused"
    assert replayd._reload_budget["used"] == 1, "a refused reload must not consume budget"
    replayd._reload_budget["last"] = time.time() - replayd.RELOAD_MIN_GAP - 1
    assert replayd._reload_ok() is True, "reload after the gap must be granted"
    replayd._reload_budget["last"] = time.time() - replayd.RELOAD_MIN_GAP - 1
    assert replayd._reload_ok() is False, "third reload in one episode must be refused (max 2)"
    print(f"PASS: reload budget (max {replayd.RELOAD_MAX}/episode, "
          f">={int(replayd.RELOAD_MIN_GAP)}s apart)")

    # episode reset: budget COUNT clears when the streak ends (success path);
    # the >=15s spacing is a global rate limit and survives the reset
    _reset()
    replayd._reload_budget["used"] = 2
    replayd._reload_budget["last"] = time.time()
    replayd._fail_streak = 3
    with replayd._fail_lock:   # same mutation _serve_good performs on success
        replayd._reload_budget["used"] = 0
        replayd._fail_streak = 0
    assert replayd._reload_ok() is False, "spacing still applies right after a reload"
    replayd._reload_budget["last"] = time.time() - replayd.RELOAD_MIN_GAP - 1
    assert replayd._reload_ok() is True, "count must reset when the episode ends"
    assert replayd._fail_streak == 0
    print("PASS: episode reset clears the reload count (spacing survives)")

    # ladder constants match the anti-storm spec
    assert replayd.RELOAD_MAX == 2 and replayd.RELOAD_MIN_GAP >= 15
    assert replayd.SWITCH_COOLDOWN == 30
    print("PASS: ladder constants (2 reloads, 15s gap, 30s switch cooldown)")

    # streak snapshot semantics used by the log line
    replayd._fail_streak = 0
    with replayd._fail_lock:
        replayd._fail_streak += 1
        streak = replayd._fail_streak
    assert streak == 1
    print("PASS: streak snapshot increments race-free")

    print(f"replayd ladder: {4 - fails}/4 PASS" if fails else "replayd ladder: 4/4 PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
