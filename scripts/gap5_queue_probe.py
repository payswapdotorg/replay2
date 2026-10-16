#!/usr/bin/env python3
"""gap5_queue_probe.py — gentle generation-watch for the queued GAP-5 task.

The quota-drain doctrine: no 30-60s probe flooding; a gentle DOM-only check
every PROBE_S seconds (no sends — sends contribute to account contention).
When the generation starts (chars grow past the echo, or a stop button /
streaming marker appears), write the marker + log and exit.
"""
import json, os, sys, time
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

LOG = '/home/z/replay2/scripts/logs/gap5_queue_probe.log'
MARKER = '/home/z/replay2/scripts/flags/gap5_generation_started'
URL_PAT = 'chat.z.ai/c/edb5160e'
ECHO = 7591
PROBE_S = 600

def log(msg):
    with open(LOG, 'a') as f:
        f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}\n")

log(f"probe online (every {PROBE_S}s, DOM-only, echo={ECHO})")
rounds = 0
while True:
    rounds += 1
    try:
        tab = channel.find_tab(pattern=URL_PAT)
        if not tab:
            log(f"round {rounds}: tab absent (closed/navigated) — will re-find on next cycle")
        else:
            cdp = channel.CDP(tab['webSocketDebuggerUrl'])
            body = cdp.eval("document.body ? (document.body.innerText || '') : ''")
            cdp.close()
            chars = len(body)
            indicators = []
            for kw in ('stop', 'generat', 'capacity', 'limit', 'queued'):
                if kw in body[-3000:].lower():
                    indicators.append(kw)
            if chars > ECHO + 200:
                log(f"round {rounds}: GENERATION STARTED (chars {ECHO} -> {chars}); indicators={indicators}")
                with open(MARKER, 'w') as f:
                    f.write(json.dumps({'ts': time.time(), 'chars': chars, 'rounds': rounds}))
                break
            log(f"round {rounds}: queued (chars={chars}, indicators={indicators})")
    except Exception as exc:
        log(f"round {rounds}: probe error {exc!r} — continuing")
    time.sleep(PROBE_S)
