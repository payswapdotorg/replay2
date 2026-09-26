#!/usr/bin/env python3
"""
yt_gap_capture.py — the FOUR-GAP capture ladder (the R30-B pending surfaces).

The gaps (frozen never-build-from-memory law — capture or stay pending):
  g1 theme-picker submenu rows   (yesterday's miss: the click never opened the
                                  picker + the dump JS had a ReferenceError —
                                  BOTH fixed here: poll-for-open, self-
                                  contained JS, raw HTML slices, early shots)
  g2 healthy subs-feed grid      (yesterday: only the degraded live-only state)
  g3 home-surface resume bar     (yesterday: none rendered)
  g4 shorts action rail          (yesterday: gate-active, shell + Play CTA only)

Order = most interactive / gate-sensitive FIRST. No gate-fighting: ONE pass
per surface, honest records, incremental saves (json + jpg + html the moment
they land). Every eval is self-contained JS (the lesson: a template that
calls an undefined helper = ReferenceError = the truth lost).
"""
import json, time, base64, os, sys, re, traceback
import urllib.request
import websocket

CDP_HTTP = "http://localhost:9222"
STAMP = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
OUT = f"/home/z/webflix/docs/parity-lab/r30/gap-captures/{STAMP}"

# ---------- the proven CDP core (yt_corpus_capture lineage) ----------

def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)

def find_yt_ws():
    tabs = json.load(urllib.request.urlopen(CDP_HTTP + "/json/list", timeout=8))
    for t in tabs:
        if t.get("type") == "page" and "youtube.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"], t["url"], t["title"]
    raise SystemExit("NO YOUTUBE TAB — window lost?")

class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.nid = 0
    def send(self, method, params=None, timeout=25):
        self.nid += 1
        mid = self.nid
        self.ws.settimeout(timeout)
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.ws.settimeout(max(1.0, deadline - time.time()))
                raw = self.ws.recv()
            except Exception as e:
                raise TimeoutError(f"{method}: {e}")
            data = json.loads(raw)
            if data.get("id") == mid:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})
        raise TimeoutError(f"{method}: deadline")
    def eval(self, expr, timeout=25, retries=1):
        last = None
        for attempt in range(retries + 1):
            try:
                r = self.send("Runtime.evaluate",
                              {"expression": expr, "returnByValue": True, "awaitPromise": True},
                              timeout=timeout + attempt * 15)
                ed = r.get("exceptionDetails")
                if ed:
                    desc = ed.get("exception", {}).get("description", str(ed))[:300]
                    raise RuntimeError(f"eval exception: {desc}")
                return r.get("result", {}).get("value")
            except Exception as e:
                last = e
                log(f"  eval retry ({attempt+1}): {type(e).__name__}: {str(e)[:110]}")
        raise last
    def nav(self, url, settle=6.0):
        self.send("Page.navigate", {"url": url}, timeout=15)
        time.sleep(settle)
    def shot(self, name):
        r = self.send("Page.captureScreenshot", {"format": "jpeg", "quality": 88}, timeout=45)
        data = base64.b64decode(r["data"])
        with open(f"{OUT}/{name}.jpg", "wb") as f:
            f.write(data)
        return len(data)
    def save(self, name, obj):
        with open(f"{OUT}/{name}.json", "w") as f:
            json.dump(obj, f, indent=1, ensure_ascii=True)
    def save_html(self, name, html):
        if not html:
            return 0
        with open(f"{OUT}/{name}.html", "w") as f:
            f.write(html[:400_000])
        return min(len(html), 400_000)

# ---------- self-contained JS payloads (NO external helper refs) ----------

# r(x) inline definition, embedded in every payload that needs it
R_DEF = (
    "const r=(el)=>{if(!el)return null;const b=el.getBoundingClientRect();"
    "const cs=getComputedStyle(el);"
    "const cls=(el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'');"
    "return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),"
    "text:(el.textContent||'').trim().slice(0,160),cls:String(cls).slice(0,110),"
    "font:cs.fontSize+' '+cs.fontWeight,display:cs.display};};"
)

