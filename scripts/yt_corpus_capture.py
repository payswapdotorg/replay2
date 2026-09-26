#!/usr/bin/env python3
"""
yt_corpus_capture.py — the R30 corpus capture ladder (the healthy-window directive).

Order = gate-vulnerable FIRST (the R28 lesson: the window degraded after ~1h):
  masthead -> bell-panel -> account-menu -> appearance (theme picker)
  -> home watched-progress -> rail (subs avatars) -> subs feed
  -> history -> playlists grid -> WL page -> LL page -> shorts action rail.

Every surface: act -> settle -> eval truth (retry, timeout-guarded) -> JPEG screenshot.
Incremental saves: each surface writes its own .json + .jpg the moment it lands.
"""
import json, time, base64, os, sys, traceback
import urllib.request
import websocket

CDP_HTTP = "http://localhost:9222"
OUT = "/home/z/webflix/docs/parity-lab/r30/lead-captures/raw"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)

def find_yt_ws():
    tabs = json.load(urllib.request.urlopen(CDP_HTTP + "/json/list"))
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
        msg = {"id": mid, "method": method, "params": params or {}}
        self.ws.settimeout(timeout)
        self.ws.send(json.dumps(msg))
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
    def eval(self, expr, timeout=20, retries=1):
        """eval with retry; raise on persistent failure."""
        last = None
        for attempt in range(retries + 1):
            try:
                r = self.send("Runtime.evaluate",
                              {"expression": expr, "returnByValue": True, "awaitPromise": True},
                              timeout=timeout + attempt * 15)
                ed = r.get("exceptionDetails")
                if ed:
                    desc = ed.get("exception", {}).get("description", str(ed))[:400]
                    raise RuntimeError(f"eval exception: {desc}")
                return r.get("result", {}).get("value")
            except Exception as e:
                last = e
                log(f"  eval retry ({attempt+1}): {type(e).__name__}: {str(e)[:120]}")
        raise last
    def nav(self, url, settle=6.0):
        self.send("Page.navigate", {"url": url}, timeout=15)
        time.sleep(settle)
    def shot(self, name):
        r = self.send("Page.captureScreenshot", {"format": "jpeg", "quality": 85}, timeout=45)
        data = base64.b64decode(r["data"])
        with open(f"{OUT}/{name}.jpg", "wb") as f:
            f.write(data)
        return len(data)
    def save(self, name, obj):
        with open(f"{OUT}/{name}.json", "w") as f:
            json.dump(obj, f, indent=1, ensure_ascii=True)

# ---------- shared JS ----------

JS_GEOM = """
(() => {
  const r = (el) => { if(!el) return null; const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    const cls = (el.className && el.className.baseVal !== undefined) ? el.className.baseVal : (el.className || '');
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
            text:(el.textContent||'').trim().slice(0,160), cls:String(cls).slice(0,100),
            font:`${cs.fontSize} ${cs.fontWeight} ${cs.fontFamily.split(',')[0].replace(/"/g,'')}`,
            color:cs.color, bg:cs.backgroundColor, radius:cs.borderRadius, display:cs.display}; };
  return r;
})()
"""

def js_wrap(body):
    """body uses: r(sel) -> measured element, q(sel) -> querySelector"""
    return "(() => { const q=(s)=>document.querySelector(s); const r=(el)=>{if(!el)return null;const b=el.getBoundingClientRect();const cs=getComputedStyle(el);const cls=(el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'');return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),text:(el.textContent||'').trim().slice(0,160),cls:String(cls).slice(0,100),font:cs.fontSize+' '+cs.fontWeight+' '+cs.fontFamily.split(',')[0].replace(/\"/g,''),color:cs.color,bg:cs.backgroundColor,radius:cs.borderRadius,display:cs.display};}; " + body + "})()"

# ---------- surfaces ----------

