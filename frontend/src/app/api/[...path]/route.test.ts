import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST } from "./route";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const req = (url: string, init?: RequestInit) => new Request(`http://app.test${url}`, init);

beforeEach(() => {
  process.env.BACKEND_URL = "http://backend:8000/";
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.BACKEND_URL;
});

describe("backend proxy", () => {
  it("forwards POST /api/chat with its JSON body to BACKEND_URL", async () => {
    const f = vi.fn().mockResolvedValue(new Response('{"ok":1}', { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", f);
    const res = await POST(req("/api/chat", { method: "POST", body: '{"message":"hi"}', headers: { "content-type": "application/json" } }), ctx("chat"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: 1 });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("http://backend:8000/api/chat");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"message":"hi"}');
  });

  it("keeps the query string and falls back to localhost:8000", async () => {
    delete process.env.BACKEND_URL;
    const f = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", f);
    await GET(req("/api/platform/info?x=1"), ctx("platform", "info"));
    expect(f.mock.calls[0][0]).toBe("http://localhost:8000/api/platform/info?x=1");
  });

  it("passes 204 through (session reset)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const res = await DELETE(req("/api/chat/s1", { method: "DELETE" }), ctx("chat", "s1"));
    expect(res.status).toBe(204);
  });

  it("passes backend error statuses through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"detail":[]}', { status: 422 })));
    expect((await POST(req("/api/chat", { method: "POST", body: "{}" }), ctx("chat"))).status).toBe(422);
  });

  it.each([
    [["health", "ready"]], [["restaurants"]], [["cart"]], [["chat", ".."]], [["chat", "..", "x"]],
    [["chat", "a/b"]], [["chat", ""]], [[]],
  ])("blocks paths outside chat/platform: %j", async (path) => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    const res = await GET(req("/api/x"), ctx(...path));
    expect(res.status).toBe(404);
    expect(f).not.toHaveBeenCalled();
  });

  it("returns a 502 JSON problem when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("ECONNREFUSED")));
    const res = await POST(req("/api/chat", { method: "POST", body: "{}" }), ctx("chat"));
    expect(res.status).toBe(502);
    expect((await res.json()).detail.error.code).toBe("backend_unreachable");
  });
});
