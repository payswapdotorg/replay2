export async function POST(req: Request) {
  try {
    const body = await req.text();
    const r = await fetch("http://127.0.0.1:3210/api/cad/op", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    const t = await r.text();
    return new Response(t, { status: r.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ ok: false, error: String(e) }, { status: 500 });
  }
}