def s_masthead(c):
    expr = js_wrap("""
      const badge = q('#bell-button') || q('ytd-notification-topbar-button-renderer button');
      let badgeText = null;
      if (badge) { const b2 = badge.querySelector('.yt-spec-button-shape-next__button-text-content, tp-yt-paper-badge, .badge-shape-wiz__text'); badgeText = b2 ? b2.textContent.trim() : null; }
      const avatar = q('#avatar-btn') || q('button[aria-label*="ccount"]');
      const mic = q('#microphone-button, button[aria-label*="earch with your voice"]');
      const cluster = q('#end');
      const notifCount = (document.title.match(/^\\((\\d+)\\)/) || [])[1] || null;
      return {title: document.title, url: location.href, signedIn: !!avatar,
              avatar: r(avatar), bell: r(badge), bellBadge: badgeText, notifTitleCount: notifCount,
              mic: r(mic), endCluster: r(cluster)};
    """)
    return c.eval(expr)

def _menu_dump_js(container_sel, item_sel, limit=60):
    # embed selectors via json.dumps so nested quotes never break the JS string
    c = json.dumps(container_sel); i = json.dumps(item_sel)
    return """(() => {
      const dump = (root) => { if(!root) return null; const b = root.getBoundingClientRect();
        const items = [...root.querySelectorAll(%s)].filter(el => {
          const bb = el.getBoundingClientRect(); return bb.width>0 && bb.height>0 && bb.height<160 && el.children.length<=10;
        }).slice(0,%d).map(el => r(el));
        return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),items:items}; };
      const roots = [...document.querySelectorAll(%s)].filter(el => {
        const b = el.getBoundingClientRect(); return b.width>0 && b.height>0; });
      return {menus: roots.slice(0,4).map(dump), title: document.title};
    })()""" % (i, limit, c)

def s_bell(c):
    # menus are driven from HOME (the masthead selectors are stable there — run-1 proof)
    c.nav("https://www.youtube.com/", settle=5.0)
    c.eval("(document.querySelector('#bell-button') || document.querySelector('ytd-notification-topbar-button-renderer button') || document.querySelector('#end button:last-of-type')).click()")
    time.sleep(2.5)
    truth = None
    try:
        truth = c.eval(_menu_dump_js(
            "ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, #notifications-container",
            "ytd-notification-renderer, .yt-lockup-metadata, h3, yt-formatted-string", 40))
    except Exception as e:
        truth = {"evalFailed": str(e)[:200]}
    return truth

def s_account_menu(c):
    try: c.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}))")
    except Exception: pass
    time.sleep(0.8)
    c.eval("(document.querySelector('#avatar-btn') || document.querySelector('button[aria-label*=\"ccount\"]')).click()")
    time.sleep(2.5)
    truth = None
    try:
        truth = c.eval(_menu_dump_js(
            "ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, #account-menu",
            "ytd-compact-link-renderer, ytd-account-item-renderer, yt-formatted-string, tp-yt-paper-item, ytd-multi-page-menu-item-renderer, a.yt-simple-endpoint", 50))
    except Exception as e:
        truth = {"evalFailed": str(e)[:200]}
    return truth

def s_appearance(c):
    # account menu should still be open; click the Appearance row
    try:
        c.eval("""(() => {
          const rows = [...document.querySelectorAll('ytd-compact-link-renderer, ytd-multi-page-menu-item-renderer, tp-yt-paper-item')];
          const ap = rows.find(el => /appearance|appearance/i.test(el.textContent || ''));
          if (ap) { ap.click(); return 'clicked'; }
          return 'no-appearance-row';
        })()""")
    except Exception as e:
        return {"evalFailed": str(e)[:200]}
    time.sleep(2.0)
    truth = None
    try:
        truth = c.eval(_menu_dump_js(
            "yt-system-data-renderer, ytd-multi-page-menu-renderer, tp-yt-iron-dropdown, #theme-picker",
            "ytd-compact-link-renderer, yt-system-data-renderer, tp-yt-paper-item, yt-formatted-string, yt-radio-button-renderer", 40))
    except Exception as e:
        truth = {"evalFailed": str(e)[:200]}
    # close menus
    try: c.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}))")
    except Exception: pass
    time.sleep(0.5)
    return truth

