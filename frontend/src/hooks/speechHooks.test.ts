import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { useSpeechSynthesis } from "./useSpeechSynthesis";

class FakeRecognition {
  static last: FakeRecognition | undefined;
  lang = ""; continuous = true; interimResults = false; maxAlternatives = 0;
  onstart: (() => void) | null = null;
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn();
  constructor() { FakeRecognition.last = this; }
  say(text: string, isFinal: boolean) {
    this.onresult?.({ resultIndex: 0, results: { length: 1, 0: { isFinal, 0: { transcript: text } } } });
  }
}

describe("useSpeechRecognition", () => {
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
    FakeRecognition.last = undefined;
  });

  it("reports unsupported browsers and does nothing on start", () => {
    const { result } = renderHook(() => useSpeechRecognition({ onFinal: vi.fn() }));
    expect(result.current.supported).toBe(false);
    act(() => result.current.start());
    expect(result.current.listening).toBe(false);
  });

  it("listens, shows interim text, and delivers the final transcript exactly once", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const onFinal = vi.fn();
    const { result } = renderHook(() => useSpeechRecognition({ onFinal }));
    expect(result.current.supported).toBe(true);
    act(() => result.current.start());
    const rec = FakeRecognition.last!;
    expect(rec).toMatchObject({ lang: "en-IN", continuous: false, interimResults: true });
    expect(result.current.listening).toBe(true);
    act(() => rec.say("biryani for", false));
    expect(result.current.interim).toBe("biryani for");
    act(() => rec.say("biryani for two under 500", true));
    act(() => rec.say("biryani for two under 500", true)); // a duplicate final event must not double-send
    expect(onFinal).toHaveBeenCalledTimes(1);
    expect(onFinal).toHaveBeenCalledWith("biryani for two under 500");
    act(() => rec.onend?.());
    expect(result.current).toMatchObject({ listening: false, interim: "" });
  });

  it("explains errors, ignores aborts, and allows listening again afterwards", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { result } = renderHook(() => useSpeechRecognition({ onFinal: vi.fn() }));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.onerror?.({ error: "not-allowed" }));
    expect(result.current.error).toMatch(/blocked/);
    act(() => FakeRecognition.last!.onend?.());
    act(() => result.current.start());
    expect(result.current.error).toBeNull(); // cleared when listening restarts
    act(() => FakeRecognition.last!.onerror?.({ error: "aborted" }));
    expect(result.current.error).toBeNull();
  });

  it("does not start a second recognizer while one is active, and stop() ends it", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { result } = renderHook(() => useSpeechRecognition({ onFinal: vi.fn() }));
    act(() => result.current.start());
    const first = FakeRecognition.last;
    act(() => result.current.start());
    expect(FakeRecognition.last).toBe(first);
    act(() => result.current.stop());
    expect(result.current.listening).toBe(false);
  });
});

describe("useSpeechSynthesis", () => {
  const spoken: { text: string; voice?: unknown; lang: string }[] = [];
  const synth = {
    speak: vi.fn((u: { text: string; voice?: unknown; lang: string; onstart?: () => void }) => {
      spoken.push(u);
      u.onstart?.();
    }),
    cancel: vi.fn(),
    getVoices: vi.fn(() => [{ lang: "en-US" }, { lang: "en-IN", name: "India" }]),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };

  beforeEach(() => {
    spoken.length = 0;
    vi.clearAllMocks();
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
    vi.stubGlobal("SpeechSynthesisUtterance", class { text: string; lang = ""; rate = 1; voice?: unknown; constructor(t: string) { this.text = t; } });
  });
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).speechSynthesis;
    vi.unstubAllGlobals();
  });

  it("speaks the spoken-form of a reply with the Indian-English voice and cancels earlier speech", () => {
    const { result } = renderHook(() => useSpeechSynthesis());
    expect(result.current.supported).toBe(true);
    act(() => result.current.speak("Total ₹490"));
    expect(synth.cancel).toHaveBeenCalled();
    expect(spoken[0]).toMatchObject({ text: "Total 490 rupees.", lang: "en-IN" });
    expect(result.current.speaking).toBe(true);
    act(() => result.current.cancel());
    expect(result.current.speaking).toBe(false);
  });

  it("stays silent for empty text and is safe when unsupported", () => {
    const { result } = renderHook(() => useSpeechSynthesis());
    act(() => result.current.speak("   "));
    expect(synth.speak).not.toHaveBeenCalled();
    delete (window as unknown as Record<string, unknown>).speechSynthesis;
    const r2 = renderHook(() => useSpeechSynthesis());
    expect(r2.result.current.supported).toBe(false);
    expect(() => act(() => r2.result.current.speak("hi"))).not.toThrow();
  });
});
