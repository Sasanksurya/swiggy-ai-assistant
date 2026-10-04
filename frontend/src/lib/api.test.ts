import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, describeError, getPlatformInfo, isChatResponse, resetSession, sendChat } from "./api";
import greet from "./fixtures/greet.json";
import plan from "./fixtures/plan.json";
import unknown from "./fixtures/unknown.json";
import platformInfo from "./fixtures/platform_info.json";
import validation from "./fixtures/validation_error.json";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("real backend fixtures satisfy the runtime guard", () => {
  it.each([["greet", greet], ["plan", plan], ["unknown", unknown]])("%s", (_n, fx) => {
    expect(isChatResponse(fx)).toBe(true);
  });
  it("rejects malformed bodies", () => {
    expect(isChatResponse(null)).toBe(false);
    expect(isChatResponse({ reply: "x" })).toBe(false);
    expect(isChatResponse({ ...greet, source: "other" })).toBe(false);
    expect(isChatResponse({ ...greet, tool_calls: "no" })).toBe(false);
  });
});

describe("sendChat", () => {
  it("posts the message, includes session_id only when known, returns the typed response", async () => {
    const f = vi.fn().mockImplementation(async () => json(plan)); // fresh Response per call, like real fetch
    vi.stubGlobal("fetch", f);
    const r = await sendChat("biryani for two", "abc");
    expect(r.cards.plan?.restaurant_name).toContain("Hyderabadi");
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "biryani for two", session_id: "abc" });
    await sendChat("hello");
    expect(JSON.parse(f.mock.calls[1][1].body)).toEqual({ message: "hello" });
  });

  it("turns FastAPI validation errors into a friendly message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(validation, 422)));
    await expect(sendChat("")).rejects.toMatchObject({ status: 422, code: "validation" });
  });

  it("surfaces platform errors with their code", async () => {
    const body = { detail: { ok: false, error: { code: "unsupported_capability", message: "Not configured yet" } } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(body, 501)));
    await expect(sendChat("x")).rejects.toMatchObject({ message: "Not configured yet", code: "unsupported_capability" });
  });

  it("reports an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(sendChat("x")).rejects.toMatchObject({ status: 0, code: "network" });
  });

  it("rejects unreadable success bodies and non-JSON errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ hello: "world" })));
    await expect(sendChat("x")).rejects.toMatchObject({ code: "bad_response" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>oops</html>", { status: 500 })));
    await expect(sendChat("x")).rejects.toMatchObject({ status: 500, message: "Something went wrong (error 500)." });
  });

  it("lets aborts through untouched", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    await expect(sendChat("x")).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("other calls", () => {
  it("getPlatformInfo returns the synthetic-data banner", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(platformInfo)));
    const info = await getPlatformInfo();
    expect(info.synthetic).toBe(true);
    expect(info.banner).toMatch(/synthetic/i);
  });

  it("resetSession encodes the id and accepts 204", async () => {
    const f = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    await resetSession("a b");
    expect(f.mock.calls[0][0]).toBe("/api/chat/a%20b");
    expect(f.mock.calls[0][1].method).toBe("DELETE");
    f.mockResolvedValue(json({}, 500));
    await expect(resetSession("x")).rejects.toBeInstanceOf(ApiError);
  });

  it("describeError handles strings and unknown shapes", () => {
    expect(describeError({ detail: "plain" }, 400).message).toBe("plain");
    expect(describeError(null, 503).message).toContain("503");
  });
});
