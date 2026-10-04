/**
 * Same-origin proxy to the FastAPI backend. Reads BACKEND_URL at request time (works in Docker),
 * avoids CORS, and only exposes what the UI needs: /api/chat/** and /api/platform/**.
 */
const ALLOWED = new Set(["chat", "platform"]);

const backendUrl = () => (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const problem = (status: number, code: string, message: string) =>
  Response.json({ detail: { ok: false, error: { code, message } } }, { status });

async function proxy(req: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  const safe =
    path.length > 0 &&
    ALLOWED.has(path[0]) &&
    path.every((s) => s !== "" && s !== "." && s !== ".." && !/[\\/]/.test(s));
  if (!safe) return problem(404, "not_found", "Unknown endpoint");

  const target = `${backendUrl()}/api/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    signal: AbortSignal.timeout(20_000),
    cache: "no-store",
  };
  if (req.method === "POST") init.body = await req.text();

  try {
    const res = await fetch(target, init);
    if (res.status === 204) return new Response(null, { status: 204 });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return problem(502, "backend_unreachable", "Can't reach Sarah's server. Check that the backend is running.");
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE };
