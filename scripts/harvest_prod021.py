#!/usr/bin/env python3
"""harvest_prod021.py (v2, direct-HTTP) — fetch PROD-021's staged delivery/
from its worker sandbox via the chat.z.ai workspaces API over plain HTTPS
(Bearer token from flags/chat_token) — no browser/CDP dependency.

Why v2: the in-page fetch path (CDP eval per file) proved unreliable under
the recurring renderer-wedge; the API is user-scoped, so a direct request
with the session token is equivalent and far faster.
"""
import base64
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CHAT = "bf13f267-40bb-4a82-8f9b-d725e916784e"
WSID = "ws-411d870e-6ffb-4e6a-8f9d-0639815338c7"
OUT = os.path.join(BASE, "harvests", "prod021-delivery")
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"

TOK = open(os.path.join(BASE, "flags", "chat_token")).read().strip().strip('"')


def call(path, body=None, timeout=60):
    url = f"{API}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {TOK}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# 1. tree
tree = json.loads(call("ls-tree", {"chatId": CHAT, "workspace_id": WSID}).decode())
files = [f for f in tree if f.startswith("delivery/")]
print(f"delivery files: {len(files)}", flush=True)
os.makedirs(OUT, exist_ok=True)

ok = fail = 0
for i, fp in enumerate(files):
    rel = fp[len("delivery/"):]
    dest = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dest) or OUT, exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        ok += 1
        continue
    for attempt in range(4):
        try:
            raw = call("content", {"chatId": CHAT, "workspace_id": WSID,
                                   "rev": "latest", "filepath": fp}, timeout=110)
            # detect text: no NUL and valid UTF-8
            is_text = b"\x00" not in raw
            if is_text:
                try:
                    txt = raw.decode("utf-8")
                    open(dest, "w", encoding="utf-8", newline="").write(txt)
                except UnicodeDecodeError:
                    is_text = False
            if not is_text:
                open(dest, "wb").write(raw)
            ok += 1
            if (i + 1) % 20 == 0:
                print(f"[{i+1}/{len(files)}] ... {rel[:55]}", flush=True)
            break
        except Exception as e:
            if attempt == 3:
                fail += 1
                print(f"FAIL {rel}: {e}", flush=True)
            else:
                time.sleep(3)
print(f"HARVEST DONE ok={ok} fail={fail}", flush=True)