# generic overlay scan: the biggest visible absolutely/fixed-position papers
# (the account menu / theme picker render as these even when named selectors
# miss — yesterday's lesson: selectors matched 0 while the menu was VISIBLE)
OVERLAY_SCAN = "(() => {" + R_DEF + """
  const vis = (el) => { const b = el.getBoundingClientRect();
    return b.width > 150 && b.height > 80; };
  const cand = [...document.querySelectorAll(
    'ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, yt-system-data-renderer, '+
    '#theme-picker, #account-menu, ytd-popup-container > *, [role="menu"], '+
    'tp-yt-paper-dialog, yt-sheet-view-model, .yt-spec-bottom-sheet-modal')];
  const seen = new Set(); const out = [];
  for (const el of cand) {
    if (seen.has(el)) continue;
    cand.forEach(o => { if (o !== el && o.contains(el)) seen.add(el); });
    if (seen.has(el) || !vis(el)) continue;
    const html = el.outerHTML || '';
    out.push({ tag: el.tagName.toLowerCase(), geom: r(el),
      text: (el.textContent||'').trim().slice(0,400),
      htmlLen: html.length, rows: (el.textContent||'').split('\\n').map(s=>s.trim())
        .filter(s=>s.length>0&&s.length<80).slice(0,30) });
  }
  out.sort((a,b)=>(b.htmlLen||0)-(a.htmlLen||0));
  return JSON.parse(JSON.stringify({count: out.length, overlays: out.slice(0,4),
    docTitle: document.title}));
})()"""

def overlay_html_slicer(idx):
    """capture the outerHTML of the idx-th biggest visible overlay (for offline truth)."""
    return "(() => {" + R_DEF + f"""
  const vis = (el) => {{ const b = el.getBoundingClientRect();
    return b.width > 150 && b.height > 80; }};
  const cand = [...document.querySelectorAll(
    'ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, yt-system-data-renderer, '+
    '#theme-picker, #account-menu, ytd-popup-container > *, [role="menu"], '+
    'tp-yt-paper-dialog, yt-sheet-view-model, .yt-spec-bottom-sheet-modal')];
  const seen = new Set(); const out = [];
  for (const el of cand) {{
    if (seen.has(el)) continue;
    cand.forEach(o => {{ if (o !== el && o.contains(el)) seen.add(el); }});
    if (seen.has(el) || !vis(el)) continue;
    out.push(el);
  }}
  out.sort((a,b)=>((b.outerHTML||'').length)-((a.outerHTML||'').length));
  const el = out[{idx}];
  return el ? (el.outerHTML || '').slice(0, 380000) : '';
}})()"""

MENU_OPEN_CHECK = "(() => {" + R_DEF + """
  const vis = (el) => { const b = el.getBoundingClientRect();
    return b.width > 150 && b.height > 80; };
  const cand = [...document.querySelectorAll(
    'ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, [role="menu"], '+
    'ytd-popup-container > *, yt-system-data-renderer')].filter(vis);
  return JSON.parse(JSON.stringify({open: cand.length > 0, count: cand.length,
    titles: cand.slice(0,3).map(el => (el.textContent||'').trim().slice(0,120)),
    docTitle: document.title}));
})()"""

THEME_PICKER_CHECK = "(() => {" + R_DEF + """
  const vis = (el) => { const b = el.getBoundingClientRect();
    return b.width > 100 && b.height > 60; };
  const pick = [...document.querySelectorAll(
    '#theme-picker, yt-system-data-renderer, '+
    'yt-radio-button-renderer, tp-yt-paper-listbox')].filter(vis);
  const anyThemeText = pick.some(el => /theme|appearance|device|dark|light/i.test(el.textContent||''));
  return JSON.parse(JSON.stringify({open: pick.length > 0, anyThemeText,
    count: pick.length, texts: pick.slice(0,2).map(el=>(el.textContent||'').trim().slice(0,300)),
    docTitle: document.title}));
})()"""

