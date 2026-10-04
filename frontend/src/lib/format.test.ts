import { describe, expect, it } from "vitest";
import { budgetState, cleanName, formatInr, statusLabel } from "./format";

describe("format", () => {
  it("formats rupees with Indian digit grouping", () => {
    expect(formatInr(490)).toBe("₹490");
    expect(formatInr(125000)).toBe("₹1,25,000");
    expect(formatInr(12.5)).toBe("₹12.5");
  });
  it("cleans names and statuses", () => {
    expect(cleanName("Demo Biryani House (Synthetic)")).toBe("Demo Biryani House");
    expect(cleanName("Plain")).toBe("Plain");
    expect(statusLabel("OUT_FOR_DELIVERY")).toBe("Out for delivery");
  });
  it("computes budget usage", () => {
    expect(budgetState(490, 500)).toEqual({ percent: 98, left: 10, over: 0 });
    expect(budgetState(530, 500)).toEqual({ percent: 100, left: 0, over: 30 });
    expect(budgetState(0, 500)).toEqual({ percent: 0, left: 500, over: 0 });
    expect(budgetState(100, 0)).toMatchObject({ over: 100 });
  });
});
