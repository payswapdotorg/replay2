#!/usr/bin/env python3
"""wave3_revival.py — sole dispatcher + liveness monitor for the TL2 wave-3
lanes (F1/F2/F3/F4).

Evening-peak lesson (2026-09-28 12:xx UTC, Beijing ~20:xx): with the
sandbox/generation concurrency saturated, creates still land their prompts
(sent:true, full WO in the server tree) but the task never provisions a pod
and never generates — 'admitted-but-not-generating'. A dead-admitted chat
never renders its thread: the /c/<id> URL bounces back to the landing page.
F1 proved the cure: a fresh create with a free slot provisions + generates
within ~3 minutes (chat 3b16f356: workspace live, assistant turn, title).

This daemon owns ALL wave-3 dispatch sequencing (the login sentinel exited
after the initial creates; the completion watcher only detects markers and
harvests). Cycle (120s):

  1. Liveness per dispatched+unharvested lane:
     - LIVE  = workspace exists for its chat OR an assistant turn is on
               record server-side
     - DEAD-admitted = age > DEAD_MIN, no workspace, user-only roles, and
               the chat URL bounces (thread never rendered)
     - TURN-DEAD = workspace exists but chat DOM chars frozen > FREEZE_MIN
               mid-thread (chars > 3000, no marker yet) — zombie cure:
               void + fresh chat, never fight it
  2. While NO lane is LIVE: revive the first DEAD unharvested lane (void +
     fresh create + state update), else first-dispatch the next
     undispatched lane — in F1 < F2 < F3 < F4 order.
  3. While a lane IS LIVE: every PROBE_MIN, one parallel-probe create of
     the next queued lane; alive within PROBE_SETTLE => cap lifted, let it
     run; else void + back off (peak litter is cheap; voids keep the
     registry straight).

State: flags/wave3_lanes.json under flock (the watcher uses the same lock
and re-reads before writing)."""
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "wave3_revival.log")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE = os.path.join(FLAGS, "wave3_lanes.json")
STATE_LOCK = os.path.join(FLAGS, "wave3_lanes.lock")
REG = os.path.join(FLAGS, "session_registry.jsonl")
PY = "/home/z/.venv/bin/python3"
TOK_FILE = os.path.join(FLAGS, "chat_token")

CADENCE = 120
DEAD_MIN = 15 * 60        # seconds post-dispatch before dead-admission call
NO_TURN_MIN = 30 * 60     # workspace provisioned but assistant turn never
                         # fired => turn-death zombie (2026-09-28 evening
                         # class: pods provision under the generation-
                         # dispatch outage, roles=[user] only, no title,
                         # thread-bounce DOM; per-chat send gate law =
                         # fresh-chat cure, never fight the zombie)
FREEZE_MIN = 25 * 60      # seconds of frozen mid-thread chars => turn-death
PROBE_MIN = 30 * 60       # seconds between parallel probes
LANE_ORDER = ["flauz-F1-tl2", "flauz-F2-tl2", "flauz-F3-tl2", "flauz-F4-tl2"]


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------- state (flock) --

def _locked(fn):
    os.makedirs(FLAGS, exist_ok=True)
    lk = open(STATE_LOCK, "w")
    fcntl.flock(lk, fcntl.LOCK_EX)
    try:
        return fn()
    finally:
        fcntl.flock(lk, fcntl.LOCK_UN)
        lk.close()


def read_lanes():
    def rd():
        if os.path.exists(STATE):
            try:
                with open(STATE) as f:
                    return json.load(f).get("lanes", [])
            except Exception:
                return []
        return []
    return _locked(rd)


def update_lane(name, **fields):
    def wr():
        lanes = []
        if os.path.exists(STATE):
            try:
                with open(STATE) as f:
                    lanes = json.load(f).get("lanes", [])
            except Exception:
                lanes = []
        for l in lanes:
            if l.get("name") == name:
                l.update(fields)
                break
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"lanes": lanes}, f, indent=1)
        os.replace(tmp, STATE)
        return lanes
    return _locked(wr)


def lane_by_name(lanes, name):
    for l in lanes:
        if l.get("name") == name:
            return l
    return None


# ------------------------------------------------------------- API helpers --

def _tok():
    try:
        return open(TOK_FILE).read().strip()
    except OSError:
        return ""


def _get(url, tries=3):
    tok = _tok()
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(5)
    return None


def workspaces_map():
    data = _get("https://chat.z.ai/api/v1/web-dev/workspaces/user-fc")
    out = {}
    if isinstance(data, dict):
        for w in (data.get("workspaces") or []):
            cid = str(w.get("chat_id") or "").removeprefix("chat-")
            if cid:
                out[cid] = w.get("function_name") or ""
    return out


