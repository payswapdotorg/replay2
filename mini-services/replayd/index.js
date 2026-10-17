/**
 * replayd gateway — :3100 (bun/mini-service, fixed port)
 *
 * 2026-10-12 recovery #8 architecture (ef69b13):
 *   python CDP core  :3110  (CDP machinery — frames/input/tabs/self-healing)
 *   bun gateway      :3100  (socket.io live stream + /health + /test/drag
 *                            self-test + /home test page + legacy endpoint
 *                            proxying)
 *
 * REBUILT 2026-10-12 recovery #9: the original gateway source lived only at
 * /home/z/my-project/mini-services/replayd (an UNTRACKED path — wiped by the
 * pod recycle). This is a faithful rebuild from the documented contract; the
 * canonical source is now ALSO tracked in replay2 (scripts/gateway/) and
 * launch_gateway.py materializes this dir from it when missing.
 *
 * Routes:
 *   GET  /healthz    → proxied to the core (ring/deploy health semantics:
 *                      gateway is healthy iff the core answers)
 *   GET  /health     → gateway's own health (uptime, core reachability,
 *                      socket.io client count)
 *   GET  /frame      → proxied binary (image/jpeg)
 *   GET  /tabs       → proxied
 *   POST /tabs       → proxied (tab select)
 *   POST /event      → proxied (input injection: nav/type/click/drag/…)
 *   POST /test/drag  → proxied (core's in-process drag self-test)
 *   GET  / | /home   → test page (status + live frame + drag self-test)
 *   socket.io        → "hello" on connect; while clients are attached, a
 *                      1s pump emits "frame" (base64 jpeg) + "tabs" events
 *                      (the live stream the Wave-13 console consumed).
 *   anything else    → 404 {"ok":false,"error":"not-found"} (core parity)
 */
import http from "node:http";
import { Server } from "socket.io";

const PORT = 3100;
const CORE = process.env.REPLAYD_CORE_URL || "http://127.0.0.1:3110";
const started = Date.now();

// ------------------------------------------------------------------ proxy
async function proxy(req, res, corePath) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks);
  const headers = { "Content-Type": req.headers["content-type"] || "application/json" };
  try {
    const r = await fetch(CORE + corePath, {
      method: req.method,
      headers: body.length ? headers : undefined,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : body,
    });
    const buf = Buffer.from(await r.arrayBuffer());
    res.writeHead(r.status, {
      "Content-Type": r.headers.get("content-type") || "application/json",
      "Cache-Control": r.headers.get("cache-control") || "no-store",
      "Content-Length": buf.length,
    });
    res.end(buf);
  } catch (e) {
    const msg = JSON.stringify({ ok: false, error: "core-unreachable", detail: String(e).slice(0, 200) });
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(msg);
  }
}

async function coreOk() {
  try {
    const r = await fetch(CORE + "/healthz", { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------------ pages
const HOME = `<!doctype html><html><head><meta charset="utf-8"><title>replayd gateway</title>
<style>body{font:14px/1.5 ui-monospace,monospace;background:#0d1117;color:#c9d1d9;margin:2rem}
a{color:#58a6ff}button{font:inherit;padding:.4rem 1rem;cursor:pointer}
img{max-width:720px;border:1px solid #30363d;border-radius:6px}
pre{background:#161b22;padding:.8rem;border-radius:6px;overflow:auto}</style></head><body>
<h1>replayd gateway :3100</h1>
<p>bun gateway → python CDP core (:3110) — recovery #9 rebuild (ef69b13 contract)</p>
<p><a href="/health">/health</a> · <a href="/healthz">/healthz</a> · <a href="/tabs">/tabs</a> ·
<a href="/frame">/frame</a> · socket.io live stream at <code>/socket.io/</code></p>
<h2>live frame</h2><img src="/frame" alt="live replay frame" id="f">
<script>setInterval(()=>{const i=document.getElementById('f');i.src='/frame?'+Date.now()},2000)</script>
<h2>drag self-test</h2>
<button onclick="fetch('/test/drag',{method:'POST'}).then(r=>r.json()).then(j=>document.getElementById('o').textContent=JSON.stringify(j,null,2))">POST /test/drag</button>
<pre id="o">—</pre>
</body></html>`;

// ------------------------------------------------------------------ server
const server = http.createServer(async (req, res) => {
  const path = (req.url || "/").split("?")[0];
  switch (path) {
    case "/healthz":
    case "/frame":
    case "/tabs":
    case "/event":
    case "/test/drag":
      return proxy(req, res, path);
    case "/health": {
      const core = await coreOk();
      const body = {
        ok: true,
        gateway: { port: PORT, uptime: Math.round((Date.now() - started) / 1000), clients: io.engine.clientsCount },
        core: { url: CORE, ok: core },
      };
      res.writeHead(core ? 200 : 502, { "Content-Type": "application/json" });
      return res.end(JSON.stringify(body));
    }
    case "/":
    case "/home":
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      return res.end(HOME);
    default:
      res.writeHead(404, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ ok: false, error: "not-found" }));
  }
});

// ------------------------------------------------------------------ socket.io
const io = new Server(server, { cors: { origin: "*", methods: ["GET", "POST"] }, path: "/socket.io/" });
let pump = null;
let lastTabs = "";

io.on("connection", (sock) => {
  sock.emit("hello", { gateway: "replayd-gateway:3100", core: CORE, ts: Date.now() });
  if (!pump) {
    pump = setInterval(async () => {
      if (io.engine.clientsCount === 0) { clearInterval(pump); pump = null; return; }
      try {
        const r = await fetch(CORE + "/frame");
        if (r.ok) {
          const b = Buffer.from(await r.arrayBuffer()).toString("base64");
          io.emit("frame", { jpeg: b, ts: Date.now() });
        }
      } catch { /* core hiccup — next tick */ }
      try {
        const r = await fetch(CORE + "/tabs");
        const t = await r.text();
        if (t !== lastTabs) { lastTabs = t; io.emit("tabs", JSON.parse(t)); }
      } catch { /* next tick */ }
    }, 1000);
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`replayd gateway online on :${PORT} (core ${CORE}, pid ${process.pid})`);
});