CLICK_APPEARANCE = "(() => {" + R_DEF + """
  const rows = [...document.querySelectorAll(
    'ytd-compact-link-renderer, ytd-multi-page-menu-item-renderer, '+
    'tp-yt-paper-item, [role="menuitem"], yt-formatted-string, a.yt-simple-endpoint, ytd-account-item-renderer')];
  const ap = rows.find(el => {
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && /^\\s*appearance\\s*$/i.test(el.textContent || '');
  }) || rows.find(el => { const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && /appearance|theme/i.test(el.textContent || '') && (el.textContent||'').length < 60; });
  if (!ap) return 'no-appearance-row; rows=' + rows.filter(el => {
    const b = el.getBoundingClientRect(); return b.width>0 && b.height>0; }).slice(0,25)
    .map(el => (el.textContent||'').trim().slice(0,30)).join(' | ');
  const clickable = ap.closest('ytd-compact-link-renderer, [role="menuitem"], tp-yt-paper-item, a, button') || ap;
  clickable.click();
  return 'clicked: ' + (clickable.tagName||'') + ' :: ' + (clickable.textContent||'').trim().slice(0,60);
})()"""

HOME_PROGRESS = "(() => {" + R_DEF + """
  const cards = [...document.querySelectorAll(
    'ytd-rich-item-renderer, yt-lockup-view-model, ytd-rich-grid-media')].slice(0, 30);
  const out = cards.map(card => {
    const prog = card.querySelector('#progress, [class*=progress] span, [class*=progress]');
    const title = card.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a');
    let pw = null; if (prog) { const cs2 = getComputedStyle(prog); pw = prog.style.width || cs2.width; }
    return {title: title ? (title.textContent||'').trim().slice(0,80) : null,
            hasProgress: !!prog, progressWidth: pw};
  });
  const shelves = [...document.querySelectorAll(
    'ytd-rich-section-renderer, #secondary, ytd-shelf-renderer')].map(s =>
    (s.textContent||'').trim().slice(0,60)).filter(t=>t).slice(0,8);
  const contShelf = [...document.querySelectorAll('span, h2, yt-formatted-string')]
    .map(e => (e.textContent||'').trim()).filter(t =>
      /continue watching|keep watching|since you'/i.test(t)).slice(0,3);
  return JSON.parse(JSON.stringify({title: document.title, url: location.href.slice(0,80),
    cardCount: cards.length, withProgress: out.filter(x=>x.hasProgress).length,
    progressCards: out.filter(x=>x.hasProgress).slice(0,8), shelves, contShelf}));
})()"""

FEED_STATE = "(() => {" + R_DEF + """
  const cards = [...document.querySelectorAll(
    'yt-lockup-view-model, ytd-rich-item-renderer, ytd-rich-grid-media, ytd-video-renderer')].slice(0, 14);
  const out = cards.map(card => {
    const title = card.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a, #video-title');
    const ch = card.querySelector('.ytLockupMetadataViewModelMetadata a, #channel-name a, ytd-channel-name a');
    const meta = card.querySelector('.ytLockupMetadataViewModelMetadata, #metadata-line');
    const thumb = card.querySelector('img.yt-core-image, ytd-thumbnail img');
    const badge = card.querySelector('.ytBadgeShapeText, .badge-shape-wiz__text');
    const t = r(title); const th = r(thumb);
    return {title: title ? (title.textContent||'').trim().slice(0,100) : null,
            titleGeom: t ? {h:t.h, w:t.w, font:t.font} : null,
            channel: ch ? (ch.textContent||'').trim().slice(0,60) : null,
            meta: meta ? (meta.textContent||'').trim().slice(0,140) : null,
            thumb: th, badge: badge ? (badge.textContent||'').trim().slice(0,24) : null};
  });
  const banners = [...document.querySelectorAll('yt-formatted-string, .ytAlertViewModel, div')]
    .map(e => (e.textContent||'').trim()).filter(t =>
      /live|nothing to see|no content|unavailable|later/i.test(t) && t.length > 15 && t.length < 160)
    .slice(0,5);
  return JSON.parse(JSON.stringify({title: document.title, url: location.href.slice(0,80),
    cardCount: cards.length, cards: out.slice(0,10), banners,
    grid: r(document.querySelector('ytd-rich-grid-renderer'))}));
})()"""

