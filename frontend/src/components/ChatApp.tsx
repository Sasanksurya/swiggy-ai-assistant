"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getPlatformInfo } from "@/lib/api";
import { cleanName, formatInr } from "@/lib/format";
import type { ChatResponse, PlatformInfo, Plan } from "@/lib/types";
import { budgetOf, peopleOf, useChat, type ChatMessage } from "@/hooks/useChat";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "@/hooks/useSpeechSynthesis";
import { CheckoutCard, MenuList, OrderCard, PlanCard, RestaurantList } from "./Cards";
import { Slip } from "./Slip";

const SUGGESTIONS = [
  "Biryani for two under ₹500",
  "Veg items under ₹100",
  "Dosa restaurants",
  "Where is order ORD-DEMO-1002?",
];

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function Cards({ r, active, onAsk }: { r: ChatResponse; active: boolean; onAsk: (t: string) => void }) {
  const { cards } = r;
  const plans = cards.plans ?? [];
  return (
    <>
      {cards.restaurants && <RestaurantList restaurants={cards.restaurants} synthetic={r.synthetic} onAsk={onAsk} />}
      {cards.items && <MenuList items={cards.items} onAsk={onAsk} />}
      {cards.plan && (
        <PlanCard plan={cards.plan} alternatives={plans.slice(1)} budget={budgetOf(r)} people={peopleOf(r)} onAsk={onAsk} />
      )}
      {!cards.plan && plans.length > 0 && <PlanChoices plans={plans} onAsk={onAsk} />}
      {cards.checkout?.requires_confirmation && <CheckoutCard checkout={cards.checkout} active={active} onAsk={onAsk} />}
      {cards.order && <OrderCard order={cards.order} />}
    </>
  );
}

/** Options Sarah found but did not add (the order already had items). */
function PlanChoices({ plans, onAsk }: { plans: Plan[]; onAsk: (t: string) => void }) {
  return (
    <ul className="rows" aria-label="Meal options">
      {plans.map((p, i) => (
        <li key={p.restaurant_id} className="row">
          <div className="row__main">
            <p className="row__title">{cleanName(p.restaurant_name)}</p>
            <p className="row__meta">{formatInr(p.subtotal_inr)} for items, before delivery</p>
          </div>
          <button type="button" className="btn btn--quiet" onClick={() => onAsk(`use option ${i + 1}`)}>
            Use this
          </button>
        </li>
      ))}
    </ul>
  );
}

function Message({ m, active, onAsk, onRetry }: { m: ChatMessage; active: boolean; onAsk: (t: string) => void; onRetry: (id: string) => void }) {
  if (m.role === "user") {
    return (
      <div className="msg msg--user">
        <p>{m.text}</p>
      </div>
    );
  }
  if (m.role === "error") {
    return (
      <div className="msg msg--error" role="alert">
        <p>{m.text}</p>
        <button type="button" className="btn btn--quiet" onClick={() => onRetry(m.id)}>
          Try again
        </button>
      </div>
    );
  }
  return (
    <article className="msg msg--sarah">
      <p className="msg__who">{m.response.assistant_name}</p>
      <p className="msg__text">{m.text}</p>
      <Cards r={m.response} active={active} onAsk={onAsk} />
    </article>
  );
}

