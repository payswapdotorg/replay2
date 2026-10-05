#!/usr/bin/env python3
"""drought_sentinel.py — 24/7 admission-drought sentinel + auto D-028
recovery (rebuilt 2026-10-03 after reset-4 rolled the tree back; faithful
reconstruction of the pre-reset D-036 sentinel from its logs, state files
and verbatim recover() core).

Generations:
- D-028 (2026-10-02): one-shot sentinel, hardcoded wave-28 lanes.
- D-031..33: env law (load_env before dispatch children), packet
  resolution order (_staged > _redispatch > raw, __DISPATCH_BASE__ guard),
  dynamic lane set (flags/lane_list.txt).
- D-036 (2026-10-03): STANDING sentinel — after a recovery it keeps
  running (mode=post-recovery) and watches for relapse: when all lanes
  stay queued longer than POST_STALE (7200s past the newest dispatch ts),
  drought mode resumes (outage_hold re-set per doctrine) and rolling
  canaries (20-min cadence, max 2 live, TTL 1800s unadmitted) detect the
  next break, when recover() fires again. recoveries counter increments.

State: flags/drought_fresh_probes.json (survives sentinel restarts):
  {"next_probe": N, "probes": {"PROBEN": {"cid":..., "ts":...}},
   "last_launch": epoch, "mode": "drought"|"post-recovery",
   "recoveries": N, "dead": {lane: consecutive_probe_failures}}

Lanes: flags/lane_list.txt (one TXXX per line). Chat ids resolve from
flags/session_registry.jsonl (latest non-void row per name) — the registry
and packets are the truth, never the wedge-prone DOM.

TRIGGER (recover): any fresh canary msgs>=2 (admitted) OR any lane
batch_msgs>0 (generating). Safe pre-login: failed probes read as dead and
are tolerated; canary launches fail-harmless until the browser is
authenticated.

Launch: dfork_launch.py /tmp/drought_sentinel.log <py> drought_sentinel.py
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
PY = sys.executable

POLL = 120            # s between cycles
CANARY_EVERY = 1200   # s between canary launches (20 min)
CANARY_TTL = 1800     # s before an unadmitted canary is retired
MAX_LIVE_PROBES = 2   # concurrent live canaries
POST_STALE = 7200     # s of all-queued (past newest dispatch) => relapse
GRACE = 90            # s between break detection and lane surgery

# The Lead maintains flags/lane_list.txt (one lane name per line); the
# fallback below is the CURRENT wave (D-033: lanes change per wave — never
# hardcode a previous wave's set as the fallback).
_LANE_FILE = os.path.join(FLAGS, "lane_list.txt")
_FALLBACK_LANES = ["T035", "T042", "T048"]

# Worker-era lane names (lab006, mkt073r5, studio009, unicom-w1-003 ...) sit
# alongside legacy T### names; accept both wherever a lane name is parsed.
LANE_RE = re.compile(r"T\d{3}|[a-z][a-z0-9-]{2,30}")

REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
HB = os.path.join(FLAGS, "drought_sentinel_hb.txt")
VERDICT = os.path.join(FLAGS, "drought_sentinel_verdict.json")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
HOLD = os.path.join(FLAGS, "outage_hold.txt")
FRESH_STATE = os.path.join(FLAGS, "drought_fresh_probes.json")
CANARY_PROMPT = os.path.join(FLAGS, "canary_prompt.md")
ENV_SH = os.path.join(BASE, "env.sh")
REPLAY_STATE = "/home/z/my-project/replay-state"

_CANARY_TEXT = (
    "Reply with the single word OK and nothing else. This is an "
    "admission-liveness canary probe from the replay orchestrator; no "
    "work, no tools, no report.")


def log(msg):
    print(f"[drought_sentinel {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env():
    """Source scripts/env.sh vars into os.environ (for _subst_pat children)."""
    try:
        for line in open(ENV_SH):
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                k, v = line[7:].split("=", 1)
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()
    except OSError:
        pass


def outbox(action, text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time()), "action": action, "text": text})
                + "\n")
    except OSError:
        pass


def lane_names():
    try:
        names = [l.strip() for l in open(_LANE_FILE)
                 if LANE_RE.fullmatch(l.strip())]
        if names:
            return names
    except OSError:
        pass
    return list(_FALLBACK_LANES)


def lane_sessions():
    """Latest live dispatch per lane name from the registry.
    Returns {name: (chat_id, ts)}. Void/failed/done rows close a lane;
    a later fresh dispatch row re-opens it. Registry = truth."""
    out = {}
    try:
        rows = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except (OSError, ValueError):
        return out
    for r in rows:
        name = r.get("name", "")
        if LANE_RE.fullmatch(name):
            if r.get("action") in ("void", "failed", "done"):
                continue
            url = r.get("url") or ""
            m = re.search(r"/c/([0-9a-f-]{36})", url)
            if m:
                out[name] = (m.group(1), int(r.get("ts") or 0))  # LAST wins
    # only CURRENT lanes (D-033): stale waves' registry rows never leak in
    keep = set(lane_names())
    return {n: v for n, v in out.items() if n in keep}


def probe(cid):
    """Server-side probe via probe_chat.py; None on any failure. An error
    JSON (http-403/no-tab/guest) reads as DEAD — never as queued."""
    try:
        out = subprocess.run(
            [PY, os.path.join(BASE, "probe_chat.py"), cid],
            capture_output=True, text=True, timeout=45).stdout.strip()
        d = json.loads(out)
        if d.get("err") or not d.get("alive"):
            return None
        return {"msgs": d.get("msgs", 0),
                "batch_msgs": (d.get("batch") or {}).get("msgs", 0),
                "alive": bool(d.get("alive"))}
    except Exception:
        return None


def read_state():
    try:
        return json.load(open(FRESH_STATE))
    except (OSError, ValueError):
        return {"next_probe": 1, "probes": {}, "last_launch": 0.0,
                "mode": "drought", "recoveries": 0, "dead": {}}


def write_state(st):
    try:
        with open(FRESH_STATE, "w") as f:
            json.dump(st, f, indent=1)
    except OSError:
        pass
    try:  # mirror to the persistent payload (reset-proofing)
        import shutil
        shutil.copy(FRESH_STATE, os.path.join(
            REPLAY_STATE, "drought_fresh_probes.json"))
    except Exception:
        pass


def _state_char(s):
    if s is None:
        return "x"
    if s["batch_msgs"] > 0:
        return "g"
    if s["msgs"] >= 2:
        return "a"
    return "q"


def launch_canary(n):
    """Fresh canary via the composer path (dispatch_worker create)."""
    try:
        if not os.path.exists(CANARY_PROMPT):
            with open(CANARY_PROMPT, "w") as f:
                f.write(_CANARY_TEXT + "\n")
        # 2026-10-03 (reset-4 fix): a stale registry row for this probe name
        # (pre-reset canary, never admitted, re-added by the registry
        # rebuild) blocks create() with "already exists" forever — void it
        # and retry once. The sentinel's fresh-probe state starts empty
        # after a reset, so rows for the name are stale by construction.
        for _attempt in (1, 2):
            r = subprocess.run(
                [PY, os.path.join(BASE, "dispatch_worker.py"),
                 "create", f"PROBE{n}", CANARY_PROMPT],
                capture_output=True, text=True, timeout=420, cwd=BASE)
            m = re.search(r"/c/([0-9a-f-]{36})", r.stdout or "")
            if not m:
                # 2026-10-03 (new-frontend fix): the prod-fe-1.1.98 send path
                # prints "prompt sent: VERIFIED" WITHOUT a /c/ URL line (the
                # URL-printing ACCEPTED branch is a different path) — the
                # registry row create() wrote is the source of truth.
                try:
                    reg = os.path.join(BASE, "flags", "session_registry.jsonl")
                    last_live = None
                    for line in open(reg, encoding="utf-8"):
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        if rec.get("name") == f"PROBE{n}" and rec.get("url") and not rec.get("action"):
                            last_live = rec  # last non-void row wins
                    if last_live:
                        m = re.search(r"/c/([0-9a-f-]{36})", last_live["url"])
                except Exception:
                    pass
            if m:
                log(f"PROBE{n} dispatched -> {m.group(1)[:8]} (queued; watching)")
                return m.group(1)
            if "already exists" in (r.stdout or ""):
                log(f"PROBE{n} blocked by a stale registry row — voiding + retry")
                subprocess.run(
                    [PY, os.path.join(BASE, "dispatch_worker.py"), "void", f"PROBE{n}",
                     "stale pre-reset canary row (drought sentinel relaunch, reset-4)"],
                    capture_output=True, text=True, timeout=120, cwd=BASE)
                continue
            log(f"PROBE{n} launch FAILED (pre-login or composer error): "
                + (r.stdout or "").strip()[-160:])
            return None
        log(f"PROBE{n} launch FAILED (stale row could not be voided)")
    except Exception as e:
        log(f"PROBE{n} launch error: {e}")
    return None


def _close_tabs_for_cid(cid):
    """2026-10-03 (tab-hygiene fix): a retired/dead canary's parked /c/ tab
    must not linger — 15+ orphan chat tabs accumulated over a day of rolling
    probes (the supervisor's tab GC never closes /c/ tabs by design, for
    lane sessions). Canary chats are disposable: close every tab whose URL
    carries this chat id. Never raises."""
    if not cid or len(cid) < 8:
        return
    try:
        import urllib.request
        tabs = json.load(urllib.request.urlopen(
            "http://127.0.0.1:9222/json", timeout=8))
        for t in tabs:
            u = t.get("url") or ""
            if u.startswith("https://chat.z.ai/c/") and cid[:13] in u:
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:9222/json/close/" + t["id"],
                        timeout=5).read()
                except Exception:
                    pass
    except Exception:
        pass


def recover(trigger, lanes, lane_now, probes_now):
    """D-028 auto-recovery. Lift hold -> 90s grace -> re-probe -> void +
    re-dispatch stale lanes from packets -> re-arm watchers -> retire
    canaries -> verdict -> post-recovery mode (sentinel keeps running)."""
    log(f"TRIGGER: {trigger} — 90s grace for lane admission window")
    time.sleep(GRACE)
    lanes = lane_sessions()
    lane_now = {n: probe(c) for n, (c, _ts) in lanes.items()}
    log("post-grace: " + json.dumps(
        {n: lane_now[n] for n in lane_now if lane_now[n]})[:400])

    events = []

    if os.path.exists(HOLD):
        os.remove(HOLD)
        events.append("outage_hold lifted")

    load_env()  # PAT env fresh for dispatch children

    for name in lane_names():
        if name not in lanes:
            events.append(f"{name}: no registry session — Lead review")
            log(f"{name} not resolvable in registry — skipping")
            continue
        c_state = lane_now.get(name)
        if c_state and c_state["batch_msgs"] > 0:
            events.append(f"{name}: GENERATING — untouched")
            log(f"{name} generating — no re-dispatch")
            continue
        # D-033: packet resolution order — staged (resolved dispatch base,
        # most recent send) > redispatch (wave-28 form) > raw (must NOT carry
        # the __DISPATCH_BASE__ placeholder; a placeholder packet would
        # dispatch a broken base string to the worker).
        pkt = None
        for cand in (f"pkt_{name}_staged.md", f"pkt_{name}_redispatch.md",
                     f"pkt_{name}.md"):
            cp = os.path.join(FLAGS, cand)
            if os.path.exists(cp):
                try:
                    _t = open(cp, encoding="utf-8").read()
                except OSError:
                    continue
                if "__DISPATCH_BASE__" in _t:
                    continue  # unresolved placeholder — unusable
                pkt = cp
                break
        if not pkt:
            events.append(f"{name}: packet missing — Lead review")
            log(f"{name} packet MISSING — skipping")
            continue
        # void (registry) even if the chat is dead/corrupted — packets rule
        # 2026-10-05 R19 crash fix: an admission-surgery subprocess timeout
        # must never kill the sentinel — the mkt073r5 create hit 420s during
        # the first live admission window and the uncaught TimeoutExpired
        # took the whole daemon down mid-pass (studio009 never refreshed,
        # canary assault dead until manual restart). Per-lane guard + continue.
        try:
            r1 = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                                 "void", name,
                                 "drought-break stale-queue re-dispatch per D-028 "
                                 "(queued 16h+, never admitted; fresh canary "
                                 "proves admission works again)"],
                                capture_output=True, text=True, timeout=120,
                                cwd=BASE)
            log(f"{name} void rc={r1.returncode}")
            r2 = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                                 "create", name, pkt],
                                capture_output=True, text=True, timeout=420,
                                cwd=BASE)
        except subprocess.TimeoutExpired as te:
            events.append(f"{name}: surgery TIMEOUT "
                          f"({'create' if 'create' in str(te.cmd) else 'void'}) "
                          "— landing unverified, next cycle re-checks")
            log(f"{name} surgery TIMEOUT — continuing (create may have landed)")
            continue
        sent_ok = "VERIFIED" in r2.stdout
        events.append(f"{name}: voided + re-dispatched "
                      f"(sent={'VERIFIED' if sent_ok else 'CHECK ' + r2.stdout[-150:]})")
        log(f"{name} re-dispatch rc={r2.returncode} verified={sent_ok}")
        if sent_ok:
            # kill any stale watcher for this lane + drop its spec (the
            # supervisor resurrects from spec files), then arm a fresh one
            subprocess.run(["pkill", "-f", f"queue_watch.py {name} "],
                           capture_output=True)
            try:
                os.remove(os.path.join(FLAGS, f"queue_watch.spec.{name}"))
            except OSError:
                pass
            time.sleep(2)
            subprocess.Popen([PY, os.path.join(BASE, "launch_queue_watch.py"),
                              name, "00000000", "COMPLETION REPORT"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True, cwd=BASE)
            events.append(f"{name}: queue_watch re-armed")

    # retire the live canaries (diagnostic complete)
    for pname, pd in list(probes_now.items()):
        subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                        "void", pname,
                        "drought broken (canary) — diagnostic complete"],
                       capture_output=True, text=True, timeout=120, cwd=BASE)
        events.append(f"canary {pname} retired")

    verdict = {"ts": int(time.time()), "trigger": trigger,
               "fresh": {p: s for p, s in probes_now.items() if s},
               "lanes": {n: lane_now.get(n) for n in lanes},
               "events": events}
    try:
        with open(VERDICT, "w") as f:
            json.dump(verdict, f, indent=2)
    except OSError:
        pass
    outbox("drought_sentinel",
           "DROUGHT BROKEN — auto-recovery executed: " + "; ".join(events))

    st = read_state()
    st["recoveries"] = int(st.get("recoveries", 0)) + 1
    st["mode"] = "post-recovery"
    st["probes"] = {}
    st["dead"] = {}
    write_state(st)
    log(f"verdict written — recovery #{st['recoveries']} complete; "
        "post-recovery watch continues")


def main():
    load_env()
    st = read_state()
    log(f"armed — mode={st.get('mode', 'drought')} lanes={lane_names()} "
        f"recoveries={st.get('recoveries', 0)} poll={POLL}s")

    while True:
        try:
            open(HB, "w").write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except OSError:
            pass

        lanes = lane_sessions()
        lane_now = {n: probe(c) for n, (c, _ts) in lanes.items()}
        probes_now = {}
        for pname, pd in list(st.get("probes", {}).items()):
            probes_now[pname] = probe(pd.get("cid", ""))
        log("cycle: " + " ".join(f"{n}={_state_char(s)}"
                                 for n, s in lane_now.items())
            + (" | probes: " + " ".join(f"{p}={_state_char(s)}"
                                        for p, s in probes_now.items())
               if probes_now else ""))

        # dead counters (informational + alarm)
        for n, s in lane_now.items():
            st.setdefault("dead", {})
            st["dead"][n] = 0 if s else st["dead"].get(n, 0) + 1
            if st["dead"][n] == 10:
                outbox("drought_sentinel",
                       f"lane {n} probe-dead for 10 consecutive cycles — "
                       "Lead review (chat dead or browser logged out?)")

        # TRIGGER: fresh canary admitted OR lane generating
        trigger = None
        for pname, s in probes_now.items():
            if s and s["msgs"] >= 2:
                trigger = f"fresh-canary {pname}"
                break
        if trigger is None:
            for n, s in lane_now.items():
                if s and s["batch_msgs"] > 0:
                    trigger = f"lane-generating {n}"
                    break
        if trigger is not None:
            recover(trigger, lanes, lane_now, probes_now)
            st = read_state()
            continue

        now = time.time()
        if st.get("mode") == "drought":
            # retire TTL-expired unadmitted canaries
            for pname in list(st.get("probes", {})):
                if now - st["probes"][pname].get("ts", 0) > CANARY_TTL:
                    log(f"{pname} retired (TTL {CANARY_TTL}s unadmitted)")
                    _cid = st["probes"][pname].get("cid", "")
                    del st["probes"][pname]
                    _close_tabs_for_cid(_cid)
            # rolling launches
            if (now - st.get("last_launch", 0) >= CANARY_EVERY
                    and len(st.get("probes", {})) < MAX_LIVE_PROBES):
                log(f"launching fresh canary PROBE{st.get('next_probe', 1)} "
                    "(composer path)")
                cid = launch_canary(st.get("next_probe", 1))
                st["last_launch"] = now
                st["next_probe"] = int(st.get("next_probe", 1)) + 1
                if cid:
                    st.setdefault("probes", {})[f"PROBE{st['next_probe'] - 1}"] = {
                        "cid": cid, "ts": now}
                else:
                    # 2026-10-03 (peak-flakiness fix): transient composer
                    # failures (model menu race, missing skill chips, promo
                    # modal timing) should not burn a full 20-min cadence —
                    # retry after ~5 min. Bounded by MAX_LIVE_PROBES (only
                    # SUCCESSFUL launches enter the probe set), and the
                    # failure path is pre-send (no prompt spam server-side).
                    st["last_launch"] = now - CANARY_EVERY + 300
                    log(f"launch failed — fast retry in ~5min (peak-flakiness policy)")
        else:
            # post-recovery: relapse check (D-036). All lanes queued-alive
            # and POST_STALE past the newest dispatch ts => drought resumed.
            if lanes and lane_now:
                queued = all(
                    s is not None and s["batch_msgs"] == 0
                    for s in lane_now.values())
                max_ts = max(ts for (_c, ts) in lanes.values())
                if queued and now - max_ts > POST_STALE:
                    log("post-recovery lanes all queued > "
                        f"{POST_STALE}s — drought mode resumed")
                    st["mode"] = "drought"
                    # re-set the outage_hold per doctrine (suppress watcher
                    # send paths while lanes are queued-alive; read paths
                    # continue; canaries exempt; raw kicks forbidden F019)
                    if not os.path.exists(HOLD):
                        with open(HOLD, "w") as f:
                            f.write(time.strftime(
                                "%Y-%m-%d %H:%M:%S UTC — drought resumed "
                                "(sentinel D-036 relapse); watcher send "
                                "paths suppressed; lifted at recovery\n"))
                        try:
                            import shutil
                            shutil.copy(HOLD, os.path.join(
                                REPLAY_STATE, "outage_hold.txt"))
                        except Exception:
                            pass
                        outbox("drought_sentinel",
                               "drought relapse declared — outage_hold "
                               "re-set, canaries resume")
                    st["last_launch"] = 0  # launch a canary next cycle

        write_state(st)
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
