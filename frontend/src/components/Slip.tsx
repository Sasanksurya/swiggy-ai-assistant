import { budgetState, cleanName, formatInr } from "@/lib/format";
import type { Cart } from "@/lib/types";

export function Slip({
  cart,
  restaurantName,
  budget,
  open,
  onToggle,
  note = "Sarah can fill your order but can't place it yet.",
}: {
  cart?: Cart;
  restaurantName?: string;
  budget?: number;
  open: boolean;
  onToggle: () => void;
  note?: string;
}) {
  const lines = cart?.lines ?? [];
  const count = lines.reduce((n, l) => n + l.quantity, 0);
  const b = cart && budget ? budgetState(cart.total_inr, budget) : undefined;

  return (
    <aside className="slip" data-open={open} aria-label="Your order">
      <button type="button" className="slip__toggle" onClick={onToggle} aria-expanded={open} aria-controls="slip-body">
        <span>Your order</span>
        <span className="money">{count ? `${count} ${count === 1 ? "item" : "items"}, ${formatInr(cart!.total_inr)}` : "Empty"}</span>
      </button>

      <div id="slip-body" className="slip__body">
        <h2 className="slip__title">Your order</h2>
        {lines.length === 0 ? (
          <p className="slip__empty">Nothing here yet. Ask Sarah for a meal and it appears here.</p>
        ) : (
          <div key={`${cart!.total_inr}-${lines.length}`} className="slip__print">
            {restaurantName && <p className="slip__from">{cleanName(restaurantName)}</p>}
            <ul className="slip__lines">
              {lines.map((l) => (
                <li key={l.item_id}>
                  <span className="slip__qty">{l.quantity}</span>
                  <span className="slip__name">{l.name}</span>
                  <span className="money">{formatInr(l.line_total_inr)}</span>
                </li>
              ))}
            </ul>
            <dl className="slip__sums">
              <div><dt>Items</dt><dd className="money">{formatInr(cart!.subtotal_inr)}</dd></div>
              <div><dt>Delivery</dt><dd className="money">{formatInr(cart!.delivery_fee_inr)}</dd></div>
              <div className="slip__total"><dt>Total</dt><dd className="money">{formatInr(cart!.total_inr)}</dd></div>
            </dl>
            {b && budget && (
              <div className="meter" data-over={b.over > 0}>
                <div className="meter__bar" role="img" aria-label={`${b.percent}% of your ${formatInr(budget)} budget used`}>
                  <span style={{ width: `${b.percent}%` }} />
                </div>
                <p className="meter__label">
                  {formatInr(cart!.total_inr)} of {formatInr(budget)}.{" "}
                  {b.over > 0 ? `${formatInr(b.over)} over budget` : `${formatInr(b.left)} left`}
                </p>
              </div>
            )}
          </div>
        )}
        <p className="slip__note">{note}</p>
      </div>
    </aside>
  );
}
