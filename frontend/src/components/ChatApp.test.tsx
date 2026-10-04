import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import type { ChatResponse, PlatformInfo } from "@/lib/types";
import checkout from "@/lib/fixtures/checkout.json";
import greet from "@/lib/fixtures/greet.json";
import ordered from "@/lib/fixtures/ordered.json";
import items from "@/lib/fixtures/items.json";
import order from "@/lib/fixtures/order.json";
import plan from "@/lib/fixtures/plan.json";
import platformInfo from "@/lib/fixtures/platform_info.json";
import { ChatApp } from "./ChatApp";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  sendChat: vi.fn(),
  getPlatformInfo: vi.fn(),
  resetSession: vi.fn().mockResolvedValue(undefined),
}));
import { getPlatformInfo, resetSession, sendChat } from "@/lib/api";

const res = (x: unknown) => x as ChatResponse;
const mockSend = vi.mocked(sendChat);

class FakeRecognition {
  static last: FakeRecognition | undefined;
  onstart: (() => void) | null = null;
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  lang = ""; continuous = false; interimResults = false; maxAlternatives = 1;
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn();
  constructor() { FakeRecognition.last = this; }
  say(text: string, isFinal: boolean) {
    this.onresult?.({ resultIndex: 0, results: { length: 1, 0: { isFinal, 0: { transcript: text } } } });
  }
}

const spoken: string[] = [];
const synth = {
  speak: vi.fn((u: { text: string }) => spoken.push(u.text)),
  cancel: vi.fn(),
  getVoices: vi.fn(() => []),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};
const win = window as unknown as Record<string, unknown>;

function enableVoice() {
  win.webkitSpeechRecognition = FakeRecognition;
  Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  vi.stubGlobal("SpeechSynthesisUtterance", class { text: string; constructor(t: string) { this.text = t; } });
}

beforeEach(() => {
  vi.clearAllMocks();
  spoken.length = 0;
  vi.mocked(getPlatformInfo).mockResolvedValue(platformInfo as PlatformInfo);
});
afterEach(() => {
  delete win.webkitSpeechRecognition;
  delete win.speechSynthesis;
  vi.unstubAllGlobals();
});

