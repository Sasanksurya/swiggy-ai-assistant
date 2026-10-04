import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";
import greet from "@/lib/fixtures/greet.json";
import plan from "@/lib/fixtures/plan.json";
import { budgetOf, peopleOf, useChat } from "./useChat";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  sendChat: vi.fn(),
  resetSession: vi.fn().mockResolvedValue(undefined),
}));
import { resetSession, sendChat } from "@/lib/api";

const asResponse = (x: unknown) => x as ChatResponse;
/** The response shape from an older backend that predates budget_inr/people. */
const legacyOf = (r: ChatResponse): ChatResponse => {
  const copy = structuredClone(r);
  delete copy.cards.budget_inr;
  delete copy.cards.people;
  return copy;
};
const mockSend = vi.mocked(sendChat);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useChat", () => {
  it("adds the user message, then Sarah's reply, and remembers the session", async () => {
    mockSend.mockResolvedValue(asResponse(greet));
    const onReply = vi.fn();
    const { result } = renderHook(() => useChat({ onReply }));
    await act(() => result.current.send("  hi  ", "voice"));
    expect(result.current.messages.map((m) => [m.role, m.text])).toEqual([
      ["user", "hi"],
      ["sarah", asResponse(greet).reply],
    ]);
    expect(result.current.sessionId).toBe("fx1");
    expect(onReply).toHaveBeenCalledWith(expect.objectContaining({ intent: "greet" }), "voice");
    await act(() => result.current.send("again"));
    expect(mockSend).toHaveBeenLastCalledWith("again", "fx1", expect.any(AbortSignal));
  });

  it("ignores blank messages and sends made while one is in flight", async () => {
    let release!: (r: ChatResponse) => void;
    mockSend.mockImplementation(() => new Promise((res) => (release = res)));
    const { result } = renderHook(() => useChat());
    await act(() => result.current.send("   "));
    expect(mockSend).not.toHaveBeenCalled();
    act(() => void result.current.send("first"));
    await waitFor(() => expect(result.current.sending).toBe(true));
    await act(() => result.current.send("second"));
    expect(mockSend).toHaveBeenCalledTimes(1);
    await act(async () => release(asResponse(greet)));
    expect(result.current.sending).toBe(false);
    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
  });

  it("derives the live cart, plan and budget from the latest responses", async () => {
    mockSend.mockResolvedValue(asResponse(plan));
    const { result } = renderHook(() => useChat());
    expect(result.current.cart).toBeUndefined();
    await act(() => result.current.send("biryani for two under 500"));
    expect(result.current.cart?.total_inr).toBe(490);
    expect(result.current.plan?.restaurant_name).toContain("Hyderabadi");
    expect(result.current.budget).toBe(500); // explicit budget_inr from the backend
    expect(result.current.people).toBe(2);
  });

  it("shows an error with the server's message and retries without duplicating the user message", async () => {
    mockSend.mockRejectedValueOnce(new ApiError("Can't reach Sarah's server.", 0, "network"));
    const { result } = renderHook(() => useChat());
    await act(() => result.current.send("hello", "voice"));
    const err = result.current.messages.at(-1)!;
    expect(err).toMatchObject({ role: "error", text: "Can't reach Sarah's server.", retryText: "hello" });
    mockSend.mockResolvedValueOnce(asResponse(greet));
    await act(async () => void (await result.current.retry(err.id)));
    expect(result.current.messages.map((m) => m.role)).toEqual(["user", "sarah"]);
    expect(mockSend).toHaveBeenCalledTimes(2);
  });

  it("falls back to a generic message for unexpected errors", async () => {
    mockSend.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useChat());
    await act(() => result.current.send("x"));
    expect(result.current.messages.at(-1)!.text).toBe("Something went wrong. Please try again.");
  });

  it("reset clears everything, tells the server, and starts a fresh session", async () => {
    mockSend.mockResolvedValue(asResponse(plan));
    const { result } = renderHook(() => useChat());
    await act(() => result.current.send("biryani"));
    await act(() => result.current.reset());
    expect(resetSession).toHaveBeenCalledWith("fx4");
    expect(result.current).toMatchObject({ messages: [], cart: undefined, sessionId: undefined });
    await act(() => result.current.send("hi"));
    expect(mockSend).toHaveBeenLastCalledWith("hi", undefined, expect.any(AbortSignal));
  });

  it("reset still works when the server call fails", async () => {
    mockSend.mockResolvedValue(asResponse(greet));
    vi.mocked(resetSession).mockRejectedValueOnce(new Error("down"));
    const { result } = renderHook(() => useChat());
    await act(() => result.current.send("hi"));
    await act(() => result.current.reset());
    expect(result.current.messages).toEqual([]);
  });
});

describe("older backends without budget_inr/people", () => {
  it("falls back to what the user said on that turn", () => {
    const legacy = legacyOf(asResponse(plan));
    expect(budgetOf(legacy)).toBe(500);
    expect(peopleOf(legacy)).toBe(2);
  });
});

describe("budgetOf", () => {
  it("prefers the explicit budget and ignores max_price outside plans", () => {
    const base = asResponse(plan);
    expect(budgetOf({ ...base, cards: { ...base.cards, budget_inr: 700 } })).toBe(700);
    expect(budgetOf({ ...legacyOf(base), intent: "search_menu" })).toBeUndefined(); // max_price alone is not a plan budget
  });
});