SHORTS_STATE = "(() => {" + R_DEF + """
  const btns = [...document.querySelectorAll('button, ytd-button-renderer, yt-button-view-model')]
    .filter(b => { const bb = b.getBoundingClientRect(); return bb.width>0 && bb.height>0; }).slice(0, 40);
  const acts = btns.map(b => { const aria = b.getAttribute('aria-label') || '';
    return {aria: aria.slice(0,80), text: (b.textContent||'').trim().slice(0,40)}; })
    .filter(x => x.aria || x.text).slice(0, 24);
  const counts = [...document.querySelectorAll(
    '.yt-formatted-string, .yt-spec-button-shape-next__button-text-content')]
    .map(e => (e.textContent||'').trim()).filter(Boolean).slice(0, 14);
  const vid = document.querySelector('#shorts-player video, video');
  const gate = [...document.querySelectorAll('yt-formatted-string, div, span')]
    .map(e => (e.textContent||'').trim()).filter(t =>
      /unusual traffic|sign in to confirm|not a bot|verify/i.test(t)).slice(0,2);
  return JSON.parse(JSON.stringify({title: document.title, actionButtons: acts, counts,
    gateText: gate, video: vid ? {readyState: vid.readyState, paused: vid.paused,
      src: (vid.currentSrc||vid.src||'').slice(0,90)} : null}));
})()"""

# ---------- the ladder ----------

def poll(c, expr, want_true, key, tries=8, delay=1.0, timeout=18):
    """poll an eval until it returns {key: want_true} or tries run out."""
    last = None
    for i in range(tries):
        try:
            v = c.eval(expr, timeout=timeout)
            last = v
            if v and v.get(key) == want_true:
                return True, v
        except Exception as e:
            last = {"evalError": f"{type(e).__name__}: {str(e)[:120]}"}
        time.sleep(delay)
    return False, last

def g1_theme_picker(c):
    rec = {"surface": "g1-theme-picker"}
    c.nav("https://www.youtube.com/", settle=5.0)
    try: c.shot("g1-0-home-baseline")
    except Exception: pass
    # 1) open the account menu
    try:
        c.eval("(document.querySelector('#avatar-btn') || document.querySelector('button[aria-label*=\"ccount\"]')).click()")
    except Exception as e:
        rec["avatarClickError"] = str(e)[:150]
    opened, v = poll(c, MENU_OPEN_CHECK, True, "open", tries=8, delay=1.0)
    rec["menuOpen"] = opened; rec["menuProbe"] = v
    if opened:
        try: c.shot("g1-1-account-menu")
        except Exception: pass
        try:
            html = c.eval(overlay_html_slicer(0), timeout=25)
            rec["menuHtmlBytes"] = c.save_html("g1-1-account-menu", html)
        except Exception as e:
            rec["menuHtmlError"] = str(e)[:120]
    # 2) click the Appearance row (whatever happened above — honest either way)
    try:
        rec["appearanceClick"] = c.eval(CLICK_APPEARANCE, timeout=20)
    except Exception as e:
        rec["appearanceClickError"] = str(e)[:150]
    picked, v = poll(c, THEME_PICKER_CHECK, True, "open", tries=8, delay=1.0)
    rec["pickerOpen"] = picked; rec["pickerProbe"] = v
    if picked:
        try: c.shot("g1-2-theme-picker")
        except Exception: pass
        try:
            html = c.eval(overlay_html_slicer(0), timeout=25)
            rec["pickerHtmlBytes"] = c.save_html("g1-2-theme-picker", html)
        except Exception as e:
            rec["pickerHtmlError"] = str(e)[:120]
        # the rows truth (self-contained, from the biggest overlay)
        try:
            rows = c.eval("(() => {" + R_DEF + """
  const vis = (el) => { const b = el.getBoundingClientRect();
    return b.width > 100 && b.height > 60; };
  const pick = [...document.querySelectorAll(
    '#theme-picker, yt-system-data-renderer, ytd-multi-page-menu-renderer, '+
    'tp-yt-iron-dropdown, [role="menu"]')].filter(vis);
  pick.sort((a,b)=>(b.outerHTML||'').length-(a.outerHTML||'').length);
  const root = pick[0];
  if (!root) return null;
  const rows = [...root.querySelectorAll(
    'yt-radio-button-renderer, ytd-compact-link-renderer, tp-yt-paper-item, '+
    '[role="menuitem"], yt-formatted-string, .yt-settings-button, button')]
    .filter(el => { const b = el.getBoundingClientRect();
      return b.width>0 && b.height>0 && b.height<90 && (el.textContent||'').trim().length>0
        && (el.textContent||'').trim().length<50; });
  return JSON.parse(JSON.stringify({rowCount: rows.length,
    rows: rows.map(el => r(el)).slice(0,14)}));
})()""", timeout=20)
            rec["pickerRows"] = rows
        except Exception as e:
            rec["pickerRowsError"] = str(e)[:150]
    else:
        try: c.shot("g1-2-theme-picker-NOT-OPEN")
        except Exception: pass
    # close menus — leave the estate clean
    try: c.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}))")
    except Exception: pass
    return rec

