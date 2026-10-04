import { cleanName, formatInr, statusLabel } from "@/lib/format";
import type { Checkout, MenuItem, OrderInfo, Plan, Restaurant } from "@/lib/types";

type Ask = (text: string) => void;

export function VegMark({ veg }: { veg: boolean }) {
  return (
    <span className={`vegmark ${veg ? "is-veg" : "is-nonveg"}`} role="img" aria-label={veg ? "Vegetarian" : "Non-vegetarian"}>
      <span />
    </span>
  );
}

export function DemoTag({ show }: { show: boolean }) {
  return show ? <span className="demotag" title="Synthetic demo data, not real Swiggy data">demo</span> : null;
}

export function RestaurantList({ restaurants, synthetic, onAsk }: { restaurants: Restaurant[]; synthetic: boolean; onAsk: Ask }) {
  if (!restaurants.length) return null;
  return (
    <ul className="rows" aria-label="Restaurants">
      {restaurants.map((r, i) => (
        <li key={r.id} className="row">
          <div className="row__main">
            <p className="row__title">
              {cleanName(r.name)} <DemoTag show={synthetic} />
            </p>
            <p className="row__meta">
              {r.cuisines.join(", ")}. {r.rating} rating, {r.delivery_time_min} min, about {formatInr(r.price_for_two_inr)} for two
              {r.is_open ? "" : ". Closed now"}
            </p>
          </div>
          <button type="button" className="btn btn--quiet" onClick={() => onAsk(`show the menu of number ${i + 1}`)}>
            See menu
          </button>
        </li>
      ))}
    </ul>
  );
}

export function MenuList({ items, onAsk }: { items: MenuItem[]; onAsk: Ask }) {
  if (!items.length) return null;
  return (
    <ul className="rows" aria-label="Dishes">
      {items.map((it, i) => (
        <li key={it.id} className="row">
          <VegMark veg={it.veg} />
          <div className="row__main">
            <p className="row__title">{it.name}</p>
            <p className="row__meta">{it.category}</p>
          </div>
          <span className="money">{formatInr(it.price_inr)}</span>
          <button type="button" className="btn btn--quiet" onClick={() => onAsk(`add number ${i + 1}`)} aria-label={`Add ${it.name}`}>
            Add
          </button>
        </li>
      ))}
    </ul>
  );
}

export function PlanCard({
  plan,
  alternatives,
  budget,
  people,
  onAsk,
}: {
  plan: Plan;
  alternatives: Plan[];
  budget?: number;
  people?: number;
  onAsk: Ask;
}) {
  const facts = [
    plan.rating != null ? `${plan.rating} rating` : null,
    plan.delivery_time_min != null ? `${plan.delivery_time_min} min` : null,
  ].filter(Boolean);
  return (
    <section className="plan" aria-label="Sarah's pick">
      <p className="plan__lead">
        {people ? `For ${people} ${people === 1 ? "person" : "people"}` : "Sarah's pick"}
        {budget ? `, within ${formatInr(budget)}` : ""}
      </p>
      <p className="plan__name">{cleanName(plan.restaurant_name)}</p>
      <p className="row__meta">{facts.join(", ")}. Added to your order.</p>
      {alternatives.length > 0 && (
        <ul className="rows rows--tight" aria-label="Other options">
          {alternatives.map((alt, i) => (
            <li key={alt.restaurant_id} className="row">
              <div className="row__main">
                <p className="row__title">{cleanName(alt.restaurant_name)}</p>
                <p className="row__meta">{formatInr(alt.subtotal_inr)} for items, before delivery</p>
              </div>
              <button type="button" className="btn btn--quiet" onClick={() => onAsk(`use option ${i + 2}`)}>
                Switch to this
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function OrderCard({ order }: { order: OrderInfo }) {
  return (
    <p className="orderchip">
      <span className="orderchip__id">{order.order_id}</span>
      <span className="orderchip__status">{statusLabel(order.status)}</span>
      {order.simulated && <span className="demotag" title="Nothing was ordered or charged">simulated</span>}
    </p>
  );
}

/** Swiggy requires an explicit yes. The buttons only work while this is the latest message. */
export function CheckoutCard({ checkout, active, onAsk }: { checkout: Checkout; active: boolean; onAsk: Ask }) {
  return (
    <section className="checkout" aria-label="Confirm your order">
      <p className="checkout__lead">Place this order from {cleanName(checkout.restaurant)}?</p>
      <p className="row__meta">
        Total {formatInr(checkout.total_inr)}, cash on delivery. Delivering to {cleanName(checkout.address)}.
      </p>
      <div className="checkout__actions">
        <button type="button" className="btn btn--solid" disabled={!active} onClick={() => onAsk("yes")}>
          Yes, place order
        </button>
        <button type="button" className="btn btn--quiet" disabled={!active} onClick={() => onAsk("no")}>
          No, cancel
        </button>
      </div>
    </section>
  );
}
