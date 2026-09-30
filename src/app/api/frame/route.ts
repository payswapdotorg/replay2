import { BRIDGE, REPLAYD_URL, runBridge, timeoutSignal } from "@/lib/replay";

export async function GET() {
  // hot path: persistent replay daemon (~90ms frames, persistent CDP conns)
  try {
    const r = await fetch(`${REPLAYD_URL}/frame`, {
      cache: "no-store",
      signal: timeoutSignal(4000),
    });
    if (r.ok) {
      const buf = await r.arrayBuffer();
      if (buf.byteLength > 0) {
        return new Response(new Uint8Array(buf), {
          headers: {
            "Content-Type": "image/jpeg",
            "Cache-Control": "no-store, no-cache, must-revalidate",
          },
        });
      }
    } else {
      // replayd reachable but erroring (CDP hiccup): fail FAST so the client
      // retries quickly. Never spawn bridge here — a second concurrent CDP
      // screenshot client corrupts the daemon's capture session (lesson 73).
      return new Response("", { status: 503 });
    }
  } catch {
    /* daemon unreachable — legacy spawn fallback below */
  }
  try {
    const { stdout } = await runBridge("frame", undefined, 8000);
    const buf = stdout as unknown as Buffer;
    if (!buf || buf.length === 0) {
      return new Response("", { status: 500 });
    }
    return new Response(new Uint8Array(buf), {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "no-store, no-cache, must-revalidate",
      },
    });
  } catch {
    return new Response("", { status: 500 });
  }
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