def g2_subs_feed(c):
    c.nav("https://www.youtube.com/feed/subscriptions", settle=7.0)
    rec = {"surface": "g2-subs-feed"}
    try: rec["truth"] = c.eval(FEED_STATE, timeout=25)
    except Exception as e: rec["error"] = str(e)[:200]
    try: rec["screenshotBytes"] = c.shot("g2-subs-feed")
    except Exception as e: rec["screenshotError"] = str(e)[:150]
    return rec

def g3_home_progress(c):
    c.nav("https://www.youtube.com/", settle=7.0)
    rec = {"surface": "g3-home-progress"}
    try: rec["truth"] = c.eval(HOME_PROGRESS, timeout=25)
    except Exception as e: rec["error"] = str(e)[:200]
    try: rec["screenshotBytes"] = c.shot("g3-home-progress")
    except Exception as e: rec["screenshotError"] = str(e)[:150]
    return rec

def g4_shorts(c):
    c.nav("https://www.youtube.com/shorts", settle=9.0)
    rec = {"surface": "g4-shorts"}
    try: rec["truth"] = c.eval(SHORTS_STATE, timeout=25)
    except Exception as e: rec["error"] = str(e)[:200]
    try: rec["screenshotBytes"] = c.shot("g4-shorts")
    except Exception as e: rec["screenshotError"] = str(e)[:150]
    return rec

LADDER = [
    ("g1-theme-picker", g1_theme_picker, "the interactive one first — healthiest moments"),
    ("g2-subs-feed",    g2_subs_feed,    "the healthy grid (yesterday: degraded only)"),
    ("g3-home-progress", g3_home_progress, "the resume bar on home"),
    ("g4-shorts",       g4_shorts,       "the action rail (yesterday: gate-active)"),
]

def main():
    os.makedirs(OUT, exist_ok=True)
    ws_url, url, title = find_yt_ws()
    log(f"YT TAB: {title!r} @ {url}")
    log(f"OUT: {OUT}")
    c = CDP(ws_url)
    results = {}
    for name, fn, desc in LADDER:
        log(f"SURFACE {name} — {desc}")
        t0 = time.time()
        try:
            rec = fn(c)
        except Exception as e:
            rec = {"surface": name, "fatal": f"{type(e).__name__}: {str(e)[:250]}",
                   "trace": traceback.format_exc()[-400:]}
        rec["capturedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec["elapsedS"] = round(time.time() - t0, 1)
        c.save(name, rec)
        ok = ("pickerOpen" in rec and rec.get("pickerOpen")) or \
             ("truth" in rec) or ("pickerRows" in rec)
        results[name] = "ok" if ok else ("partial" if rec.get("menuOpen") else "failed")
        log(f"  saved {name}.json -> {results[name]} ({rec['elapsedS']}s)")
    with open(f"{OUT}/_ladder.json", "w") as f:
        json.dump({"windowTitle": title, "out": OUT,
                   "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "results": results}, f, indent=1)
    log("GAP LADDER COMPLETE: " + json.dumps(results))
    # the watcher reads this file for the verdict
    with open("/home/z/replay2/scripts/flags/yt-gap-last-capture", "w") as f:
        f.write(OUT + "\n" + json.dumps(results) + "\n")

if __name__ == "__main__":
    main()
