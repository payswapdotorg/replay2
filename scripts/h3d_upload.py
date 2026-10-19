#!/usr/bin/env python3
"""h3d_upload.py — set a local file on the FIRST visible image file-input of
the hyper3d tab via CDP DOM.setFileInputFiles (bypasses the native picker)."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
import websocket  # noqa: E402


def main():
    path = sys.argv[1]
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    tabs = channel.list_tabs()
    h3d = [t for t in tabs if "hyper3d" in (t.get("url") or "")]
    if not h3d:
        print(json.dumps({"error": "no tab"}))
        return
    ws = websocket.create_connection(h3d[0]["webSocketDebuggerUrl"], timeout=20)
    mid = [0]

    def send(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        while True:
            ev = json.loads(ws.recv())
            if ev.get("id") == mid[0]:
                return ev

    try:
        send("DOM.enable")
        doc = send("DOM.getDocument", {"depth": -1, "pierce": True})
        root = doc["result"]["root"]["nodeId"]
        qr = send("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file]"})
        nodes = qr["result"]["nodeIds"]
        if not nodes or idx >= len(nodes):
            print(json.dumps({"error": "no file inputs", "n": len(nodes)}))
            return
        # pick the idx-th image-accepting input (by DOM order)
        chosen = None
        img_inputs = []
        for nid in nodes:
            ar = send("DOM.getAttributes", {"nodeId": nid})
            attrs = ar["result"]["attributes"]
            d = dict(zip(attrs[::2], attrs[1::2]))
            acc = d.get("accept", "")
            if "image" in acc or ".png" in acc or ".jpg" in acc or ".webp" in acc:
                img_inputs.append((nid, d.get("id") or "", acc))
        if not img_inputs:
            print(json.dumps({"error": "no image inputs", "n": len(nodes)}))
            return
        chosen = img_inputs[idx][0] if idx < len(img_inputs) else img_inputs[0][0]
        print("candidates:", json.dumps(img_inputs), file=sys.stderr)
        r = send("DOM.setFileInputFiles", {"files": [path], "nodeId": chosen})
        if "error" in r:
            print(json.dumps({"error": r["error"]["message"]}))
            return
        print(json.dumps({"ok": True, "nodeId": chosen, "imageInputs": len(img_inputs)}))
    finally:
        ws.close()


if __name__ == "__main__":
    main()
