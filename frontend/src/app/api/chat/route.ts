export async function POST(req: Request) {
  const body = await req.text();

  const res = await fetch("http://127.0.0.1:8000/api/chat", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body,
  });

  return new Response(await res.text(), {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
}