describe("ChatApp: text", () => {
  it("opens with a welcome, suggestions, the demo-data banner and an empty order", async () => {
    render(<ChatApp />);
    expect(screen.getByRole("heading", { name: "Sarah" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What are you craving?" })).toBeInTheDocument();
    expect(await screen.findByRole("note")).toHaveTextContent(/synthetic, not real Swiggy data/);
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /under|Dosa|Where/ })).toHaveLength(4);
  });

  it("a suggestion sends the message, shows Sarah's reply, her pick and the live order with its budget meter", async () => {
    mockSend.mockResolvedValue(res(plan));
    render(<ChatApp />);
    await userEvent.click(screen.getByRole("button", { name: "Biryani for two under ₹500" }));
    expect(mockSend).toHaveBeenCalledWith("Biryani for two under ₹500", undefined, expect.any(AbortSignal));
    const log = screen.getByRole("log");
    expect(await within(log).findByText(/my pick is Sample Hyderabadi Kitchen/)).toBeInTheDocument();
    expect(within(log).getByText("For 2 people, within ₹500")).toBeInTheDocument();
    const slip = screen.getByRole("complementary", { name: "Your order" });
    expect(within(slip).getByText("Sample Hyderabadi Kitchen")).toBeInTheDocument();
    expect(within(slip).getByText(/₹490 of ₹500\./)).toHaveTextContent("₹10 left");
    expect(screen.queryByRole("heading", { name: "What are you craving?" })).not.toBeInTheDocument();
  });

  it("types and sends, clears the box, and keeps Send disabled for blank input", async () => {
    mockSend.mockResolvedValue(res(greet));
    render(<ChatApp />);
    const send = screen.getByRole("button", { name: "Send" });
    const box = screen.getByRole("textbox", { name: "Message to Sarah" });
    expect(send).toBeDisabled();
    await userEvent.type(box, "hi");
    expect(send).toBeEnabled();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(mockSend).toHaveBeenCalledWith("hi", undefined, expect.any(AbortSignal)));
    expect(box).toHaveValue("");
    expect(await screen.findByText(/Hi, I'm Sarah/)).toBeInTheDocument();
  });

  it("menu rows send position-based requests", async () => {
    mockSend.mockResolvedValue(res(items));
    render(<ChatApp />);
    await userEvent.click(screen.getByRole("button", { name: "Veg items under ₹100" }));
    await userEvent.click((await screen.findAllByRole("button", { name: /^Add / }))[0]);
    expect(mockSend).toHaveBeenLastCalledWith("add number 1", expect.anything(), expect.anything());
  });

  it("shows order status as a readable chip", async () => {
    mockSend.mockResolvedValue(res(order));
    render(<ChatApp />);
    await userEvent.click(screen.getByRole("button", { name: /Where is order/ }));
    expect(await screen.findByText("Out for delivery")).toBeInTheDocument();
  });

  it("explains errors and retries without repeating the user's message", async () => {
    mockSend.mockRejectedValueOnce(new ApiError("Can't reach Sarah's server. Check that the backend is running.", 0, "network"));
    render(<ChatApp />);
    await userEvent.click(screen.getByRole("button", { name: "Dosa restaurants" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Sarah's server");
    mockSend.mockResolvedValueOnce(res(greet));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Hi, I'm Sarah/)).toBeInTheDocument();
    expect(screen.getAllByText("Dosa restaurants")).toHaveLength(1);
  });

  it("warns when the backend is down at load", async () => {
    vi.mocked(getPlatformInfo).mockRejectedValue(new ApiError("down", 0, "network"));
    render(<ChatApp />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Start the backend/);
  });

  it("New chat clears the conversation, the order and the server session", async () => {
    mockSend.mockResolvedValue(res(plan));
    render(<ChatApp />);
    await userEvent.click(screen.getByRole("button", { name: "Biryani for two under ₹500" }));
    await screen.findByText(/my pick is/);
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(resetSession).toHaveBeenCalledWith("fx4");
    expect(await screen.findByRole("heading", { name: "What are you craving?" })).toBeInTheDocument();
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
  });
});

describe("ChatApp: checkout", () => {
  it("asks for confirmation with buttons, orders only on Yes, then clears the order slip", async () => {
    render(<ChatApp />);
    expect(await screen.findByText(/Demo mode: orders are simulated/)).toBeInTheDocument();

    mockSend.mockResolvedValueOnce(res(checkout));
    await userEvent.type(screen.getByRole("textbox", { name: "Message to Sarah" }), "checkout{Enter}");
    expect(await screen.findByRole("region", { name: "Confirm your order" })).toHaveTextContent("Delivering to Demo Office Park");
    expect(within(screen.getByRole("complementary", { name: "Your order" })).getByText("Masala Dosa")).toBeInTheDocument();
    expect(mockSend).toHaveBeenCalledTimes(1); // nothing was ordered by merely asking

    mockSend.mockResolvedValueOnce(res(ordered));
    await userEvent.click(screen.getByRole("button", { name: "Yes, place order" }));
    expect(mockSend).toHaveBeenLastCalledWith("yes", expect.anything(), expect.anything());
    expect(await screen.findByText(/Order ORD-SIM-0001 is confirmed/)).toBeInTheDocument();
    expect(screen.getByText("simulated")).toBeInTheDocument();
    expect(within(screen.getByRole("complementary", { name: "Your order" })).getByText(/Nothing here yet/)).toBeInTheDocument();
    // the old confirmation card can no longer be used
    expect(screen.getByRole("button", { name: "Yes, place order" })).toBeDisabled();
  });

  it("declining sends 'no'", async () => {
    mockSend.mockResolvedValueOnce(res(checkout));
    render(<ChatApp />);
    await userEvent.type(screen.getByRole("textbox", { name: "Message to Sarah" }), "checkout{Enter}");
    mockSend.mockResolvedValueOnce(res(greet));
    await userEvent.click(await screen.findByRole("button", { name: "No, cancel" }));
    expect(mockSend).toHaveBeenLastCalledWith("no", expect.anything(), expect.anything());
  });

  it("is honest about ordering when the backend cannot place orders", async () => {
    vi.mocked(getPlatformInfo).mockResolvedValue({
      ...(platformInfo as PlatformInfo),
      synthetic: false,
      banner: null,
      capabilities: { ...platformInfo.capabilities, place_order: false },
    } as PlatformInfo);
    render(<ChatApp />);
    expect(await screen.findByText("Sarah can fill your order but can't place it yet.")).toBeInTheDocument();
  });
});

describe("ChatApp: voice", () => {
  it("disables the mic with a clear hint when the browser has no speech recognition", async () => {
    render(<ChatApp />);
    expect(screen.getByRole("button", { name: "Talk to Sarah" })).toBeDisabled();
    expect(await screen.findByText(/Voice input isn't available in this browser/)).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument(); // no speech output either
  });

  it("talk -> live caption -> auto-sends the transcript -> Sarah answers out loud in plain language", async () => {
    enableVoice();
    mockSend.mockResolvedValue(res(plan));
    render(<ChatApp />);
    const mic = screen.getByRole("button", { name: "Talk to Sarah" });
    await waitFor(() => expect(mic).toBeEnabled());
    expect(screen.queryByText(/isn't available/)).not.toBeInTheDocument();

    await userEvent.click(mic);
    expect(synth.cancel).toHaveBeenCalled(); // never talk over Sarah
    expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Listening…")).toBeInTheDocument();

    act(() => FakeRecognition.last!.say("biryani for two", false));
    expect(screen.getByText("biryani for two")).toBeInTheDocument();
    act(() => FakeRecognition.last!.say("Hey Sarah biryani for two under 500", true));
    act(() => FakeRecognition.last!.onend?.());

    await waitFor(() => expect(mockSend).toHaveBeenCalledWith("Hey Sarah biryani for two under 500", undefined, expect.any(AbortSignal)));
    await waitFor(() => expect(spoken).toHaveLength(1));
    expect(spoken[0]).toContain("my pick is Sample Hyderabadi Kitchen");
    expect(spoken[0]).toContain("500 rupees");
    expect(spoken[0]).not.toMatch(/[₹•×★]/);
    expect(screen.getByRole("button", { name: "Talk to Sarah" })).toHaveAttribute("aria-pressed", "false");
  });

  it("typed messages are silent by default and spoken when 'Read replies aloud' is on", async () => {
    enableVoice();
    mockSend.mockResolvedValue(res(greet));
    render(<ChatApp />);
    const box = screen.getByRole("textbox", { name: "Message to Sarah" });
    await userEvent.type(box, "hi{Enter}");
    await screen.findByText(/Hi, I'm Sarah/);
    expect(spoken).toHaveLength(0);

    await userEvent.click(screen.getByRole("switch", { name: "Read replies aloud" }));
    await userEvent.type(box, "hello{Enter}");
    await waitFor(() => expect(spoken).toHaveLength(1));
  });

  it("explains microphone errors", async () => {
    enableVoice();
    render(<ChatApp />);
    const mic = screen.getByRole("button", { name: "Talk to Sarah" });
    await waitFor(() => expect(mic).toBeEnabled());
    await userEvent.click(mic);
    act(() => FakeRecognition.last!.onerror?.({ error: "not-allowed" }));
    act(() => FakeRecognition.last!.onend?.());
    expect(await screen.findByRole("alert")).toHaveTextContent(/Microphone access is blocked/);
  });
});
