"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, resetSession, sendChat } from "@/lib/api";
import type { Cart, ChatResponse, Plan } from "@/lib/types";

export type Via = "voice" | "text";

export type ChatMessage =
  | { id: string; role: "user"; text: string; via: Via }
  | { id: string; role: "sarah"; text: string; response: ChatResponse }
  | { id: string; role: "error"; text: string; retryText: string; via: Via };

/** The budget behind a plan: explicit from the backend, else what the user said on that turn. */
export function budgetOf(r: ChatResponse): number | undefined {
  if (typeof r.cards.budget_inr === "number") return r.cards.budget_inr;
  const m = r.entities.max_price;
  return r.intent === "plan_meal" && typeof m === "number" ? m : undefined;
}

/** Group size behind a plan: explicit from the backend, else what the user said on that turn. */
export function peopleOf(r: ChatResponse): number | undefined {
  const p = r.cards.people ?? r.entities.people;
  return typeof p === "number" ? p : undefined;
}

export interface UseChatOptions {
  onReply?: (response: ChatResponse, via: Via) => void;
}

export function useChat(options: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const idRef = useRef(0);
  const busyRef = useRef(false);
  const sessionRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const onReplyRef = useRef(options.onReply);
  useEffect(() => {
    onReplyRef.current = options.onReply; // always call the latest callback, without reading refs while rendering
  });

  const nextId = () => `m${++idRef.current}`;

  const run = useCallback(async (text: string, via: Via, addUser: boolean) => {
    const clean = text.trim();
    if (!clean || busyRef.current) return;
    busyRef.current = true;
    setSending(true);
    if (addUser) setMessages((m) => [...m, { id: nextId(), role: "user", text: clean, via }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await sendChat(clean, sessionRef.current, ctrl.signal);
      sessionRef.current = res.session_id;
      setSessionId(res.session_id);
      setMessages((m) => [...m, { id: nextId(), role: "sarah", text: res.reply, response: res }]);
      onReplyRef.current?.(res, via);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
      setMessages((m) => [...m, { id: nextId(), role: "error", text: msg, retryText: clean, via }]);
    } finally {
      busyRef.current = false;
      setSending(false);
    }
  }, []);

  const send = useCallback((text: string, via: Via = "text") => run(text, via, true), [run]);

  const retry = useCallback(
    (id: string) => {
      const failed = messages.find((m) => m.id === id);
      if (!failed || failed.role !== "error" || busyRef.current) return;
      setMessages((m) => m.filter((x) => x.id !== id));
      return run(failed.retryText, failed.via, false); // the user's message is already on screen
    },
    [messages, run],
  );

  const reset = useCallback(async () => {
    abortRef.current?.abort();
    busyRef.current = false;
    setSending(false);
    const old = sessionRef.current;
    sessionRef.current = undefined;
    setSessionId(undefined);
    setMessages([]);
    if (old) await resetSession(old).catch(() => undefined); // best effort; a new id is used regardless
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const { cart, plan, budget, people } = useMemo(() => {
    let cart: Cart | undefined;
    let plan: Plan | undefined;
    let budget: number | undefined;
    let people: number | undefined;
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "sarah") continue;
      cart ??= m.response.cards.cart;
      if (!plan && m.response.cards.plan) {
        plan = m.response.cards.plan;
        budget = budgetOf(m.response);
        people = peopleOf(m.response);
      }
      if (cart && plan) break;
    }
    return { cart, plan, budget, people };
  }, [messages]);

  return { messages, sending, sessionId, cart, plan, budget, people, send, retry, reset };
}