def s_home_progress(c):
    c.nav("https://www.youtube.com/", settle=7.0)
    expr = js_wrap("""
      const cards = [...document.querySelectorAll('ytd-rich-item-renderer, yt-lockup-view-model, ytd-rich-grid-media')].slice(0, 24);
      const out = cards.map(card => {
        const prog = card.querySelector('#progress, [class*=progress]');
        const thumb = card.querySelector('img.yt-core-image, img');
        const title = card.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a');
        const meta = card.querySelector('.ytLockupMetadataViewModelMetadata, #metadata-line, #channel-info, .yt-lockup-metadata-view-model__metadata');
        let pw = null, pgh = null;
        if (prog) { const cs2 = getComputedStyle(prog); pw = prog.style.width || cs2.width; pgh = cs2.height; }
        return {title: title ? (title.textContent||'').trim().slice(0,90) : null,
                hasProgress: !!prog, progressWidth: pw, progressH: pgh,
                thumb: r(thumb), meta: meta ? (meta.textContent||'').trim().slice(0,120) : null};
      });
      const withProgress = out.filter(x => x.hasProgress).length;
      return {title: document.title, cards: out, withProgressCount: withProgress, cardCount: cards.length};
    """)
    return c.eval(expr)

def s_rail(c):
    # open the guide drawer first so geometries are real (the collapsed rail measures 0)
    try: c.eval("(() => { const g = document.querySelector('#guide-button') || document.querySelector('#guide svg'); if (g) g.closest('button') ? g.closest('button').click() : g.click(); return 'ok'; })()")
    except Exception: pass
    time.sleep(2.0)
    expr = js_wrap("""
      const sections = [...document.querySelectorAll('ytd-guide-section-renderer')].slice(0, 10).map(sec => {
        const heading = sec.querySelector('#guide-section-title, yt-formatted-string');
        const entries = [...sec.querySelectorAll('ytd-guide-entry-renderer')].slice(0, 14).map(e => {
          const img = e.querySelector('img');
          const avatar = img ? r(img) : null;
          if (avatar) { avatar.src = (img.src||'').slice(0,120); avatar.natWH = img.naturalWidth+'x'+img.naturalHeight; }
          const t = r(e);
          return {text: t ? t.text : null, geom: t ? {x:t.x,y:t.y,w:t.w,h:t.h} : null, avatar: avatar,
                  active: /active/.test(String(e.className||'')) || !!e.querySelector('.active')};
        });
        return {heading: heading ? heading.textContent.trim().slice(0,50) : null, entries: entries};
      });
      const drawer = q('tp-yt-drawer#guide');
      return {title: document.title, sections: sections, drawer: r(drawer)};
    """)
    return c.eval(expr)

def _feed_cards_js(container_note):
    # modern DOM: yt-lockup-view-model (home/subs/history) + legacy fallbacks
    return js_wrap("""
      const cards = [...document.querySelectorAll('yt-lockup-view-model, ytd-rich-item-renderer, ytd-rich-grid-media, ytd-video-renderer')].slice(0, 12);
      const out = cards.map(card => {
        const title = card.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a, #video-title');
        const ch = card.querySelector('.ytLockupMetadataViewModelMetadata a, #channel-name a, ytd-channel-name a');
        const meta = card.querySelector('.ytLockupMetadataViewModelMetadata, #metadata-line, .yt-lockup-metadata-view-model__metadata');
        const thumb = card.querySelector('img.yt-core-image, ytd-thumbnail img');
        const badge = card.querySelector('.ytBadgeShapeText, ytd-thumbnail-overlay-time-status-renderer, .badge-shape-wiz__text');
        const t = r(title); const th = r(thumb);
        return {title: title ? (title.textContent||'').trim().slice(0,100) : null,
                titleGeom: t ? {h:t.h, font:t.font, w:t.w} : null,
                channel: ch ? (ch.textContent||'').trim().slice(0,60) : null,
                meta: meta ? (meta.textContent||'').trim().slice(0,140) : null,
                thumb: th, duration: badge ? (badge.textContent||'').trim().slice(0,20) : null};
      });
      return {note: '%s', title: document.title, url: location.href, cards: out,
              grid: r(document.querySelector('ytd-rich-grid-renderer')) || r(document.querySelector('#contents.ytd-browse'))};
    """ % container_note)

def s_subs_feed(c):
    c.nav("https://www.youtube.com/feed/subscriptions", settle=7.0)
    return c.eval(_feed_cards_js("subscriptions feed"))

