import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatResponse } from "@/lib/types";
import items from "@/lib/fixtures/items.json";
import order from "@/lib/fixtures/order.json";
import plan from "@/lib/fixtures/plan.json";
import restaurants from "@/lib/fixtures/restaurants.json";
import checkout from "@/lib/fixtures/checkout.json";
import ordered from "@/lib/fixtures/ordered.json";
import { CheckoutCard, MenuList, OrderCard, PlanCard, RestaurantList } from "./Cards";
import { Slip } from "./Slip";

const r = (x: unknown) => x as ChatResponse;

describe("RestaurantList", () => {
  it("shows clean names, a demo tag, facts, and asks for the menu by position", async () => {
    const onAsk = vi.fn();
    render(<RestaurantList restaurants={r(restaurants).cards.restaurants!} synthetic onAsk={onAsk} />);
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText(/Sample Dosa Corner/)).toBeInTheDocument();
    expect(screen.queryByText(/\(Synthetic\)/)).not.toBeInTheDocument();
    expect(within(rows[0]).getByText("demo")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/4\.4 rating, 25 min, about ₹250 for two/)).toBeInTheDocument();
    await userEvent.click(within(rows[0]).getByRole("button", { name: "See menu" }));
    expect(onAsk).toHaveBeenCalledWith("show the menu of number 1");
  });

  it("omits the demo tag for real data and flags closed restaurants", () => {
    const data = [{ ...r(restaurants).cards.restaurants![0], is_open: false }];
    render(<RestaurantList restaurants={data} synthetic={false} onAsk={vi.fn()} />);
    expect(screen.queryByText("demo")).not.toBeInTheDocument();
    expect(screen.getByText(/Closed now/)).toBeInTheDocument();
  });
});

describe("MenuList", () => {
  it("labels veg status for assistive tech and adds by position", async () => {
    const onAsk = vi.fn();
    render(<MenuList items={r(items).cards.items!} onAsk={onAsk} />);
    expect(screen.getAllByRole("img", { name: "Vegetarian" }).length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByRole("button", { name: /^Add / })[1]);
    expect(onAsk).toHaveBeenCalledWith("add number 2");
  });
});

describe("PlanCard", () => {
  const c = r(plan).cards;
  it("explains the pick and offers the other options", async () => {
    const onAsk = vi.fn();
    render(<PlanCard plan={c.plan!} alternatives={c.plans!.slice(1)} budget={500} people={2} onAsk={onAsk} />);
    expect(screen.getByText("For 2 people, within ₹500")).toBeInTheDocument();
    expect(screen.getByText("Sample Hyderabadi Kitchen")).toBeInTheDocument();
    expect(screen.getByText(/4\.3 rating, 32 min/)).toBeInTheDocument();
    expect(screen.getByText(/₹500 for items, before delivery/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Switch to this" }));
    expect(onAsk).toHaveBeenCalledWith("use option 2");
  });
});

describe("OrderCard", () => {
  it("shows the id and a readable status", () => {
    render(<OrderCard order={r(order).cards.order!} />);
    expect(screen.getByText("ORD-DEMO-1002")).toBeInTheDocument();
    expect(screen.getByText("Out for delivery")).toBeInTheDocument();
  });
});

describe("CheckoutCard", () => {
  const c = r(checkout).cards.checkout!;

  it("shows what will be ordered and where, and answers with yes or no", async () => {
    const onAsk = vi.fn();
    render(<CheckoutCard checkout={c} active onAsk={onAsk} />);
    expect(screen.getByText("Place this order from Sample Dosa Corner?")).toBeInTheDocument();
    expect(screen.getByText(/Total ₹210, cash on delivery\. Delivering to Demo Office Park, Demo Area B\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, place order" }));
    await userEvent.click(screen.getByRole("button", { name: "No, cancel" }));
    expect(onAsk.mock.calls).toEqual([["yes"], ["no"]]);
  });

  it("cannot be used once the conversation has moved on", async () => {
    const onAsk = vi.fn();
    render(<CheckoutCard checkout={c} active={false} onAsk={onAsk} />);
    expect(screen.getByRole("button", { name: "Yes, place order" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "No, cancel" })).toBeDisabled();
  });
});

describe("OrderCard for a simulated order", () => {
  it("is clearly labelled as simulated", () => {
    render(<OrderCard order={r(ordered).cards.order!} />);
    expect(screen.getByText("ORD-SIM-0001")).toBeInTheDocument();
    expect(screen.getByText("simulated")).toHaveAttribute("title", "Nothing was ordered or charged");
  });
});

describe("Slip", () => {
  const cart = r(plan).cards.cart!;
  const slip = (over: Partial<Parameters<typeof Slip>[0]> = {}) =>
    render(<Slip cart={cart} restaurantName="Sample Hyderabadi Kitchen (Synthetic)" budget={500} open onToggle={vi.fn()} {...over} />);

  it("prints the order like a receipt with totals taken from the cart", () => {
    slip();
    expect(screen.getByText("Sample Hyderabadi Kitchen")).toBeInTheDocument();
    expect(screen.getByText("Hyderabadi Veg Biryani")).toBeInTheDocument();
    expect(screen.getByText("₹380")).toBeInTheDocument();
    expect(screen.getByText("Soft Drink (Cola)")).toBeInTheDocument();
    const total = screen.getByText("Total").closest("div")!;
    expect(within(total).getByText("₹490")).toBeInTheDocument();
    expect(screen.getByText("Delivery").closest("div")).toHaveTextContent("₹30");
  });

  it("shows the budget meter with what is left", () => {
    slip();
    expect(screen.getByText(/₹490 of ₹500\./)).toHaveTextContent("₹10 left");
    expect(screen.getByRole("img", { name: "98% of your ₹500 budget used" })).toBeInTheDocument();
  });

  it("says plainly when the order is over budget", () => {
    slip({ budget: 450 });
    expect(screen.getByText(/₹490 of ₹450\./)).toHaveTextContent("₹40 over budget");
  });

  it("has no meter without a budget, an empty state, and an honest note", () => {
    const { unmount } = slip({ budget: undefined });
    expect(screen.queryByText(/ of ₹/)).not.toBeInTheDocument();
    expect(screen.getByText("Sarah can fill your order but can't place it yet.")).toBeInTheDocument();
    unmount();
    slip({ cart: undefined });
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
  });

  it("shows a custom note", () => {
    slip({ note: "Demo mode: orders are simulated. Nothing is ordered or charged." });
    expect(screen.getByText(/Demo mode: orders are simulated/)).toBeInTheDocument();
  });

  it("summarises on the collapsed bar and toggles", async () => {
    const onToggle = vi.fn();
    slip({ open: false, onToggle });
    const bar = screen.getByRole("button", { name: /Your order/ });
    expect(bar).toHaveTextContent("4 items, ₹490");
    expect(bar).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(bar);
    expect(onToggle).toHaveBeenCalled();
  });
});
