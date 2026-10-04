"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { pickVoice, toSpokenText } from "@/lib/speech";

const subscribeNothing = () => () => {};

export function useSpeechSynthesis(lang = "en-IN") {
  const supported = useSyncExternalStore(subscribeNothing, () => "speechSynthesis" in window, () => false);
  const [speaking, setSpeaking] = useState(false);
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    const load = () => {
      voicesRef.current = synth.getVoices();
    };
    load();
    synth.addEventListener?.("voiceschanged", load); // voices arrive asynchronously in Chrome
    return () => {
      synth.removeEventListener?.("voiceschanged", load);
      synth.cancel();
    };
  }, []);

  const cancel = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
      const spoken = toSpokenText(text);
      if (!spoken) return;
      const synth = window.speechSynthesis;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(spoken);
      const voice = pickVoice(voicesRef.current.length ? voicesRef.current : synth.getVoices(), lang);
      if (voice) u.voice = voice;
      u.lang = voice?.lang ?? lang;
      u.rate = 1.02;
      u.onstart = () => setSpeaking(true);
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      synth.speak(u);
    },
    [lang],
  );

  return { supported, speaking, speak, cancel };
}
