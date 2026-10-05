#!/usr/bin/env python3
"""retry_w3.py — outer retry loop for the unicom-w3-003 dispatch.

The platform's GLM-5.3 capacity comes in waves (~30-40 min). Each
dispatch_worker create assaults 12 rounds internally, but a squeezed
window exhausts it with 'NOT VERIFIED'. This loop adds outer retries:
  every ROUND_S: void any stale w3 record -> fire create (wait) ->
  when a sent=true record appears, verify REAL liveness by opening the
  chat URL in a tab (a zombie record redirects to home instantly —
  the list API alone is NOT truth). Stop on real liveness.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import channel  # noqa: E402
import chats_http  # noqa: E402

NAME = "unicom-w3-003"
PROMPT = os.path.join(HERE, "worker-prompts", "unicom-w3-003.md")
REGISTRY = os.path.join(HERE, "flags", "session_registry.jsonl")
LOG = os.path.join(HERE, "logs", "retry_w3.log")
ROUND_S = 300
MAX_TRIES = 8


def log(msg):
    line = f"[retry-w3 {time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def newest_sent_url():
    url = None
    try:
        with open(REGISTRY) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("name") == NAME and r.get("sent") and r.get("url") \
                        and r.get("action") != "void":
                    url = r["url"]  # newest wins (file order)
    except FileNotFoundError:
        pass
    return url


def record_blocks():
    """any non-void record for NAME newer than the last void?"""
    blocked = False
    try:
        with open(REGISTRY) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("name") != NAME:
                    continue
                if r.get("action") == "void":
                    blocked = False
                else:
                    blocked = True
    except FileNotFoundError:
        pass
    return blocked


def chat_live_for_real(url):
    """Open the chat URL in a tab; a zombie redirects to home. Truth test."""
    try:
        tab = channel.new_tab(url)
        time.sleep(9)
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            href = c.eval("location.href", timeout=10) or ""
        finally:
            c.close()
        try:
            import urllib.request
            urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:9222/json/close/" + tab["id"]), timeout=5).read()
        except Exception:
            pass
        if "/c/" in href and href.rstrip("/").endswith(url.split("/c/")[-1].split("/")[0][:24]):
            return True
        log(f"liveness FAIL: opened {url[:50]} -> landed on {href[:50]} (zombie)")
        return False
    except Exception as e:
        log(f"liveness probe error: {e!r}")
        return False


def main():
    log(f"armed — {MAX_TRIES} tries, {ROUND_S}s apart")
    for attempt in range(1, MAX_TRIES + 1):
        url = newest_sent_url()
        if url and chat_live_for_real(url):
            log(f"W3-003 LIVE for real at {url[:60]} — done")
            return 0
        if record_blocks():
            subprocess.run([sys.executable, os.path.join(HERE, "dispatch_worker.py"),
                            "void", NAME, f"retry-w3 outer loop attempt {attempt}"],
                           capture_output=True, timeout=180, cwd=HERE)
            log("stale record voided")
        log(f"attempt {attempt}/{MAX_TRIES}: firing create")
        with open(os.path.join(HERE, "logs", "dispatch-unicom-w3-003.log"), "a") as lg:
            try:
                subprocess.run([sys.executable, os.path.join(HERE, "dispatch_worker.py"),
                                "create", NAME, PROMPT],
                               stdout=lg, stderr=subprocess.STDOUT, timeout=900, cwd=HERE)
            except subprocess.TimeoutExpired:
                log("create timed out (900s) — next round")
        url = newest_sent_url()
        if url and chat_live_for_real(url):
            log(f"W3-003 LIVE for real at {url[:60]} — done")
            return 0
        log(f"attempt {attempt} did not land — sleeping {ROUND_S}s")
        time.sleep(ROUND_S)
    log("exhausted outer retries — TL attention needed")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
