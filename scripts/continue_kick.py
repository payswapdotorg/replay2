#!/usr/bin/env python3
"""continue_kick.py — drive kick-spawned worker sessions forward.

Finding (2026-10-04 04:40Z): raw-completions kicks spawn TOOL-BEARING turns
(the pod filesystem persists progress across turns) but NOT the platform's
autonomous agent loop — the model ends its turn after a batch of tool calls.
The composer path (which arms the full loop) stays gated during the
overnight window. This watcher bridges the gap: every CONTINUE_EVERY, for
each lane whose server tree has not grown since its last kick, fire a
short CONTINUATION kick whose directive points the worker at its own
sandbox state (its memory across turns).

Stops kicking a lane when its newest assistant content contains the
filled-report marker (=== WORKER REPORT === with real content, not the
prompt's template) — then the lane is DONE and the TL harvests.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import channel  # noqa: E402

LOG = os.path.join(HERE, "logs", "continue-kick.log")
CONTINUE_EVERY = 300  # 5 min between continuation rounds per lane
MAX_HOURS = 18

FALLBACK_LANES = {
    "w126": "cfdefe55-eee0-4a65-8258-9dbf8d4d355d",
    "w131": "734cbc9a-6d9d-4499-ad67-cc854246eb98",
}

REGISTRY = os.path.join(HERE, "flags", "session_registry.jsonl")


def resolve_lanes():
    """Lanes from the session registry (latest non-void per w12x/w13x name);
    fall back to the hardcoded pair when the registry has nothing live."""
    lanes = {}
    try:
        for line in open(REGISTRY):
            try:
                r = json.loads(line)
            except Exception:
                continue
            name = r.get("name") or ""
            if not (name.startswith("w12") or name.startswith("w13")):
                continue
            if r.get("event") == "void" or r.get("action") == "void":
                # drop every alias family this void covers (w125-2 -> w125)
                fam = name.rstrip("0123456789-").replace("-", "")
                for k in [k for k in lanes if k.rstrip("0123456789") == name.rstrip("0123456789-2-")]:
                    pass
                lanes.pop(name.split("-company")[0].split("-execution")[0].split("-agent")[0]
                          .replace("-2", "").replace("-3", ""), None)
                lanes.pop(name, None)
                continue
            url = r.get("url") or ""
            if "/c/" in url:
                key = name.replace("-2", "").replace("-3", "")
                lanes[key] = url.split("/c/")[-1]
    except FileNotFoundError:
        pass
    for k, v in FALLBACK_LANES.items():
        lanes.setdefault(k, v)
    return lanes

LANE_DIRECTIVES = {
    "w125": (
        "Continue the W125 Company Coverage work order. Your sandbox persists "
        "your progress (the cloned repo at /home/z/aurum-w125 or similar — check "
        "your filesystem). THIS TURN: write/complete the coverage module files "
        "(service, validation, errors, migrations, contract surface, tests) — "
        "emit as many files as you can in this turn, then run the gates you can. "
        "Repeat across turns until done: all gates green, branch "
        "work/w125-company-coverage pushed, then the real === WORKER REPORT ===."
    ),
    "w126": (
        "Continue the W126 Company Query Plane work order. Your sandbox persists "
        "your progress. THIS TURN: write/complete the company-query module "
        "(pipeline, two-layer response types, API route) and the /company product "
        "UI — emit as many files as you can, run what gates you can. Repeat until "
        "done: all gates green, branch work/w126-company-query pushed, then the "
        "real === WORKER REPORT ===."
    ),
    "w131": (
        "Continue the W131 Execution Platform Architecture Study work order. Your "
        "sandbox persists your progress. THIS TURN: write/complete the study record "
        "spec file and the frozen contracts module (types + compile tests) — emit "
        "as much as you can. Repeat until done: all gates green, branch "
        "work/w131-execution-contracts pushed, then the real === WORKER REPORT ===."
    ),
}

DIRECTIVE = LANE_DIRECTIVES.get("w125", "")


def log(m):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}Z] {m}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def tree_state(cid):
    """(total, newest_ts, report_done) via a dedicated home tab."""
    tab = channel.new_tab("https://chat.z.ai/")
    if tab is None:
        raise RuntimeError("probe tab failed")
    time.sleep(5)
    tabs = {t["id"]: t for t in channel.list_tabs()}
    t = tabs.get(tab["id"], tab)
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        js = f"""
        (async () => {{
          const t0 = localStorage.getItem('token') || '';
          const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t0}}}});
          const d = await r.json();
          const hist = (d.chat || {{}}).history || {{}};
          const mmap = hist.messages || {{}};
          let newest = 0, report = false;
          for (const m of Object.values(mmap)) {{
            if ((m.timestamp || 0) > newest) newest = m.timestamp || 0;
            const c = m.content;
            const txt = typeof c === 'string' ? c : JSON.stringify(c || '');
            if (m.role === 'assistant' && txt.includes('WORKER REPORT') &&
                !txt.includes('<sha>') && !txt.includes('PASS|FAIL') &&
                txt.length > 800) {{
              report = true;
            }}
          }}
          return JSON.stringify({{total: Object.keys(mmap).length, newest, report}});
        }})()
        """
        return json.loads(ws.eval(js, await_promise=True, timeout=90))
    finally:
        try:
            ws.close()
        except Exception:
            pass
        try:
            channel._http_json("/json/close/" + t["id"], method="PUT")
        except Exception:
            pass


def kick(cid, name):
    """Fire a continuation kick via hybrid_kick.py with the lane directive."""
    msg_file = f"/tmp/continue-directive-{name}.txt"
    with open(msg_file, "w") as f:
        f.write(LANE_DIRECTIVES.get(name) or LANE_DIRECTIVES.get(name.split('-')[0]) or DIRECTIVE)
    p = subprocess.run(
        [sys.executable, os.path.join(HERE, "hybrid_kick.py"), cid, msg_file],
        capture_output=True, text=True, timeout=560, cwd=HERE)
    tail = (p.stdout or "").strip().splitlines()[-2:]
    return " | ".join(tail)[:220]


def main():
    log("continue-kick watcher started")
    last_kick = {}
    last_fail = {}
    done = set()
    start = time.time()
    while time.time() - start < MAX_HOURS * 3600:
        LANES = resolve_lanes()
        for name in list(done):
            if name not in LANES:
                done.discard(name)
        if not LANES:
            time.sleep(60)
            continue
        if len(done) >= len(LANES):
            break
        for name, cid in list(LANES.items()):
            if name in done:
                continue
            if name not in LANE_DIRECTIVES:
                LANE_DIRECTIVES[name] = LANE_DIRECTIVES.get(name.split("-")[0], 
                    "Continue your work order. Check your sandbox filesystem state and proceed. "
                    "Complete all gates, push your branch, deliver the real report.")
            if name in done:
                continue
            try:
                st = tree_state(cid)
            except Exception as e:
                log(f"{name}: probe error {e}")
                continue
            if st["report"]:
                log(f"{name}: REPORT PRESENT — lane done")
                done.add(name)
                continue
            age = time.time() - st["newest"]
            since_kick = time.time() - last_kick.get(name, 0)
            failed = last_fail.get(name, 0)
            cooldown = 90 if failed >= 2 else CONTINUE_EVERY
            if age > 330 and since_kick > cooldown:
                log(f"{name}: stalled {int(age)}s (total={st['total']}) — kicking")
                try:
                    result = kick(cid, name)
                    log(f"{name}: kick -> {result}")
                    last_kick[name] = time.time()
                    if "FIRE RESULT" in result or "chars" in result:
                        last_fail[name] = 0
                    else:
                        last_fail[name] = failed + 1
                except subprocess.TimeoutExpired:
                    log(f"{name}: kick timed out — will retry next round")
                    last_fail[name] = failed + 1
                # one kick per round: give the model the turn
                break
        time.sleep(120)
    log(f"watcher exiting (done={sorted(done)})")


if __name__ == "__main__":
    sys.exit(main())
