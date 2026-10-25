// CAD Studio review — server-side proxy to the cad-bridge mini-service (:3210)
// (station #29, 2026-10-25: the operator inspects the live PaySwap CAD Studio
// desktop app through this route; same-origin for the browser, no gateway hops)
export async function GET() {
  try {
    const r = await fetch("http://127.0.0.1:3210/api/cad/frame", { cache: "no-store" });
    if (r.ok) {
      const buf = await r.arrayBuffer();
      return new Response(new Uint8Array(buf), {
        headers: { "Content-Type": "image/png", "Cache-Control": "no-store, no-cache, must-revalidate" },
      });
    }
    return new Response("", { status: 503 });
  } catch {
    return new Response("", { status: 503 });
  }
}
