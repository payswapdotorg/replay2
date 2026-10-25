"use client";

/**
 * CAD Studio review view (station #29, 2026-10-25) — the operator's live
 * window into the PaySwap CAD Studio desktop app running under Xvfb +
 * lavapipe on this pod. Frames come from the app's own GUI automation
 * control socket (`capture` op — the actual GPU frame) via the cad-bridge
 * mini-service; the command strip relays `run` ops back through the same
 * socket. Follows the replay-console frame-loop conventions.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { DraftingCompass, RefreshCw, Play, Crosshair } from "lucide-react";

type CadStatus = {
  ok: boolean;
  app: { pid: number; session_id: string } | null;
  hello: { document_id: string | null; revision: number | null } | null;
  frame: { ts: number; age_ms: number; dim: string | null; bytes: number } | null;
  error: string | null;
};

const FRAME_IDLE_MS = 2600; // bridge re-captures every 2.5s
const FRAME_FAST_MS = 900; // after an op, poll faster briefly
const STATUS_MS = 10000;

export default function CadReview() {
  const [status, setStatus] = useState<CadStatus | null>(null);
  const [frameSeq, setFrameSeq] = useState(0);
  const [cmd, setCmd] = useState("");
  const [opResult, setOpResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fastUntil = useRef(0);

  const refreshFrame = useCallback(async () => {
    // cache-busted fetch; a 503 just means no frame yet (app booting)
    try {
      await fetch(`/api/cad/frame?t=${Date.now()}`, { cache: "no-store" });
    } catch { /* bridge down */ }
    setFrameSeq((s) => s + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    const loop = async () => {
      while (alive) {
        await refreshFrame();
        const wait = Date.now() < fastUntil.current ? FRAME_FAST_MS : FRAME_IDLE_MS;
        await new Promise((r) => setTimeout(r, wait));
      }
    };
    loop();
    return () => { alive = false; };
  }, [refreshFrame]);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await fetch("/api/cad/status", { cache: "no-store" });
        if (r.ok) setStatus(await r.json());
      } catch { /* bridge down */ }
    }, STATUS_MS);
    return () => clearInterval(t);
  }, []);

  const sendOp = useCallback(async (op: Record<string, unknown>, label: string) => {
    setBusy(true);
    setOpResult(`${label} …`);
    try {
      const r = await fetch("/api/cad/op", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(op),
      });
      const j = await r.json().catch(() => ({}));
      setOpResult(`${label}: ${JSON.stringify(j).slice(0, 220)}`);
      fastUntil.current = Date.now() + 6000;
    } catch (e) {
      setOpResult(`${label}: FAILED ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const submitCmd = useCallback(async () => {
    const c = cmd.trim();
    if (!c) return;
    setCmd("");
    await sendOp({ op: "run", cmd: c }, `run ${c.slice(0, 40)}`);
  }, [cmd, sendOp]);

  const frameAlive = status?.frame ? status.frame.age_ms < 15000 : false;
  const appUp = !!status?.app;

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col bg-neutral-950 text-neutral-100">
      {/* status strip */}
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-800 px-3 py-2 text-[11px] sm:px-6">
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${appUp ? "border-emerald-800 bg-emerald-950 text-emerald-300" : "border-neutral-800 bg-neutral-900 text-neutral-400"}`}>
          <DraftingCompass className="h-3 w-3" aria-hidden="true" /> PaySwap CAD Studio {appUp ? `pid ${status?.app?.pid}` : "down"}
        </span>
        {status?.hello?.revision != null && (
          <span className="rounded-full border border-neutral-800 bg-neutral-900 px-2 py-0.5 text-neutral-400">
            rev {status.hello.revision}
          </span>
        )}
        {status?.frame?.dim && (
          <span className="rounded-full border border-neutral-800 bg-neutral-900 px-2 py-0.5 text-neutral-400">
            {status.frame.dim} · {(status.frame.bytes / 1024).toFixed(0)} KB
          </span>
        )}
        <span className={`rounded-full border px-2 py-0.5 ${frameAlive ? "border-emerald-800 bg-emerald-950 text-emerald-300" : "border-amber-800 bg-amber-950 text-amber-300"}`}>
          {frameAlive ? "frame live" : "waiting for frame…"}
        </span>
        {status?.error && (
          <span className="rounded-full border border-amber-800 bg-amber-950 px-2 py-0.5 text-amber-300" title={status.error}>
            {status.error.slice(0, 60)}
          </span>
        )}
        <span className="ml-auto hidden text-neutral-600 sm:block">
          GPU frames via the app automation socket (capture) · cad-bridge :3210
        </span>
      </div>

      {/* live frame */}
      <div className="relative flex-1 overflow-hidden bg-[#1a1a1a]">
        <img
          src={`/api/cad/frame?t=${frameSeq}`}
          alt="PaySwap CAD Studio live viewport (GPU capture)"
          className="h-full w-full object-contain"
          style={{ imageRendering: "auto" }}
        />
        {!appUp && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="rounded-lg border border-neutral-800 bg-neutral-900/95 px-6 py-4 text-center text-sm text-neutral-400">
              <DraftingCompass className="mx-auto mb-2 h-8 w-8 text-neutral-600" aria-hidden="true" />
              PaySwap CAD Studio is not running on this station.
              <div className="mt-1 text-[11px] text-neutral-600">
                Launch state is recorded in the station worklog; the bridge reconnects automatically.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* command strip */}
      <div className="border-t border-neutral-800 bg-neutral-950 px-3 py-2 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => sendOp({ op: "run", cmd: "ZOOM E" }, "ZOOM extents")}
            disabled={busy || !appUp}
            className="inline-flex items-center gap-1 rounded-md border border-neutral-800 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
          >
            <Crosshair className="h-3.5 w-3.5" aria-hidden="true" /> Zoom Extents
          </button>
          <button
            onClick={() => { fastUntil.current = Date.now() + 8000; refreshFrame(); }}
            className="inline-flex items-center gap-1 rounded-md border border-neutral-800 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-300 hover:bg-neutral-800"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Refresh
          </button>
          <form
            className="flex min-w-[240px] flex-1 items-center gap-2"
            onSubmit={(e) => { e.preventDefault(); submitCmd(); }}
          >
            <input
              value={cmd}
              onChange={(e) => setCmd(e.target.value)}
              placeholder="CAD command (e.g. LINE 0,0 100,100 · CIRCLE · LINETYPE SET DASHED)"
              className="w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs text-neutral-200 placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
              disabled={busy || !appUp}
            />
            <button
              type="submit"
              disabled={busy || !appUp || !cmd.trim()}
              className="inline-flex items-center gap-1 rounded-md bg-neutral-100 px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-white disabled:opacity-40"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" /> Run
            </button>
          </form>
        </div>
        {opResult && (
          <div className="mt-1 truncate font-mono text-[11px] text-neutral-500" title={opResult}>
            {opResult}
          </div>
        )}
      </div>
    </div>
  );
}
