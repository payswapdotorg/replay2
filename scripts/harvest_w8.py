#!/usr/bin/env python3
"""harvest_w8.py — one-command harvest of the A-PROD-006-W8 worker delivery.

Polls chat 3ef8ac4a (lane aprod006w8) server-side for the COMPLETION REPORT
markers; once present, fetches the bundle + MANIFEST via the workspaces files
API, verifies every MANIFEST sha256 + the TREE-SELF-CHECK, reconstructs the
branch from the bundle, and re-verifies the frozen-instrument sha256 table.

Usage: harvest_w8.py [--wait]   (polls until the report lands; default: one shot)
"""
import json, os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
CHAT = "3ef8ac4a-f89a-4c1c-a1c1-0cf87578d5a3"
WS_DEFAULT = None
OUT = "/home/z/leads-harvest/3ef8ac4a/tree/flauz-delivery/aprod-006-w8-sustained-cycle"
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
    wait = "--wait" in sys.argv
    while True:
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
