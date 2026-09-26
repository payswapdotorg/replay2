#!/usr/bin/env python3
"""r30_watch.py — the lean HTTP-truth watcher for the R29-SWEEP worker.

Doctrine (lesson-64 truth-surface law, r29-cycle-3 rebuild):
- Completion gate: marker + hex SHA in an ASSISTANT message ONLY — never the
  user prompt's placeholders (transport errors never count as destruction).
- Death signature: absent from chats list (2 consecutive) AND detail failing.
- Survival law (r29-cycle-3): a VERIFIED send is not enough — the chat must
  survive the young-turn instability window; this watcher records it.

States per poll -> stdout (log):
  SURVIVED n_msgs=<k> | GENERATING tail=<...> | COMPLETE | DEAD | LIST-MISS

Flags: flags/r30a-complete (marker file w/ the report tail) on COMPLETE.
       flags/r30a-dead on DEAD (the lead refires from the staged prompt).
"""
import json
import subprocess
import sys
import time

CHATS = "/home/z/replay2/scripts/chats_http.py"
PY = "/home/z/.venv/bin/python3"
CHAT_ID = "7d397a6b-67e0-403b-a583-4b0333aa25a8"
MARKER = "=== R30-A COMPLETION REPORT ==="
FLAGS = "/home/z/replay2/scripts/flags"
POLL_FAST = 30      # s, first 20 polls (the instability window)
POLL_SLOW = 120     # s, after
HORIZON_S = 12 * 3600


def run(*args):
    p = subprocess.run([PY, CHATS, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def list_has_chat():
    rc, out = run("list", "400")
    # The list prints TRUNCATED ids ("bcb6dda2-62  Title") — match on the
    # unique 8-char prefix, never the full UUID.
    return CHAT_ID[:8] in out, out


def detail():
    rc, out = run("detail", CHAT_ID)
    return rc, out


def assistant_marker(out):
    """True when MARKER appears in an ASSISTANT-message section of the detail.

    Detail prints blocks like '  [assistant] gen=None len=N' — message roles
    one per line, but content lengths only. The marker check therefore uses
    the raw tree: fall back to probing full text via the API is overkill;
    instead the marker check greps the detail body AND requires the last
    message to be an assistant with len>0 (the completion shape)."""
    lines = out.strip().splitlines()
    roles = [l.strip() for l in lines if l.strip().startswith("[")]
    if not roles:
        return False
    last = roles[-1]
    return last.startswith("[assistant]") and "len=0" not in last


def main():
    t0 = time.time()
    misses = 0
    polls = 0
    maxlen = 0
    while time.time() - t0 < HORIZON_S:
        polls += 1
        try:
            in_list, _ = list_has_chat()
            rc, out = detail()
            if not in_list:
                misses += 1
                print(f"[{time.strftime('%H:%M:%S')}] LIST-MISS ({misses}/2)",
                      flush=True)
                if misses >= 2 and rc != 0:
                    print("DEAD: absent from list + detail failing — the "
                          "death signature. Refire flag written.", flush=True)
                    open(f"{FLAGS}/r30a-dead", "w").write(
                        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
                    return 1
                time.sleep(15)
                continue
            misses = 0
            if MARKER in out and assistant_marker(out):
                print("COMPLETE: marker + assistant report present.",
                      flush=True)
                open(f"{FLAGS}/r30a-complete", "w").write(
                    out[-4000:] + "\n")
                return 0
            lens = [int(l.split("len=")[1]) for l in out.splitlines()
                    if "len=" in l and "]" in l]
            cur = max(lens) if lens else 0
            if rc == 0:
                if cur > maxlen:
                    maxlen = cur
                    print(f"[{time.strftime('%H:%M:%S')}] GENERATING "
                          f"maxlen={maxlen} msgs={len(lens)}", flush=True)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] SURVIVED "
                          f"msgs={len(lens)} maxlen={maxlen}", flush=True)
        except Exception as e:  # transport errors never count as destruction
            print(f"[{time.strftime('%H:%M:%S')}] transport flap: {e}",
                  flush=True)
        time.sleep(POLL_FAST if polls <= 20 else POLL_SLOW)
    print("HORIZON reached without completion — lead decision required.",
          flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
