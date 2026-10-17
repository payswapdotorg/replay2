#!/usr/bin/env python3
"""harvest_gap6a.py — one-command harvest of the GAP-6A worker delivery
(the row-6 wave 1: the background-agent UX runtime).

Polls the lane gap6a's CURRENT chat server-side (registry-resolved, the
harvest_w8.py pattern) for the FLAUZ-GAP6A-REPORT markers; once present,
fetches the bundle + MANIFEST via the workspaces files API, then runs the
station-side verifier (verify_gap6a_manifest.py) with the report's declared
BASE (the work order allows a rebase onto a newer main tip at spawn — the
verifier checks the parent is a real main ancestor, never a fabricated base).

Usage: harvest_gap6a.py [--wait]   (polls until the report lands; default: one shot)
"""
import json, os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
LANE = "gap6a"
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
_FALLBACK_CHAT = "3ed83b7b-2176-482b-9c5c-ef51407e4df8"  # the 2026-10-17 dispatch


def resolve_chat():
    """The lane's CURRENT live chat id from the registry (the truth source)."""
    try:
        rows = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except (OSError, ValueError):
        return _FALLBACK_CHAT
    chat = None
    for r in rows:
        if r.get("name") != LANE:
            continue
        if r.get("action") in ("void", "failed", "done"):
            chat = None
            continue
        m = re.search(r"/c/([0-9a-f-]{36})", r.get("url") or "")
        if m:
            chat = m.group(1)
    return chat or _FALLBACK_CHAT


CHAT = resolve_chat()
OUT = f"/home/z/leads-harvest/{CHAT[:8]}/tree/flauz-delivery/gap6a-bgux"
MARK_BEGIN = "FLAUZ-GAP6A-REPORT BEGIN"
MARK_END = "FLAUZ-GAP6A-REPORT END"
FILES = ["flauz-delivery/gap6a-bgux/gap6a-bgux.bundle",
         "flauz-delivery/gap6a-bgux/MANIFEST"]


def chat_detail():
    r = subprocess.run([sys.executable, os.path.join(BASE, "chats_http.py"),
                        "detail", CHAT], capture_output=True, text=True, timeout=90)
    return r.stdout


def report_text(_):
    sys.path.insert(0, BASE)
    token = open(os.path.join(BASE, "flags/chat_token")).read().strip()
    import urllib.request
    req = urllib.request.Request(
        f"https://chat.z.ai/api/v1/chats/{CHAT}",
        headers={"Authorization": f"Bearer {token}"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    msgs = d.get("messages") or []
    texts = []
    def walk(m):
        texts.append((m.get("role"), json.dumps(m.get("content"))[:200000]))
        for c in (m.get("children") or []):
            walk(c)
    for m in msgs:
        walk(m)
    return "\n".join(t for _r, t in texts)


def workspace_id():
    out = chat_detail()
    m = re.search(r"workspace[^\n]*?([0-9a-f-]{16,})", out, re.I)
    return m.group(1) if m else None


def main():
    global CHAT, OUT
    wait = "--wait" in sys.argv
    while True:
        if wait:
            CHAT = resolve_chat()
            OUT = f"/home/z/leads-harvest/{CHAT[:8]}/tree/flauz-delivery/gap6a-bgux"
        blob = report_text(chat_detail())
        if MARK_BEGIN in blob and MARK_END in blob:
            rep = blob[blob.index(MARK_BEGIN):blob.index(MARK_END) + len(MARK_END)]
            print("=== GAP-6A COMPLETION REPORT FOUND ===")
            print(rep[:3000])
            os.makedirs(OUT, exist_ok=True)
            open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8").write(rep)
            break
        if not wait:
            print("report not present yet (one-shot exit)")
            return 1
        print(f"[{time.strftime('%H:%M:%S')}] waiting for GAP-6A report ...", flush=True)
        time.sleep(120)
    # fetch files
    wsid = workspace_id()
    if not wsid:
        print("no workspace id found in chat detail — run harvest_files manually")
        return 2
    os.makedirs(OUT, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(BASE, "harvest_files.py"),
                        CHAT, wsid] + FILES, capture_output=True, text=True, timeout=600)
    print(r.stdout[-2000:])
    print(r.stderr[-500:])
    # verify manifest + the report-declared base (rebase-aware)
    man = os.path.join(OUT, "MANIFEST")
    rep_path = os.path.join(OUT, "REPORT.txt")
    if os.path.exists(man) and os.path.exists(rep_path):
        print("=== GAP-6A MANIFEST VERIFY ===")
        base = None
        m = re.search(r"^BASE:\s*([0-9a-f]{40})\s*$", open(rep_path).read(), re.M)
        if m:
            base = m.group(1)
        cmd = ["python3", os.path.join(BASE, "verify_gap6a_manifest.py"), man, OUT]
        if base:
            cmd += ["--base", base]
        v = subprocess.run(cmd, capture_output=True, text=True)
        print(v.stdout, v.stderr)
        return v.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