def s_history(c):
    c.nav("https://www.youtube.com/feed/history", settle=8.0)
    expr = js_wrap("""
      const rows = [...document.querySelectorAll('yt-lockup-view-model, ytd-video-renderer, ytd-rich-grid-media')].slice(0, 10);
      const out = rows.map(row => {
        const title = row.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a, #video-title');
        const ch = row.querySelector('.ytLockupMetadataViewModelMetadata a, ytd-channel-name a, #channel-name a');
        const meta = row.querySelector('.ytLockupMetadataViewModelMetadata, #metadata-line, #description');
        const thumb = row.querySelector('img.yt-core-image, ytd-thumbnail img');
        const prog = row.querySelector('#progress, [class*=progress]');
        return {title: title ? (title.textContent||'').trim().slice(0,100) : null,
                channel: ch ? (ch.textContent||'').trim().slice(0,60) : null,
                meta: meta ? (meta.textContent||'').trim().slice(0,150) : null,
                thumb: r(thumb),
                progress: prog ? (prog.style.width || getComputedStyle(prog).width) : null};
      });
      const railBtns = [...document.querySelectorAll('ytd-button-renderer button, yt-chip-cloud-chip-renderer, button')].slice(0,24).map(b => (b.textContent||'').trim().slice(0,40)).filter(Boolean);
      return {title: document.title, rows: out, railButtons: railBtns};
    """)
    return c.eval(expr)

def s_playlists(c):
    c.nav("https://www.youtube.com/feed/playlists", settle=8.0)
    expr = js_wrap("""
      const cards = [...document.querySelectorAll('yt-lockup-view-model, ytd-rich-grid-media, ytd-lockup-renderer, ytd-rich-item-renderer')].slice(0, 12);
      const out = cards.map(card => {
        const title = card.querySelector('h3 a, h3, .ytLockupMetadataViewModelHeading a, #video-title');
        const meta = card.querySelector('.ytLockupMetadataViewModelMetadata, #metadata-line');
        const thumb = card.querySelector('img.yt-core-image, ytd-thumbnail img');
        const stack = card.querySelector('.yt-lockup-thumbnail-overlay-playlist, #overlays, ytd-thumbnail-overlay-side-renderer, yt-collections-stack, .ytCollectionsStackHost');
        const st = r(stack);
        if (st && stack.querySelector('img')) { st.stackImgs = stack.querySelectorAll('img').length; }
        return {title: title ? (title.textContent||'').trim().slice(0,80) : null,
                meta: meta ? (meta.textContent||'').trim().slice(0,120) : null,
                thumb: r(thumb), stack: st};
      });
      return {title: document.title, cards: out};
    """)
    return c.eval(expr)

def _playlist_page_js(name):
    return js_wrap("""
      const header = document.querySelector('ytd-playlist-header-renderer') || document.querySelector('#playlist');
      const title = document.querySelector('.yt-dynamic-sizing-formatted-string, h1, #title, .ytLockupMetadataViewModelHeading');
      const count = document.querySelector('#stats .yt-formatted-string:first-child, ytd-playlist-byline-renderer .yt-formatted-string, yt-formatted-string.style-scope.ytd-playlist-byline-renderer');
      const rows = [...document.querySelectorAll('ytd-playlist-video-renderer, ytd-video-renderer, yt-lockup-view-model')].slice(0, 10).map(row => {
        const t = row.querySelector('#video-title, a#video-title, h3 a, h3');
        const idx = row.querySelector('#index-container, .yt-ui-ellipsis, #index');
        const thumb = row.querySelector('ytd-thumbnail img, img.yt-core-image');
        return {title: t ? (t.textContent||'').trim().slice(0,90) : null, index: idx ? (idx.textContent||'').trim().slice(0,12) : null, thumb: r(thumb)};
      });
      return {page: '%s', title: title ? (title.textContent||'').trim().slice(0,80) : null,
              count: count ? (count.textContent||'').trim().slice(0,60) : null,
              headerGeom: r(header), rows: rows, docTitle: document.title, url: location.href.slice(0,90)};
    """ % name)

def s_watch_later(c):
    c.nav("https://www.youtube.com/playlist?list=WL", settle=7.0)
    return c.eval(_playlist_page_js("watch-later"))

def s_liked(c):
    c.nav("https://www.youtube.com/playlist?list=LL", settle=7.0)
    return c.eval(_playlist_page_js("liked-videos"))