export function ChatApp() {
  const [info, setInfo] = useState<PlatformInfo | null>(null);
  const [offline, setOffline] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const [draft, setDraft] = useState("");
  const [slipOpen, setSlipOpen] = useState(false);
  const readAloudRef = useRef(readAloud);
  useEffect(() => {
    readAloudRef.current = readAloud;
  }, [readAloud]);
  const endRef = useRef<HTMLDivElement>(null);

  const synth = useSpeechSynthesis();
  const chat = useChat({
    onReply: (res, via) => {
      if (via === "voice" || readAloudRef.current) synth.speak(res.reply);
    },
  });
  const rec = useSpeechRecognition({ onFinal: (text) => void chat.send(text, "voice") });

  useEffect(() => {
    const ctrl = new AbortController();
    getPlatformInfo(ctrl.signal)
      .then((i) => {
        setInfo(i);
        setOffline(false);
      })
      .catch((e) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) setOffline(true);
      });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "end" });
  }, [chat.messages, chat.sending]);

  const restaurantNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const m of chat.messages) {
      if (m.role !== "sarah") continue;
      const c = m.response.cards;
      c.restaurants?.forEach((r) => (names[r.id] = r.name));
      if (c.restaurant) names[c.restaurant.id] = c.restaurant.name;
      c.plans?.forEach((p) => (names[p.restaurant_id] = p.restaurant_name));
    }
    return names;
  }, [chat.messages]);

  const ask = (text: string) => {
    synth.cancel();
    void chat.send(text, "text");
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || chat.sending) return;
    ask(draft);
    setDraft("");
  };

  const toggleMic = () => {
    if (rec.listening) return rec.stop();
    synth.cancel(); // never listen while Sarah is talking
    rec.start();
  };

  const empty = chat.messages.length === 0;
  const lastId = chat.messages.at(-1)?.id;
  const canOrder = !!info?.capabilities?.place_order;
  const slipNote = !canOrder
    ? undefined
    : info?.synthetic
      ? "Demo mode: orders are simulated. Nothing is ordered or charged."
      : "Sarah places your order only after you confirm it.";

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1 className="top__name">Sarah</h1>
          <p className="top__sub">Your food assistant</p>
        </div>
        <div className="top__actions">
          {synth.supported && (
            <label className="switch">
              <input type="checkbox" role="switch" checked={readAloud} onChange={(e) => { setReadAloud(e.target.checked); if (!e.target.checked) synth.cancel(); }} />
              <span>Read replies aloud</span>
            </label>
          )}
          <button type="button" className="btn btn--quiet" onClick={() => { synth.cancel(); void chat.reset(); }} disabled={empty && !chat.sessionId}>
            New chat
          </button>
        </div>
      </header>

      {info?.synthetic && info.banner && (
        <p className="banner" role="note">
          {info.banner}
        </p>
      )}
      {offline && (
        <p className="banner banner--error" role="alert">
          Sarah&apos;s server isn&apos;t responding. Start the backend, then refresh this page.
        </p>
      )}

      <div className="layout">
        <main className="chat">
          <div className="thread" role="log" aria-live="polite" aria-label="Conversation with Sarah">
            {empty ? (
              <section className="welcome">
                <h2>What are you craving?</h2>
                <p>Tell Sarah the dish, how many people are eating, and your budget. She finds the restaurant and fills your order.</p>
                <ul className="chips" aria-label="Try asking">
                  {SUGGESTIONS.map((s) => (
                    <li key={s}>
                      <button type="button" className="chip" onClick={() => ask(s)} disabled={chat.sending}>
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : (
              chat.messages.map((m) => (
                <Message key={m.id} m={m} active={m.id === lastId && !chat.sending} onAsk={ask} onRetry={(id) => void chat.retry(id)} />
              ))
            )}
            {chat.sending && <p className="thinking">Sarah is thinking…</p>}
            <div ref={endRef} />
          </div>

          <div className="composer-wrap">
            {rec.listening && (
              <p className="caption" aria-live="polite">
                {rec.interim || "Listening…"}
              </p>
            )}
            {rec.error && (
              <p className="hint hint--error" role="alert">
                {rec.error}
              </p>
            )}
            {rec.checked && !rec.supported && (
              <p className="hint">Voice input isn&apos;t available in this browser. Try Chrome or Edge, or type your message.</p>
            )}
            <form className="composer" onSubmit={submit}>
              <button
                type="button"
                className="mic"
                data-listening={rec.listening}
                onClick={toggleMic}
                disabled={!rec.supported}
                aria-pressed={rec.listening}
                aria-label={rec.listening ? "Stop listening" : "Talk to Sarah"}
              >
                <MicIcon />
              </button>
              <input
                className="composer__input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type a message, or tap the mic"
                aria-label="Message to Sarah"
                maxLength={500}
                autoComplete="off"
              />
              <button type="submit" className="btn btn--solid" disabled={chat.sending || !draft.trim()}>
                Send
              </button>
            </form>
          </div>
        </main>

        <Slip
          cart={chat.cart}
          restaurantName={chat.cart?.restaurant_id ? restaurantNames[chat.cart.restaurant_id] : undefined}
          budget={chat.budget}
          note={slipNote}
          open={slipOpen}
          onToggle={() => setSlipOpen((o) => !o)}
        />
      </div>
    </div>
  );
}
