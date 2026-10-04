import { describe, expect, it } from "vitest";
import { pickVoice, recognitionErrorMessage, toSpokenText } from "./speech";
import plan from "./fixtures/plan.json";
import restaurants from "./fixtures/restaurants.json";
import items from "./fixtures/items.json";

describe("toSpokenText", () => {
  it("speaks Sarah's real plan reply naturally (no symbols, rupees spelled out)", () => {
    const s = toSpokenText(plan.reply);
    expect(s).toContain("For 2 within 500 rupees, my pick is Sample Hyderabadi Kitchen (4.3 stars, 32 minutes).");
    expect(s).toContain("2 Hyderabadi Veg Biryani, 380 rupees.");
    expect(s).toContain("Subtotal 460 rupees plus delivery 30 rupees, total 490 rupees.");
    expect(s).toContain("That's 10 rupees under your budget of 500 rupees.");
    expect(s).toContain("Option 2: Demo Biryani House, 500 rupees (items, before delivery).");
    for (const ch of ["₹", "•", "×", "—", "★", "(Synthetic)", "\n"]) expect(s).not.toContain(ch);
  });

  it("speaks real list replies", () => {
    expect(toSpokenText(restaurants.reply)).toMatch(/Option 1: Sample Dosa Corner, South Indian, Breakfast/);
    expect(toSpokenText(items.reply)).not.toMatch(/₹|—/);
  });

  it("handles singular minutes, thousands separators and empty input", () => {
    expect(toSpokenText("Arrives in 1 min")).toBe("Arrives in 1 minute.");
    expect(toSpokenText("Total ₹1,250")).toBe("Total 1,250 rupees.");
    expect(toSpokenText("Under ₹500, nice")).toBe("Under 500 rupees, nice.");
    expect(toSpokenText("Fee ₹12.50")).toBe("Fee 12.50 rupees.");
    expect(toSpokenText("  \n ")).toBe("");
  });

  it("caps long replies at a sentence boundary", () => {
    const long = Array.from({ length: 60 }, (_, i) => `Sentence number ${i} is here.`).join(" ");
    const s = toSpokenText(long);
    expect(s.length).toBeLessThanOrEqual(600);
    expect(s.endsWith(".")).toBe(true);
  });
});

describe("recognitionErrorMessage / pickVoice", () => {
  it("maps browser error codes to guidance, and ignores user aborts", () => {
    expect(recognitionErrorMessage("aborted")).toBeNull();
    expect(recognitionErrorMessage("not-allowed")).toMatch(/blocked/);
    expect(recognitionErrorMessage("no-speech")).toMatch(/didn't hear/);
    expect(recognitionErrorMessage("whatever")).toMatch(/stopped unexpectedly/);
  });

  it("prefers en-IN, then any English, else nothing", () => {
    const v = (lang: string, name = lang) => ({ lang, name }) as SpeechSynthesisVoice;
    expect(pickVoice([v("en-US"), v("en-IN"), v("hi-IN")], "en-IN")?.lang).toBe("en-IN");
    expect(pickVoice([v("hi-IN"), v("en_GB")], "en-IN")?.lang).toBe("en_GB");
    expect(pickVoice([v("hi-IN")], "en-IN")).toBeUndefined();
  });
});

describe("toSpokenText for ordering", () => {
  it("reads the order summary and the confirmation question clearly", async () => {
    const { default: checkout } = await import("./fixtures/checkout.json");
    const { default: ordered } = await import("./fixtures/ordered.json");
    const s = toSpokenText(checkout.reply);
    expect(s).toContain("Here's your order from Sample Dosa Corner: 2 Masala Dosa, 180 rupees.");
    expect(s).toContain("Subtotal 180 rupees plus delivery 30 rupees, total 210 rupees.");
    expect(s).toContain("Payment: cash on delivery.");
    expect(s).toContain("Do you want to proceed with placing this order to this address?");
    expect(s).toContain("Say 'yes' to place it or 'no' to cancel.");
    expect(s).not.toMatch(/[₹•×—]|\(Synthetic\)/);
    // short enough that the question is not cut off
    expect(s.length).toBeLessThan(600);
    expect(toSpokenText(ordered.reply)).toContain("Order ORD-SIM-0001 is confirmed. Total 210 rupees");
    expect(toSpokenText(ordered.reply)).toContain("simulated demo order");
  });
});