def s_shorts(c):
    c.nav("https://www.youtube.com/shorts", settle=9.0)
    expr = js_wrap("""
      const allBtns = [...document.querySelectorAll('button, ytd-button-renderer')].filter(b => {
        const bb = b.getBoundingClientRect(); return bb.width>0 && bb.height>0; }).slice(0, 40);
      const acts = allBtns.map(b => { const m = r(b); const aria = b.getAttribute('aria-label') || ''; return {aria: aria.slice(0,80), text: (b.textContent||'').trim().slice(0,40), geom: m ? {x:m.x,y:m.y,w:m.w,h:m.h} : null}; }).filter(x => x.aria || x.text);
      let counts = [...document.querySelectorAll('.yt-formatted-string, .yt-spec-button-shape-next__button-text-content')].slice(0, 14).map(e => (e.textContent||'').trim().slice(0,40)).filter(Boolean);
      const channel = document.querySelector('ytd-channel-name a, ytd-reel-player-overlay-renderer #channel-name a, .yt-shorts-channel-link');
      const subs = document.querySelector('ytd-subscribe-button-renderer button, yt-subscribe-button-view-model button, .yt-spec-subscribe-button, button[aria-label*="ubscribe"]');
      const vid = document.querySelector('#shorts-player video, video');
      const tags = {}; document.querySelectorAll('ytd-reel-video-renderer, ytd-reel-renderer, yt-shorts, #shorts-container').forEach(el => { tags[el.tagName.toLowerCase()] = true; });
      return {title: document.title, domTags: Object.keys(tags), actionButtons: acts, counts: counts,
              channel: channel ? (channel.textContent||'').trim().slice(0,60) : null,
              subscribeBtn: r(subs),
              video: vid ? {src: (vid.currentSrc||vid.src||'').slice(0,100) || null, readyState: vid.readyState, paused: vid.paused} : null};
    """)
    return c.eval(expr)

import sys as _sys
_ONLY = _sys.argv[1:] if len(_sys.argv) > 1 else None
LADDER = [
    ("01-masthead",      s_masthead,      "masthead account cluster + bell + badge"),
    ("02-bell-panel",    s_bell,          "notifications panel (gate-vulnerable #1)"),
    ("03-account-menu",  s_account_menu,  "avatar account menu (gate-vulnerable #2)"),
    ("04-appearance",    s_appearance,    "appearance submenu + theme picker"),
    ("05-home-progress", s_home_progress, "home watched-progress (gate-vulnerable #3)"),
    ("06-rail",          s_rail,          "subscriptions rail + avatars"),
    ("07-subs-feed",     s_subs_feed,     "subscriptions feed row grammar"),
    ("08-history",       s_history,       "history page"),
    ("09-playlists",     s_playlists,     "playlists grid (WL/LL cards)"),
    ("10-watch-later",   s_watch_later,   "watch later playlist page"),
    ("11-liked",         s_liked,         "liked videos playlist page"),
    ("12-shorts",        s_shorts,        "shorts action rail + counts"),
]
if _ONLY:
    LADDER = [l for l in LADDER if l[0].startswith(tuple(_ONLY))]

def main():
    os.makedirs(OUT, exist_ok=True)
    ws_url, url, title = find_yt_ws()
    log(f"YT TAB: {title!r} @ {url}")
    c = CDP(ws_url)
    results = {}
    for name, fn, desc in LADDER:
        log(f"SURFACE {name} — {desc}")
        truth = None; err = None
        try:
            truth = fn(c)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:300]}"
            log(f"  FAILED: {err}")
        rec = {"surface": name, "desc": desc, "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if truth is not None:
            rec["truth"] = truth
        if err:
            rec["error"] = err
        try:
            rec["screenshotBytes"] = c.shot(name)
        except Exception as e:
            rec["screenshotError"] = str(e)[:200]
        c.save(name, rec)
        results[name] = "ok" if truth is not None else ("eval-failed-screenshot-only" if "screenshotBytes" in rec else "failed")
        log(f"  saved {name}.json ({results[name]})")
    with open(f"{OUT}/_ladder.json", "w") as f:
        json.dump({"startedFor": title, "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}, f, indent=1)
    log("LADDER COMPLETE: " + json.dumps(results))

if __name__ == "__main__":
    main()
