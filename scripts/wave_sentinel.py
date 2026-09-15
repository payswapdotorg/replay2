#!/usr/bin/env python3
"""wave_sentinel.py — the S122 wave sentinel (post reset #3, 2026-09-15 13:2x).

State at arm time (remote truth, verified):
  sporta main 706ba9f = 45/50. M4 6/6 (W306 merged 56cb47b by the parallel
  lane), W604 merged 424c1ce (M6 4/5). The parallel lane is IN FLIGHT on
  W704 (branch w704-live-playback, wip transit 4d4156a at 13:04 UTC — DO
  NOT TOUCH W704). The old W604/W306 packets are OBSOLETE (merged by the
  parallel lane) — never dispatch them.
  THIS lane's wave (disjoint from W704): W605 (M6 completion) + W802
  (Latency SLOs) + W804 (Product analytics) — all dependencies green.

Phases:
  A. poll LOGIN_READY 45s (12h deadline) — the watcher raises it only on a
     real non-guest JWT email.
  B. on login: settle 25s, purge the guest token cache, notify the operator,
     scan the chat list for existing wave-named sessions (double-booking
     guard — if one exists, watch it instead of dispatching).
  C. monitor: per-session marker poll via the chats HTTP rail (registry
     URL -> chat id; literal marker counted >=2 = prompt echo + answer)
     -> flags/<WID>_REPORT_READY; branch landing via git ls-remote
     (authenticated when PAT present, anonymous fallback) -> BRANCH flags
     + outbox (also watches the parallel lane's w704-live-playback for
     context only); heartbeat.
  D. PAT watch on the operator inbox (fallback path — the primary PAT is
     already in ~/.secrets/env.sh; watcher re-reads it every cycle).
  E. dispatch: when logged in AND PAT present AND the rendered packet
     exists AND no chat/branch/flag for the item -> sequential creates
     (W605 then W802 then W804; <=3 concurrent sessions, the site cap).
     rc=0 -> arm a queue_watch subprocess (the sanctioned two-state
     capacity guard) + outbox. rc=3 -> supervisor recover_capacity owns
     the retry; outbox. else -> outbox + retry next cycle (max 3 tries).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import chats_http

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = open(os.path.join(BASE, "logs", "wave_sentinel.log"), "a", buffering=1)
HB = os.path.join(FLAGS, "wave_sentinel_heartbeat")
INBOX = os.path.join(FLAGS, "operator_inbox.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
SECRETS = os.path.expanduser("~/.secrets/env.sh")
PROMPTS = os.path.join(BASE, "worker-prompts")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")

PY = sys.executable
LOGIN_FLAG = os.path.join(FLAGS, "LOGIN_READY")

WAVE = [
    {"wid": "W605", "name": "w605-3d-output-evaluation",
     "branch": "w605-3d-output-evaluation",
     "marker": "SPORTA-COMPLETION-REPORT W605 END",
     "template": "w605-3d-output-evaluation.template.md"},
    {"wid": "W802", "name": "w802-latency-slos",
     "branch": "w802-latency-slos",
     "marker": "SPORTA-COMPLETION-REPORT W802 END",
     "template": "w802-latency-slos.template.md"},
    {"wid": "W804", "name": "w804-product-analytics",
     "branch": "w804-product-analytics",
     "marker": "SPORTA-COMPLETION-REPORT W804 END",
     "template": "w804-product-analytics.template.md"},
]
CONTEXT_BRANCHES = ["w704-live-playback"]  # parallel lane's flight — notify only
MAX_TRIES = 3


def flag(p):
    return os.path.join(FLAGS, p)


def log(msg):
    LOG.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "from": "agent", "text": text}) + "\n")
        log(f"OUTBOX: {text[:140]}")
    except Exception as e:
        log(f"outbox error {e!r}")


def hb():
    try:
        with open(HB, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


# ---------------------------------------------------------------- PAT

PAT_RE = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})")


def get_pat():
    if not os.path.exists(SECRETS):
        return ""
    m = re.search(r"=(ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)", open(SECRETS).read())
    return m.group(1) if m else ""


def watch_inbox_for_pat():
    """Fallback PAT intake (console thread). Idempotent."""
    try:
        lines = open(INBOX).read().splitlines()
    except Exception:
        return
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = PAT_RE.search(str(d.get("text") or ""))
        if m and not get_pat():
            pat = m.group(1)
            os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
            with open(SECRETS, "w") as f:
                f.write(f"# reconstituted from operator console message "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} UTC\nPAYSWAP_PAT={pat}\nGITHUB_TOKEN={pat}\n")
            os.chmod(SECRETS, 0o600)
            outbox("PAT received via console thread and stored (mode 600).")
            return


# ---------------------------------------------------------------- chats rail

def list_chats(limit=100):
    try:
        data = chats_http.api(f"/api/v1/chats/list?limit={limit}")
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("items", [])
        return items or []
    except Exception as e:
        log(f"chats list error {e!r}")
        return []


def chat_detail(cid):
    try:
        data = chats_http.api(f"/api/v1/chats/{cid}")
        rec = data.get("data", data) if isinstance(data, dict) else {}
        inner = rec.get("chat", {}) or {}
        msgs = inner.get("history", {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        return msgs
    except Exception as e:
        log(f"chat detail {str(cid)[:8]} error {e!r}")
        return None


def marker_state(cid, marker):
    """'completed' when marker counted >=2 (prompt echo + assistant answer)."""
    msgs = chat_detail(cid)
    if msgs is None:
        return "unknown"
    hits = 0
    for m in msgs:
        c = m.get("content") if isinstance(m.get("content"), str) else ""
        if marker in c:
            hits += 1
    return "completed" if hits >= 2 else "pending"


def registry_chat_id(name):
    """Latest sent=True registry record for <name> -> chat id from its URL."""
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except Exception:
        return None
    best = None
    for r in recs:
        if r.get("name") == name and r.get("sent"):
            m = re.search(r"/c/([0-9a-f-]+)", r.get("url") or "")
            if m:
                best = m.group(1)
    return best


def find_chat_by_name(name):
    """Chat-list lookup by title keyword (titles appear after turn 1)."""
    key = name.split("-", 1)[1][:12].replace("-", " ")
    for it in list_chats(100):
        title = (it.get("title") or "").lower()
        if name in title or (key and key in title):
            return it.get("id")
    return None


# ---------------------------------------------------------------- branch rail

def remote_branches():
    pat = get_pat()
    if pat:
        try:
            r = subprocess.run(
                ["git", "ls-remote", "--heads",
                 f"https://{pat}@github.com/payswapdotorg/sporta"],
                capture_output=True, text=True, timeout=30)
        except Exception:
            r = None
    else:
        r = None
    if not r or r.returncode != 0:
        try:
            r = subprocess.run(
                ["git", "ls-remote", "--heads", "https://github.com/payswapdotorg/sporta"],
                capture_output=True, text=True, timeout=30)
        except Exception:
            return {}
    out = {}
    for line in (r.stdout or "").splitlines():
        if "\t" in line:
            sha, ref = line.split("\t", 1)
            out[ref.replace("refs/heads/", "")] = sha[:10]
    return out


# ---------------------------------------------------------------- dispatch

def render_packet(template):
    pat = get_pat()
    if not pat:
        return None
    src = os.path.join(PROMPTS, template)
    if not os.path.exists(src):
        return None
    dst = src.replace(".template.md", ".md")
    s = open(src).read()
    if "__PAT__" not in s:
        log(f"template {template} has no __PAT__ placeholder")
        return None
    with open(dst, "w") as f:
        f.write(s.replace("__PAT__", pat))
    os.chmod(dst, 0o600)
    return dst


def dispatch(name, prompt_file):
    try:
        r = subprocess.run(
            [PY, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt_file],
            capture_output=True, text=True, timeout=3600)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
        log(f"dispatch {name} rc={rc} tail={out[-400:]}")
        return rc, out
    except Exception as e:
        log(f"dispatch {name} error {e!r}")
        return -1, repr(e)


def arm_queue_watch(name, marker):
    tab_id = None
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
        for r in recs:
            if r.get("name") == name and r.get("tab_id"):
                tab_id = r["tab_id"]
    except Exception:
        pass
    if not tab_id:
        log(f"no tab_id for {name} — queue_watch not armed (HTTP poll covers it)")
        return False
    try:
        subprocess.Popen(
            [PY, os.path.join(BASE, "queue_watch.py"), name, tab_id, marker],
            stdout=open(os.path.join(BASE, "logs", f"queue_watch.{name}.log"), "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True, cwd=BASE)
        log(f"queue_watch armed for {name} (tab {tab_id[:8]})")
        return True
    except Exception as e:
        log(f"queue_watch arm error {e!r}")
        return False


# ---------------------------------------------------------------- phases

def assess_on_login():
    log("LOGIN detected — settling 25s")
    time.sleep(25)
    try:
        os.remove(os.path.join(FLAGS, "chat_token"))
    except Exception:
        pass
    # double-booking guard: existing wave-named chats?
    found = []
    for w in WAVE:
        cid = find_chat_by_name(w["name"])
        if cid:
            w["chat"] = cid
            found.append(w["name"])
            open(flag(f"WAVE_CHAT_{w['wid']}"), "w").write(cid)
    outbox("Login detected. Remote truth: W306+W604 were completed and merged "
           "by the parallel lane while this console was down (main 706ba9f, "
           "M4 gate 6/6); the parallel lane is currently in flight on W704. "
           "This lane's wave: W605 (3D output evaluation) + W802 (Latency "
           "SLOs) + W804 (Product analytics) — dispatching now as watchable "
           "agents-tab sessions."
           + (f" NOTE: existing chats found for {found} — watching those "
              "instead of re-dispatching." if found else ""))
    open(flag("WAVE_LOGIN_ASSESSED"), "w").write(time.strftime("%H:%M:%S"))


def try_dispatch_wave():
    if not (os.path.exists(LOGIN_FLAG) and get_pat()):
        return
    brs = remote_branches()
    for w in WAVE:
        wid, name = w["wid"], w["name"]
        if os.path.exists(flag(f"WAVE_DISPATCHED_{wid}")):
            continue
        if os.path.exists(flag(f"WAVE_CHAT_{wid}")):
            continue  # existing chat — watching, not dispatching
        if w["branch"] in brs:
            open(flag(f"WAVE_DISPATCHED_{wid}"), "w").write("branch-already-landed")
            continue  # delivered without us — verify, don't dispatch
        tries = 0
        try:
            tries = int(open(flag(f"WAVE_TRIES_{wid}")).read().strip() or "0")
        except Exception:
            pass
        if tries >= MAX_TRIES:
            continue
        packet = render_packet(w["template"])
        if not packet:
            log(f"{wid}: packet not ready (template missing?) — retry next cycle")
            return
        outbox(f"Dispatching {wid} ({name}, watchable agents-tab session)…")
        rc, _ = dispatch(name, packet)
        open(flag(f"WAVE_TRIES_{wid}"), "w").write(str(tries + 1))
        if rc == 0:
            open(flag(f"WAVE_DISPATCHED_{wid}"), "w").write(time.strftime("%H:%M:%S"))
            outbox(f"{wid} dispatched VERIFIED — watch it live in the agents "
                   "tab. I am polling its completion marker + branch push; "
                   "TL verification follows on delivery.")
            arm_queue_watch(name, w["marker"])
        elif rc == 3:
            open(flag(f"WAVE_DISPATCHED_{wid}"), "w").write("capacity-supervisor")
            outbox(f"{wid} hit the capacity wall — the supervisor's "
                   "recover_capacity machinery owns the retry assault "
                   "(automatic; nothing needed from you).")
            arm_queue_watch(name, w["marker"])
        elif rc == 1:
            # already live (someone dispatched it) — watch, don't retry
            open(flag(f"WAVE_DISPATCHED_{wid}"), "w").write("already-live")
            outbox(f"{wid}: dispatcher reports the session already exists — "
                   "watching it instead of re-dispatching.")
        else:
            outbox(f"{wid} dispatch rc={rc} — will retry (try {tries + 1}/{MAX_TRIES}).")


def check_markers_and_branches():
    brs = remote_branches()
    for w in WAVE:
        wid, name, marker = w["wid"], w["name"], w["marker"]
        # marker
        if not os.path.exists(flag(f"{wid}_REPORT_READY")):
            cid = w.get("chat") or registry_chat_id(name) or find_chat_by_name(name)
            if cid:
                w["chat"] = cid
                st = marker_state(cid, marker)
                if st == "completed":
                    open(flag(f"{wid}_REPORT_READY"), "w").write(time.strftime("%H:%M:%S"))
                    outbox(f"{wid} REPORT READY — completion marker landed in "
                           f"chat {str(cid)[:8]}. TL verification next: fresh-fetch "
                           "guard, full battery, review vs the packet, merge.")
        # branch
        if w["branch"] in brs and not os.path.exists(flag(f"BRANCH_w_{wid}")):
            open(flag(f"BRANCH_w_{wid}"), "w").write(brs[w["branch"]])
            outbox(f"{wid} BRANCH LANDED: {w['branch']} @ {brs[w['branch']]} — "
                   "the worker delivered. TL: verify + merge.")
    # context branches (parallel lane) — notification only
    for b in CONTEXT_BRANCHES:
        if b in brs and not os.path.exists(flag(f"CONTEXT_BRANCH_{b.replace('-', '_')}")):
            open(flag(f"CONTEXT_BRANCH_{b.replace('-', '_')}"), "w").write(brs[b])
            outbox(f"Context: the parallel lane's {b} moved to @ {brs[b]}.")


def main():
    log("wave_sentinel online (S122 wave: W605 + W802 + W804; W704 = parallel lane)")
    outbox("Wave sentinel armed: on your login I dispatch W605 + W802 + W804 "
           "(watchable agents-tab sessions) and monitor markers + branches. "
           "W704 stays with the parallel lane.")
    deadline = time.time() + 12 * 3600
    assessed = os.path.exists(flag("WAVE_LOGIN_ASSESSED"))
    while time.time() < deadline:
        hb()
        try:
            if not assessed and os.path.exists(LOGIN_FLAG):
                assess_on_login()
                assessed = True
            if assessed:
                try_dispatch_wave()
                check_markers_and_branches()
            watch_inbox_for_pat()
        except Exception as e:
            log(f"loop error {e!r}")
        time.sleep(60 if assessed else 45)
    log("12h deadline — standing down")


if __name__ == "__main__":
    main()
