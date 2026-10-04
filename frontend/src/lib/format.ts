const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export const formatInr = (n: number): string => `₹${inr.format(n)}`;

/** The mock data tags every name "(Synthetic)"; the UI shows a single demo label instead of repeating it. */
export const cleanName = (name: string): string => name.replace(/\s*\(Synthetic\)/gi, "").trim();

export function statusLabel(status: string): string {
  const s = status.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export interface BudgetState {
  /** 0-100, how much of the budget is used (capped for the bar). */
  percent: number;
  /** Rupees left (>= 0) or 0 when over. */
  left: number;
  /** Rupees over budget (> 0) or 0. */
  over: number;
}

export function budgetState(total: number, budget: number): BudgetState {
  if (budget <= 0) return { percent: 100, left: 0, over: Math.max(total, 0) };
  return {
    percent: Math.min(100, Math.max(0, Math.round((total / budget) * 100))),
    left: Math.max(0, budget - total),
    over: Math.max(0, total - budget),
  };
}
