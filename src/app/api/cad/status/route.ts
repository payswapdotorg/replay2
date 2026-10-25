export async function GET() {
  try {
    const r = await fetch("http://127.0.0.1:3210/api/cad/status", { cache: "no-store" });
    const t = await r.text();
    return new Response(t, { status: r.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ ok: false, error: String(e) }, { status: 503 });
  }
}
