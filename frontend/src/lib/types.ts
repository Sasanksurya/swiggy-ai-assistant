/** Mirrors the FastAPI contract (see backend/app/assistant/service.py and graph.py). */

export interface Restaurant {
  id: string;
  name: string;
  cuisines: string[];
  area: string;
  rating: number;
  delivery_time_min: number;
  price_for_two_inr: number;
  is_open: boolean;
}

export interface MenuItem {
  id: string;
  restaurant_id: string;
  name: string;
  price_inr: number;
  veg: boolean;
  category: string;
  available: boolean;
}

export interface CartLine {
  item_id: string;
  name: string;
  quantity: number;
  unit_price_inr: number;
  line_total_inr: number;
}

export interface Cart {
  session_id: string;
  restaurant_id: string | null;
  lines: CartLine[];
  subtotal_inr: number;
  delivery_fee_inr: number;
  total_inr: number;
}

export interface PlanLine {
  item_id: string;
  name: string;
  price_inr: number;
  quantity: number;
  role: "main" | "drink";
}

export interface Plan {
  restaurant_id: string;
  restaurant_name: string;
  rating: number | null;
  delivery_time_min: number | null;
  lines: PlanLine[];
  subtotal_inr: number;
  drinks_ok: boolean;
}

export interface OrderInfo {
  order_id: string;
  status: string;
  restaurant_id?: string;
  restaurant_name?: string;
  items?: { item_id: string; quantity: number; name?: string }[];
  total_inr?: number;
  payment_method?: string;
  delivery_address?: string;
  /** true for orders placed in the mock: nothing was really ordered. */
  simulated?: boolean;
}

/** Shown when Sarah is waiting for an explicit yes before placing an order. */
export interface Checkout {
  restaurant: string;
  address: string;
  payment_method: string;
  total_inr: number;
  requires_confirmation: boolean;
}

export interface Cards {
  restaurants?: Restaurant[];
  restaurant?: Restaurant;
  items?: MenuItem[];
  cart?: Cart;
  plan?: Plan;
  plans?: Plan[];
  order?: OrderInfo;
  checkout?: Checkout;
  /** Added by the backend patch: the budget and group size behind a plan. */
  budget_inr?: number;
  people?: number;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  ok: boolean;
  error_code: string | null;
}

export interface ChatResponse {
  session_id: string;
  assistant_name: string;
  reply: string;
  intent: string;
  entities: Record<string, unknown>;
  cards: Cards;
  tool_calls: ToolCall[];
  source: "mock" | "swiggy";
  /** true => data is not real Swiggy data; the UI must say so. */
  synthetic: boolean;
}

export interface PlatformInfo {
  mode: "mock" | "swiggy";
  synthetic: boolean;
  banner: string | null;
  capabilities: Record<string, boolean>;
}
