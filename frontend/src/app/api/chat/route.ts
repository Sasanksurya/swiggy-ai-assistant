// Same-origin POST proxy for the chat endpoint. Reads BACKEND_URL at request time so it works both
// locally (npm run dev -> http://localhost:8000) and in Docker (-> http://backend:8000). Hardcoding
// 127.0.0.1 breaks in a container, where it points at the frontend itself, not the backend.
const backendUrl = () => (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export async function POST(req: Request) {
  const body = await req.text();

  const res = await fetch(`${backendUrl()}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  });

  return new Response(await res.text(), {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
