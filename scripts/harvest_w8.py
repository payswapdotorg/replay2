#!/usr/bin/env python3
"""harvest_w8.py — one-command harvest of the A-PROD-006-W8 worker delivery.

Polls the lane aprod006w8's CURRENT chat server-side (registry-resolved:
the latest non-void row's /c/<uuid> — survives the sentinel's recover()
void+re-dispatch cycles) for the COMPLETION REPORT
markers; once present, fetches the bundle + MANIFEST via the workspaces files
API, verifies every MANIFEST sha256 + the TREE-SELF-CHECK, reconstructs the
branch from the bundle, and re-verifies the frozen-instrument sha256 table.

Usage: harvest_w8.py [--wait]   (polls until the report lands; default: one shot)
"""
import json, os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
LANE = "aprod006w8"
REGISTRY = os.path.join(BASE, "flags", "session_registry.jsonl")
_FALLBACK_CHAT = "54dddc88-108d-4acd-aa4c-59e89b66eac6"  # R39-a re-dispatch lane


def resolve_chat():
    """The lane's CURRENT live chat id from the registry (the truth source).
    Void/failed/done rows CLOSE the lane; a later create/tab-reopen/send row
    re-opens it with its /c/<uuid>. Survives recover() void+re-dispatch: the
    fresh create row carries the new chat id. Falls back to the last-known
    id only if the registry is unreadable or the lane is mid-recovery
    (voided, fresh create not yet landed — a seconds-wide gap)."""
    try:
        rows = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except (OSError, ValueError):
        return _FALLBACK_CHAT
    chat = None
    for r in rows:
        if r.get("name") != LANE:
            continue
        if r.get("action") in ("void", "failed", "done"):
            chat = None  # closes the lane (registry truth)
            continue
        m = re.search(r"/c/([0-9a-f-]{36})", r.get("url") or "")
        if m:
            chat = m.group(1)  # LAST live row wins
    return chat or _FALLBACK_CHAT


CHAT = resolve_chat()
WS_DEFAULT = None
OUT = f"/home/z/leads-harvest/{CHAT[:8]}/tree/flauz-delivery/aprod-006-w8-sustained-cycle"
MARK_BEGIN = "FLAUZ-APROD-006-W8-REPORT BEGIN"
MARK_END = "FLAUZ-APROD-006-W8-REPORT END"
FILES = ["flauz-delivery/aprod-006-w8-sustained-cycle/aprod-006-w8.bundle",
         "flauz-delivery/aprod-006-w8-sustained-cycle/MANIFEST"]


def chat_detail():
    r = subprocess.run([sys.executable, os.path.join(BASE, "chats_http.py"),
                        "detail", CHAT], capture_output=True, text=True, timeout=90)
    return r.stdout


def report_text(detail_out):
    # the report lives in the LAST assistant message; chats_http detail prints
    # a tree summary — use the raw API for full text when markers may exist
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
    blob = "\n".join(t for _r, t in texts)
    return blob


def workspace_id():
    # the workspace id rides the chat detail tree (web-dev workspaces metadata)
    out = chat_detail()
    m = re.search(r"workspace[^\n]*?([0-9a-f-]{16,})", out, re.I)
    return m.group(1) if m else None


def main():
    global CHAT, OUT
    wait = "--wait" in sys.argv
    while True:
        if wait:  # long-running: track recover() void+re-dispatch mid-wait (R40-a)
            CHAT = resolve_chat()
            OUT = f"/home/z/leads-harvest/{CHAT[:8]}/tree/flauz-delivery/aprod-006-w8-sustained-cycle"
        blob = report_text(chat_detail())
        if MARK_BEGIN in blob and MARK_END in blob:
            rep = blob[blob.index(MARK_BEGIN):blob.index(MARK_END) + len(MARK_END)]
            print("=== COMPLETION REPORT FOUND ===")
            print(rep[:3000])
            break
        if not wait:
            print("report not present yet (one-shot exit)")
            return 1
        print(f"[{time.strftime('%H:%M:%S')}] waiting for report ...", flush=True)
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
    # verify manifest
    man = os.path.join(OUT, "MANIFEST")
    if os.path.exists(man):
        print("=== MANIFEST VERIFY ===")
        v = subprocess.run(["python3", os.path.join(BASE, "verify_w8_manifest.py"),
                            man, OUT], capture_output=True, text=True)
        print(v.stdout, v.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