def has_assistant_turn(cid):
    d = _get(f"https://chat.z.ai/api/v1/chats/{cid}")
    if not d:
        return None  # unknown (API flaky)
    msgs = ((d.get("chat") or {}).get("history") or {}).get("messages") or {}
    return any(m.get("role") == "assistant" for m in msgs.values())


def dom_read(cid, settle_rounds=4):
    """Fresh-tab read: (chars, rendered) — rendered False = bounced home."""
    t = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    if t is None:
        return None, False
    best = ""
    rendered = False
    try:
        c = CDP(t["webSocketDebuggerUrl"], timeout=40)
        try:
            for _ in range(settle_rounds):
                time.sleep(4)
                body = c.eval("document.body.innerText || ''", timeout=25) or ""
                if len(body) > len(best):
                    best = body
            url = c.eval("location.href", timeout=10) or ""
            rendered = cid in url
        finally:
            c.close()
    except Exception as e:
        log(f"  dom_read({cid[:8]}) error: {e}")
    finally:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{t['id']}", timeout=5).read()
        except Exception:
            pass
    return len(best), rendered


# ------------------------------------------------------------ dispatch steps --

def void_lane(name, reason, chat_id=None):
    try:
        r = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                            "void", name, reason],
                           capture_output=True, text=True, timeout=150)
        log(f"  [{name}] void rc={r.returncode}: {(r.stdout or '').strip()[:70]}")
    except Exception as e:
        log(f"  [{name}] void error: {e}")
    # 2026-09-28 law: a voided lane's POD must be released or the sandbox
    # cap re-fills with dead rows (root cause of the 16:10-18:10 streak).
    # DELETE /api/v1/web-dev/workspaces/{chat_id} with the cached JWT.
    cid = chat_id
    if not cid:
        try:
            for l in read_lanes():
                if l.get("name") == name:
                    cid = l.get("chat")
                    break
        except Exception:
            pass
    if cid:
        try:
            tok = _tok()
            if tok:
                req = urllib.request.Request(
                    f"https://chat.z.ai/api/v1/web-dev/workspaces/{cid}",
                    method="DELETE",
                    headers={"Authorization": f"Bearer {tok}",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    log(f"  [{name}] pod released ({cid[:8]}): "
                        f"{r.read().decode()[:80]}")
        except Exception as e:
            log(f"  [{name}] pod release err: {e}")


def _latest_sent_record(name):
    rec = None
    try:
        with open(REG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("name") == name:
                    if d.get("action") in ("void", "failed", "done"):
                        rec = None
                    elif d.get("sent"):
                        rec = d
    except OSError:
        return None
    return rec


def create_lane(name, prompt_rel):
    """Detached create; poll the registry for the new sent record."""
    logp = os.path.join(BASE, "logs", f"create_{name}.log")
    subprocess.Popen([PY, os.path.join(BASE, "launch_create.py"), name,
                      os.path.join(BASE, prompt_rel)],
                     stdout=open(logp, "a"), stderr=subprocess.STDOUT,
                     start_new_session=True, cwd=BASE)
    deadline = time.time() + 420
    while time.time() < deadline:
        time.sleep(15)
        rec = _latest_sent_record(name)
        if rec:
            m = re.search(r"/c/([0-9a-f-]{16,})", rec.get("url") or "")
            if m:
                return m.group(1)
    return None


def dispatch_or_revive(name, prompt_rel, old_chat, revive, probe=False):
    if revive and old_chat:
        void_lane(name, "revival: dead-admitted/turn-dead "
                        f"(old chat {old_chat[:8]}); fresh-chat doctrine")
    cid = create_lane(name, prompt_rel)
    if not cid:
        log(f"  [{name}] create did not land a sent record; retry next cycle")
        return None
    update_lane(name, chat=cid, dispatched=True, created_at=int(time.time()),
                last_chars=None, chars_frozen_since=0)
    tag = "probe-dispatched" if probe else ("revived" if revive else "dispatched")
    log(f"  [{name}] {tag} chat={cid}")
    outbox(f"[TL2 wave3] {name} {tag} — chat {cid[:8]}.")
    return cid


# ------------------------------------------------------------------- cycle --

def assess(lanes):
    """name -> {live: True/False/None, reason}."""
    wsmap = workspaces_map()
    st = {}
    for l in lanes:
        name, cid = l.get("name"), l.get("chat")
        if not cid or l.get("harvested"):
            continue
        if wsmap.get(cid):
            # provisioned — but is the turn alive? A pod with no assistant
            # turn is a turn-death zombie (send gate law: fresh-chat cure).
            turn = has_assistant_turn(cid)
            age = time.time() - (l.get("created_at") or 0)
            if turn is True:
                st[name] = {"live": True, "reason": "workspace+turn"}
            elif turn is None:
                st[name] = {"live": True, "reason": "ws (turn unknown)"}
            elif age > NO_TURN_MIN:
                st[name] = {"live": False,
                            "reason": "provisioned-not-generating "
                                      f"(ws, no turn, {int(age / 60)}m)"}
            else:
                st[name] = {"live": True,
                            "reason": f"ws provisioned, turn pending {int(age / 60)}m"}
            continue
        turn = has_assistant_turn(cid)
        if turn is True:
            st[name] = {"live": True, "reason": "assistant-turn"}
            continue
        if turn is None:
            st[name] = {"live": None, "reason": "api-unknown"}
            continue
        age = time.time() - (l.get("created_at") or 0)
        if age < DEAD_MIN:
            st[name] = {"live": None, "reason": "young"}
            continue
        chars, rendered = dom_read(cid)
        if rendered and (chars or 0) > 3000:
            st[name] = {"live": True, "reason": "thread-rendered"}
        else:
            st[name] = {"live": False,
                        "reason": "dead-admitted (no ws, no turn, bounced)"}
    return st


def freeze_check(lanes, st):
    """Turn-death guard for LIVE lanes: frozen DOM chars => mark dead."""
    for l in lanes:
        name, cid = l.get("name"), l.get("chat")
        s = st.get(name)
        if not cid or l.get("harvested") or not s or s.get("live") is not True:
            continue
        chars, _ = dom_read(cid, settle_rounds=3)
        if chars is None:
            continue
        prev = l.get("last_chars")
        frozen_since = l.get("chars_frozen_since") or 0
        if chars == prev and (chars or 0) > 3000:
            if not frozen_since:
                update_lane(name, last_chars=chars, chars_frozen_since=time.time())
                continue
            if time.time() - frozen_since > FREEZE_MIN:
                log(f"[{name}] TURN-DEAD: chars frozen "
                    f"{int((time.time() - frozen_since) / 60)}m at {chars}")
                st[name] = {"live": False, "reason": "turn-death (frozen DOM)"}
        else:
            update_lane(name, last_chars=chars, chars_frozen_since=0)
    return st


def main():
    log("=== wave3_revival start (serial dispatch + dead-admission revival)")
    outbox("[TL2 wave3] revival daemon armed: dead-admitted chats are voided "
           "and re-created as slots free (evening-peak economics); turn-death "
           "guard active; F4 dispatches in lane order.")
    last_probe = 0.0
    while True:
        try:
            lanes = read_lanes()
            if not lanes:
                time.sleep(CADENCE)
                continue
            st = assess(lanes)
            st = freeze_check(lanes, st)
            lanes = read_lanes()  # refresh after freeze_check writes

            live = [n for n, s in st.items() if s.get("live") is True]
            dead = [n for n, s in st.items() if s.get("live") is False]

            if live:
                if time.time() - last_probe > PROBE_MIN:
                    queued = ([l for l in lanes if not l.get("harvested")
                               and l.get("name") in dead]
                              + [l for l in lanes
                                 if not l.get("chat")
                                 and not l.get("harvested")])
                    if queued:
                        cand = min(queued, key=lambda l: LANE_ORDER.index(l["name"]))
                        log(f"[probe] cap probe alongside {live}: "
                            f"creating {cand['name']}")
                        last_probe = time.time()
                        # lesson 2026-09-28: void-first when the candidate
                        # holds an old chat — otherwise the registry's stale
                        # sent record turns the probe into a no-op that
                        # "re-dispatches" onto the zombie chat id.
                        dispatch_or_revive(cand["name"], cand["prompt"],
                                           cand.get("chat"),
                                           revive=bool(cand.get("chat")),
                                           probe=True)
                time.sleep(CADENCE)
                continue

            # no lane live: serial dispatch in lane order
            queued = ([l for l in lanes if not l.get("harvested")
                       and l.get("name") in dead]
                      + [l for l in lanes
                         if not l.get("chat")
                         and not l.get("harvested")])
            if queued:
                cand = min(queued, key=lambda l: LANE_ORDER.index(l["name"]))
                revive = bool(cand.get("chat"))
                log(f"[dispatch] next lane {cand['name']} "
                    f"({'revive' if revive else 'first dispatch'})")
                dispatch_or_revive(cand["name"], cand["prompt"],
                                   cand.get("chat"), revive=revive)
            elif all(s.get("live") is None for s in st.values()) and st:
                pass  # API unknown across the board — wait for clarity
            else:
                done = [l for l in lanes if l.get("harvested")]
                if lanes and len(done) >= len(lanes):
                    log("=== all wave-3 lanes harvested; revival exits")
                    outbox("[TL2 wave3] all lanes harvested — revival stands down.")
                    return
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(CADENCE)


if __name__ == "__main__":
    main()
